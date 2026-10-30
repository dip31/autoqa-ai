"""
Evidence collection & sanitisation helper used by validators.
"""
from __future__ import annotations

import re
from typing import Dict, Any, List
from urllib.parse import urlparse, parse_qs

from agentqe.security.models import SecurityEvidence
from agentqe.security.security_config import CONFIG


# Patterns for secret-like values
SECRET_KEYS = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|access[_-]?token|refresh[_-]?token|auth|authorization|cookie|session)",
    re.IGNORECASE,
)

SENSITIVE_QUERY_PARAMS = {
    "password", "pass", "pwd", "secret", "token", "api_key", "apikey",
    "access_token", "refresh_token", "session", "csrf", "xsrf",
}


def _sanitize_dict(d: Dict[str, Any]) -> Dict[str, Any]:
    """Return a shallow copy with secret-like keys removed or masked."""
    out = {}
    for k, v in d.items():
        if SECRET_KEYS.search(k):
            out[k] = "[REDACTED]"
        elif isinstance(v, str) and len(v) > 200:
            out[k] = v[:200] + "...[TRUNCATED]"
        else:
            out[k] = v
    return out


def _sanitize_url(url: str) -> str:
    """Strip credentials and sensitive query parameters from a URL."""
    try:
        parsed = urlparse(url)
        # Remove userinfo
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc += f":{parsed.port}"
        # Filter query
        qs = parse_qs(parsed.query, keep_blank_values=True)
        filtered = {k: v for k, v in qs.items() if k.lower() not in SENSITIVE_QUERY_PARAMS}
        new_query = "&".join(f"{k}={v[0]}" for k, v in filtered.items())
        return parsed._replace(netloc=netloc, query=new_query).geturl()
    except Exception:
        return "[INVALID URL]"


class EvidenceCollector:
    """Collects and stores sanitized evidence linked to findings."""

    def __init__(self, run_id: int):
        self.run_id = run_id
        self._evidence: List[SecurityEvidence] = []

    def add(
        self,
        finding_id: str,
        evidence_type: str,
        url: str,
        method: str = "GET",
        status_code: int | None = None,
        data: Dict[str, Any] | None = None,
    ) -> str:
        """Create an evidence record, sanitise, store, and return its ID."""
        safe_url = _sanitize_url(url)
        safe_data = _sanitize_dict(data or {})
        ev = SecurityEvidence(
            finding_id=finding_id,
            evidence_type=evidence_type,
            url=safe_url,
            method=method,
            status_code=status_code,
            data=safe_data,
            redacted=True,
        )
        self._evidence.append(ev)
        return ev.id

    def get_all(self) -> List[SecurityEvidence]:
        return list(self._evidence)