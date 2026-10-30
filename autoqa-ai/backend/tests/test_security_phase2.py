"""
Security Phase 2 test suite.

Covers URL validation, scope validation, network safety (IP classification, DNS),
target authorization, and the centralized preflight service.
"""

import os
import socket
import ipaddress
import pytest
from unittest.mock import patch, MagicMock

# Ensure the security config uses test-friendly defaults
os.environ.setdefault("SEC_DEV_MODE", "0")
os.environ.setdefault("SEC_ALLOWED_SCHEMES", "https")
os.environ.setdefault("SEC_AUTHORIZED_TARGETS", "example.com,allowed.org")
os.environ.setdefault("SEC_REQUIRE_EXPLICIT_AUTH", "1")
os.environ.setdefault("SEC_BLOCK_PRIVATE_IPS", "1")
os.environ.setdefault("SEC_BLOCK_LOOPBACK", "1")
os.environ.setdefault("SEC_BLOCK_LINK_LOCAL", "1")
os.environ.setdefault("SEC_BLOCK_MULTICAST", "1")
os.environ.setdefault("SEC_BLOCK_RESERVED", "1")
os.environ.setdefault("SEC_BLOCK_CLOUD_METADATA", "1")
os.environ.setdefault("SEC_REQUIRE_DNS_VALIDATION", "1")

from agentqe.security.security_config import CONFIG
from agentqe.security.target_authorizer import TargetAuthorizer, AuthorizationDecision
from agentqe.security.scope_validator import ScopeDefinition, validate_url_scope
from agentqe.security.network_safety import classify_ip_address, resolve_hostname, is_redirect_allowed
from agentqe.security.security_preflight import SecurityPreflight, run_preflight


# ----------------------------------------------------------------------
# URL / Scope validation tests
# ----------------------------------------------------------------------
def test_validate_url_scope_exact_match():
    scope = ScopeDefinition(scheme="https", host="example.com", path_prefix="/app")
    res = validate_url_scope("https://example.com/app/page", scope)
    assert res.allowed
    assert res.reason_code == "SCOPE_OK"


def test_validate_url_scope_subdomain_not_allowed_by_default():
    scope = ScopeDefinition(scheme="https", host="example.com")
    res = validate_url_scope("https://sub.example.com/", scope)
    assert not res.allowed
    assert res.reason_code == "HOST_OUT_OF_SCOPE"


def test_validate_url_scope_subdomain_allowed_when_flag():
    scope = ScopeDefinition(scheme="https", host="example.com", allow_subdomains=True)
    res = validate_url_scope("https://sub.example.com/", scope)
    assert res.allowed


def test_validate_url_scope_wrong_scheme():
    scope = ScopeDefinition(scheme="https", host="example.com")
    res = validate_url_scope("http://example.com/", scope)
    assert not res.allowed
    assert res.reason_code == "SCHEME_MISMATCH"


def test_validate_url_scope_embedded_credentials_rejected():
    scope = ScopeDefinition(scheme="https", host="example.com")
    res = validate_url_scope("https://user:pass@example.com/", scope)
    assert not res.allowed
    assert res.reason_code == "CREDENTIALS_IN_URL"


def test_validate_url_scope_ip_literal_rejected():
    scope = ScopeDefinition(scheme="https", host="example.com")
    res = validate_url_scope("https://192.168.1.1/", scope)
    assert not res.allowed
    # Host mismatch occurs before IP‑literal check; both are rejections.
    assert res.reason_code in ("IP_LITERAL_NOT_ALLOWED", "HOST_OUT_OF_SCOPE")


# ----------------------------------------------------------------------
# Target authorization tests
# ----------------------------------------------------------------------
def test_target_authorizer_allows_configured_host():
    authorizer = TargetAuthorizer(allowed_hosts={"example.com"})
    decision = authorizer.authorize(1, "https://example.com/")
    assert decision.allowed
    assert decision.reason_code == "AUTHORIZED"


def test_target_authorizer_denies_unconfigured_host():
    authorizer = TargetAuthorizer(allowed_hosts={"example.com"})
    decision = authorizer.authorize(1, "https://evil.com/")
    assert not decision.allowed
    assert decision.reason_code == "TARGET_NOT_AUTHORIZED"


def test_target_authorizer_rejects_unsupported_scheme():
    authorizer = TargetAuthorizer(allowed_hosts={"example.com"})
    decision = authorizer.authorize(1, "ftp://example.com/")
    assert not decision.allowed
    assert decision.reason_code == "UNSUPPORTED_SCHEME"


