# AgentQE ONE-CLICK WORKFLOW DIAGRAM

## Complete End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      USER INTERACTION                            │
│  Frontend: AutonomousQA.jsx                                      │
│  - Toggle to "AgentQE ML" mode                                   │
│  - Fill form (title, requirement, URL, repo, module)             │
│  - Click "Run AgentQE Pipeline" button                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API CALL                                      │
│  POST /api/agentqe/run                                          │
│  - Creates run record in DB                                      │
│  - Returns run_id                                                │
│  - Spawns background thread                                      │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│              AGENTQE PIPELINE ORCHESTRATION                      │
│  File: backend/agentqe/pipeline.py                              │
│  Function: run_agentqe_pipeline(run_id)                         │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 1: TEST STRATEGY                                │
    │  Agent: TestStrategyAgent                              │
    │  - Plan test types (UI, UNIT, API, SECURITY)           │
    │  - Set priorities (HIGH_RISK, CHANGED_CODE, etc.)      │
    │  - Define execution budget                             │
    │  Log: STRATEGY                                         │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 2: APPLICATION UNDERSTANDING                    │
    │  Functions: _crawl_page, _analyze_requirement          │
    │  - Crawl URL with Playwright                           │
    │  - Extract DOM structure and selectors                 │
    │  - Analyze requirement text                            │
    │  - Identify user flows and risk areas                  │
    │  Logs: BROWSER, ANALYSIS                               │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 3: USER-PERSPECTIVE GENERATION                  │
    │  Agent: UserAgent + _generate_rich_cases               │
    │  - Generate positive tests                             │
    │  - Generate negative tests                             │
    │  - Generate boundary tests                             │
    │  - Generate UI flow tests                              │
    │  - WITH REAL SELECTORS from crawl                      │
    │  Log: GENERATION (User)                                │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 4: ENGINEERING TEST GENERATION                  │
    │  Agent: EngineeringQAAgent                             │
    │  - Generate UNIT tests (STUB - 1 sample test)          │
    │  - Generate API tests (EMPTY)                          │
    │  - Generate Security tests (EMPTY)                     │
    │  Log: GENERATION (Engineering)                         │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 5: CANDIDATE POOL                               │
    │  Component: CandidateTestPool                          │
    │  - Merge user tests + engineering tests                │
    │  - Deduplicate by similarity                           │
    │  - Return unique candidates                            │
    │  Log: POOL                                             │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 6: TEST ENRICHMENT                              │
    │  Component: TestEnricher                               │
    │  - Add risk_score (heuristic)                          │
    │  - Add cost_estimate                                   │
    │  - Add complexity score                                │
    │  - Add historical_data placeholder                     │
    │  Log: ENRICHMENT                                       │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 7: ML RANKING (EXPERIMENTAL)                    │
    │  Component: TransformerTestRanker                      │
    │  - Extract features from tests                         │
    │  - Run through Transformer (UNTRAINED)                 │
    │  - Assign ML scores                                    │
    │  - Fallback to rule-based on failure                   │
    │  Log: RANKING                                          │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 8: ADAPTIVE SELECTION                           │
    │  Component: AdaptiveController                         │
    │  - Sort tests by ML score (or priority)                │
    │  - Select top-K tests (default: 20)                    │
    │  - Balance coverage vs budget                          │
    │  - Save ALL tests to DB                                │
    │  - Mark selected tests as "Pending"                    │
    │  Log: SELECTION                                        │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 9: TEST EXECUTION                               │
    │  Component: PlaywrightAdapter + _execute_test_pipeline │
    │  - Launch browser (Playwright)                         │
    │  - Execute each selected test                          │
    │  - Capture screenshots on failure                      │
    │  - Attempt self-healing on selector failures           │
    │  - Update test status (PASS/FAIL/HEALED/BLOCKED)       │
    │  - Save healing logs                                   │
    │  Log: EXECUTION                                        │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 10: FAILURE ANALYSIS                            │
    │  Agent: FailureAnalysisAgent                           │
    │  - Identify failed tests                               │
    │  - Extract error messages                              │
    │  - Check healing attempts                              │
    │  - Save findings to DB                                 │
    │  Log: FAILURE_ANALYSIS                                 │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 11: RISK ANALYSIS                               │
    │  Logic: Built-in risk computation                      │
    │  - Calculate module risk score                         │
    │  - Determine release readiness                         │
    │  - Identify high-risk areas                            │
    │  - Generate recommendations                            │
    │  - Save to autonomous_risk_analysis table              │
    │  Log: RISK_ANALYSIS                                    │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 12: QUALITY EVALUATION                          │
    │  Agent: AdaptiveQualityAgent                           │
    │  - Count failures                                      │
    │  - Check current_cycle vs max_cycles                   │
    │  - Decision: REPLAN (if failures + cycles remain)      │
    │  - Decision: PROCEED (if no failures or max reached)   │
    │  - Log decision (NOT automatically triggered)          │
    │  Log: QUALITY_EVAL                                     │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
    ┌────────────────────────────────────────────────────────┐
    │  STAGE 13: FINAL REPORT                                │
    │  Logic: Report generation                              │
    │  - Create executive summary                            │
    │  - Compute quality score                               │
    │  - Determine final verdict                             │
    │  - Save to autonomous_reports table                    │
    │  - Update run status to "Completed"                    │
    │  Log: REPORT, PIPELINE                                 │
    └───────────────────────┬────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FRONTEND POLLING                              │
