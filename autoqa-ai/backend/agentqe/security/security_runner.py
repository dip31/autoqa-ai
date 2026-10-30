"""
SecurityRunner – orchestrates a security validation run.

Steps:
1. Load run record (must be run_type='security' and owned by user).
2. Re‑run preflight (target authorization, scope, DNS/IP safety).
3. Build ValidationContext.
4. Launch Playwright browser with a request‑interception guard that enforces scope
   and network‑safety for every navigation/sub‑resource.
5. Execute each registered validator (passive – they use requests/ssl, not browser).
6. Collect findings, deduplicate, persist.
7. Update run status.
"""
from __future__ import annotations

import time
import logging
import threading
import json
import os
import sqlite3
from typing import List, Dict, Any, Optional
from contextlib import contextmanager

from database.db import execute_query, DB_PATH
from agentqe.interfaces import Finding
from agentqe.security.security_preflight import run_preflight, PreflightDecision
from agentqe.security.security_config import CONFIG
from agentqe.security.models import SecurityRun, SecurityFinding, ValidatorResult
from agentqe.security.evidence import EvidenceCollector
from agentqe.security.finding_classifier import classify_findings
from agentqe.security.validators import _validator_modules as _validator_names, _validator_class_names
from agentqe.security.validators.base import BaseValidator, ValidationContext
from agentqe.interfaces import registry, ISecurityValidator
from agentqe.security.scope_validator import ScopeDefinition, validate_url_scope
from agentqe.security.network_safety import resolve_hostname, classify_ip_address
from agentqe.security.authorization.authorization_repository import get_verified_authorization

# Phase 5A imports
from agentqe.security.active_testing_policy import ActiveTestingPolicy, ActiveTestingContext, PolicyDecision
from agentqe.security.active_testing_profiles import get_profile_limits, validate_profile
from agentqe.security.execution_budgets import get_budget_manager, BudgetManager, BudgetConfig, check_budget
from agentqe.security.audit_logging import (
    get_audit_logger, log_assessment_created, log_assessment_started, log_assessment_completed,
    log_assessment_failed, log_assessment_cancelled, log_policy_evaluated,
    log_policy_allowed, log_policy_denied, log_confirmation_requested,
    log_confirmation_given, log_execution_budget_exceeded, log_network_blocked,
    log_dry_run_requested, AuditEventType
)

# ZAP integration
from agentqe.security.integrations.zap_adapter import run_zap_baseline_scan, ZapScanResult

# Playwright imports for browser-based validation
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    sync_playwright = None

logger = logging.getLogger(__name__)


# Global cancellation flag for running assessments
_cancellation_flags: Dict[int, bool] = {}
_cancellation_lock = threading.Lock()


def is_cancelled(run_id: int) -> bool:
    """Check if a run has been cancelled."""
    with _cancellation_lock:
        return _cancellation_flags.get(run_id, False)


def set_cancelled(run_id: int, cancelled: bool = True) -> None:
    """Set cancellation flag for a run."""
    with _cancellation_lock:
        _cancellation_flags[run_id] = cancelled


def clear_cancellation(run_id: int) -> None:
    """Clear cancellation flag for a run."""
    with _cancellation_lock:
        _cancellation_flags.pop(run_id, None)


