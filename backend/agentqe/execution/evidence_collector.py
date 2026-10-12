"""
Phase 5 — Evidence Collector.

Collects bounded, redacted evidence for a single execution:

* screenshots (initial / per-step / pre-failure / final)
* Playwright trace archive (optional, written to disk — never a DB blob)
* browser console errors
* relevant network failures
* start / final URL

Artifacts are written under ``ExecutionConfig.artifact_dir`` using the same
safety rules as the Phase 1.5D crawler: safe filenames derived from a SHA-256
digest, size bounds, and an integrity hash. Only *paths and references* are
returned — the database never stores image or trace bytes.
"""

import hashlib
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from agentqe.execution.config import ExecutionConfig, get_execution_config
from agentqe.execution.interfaces import IEvidenceCollector
from agentqe.execution.redaction import redact_text, redact_url

logger = logging.getLogger(__name__)

_SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")


def _safe_slug(text: str, max_len: int = 40) -> str:
    """Reduce a label to a filesystem-safe slug."""
    cleaned = "".join(c if c in _SAFE_CHARS else "_" for c in str(text or ""))
    cleaned = cleaned.strip("._-") or "artifact"
    return cleaned[:max_len]


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PlaywrightEvidenceCollector(IEvidenceCollector):
    """
    Evidence collector bound to a single Playwright page.

    Attach listeners on :meth:`start`, drive the page, then call :meth:`finish`
    to obtain the evidence bundle. The collector is deliberately tolerant: a
    screenshot or trace failure never aborts the test.
    """

    def __init__(self, config: Optional[ExecutionConfig] = None,
                 execution_id: str = "unbound"):
        self.config = config or get_execution_config()
        self.execution_id = execution_id
        self.started_at = time.time()

        self.screenshots: List[Dict[str, Any]] = []
        self.console_errors: List[Dict[str, Any]] = []
        self.network_evidence: List[Dict[str, Any]] = []
        self.network_failures: List[Dict[str, Any]] = []
        self.trace_path: Optional[str] = None
        self.warnings: List[str] = []

        self._page: Any = None
        self._artifact_dir = ""
        self._trace_dir = ""
        self._trace_started = False
        self._page_errors: List[Dict[str, Any]] = []
        self._listeners_installed = False
        self._finished = False

    # ── Lifecycle ──────────────────────────────────────────────────────
    def start(self, execution_id: str = "", page: Any = None) -> None:
        self.execution_id = execution_id or self.execution_id
        self.started_at = time.time()
        self._page = page
        self._ensure_dirs()
        if page is not None:
            self._install_listeners(page)
        if self.config.playwright_trace_enabled and page is not None:
            self._start_trace()

    def finish(self, page_url: Optional[str] = None) -> Dict[str, Any]:
        if self._finished:
            return self.bundle(page_url)
        trace_error = self._stop_trace()
        if trace_error:
            self.warnings.append(trace_error)
        self._finished = True
        return self.bundle(page_url)

    def bundle(self, page_url: Optional[str] = None) -> Dict[str, Any]:
        """The evidence payload stored on the ExecutionResult."""
        return {
            "screenshots": list(self.screenshots),
            "console_errors": list(self.console_errors)[: self.config.max_console_errors],
            "network_evidence": (
                list(self.network_evidence)[: self.config.max_network_events]
                if self.config.collect_network_evidence else []
            ),
            "network_failures": list(self.network_failures)[: self.config.max_network_events],
            "page_errors": list(self._page_errors)[: self.config.max_console_errors],
            "trace_path": self.trace_path,
            "duration_ms": round((time.time() - self.started_at) * 1000, 2),
            "warnings": list(self.warnings),
            "page_url": redact_url(page_url) if page_url else None,
        }

    # ── Screenshot ─────────────────────────────────────────────────────
    def capture_screenshot(
        self,
        label: str,
        step_index: Optional[int] = None,
        page_url: Optional[str] = None,
        page: Any = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Capture a bounded screenshot and return its metadata (no bytes).

        Returns ``None`` when screenshots are disabled or capture failed; a
        failure is recorded as a warning, never raised.
        """
        if not self.config.screenshots_enabled:
            return None
        target_page = page or self._page
        if target_page is None:
            return None
        self._ensure_dirs()

        slug = _safe_slug(label)
        filename = f"{_safe_slug(self.execution_id)}_{slug}.png"
        filepath = os.path.join(self._artifact_dir, filename)

        try:
            options: Dict[str, Any] = {
                "path": filepath,
                "type": "png",
                "timeout": 10000,
                "full_page": self.config.screenshot_type == "full_page",
            }
            target_page.screenshot(**options)
        except Exception as exc:  # screenshot failures are non-fatal
            message = redact_text(f"screenshot '{label}' failed: {exc}", 200)
            self.warnings.append(message)
            logger.warning("[EvidenceCollector] %s", message)
            if os.path.exists(filepath):
                try:
                    os.remove(filepath)
                except OSError:
                    pass
            return None

        try:
            size = os.path.getsize(filepath)
        except OSError:
            size = None
        if size is not None and size > self.config.max_screenshot_bytes:
            try:
                os.remove(filepath)
            except OSError:
                pass
            self.warnings.append(
                f"screenshot '{label}' exceeded max_screenshot_bytes "
                f"({size} > {self.config.max_screenshot_bytes}); discarded"
            )
            return None

        try:
            digest = _sha256_file(filepath)
        except OSError:
            digest = None

        metadata = {
            "label": label,
            "path": filepath,
            "format": "png",
            "capture_type": self.config.screenshot_type,
            "size_bytes": size,
            "sha256": digest,
            "step_index": step_index,
            "page_url": redact_url(page_url or self._safe_page_url(target_page)),
            "captured_at": time.time(),
        }
        self.screenshots.append(metadata)
        return metadata

    # ── Trace ──────────────────────────────────────────────────────────
    def _start_trace(self) -> None:
        if self._trace_started or self._page is None:
            return
        try:
            self._page.context.tracing.start(
                screenshots=self.config.playwright_trace_screenshots,
                snapshots=self.config.playwright_trace_snapshots,
            )
            self._trace_started = True
        except Exception as exc:
            self.warnings.append(
                redact_text(f"playwright tracing unavailable: {exc}", 200)
            )
            logger.info("[EvidenceCollector] tracing unavailable: %s", exc)

    def _stop_trace(self) -> Optional[str]:
        if not self._trace_started or self._page is None:
            return None
        try:
            self._ensure_dirs()
            filename = f"{_safe_slug(self.execution_id)}_trace.zip"
            self.trace_path = os.path.join(self._trace_dir, filename)
            self._page.context.tracing.stop(path=self.trace_path)
            self._trace_started = False
        except Exception as exc:
            self._trace_started = False
            return redact_text(f"failed to stop playwright trace: {exc}", 200)
        return None

    # ── Listeners ──────────────────────────────────────────────────────
    def _install_listeners(self, page: Any) -> None:
        if self._listeners_installed:
            return
        self._listeners_installed = True

        def _on_console(message: Any) -> None:
            try:
                if message.type not in ("error", "warning"):
                    return
                self.console_errors.append({
                    "type": message.type,
                    "text": redact_text(getattr(message, "text", "") or "", 500),
                    "location": self._location(getattr(message, "location", None)),
                    "timestamp": time.time(),
                })
            except Exception:
                pass

        def _on_page_error(error: Any) -> None:
            self._page_errors.append({
                "message": redact_text(str(error), 500),
                "timestamp": time.time(),
            })

        def _on_request_failed(request: Any) -> None:
            if not self.config.collect_network_evidence:
                return
            failure = getattr(request, "failure", None)
            self.network_failures.append({
                "url": redact_url(getattr(request, "url", "")),
                "method": str(getattr(request, "method", "") or ""),
                "resource_type": str(getattr(request, "resource_type", "") or ""),
                "error": redact_text(str(failure) if failure else "request failed", 200),
                "kind": "request_failed",
                "timestamp": time.time(),
            })

        def _on_response(response: Any) -> None:
            if not self.config.collect_network_evidence:
                return
            status = getattr(response, "status", 0) or 0
            if status < 400:
                return
            request = getattr(response, "request", None)
            self.network_evidence.append({
                "url": redact_url(getattr(response, "url", "")),
                "status": status,
                "method": str(getattr(request, "method", "") or "") if request else "",
                "kind": "http_error",
                "timestamp": time.time(),
            })

        for event, handler in (
            ("console", _on_console),
            ("pageerror", _on_page_error),
            ("requestfailed", _on_request_failed),
            ("response", _on_response),
        ):
            try:
                page.on(event, handler)
            except Exception:
                pass

    @staticmethod
    def _location(location: Any) -> Optional[Dict[str, Any]]:
        if not location:
            return None
        try:
            return {
                "url": redact_url(location.get("url")),
                "line": location.get("lineNumber"),
                "column": location.get("columnNumber"),
            }
        except Exception:
            return None

    @staticmethod
    def _safe_page_url(page: Any) -> str:
        try:
            return str(getattr(page, "url", "") or "")
        except Exception:
            return ""

    # ── Dirs ───────────────────────────────────────────────────────────
    def _ensure_dirs(self) -> None:
        if not self._artifact_dir:
            self._artifact_dir = self.config.artifact_dir
            os.makedirs(self._artifact_dir, exist_ok=True)
        if not self._trace_dir:
            self._trace_dir = self.config.trace_dir
            os.makedirs(self._trace_dir, exist_ok=True)


class NullEvidenceCollector(IEvidenceCollector):
    """No-op collector used when evidence capture is disabled entirely."""

    def __init__(self, config: Optional[ExecutionConfig] = None, execution_id: str = "unbound"):
        self.config = config or get_execution_config()
        self.execution_id = execution_id

    def start(self, execution_id: str = "", page: Any = None) -> None:  # noqa: D102
        return None

    def capture_screenshot(self, label: str, step_index: Optional[int] = None,
                           page_url: Optional[str] = None) -> Optional[Dict[str, Any]]:  # noqa: D102
        return None

    def finish(self, page_url: Optional[str] = None) -> Dict[str, Any]:  # noqa: D102
        return {
            "screenshots": [], "console_errors": [], "network_evidence": [],
            "network_failures": [], "page_errors": [], "trace_path": None,
            "duration_ms": 0.0, "warnings": [], "page_url": None,
        }


def artifact_reference(metadata: Dict[str, Any], execution_id: str) -> Dict[str, Any]:
    """Build a persistence-friendly artifact reference from screenshot metadata."""
    return {
        "artifact_type": "screenshot",
        "path": metadata.get("path"),
        "label": metadata.get("label"),
        "step_index": metadata.get("step_index"),
        "size_bytes": metadata.get("size_bytes"),
        "sha256": metadata.get("sha256"),
        "url": metadata.get("page_url"),
        "execution_id": execution_id,
    }


def trace_reference(trace_path: str, execution_id: str) -> Dict[str, Any]:
    size = None
    try:
        size = os.path.getsize(trace_path)
    except OSError:
        pass
    return {
        "artifact_type": "trace",
        "path": trace_path,
        "label": "playwright-trace",
        "size_bytes": size,
        "execution_id": execution_id,
    }


__all__ = [
    "PlaywrightEvidenceCollector",
    "NullEvidenceCollector",
    "artifact_reference",
    "trace_reference",
]
