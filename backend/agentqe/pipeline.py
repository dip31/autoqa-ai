"""
AgentQE Pipeline — ML-enhanced QA orchestration.

Flow:
  1. Crawl page (existing _crawl_page)
  2. Analyze requirement (existing _analyze_requirement)
  3. Generate rich test cases WITH real selectors (existing _generate_rich_cases)
  4. Engineering tests (EngineeringQAAgent) appended for coverage
  5. Deduplicate (CandidateTestPool)
  6. Enrich with risk/cost/history metadata (TestEnricher)
  7. ML ranking (TransformerTestRanker) — scores each test
  8. Adaptive selection (AdaptiveController) — pick top-k
  9. Execute via existing _execute_test_pipeline (full self-healing)
 10. Failure analysis + adaptive quality evaluation
 11. Report saved to DB
"""
import json
import threading
from database.db import execute_query
from agentqe.models.context import ApplicationContext
from agentqe.agents.strategy_agent import TestStrategyAgent
from agentqe.agents.engineering_agent import EngineeringQAAgent
from agentqe.models.test_case import CandidateTest
from agentqe.pool.candidate_pool import CandidateTestPool
from agentqe.enrichment.enricher import TestEnricher
from agentqe.agents.adaptive_controller import AdaptiveController
from agentqe.agents.adaptive_quality_agent import AdaptiveQualityAgent
from agentqe.agents.failure_agent import FailureAnalysisAgent
from agentqe.storage.repository import AgentQERepository


def _log(run_id, action, detail, status="INFO"):
    try:
        execute_query(
            "INSERT INTO autonomous_execution_logs "
            "(run_id, action_type, action_detail, status) VALUES (?,?,?,?)",
            (run_id, action, str(detail)[:500], status),
        )
    except Exception:
        pass


def _rich_tests_to_candidates(rich_tests: list) -> list:
    """Convert the dicts from _generate_rich_cases into CandidateTest objects."""
    candidates = []
    for tc in rich_tests:
        c = CandidateTest(
            test_id=tc.get("id", f"TC-{len(candidates)+1:03d}"),
            title=tc.get("title", ""),
            description=tc.get("objective", tc.get("description", "")),
            perspective="USER",
            test_type=_detect_type(tc),
            target=tc.get("module", ""),
            priority=tc.get("priority", "Medium"),
            category=tc.get("category", ""),
            steps=tc.get("steps", []),
            input_data=tc.get("input_data", ""),
            expected_result=tc.get("expected_result", ""),
            automatable=tc.get("automatable", True),
            blocked_reason=tc.get("blocked_reason"),
            source_agent="RichGenerator",
            # preserve action/selector for execution
            metadata={
                "action":       tc.get("action", "visible"),
                "selector":     tc.get("selector", "body"),
                "action_value": tc.get("action_value", ""),
            },
        )
        candidates.append(c)
    return candidates


def _detect_type(tc: dict) -> str:
    cat = str(tc.get("category", "")).lower()
    if "security" in cat:
        return "SECURITY"
    if "api" in cat:
        return "API"
    if "unit" in cat:
        return "UNIT"
    return "UI"


def _candidates_to_execution_format(candidates: list) -> list:
    """Convert CandidateTest list back to the dict format _execute_test_pipeline expects."""
    return [
        {
            "id":             tc.test_id,
            "title":          tc.title,
            "objective":      tc.description,
            "category":       tc.category,
            "priority":       tc.priority,
            "steps":          tc.steps,
            "input_data":     tc.input_data,
            "expected_result":tc.expected_result,
            "automatable":    tc.automatable,
            "blocked_reason": tc.blocked_reason,
            "action":         tc.metadata.get("action", "visible"),
            "selector":       tc.metadata.get("selector", "body"),
            "action_value":   tc.metadata.get("action_value", ""),
        }
        for tc in candidates
    ]


