# AgentQE Audit Report
**Date:** September 24, 2026  
**Auditor:** Kiro AI  
**Policy:** READ-ONLY - no code was modified.

---

## EXECUTIVE SUMMARY
The codebase is a functional QA assistance platform (AutoQA AI / Flask + React) with LLM-powered tools. It does NOT implement the AgentQE dual-perspective agentic architecture.

**Most critical gaps:**
- No Transformer-based test prioritization. Zero DL code. requirements.txt has no torch, tensorflow, or transformers.
- No Candidate Test Pool with dual-perspective merging.
- No LangGraph or graph-based agent orchestration.
- No Engineering QA Agent (Pytest/HTTPX/Semgrep/ZAP/k6).
- No Adaptive Controller.
- No Docker sandbox. Playwright runs inside the Flask process thread.
- No training pipeline or DL model of any kind.

---

## COMPONENT AUDIT TABLE

| Component | Status | Evidence | Working? | Integrated? | Remaining Work |
|-----------|--------|----------|----------|-------------|----------------|
| A. Application Input | [PARTIAL] | autonomous_agent.py, repo_intelligence_agent.py | YES | YES | Missing: OpenAPI spec, existing tests, bug history |
| B. Application Analyzer Agent | [PARTIAL] | repo_intelligence_agent.py | YES | PARTIAL | No AST/Tree-sitter. Pure LLM. Not wired to Test Strategy Agent |
| C. Test Strategy Agent | [MISSING] | -- | NO | NO | Hard-coded _category_distribution() arithmetic only |
| D. User Agent | [PARTIAL] | autonomous_agent.py _generate_rich_cases() | YES | PARTIAL | Not separate agent class. No accessibility. No LangGraph node |
| E. Engineering QA Agent | [MISSING] | -- | NO | NO | No unit/API/security/perf tests. No Pytest/HTTPX/ZAP/k6/Semgrep |
| F. Candidate Test Pool | [MISSING] | -- | NO | NO | No dual-perspective pool. Tests go directly to autonomous_test_cases |
| G. Test Enrichment | [STUB] | autonomous_agent.py | PARTIAL | NO | Metadata only. No coverage/history/change/cost. Not fed to prioritizer |
| H. Transformer / Test Prioritizer | [MISSING] | -- | NO | NO | Zero DL code. No PyTorch. LLM calls are NOT a Transformer |
| I. Adaptive Controller | [MISSING] | -- | NO | NO | Hard-coded execute_limit. No risk/coverage/history Top-K selection |
| J. Test Execution | [PARTIAL] | autonomous_agent.py _execute_test_pipeline() | YES | PARTIAL | No Docker sandbox. Runs in Flask thread. No screenshots |
| K. Observation Collector | [PARTIAL] | autonomous_execution_logs table | YES | YES | No screenshots, network traces, or coverage metrics |
| L. Failure & Risk Analyzer | [PARTIAL] | autonomous_agent.py _analyze_risks() | YES | YES | Rule+LLM hybrid. No ML. No code correlation |
| M. Adaptive Quality Agent | [STUB] | _build_report() | NO | NO | Report generated. No feedback loop or re-planning |
| N. Data & Knowledge Layer | [PARTIAL] | database/db.py, autoqa.db | YES | YES | No vector DB, Redis, embeddings, or training pipeline |
| O. Human Governance | [MISSING] | AutonomousQA.jsx (Send to Dev) | PARTIAL | NO | Message is informational. No APPROVE/RE-PLAN workflow |
| P. Final Quality Report | [PARTIAL] | autonomous_agent.py _build_report() | YES | YES | Missing: coverage, security, Transformer fields, human decision |
| Q. n8n | [MISSING] | -- | NO | NO | Not present anywhere in the repository |
| R. LangGraph / Orchestration | [MISSING] | -- | NO | NO | Sequential function calls. No graph, state, routing, or RE-PLAN |
| S. Security Validation | [MISSING] | -- | NO | NO | No ZAP, Semgrep, or security test generation |

---

## DEEP LEARNING IMPLEMENTATION STATUS

**Transformer-based test prioritization is NOT implemented.**

The repository contains zero deep learning code.
requirements.txt has NO ML libraries: no torch, tensorflow, transformers, or scikit-learn.

