"""
Phase 5 — Agentic Test Execution Configuration.

All settings are environment-variable driven with safe defaults.

Every value here is deliberately conservative: Playwright is the default and
only mandatory engine, Browser Use is opt-in, and no credential material is
ever read from the ambient environment (see ``ExecutionConfig.credentials``).
"""

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Bounds (mirrors Phase 1.5D screenshot bounds) ────────────────────────────
MAX_SCREENSHOT_BYTES = 5_000_000
MAX_SCREENSHOT_WIDTH = 3840
MAX_SCREENSHOT_HEIGHT = 2160

#: Directory (relative to the repository root) for execution artifacts.
DEFAULT_ARTIFACT_DIR = "backend/data/agentqe/executions"

#: Directory (relative to the repository root) for Playwright traces.
DEFAULT_TRACE_DIR = "backend/data/agentqe/traces"

#: Hard ceiling on the number of tests a single batch request may execute.
DEFAULT_MAX_TESTS_PER_RUN = 50


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning("[ExecutionConfig] %s=%r is not an integer; using %s", name, raw, default)
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning("[ExecutionConfig] %s=%r is not a number; using %s", name, raw, default)
        return default


def _repo_root() -> Path:
    # agentqe/execution/config.py -> backend/agentqe/execution -> ... -> repo root
    return Path(__file__).resolve().parents[3]


def _resolve_dir(relative: str) -> str:
    root = _repo_root()
    candidate = Path(relative)
    if candidate.is_absolute():
        return str(candidate)
    return str(root / candidate)


