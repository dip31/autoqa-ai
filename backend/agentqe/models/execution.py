from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_execution_id() -> str:
    return f"exec_{uuid.uuid4().hex[:16]}"


@dataclass
class ExecutionResult:
    """
    Structured result of a single Phase 5 test execution.

    Backwards compatible with the pre-Phase-5 dataclass: every original field
    (``test_id``, ``status``, ``duration_ms``, ``error``, ``coverage``,
    ``healed``, ``screenshot_path``, ``security_findings``, ``metadata``) is
    preserved with the same name and default. Phase 5 adds the fields the
    execution layer, the API, and the UI need.

    Nothing here may contain secrets — the executor redacts before building
    this object.
    """

    # ── Identity ──────────────────────────────────────────────────────────
    # NOTE: ``test_id`` and ``status`` stay first so the pre-Phase-5 positional
    # construction ExecutionResult(test_id, status, ...) keeps working.
    test_id: str = ""
    status: str = "skipped"
    execution_id: str = field(default_factory=_new_execution_id)

    # ── Outcome ───────────────────────────────────────────────────────────
    #: passed | failed | skipped | blocked | unsupported | timeout | error
    #: playwright | browser_use | hybrid | none
    executor: str = "none"
    error: Optional[str] = None
    #: Structural failure category (see execution.schemas.FailureCategory).
    error_category: Optional[str] = None

    # ── Timing ────────────────────────────────────────────────────────────
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0

    # ── Step accounting ───────────────────────────────────────────────────
    steps_total: int = 0
    steps_completed: int = 0
    failed_step: Optional[int] = None
    steps: List[Dict[str, Any]] = field(default_factory=list)

    # ── Assertion accounting ──────────────────────────────────────────────
    assertions_total: int = 0
    assertions_passed: int = 0
    assertions_failed: int = 0
    assertions: List[Dict[str, Any]] = field(default_factory=list)

    # ── Evidence ──────────────────────────────────────────────────────────
    screenshots: List[Dict[str, Any]] = field(default_factory=list)
    network_evidence: List[Dict[str, Any]] = field(default_factory=list)
    console_errors: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    trace_path: Optional[str] = None
    evidence_refs: List[str] = field(default_factory=list)

    # ── Page / navigation ─────────────────────────────────────────────────
    start_url: Optional[str] = None
    page_url: Optional[str] = None
    final_url: Optional[str] = None

    # ── Phase 4 ranking provenance (needed for future Transformer training) ─
    rank_position: Optional[int] = None
    priority_score: Optional[float] = None
    predicted_priority: Optional[float] = None
    ranking_mode: Optional[str] = None
    model_status: Optional[str] = None
    model_version: Optional[str] = None
    feature_version: Optional[str] = None
    features: Dict[str, float] = field(default_factory=dict)
    feature_contributions: Dict[str, float] = field(default_factory=dict)

    # ── Legacy fields (preserved) ─────────────────────────────────────────
    coverage: float = 0.0
    healed: bool = False
    screenshot_path: Optional[str] = None
    security_findings: int = 0

    # ── Free-form ─────────────────────────────────────────────────────────
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Legacy positional usage was ExecutionResult(test_id, status, ...).
        if not self.test_id:
            raise ValueError("ExecutionResult requires a non-empty test_id")
        self.started_at = self.started_at or _utc_now_iso()

    # ── Convenience ───────────────────────────────────────────────────────
    @property
    def executed(self) -> bool:
        return self.status in ("passed", "failed", "timeout", "error")

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    @property
    def training_record(self) -> Dict[str, Any]:
        """
        Training-shaped projection for a *future* Transformer retrain.

        Phase 5 records what it observed. It does NOT invent defect severity,
        novelty, root cause, or recovery success — those are Phase 6 fields and
        are intentionally absent.
        """
        return {
            "test_id": self.test_id,
            "features": dict(self.features),
            "predicted_priority": self.predicted_priority,
            "ranking_mode": self.ranking_mode,
            "model_status": self.model_status,
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "rank_position": self.rank_position,
            "priority_score": self.priority_score,
            "execution_status": self.status,
            "executor": self.executor,
            "duration_ms": round(self.duration_ms, 2),
            "failure": (
                {
                    "category": self.error_category,
                    "message": self.error,
                    "step_index": self.failed_step,
                }
                if self.error or self.error_category
                else None
            ),
        }

    def to_dict(self) -> dict:
        return {
            "execution_id": self.execution_id,
            "test_id": self.test_id,
            "status": self.status,
            "executor": self.executor,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": round(self.duration_ms, 2),
            "steps_total": self.steps_total,
            "steps_completed": self.steps_completed,
            "failed_step": self.failed_step,
            "steps": list(self.steps),
            "assertions_total": self.assertions_total,
            "assertions_passed": self.assertions_passed,
            "assertions_failed": self.assertions_failed,
            "assertions": list(self.assertions),
            "error": self.error,
            "error_category": self.error_category,
            "screenshots": list(self.screenshots),
            "network_evidence": list(self.network_evidence),
            "console_errors": list(self.console_errors),
            "artifacts": list(self.artifacts),
            "trace_path": self.trace_path,
            "page_url": self.page_url,
            "start_url": self.start_url,
            "final_url": self.final_url,
            "evidence_refs": list(self.evidence_refs),
            "rank_position": self.rank_position,
            "priority_score": self.priority_score,
            "predicted_priority": self.predicted_priority,
            "ranking_mode": self.ranking_mode,
            "model_status": self.model_status,
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "features": dict(self.features),
            "feature_contributions": dict(self.feature_contributions),
            # legacy
            "coverage": self.coverage,
            "healed": self.healed,
            "screenshot_path": self.screenshot_path,
            "security_findings": self.security_findings,
            "metadata": dict(self.metadata),
        }

    # ── Row mapping (for persistence) ─────────────────────────────────────
    def to_record(self) -> Dict[str, Any]:
        """Flat, JSON-serialisable mapping used by the repository layer."""
        import json

        def _dump(value: Any) -> Optional[str]:
            if value in (None, [], {}):
                return None
            return json.dumps(value)

        return {
            "execution_id": self.execution_id,
            "test_id": self.test_id,
            "test_title": (self.metadata or {}).get("test_title"),
            "status": self.status,
            "executor": self.executor,
            "error": self.error,
            "error_category": self.error_category,
            "started_at": self.started_at,
            "completed_at": self.completed_at or _utc_now_iso(),
            "duration_ms": self.duration_ms,
            "steps_total": self.steps_total,
            "steps_completed": self.steps_completed,
            "failed_step": self.failed_step,
            "assertions_total": self.assertions_total,
            "assertions_passed": self.assertions_passed,
            "assertions_failed": self.assertions_failed,
            "start_url": self.start_url,
            "page_url": self.page_url,
            "final_url": self.final_url,
            "trace_path": self.trace_path,
            "rank_position": self.rank_position,
            "priority_score": self.priority_score,
            "predicted_priority": self.predicted_priority,
            "ranking_mode": self.ranking_mode,
            "model_status": self.model_status,
            "model_version": self.model_version,
            "feature_version": self.feature_version,
            "features_json": _dump(self.features),
            "feature_contributions_json": _dump(self.feature_contributions),
            "screenshots_json": _dump(self.screenshots),
            "network_evidence_json": _dump(self.network_evidence),
            "console_errors_json": _dump(self.console_errors),
            "artifacts_json": _dump(self.artifacts),
            "evidence_refs_json": _dump(self.evidence_refs),
            "steps_json": _dump(self.steps),
            "training_json": _dump(self.training_record),
            "metadata_json": _dump(self.metadata),
        }
