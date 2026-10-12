"""
Phase 5 — Execution Persistence.

Stores execution history in dedicated ``agentqe_execution*`` tables. The
existing ``autonomous_*`` tables (legacy AutoQA) are NOT touched.

Design notes:

* JSON payloads use the repo convention: a ``TEXT`` column named ``*_json``
  written with ``json.dumps`` and read with ``json.loads``.
* No image or trace bytes are ever stored — only artifact paths, sizes, and
  SHA-256 digests.
* All writes are best-effort: a persistence failure is reported on the result
  (``persisted=False``) but never breaks an execution.
* The repository is injectable so tests can run without a database.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agentqe.execution.schemas import (
    ExecutionArtifact,
    ExecutionPlan,
    ExecutionResult,
    ExecutionRunResult,
    ExecutionSummary,
)

logger = logging.getLogger(__name__)

try:
    from database.db import execute_query
    DB_AVAILABLE = True
except Exception:  # pragma: no cover
    execute_query = None
    DB_AVAILABLE = False


def _json(value: Any) -> Optional[str]:
    if value in (None, [], {}, ""):
        return None
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def _load_json(value: Any, default: Any = None) -> Any:
    if not value:
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


#: Columns written into ``agentqe_executions`` (ordered, matches init_db.py).
EXECUTION_COLUMNS = (
    "execution_id", "execution_run_id", "autonomous_run_id", "user_id",
    "application_id", "test_id", "test_title", "status", "executor", "layer",
    "error", "error_category", "started_at", "completed_at", "duration_ms",
    "steps_total", "steps_completed", "failed_step", "assertions_total",
    "assertions_passed", "assertions_failed", "start_url", "page_url",
    "final_url", "trace_path", "rank_position", "priority_score",
    "predicted_priority", "ranking_mode", "model_status", "model_version",
    "feature_version", "features_json", "feature_contributions_json",
    "screenshots_json", "network_evidence_json", "console_errors_json",
    "artifacts_json", "evidence_refs_json", "steps_json", "training_json",
    "metadata_json",
)

#: JSON columns expanded on read.
_JSON_COLUMNS = {
    "features_json": ("features", dict),
    "feature_contributions_json": ("feature_contributions", dict),
    "screenshots_json": ("screenshots", list),
    "network_evidence_json": ("network_evidence", list),
    "console_errors_json": ("console_errors", list),
    "artifacts_json": ("artifacts", list),
    "evidence_refs_json": ("evidence_refs", list),
    "steps_json": ("steps", list),
    "training_json": ("training", dict),
    "metadata_json": ("metadata", dict),
}


class ExecutionRepository:
    """
    Persistence for Phase 5 execution history.

    Table layout (see ``database/init_db.py``):
      * ``agentqe_execution_runs``     — one batch
      * ``agentqe_executions``         — one test execution
      * ``agentqe_execution_steps``    — one executed step
      * ``agentqe_execution_artifacts``— screenshots / traces
    """

    def __init__(self, query_fn: Any = None):
        self._query = query_fn or execute_query
        self.available = self._query is not None

    # ── Run ────────────────────────────────────────────────────────────
    def create_run(self, run: Dict[str, Any]) -> Optional[int]:
        """Insert an ``agentqe_execution_runs`` row and return its id."""
        if not self.available:
            return None
        payload = {
            "execution_run_id": run.get("execution_run_id"),
            "user_id": run.get("user_id"),
            "autonomous_run_id": run.get("autonomous_run_id"),
            "application_id": run.get("application_id"),
            "base_url": run.get("base_url"),
            "status": run.get("status", "running"),
            "total_tests": run.get("total_tests", 0),
            "summary_json": _json(run.get("summary")),
            "config_json": _json(run.get("config")),
            "metadata_json": _json(run.get("metadata")),
        }
        try:
            return self._query(
                "INSERT INTO agentqe_execution_runs "
                "(execution_run_id, user_id, autonomous_run_id, application_id, base_url, "
                " status, total_tests, summary_json, config_json, metadata_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    payload["execution_run_id"], payload["user_id"],
                    payload["autonomous_run_id"], payload["application_id"],
                    payload["base_url"], payload["status"], payload["total_tests"],
                    payload["summary_json"], payload["config_json"],
                    payload["metadata_json"],
                ),
            )
        except Exception as exc:
            logger.warning("[ExecutionRepository] could not create execution run: %s", exc)
            return None

    def complete_run(
        self,
        execution_run_id: str,
        summary: ExecutionSummary,
        status: str = "completed",
    ) -> bool:
        if not self.available:
            return False
        try:
            self._query(
                "UPDATE agentqe_execution_runs SET status=?, total_tests=?, passed=?, "
                "failed=?, blocked=?, unsupported=?, timeout=?, error=?, skipped=?, "
                "duration_ms=?, completed_at=? WHERE execution_run_id=?",
                (
                    status, summary.total, summary.passed, summary.failed,
                    summary.blocked, summary.unsupported, summary.timeout,
                    summary.error, summary.skipped, summary.duration_ms,
                    _utc_now(), execution_run_id,
                ),
            )
            return True
        except Exception as exc:
            logger.warning("[ExecutionRepository] could not complete execution run: %s", exc)
            return False

    def get_run(self, execution_run_id: str) -> Optional[Dict[str, Any]]:
        if not self.available:
            return None
        try:
            rows = self._query(
                "SELECT * FROM agentqe_execution_runs WHERE execution_run_id=?",
                (execution_run_id,), fetch=True,
            )
        except Exception as exc:
            logger.warning("[ExecutionRepository] could not read execution run: %s", exc)
            return None
        if not rows:
            return None
        row = dict(rows[0])
        row["summary"] = _load_json(row.pop("summary_json", None), {}) or {}
        row["config"] = _load_json(row.pop("config_json", None), {}) or {}
        row["metadata"] = _load_json(row.pop("metadata_json", None), {}) or {}
        return row

    def list_runs(self, user_id: Optional[int] = None, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.available:
            return []
        try:
            if user_id is not None:
                rows = self._query(
                    "SELECT * FROM agentqe_execution_runs WHERE user_id=? "
                    "ORDER BY id DESC LIMIT ?",
                    (user_id, int(limit)), fetch=True,
                )
            else:
                rows = self._query(
                    "SELECT * FROM agentqe_execution_runs ORDER BY id DESC LIMIT ?",
                    (int(limit),), fetch=True,
                )
        except Exception:
            return []
        return [dict(r) for r in rows or []]

    # ── Executions ─────────────────────────────────────────────────────
    def save_execution(
        self,
        result: ExecutionResult,
        run_id: Optional[int] = None,
        plan: Optional[ExecutionPlan] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[int]:
        """Persist one ExecutionResult plus its steps and artifacts."""
        if not self.available:
            return None
        ctx = context or {}
        record = result.to_record()
        record.setdefault("execution_run_id", ctx.get("execution_run_id"))
        record["autonomous_run_id"] = ctx.get("autonomous_run_id")
        record["user_id"] = ctx.get("user_id")
        record["application_id"] = ctx.get("application_id")
        record["layer"] = (result.metadata or {}).get("layer")

        columns = [c for c in EXECUTION_COLUMNS if c in record]
        values = [record[c] for c in columns]
        placeholders = ",".join(["?"] * len(columns))
        try:
            execution_pk = self._query(
                f"INSERT INTO agentqe_executions ({','.join(columns)}) VALUES ({placeholders})",
                tuple(values),
            )
        except Exception as exc:
            logger.warning("[ExecutionRepository] could not save execution: %s", exc)
            return None

        if result.steps:
            self._save_steps(result, execution_pk, result.execution_id)
        self._save_artifacts(result, execution_pk, result.execution_id)
        return execution_pk

    def _save_steps(self, result: ExecutionResult, execution_pk: Optional[int],
                    execution_id: str) -> None:
        for step in result.steps:
            try:
                self._query(
                    "INSERT INTO agentqe_execution_steps "
                    "(execution_id, execution_pk, step_index, action, target, status, "
                    " duration_ms, selector_used, selector_strategy, error, error_category, "
                    " assertion_type, assertion_passed, screenshot_path, page_url, step_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        execution_id, execution_pk, step.get("index"), step.get("action"),
                        str(step.get("target") or "")[:300], step.get("status"),
                        step.get("duration_ms"), step.get("selector_used"),
                        step.get("selector_strategy"), step.get("error"),
                        step.get("error_category"),
                        (step.get("assertion") or {}).get("assertion_type"),
                        None if (step.get("assertion") or {}).get("passed") is None
                        else int(bool((step.get("assertion") or {}).get("passed"))),
                        step.get("screenshot_path"), step.get("page_url"),
                        _json(step),
                    ),
                )
            except Exception as exc:
                logger.debug("[ExecutionRepository] step insert failed (non-fatal): %s", exc)
                return

    def _save_artifacts(self, result: ExecutionResult, execution_pk: Optional[int],
                        execution_id: str) -> None:
        artifacts: List[Dict[str, Any]] = list(result.artifacts or [])
        for shot in result.screenshots:
            if not any(a.get("path") == shot.get("path") for a in artifacts):
                artifacts.append({
                    "artifact_type": "screenshot", "path": shot.get("path"),
                    "label": shot.get("label"), "step_index": shot.get("step_index"),
                    "size_bytes": shot.get("size_bytes"), "sha256": shot.get("sha256"),
                    "url": shot.get("page_url"),
                })
        for artifact in artifacts:
            if not artifact.get("path"):
                continue
            try:
                self._query(
                    "INSERT INTO agentqe_execution_artifacts "
                    "(execution_id, execution_pk, artifact_type, path, label, step_index, "
                    " size_bytes, sha256, url, metadata_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        execution_id, execution_pk,
                        artifact.get("artifact_type", "screenshot"),
                        str(artifact.get("path"))[:1000], artifact.get("label"),
                        artifact.get("step_index"), artifact.get("size_bytes"),
                        artifact.get("sha256"), artifact.get("url"),
                        _json(artifact.get("metadata")),
                    ),
                )
            except Exception as exc:
                logger.debug("[ExecutionRepository] artifact insert failed (non-fatal): %s", exc)
                return

    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Read one execution with its steps and artifacts."""
        if not self.available:
            return None
        try:
            rows = self._query(
                "SELECT * FROM agentqe_executions WHERE execution_id=?",
                (execution_id,), fetch=True,
            )
        except Exception as exc:
            logger.warning("[ExecutionRepository] could not read execution: %s", exc)
            return None
        if not rows:
            return None
        record = self._hydrate(dict(rows[0]))
        record["steps"] = self.get_steps(execution_id) or record.get("steps") or []
        record["artifacts"] = self.get_artifacts(execution_id) or record.get("artifacts") or []
        return record

    def list_executions(
        self,
        execution_run_id: Optional[str] = None,
        user_id: Optional[int] = None,
        test_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        if not self.available:
            return []
        clauses: List[str] = []
        params: List[Any] = []
        if execution_run_id:
            clauses.append("execution_run_id=?")
            params.append(execution_run_id)
        if user_id is not None:
            clauses.append("user_id=?")
            params.append(user_id)
        if test_id:
            clauses.append("test_id=?")
            params.append(test_id)
        if status:
            clauses.append("status=?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.extend([int(limit), int(offset)])
        try:
            rows = self._query(
                f"SELECT * FROM agentqe_executions {where} "
                f"ORDER BY CASE rank_position WHEN NULL THEN 999999 ELSE rank_position END, id "
                f"LIMIT ? OFFSET ?",
                tuple(params), fetch=True,
            )
        except Exception as exc:
            logger.warning("[ExecutionRepository] could not list executions: %s", exc)
            return []
        return [self._hydrate(dict(r)) for r in rows or []]

    def get_steps(self, execution_id: str) -> List[Dict[str, Any]]:
        if not self.available:
            return []
        try:
            rows = self._query(
                "SELECT * FROM agentqe_execution_steps WHERE execution_id=? ORDER BY step_index",
                (execution_id,), fetch=True,
            )
        except Exception:
            return []
        steps = []
        for row in rows or []:
            data = dict(row)
            data["step"] = _load_json(data.get("step_json"), {}) or {}
            steps.append(data)
        return steps

    def get_artifacts(self, execution_id: str) -> List[Dict[str, Any]]:
        if not self.available:
            return []
        try:
            rows = self._query(
                "SELECT * FROM agentqe_execution_artifacts WHERE execution_id=? ORDER BY id",
                (execution_id,), fetch=True,
            )
        except Exception:
            return []
        artifacts = []
        for row in rows or []:
            data = dict(row)
            data["metadata"] = _load_json(data.get("metadata_json"), {}) or {}
            artifacts.append(data)
        return artifacts

    def summarise(self, execution_run_id: str) -> Dict[str, int]:
        """Dashboard counts for one execution run."""
        summary = ExecutionSummary()
        if not self.available:
            return summary.to_dict()
        try:
            rows = self._query(
                "SELECT status, COUNT(*) AS n FROM agentqe_executions "
                "WHERE execution_run_id=? GROUP BY status",
                (execution_run_id,), fetch=True,
            )
        except Exception:
            return summary.to_dict()
        for row in rows or []:
            status = row.get("status")
            count = int(row.get("n") or 0)
            summary.total += count
            if status in ("passed", "failed", "timeout", "error"):
                summary.executed += count
            if hasattr(summary, status):
                setattr(summary, status, getattr(summary, status) + count)
        return summary.to_dict()

    @staticmethod
    def _hydrate(row: Dict[str, Any]) -> Dict[str, Any]:
        for column, (key, factory) in _JSON_COLUMNS.items():
            if column in row:
                row[key] = _load_json(row[column], factory())
        return row

    # ── Whole-run persistence ──────────────────────────────────────────
    def save_run_result(
        self,
        run_result: ExecutionRunResult,
        context: Optional[Dict[str, Any]] = None,
        plans: Optional[Dict[str, ExecutionPlan]] = None,
    ) -> bool:
        """Persist an entire batch. Returns True when the run row was created."""
        ctx = dict(context or {})
        ctx.setdefault("execution_run_id", run_result.execution_run_id)
        plans = plans or {}
        run_pk = self.create_run({
            **ctx,
            "status": "completed",
            "total_tests": len(run_result.results),
            "summary": run_result.summary.to_dict(),
            "config": run_result.metadata.get("config"),
            "metadata": run_result.metadata.get("run"),
        })
        for result in run_result.results:
            try:
                self.save_execution(
                    result, run_id=run_pk, plan=plans.get(result.test_id), context=ctx
                )
            except Exception as exc:
                logger.warning("[ExecutionRepository] execution save failed: %s", exc)
        self.complete_run(run_result.execution_run_id, run_result.summary)
        run_result.persisted = run_pk is not None
        return run_result.persisted


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ["ExecutionRepository", "DB_AVAILABLE", "EXECUTION_COLUMNS"]
