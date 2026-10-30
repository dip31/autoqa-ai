"""
OWASP ZAP Baseline Scan Adapter for AutoQA AI.

Provides a controlled wrapper around the official ZAP Docker image to execute
passive baseline scans against authorized targets.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from agentqe.interfaces import Finding
from agentqe.security.authorization.authorization_repository import get_authorization
from agentqe.security.evidence import EvidenceCollector
from agentqe.security.finding_classifier import classify_findings
from database.db import execute_query

logger = logging.getLogger(__name__)

# ZAP Docker image (pinned version for reproducibility)
ZAP_DOCKER_IMAGE = os.getenv("ZAP_DOCKER_IMAGE", "owasp/zap2docker-stable:2.14.0")
# Maximum scan duration (seconds)
MAX_SCAN_DURATION = int(os.getenv("ZAP_MAX_DURATION", "300"))
# Temporary directory for ZAP output
ZAP_TMP_DIR = os.getenv("ZAP_TMP_DIR", tempfile.gettempdir())


@dataclass
class ZapScanResult:
    success: bool
    findings: List[Finding]
    raw_alerts: List[Dict[str, Any]]
    error: Optional[str] = None
    duration_seconds: float = 0.0
    timed_out: bool = False
    cancelled: bool = False


def _check_docker_available() -> bool:
    """Return True if Docker CLI is available and daemon reachable."""
    try:
        subprocess.run(["docker", "version"], check=True, capture_output=True, timeout=10)
        return True
    except Exception:
        return False


def _pull_zap_image() -> bool:
    """Pull the ZAP Docker image if not present locally."""
    try:
        subprocess.run(["docker", "pull", ZAP_DOCKER_IMAGE], check=True, capture_output=True, timeout=120)
        return True
    except Exception as exc:
        logger.error("Failed to pull ZAP image %s: %s", ZAP_DOCKER_IMAGE, exc)
        return False


def _run_zap_baseline(target_url: str, output_dir: str) -> subprocess.CompletedProcess:
    """
    Execute ZAP Baseline Scan via Docker.

    Uses the official baseline scan command:
    docker run -t --rm -v $(pwd):/zap/wrk/:rw -u root owasp/zap2docker-stable zap-baseline.py -t <target> -J report.json -r report.html
    """
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{output_dir}:/zap/wrk/:rw",
        "-u", "root",
        ZAP_DOCKER_IMAGE,
        "zap-baseline.py",
        "-t", target_url,
        "-J", "report.json",
        "-r", "report.html",
        "-d",  # do not fail on warnings
    ]
    logger.info("Running ZAP baseline scan: %s", " ".join(cmd))
    return subprocess.run(cmd, capture_output=True, text=True, timeout=MAX_SCAN_DURATION)


def _parse_zap_json(report_path: str) -> List[Dict[str, Any]]:
    """Parse ZAP JSON report and return list of alerts."""
    try:
        with open(report_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # ZAP baseline JSON structure: {"site": [...], "alerts": [...]}
        alerts = data.get("alerts", [])
        return alerts
    except Exception as exc:
        logger.error("Failed to parse ZAP JSON report %s: %s", report_path, exc)
        return []


def _normalize_zap_alert(alert: Dict[str, Any], run_id: int, collector: EvidenceCollector) -> Finding:
    """Convert a ZAP alert dict into an AutoQA Finding (generic interface)."""
    # Map ZAP risk levels to internal severity
    risk_map = {
        "High": "High",
        "Medium": "Medium",
        "Low": "Low",
        "Informational": "Informational",
    }
    severity = risk_map.get(alert.get("risk", "Informational"), "Informational")
    confidence_raw = alert.get("confidence", 1)
    try:
        confidence = int(confidence_raw)
    except (TypeError, ValueError):
        confidence = 1
    # Normalize confidence 0-3 to 0.0-1.0
    conf_score = max(0.0, min(1.0, confidence / 3.0))

    # Build evidence dict for generic Finding
    evidence_dict = {
        "evidence": alert.get("evidence", ""),
        "instances": alert.get("instances", []),
        "reference": alert.get("reference", ""),
        "solution": alert.get("solution", ""),
        "cwe": alert.get("cweid"),
        "wasc": alert.get("wascid"),
        "param": alert.get("param"),
        "attack": alert.get("attack"),
    }

    finding = Finding(
        finding_id=str(uuid.uuid4()),
        category=alert.get("name", "ZAP Alert"),
        severity=severity,
        description=alert.get("description", ""),
        evidence=evidence_dict,
        source="OWASP ZAP",
        status="OPEN",
        metadata={
            "zap_alert_id": alert.get("pluginid"),
            "confidence": conf_score,
        },
        classification=alert.get("name", "ZAP Alert"),
    )
    # Attach evidence to collector for persistence (optional)
    for inst in alert.get("instances", []):
        collector.add(
            finding_id=finding.finding_id,
            evidence_type="http_response",
            url=inst.get("uri", ""),
            method=inst.get("method", "GET"),
            status_code=inst.get("status", 0),
            data={"evidence": inst.get("evidence", ""), "snippet": inst.get("snippet", "")},
        )
    return finding


def run_zap_baseline_scan(run_id: int, target_url: str, user_id: int) -> ZapScanResult:
    """
    High-level function to run ZAP baseline scan for a given run.

    Steps:
    1. Verify ZAP enabled flag.
    2. Verify Docker availability.
    3. Pull ZAP image if needed.
    4. Create temporary directory for output.
    5. Run ZAP baseline scan.
    6. Parse JSON output.
    7. Normalize alerts into Findings.
    8. Persist findings & evidence via existing DB helpers.
    9. Return structured result.
    """
    start_ts = time.time()
    # Feature gate: ZAP_ENABLED (default false)
    zap_enabled = os.getenv("ZAP_ENABLED", "false").lower() in ("1", "true", "yes")
    if not zap_enabled:
        return ZapScanResult(
            success=False,
            findings=[],
            raw_alerts=[],
            error="ZAP_DISABLED",
            duration_seconds=time.time() - start_ts,
        )
    if not _check_docker_available():
        return ZapScanResult(
            success=False,
            findings=[],
            raw_alerts=[],
            error="Docker not available or daemon unreachable",
            duration_seconds=time.time() - start_ts,
        )

    if not _pull_zap_image():
        return ZapScanResult(
            success=False,
            findings=[],
            raw_alerts=[],
            error="Failed to pull ZAP Docker image",
            duration_seconds=time.time() - start_ts,
        )

    with tempfile.TemporaryDirectory(dir=ZAP_TMP_DIR, prefix=f"zap_{run_id}_") as tmpdir:
        try:
            proc = _run_zap_baseline(target_url, tmpdir)
        except subprocess.TimeoutExpired:
            return ZapScanResult(
                success=False,
                findings=[],
                raw_alerts=[],
                error="ZAP scan timed out",
                duration_seconds=time.time() - start_ts,
                timed_out=True,
            )
        except Exception as exc:
            return ZapScanResult(
                success=False,
                findings=[],
                raw_alerts=[],
                error=f"ZAP execution error: {exc}",
                duration_seconds=time.time() - start_ts,
            )

        # ZAP baseline returns non-zero exit code when alerts found; treat as success if JSON exists
        json_path = os.path.join(tmpdir, "report.json")
        if not os.path.exists(json_path):
            logger.error("ZAP JSON report missing. stdout: %s stderr: %s", proc.stdout, proc.stderr)
            return ZapScanResult(
                success=False,
                findings=[],
                raw_alerts=[],
                error="ZAP did not produce JSON report",
                duration_seconds=time.time() - start_ts,
            )

        alerts = _parse_zap_json(json_path)
        # If JSON existed but parsing yielded no alerts and file not empty, treat as failure
        if not alerts and os.path.getsize(json_path) > 0:
            return ZapScanResult(
                success=False,
                findings=[],
                raw_alerts=[],
                error="ZAP JSON report could not be parsed",
                duration_seconds=time.time() - start_ts,
            )
        collector = EvidenceCollector(run_id)
        findings = [_normalize_zap_alert(a, run_id, collector) for a in alerts]

        # Deduplicate / classify using existing pipeline
        classified = classify_findings(findings)

# Persist findings & evidence (reuse logic from security_runner)
        for f in classified:
            fid = execute_query(
                """INSERT INTO security_findings
                   (run_id, validator_id, finding_type, title, description,
                    severity, confidence, affected_url, evidence, recommendation, classification,
                    check_type, active_check_id, execution_phase)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    "zap_baseline",
                    f.category,
                    f.category,  # title
                    f.description,
                    f.severity,
                    f.metadata.get("confidence", 0.5),
                    f.metadata.get("instances", [{}])[0].get("uri", "") if f.metadata.get("instances") else "",
                    str(f.evidence),
                    f.metadata.get("solution", ""),
                    f.classification,
"passive",
                        None,
                        "passive",
                    ),
                )
            # Persist evidence
            for ev in collector.get_all():
                if ev.finding_id == f.finding_id:
                    execute_query(
                        """INSERT INTO security_evidence
                           (finding_id, evidence_type, url, method, status_code, data, check_type, active_check_id)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (fid, ev.evidence_type, ev.url, ev.method, ev.status_code, str(ev.data),
                         getattr(ev, 'check_type', 'passive'), getattr(ev, 'active_check_id', None)),
                    )

        duration = time.time() - start_ts
        return ZapScanResult(
            success=True,
            findings=classified,
            raw_alerts=alerts,
            duration_seconds=duration,
        )