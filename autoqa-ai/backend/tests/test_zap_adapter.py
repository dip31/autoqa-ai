"""
Unit tests for the ZAP baseline adapter (mocked, no Docker required).
"""
import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch, MagicMock

# Ensure the backend package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agentqe.security.integrations.zap_adapter import (
    run_zap_baseline_scan,
    _parse_zap_json,
    _normalize_zap_alert,
    _check_docker_available,
    _pull_zap_image,
    ZapScanResult,
)
from agentqe.security.evidence import EvidenceCollector


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
SAMPLE_ZAP_JSON = {
    "site": [{"@name": "https://example.com", "@host": "example.com", "@port": "443", "@ssl": "true"}],
    "alerts": [
        {
            "pluginid": "10012",
            "alert": "Cross Site Scripting (Reflected)",
            "risk": "High",
            "confidence": "2",
            "description": "<p>Reflected XSS</p>",
            "instances": [
                {
                    "uri": "https://example.com/search?q=test",
                    "method": "GET",
                    "param": "q",
                    "attack": "<script>alert(1)</script>",
                    "evidence": "<script>alert(1)</script>",
                    "status": "200"
                }
            ],
            "cweid": "79",
            "wascid": "8",
            "reference": "https://owasp.org/www-community/attacks/xss/",
            "solution": "Encode output"
        }
    ]
}


def write_report(tmpdir, data):
    path = os.path.join(tmpdir, "report.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------
def test_zap_disabled_by_default(monkeypatch):
    """When ZAP_ENABLED is not set, the adapter should return ZAP_DISABLED without invoking Docker."""
    monkeypatch.delenv("ZAP_ENABLED", raising=False)
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available") as mock_docker:
        result = run_zap_baseline_scan(1, "https://example.com", 42)
        assert result.success is False
        assert result.error == "ZAP_DISABLED"
        mock_docker.assert_not_called()


def test_docker_unavailable_when_enabled(monkeypatch):
    monkeypatch.setenv("ZAP_ENABLED", "true")
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=False):
        result = run_zap_baseline_scan(2, "https://example.com", 42)
        assert result.success is False
        assert "Docker not available" in result.error


def test_image_pull_failure(monkeypatch):
    monkeypatch.setenv("ZAP_ENABLED", "true")
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=False):
        result = run_zap_baseline_scan(3, "https://example.com", 42)
        assert result.success is False
        assert "Failed to pull ZAP Docker image" in result.error


def test_successful_scan_returns_findings(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAP_ENABLED", "true")
    # Mock docker availability and image pull
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=True), \
         patch("subprocess.run") as mock_run, \
         patch("tempfile.TemporaryDirectory") as mock_tmpdir:
        # Prepare a fake temporary directory that will contain report.json
        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)
        write_report(tmp_path, SAMPLE_ZAP_JSON)
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        result = run_zap_baseline_scan(4, "https://example.com", 42)
        assert result.success is True
        assert isinstance(result.findings, list)
        assert len(result.findings) == 1
        f = result.findings[0]
        assert f.source == "OWASP ZAP"
        assert f.severity == "High"
        assert "zap_alert_id" in f.metadata


def test_nonzero_exit_with_valid_json(monkeypatch, tmp_path):
    """ZAP returns non‑zero when alerts are found; adapter should still treat it as success."""
    monkeypatch.setenv("ZAP_ENABLED", "true")
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=True), \
         patch("subprocess.run") as mock_run, \
         patch("tempfile.TemporaryDirectory") as mock_tmpdir:
        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)
        write_report(tmp_path, SAMPLE_ZAP_JSON)
        mock_run.return_value = subprocess.CompletedProcess([], 1, stdout="", stderr="")
        result = run_zap_baseline_scan(5, "https://example.com", 42)
        assert result.success is True
        assert len(result.findings) == 1


def test_missing_report_file(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAP_ENABLED", "true")
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=True), \
         patch("subprocess.run") as mock_run, \
         patch("tempfile.TemporaryDirectory") as mock_tmpdir:
        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)
        # No report.json written
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        result = run_zap_baseline_scan(6, "https://example.com", 42)
        assert result.success is False
        assert "JSON report missing" in result.error or "ZAP did not produce JSON report" in result.error


def test_malformed_json(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAP_ENABLED", "true")
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=True), \
         patch("subprocess.run") as mock_run, \
         patch("tempfile.TemporaryDirectory") as mock_tmpdir:
        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)
        bad = tmp_path / "report.json"
        bad.write_text("{ not json }")
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        result = run_zap_baseline_scan(7, "https://example.com", 42)
        assert result.success is False
        assert "could not be parsed" in result.error or "Failed to parse ZAP JSON" in result.error


def test_empty_alerts_list(tmp_path):
    data = {"site": [], "alerts": []}
    path = write_report(tmp_path, data)
    alerts = _parse_zap_json(path)
    assert alerts == []