# ----------------------------------------------------------------------
# Database helper with retry logic for SQLite locking issues
# ----------------------------------------------------------------------
@contextmanager
def db_connection():
    """Context manager for database connection with retry logic for SQLite locks."""
    max_retries = 5
    base_delay = 0.1  # 100ms
    
    for attempt in range(max_retries):
        conn = None
        try:
            db_host = os.getenv("DB_HOST")
            is_mysql = db_host and db_host != "localhost"
            
            if is_mysql:
                import mysql.connector
                conn = mysql.connector.connect(
                    host=os.getenv("DB_HOST"),
                    user=os.getenv("DB_USER"),
                    password=os.getenv("DB_PASSWORD"),
                    database=os.getenv("DB_NAME"),
                    get_warnings=True,
                    charset="utf8mb4",
                    collation="utf8mb4_unicode_ci",
                )
                conn.autocommit = True
                yield conn
                return
            else:
                conn = sqlite3.connect(DB_PATH, timeout=30.0)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA busy_timeout = 30000")  # 30 second busy timeout
                yield conn
                return
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # exponential backoff
                    logger.warning(f"Database locked, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
            raise
        except Exception:
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
        break
    else:
        raise RuntimeError("Max retries exceeded for database connection")


def execute_query_with_retry(query: str, params=None, fetch=False, max_retries: int = 3):
    """Execute query with retry logic for database locks."""
    for attempt in range(max_retries):
        try:
            with db_connection() as conn:
                cursor = conn.cursor()
                
                # SQLite uses '?' as placeholder
                cursor.execute(query, params or ())
                
                if fetch:
                    rows = cursor.fetchall()
                    result = [dict(row) for row in rows]
                else:
                    result = None
                
                conn.commit()
                last_id = cursor.lastrowid
                return result if fetch else last_id
                
        except sqlite3.OperationalError as e:
            if "locked" in str(e).lower() or "busy" in str(e).lower():
                if attempt < max_retries - 1:
                    delay = 0.1 * (2 ** attempt)  # exponential backoff
                    logger.warning(f"Database locked, retrying in {delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(delay)
                    continue
            raise
        except Exception:
            raise
    
    raise RuntimeError("Max retries exceeded for database operation")


# ----------------------------------------------------------------------
# Playwright request guard
# ----------------------------------------------------------------------
def _create_request_guard(scope: ScopeDefinition):
    """Return a callback for page.route that aborts out‑of‑scope or unsafe requests."""
    def guard(route):
        request = route.request
        url = request.url
        # Quick scheme check
        if not url.startswith(("http://", "https://")):
            route.abort("blockedbyclient")
            return
        # Scope validation
        res = validate_url_scope(url, scope)
        if not res.allowed:
            logger.warning("Request guard blocked out‑of‑scope URL: %s (%s)", url, res.reason_code)
            route.abort("blockedbyclient")
            return
        # Network safety – resolve host and check IP (best‑effort)
        from urllib.parse import urlparse
        host = urlparse(url).hostname or ""
        try:
            dns = resolve_hostname(host)
            if not dns.allowed:
                logger.warning("Request guard blocked prohibited IP for %s: %s", host, dns.reason_code)
                route.abort("blockedbyclient")
                return
        except Exception:
            # If resolution fails, be conservative and block
            logger.warning("Request guard could not resolve %s – blocking", host)
            route.abort("blockedbyclient")
            return
        route.continue_()
    return guard


# ----------------------------------------------------------------------
# Playwright-based browser validation for dynamic checks
# ----------------------------------------------------------------------
def _run_browser_validators(
    run_id: int,
    normalized_target: str,
    scope_def: ScopeDefinition,
    request_guard,
    vctx: ValidationContext,
    validators: List[BaseValidator],
) -> List[Finding]:
    """
    Launch a Playwright browser with request guard and run validators that need
    a live browser (e.g., redirect chain analysis, CSP evaluation).
    """
    if not PLAYWRIGHT_AVAILABLE:
        logger.warning("Playwright not available; skipping browser-based validators")
        return []

    browser_findings: List[Finding] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 720},
            user_agent="AutoQA-Security/1.0",
        )
        page = ctx.new_page()
        page.route("**/*", request_guard)

        try:
            logger.info(f"Security run {run_id}: Navigating to {normalized_target}")
            page.goto(normalized_target, timeout=30000, wait_until="domcontentloaded")
            time.sleep(1)

            # Check for cancellation after navigation
            if is_cancelled(run_id):
                logger.info(f"Security run {run_id} cancelled during browser validation")
                return []

            # Run each validator that may need browser context
            for val in validators:
                if is_cancelled(run_id):
                    break
                try:
                    # Some validators may need the page object; inject via context metadata
                    vctx.page = page
                    vctx.run_id = run_id
                    findings = val.execute(vctx)
                    browser_findings.extend(findings)
                except Exception as exc:
                    logger.error(f"Validator {val.validator_id} failed in browser context: {exc}")

        except Exception as exc:
            logger.error(f"Browser validation failed for run {run_id}: {exc}")
        finally:
            try:
                page.close()
                ctx.close()
                browser.close()
            except Exception:
                pass

    return browser_findings


# ----------------------------------------------------------------------
# Build ValidationContext shared by validators
# ----------------------------------------------------------------------
def build_validation_context(app_context, candidate_tests) -> "ValidationContext":
    """Adapter used by ValidatorAdapter (ISecurityValidator)."""
    # For passive validators we don't need the full app_context; construct minimal.
    from agentqe.security.models import SecurityRun, TargetAuthorization
    from agentqe.security.evidence import EvidenceCollector

    run = SecurityRun(
        id=app_context.metadata.get("run_id", 0),
        user_id=app_context.metadata.get("user_id", 0),
        normalized_target=app_context.url,
    )
    auth = TargetAuthorization(
        hostname=app_context.url.split("://")[1].split("/")[0],
        scheme=app_context.url.split("://")[0],
    )
    scope = {
        "scheme": auth.scheme,
        "host": auth.hostname,
        "port": None,
        "path_prefix": "/",
        "allow_subdomains": False,
    }
    return ValidationContext(run, auth, app_context.url, scope, EvidenceCollector(run.id))


