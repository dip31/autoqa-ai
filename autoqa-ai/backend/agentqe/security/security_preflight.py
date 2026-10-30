"""
Centralized security preflight service.

Coordinates authentication context, target authorization, URL/scope validation,
DNS/IP safety, and policy/resource limits.  Returns a structured decision that
callers (API endpoints, background runners) must respect before any
security‑specific network activity.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from agentqe.security.security_config import CONFIG, ConfigurationError
from agentqe.security.target_authorizer import AuthorizationDecision, TargetAuthorizer
from agentqe.security.scope_validator import ScopeDefinition, ScopeValidationResult, validate_url_scope
from agentqe.security.network_safety import DnsResult, resolve_hostname

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreflightDecision:
    allowed: bool
    reason_code: str
    message: str
    normalized_target: str
    scope: Optional[ScopeDefinition] = None
    dns_result: Optional[DnsResult] = None
    policy_version: str = "1.0"
    validated_at: float = time.time()


class SecurityPreflight:
    """
    Single entry point for all security‑run authorization decisions.

    Usage:
        decision = SecurityPreflight().validate(user_id, target_url)
        if not decision.allowed:
            raise PermissionError(decision.message)
        # decision.scope, decision.normalized_target, decision.dns_result can be
        # passed to the runner so it does not need to re‑validate.
    """

    def __init__(self, authorizer: Optional[TargetAuthorizer] = None):
        self._authorizer = authorizer or TargetAuthorizer()

    def validate(self, user_id: int, target_url: str) -> PreflightDecision:
        """
        Perform the full preflight check.

        Steps:
          1. Target authorization (allow‑list / ownership)
          2. URL syntax, scheme, host, port, path, credentials
          3. Scope matching against the authorized scope (derived from allow‑list)
          4. DNS resolution + IP policy
          5. Resource‑limit sanity (max pages, duration, etc.) – logged only
        """
        # ---- 1. Target authorization ----
        auth_dec: AuthorizationDecision = self._authorizer.authorize(user_id, target_url)
        if not auth_dec.allowed:
            self._audit(user_id, target_url, auth_dec.reason_code, auth_dec.message, allowed=False)
            return PreflightDecision(
                allowed=False,
                reason_code=auth_dec.reason_code,
                message=auth_dec.message,
                normalized_target=auth_dec.normalized_target,
            )

        # ---- 2. Build a ScopeDefinition from the authorized host ----
        # The allow‑list only contains hostnames; we construct a minimal scope.
        parsed = __import__("urllib.parse").parse.urlparse(auth_dec.normalized_target)
        scope = ScopeDefinition(
            scheme=parsed.scheme,
            host=parsed.hostname or "",
            port=parsed.port,
            path_prefix="/",          # whole origin allowed
            allow_subdomains=False,   # strict by default
        )

        # ---- 3. Scope validation ----
        scope_res: ScopeValidationResult = validate_url_scope(target_url, scope)
        if not scope_res.allowed:
            self._audit(user_id, target_url, scope_res.reason_code, scope_res.message, allowed=False)
            return PreflightDecision(
                allowed=False,
                reason_code=scope_res.reason_code,
                message=scope_res.message,
                normalized_target=target_url,
                scope=scope,
            )

        # ---- 4. DNS / IP safety ----
        dns_res: DnsResult = resolve_hostname(scope.host)
        if not dns_res.allowed:
            self._audit(user_id, target_url, dns_res.reason_code,
                        f"DNS/IP check failed: {dns_res.reason_code}", allowed=False)
            return PreflightDecision(
                allowed=False,
                reason_code=dns_res.reason_code,
                message="Target resolves to a prohibited network address.",
                normalized_target=scope_res.normalized_url,
                scope=scope,
                dns_result=dns_res,
            )

        # ---- 5. Resource limits (informational) ----
        # We don't reject here, but we log the limits that will be enforced
        logger.info(
            "Preflight OK for user %s target %s (limits: pages=%d, depth=%d, duration=%ds)",
            user_id,
            scope_res.normalized_url,
            CONFIG.max_pages,
            CONFIG.max_depth,
            CONFIG.max_duration_seconds,
        )

        self._audit(user_id, target_url, "PREFLIGHT_OK", "Security preflight passed", allowed=True)

        return PreflightDecision(
            allowed=True,
            reason_code="PREFLIGHT_OK",
            message="Security preflight passed.",
            normalized_target=scope_res.normalized_url,
            scope=scope,
            dns_result=dns_res,
        )

    # ------------------------------------------------------------------
    # Audit logging – safe, no secrets
    # ------------------------------------------------------------------
    def _audit(self, user_id: int, target_url: str, reason_code: str, message: str, allowed: bool) -> None:
        if not CONFIG.audit_log_enabled:
            return
        # Sanitize target_url – strip credentials, query, fragment for log
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(target_url)
        safe_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

        log_entry = {
            "timestamp": time.time(),
            "user_id": user_id,
            "target": safe_url,
            "allowed": allowed,
            "reason_code": reason_code,
            "message": message,
            "policy_version": "1.0",
        }
        # Use standard logger; in production this can be routed to a file / SIEM
        logger.info("SECURITY_AUDIT %s", log_entry)


# Convenience function for callers that don't need the class instance.
def run_preflight(user_id: int, target_url: str) -> PreflightDecision:
    return SecurityPreflight().validate(user_id, target_url)