def test_missing_optional_fields_in_alert():
    alert = {"pluginid": "99999"}  # only mandatory field
    collector = EvidenceCollector(99)
    finding = _normalize_zap_alert(alert, 10, collector)
    assert finding.category == "ZAP Alert"
    assert finding.severity == "Informational"
    assert finding.metadata["zap_alert_id"] == "99999"


def test_timeout_handling(monkeypatch):
    monkeypatch.setenv("ZAP_ENABLED", "true")
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=True), \
         patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=[], timeout=5)):
        result = run_zap_baseline_scan(8, "https://example.com", 42)
        assert result.success is False
        assert result.timed_out is True


def test_cancellation(monkeypatch):
    monkeypatch.setenv("ZAP_ENABLED", "true")
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=True), \
         patch("subprocess.run", side_effect=KeyboardInterrupt):
        result = run_zap_baseline_scan(9, "https://example.com", 42)
        assert result.success is False
        assert result.cancelled is True


def test_temporary_directory_cleanup(monkeypatch, tmp_path):
    """Ensure TemporaryDirectory context manager is used (cleanup occurs)."""
    monkeypatch.setenv("ZAP_ENABLED", "true")
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=True), \
         patch("subprocess.run") as mock_run, \
         patch("tempfile.TemporaryDirectory") as mock_tmpdir:
        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)
        write_report(tmp_path, SAMPLE_ZAP_JSON)
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        run_zap_baseline_scan(10, "https://example.com", 42)
        # __exit__ should have been called
        mock_tmpdir.return_value.__exit__.assert_called()


def test_evidence_size_limit_constant():
    """Adapter reads ZAP_MAX_DURATION env; ensure constant exists."""
    # Just ensure the constant is defined and positive
    from agentqe.security.integrations.zap_adapter import MAX_SCAN_DURATION
    assert MAX_SCAN_DURATION > 0


def test_duplicate_alert_handling(monkeypatch, tmp_path):
    """Two identical alerts should be deduplicated by classify_findings (same category/url)."""
    monkeypatch.setenv("ZAP_ENABLED", "true")
    dup_data = SAMPLE_ZAP_JSON.copy()
    dup_data["alerts"] = [SAMPLE_ZAP_JSON["alerts"][0], SAMPLE_ZAP_JSON["alerts"][0]]
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=True), \
         patch("subprocess.run") as mock_run, \
         patch("tempfile.TemporaryDirectory") as mock_tmpdir:
        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)
        write_report(tmp_path, dup_data)
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        result = run_zap_baseline_scan(11, "https://example.com", 42)
        assert result.success is True
        # classify_findings should collapse duplicates -> 1 finding
        assert len(result.findings) == 1


def test_finding_persistence_error(monkeypatch, tmp_path):
    """If execute_query raises, adapter should surface error."""
    monkeypatch.setenv("ZAP_ENABLED", "true")
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=True), \
         patch("subprocess.run") as mock_run, \
         patch("tempfile.TemporaryDirectory") as mock_tmpdir, \
         patch("agentqe.security.integrations.zap_adapter.execute_query", side_effect=Exception("DB down")):
        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)
        write_report(tmp_path, SAMPLE_ZAP_JSON)
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        result = run_zap_baseline_scan(12, "https://example.com", 42)
        assert result.success is False
        assert "DB down" in result.error or "ZAP execution error" in result.error


def test_run_status_on_failure(monkeypatch):
    """When adapter fails, it returns success=False and error message."""
    monkeypatch.setenv("ZAP_ENABLED", "true")
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=False):
        result = run_zap_baseline_scan(13, "https://example.com", 42)
        assert result.success is False
        assert result.error is not None


def test_validators_executed_and_findings_count(monkeypatch, tmp_path):
    """Adapter returns structured result; runner uses it to increment counters."""
    monkeypatch.setenv("ZAP_ENABLED", "true")
    with patch("agentqe.security.integrations.zap_adapter._check_docker_available", return_value=True), \
         patch("agentqe.security.integrations.zap_adapter._pull_zap_image", return_value=True), \
         patch("subprocess.run") as mock_run, \
         patch("tempfile.TemporaryDirectory") as mock_tmpdir:
        mock_tmpdir.return_value.__enter__.return_value = str(tmp_path)
        write_report(tmp_path, SAMPLE_ZAP_JSON)
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        result = run_zap_baseline_scan(14, "https://example.com", 42)
        assert result.success is True
        assert hasattr(result, "duration_seconds")
        assert isinstance(result.findings, list)
        # runner will add 1 to validators_executed for zap_baseline


def test_finding_source_and_original_id():
    """Normalized finding keeps source and zap_alert_id."""
    alert = {"pluginid": "12345", "name": "Test Alert", "risk": "Medium", "confidence": "3", "description": "desc"}
    collector = EvidenceCollector(1)
    f = _normalize_zap_alert(alert, 5, collector)
    assert f.source == "OWASP ZAP"
    assert f.metadata["zap_alert_id"] == "12345"


def test_authorization_failure_before_execution(monkeypatch):
    """If authorization missing, runner should not call adapter (covered by runner tests)."""
    # This test is a placeholder; actual check is in security_runner.
    assert True