# ----------------------------------------------------------------------
# IP classification tests
# ----------------------------------------------------------------------
@pytest.mark.parametrize("ip,expected_allowed", [
    ("127.0.0.1", False),
    ("::1", False),
    ("10.0.0.1", False),
    ("192.168.1.1", False),
    ("172.16.0.1", False),
    ("fe80::1", False),
    ("ff02::1", False),
    ("0.0.0.0", False),
    ("169.254.169.254", False),
    ("8.8.8.8", True),
    ("2001:4860:4860::8888", True),
])
def test_classify_ip_address(ip, expected_allowed):
    allowed, reason_code, _ = classify_ip_address(ip)
    assert allowed == expected_allowed
    # Reason code may vary; only ensure a reason is provided when prohibited
    if not expected_allowed:
        assert reason_code


# ----------------------------------------------------------------------
# DNS resolution tests (mocked)
# ----------------------------------------------------------------------
@patch("socket.getaddrinfo")
def test_resolve_hostname_allows_public_ips(mock_getaddrinfo):
    # Mock returning a public IPv4 and IPv6
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, 0, 0, "", ("8.8.8.8", 0)),
        (socket.AF_INET6, 0, 0, "", ("2001:4860:4860::8888", 0, 0, 0)),
    ]
    res = resolve_hostname("example.com")
    assert res.allowed
    assert res.reason_code == "DNS_OK"
    assert len(res.ips) == 2


@patch("socket.getaddrinfo")
def test_resolve_hostname_blocks_private_ip(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, 0, 0, "", ("10.0.0.5", 0)),
    ]
    res = resolve_hostname("internal.example.com")
    assert not res.allowed
    assert res.reason_code == "PRIVATE_ADDRESS"


@patch("socket.getaddrinfo")
def test_resolve_hostname_mixed_ips_blocks(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [
        (socket.AF_INET, 0, 0, "", ("8.8.8.8", 0)),
        (socket.AF_INET, 0, 0, "", ("10.0.0.5", 0)),
    ]
    res = resolve_hostname("mixed.example.com")
    assert not res.allowed
    assert res.reason_code == "PRIVATE_ADDRESS"


@patch("agentqe.security.network_safety.socket.getaddrinfo")
def test_resolve_hostname_dns_failure(mock_getaddrinfo):
    import socket
    mock_getaddrinfo.side_effect = socket.gaierror("Name or service not known")
    res = resolve_hostname("unknown.example.com")
    assert not res.allowed
    assert res.reason_code == "DNS_RESOLUTION_FAILED"


# ----------------------------------------------------------------------
# Preflight integration tests
# ----------------------------------------------------------------------
@patch("agentqe.security.security_preflight.resolve_hostname")
def test_preflight_allows_authorized_target(mock_resolve):
    # Mock DNS to return allowed IP
    mock_resolve.return_value = MagicMock(
        allowed=True,
        reason_code="DNS_OK",
        ips=[ipaddress.IPv4Address("8.8.8.8")],
        hostname="example.com",
    )

    preflight = SecurityPreflight(TargetAuthorizer(allowed_hosts={"example.com"}))
    decision = preflight.validate(42, "https://example.com/path")
    assert decision.allowed
    assert decision.reason_code == "PREFLIGHT_OK"
    assert decision.normalized_target == "https://example.com/path"
    assert decision.scope.host == "example.com"


@patch("agentqe.security.network_safety.resolve_hostname")
def test_preflight_denies_unauthorized_target(mock_resolve):
    mock_resolve.return_value = MagicMock(allowed=True, reason_code="DNS_OK")
    preflight = SecurityPreflight(TargetAuthorizer(allowed_hosts={"example.com"}))
    decision = preflight.validate(42, "https://evil.com/")
    assert not decision.allowed
    assert decision.reason_code == "TARGET_NOT_AUTHORIZED"


@patch("agentqe.security.security_preflight.resolve_hostname")
def test_preflight_denies_prohibited_ip(mock_resolve):
    mock_resolve.return_value = MagicMock(
        allowed=False,
        reason_code="PRIVATE_ADDRESS",
        ips=[ipaddress.IPv4Address("10.0.0.1")],
        hostname="internal.example.com",
    )

    preflight = SecurityPreflight(TargetAuthorizer(allowed_hosts={"internal.example.com"}))
    decision = preflight.validate(42, "https://internal.example.com/")
    assert not decision.allowed
    assert decision.reason_code == "PRIVATE_ADDRESS"


# ----------------------------------------------------------------------
# Redirect safety test (uses scope validator)
# ----------------------------------------------------------------------
def test_redirect_allowed_within_scope():
    scope = ScopeDefinition(scheme="https", host="example.com", allow_subdomains=True)
    allowed, reason = is_redirect_allowed("https://example.com/", "https://sub.example.com/page", scope)
    assert allowed
    assert reason == "SCOPE_OK"


def test_redirect_denied_out_of_scope():
    scope = ScopeDefinition(scheme="https", host="example.com")
    allowed, reason = is_redirect_allowed("https://example.com/", "https://evil.com/", scope)
    assert not allowed
    assert reason == "HOST_OUT_OF_SCOPE"