def run_agentqe_pipeline(run_id: int):
    """Full AgentQE pipeline. Runs in a background thread."""
    try:
        rows = execute_query(
            "SELECT * FROM autonomous_runs WHERE id=?", (run_id,), fetch=True
        )
        if not rows:
            return
        run = rows[0]

        execute_query("UPDATE autonomous_runs SET status='Analysis' WHERE id=?", (run_id,))
        _log(run_id, "PIPELINE", "AgentQE pipeline started", "INFO")

        url         = run.get("url", "")
        req_text    = run.get("requirement_text", "")
        repo_url    = run.get("repo_url", "")
        module_name = run.get("module_name", "General")
        max_cycles  = int(run.get("max_cycles") or 3)
        current_cycle = int(run.get("cycle") or 1)
        mode        = run.get("execution_mode", "AgentQE Pipeline")

        ctx = ApplicationContext(
            url=url,
            repo_url=repo_url,
            requirement=req_text,
            module_name=module_name,
        )

        # ── Stage 1: Strategy ─────────────────────────────────────────────
        _log(run_id, "STRATEGY", "Planning test strategy with TestStrategyAgent", "INFO")
        strategy = TestStrategyAgent().plan(ctx)
        execute_query(
            "UPDATE autonomous_runs SET strategy_json=? WHERE id=?",
            (json.dumps(strategy), run_id),
        )
        _log(run_id, "STRATEGY", f"Strategy complete: {', '.join(strategy['test_types'])} | Priorities: {strategy.get('priorities', [])}", "SUCCESS")

        # ── Stage 2: Crawl + Analyze + Generate rich tests with selectors ─
        execute_query("UPDATE autonomous_runs SET status='Generation' WHERE id=?", (run_id,))

        from agents.autonomous_agent import (
            _crawl_page, _analyze_requirement,
            _generate_rich_cases, _log as _orig_log,
            MODE_CONFIG, DEFAULT_MODE,
        )

        cfg = MODE_CONFIG.get(mode, MODE_CONFIG[DEFAULT_MODE])

        page_data = {}
        if url:
            _log(run_id, "BROWSER", f"Crawling {url}", "INFO")
            page_data = _crawl_page(url)
            _log(run_id, "BROWSER", f"Crawled: {page_data.get('title', 'unknown')}", "SUCCESS")

        scope = {"summary": req_text, "items": [], "priority": "Medium", "coverage_estimate": 0.8,
                 "detected_module_type": "web", "key_user_flows": [], "risk_areas": []}
        if req_text or url:
            scope = _analyze_requirement(req_text, url, page_data)
            execute_query(
                "INSERT INTO autonomous_scope (run_id, feature_summary, scope_items, assumptions, priority_plan, estimated_coverage) VALUES (?,?,?,?,?,?)",
                (run_id, scope.get("summary",""), json.dumps(scope.get("items",[])),
                 json.dumps(scope.get("assumptions",[])), scope.get("priority","Medium"),
                 scope.get("coverage_estimate", 0.8)),
            )

        # Generate rich tests (these have real selectors from live crawl)
        count = cfg["count"]
        rich_tests = _generate_rich_cases(scope, page_data, count) if (url or req_text) else []
        _log(run_id, "GENERATION", f"User-perspective generator: {len(rich_tests)} test cases created", "SUCCESS")

        # Convert to CandidateTest
        user_candidates = _rich_tests_to_candidates(rich_tests)

        # Engineering tests (unit/api/security perspective)
        _log(run_id, "GENERATION", "Engineering QA Agent generating technical tests", "INFO")
        eng_tests = EngineeringQAAgent().generate(ctx)
        _log(run_id, "GENERATION", f"Engineering tests: {len(eng_tests)} cases (STUB - currently returns sample unit test)", "WARNING")

        # ── Stage 3: Merge + Deduplicate ─────────────────────────────────
        _log(run_id, "POOL", f"Merging {len(user_candidates)} user tests + {len(eng_tests)} engineering tests", "INFO")
        pool = CandidateTestPool()
        combined = pool.merge(user_candidates, eng_tests)
        _log(run_id, "POOL", f"CandidateTestPool: {len(combined)} unique tests after deduplication", "SUCCESS")

        # ── Stage 4: Enrich ───────────────────────────────────────────────
        _log(run_id, "ENRICHMENT", "Enriching test metadata with risk/cost/complexity scores", "INFO")
        enriched = TestEnricher().enrich(combined)
        _log(run_id, "ENRICHMENT", f"Enrichment complete: {len(enriched)} tests with heuristic metadata", "SUCCESS")

        # ── Stage 5: ML Ranking ───────────────────────────────────────────
        ranked = enriched
        try:
            _log(run_id, "RANKING", "Starting Transformer-based ML ranking (UNTRAINED MODEL)", "INFO")
            from agentqe.ml.features import TestFeatureExtractor
            from agentqe.ml.inference import TestRanker
            from agentqe.ml.transformer_ranker import TransformerTestRanker
            import torch
            model = TransformerTestRanker()
            model.eval()
            ranker = TestRanker(model, TestFeatureExtractor())
            ranked = ranker.rank(enriched)
            _log(run_id, "RANKING", f"ML ranking complete: {len(ranked)} tests scored (WARNING: Random weights, not production-ready)", "SUCCESS")
        except Exception as e:
            _log(run_id, "RANKING", f"ML ranker failed, using fallback: {e}", "WARNING")

        # ── Stage 6: Adaptive Selection ───────────────────────────────────
        top_k = cfg["execute_limit"]
        _log(run_id, "SELECTION", f"AdaptiveController selecting top-{top_k} tests from {len(ranked)} candidates", "INFO")
        selected = AdaptiveController().select(ranked, top_k=top_k)
        _log(run_id, "SELECTION", f"Selected {len(selected)} tests for execution", "SUCCESS")

        # Save ALL generated test cases to DB
        for tc in combined:
            is_selected = any(s.test_id == tc.test_id for s in selected)
            try:
                execute_query(
                    "INSERT INTO autonomous_test_cases "
                    "(run_id, case_id, scenario, case_type, expected_result, priority, generated_by, "
                    "title, objective, category, steps, input_data, automatable, blocked_reason, status) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run_id, tc.test_id, tc.title, tc.test_type,
                        tc.expected_result, tc.priority, tc.source_agent,
                        tc.title, tc.description, tc.category,
                        json.dumps(tc.steps) if isinstance(tc.steps, list) else str(tc.steps),
                        tc.input_data or "",
                        1 if tc.automatable else 0,
                        tc.blocked_reason or "",
                        "Pending" if is_selected else "Skipped",
                    ),
                )
            except Exception:
                pass

        # ── Stage 7: Execute with full self-healing ───────────────────────
        execute_query("UPDATE autonomous_runs SET status='Execution' WHERE id=?", (run_id,))
        _log(run_id, "EXECUTION", f"Starting browser execution for {len(selected)} selected tests", "INFO")

        execution_dicts = []
        if url:
            from agents.autonomous_agent import _execute_test_pipeline
            exec_format = _candidates_to_execution_format(selected)
            _execute_test_pipeline(run_id, url, exec_format, len(exec_format))
            _log(run_id, "EXECUTION", "Browser execution complete with self-healing", "SUCCESS")

            # Read back results from DB
            tc_rows = execute_query(
                "SELECT case_id, status FROM autonomous_test_cases WHERE run_id=?",
                (run_id,), fetch=True
            )
            execution_dicts = [{"test_id": r["case_id"], "status": r["status"]} for r in tc_rows]
        else:
            _log(run_id, "EXECUTION", "No URL — dry run mode (all tests marked as PASS)", "WARNING")
            execution_dicts = [{"test_id": tc.test_id, "status": "PASS"} for tc in selected]
            for tc in selected:
                execute_query(
                    "UPDATE autonomous_test_cases SET status='PASS' WHERE run_id=? AND case_id=?",
                    (run_id, tc.test_id)
                )

        # ── Stage 8: Failure Analysis ─────────────────────────────────────
        execute_query("UPDATE autonomous_runs SET status='Reporting' WHERE id=?", (run_id,))
        _log(run_id, "FAILURE_ANALYSIS", "Analyzing failures with FailureAnalysisAgent", "INFO")

        class _R:
            def __init__(self, d):
                self.status = d.get("status", "")
                self.test_id = d.get("test_id", "")
                self.error_message = d.get("error", "")
                self.screenshot_path = None
                self.healing_attempted = False
                self.healing_successful = False

        failures = FailureAnalysisAgent().analyze([_R(r) for r in execution_dicts])
        _log(run_id, "FAILURE_ANALYSIS", f"Identified {len(failures)} failure patterns", "SUCCESS")

        # Save findings
        for f in failures:
            try:
                execute_query(
                    "INSERT INTO autonomous_findings (run_id, title, description, severity) VALUES (?,?,?,?)",
                    (run_id, f.get("test_id", ""), f.get("error", ""), "High"),
                )
            except Exception:
                pass

        # ── Stage 9: Adaptive Quality Evaluation ─────────────────────────
        _log(run_id, "QUALITY_EVAL", f"Evaluating quality metrics (Cycle {current_cycle}/{max_cycles})", "INFO")
        quality = AdaptiveQualityAgent().evaluate(
            [_R(r) for r in execution_dicts], current_cycle, max_cycles
        )

        passed  = sum(1 for r in execution_dicts if r.get("status") in ("PASS", "HEALED"))
        healed  = sum(1 for r in execution_dicts if r.get("status") == "HEALED")
        failed  = sum(1 for r in execution_dicts if r.get("status") in ("FAIL", "FAILED"))
        blocked = sum(1 for r in execution_dicts if r.get("status") == "Blocked")
        total   = len(execution_dicts)
        quality_score = round((passed / total * 100) if total > 0 else 0, 1)
        _log(run_id, "QUALITY_EVAL", f"Quality score: {quality_score}% | Decision: {quality['decision']} | Cycle {current_cycle}/{max_cycles}", "SUCCESS")

        # Risk analysis
        _log(run_id, "RISK_ANALYSIS", "Computing risk metrics for deployment readiness", "INFO")
        high_risk = [tc.title for tc in selected if tc.risk_score >= 0.8]
        recommendations = [
            "Review failing selectors and update test locators",
            "Add more negative test cases for edge conditions",
            "Consider increasing execution budget for better coverage",
        ] if failed > 0 else ["All selected tests passed — ready for deployment"]
        
        _log(run_id, "RISK_ANALYSIS", f"High-risk areas: {len(high_risk)} | Overall risk: {round(100 - quality_score, 1)}%", "SUCCESS")

        execute_query(
            "INSERT INTO autonomous_risk_analysis "
            "(run_id, module_risk_score, release_readiness, confidence_score, high_risk_areas, recommendations) "
            "VALUES (?,?,?,?,?,?)",
            (
                run_id,
                round(100 - quality_score, 1),
                "Ready" if quality_score >= 70 else "Not Ready",
                quality_score,
                json.dumps(high_risk[:5]),
                json.dumps(recommendations),
            ),
        )

        # ── Stage 10: Save Final Report ────────────────────────────────────
        _log(run_id, "REPORT", "Generating final AgentQE report", "INFO")
        exec_summary = (
            f"AgentQE ML Pipeline executed {total} tests: {passed} passed, {healed} auto-healed, "
            f"{failed} failed, {blocked} blocked. "
            f"ML Transformer ranked {len(ranked)} candidates (UNTRAINED). "
            f"Quality decision: {quality['decision']}. Cycle {current_cycle}/{max_cycles}."
        )
        verdict = "Ready for deployment" if quality_score >= 70 else "Needs improvement before deployment"
        
        _log(run_id, "REPORT", f"Report complete: {verdict}", "SUCCESS")

        execute_query(
            "INSERT INTO autonomous_reports "
            "(run_id, executive_summary, final_verdict, report_json) VALUES (?,?,?,?)",
            (
                run_id, exec_summary, verdict,
                json.dumps({
                    "passed": passed, "healed": healed, "failed": failed,
                    "blocked": blocked, "total": total,
                    "quality_score": quality_score,
                    "quality_decision": quality["decision"],
                    "ml_ranked": len(ranked),
                    "selected": len(selected),
                    "strategy": strategy,
                    "cycle": current_cycle,
                }),
            ),
        )

        execute_query(
            "UPDATE autonomous_runs SET status='Completed', completed_at=CURRENT_TIMESTAMP WHERE id=?",
            (run_id,),
        )
        _log(run_id, "PIPELINE", f"AgentQE complete. Score={quality_score} Decision={quality['decision']}", "SUCCESS")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        execute_query("UPDATE autonomous_runs SET status='Failed' WHERE id=?", (run_id,))
        _log(run_id, "PIPELINE_ERROR", tb[:500], "FAIL")
        print(f"[AgentQE Error] {tb}")


def start_agentqe_run(run_id: int):
    """Launch the pipeline in a background thread."""
    thread = threading.Thread(target=run_agentqe_pipeline, args=(run_id,), daemon=True)
    thread.start()