def _load_credentials() -> Dict[str, str]:
    """
    Load *test* credential references.

    This is an explicit opt-in allow-list of synthetic values used to fill
    credential-shaped form fields during execution. It is intentionally NOT a
    reader of real secrets: values come from
    ``AGENTQE_EXECUTION_CREDENTIALS`` (JSON object) and are treated as safe
    test data by definition.
    """
    raw = os.getenv("AGENTQE_EXECUTION_CREDENTIALS", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("[ExecutionConfig] AGENTQE_EXECUTION_CREDENTIALS is not valid JSON; ignoring")
        return {}
    if not isinstance(parsed, dict):
        logger.warning("[ExecutionConfig] AGENTQE_EXECUTION_CREDENTIALS must be a JSON object; ignoring")
        return {}
    return {str(k): str(v) for k, v in parsed.items()}


@dataclass
class ExecutionConfig:
    """
    Runtime configuration for Phase 5 execution.

    Attributes map 1:1 to environment variables so a deployment can be tuned
    without code changes.
    """

    # ── Engine availability ──────────────────────────────────────────────
    #: Playwright is the primary engine. When False, every run degrades to
    #: structured ``EXECUTOR_ERROR`` results rather than raising.
    playwright_enabled: bool = field(
        default_factory=lambda: _env_bool("AGENTQE_PLAYWRIGHT_ENABLED", True)
    )
    playwright_headless: bool = field(
        default_factory=lambda: _env_bool("AGENTQE_PLAYWRIGHT_HEADLESS", True)
    )
    playwright_browser: str = field(
        default_factory=lambda: os.getenv("AGENTQE_PLAYWRIGHT_BROWSER", "chromium")
    )

    # ── Browser Use (optional, agentic) ──────────────────────────────────
    #: Browser Use is OFF by default. Phase 5 never requires it.
    browser_use_enabled: bool = field(
        default_factory=lambda: _env_bool("AGENTQE_BROWSER_USE_ENABLED", False)
    )
    #: Allow Browser Use as a recovery path when deterministic execution fails.
    browser_use_fallback_enabled: bool = field(
        default_factory=lambda: _env_bool("AGENTQE_BROWSER_USE_FALLBACK_ENABLED", False)
    )
    #: Only fall back for these structural failure categories.
    browser_use_fallback_categories: tuple = field(
        default_factory=lambda: tuple(
            c.strip()
            for c in os.getenv(
                "AGENTQE_BROWSER_USE_FALLBACK_CATEGORIES",
                "ELEMENT_NOT_FOUND,UNSUPPORTED_ACTION",
            ).split(",")
            if c.strip()
        )
    )
    browser_use_max_steps: int = field(
        default_factory=lambda: _env_int("AGENTQE_BROWSER_USE_MAX_STEPS", 8)
    )
    browser_use_timeout_ms: int = field(
        default_factory=lambda: _env_int("AGENTQE_BROWSER_USE_TIMEOUT_MS", 60000)
    )

    # ── Timeouts ─────────────────────────────────────────────────────────
    execution_timeout_ms: int = field(
        default_factory=lambda: _env_int("AGENTQE_EXECUTION_TIMEOUT_MS", 60000)
    )
    step_timeout_ms: int = field(
        default_factory=lambda: _env_int("AGENTQE_STEP_TIMEOUT_MS", 15000)
    )
    navigation_timeout_ms: int = field(
        default_factory=lambda: _env_int("AGENTQE_NAVIGATION_TIMEOUT_MS", 30000)
    )

    # ── Evidence ────────────────────────────────────────────────────────
    screenshots_enabled: bool = field(
        default_factory=lambda: _env_bool("AGENTQE_EXECUTION_SCREENSHOTS", True)
    )
    #: Screenshot after every successful step (noisy — off by default).
    screenshot_per_step: bool = field(
        default_factory=lambda: _env_bool("AGENTQE_EXECUTION_SCREENSHOT_PER_STEP", False)
    )
    screenshot_type: str = field(
        default_factory=lambda: os.getenv("AGENTQE_EXECUTION_SCREENSHOT_TYPE", "viewport")
    )
    max_screenshot_bytes: int = field(
        default_factory=lambda: _env_int(
            "AGENTQE_EXECUTION_MAX_SCREENSHOT_BYTES", MAX_SCREENSHOT_BYTES
        )
    )
    viewport_width: int = field(
        default_factory=lambda: _env_int("AGENTQE_EXECUTION_VIEWPORT_WIDTH", 1280)
    )
    viewport_height: int = field(
        default_factory=lambda: _env_int("AGENTQE_EXECUTION_VIEWPORT_HEIGHT", 720)
    )

    playwright_trace_enabled: bool = field(
        default_factory=lambda: _env_bool("AGENTQE_PLAYWRIGHT_TRACE", False)
    )
    playwright_trace_screenshots: bool = field(
        default_factory=lambda: _env_bool("AGENTQE_PLAYWRIGHT_TRACE_SCREENSHOTS", True)
    )
    playwright_trace_snapshots: bool = field(
        default_factory=lambda: _env_bool("AGENTQE_PLAYWRIGHT_TRACE_SNAPSHOTS", True)
    )

    # ── Evidence collection bounds ───────────────────────────────────────
    max_console_errors: int = field(
        default_factory=lambda: _env_int("AGENTQE_EXECUTION_MAX_CONSOLE_ERRORS", 25)
    )
    max_network_events: int = field(
        default_factory=lambda: _env_int("AGENTQE_EXECUTION_MAX_NETWORK_EVENTS", 50)
    )
    collect_network_evidence: bool = field(
        default_factory=lambda: _env_bool("AGENTQE_EXECUTION_COLLECT_NETWORK", True)
    )

    # ── Storage ──────────────────────────────────────────────────────────
    artifact_dir: str = field(
        default_factory=lambda: _resolve_dir(
            os.getenv("AGENTQE_EXECUTION_ARTIFACT_DIR", DEFAULT_ARTIFACT_DIR)
        )
    )
    trace_dir: str = field(
        default_factory=lambda: _resolve_dir(
            os.getenv("AGENTQE_EXECUTION_TRACE_DIR", DEFAULT_TRACE_DIR)
        )
    )
    persist_executions: bool = field(
        default_factory=lambda: _env_bool("AGENTQE_EXECUTION_PERSIST", True)
    )

    # ── Batch safety ─────────────────────────────────────────────────────
    #: Phase 5 is sequential by design. Values > 1 are clamped (see
    #: ``ExecutionService``) — correctness over speed.
    concurrency: int = field(
        default_factory=lambda: _env_int("AGENTQE_EXECUTION_CONCURRENCY", 1)
    )
    max_tests_per_run: int = field(
        default_factory=lambda: _env_int(
            "AGENTQE_EXECUTION_MAX_TESTS", DEFAULT_MAX_TESTS_PER_RUN
        )
    )
    #: Cap on the number of *unsupported/blocked* results returned verbatim.
    max_artifact_paths_in_result: int = field(
        default_factory=lambda: _env_int("AGENTQE_EXECUTION_MAX_ARTIFACT_REFS", 20)
    )

    # ── Safe test data ───────────────────────────────────────────────────
    #: Synthetic values used to fill credential-shaped fields, keyed by a
    #: logical name (``password``, ``email``, ...). Never real secrets.
    credentials: Dict[str, str] = field(default_factory=_load_credentials)
    #: Used when a step needs a credential and no reference is configured.
    safe_credential_placeholder: str = field(
        default_factory=lambda: os.getenv(
            "AGENTQE_SAFE_CREDENTIAL_PLACEHOLDER", "AgentQE-Test-Value-Do-Not-Use"
        )
    )
    #: Synthetic value for non-secret fields (email, name, search, ...).
    safe_synthetic_value: str = field(
        default_factory=lambda: os.getenv("AGENTQE_SAFE_SYNTHETIC_VALUE", "agentqe-test@example.invalid")
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialisable snapshot for persistence (credentials are excluded)."""
        return {
            "playwright_enabled": self.playwright_enabled,
            "playwright_headless": self.playwright_headless,
            "playwright_browser": self.playwright_browser,
            "browser_use_enabled": self.browser_use_enabled,
            "browser_use_fallback_enabled": self.browser_use_fallback_enabled,
            "browser_use_fallback_categories": list(self.browser_use_fallback_categories),
            "execution_timeout_ms": self.execution_timeout_ms,
            "step_timeout_ms": self.step_timeout_ms,
            "navigation_timeout_ms": self.navigation_timeout_ms,
            "screenshots_enabled": self.screenshots_enabled,
            "screenshot_per_step": self.screenshot_per_step,
            "screenshot_type": self.screenshot_type,
            "playwright_trace_enabled": self.playwright_trace_enabled,
            "collect_network_evidence": self.collect_network_evidence,
            "artifact_dir": self.artifact_dir,
            "trace_dir": self.trace_dir,
            "persist_executions": self.persist_executions,
            "concurrency": self.concurrency,
            "max_tests_per_run": self.max_tests_per_run,
            # Deliberately reports the *count* of configured references only.
            "configured_credential_references": sorted(self.credentials.keys()),
        }

    def effective_concurrency(self) -> int:
        """Phase 5 executes sequentially; anything above 1 is clamped."""
        return 1 if self.concurrency <= 1 else 1

    def resolve_credential(self, key: str) -> Optional[str]:
        """
        Return the configured synthetic value for ``key``.

        ``key`` is a logical name such as ``password``/``email``/``secret``,
        optionally with a field-name suffix (``login_password``).
        """
        if not key:
            return None
        if key in self.credentials:
            return self.credentials[key]
        for name, value in self.credentials.items():
            if name.endswith(f"_{key}") or key.endswith(f"_{name}"):
                return value
        return None


_default_config: Optional[ExecutionConfig] = None


def get_execution_config(refresh: bool = False) -> ExecutionConfig:
    """Return the process-wide execution configuration (lazily built)."""
    global _default_config
    if _default_config is None or refresh:
        _default_config = ExecutionConfig()
    return _default_config


__all__ = [
    "ExecutionConfig",
    "get_execution_config",
    "MAX_SCREENSHOT_BYTES",
    "MAX_SCREENSHOT_WIDTH",
    "MAX_SCREENSHOT_HEIGHT",
]