| Question | Answer |
|---------|--------|
| 1. DL model exists? | NONE. Zero DL code in the entire repository. |
| 2. Transformer implemented? | NO. Explicitly not implemented. |
| 3. Training pipeline? | NO. No training loop, optimizer, or loss function. |
| 4. Dataset? | NONE. |
| 5. Input features? | N/A |
| 6. Target label? | N/A |
| 7. Test representation? | JSON dicts / SQLite rows. No vector/embedding representation. |
| 8. Loss function? | NONE defined. |
| 9. Metrics? | Pass/fail/healed counts only. No ML metrics. |
| 10. Train/val/test split? | NO. |
| 11. Model evaluation? | NO. |
| 12. Model used in app? | NO model exists. |

**Minimum additions for a meaningful DL project:**
1. Labeled dataset from execution history (test_features, failure_probability)
2. Feature extraction: test type, priority, historical pass rate, code change impact, execution cost
3. Transformer encoder (minimum 2-layer, 4-head, d_model=64)
4. Regression/ranking head producing a priority score
5. Training loop with BCELoss or LambdaRank
6. Evaluation: NDCG@K, Precision@K, or APFD
7. Inference integrated into _execute_test_pipeline() for actual test ordering

---

## AGENTIC AI STATUS

**Agentic AI Maturity: LOW**

run_autonomous_qa() is a fixed 6-step linear function. No graph, no state machine, no conditional branching based on intermediate results.
The SelfHealingEngine is the most agentic component (4-stage retry with DOM scoring) but operates only at selector-recovery level.
LangGraph, LangChain, AutoGen, CrewAI — entirely absent from requirements.txt and the codebase.

| Agentic Behavior | Present? | Evidence |
|---------|---------|----------|
| Autonomous decision making | PARTIAL | LLM decides test content; execution order is fixed |
| Tool usage | YES | Playwright, GitHub API, Gemini, Groq |
| State | PARTIAL | SQLite holds state; no in-memory agent state object |
| Planning | STUB | _analyze_requirement() produces scope; no dynamic plan |
| Conditional routing | NO | Linear function calls only |
| Feedback | NO | Results not re-fed into planning |
| Iteration / loops | NO | Single pass; no cycles |
| Re-planning | NO | Not implemented |
| Memory / history | PARTIAL | DB stores history; agents never query it for decisions |
| Human-in-the-loop | NO | Send to Dev is informational only |

---

## WHAT IS WORKING
- User auth (JWT + bcrypt)
- Test case review via Groq (testcase_agent.py)
- Code review via Groq (code_agent.py)
- Website scrape + test generation via Playwright + Groq (website_agent.py)
- Test case generation from requirements (generator_agent.py)
- Risk prediction (risk_agent.py)
- Smart report (report_agent.py)
- Autonomous QA pipeline: crawl > analyze > generate > execute > risk > report
- 4-stage self-healing engine (SelfHealingEngine)
- GitHub repo intelligence scanner (repo_intelligence_agent.py)
- Developer portal: diagram generation, code generation, code review
- QA-to-Dev messaging
- SQLite / MySQL database layer
- React frontend with all pages

---

## WHAT IS MISSING
1. Test Strategy Agent
2. Engineering QA Agent (unit/API/security/perf)
3. Candidate Test Pool (dual-perspective schema)
4. Test Enrichment pipeline
5. Transformer model (architecture, training, inference)
6. Adaptive Controller (Top-K selection)
7. Docker sandbox for test isolation
8. Screenshot / network observation capture
9. LangGraph orchestration (graph, state, conditional routing)
10. RE-PLAN path from human review back to Test Strategy Agent
11. Semgrep / OWASP ZAP security integration
12. Historical data re-use for enrichment and model training
13. Adaptive Quality Agent (genuine feedback-driven re-planning)
14. n8n

---

## WHAT IS INCORRECT OR MISALIGNED

