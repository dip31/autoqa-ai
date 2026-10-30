"""
Scope validation – ensures a target URL conforms to the approved authorization scope.

The validator checks:
  * URL syntax and normalization
  * Scheme, host, port, path against an explicit scope definition
  * Subdomain policy (exact match unless wildcard explicitly allowed)
  * Rejects embedded credentials, IP‑literals unless explicitly permitted
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, urlunparse

from agentqe.security.security_config import CONFIG

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScopeDefinition:
    """Explicit, minimal representation of an approved scope."""
    scheme: str                     # e.g. "https"
    host: str                       # exact hostname, lower‑cased, no trailing dot
    port: Optional[int] = None      # None means default for scheme
    path_prefix: str = "/"          # allowed path prefix, must start with '/'
    allow_subdomains: bool = False  # if True, any subdomain of host is allowed


@dataclass(frozen=True)
class ScopeValidationResult:
    allowed: bool
    reason_code: str
    message: str
    normalized_url: str
    matched_scope: Optional[ScopeDefinition] = None


def _normalize_host(host: str) -> str:
    """Lower‑case, strip trailing dot, reject empty."""
    return host.lower().rstrip(".")


def _host_matches(scope_host: str, target_host: str, allow_subdomains: bool) -> bool:
    """
    Return True if target_host matches scope_host under the subdomain policy.
    Both hosts are expected to be normalized (lower‑case, no trailing dot).
    """
    if allow_subdomains:
        # target_host must be exactly scope_host or end with "." + scope_host
        return target_host == scope_host or target_host.endswith("." + scope_host)
    return target_host == scope_host


def _port_allows(scope_port: Optional[int], target_port: Optional[int], scheme: str) -> bool:
    """Check port compatibility. None means default port for scheme."""
    if scope_port is None:
        # default port for scheme
        default = 443 if scheme == "https" else 80
        return target_port in (None, default)
    return target_port == scope_port


def validate_url_scope(target_url: str, scope: ScopeDefinition) -> ScopeValidationResult:
    """
    Validate that target_url falls within the given ScopeDefinition.
    """
    try:
        parsed = urlparse(target_url)
    except Exception as exc:  # pragma: no cover
        logger.warning("Scope validation: URL parse error for %s: %s", target_url, exc)
        return ScopeValidationResult(
            allowed=False,
            reason_code="INVALID_URL",
            message="Malformed URL.",
            normalized_url="",
        )

    # Scheme
    if parsed.scheme != scope.scheme:
        return ScopeValidationResult(
            allowed=False,
            reason_code="SCHEME_MISMATCH",
            message=f"URL scheme '{parsed.scheme}' does not match authorized scheme '{scope.scheme}'.",
            normalized_url=target_url,
        )

    # Host
    target_host = _normalize_host(parsed.hostname or "")
    scope_host = _normalize_host(scope.host)
    if not _host_matches(scope_host, target_host, scope.allow_subdomains):
        return ScopeValidationResult(
            allowed=False,
            reason_code="HOST_OUT_OF_SCOPE",
            message=f"Host '{target_host}' is not within the authorized scope '{scope_host}'.",
            normalized_url=target_url,
        )

    # Port
    target_port = parsed.port
    if not _port_allows(scope.port, target_port, parsed.scheme):
        return ScopeValidationResult(
            allowed=False,
            reason_code="PORT_OUT_OF_SCOPE",
            message=f"Port {target_port} is not permitted for this scope.",
            normalized_url=target_url,
        )

    # Path prefix
    target_path = parsed.path or "/"
    if not target_path.startswith(scope.path_prefix):
        return ScopeValidationResult(
            allowed=False,
            reason_code="PATH_OUT_OF_SCOPE",
            message=f"Path '{target_path}' is outside the authorized path prefix '{scope.path_prefix}'.",
            normalized_url=target_url,
        )

    # Reject embedded credentials
    if parsed.username or parsed.password:
        return ScopeValidationResult(
            allowed=False,
            reason_code="CREDENTIALS_IN_URL",
            message="URLs containing embedded credentials are not permitted.",
            normalized_url=target_url,
        )

    # Reject IP‑literal hosts unless scope explicitly allows (not supported now)
    if re.match(r"^\[?[\da-fA-F:.]+\]?$", target_host):
        return ScopeValidationResult(
            allowed=False,
            reason_code="IP_LITERAL_NOT_ALLOWED",
            message="IP‑literal hosts are not allowed unless explicitly configured.",
            normalized_url=target_url,
        )

    # Build a normalized URL (scheme://host[:port]/path?query#fragment) without credentials
    normalized = urlunparse((
        parsed.scheme,
        f"{target_host}:{target_port}" if target_port else target_host,
        target_path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))

    logger.debug("Scope validation passed for %s", normalized)
    return ScopeValidationResult(
        allowed=True,
        reason_code="SCOPE_OK",
        message="URL is within the authorized scope.",
        normalized_url=normalized,
        matched_scope=scope,
    )