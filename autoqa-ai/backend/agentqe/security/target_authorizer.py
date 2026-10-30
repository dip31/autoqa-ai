"""
Target authorization service.

Determines whether a user may initiate a security‑validation run against a
specific target.  The current implementation uses a global allow‑list that can
be configured via environment variable.  This is a placeholder for a more
robust ownership‑verification workflow (DNS‑TXT, hosted file, admin approval)
that can be added in later phases.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional, Set
from urllib.parse import urlparse

from agentqe.security.security_config import CONFIG, ConfigurationError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason_code: str
    message: str
    normalized_target: str


class TargetAuthorizer:
    """
    Authorize a (user, target) pair.

    The authorizer checks:
      1. The target URL is syntactically valid and uses an allowed scheme.
      2. The target hostname appears in the configured authorization allow‑list.
      3. (Future) The user owns or has been granted permission for the target.
    """

    def __init__(self, allowed_hosts: Optional[Set[str]] = None):
        # Allow‑list can be injected for testing; otherwise read from env.
        if allowed_hosts is None:
            env = os.getenv("SEC_AUTHORIZED_TARGETS", "")
            allowed_hosts = {h.strip().lower() for h in env.split(",") if h.strip()}
        self._allowed_hosts = allowed_hosts

    def authorize(self, user_id: int, target_url: str) -> AuthorizationDecision:
        """
        Return an AuthorizationDecision for the given user and target URL.
        """
        # 1. Basic URL validation – delegate to scope validator later, but do a quick check.
        try:
            parsed = urlparse(target_url)
        except Exception as exc:  # pragma: no cover – defensive
            logger.warning("Target authorization: URL parse failed for %s: %s", target_url, exc)
            return AuthorizationDecision(
                allowed=False,
                reason_code="INVALID_URL",
                message="The supplied target URL is malformed.",
                normalized_target="",
            )

        if parsed.scheme not in CONFIG.allowed_schemes:
            logger.info("Target authorization: scheme %s not allowed for user %s", parsed.scheme, user_id)
            return AuthorizationDecision(
                allowed=False,
                reason_code="UNSUPPORTED_SCHEME",
                message=f"Scheme '{parsed.scheme}' is not permitted by security policy.",
                normalized_target=target_url,
            )

        hostname = parsed.hostname or ""
        normalized_host = hostname.lower().rstrip(".")

        # 2. Allow‑list check
        if CONFIG.require_explicit_authorization:
            allowed = False
            # Global allow-list
            if normalized_host in self._allowed_hosts:
                allowed = True
            else:
                # Check per-user DB authorization records
                try:
                    from agentqe.security.authorization.authorization_repository import get_verified_authorization
                    auth = get_verified_authorization(user_id, normalized_host)
                    if auth:
                        allowed = True
                except Exception:
                    pass
            if not allowed:
                logger.warning(
                    "Target authorization denied: host %s not authorized for user %s",
                    normalized_host,
                    user_id,
                )
                return AuthorizationDecision(
                    allowed=False,
                    reason_code="TARGET_NOT_AUTHORIZED",
                    message="The target host is not authorized for security validation.",
                    normalized_target=f"{parsed.scheme}://{normalized_host}",
                )

        # 3. (Future) per‑user permission check – currently global allow‑list only.
        logger.info("Target authorized for user %s: %s", user_id, normalized_host)
        return AuthorizationDecision(
            allowed=True,
            reason_code="AUTHORIZED",
            message="Target authorized.",
            normalized_target=f"{parsed.scheme}://{normalized_host}",
        )


# Backwards‑compatible functional helper used by the preflight service.
def authorize_target(user_id: int, target_url: str) -> AuthorizationDecision:
    authorizer = TargetAuthorizer()
    return authorizer.authorize(user_id, target_url)