| Issue | Description |
|-------|-------------|
| Duplicate Flask app | app = Flask(__name__) declared twice in app.py. Bottom instance wiped all routes. Fixed during session. |
| Model name missing prefix | gpt-oss-120b used without openai/ prefix causing 404. Fixed during session. |
| Playwright in threading.Thread | Causes asyncio/watchdog interference with Flask debug reloader. Mitigated with stat reloader. |
| Dashboard hardcodes Groq LLaMA 3.3 | Tech stack display outdated after model change to openai/gpt-oss-120b. |
| autonomous_repo_intelligence table | Referenced in autonomous_agent.py but missing from init_db.py initial schema. Migration-only. |
| docker-compose.yml broken | References ../docker/backend/Dockerfile paths that do not exist in the repository. |

---

## END-TO-END FLOW STATUS

**Current actual flow:**
  > User submits URL + requirement + optional repo URL
  > [Optional] GitHub repo scan (LLM only)
  > Playwright page crawl
  > Gemini: requirement analysis > scope JSON
  > Gemini: generate N test cases (UI/UX perspective only)
  > Playwright: execute tests sequentially (no sandbox)
  > 4-stage self-healing on selector failures
  > Gemini: risk narrative
  > Gemini: final report JSON
  > Frontend displays results

**Missing vs. target:**
  [x] Application Analyzer > Test Strategy Agent routing
  [x] Dual perspective (User Agent + Engineering QA Agent running in parallel)
  [x] Candidate Test Pool merge from both perspectives
  [x] Test enrichment (coverage, history, change impact, cost)
  [x] Transformer prioritization
  [x] Adaptive Controller Top-K selection
  [x] Docker sandbox for isolated execution
  [x] Observation collector (screenshots, network, coverage)
  [x] Failure/Risk Analyzer > Evidence/History update
  [x] Adaptive Quality Agent feedback loop
  [x] Human review > RE-PLAN / PROCEED branch
  [x] LangGraph state machine

---

## RECOMMENDED NEXT 10 DEVELOPMENT TASKS

### TASK 1: Add LangGraph and Define Agent Graph Structure
- **Why it is needed:** Foundation for all conditional routing, RE-PLAN, and human-in-the-loop.
- **Files / modules affected:** requirements.txt (+langgraph), backend/agents/agent_graph.py (NEW), autonomous_agent.py (refactor)
- **Dependency:** None — this is the foundation task.
- **Expected output:** StateGraph with nodes and at least one conditional edge exercised.
- **Definition of Done:** run_autonomous_qa() delegates to graph; conditional edge from human_review to plan_strategy works.

### TASK 2: Define Candidate Test Pool Schema and API
- **Why it is needed:** Transformer requires unified dual-perspective input.
- **Files / modules affected:** database/init_db.py (add table), backend/agents/test_pool.py (NEW)
- **Dependency:** Task 1
- **Expected output:** Table: id, run_id, test_id, perspective (USER/ENGINEERING), features_json, transformer_score, selected.
- **Definition of Done:** Both agents write to this table with perspective field populated.

### TASK 3: Implement Engineering QA Agent (Minimum Viable)
- **Why it is needed:** Dual-perspective is the core requirement and is completely absent.
- **Files / modules affected:** backend/agents/engineering_agent.py (NEW), agent_graph.py (wire as node)
- **Dependency:** Tasks 1, 2
- **Expected output:** Generates Pytest unit stubs + HTTPX API tests; stores in pool with perspective=ENGINEERING.
- **Definition of Done:** 10+ engineering tests appear in candidate_test_pool per run with a repo URL.

### TASK 4: Extract Feature Vectors from Candidate Tests
- **Why it is needed:** Transformer needs numerical input, not raw JSON.
- **Files / modules affected:** backend/agents/feature_extractor.py (NEW), test_pool.py (call extractor)
- **Dependency:** Tasks 2, 3
- **Expected output:** extract_features() returns fixed-length np.ndarray (32 dims): category/priority one-hot, historical pass rate, exec time, module index, perspective.
- **Definition of Done:** Every test in candidate_test_pool has populated features_json deserializable to float array.

### TASK 5: Implement Transformer Encoder + Ranking Head (PyTorch)
- **Why it is needed:** Core DL requirement for the course project and AgentQE architecture.
- **Files / modules affected:** requirements.txt (+torch>=2.0.0), backend/ml/transformer_ranker.py (NEW), backend/ml/train.py (NEW), backend/ml/evaluate.py (NEW)
- **Dependency:** Task 4
- **Expected output:** nn.TransformerEncoder (2 layers, 4 heads, d_model=64) + linear head -> scalar score. Checkpoint at backend/ml/checkpoints/ranker.pt.
- **Definition of Done:** Model trains without error; NDCG@5 > random baseline.

