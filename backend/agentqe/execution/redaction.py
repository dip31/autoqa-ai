"""
Phase 5 — Safe Test Data & Redaction.

AgentQE execution must never use, log, or persist real secrets. This module is
the single choke point for that guarantee:

* :func:`redact_text` scrubs free-form strings (errors, console output, DOM
  text) before they leave the executor.
* :func:`redact_url` scrubs query strings, userinfo, and fragments.
* :func:`redact_headers` redacts sensitive headers (reusing the crawler's
  ``SENSITIVE_HEADERS`` set so behaviour stays consistent).
* :func:`sanitize_step_value` decides what value is *safe to type* into a
  field, substituting a configured test-credential reference or a synthetic
  placeholder for anything credential-shaped.

Nothing here reads the process environment for secrets. Test credentials come
only from :class:`~agentqe.execution.config.ExecutionConfig.credentials`,
which is an explicit opt-in allow-list of synthetic values.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

logger = logging.getLogger(__name__)

REDACTED = "[REDACTED]"

#: Reuse the crawler's list so redaction stays consistent across phases.
try:  # pragma: no cover - import guard only
    from agentqe.crawler.application_crawler import SENSITIVE_HEADERS  # type: ignore
except Exception:  # pragma: no cover
    SENSITIVE_HEADERS = {
        "authorization", "proxy-authorization", "cookie", "set-cookie",
        "x-api-key", "api-key", "token", "access-token", "refresh-token",
        "csrf", "xsrf", "session", "secret", "x-csrf-token", "x-xsrf-token",
        "x-auth-token", "x-access-token", "x-refresh-token",
    }

#: Query-string parameters whose values are redacted.
SENSITIVE_QUERY_PARAMS = {
    "access_token", "api_key", "apikey", "auth", "authorization", "code",
    "credential", "credentials", "id_token", "key", "pass", "passwd",
    "password", "pwd", "refresh_token", "secret", "session", "sig",
    "signature", "state", "token", "x-api-key", "xsrf",
}

#: Field / attribute names that indicate credential-shaped data.
SENSITIVE_FIELD_NAMES = {
    "access_token", "api-key", "api_key", "apikey", "auth", "authorization",
    "client_secret", "confirm_password", "credential", "csrf", "current_password",
    "id_token", "passwd", "password", "password1", "password2", "pass",
    "pin", "pwd", "refresh_token", "secret", "session", "sessionid",
    "session_id", "signature", "token", "x-api-key", "x-auth-token", "xsrf",
}

#: Regexes applied by :func:`redact_text`.
_TEXT_PATTERNS: List[Tuple[re.Pattern, str]] = [
    # Authorization: Bearer <jwt-or-opaque>
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-~+/]{8,}=*"), f"Bearer {REDACTED}"),
    (re.compile(r"(?i)\bbasic\s+[A-Za-z0-9+/]{8,}=*"), f"Basic {REDACTED}"),
    # key=value / key: value for credential-shaped keys
    (
        re.compile(
            r"(?i)\b("
            r"password|passwd|pwd|pass|secret|token|api[_-]?key|access[_-]?token|"
            r"refresh[_-]?token|client[_-]?secret|auth(?:orization)?|session[_-]?id|"
            r"cookie|csrf|xsrf|pin"
            r")(\s*[:=]\s*)(\"|')?([^\s\"',;&)}\]]{3,})(\3)?"),
        lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}",
    ),
    # JWTs appearing anywhere
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\b"),
        REDACTED,
    ),
    # Common provider key shapes
    (re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"), REDACTED),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), REDACTED),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), REDACTED),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}\b"), REDACTED),
    (re.compile(r"\bey[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"), REDACTED),
]

#: Long high-entropy strings (32+ chars, no spaces) look like tokens.
_HEXISH = re.compile(r"^[A-Za-z0-9_\-+/=]{32,}$")
_HEX_ONLY = re.compile(r"^[0-9a-fA-F]{32,}$")

#: Maximum stored length for any redacted/recorded string.
MAX_RECORDED_TEXT = 2000


def is_sensitive_name(name: Optional[str]) -> bool:
    """True when ``name`` looks like a credential/secret identifier."""
    if not name:
        return False
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    if not normalized:
        return False
    if normalized in SENSITIVE_FIELD_NAMES:
        return True
    # password / passwd / secret / token as part of a composite name
    return any(
        token in normalized
        for token in ("password", "passwd", "secret", "token", "api_key", "apikey", "credential")
    )


def looks_like_secret(value: Optional[str]) -> bool:
    """
    Heuristic: does this *value* look like real secret material?

    Used to decide whether a generated step's literal value must be replaced
    with a safe synthetic value.
    """
    if value is None:
        return False
    text = str(value).strip()
    if len(text) < 8:
        return False
    if text.startswith("${") or text.startswith("{{") or text.startswith("$ENV"):
        return False
    if _HEX_ONLY.match(text) or _HEXISH.match(text):
        return True
    lowered = text.lower()
    if any(marker in lowered for marker in ("sk-", "ghp_", "akia", "aiza", "bearer ")):
        return True
    if lowered.startswith("eyj") and lowered.count(".") >= 2:
        return True
    # Mixed letters+digits of decent length with no spaces looks machine-made.
    if " " not in text and any(c.isdigit() for c in text) and any(c.isalpha() for c in text):
        if len(text) >= 16:
            return True
    return False


def redact_text(value: Any, max_length: int = MAX_RECORDED_TEXT) -> str:
    """
    Scrub secret-shaped substrings from free-form text.

    Safe to call on errors, console messages, DOM text, and assertion output.
    """
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    for pattern, replacement in _TEXT_PATTERNS:
        if callable(replacement):
            text = pattern.sub(replacement, text)
        else:
            text = pattern.sub(replacement, text)
    if len(text) > max_length:
        text = text[:max_length] + f"...[truncated {len(text) - max_length} chars]"
    return text


def redact_url(url: Optional[str], max_length: int = 500) -> str:
    """
    Return a display-safe URL.

    Redacts userinfo (``user:pass@``), credential-shaped query parameters, and
    the fragment (often carries tokens). Keeps path structure intact because
    it is essential evidence.
    """
    if not url:
        return ""
    text = str(url)
    try:
        parsed = urlparse(text)
    except ValueError:
        return redact_text(text, max_length)

    netloc = parsed.netloc
    if "@" in netloc:
        userinfo, _, hostpart = netloc.rpartition("@")
        user = userinfo.split(":", 1)[0]
        netloc = f"{user}:{REDACTED}@{hostpart}" if ":" in userinfo else f"{REDACTED}@{hostpart}"

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    safe_pairs = [
        (k, REDACTED if k.strip().lower() in SENSITIVE_QUERY_PARAMS else v)
        for k, v in query_pairs
    ]
    query = urlencode(safe_pairs, doseq=True)
    fragment = REDACTED if parsed.fragment else ""

    safe = urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, query, fragment))
    return redact_text(safe, max_length)


def redact_headers(headers: Optional[Dict[str, Any]], max_keys: int = 20,
                   max_value_length: int = 200) -> Dict[str, str]:
    """
    Redact sensitive headers and bound the output.

    Full request headers are never logged; only a bounded, redacted subset is
    kept as evidence.
    """
    if not headers:
        return {}
    safe: Dict[str, str] = {}
    try:
        items = list(headers.items())
    except AttributeError:
        return {}
    for key, value in items[:max_keys]:
        lower = str(key).lower()
        if lower in SENSITIVE_HEADERS or is_sensitive_name(lower):
            safe[str(key)] = REDACTED
            continue
        text = "" if value is None else str(value)
        text = redact_text(text, max_value_length)
        safe[str(key)] = text
    return safe


def redact_mapping(data: Optional[Dict[str, Any]], max_depth: int = 4) -> Dict[str, Any]:
    """Recursively redact a dict, dropping sensitive values wholesale."""
    if not data or max_depth <= 0:
        return {}
    safe: Dict[str, Any] = {}
    for key, value in list(data.items())[:100]:
        if is_sensitive_name(key):
            safe[str(key)] = REDACTED
            continue
        if isinstance(value, dict):
            safe[str(key)] = redact_mapping(value, max_depth - 1)
        elif isinstance(value, (list, tuple)):
            safe[str(key)] = [
                redact_mapping(v, max_depth - 1) if isinstance(v, dict)
                else redact_text(v, 200) if isinstance(v, str)
                else v
                for v in list(value)[:50]
            ]
        elif isinstance(value, str):
            safe[str(key)] = redact_text(value, 200)
        else:
            safe[str(key)] = value
    return safe


# ── Safe input values ───────────────────────────────────────────────────────

#: Maps a recognised field name to the logical credential key used for lookup.
_CREDENTIAL_KEY_BY_NAME = {
    "password": "password",
    "confirm_password": "password",
    "current_password": "password",
    "new_password": "password",
    "passwd": "password",
    "pwd": "password",
    "pass": "password",
    "pin": "pin",
    "otp": "otp",
    "token": "token",
    "access_token": "token",
    "secret": "secret",
    "api_key": "api_key",
    "apikey": "api_key",
}


def credential_key_for(name: Optional[str]) -> Optional[str]:
    """Return the logical credential key for a field name, if any."""
    if not name:
        return None
    normalized = re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")
    if normalized in _CREDENTIAL_KEY_BY_NAME:
        return _CREDENTIAL_KEY_BY_NAME[normalized]
    for field_name, key in _CREDENTIAL_KEY_BY_NAME.items():
        if field_name in normalized:
            return key
    return None


def sanitize_step_value(
    field_name: Optional[str],
    value: Any,
    config: Any = None,
) -> Tuple[Any, str]:
    """
    Decide what is safe to *type* into ``field_name``.

    Returns ``(safe_value, note)`` where ``note`` describes the substitution
    for the execution record (``""`` when the value was kept verbatim).

    Rules:
      1. Credential-shaped field  → configured synthetic reference, else the
         safe placeholder. The real/generated value is discarded.
      2. Non-credential field but the value looks like secret material
         → the safe synthetic value.
      3. Otherwise → keep the value, truncated.
    """
    from agentqe.execution.config import get_execution_config

    cfg = config or get_execution_config()

    if value is None:
        return None, ""

    if is_sensitive_name(field_name):
        key = credential_key_for(field_name) or "password"
        reference = cfg.resolve_credential(key)
        if reference is None:
            reference = cfg.safe_credential_placeholder
            note = f"sensitive field sanitized; no configured reference for '{key}', used safe placeholder"
        else:
            note = f"sensitive field sanitized; used configured test reference '{key}'"
        return reference, note

    text = str(value)
    if looks_like_secret(text):
        return cfg.safe_synthetic_value, (
            "value looked like secret material; replaced with safe synthetic value"
        )
    if len(text) > 200:
        return text[:200], "value truncated to 200 characters"
    return text, ""


def safe_value_for_display(value: Any) -> Any:
    """Last-line display guard: never surface anything secret-shaped."""
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    if looks_like_secret(text):
        return REDACTED
    return redact_text(text, 500)


__all__ = [
    "REDACTED", "SENSITIVE_HEADERS", "SENSITIVE_QUERY_PARAMS", "SENSITIVE_FIELD_NAMES",
    "is_sensitive_name", "looks_like_secret", "redact_text", "redact_url",
    "redact_headers", "redact_mapping", "sanitize_step_value",
    "credential_key_for", "safe_value_for_display",
]