│  - UI polls GET /api/autonomous-qa/run/<id> every 2.5s          │
│  - Updates status, logs, test cases, findings, report           │
│  - Stops polling when status = Completed/Failed                 │
│  - Displays real-time progress in stepper                       │
│  - Shows stage-by-stage logs                                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│               STAGE 14: HUMAN REVIEW (OPTIONAL)                  │
│  API: POST /api/agentqe/review/<run_id>                        │
│  - User can submit APPROVE/REPLAN decision                      │
│  - Feedback text is saved                                       │
│  - Review is persisted (NOT blocking)                           │
│  - Does NOT automatically trigger replan                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Diagram

```
                    ┌─────────────┐
                    │    User     │
                    └──────┬──────┘
                           │
                           ▼
                ┌──────────────────┐
                │  React Frontend  │
                │  (AutonomousQA)  │
                └──────┬───────────┘
                       │
                       │ POST /api/agentqe/run
                       │
                       ▼
        ┌──────────────────────────────┐
        │      Flask Backend           │
        │  /api/agentqe/run endpoint   │
        └──────┬───────────────────────┘
               │
               │ Creates run_id
               │ Spawns thread
               │
               ▼
        ┌──────────────────────┐
        │  Background Thread   │
        │  run_agentqe_pipeline│
        └──────┬───────────────┘
               │
               │ Executes 14 stages
               │ Logs to DB
               │
               ▼
        ┌──────────────────────┐
        │   SQLite Database    │
        │  - autonomous_runs   │
        │  - test_cases        │
        │  - execution_logs    │
        │  - findings          │
        │  - risk_analysis     │
        │  - reports           │
        │  - healing_logs      │
        └──────┬───────────────┘
               │
               │ GET /api/autonomous-qa/run/<id>
               │ (polled every 2.5s)
               │
               ▼
        ┌──────────────────────┐
        │  React Frontend      │
        │  Real-time Updates   │
        │  - Status stepper    │
        │  - Live logs         │
        │  - Test results      │
        │  - Final report      │
        └──────────────────────┘
```

---

## Component Architecture

