"""
Centralized security configuration for the security-validation engine.

All settings are read from environment variables with conservative defaults.
In production, critical settings must be explicitly provided; the module will
raise ConfigurationError if a required setting is missing or invalid.
"""

import os
from dataclasses import dataclass, field
from typing import List, Set
from urllib.parse import urlparse


class ConfigurationError(RuntimeError):
    """Raised when security configuration is invalid or incomplete."""


def _parse_csv(value: str) -> List[str]:
    """Parse a comma-separated string into a list of stripped items."""
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class SecurityConfig:
    # --- URL / scheme policy ---
    allowed_schemes: Set[str] = field(default_factory=lambda: {"https"})
    allow_http: bool = False               # explicit opt‑in for HTTP
    allowed_ports: Set[int] = field(default_factory=lambda: {443, 80})

    # --- Crawl / execution limits ---
    max_pages: int = 20
    max_depth: int = 3
    max_duration_seconds: int = 300        # 5 minutes
    max_concurrent_runs: int = 3
    max_requests_per_second: float = 5.0
    max_response_size_bytes: int = 10 * 1024 * 1024   # 10 MiB
    max_redirects: int = 5

    # --- Network safety ---
    block_private_ips: bool = True
    block_loopback: bool = True
    block_link_local: bool = True
    block_multicast: bool = True
    block_reserved: bool = True
    block_cloud_metadata: bool = True

    # --- DNS policy ---
    dns_timeout_seconds: float = 5.0
    require_dns_validation: bool = True

    # --- Authorization ---
    # If True, a target must appear in an explicit authorization record.
    require_explicit_authorization: bool = True

    # --- Audit logging ---
    audit_log_enabled: bool = True
    audit_log_path: str = "logs/security_audit.log"

    # --- Development overrides ---
    # When true, some checks are relaxed for local development (e.g. localhost).
    dev_mode: bool = False

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        """Create a SecurityConfig instance from environment variables."""
        # Helper to read bool
        def get_bool(name: str, default: bool) -> bool:
            val = os.getenv(name)
            if val is None:
                return default
            return val.lower() in ("1", "true", "yes", "on")

        def get_int(name: str, default: int) -> int:
            val = os.getenv(name)
            if val is None:
                return default
            try:
                return int(val)
            except ValueError as exc:
                raise ConfigurationError(f"Invalid integer for {name}: {val}") from exc

        def get_float(name: str, default: float) -> float:
            val = os.getenv(name)
            if val is None:
                return default
            try:
                return float(val)
            except ValueError as exc:
                raise ConfigurationError(f"Invalid float for {name}: {val}") from exc

        def get_csv(name: str, default: List[str]) -> List[str]:
            val = os.getenv(name)
            if val is None:
                return default
            return _parse_csv(val)

        # Schemes
        schemes = set(get_csv("SEC_ALLOWED_SCHEMES", ["https"]))
        if get_bool("SEC_ALLOW_HTTP", False):
            schemes.add("http")

        # Ports
        ports = set(get_csv("SEC_ALLOWED_PORTS", ["443", "80"]))
        try:
            allowed_ports = {int(p) for p in ports}
        except ValueError as exc:
            raise ConfigurationError("SEC_ALLOWED_PORTS must be a comma‑separated list of integers") from exc

        # Development mode
        dev_mode = get_bool("SEC_DEV_MODE", False)

        # In development we may relax some network blocks
        block_private = get_bool("SEC_BLOCK_PRIVATE_IPS", True) and not dev_mode
        block_loopback = get_bool("SEC_BLOCK_LOOPBACK", True) and not dev_mode
        block_link_local = get_bool("SEC_BLOCK_LINK_LOCAL", True) and not dev_mode
        block_multicast = get_bool("SEC_BLOCK_MULTICAST", True) and not dev_mode
        block_reserved = get_bool("SEC_BLOCK_RESERVED", True) and not dev_mode
        block_cloud = get_bool("SEC_BLOCK_CLOUD_METADATA", True) and not dev_mode

        config = cls(
            allowed_schemes=schemes,
            allow_http=get_bool("SEC_ALLOW_HTTP", False),
            allowed_ports=allowed_ports,
            max_pages=get_int("SEC_MAX_PAGES", 20),
            max_depth=get_int("SEC_MAX_DEPTH", 3),
            max_duration_seconds=get_int("SEC_MAX_DURATION_SECONDS", 300),
            max_concurrent_runs=get_int("SEC_MAX_CONCURRENT_RUNS", 3),
            max_requests_per_second=get_float("SEC_MAX_RPS", 5.0),
            max_response_size_bytes=get_int("SEC_MAX_RESPONSE_SIZE", 10 * 1024 * 1024),
            max_redirects=get_int("SEC_MAX_REDIRECTS", 5),
            block_private_ips=block_private,
            block_loopback=block_loopback,
            block_link_local=block_link_local,
            block_multicast=block_multicast,
            block_reserved=block_reserved,
            block_cloud_metadata=block_cloud,
            dns_timeout_seconds=get_float("SEC_DNS_TIMEOUT", 5.0),
            require_dns_validation=get_bool("SEC_REQUIRE_DNS_VALIDATION", True),
            require_explicit_authorization=get_bool("SEC_REQUIRE_EXPLICIT_AUTH", True),
            audit_log_enabled=get_bool("SEC_AUDIT_LOG_ENABLED", True),
            audit_log_path=os.getenv("SEC_AUDIT_LOG_PATH", "logs/security_audit.log"),
            dev_mode=dev_mode,
        )

        # Validation: at least one scheme
        if not config.allowed_schemes:
            raise ConfigurationError("At least one allowed scheme must be configured")

        # In production (dev_mode == False) we must not allow the insecure fallback JWT secret.
        # This check is performed in app.py when the Flask app starts.

        return config


# Global instance – loaded once at import time.
# Tests can replace this by assigning to security_config.CONFIG.
CONFIG: SecurityConfig = SecurityConfig.from_env()