# ----------------------------------------------------------------------
# Main runner entry point
# ----------------------------------------------------------------------
def execute_security_run(run_id: int) -> None:
    """Background function – called from a thread (like AgentQE)."""
    start_ts = time.time()
    # 1. Load run
    rows = execute_query(
        "SELECT * FROM autonomous_runs WHERE id=? AND run_type='security'", (run_id,), fetch=True
    )
    if not rows:
        logger.error("Security run %s not found", run_id)
        return
    run_row = rows[0]
    user_id = run_row["user_id"]
    target_url = run_row["url"]
    mode = run_row.get("mode", "passive")
    profile = run_row.get("profile", "passive_only")
    dry_run = bool(run_row.get("dry_run", False))
    confirmed = bool(run_row.get("confirmed", False))
    profile_limits_str = run_row.get("profile_limits")
    profile_limits = json.loads(profile_limits_str) if profile_limits_str else {}

    # Log assessment creation
    log_assessment_created(run_row.get("user_id", user_id), run_id, target_url, 
                          run_row.get("mode", "passive"), run_row.get("profile", "passive_only"))

    # 2. Preflight (re‑validate)
    decision: PreflightDecision = run_preflight(user_id, target_url)
    if not decision.allowed:
        _finish_run(run_id, "Failed", f"Preflight rejected: {decision.message}", start_ts)
        return

    # 3. Verify authorization record exists and is verified
    auth = get_verified_authorization(user_id, decision.scope.host)
    if not auth:
        _finish_run(run_id, "Failed", "No verified authorization for target", start_ts)
        return

    # 4. Update status to Running
    execute_query(
        "UPDATE autonomous_runs SET status='Running', started_at=CURRENT_TIMESTAMP WHERE id=?",
        (run_id,),
    )
    log_assessment_started(user_id, run_id, target_url)

    # 5. Prepare scope definition for guard
    scope_def = ScopeDefinition(
        scheme=decision.scope.scheme,
        host=decision.scope.host,
        port=decision.scope.port,
        path_prefix="/",
        allow_subdomains=False,
    )

    # 6. Evidence collector
    collector = EvidenceCollector(run_id)

    # 7. Instantiate validators from registry
    validators: List[BaseValidator] = []
    for name in _validator_names:
        # each module registers its class in globals; we can import dynamically
        mod = __import__(f"agentqe.security.validators.{name}", fromlist=[name])
        cls_name = _validator_class_names.get(name)
        if cls_name is None:
            logger.warning("No class name mapping for validator module: %s", name)
            continue
        cls = getattr(mod, cls_name)
        validators.append(cls())

    # 8. Run validators (passive – they use requests/ssl, not Playwright)
    all_findings: List[Finding] = []
    validator_results: List[ValidatorResult] = []

    # Build a ValidationContext for passive validators
    from agentqe.security.models import SecurityRun as SR, TargetAuthorization as TA
    sr = SR(id=run_id, user_id=user_id, normalized_target=decision.normalized_target)
    ta = TA(hostname=decision.scope.host, scheme=decision.scope.scheme)
    vctx = ValidationContext(sr, ta, decision.normalized_target, {
        "scheme": decision.scope.scheme,
        "host": decision.scope.host,
        "port": decision.scope.port,
        "path_prefix": "/",
        "allow_subdomains": False,
    }, collector)

    for val in validators:
        # Check for cancellation before each validator
        if is_cancelled(run_id):
            logger.info(f"Security run {run_id} cancelled before validator {val.validator_id}")
            break
        
        # Check execution time limit
        elapsed_total = time.time() - start_ts
        if elapsed_total > CONFIG.max_duration_seconds:
            logger.warning(f"Security run {run_id} exceeded max duration ({CONFIG.max_duration_seconds}s)")
            log_execution_budget_exceeded(user_id, run_id, target_url, "duration", 
                                        CONFIG.max_duration_seconds, elapsed_total)
            _finish_run(run_id, "Failed", f"Execution exceeded max duration ({CONFIG.max_duration_seconds}s)", start_ts)
            return
        
        # Check budget
        if not check_budget(run_id):
            log_execution_budget_exceeded(user_id, run_id, target_url, "budget", "exceeded", "exceeded")
            _finish_run(run_id, "Failed", "Budget exceeded", start_ts)
            return

        v_start = time.perf_counter()
        try:
            findings = val.execute(vctx)
            elapsed = (time.perf_counter() - v_start) * 1000
            vr = ValidatorResult(
                validator_id=val.validator_id,
                validator_name=val.name,
                run_id=run_id,
                status="Completed",
                duration_ms=elapsed,
                checks_performed=1,
                findings_generated=len(findings),
            )
            all_findings.extend(findings)
        except Exception as exc:
            elapsed = (time.perf_counter() - v_start) * 1000
            vr = ValidatorResult(
                validator_id=val.validator_id,
                validator_name=val.name,
                run_id=run_id,
                status="Failed",
                duration_ms=elapsed,
                error=str(exc),
            )
        validator_results.append(vr)

    # ZAP Baseline integration (if selected profile)
    if profile == "zap_baseline":
        logger.info("Running OWASP ZAP Baseline scan for run %s", run_id)
        zap_result: ZapScanResult = run_zap_baseline_scan(run_id, target_url, user_id)
        if not zap_result.success:
            _finish_run(run_id, "Failed", f"ZAP scan failed: {zap_result.error}", start_ts)
            return
        all_findings.extend(zap_result.findings)
        logger.info("ZAP baseline scan completed with %d findings in %.1fs", len(zap_result.findings), zap_result.duration_seconds)

    # 9. Browser navigation for dynamic checks with request guard
    # Launch Playwright with request guard for validators that need live browser
    request_guard = _create_request_guard(scope_def)
    browser_findings = _run_browser_validators(
        run_id=run_id,
        normalized_target=decision.normalized_target,
        scope_def=scope_def,
        request_guard=request_guard,
        vctx=vctx,
        validators=validators,
    )
    all_findings.extend(browser_findings)

    # Check for cancellation before proceeding
    if is_cancelled(run_id):
        log_assessment_cancelled(user_id, run_id, target_url)
        _finish_run(run_id, "Cancelled", "Assessment cancelled by user", start_ts)
        return

    # 10. Deduplicate / classify
    final_findings = classify_findings(all_findings)

    # 11. Persist findings & evidence
    for f in final_findings:
        # Insert finding
        fid = execute_query(
            """INSERT INTO security_findings
               (run_id, validator_id, finding_type, title, description,
                severity, confidence, affected_url, evidence, recommendation, classification,
                check_type, active_check_id, execution_phase)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run_id,
                f.source,
                f.category,
                f.description,  # use description as title
                f.description,
                f.severity,
                f.metadata.get("confidence", 0.5) if f.metadata else 0.5,
                f.metadata.get("affected_url", "") if f.metadata else "",
                str(f.evidence),
                f.metadata.get("recommendation", "") if f.metadata else "",
                f.classification,
                getattr(f, 'check_type', 'passive'),
                getattr(f, 'active_check_id', None),
                getattr(f, 'execution_phase', 'passive'),
            ),
        )
        # Persist evidence linked to this finding
        for ev in collector.get_all():
            if ev.finding_id == f.finding_id:
                execute_query(
                    """INSERT INTO security_evidence
                       (finding_id, evidence_type, url, method, status_code, data, check_type, active_check_id)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (fid, ev.evidence_type, ev.url, ev.method, ev.status_code, str(ev.data),
                     getattr(ev, 'check_type', 'passive'), getattr(ev, 'active_check_id', None)),
                )

    # 12. Update run summary
    duration = time.time() - start_ts
    validators_count = len(validators) + (1 if profile == "zap_baseline" else 0)
    execute_query(
        """UPDATE autonomous_runs
           SET status='Completed', completed_at=CURRENT_TIMESTAMP,
               duration_seconds=?, validators_executed=?, findings_count=?
           WHERE id=?""",
        (duration, validators_count, len(final_findings), run_id),
    )
    logger.info("Security run %s completed in %.1fs – %d findings", run_id, duration, len(final_findings))
    log_assessment_completed(user_id, run_id, target_url, len(final_findings))


def _finish_run(run_id: int, status: str, error_summary: str, start_ts: float) -> None:
    duration = time.time() - start_ts
    execute_query(
        """UPDATE autonomous_runs
           SET status=?, completed_at=CURRENT_TIMESTAMP, duration_seconds=?, error_summary=?
           WHERE id=?""",
        (status, duration, error_summary, run_id),
    )
    clear_cancellation(run_id)


def execute_security_run_safely(run_id: int) -> None:
    """Run an assessment from a background thread without leaving it stuck."""
    try:
        execute_security_run(run_id)
    except Exception as exc:
        logger.exception("Security run %s failed unexpectedly", run_id)
        _finish_run(run_id, "Failed", f"Security runner error: {exc}", time.time())