```
Frontend (React)
├── pages/
│   └── AutonomousQA.jsx ────────────┐
├── api/                             │
│   └── client.js                    │
│       ├── runAgentQE()             │
│       ├── getAutonomousRunDetails()│
│       └── submitAgentQEReview()    │
└── components/                      │
    ├── Loader.jsx                   │
    └── ScoreBadge.jsx               │
                                     │
                                     ▼
Backend (Flask + Python)             │
├── app.py                           │
│   ├── /api/agentqe/run ◄───────────┘
│   ├── /api/autonomous-qa/run/<id>
│   └── /api/agentqe/review/<id>
│
├── agentqe/
│   ├── pipeline.py ◄─────────── Core orchestrator
│   │   ├── run_agentqe_pipeline()
│   │   └── start_agentqe_run()
│   │
│   ├── agents/
│   │   ├── strategy_agent.py
│   │   ├── user_agents.py
│   │   ├── engineering_agent.py
│   │   ├── adaptive_controller.py
│   │   ├── adaptive_quality_agent.py
│   │   └── failure_agent.py
│   │
│   ├── enrichment/
│   │   └── enricher.py
│   │
│   ├── execution/
│   │   ├── playwright_adapter.py
│   │   ├── pytest_runner.py (unused)
│   │   ├── api_runner.py (unused)
│   │   └── security_runner.py (empty)
│   │
│   ├── ml/
│   │   ├── transformer_ranker.py
│   │   ├── features.py
│   │   └── inference.py
│   │
│   ├── models/
│   │   ├── context.py
│   │   ├── test_case.py
│   │   └── execution.py
│   │
│   ├── pool/
│   │   └── candidate_pool.py
│   │
│   ├── human/
│   │   ├── review.py
│   │   └── review_service.py
│   │
│   └── storage/
│       └── repository.py
│
└── agents/ (legacy)
    ├── autonomous_agent.py ◄───── Used for crawl/analyze
    └── generator_agent.py ◄────── Used for AI generation
```

---

## Execution Timeline Example

```
T+0s    ┌─────────────────────────────────────────┐
        │ User clicks "Run AgentQE Pipeline"      │
        └─────────────────────────────────────────┘

T+0.5s  ┌─────────────────────────────────────────┐
        │ Run created in DB, run_id returned      │
        │ Background thread starts                │
        │ Status: "Starting"                      │
        └─────────────────────────────────────────┘

T+1s    ┌─────────────────────────────────────────┐
        │ Stage 1: TEST STRATEGY                  │
        │ Strategy planned and saved              │
        │ Status: "Analysis"                      │
        └─────────────────────────────────────────┘

T+3s    ┌─────────────────────────────────────────┐
        │ Stage 2: APPLICATION UNDERSTANDING      │
        │ Browser launches, crawls URL            │
        │ Extracts DOM and selectors              │
        └─────────────────────────────────────────┘

T+8s    ┌─────────────────────────────────────────┐
        │ Stage 3: USER TEST GENERATION           │
        │ AI generates 15 user test cases         │
        │ Status: "Generation"                    │
        └─────────────────────────────────────────┘

T+12s   ┌─────────────────────────────────────────┐
        │ Stage 4: ENGINEERING TEST GENERATION    │
        │ Returns 1 stub UNIT test                │
        └─────────────────────────────────────────┘

T+13s   ┌─────────────────────────────────────────┐
        │ Stage 5: CANDIDATE POOL                 │
        │ Merges and deduplicates → 16 tests      │
        └─────────────────────────────────────────┘

T+14s   ┌─────────────────────────────────────────┐
        │ Stage 6: TEST ENRICHMENT                │
        │ Adds risk/cost/complexity scores        │
        └─────────────────────────────────────────┘

T+15s   ┌─────────────────────────────────────────┐
        │ Stage 7: ML RANKING                     │
        │ Transformer scores tests (untrained)    │
        └─────────────────────────────────────────┘

T+16s   ┌─────────────────────────────────────────┐
        │ Stage 8: ADAPTIVE SELECTION             │
        │ Selects top 10 tests for execution      │
        └─────────────────────────────────────────┘

T+17s   ┌─────────────────────────────────────────┐
        │ Stage 9: TEST EXECUTION                 │
        │ Browser executes 10 tests               │
        │ - 7 PASS                                │
        │ - 2 HEALED                              │
        │ - 1 FAIL                                │
        │ Status: "Execution"                     │
        └─────────────────────────────────────────┘

T+45s   ┌─────────────────────────────────────────┐
        │ Stage 10: FAILURE ANALYSIS              │
        │ Analyzes 1 failure                      │
        └─────────────────────────────────────────┘

T+46s   ┌─────────────────────────────────────────┐
        │ Stage 11: RISK ANALYSIS                 │
        │ Risk score: 10% (90% passed)            │
        │ Readiness: "Ready"                      │
        └─────────────────────────────────────────┘

T+47s   ┌─────────────────────────────────────────┐
        │ Stage 12: QUALITY EVALUATION            │
        │ Decision: PROCEED (1 failure, cycle 1)  │
        │ Status: "Reporting"                     │
        └─────────────────────────────────────────┘

T+48s   ┌─────────────────────────────────────────┐
        │ Stage 13: FINAL REPORT                  │
        │ Report generated and saved              │
        │ Status: "Completed"                     │
        └─────────────────────────────────────────┘

T+48.5s ┌─────────────────────────────────────────┐
        │ Frontend detects "Completed" status     │
        │ Stops polling                           │
        │ Displays final report                   │
        └─────────────────────────────────────────┘

T+60s   ┌─────────────────────────────────────────┐
        │ (Optional) User submits review          │
        │ Decision: APPROVE                       │
        │ Feedback saved to DB                    │
        └─────────────────────────────────────────┘
```