### TASK 6: Implement Adaptive Controller (Top-K Selection)
- **Why it is needed:** Replaces hard-coded execute_limit with intelligent risk/coverage/Transformer-weighted selection.
- **Files / modules affected:** backend/agents/adaptive_controller.py (NEW), agent_graph.py (wire between pool and execution)
- **Dependency:** Task 5
- **Expected output:** select_top_k(pool, k, budget_seconds) returns ordered top-k test IDs by Transformer score x risk x coverage.
- **Definition of Done:** Execution order changes between runs with different risk profiles; selected=1 set in pool.

### TASK 7: Docker Sandbox for Test Execution
- **Why it is needed:** Playwright in threading.Thread causes watchdog interference and zero test isolation.
- **Files / modules affected:** docker/playwright/Dockerfile (NEW), backend/agents/execution_sandbox.py (NEW), autonomous_agent.py (replace _execute_test_pipeline)
- **Dependency:** Task 1
- **Expected output:** Each run spawns isolated Docker container; results returned via stdout JSON; container removed after run.
- **Definition of Done:** Two concurrent runs use separate containers; Flask unaffected by Playwright events.

### TASK 8: Screenshot Capture on Test Failure
- **Why it is needed:** Evidence collection is specified; currently failures produce text strings only.
- **Files / modules affected:** autonomous_agent.py SelfHealingEngine._try() (add page.screenshot()), init_db.py (screenshot_path already in schema but unpopulated)
- **Dependency:** Task 7
- **Expected output:** page.screenshot() called on FAIL; path stored in autonomous_findings.screenshot_path; frontend renders it.
- **Definition of Done:** At least one screenshot saved per failed test; frontend can display it.

### TASK 9: Human Governance - APPROVE / RE-PLAN Workflow
- **Why it is needed:** Human oversight is a core AgentQE requirement. Current Send to Dev is informational only.
- **Files / modules affected:** app.py (add POST /api/autonomous-qa/run/<id>/review), agent_graph.py (human_review interrupt), AutonomousQA.jsx (APPROVE/RE-PLAN buttons)
- **Dependency:** Task 1
- **Expected output:** After report, run status = Awaiting Review. Human calls /review with decision=approve or decision=replan+feedback. RE-PLAN resumes graph from plan_strategy.
- **Definition of Done:** RE-PLAN causes second pass with modified strategy; run shows two generations of test cases.

### TASK 10: Training Data Pipeline - Collect and Label from DB
- **Why it is needed:** Transformer cannot be trained without labeled data; DB already accumulates execution results.
- **Files / modules affected:** backend/ml/data_pipeline.py (NEW), backend/ml/train.py (calls pipeline)
- **Dependency:** Tasks 2, 5
- **Expected output:** build_dataset(min_runs=5) returns (X_train, y_train, X_val, y_val) with status=FAIL as positive label. 80/20 split. Minimum 50 examples.
- **Definition of Done:** train.py --from-db runs without error; training loss decreases over 5 epochs; dataset size logged.

---

## CRITICAL PATH

**PHASE 1 - MUST HAVE (demo-ready prototype):**
- Task 1: LangGraph graph structure
- Task 2: Candidate Test Pool schema
- Task 3: Engineering QA Agent (minimum viable)
- Task 4: Feature extraction
- Task 5: Transformer encoder + ranking head (PyTorch)
- Task 6: Adaptive Controller

**PHASE 2 - IMPORTANT:**
- Task 7: Docker sandbox
- Task 8: Screenshot capture
- Task 9: Human governance / RE-PLAN
- Task 10: Training data pipeline

**PHASE 3 - FUTURE / OPTIONAL:**
- Semgrep / OWASP ZAP integration
- k6 / Locust performance testing
- n8n external notifications
- Continuous learning loop
- Vector DB for embedding-based test deduplication
- Coverage instrumentation (Istanbul / Coverage.py)

---

*End of Audit Report - September 24, 2026*
