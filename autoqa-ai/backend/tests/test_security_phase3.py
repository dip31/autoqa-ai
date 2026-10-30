"""
Phase 3 security tests – validators, authorization, runner basics.
Uses mocks to avoid external network.
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Ensure env for config
os.environ.setdefault("SEC_DEV_MODE", "0")
os.environ.setdefault("SEC_ALLOWED_SCHEMES", "https")
os.environ.setdefault("SEC_AUTHORIZED_TARGETS", "example.com")
os.environ.setdefault("SEC_REQUIRE_EXPLICIT_AUTH", "1")
os.environ.setdefault("SEC_BLOCK_PRIVATE_IPS", "1")
os.environ.setdefault("SEC_BLOCK_LOOPBACK", "1")
os.environ.setdefault("SEC_BLOCK_LINK_LOCAL", "1")
os.environ.setdefault("SEC_BLOCK_MULTICAST", "1")
os.environ.setdefault("SEC_BLOCK_RESERVED", "1")
os.environ.setdefault("SEC_BLOCK_CLOUD_METADATA", "1")
os.environ.setdefault("SEC_REQUIRE_DNS_VALIDATION", "1")
os.environ.setdefault("SEC_ALLOW_HTTP", "0")

# Import after env set
from agentqe.security.authorization.authorization_repository import (
    create_authorization,
    get_authorization,
    get_user_authorizations,
    get_verified_authorization,
    mark_verified,
    revoke_authorization,
    delete_authorization,
)
from agentqe.security.authorization.ownership_verifier import start_verification, verify_hosted_file, VerificationError
from agentqe.security.validators.https_validator import HTTPSValidator
from agentqe.security.validators.security_headers_validator import SecurityHeadersValidator
from agentqe.security.validators.cookie_security_validator import CookieSecurityValidator
from agentqe.security.validators.information_disclosure_validator import InformationDisclosureValidator
from agentqe.security.validators.redirect_validator import RedirectValidator
from agentqe.security.validators.tls_validator import TLSValidator
from agentqe.security.validators.base import ValidationContext
from agentqe.security.models import SecurityRun, TargetAuthorization
from agentqe.security.evidence import EvidenceCollector
from agentqe.security.security_runner import execute_security_run
from agentqe.interfaces import Finding


# ----------------------------------------------------------------------
# Authorization repository tests
# ----------------------------------------------------------------------
def test_create_and_get_authorization():
    auth = create_authorization(1, "example.com")
    assert auth.hostname == "example.com"
    assert auth.verification_status == "pending"
    assert auth.verification_token is not None

    fetched = get_authorization(auth.id)
    assert fetched.id == auth.id
    assert fetched.user_id == 1


def test_list_user_authorizations():
    # Clean up any existing authorizations for user 1 first
    existing = get_user_authorizations(1)
    for auth in existing:
        delete_authorization(auth.id, 1)
    
    create_authorization(1, "a.com")
    create_authorization(1, "b.com")
    create_authorization(2, "c.com")
    user1 = get_user_authorizations(1)
    assert len(user1) == 2
    hostnames = {a.hostname for a in user1}
    assert hostnames == {"a.com", "b.com"}


def test_mark_verified():
    auth = create_authorization(1, "verify.com")
    ok = mark_verified(auth.id)
    assert ok
    verified = get_authorization(auth.id)
    assert verified.verification_status == "verified"
    assert verified.verified_at is not None


def test_revoke_authorization():
    auth = create_authorization(1, "revoke.com")
    ok = revoke_authorization(auth.id, 1)
    assert ok
    revoked = get_authorization(auth.id)
    assert revoked.revoked_at is not None


def test_get_verified_authorization():
    auth = create_authorization(1, "verified.com")
    mark_verified(auth.id)
    v = get_verified_authorization(1, "verified.com")
    assert v is not None
    assert v.verification_status == "verified"
    # wrong user
    assert get_verified_authorization(2, "verified.com") is None


# ----------------------------------------------------------------------
# Ownership verification tests (mock HTTP)
# ----------------------------------------------------------------------
@patch("agentqe.security.authorization.ownership_verifier.requests.get")
def test_verify_hosted_file_success(mock_get):
    auth = start_verification(1, "example.com")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = auth.verification_token
    mock_get.return_value = mock_resp

    assert verify_hosted_file(auth) is True
    mock_get.assert_called_once()


@patch("agentqe.security.authorization.ownership_verifier.requests.get")
def test_verify_hosted_file_token_mismatch(mock_get):
    auth = start_verification(1, "example.com")
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = "wrong-token"
    mock_get.return_value = mock_resp

    with pytest.raises(VerificationError):
        verify_hosted_file(auth)


@patch("agentqe.security.authorization.ownership_verifier.requests.get")
def test_verify_hosted_file_http_error(mock_get):
    auth = start_verification(1, "example.com")
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    mock_get.return_value = mock_resp

    with pytest.raises(VerificationError):
        verify_hosted_file(auth)


# ----------------------------------------------------------------------
# Validator tests (mock HTTP / TLS)
# ----------------------------------------------------------------------
def _make_vctx(target="https://example.com/"):
    run = SecurityRun(id=1, user_id=1, normalized_target=target)
    auth = TargetAuthorization(hostname="example.com", scheme="https")
    scope = {"scheme": "https", "host": "example.com", "port": None, "path_prefix": "/", "allow_subdomains": False}
    collector = EvidenceCollector(1)
    return ValidationContext(run, auth, target, scope, collector)


@patch("agentqe.security.validators.https_validator.requests.head")
def test_https_validator_https_ok(mock_head):
    mock_resp = MagicMock()
    mock_resp.url = "https://example.com/"
    mock_head.return_value = mock_resp
    v = HTTPSValidator()
    findings = v.execute(_make_vctx())
    # Should have no high severity findings
    high = [f for f in findings if f.severity in ("High", "Critical")]
    assert not high


@patch("agentqe.security.validators.https_validator.requests.head")
def test_https_validator_http_disallowed(mock_head):
    # target http, policy disallows http
    vctx = _make_vctx("http://example.com/")
    mock_resp = MagicMock()
    mock_resp.url = "http://example.com/"
    mock_head.return_value = mock_resp
    v = HTTPSValidator()
    findings = v.execute(vctx)
    assert any(f.severity == "Medium" and "HTTP" in f.description for f in findings)


@patch("agentqe.security.validators.security_headers_validator.requests.get")
def test_security_headers_missing(mock_get):
    mock_resp = MagicMock()
    mock_resp.headers = {}
    mock_resp.url = "https://example.com/"
    mock_get.return_value = mock_resp
    v = SecurityHeadersValidator()
    findings = v.execute(_make_vctx())
    # Expect findings for each missing header
    categories = {f.category for f in findings}
    assert "SecurityHeaders" in categories


@patch("agentqe.security.validators.cookie_security_validator.requests.get")
def test_cookie_security_missing_flags(mock_get):
    mock_resp = MagicMock()
    mock_resp.headers = {"Set-Cookie": "session=abc; Path=/"}
    mock_resp.url = "https://example.com/"
    mock_get.return_value = mock_resp
    v = CookieSecurityValidator()
    findings = v.execute(_make_vctx())
    assert any("Secure" in f.description for f in findings)


@patch("agentqe.security.validators.information_disclosure_validator.requests.get")
def test_info_disclosure_server_header(mock_get):
    mock_resp = MagicMock()
    mock_resp.headers = {"Server": "Apache/2.4.41"}
    mock_resp.text = ""
    mock_resp.url = "https://example.com/"
    mock_get.return_value = mock_resp
    v = InformationDisclosureValidator()
    findings = v.execute(_make_vctx())
    assert any(f.category == "InformationDisclosure" for f in findings)


@patch("agentqe.security.validators.redirect_validator.requests.get")
@patch("socket.getaddrinfo")
def test_redirect_validator_out_of_scope(mock_getaddrinfo, mock_get):
    # First response redirect to external
    resp1 = MagicMock()
    resp1.status_code = 302
    resp1.headers = {"Location": "https://evil.com/"}
    resp1.url = "https://example.com/"
    resp2 = MagicMock()
    resp2.status_code = 200
    resp2.url = "https://evil.com/"
    mock_get.side_effect = [resp1, resp2]
    # DNS for evil.com -> public IP
    mock_getaddrinfo.return_value = [(2, 1, 6, "", ("8.8.8.8", 0))]
    v = RedirectValidator()
    findings = v.execute(_make_vctx())
    assert any(f.category == "ScopeViolation" for f in findings)


@patch("agentqe.security.validators.tls_validator.socket.create_connection")
@patch("agentqe.security.validators.tls_validator.ssl.create_default_context")
def test_tls_validator_expiring_soon(mock_ssl_ctx, mock_create_conn):
    # Build a mock cert with notAfter soon
    import ssl
    from datetime import datetime, timezone, timedelta
    mock_sock = MagicMock()
    mock_ssock = MagicMock()
    mock_create_conn.return_value.__enter__.return_value = mock_sock
    mock_ssl_ctx.return_value.wrap_socket.return_value.__enter__.return_value = mock_ssock
    exp_date = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%b %d %H:%M:%S %Y %Z")
    mock_ssock.getpeercert.return_value = {"notAfter": exp_date, "subjectAltName": [("DNS", "example.com")], "subject": []}
    v = TLSValidator()
    findings = v.execute(_make_vctx())
    assert any(f.severity == "High" and "expires" in f.description.lower() for f in findings)


# ----------------------------------------------------------------------
# Runner basic test (mock preflight and validators)
# ----------------------------------------------------------------------
@patch("agentqe.security.security_runner.run_preflight")
@patch("agentqe.security.security_runner.get_verified_authorization")
@patch("agentqe.security.security_runner.execute_query")
@patch("agentqe.security.security_runner.is_cancelled")
@patch("agentqe.security.security_runner.check_budget")
@patch("agentqe.security.security_runner._run_browser_validators")
@patch("agentqe.security.security_runner.classify_findings")
@patch("agentqe.security.security_runner.log_assessment_started")
@patch("agentqe.security.security_runner.log_assessment_completed")
@patch("agentqe.security.security_runner.log_assessment_created")
@patch("agentqe.security.security_runner._validator_names", ["https_validator"])
@patch("agentqe.security.validators.https_validator.HTTPSValidator.execute")
def test_execute_security_run_calls_preflight(
    mock_validator_execute,
    mock_log_created,
    mock_log_completed,
    mock_log_started,
    mock_classify_findings,
    mock_run_browser,
    mock_check_budget,
    mock_is_cancelled,
    mock_execute_query,
    mock_get_verified,
    mock_preflight,
):
    # Setup mocks
    mock_preflight.return_value = MagicMock(allowed=True, normalized_target="https://example.com/",
                                            scope=MagicMock(scheme="https", host="example.com", port=None))
    mock_get_verified.return_value = MagicMock(hostname="example.com", scheme="https")
    mock_validator_execute.return_value = []  # No findings
    mock_check_budget.return_value = True
    mock_is_cancelled.return_value = False
    mock_run_browser.return_value = []
    mock_classify_findings.return_value = []
    
    # Mock execute_query to return a run for the initial SELECT, then None for UPDATEs
    mock_execute_query.side_effect = [
        [{"id": 999, "user_id": 1, "url": "https://example.com/", "run_type": "security"}],  # SELECT run
        None,  # UPDATE status='Running'
        None,  # UPDATE status='Completed'
    ]

    # Run
    execute_security_run(999)

    # Ensure run status updated
    calls = [c[0][0] for c in mock_execute_query.call_args_list]
    print("Calls made:", calls)
    assert any("UPDATE autonomous_runs SET status='Running'" in c for c in calls)
    assert any("status='Completed'" in c for c in calls)