---

## Log Action Types Reference

| Action Type        | Stage                      | Description                           |
|--------------------|----------------------------|---------------------------------------|
| `PIPELINE`         | Overall                    | Pipeline start/complete/error         |
| `STRATEGY`         | Test Strategy              | Strategy planning logs                |
| `BROWSER`          | Application Understanding  | Page crawling logs                    |
| `ANALYSIS`         | Application Understanding  | Requirement analysis logs             |
| `GENERATION`       | Test Generation            | User + Engineering test generation    |
| `POOL`             | Candidate Pool             | Merging and deduplication             |
| `ENRICHMENT`       | Test Enrichment            | Metadata enrichment                   |
| `RANKING`          | ML Ranking                 | Transformer scoring                   |
| `SELECTION`        | Adaptive Selection         | Top-K test selection                  |
| `EXECUTION`        | Test Execution             | Browser test execution                |
| `FAILURE_ANALYSIS` | Failure Analysis           | Failure root cause analysis           |
| `RISK_ANALYSIS`    | Risk Analysis              | Risk computation                      |
| `QUALITY_EVAL`     | Quality Evaluation         | REPLAN/PROCEED decision               |
| `REPORT`           | Final Report               | Report generation                     |

---

## Status Flow

```
Starting
   ↓
Analysis (Strategy + Understanding)
   ↓
Generation (User + Engineering tests)
   ↓
Execution (Browser automation)
   ↓
Reporting (Analysis + Risk + Report)
   ↓
Completed
```

---

## Decision Points

### 1. ML Ranking Fallback
```
Try Transformer ranking
  ↓
Success? → Use ML scores
  ↓
Fail? → Use rule-based priority fallback
```

### 2. Quality Evaluation
```
Count failures
  ↓
failures > 0 AND cycle < max_cycles?
  ↓
YES → Log "REPLAN" (not auto-triggered)
  ↓
NO → Log "PROCEED"
```

### 3. Test Execution
```
For each selected test:
  ↓
Execute browser action
  ↓
Success? → Mark PASS
  ↓
Fail? → Attempt self-healing
    ↓
    Healed? → Mark HEALED
    ↓
    Still Fail? → Mark FAIL
```

---

**Diagram Version**: 1.0  
**Date**: 2026-09-25  
**Status**: ✅ CURRENT ARCHITECTURE
