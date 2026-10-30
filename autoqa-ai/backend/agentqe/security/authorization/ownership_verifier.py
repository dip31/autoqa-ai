"""
Ownership verification via hosted‑file challenge.

The user creates an authorization record (pending). The service generates a random token
and tells the user to place a file at:

    https://<hostname>/.well-known/autoqa-challenge.txt

containing exactly that token. The verifier fetches the file (HTTPS only) and checks the
content. On success the authorization is marked verified.
"""
from __future__ import annotations

import logging
import requests
from urllib.parse import urljoin

from agentqe.security.authorization.authorization_repository import (
    get_authorization,
    mark_verified,
)
from agentqe.security.models import TargetAuthorization
from agentqe.security.security_config import CONFIG

logger = logging.getLogger(__name__)


CHALLENGE_PATH = "/.well-known/autoqa-challenge.txt"
REQUEST_TIMEOUT = 10  # seconds


class VerificationError(Exception):
    """Raised when verification cannot be completed."""
    pass


def verify_hosted_file(auth: TargetAuthorization) -> bool:
    """
    Perform the hosted‑file verification for a pending authorization.

    Returns True on success, raises VerificationError on failure.
    """
    if auth.verification_status != "pending":
        raise VerificationError("Authorization is not in pending state")

    if not auth.verification_token:
        raise VerificationError("Missing verification token")

    # Build verification URL – must use the authorized scheme/host/port
    port_part = f":{auth.port}" if auth.port else ""
    base = f"{auth.scheme}://{auth.hostname}{port_part}"
    verify_url = urljoin(base, CHALLENGE_PATH)

    # Enforce HTTPS unless dev mode explicitly allows HTTP
    if auth.scheme != "https" and not CONFIG.allow_http:
        raise VerificationError("HTTP scheme not allowed for verification")

    try:
        resp = requests.get(verify_url, timeout=REQUEST_TIMEOUT, allow_redirects=False)
    except requests.RequestException as exc:
        logger.warning("Verification request failed for %s: %s", verify_url, exc)
        raise VerificationError(f"Unable to reach challenge URL: {exc}") from exc

    if resp.status_code != 200:
        raise VerificationError(f"Challenge URL returned {resp.status_code}")

    # Compare token – strip whitespace
    presented = resp.text.strip()
    if presented != auth.verification_token:
        logger.warning("Token mismatch for %s (expected %s, got %s)",
                       auth.hostname, auth.verification_token, presented)
        raise VerificationError("Challenge token does not match")

    # Success – mark verified
    if not mark_verified(auth.id):
        raise VerificationError("Failed to update authorization status")

    logger.info("Hosted‑file verification succeeded for %s", auth.hostname)
    return True


def start_verification(user_id: int, hostname: str, **kwargs) -> TargetAuthorization:
    """
    Convenience wrapper used by the API: creates a pending authorization record
    and returns it with the challenge token so the caller can instruct the user.
    """
    from agentqe.security.authorization.authorization_repository import create_authorization

    auth = create_authorization(user_id, hostname, **kwargs)
    return auth