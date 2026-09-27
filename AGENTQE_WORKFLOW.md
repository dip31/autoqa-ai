# AgentQE One-Click Workflow Guide

## Overview

The AgentQE one-click workflow is now fully integrated into the AutoQA application. This document describes how to use it and what happens under the hood.

## What is AgentQE?

AgentQE is an **ML-enhanced, multi-perspective QA orchestration pipeline** that goes beyond traditional autonomous QA by:

1. **Multi-Perspective Test Generation**: Combines user-focused tests with engineering QA tests (unit/API/security)
2. **ML-Based Prioritization**: Uses a Transformer-based ranker to score and prioritize tests
3. **Adaptive Quality Loop**: Evaluates results and can recommend re-planning
4. **Candidate Test Pool**: Deduplicates and merges tests from multiple sources
5. **Test Enrichment**: Adds risk, cost, and complexity metadata
6. **Failure Analysis**: Post-execution analysis with actionable recommendations

## How to Use the One-Click Workflow

### Step 1: Navigate to Autonomous QA Page

From the main dashboard, click on **"Autonomous QA"** in the sidebar.

### Step 2: Fill in the Form

Required fields:
- **Run Title**: A descriptive name for this test run
- **Requirement/User Story**: The feature or functionality you want to test

Optional fields:
- **Module**: Module name (e.g., "Frontend", "Authentication")
- **Initial URL**: Website URL to test (enables browser execution)
- **Git Repository URL**: For repository intelligence scanning

### Step 3: Select Pipeline Mode

At the bottom of the form, choose:
- **🤖 Standard**: Traditional autonomous QA pipeline
- **⚡ AgentQE ML**: Advanced ML-enhanced pipeline

Toggle to **"AgentQE ML"** for the one-click full workflow.

### Step 4: Click "Run AgentQE Pipeline"

The system will:
1. Create a run entry in the database
2. Launch the AgentQE pipeline in a background thread
3. Navigate you to the run detail page
4. Begin real-time polling to show progress

### Step 5: Monitor Progress

The UI shows:
- **5-Stage Stepper**: Analysis → Generation → Execution → Reporting → Completed
- **AgentQE Stage Detail**: Expanded view showing STRATEGY, POOL, ENRICHMENT, RANKING, SELECTION, etc.
- **Live Logs**: Real-time browser actions and stage transitions
- **Test Cases**: All generated tests with status
- **Auto-Heal**: Self-healing attempts and results
- **Final Report**: Executive summary and recommendations

## The End-to-End Workflow

### Stage 1: Application Understanding

**What happens:**
- If URL provided: Crawls the live website using Playwright
- Extracts page structure: forms, buttons, links, navigation
- Detects application type (e-commerce, SaaS, blog, etc.)
- Identifies key user flows (login, search, checkout, etc.)

**Agent:** `_crawl_page()` + `_analyze_requirement()`

**Logs:** `BROWSER`, `CRAWL`, `ANALYSIS`

### Stage 2: Test Strategy Planning

**What happens:**
- `TestStrategyAgent` analyzes requirement and app context
- Plans test types: UI, API, Security, Unit, Integration
- Determines priorities and coverage areas

**Agent:** `TestStrategyAgent`

**Logs:** `STRATEGY`

**Output:** Strategy JSON with test types and priorities

### Stage 3: Multi-Perspective Test Generation

**What happens:**
- **User Tests**: Rich test generator creates 20-40 user-focused tests with real selectors
- **Engineering Tests**: EngineeringQAAgent adds technical perspective tests

**Agents:** 
- `_generate_rich_cases()` (user perspective)
- `EngineeringQAAgent` (engineering perspective)

**Logs:** `GENERATION`

**Current Reality:**
- User tests: Fully functional, includes real browser selectors
- Engineering tests: **Currently a stub** — returns 1 sample unit test

### Stage 4: Candidate Test Pool

**What happens:**
- Merges user + engineering tests
- Deduplicates based on title/description similarity
- Creates unified test pool

**Component:** `CandidateTestPool`

**Logs:** `POOL`

### Stage 5: Test Enrichment

**What happens:**
- Adds metadata to each test:
  - Risk score (0.0 - 1.0)
  - Execution cost estimate
  - Complexity score
  - Historical performance (currently heuristic)

**Component:** `TestEnricher`

**Logs:** `ENRICHMENT`

**Current Reality:** Uses heuristic values, not real historical data

### Stage 6: ML Transformer Ranking

**What happens:**
- Extracts features from each test
- Passes through Transformer model
- Assigns ML-based priority score

**Components:**
- `TestFeatureExtractor`
- `TransformerTestRanker`
- `TestRanker`

**Logs:** `RANKING`

**Current Reality:**
- ⚠️ **Model is UNTRAINED** — uses random initialization weights
- Scores are generated but not production-ready
- Fallback to rule-based ranking if Transformer fails

### Stage 7: Adaptive Test Selection

**What happens:**
- Selects top-K tests from ranked pool
- Considers execution budget constraints
- Balances coverage vs. efficiency

**Component:** `AdaptiveController`

**Logs:** `SELECTION`

**Output:** Subset of tests to execute (typically 18-30 tests)

### Stage 8: Test Execution

**What happens:**
- Launches Playwright browser (headless Chrome)
- Executes each selected test with **4-stage self-healing**:
  1. Direct attempt
  2. Retry after timing delay
  3. Relaxed selector matching
  4. DOM similarity search

**Components:**
- `_execute_test_pipeline()`
- `SelfHealingEngine`

**Logs:** `EXECUTION`, `BROWSER_ACTION`, `HEALING`, `RESULT`

**Statuses:**
- `PASS`: Test passed on first attempt
- `HEALED`: Test failed initially but auto-healed
- `FAIL`: All 4 healing stages exhausted
- `Blocked`: Requires manual data/auth
- `Skipped`: Beyond execution limit

### Stage 9: Failure Analysis

**What happens:**
- Analyzes failed tests
- Identifies patterns
- Categorizes failure types
- Generates findings

**Agent:** `FailureAnalysisAgent`

**Logs:** `FAILURE_ANALYSIS`

### Stage 10: Adaptive Quality Evaluation

**What happens:**
- Computes quality score (0-100%)
- Evaluates cycle completion
- Returns decision: `PROCEED` or `REPLAN`

**Agent:** `AdaptiveQualityAgent`

**Logs:** `QUALITY_EVAL`

**Current Reality:**
- Decision is computed but does NOT automatically trigger re-test
- Re-test loop is **not yet implemented**

### Stage 11: Risk Analysis

**What happens:**
- Identifies high-risk test areas
- Computes module risk score
- Determines release readiness

**Logs:** `RISK_ANALYSIS`

**Output:**
- Risk score
- Confidence level
- High-risk areas
- Recommendations

### Stage 12: Final Report Generation

**What happens:**
- Aggregates all metrics
- Generates executive summary
- Compiles detailed report JSON
- Saves to database

**Logs:** `REPORT`, `PIPELINE`

**Output:**
- Executive summary
- Final verdict
- Complete report JSON

### Stage 13: Human Review (Optional)

**What happens:**
- User can review results
- Submit APPROVE or REPLAN decision
- Decision is persisted to database

**API:** `POST /api/agentqe/review/{run_id}`

**Current Reality:**
- ⚠️ Review is saved but does NOT automatically restart the pipeline
- No blocking/resume mechanism currently implemented

### Stage 14: Re-Test (Future)

**Current Status:** ⚠️ **Not implemented**

**Planned behavior:**
- If REPLAN decision → regenerate tests → re-execute
- If APPROVE decision → finalize and close

## API Endpoints

### Start AgentQE Run

```
POST /api/agentqe/run
Authorization: Bearer <token>

{
  "title": "User Auth Testing",
  "module_name": "Authentication",
  "requirement_text": "Test login and registration flows",
  "url": "https://example.com",
  "repo_url": "https://github.com/user/repo",
  "execution_mode": "AgentQE Pipeline",
  "max_cycles": 3
}

Response:
{
  "success": true,
  "run_id": 123
}
```

### Get Run Details

```
GET /api/autonomous-qa/run/{run_id}
Authorization: Bearer <token>

Response:
{
  "success": true,
  "run": { ... },
  "scope": { ... },
  "test_cases": [ ... ],
  "logs": [ ... ],
  "findings": [ ... ],
  "risk": { ... },
  "report": { ... },
  "healing": [ ... ],
  "repo_intelligence": { ... }
}
```

### Submit Human Review

```
POST /api/agentqe/review/{run_id}
Authorization: Bearer <token>

{
  "decision": "APPROVE",  // or "REPLAN"
  "feedback": "Tests look good, ready to deploy",
  "cycle": 1
}

Response:
{
  "success": true,
  "review": { ... }
}
```

## Database Schema

All data is stored in the existing `autonomous_*` tables:

- `autonomous_runs`: Run metadata, status, timestamps
- `autonomous_scope`: Requirement analysis results
- `autonomous_test_cases`: Generated test cases
- `autonomous_execution_logs`: Detailed action logs
- `autonomous_healing_logs`: Self-healing attempts
- `autonomous_findings`: Bug findings
- `autonomous_risk_analysis`: Risk assessment
- `autonomous_reports`: Final reports
- `autonomous_repo_intelligence`: Repo scan results

## Current Limitations

### What is NOT Yet Production-Ready

1. **Transformer Model**
   - ⚠️ Uses random weights (not trained)
   - Scores are generated but not reliable
   - Fallback to rule-based ranking available

2. **Engineering QA Agent**
   - ⚠️ Currently returns 1 dummy unit test
   - API/Security tests not generated
   - Needs real implementation

3. **Test Enrichment**
   - Uses heuristic values
   - No real historical learning
   - No coverage tracking

4. **Re-Test Loop**
   - ⚠️ Not implemented
   - REPLAN decision is saved but doesn't trigger re-execution
   - No automatic loop back to planning stage

5. **Human Review Orchestration**
   - Review is persisted
   - ⚠️ Does NOT block execution
   - ⚠️ Does NOT resume pipeline after approval

6. **Execution Runners**
   - `PytestRunner`: Exists but unused in current flow
   - `APIRunner`: Exists but unused
   - `SecurityRunner`: Empty stub

7. **Docker Sandbox**
   - ⚠️ Not functional
   - Tests run in local Playwright browser

8. **LangGraph / n8n**
   - ⚠️ Not implemented
   - Direct Python orchestration used

### What IS Production-Ready

✅ **User test generation**: Fully functional with real selectors  
✅ **Live browser crawling**: Playwright-based page analysis  
✅ **4-stage self-healing**: Robust selector recovery  
✅ **Test execution**: Reliable Playwright automation  
✅ **Failure analysis**: Pattern detection and categorization  
✅ **Risk analysis**: Scoring and recommendation generation  
✅ **Report generation**: Complete JSON reports  
✅ **UI visualization**: Real-time progress and stage tracking  
✅ **Logging system**: Comprehensive audit trail  

## Example Workflow Run

```
User: [Fills form]
  Title: "E-commerce Checkout Testing"
  Requirement: "Test product search, cart, and checkout flows"
  URL: "https://shop.example.com"
  Mode: AgentQE ML
  
User: [Clicks "Run AgentQE Pipeline"]

System: Creates run_id=42

Backend Pipeline (in thread):
  ✓ STRATEGY: Planned 5 test types (UI, Navigation, Form, Negative, Boundary)
  ✓ GENERATION: User tests = 30, Engineering tests = 1 (stub)
  ✓ POOL: 31 total → 28 unique after dedup
  ✓ ENRICHMENT: Added risk/cost metadata
  ✓ RANKING: ML scored 28 tests (UNTRAINED model warning)
  ✓ SELECTION: Selected top 20 tests
  ✓ EXECUTION: Browser launched
    - TC-001 (Search): PASS
    - TC-002 (Add to Cart): HEALED (selector retry)
    - TC-003 (Checkout): FAIL (all stages exhausted)
    - ...
  ✓ FAILURE_ANALYSIS: 3 failures analyzed
  ✓ QUALITY_EVAL: Score=82%, Decision=PROCEED
  ✓ RISK_ANALYSIS: 1 high-risk area (checkout flow)
  ✓ REPORT: Ready for deployment with 3 recommendations

UI: Shows completed run with:
  - 20 executed tests
  - 15 passed
  - 3 auto-healed
  - 2 failed
  - Quality score: 82%
  - Final verdict: "Ready for deployment"
```

## Troubleshooting

### Pipeline hangs at "Starting"

**Cause:** Background thread crash  
**Solution:** Check backend logs for Python errors

### Transformer ranking fails

**Cause:** PyTorch/model import error  
**Solution:** Pipeline automatically falls back to rule-based ranking

### All tests marked as "Blocked"

**Cause:** Tests require authentication/test data  
**Solution:** Provide URL with publicly accessible test pages

### Browser tests fail immediately

**Cause:** Playwright not installed  
**Solution:** Run `playwright install chromium`

### No logs appearing

**Cause:** Database write error  
**Solution:** Check SQLite permissions on `autoqa.db`

## Future Enhancements

1. **Train Transformer Model**: Collect execution data → train prioritization model
2. **Complete Engineering Agent**: Real API/unit/security test generation
3. **Implement Re-Test Loop**: Automatic REPLAN → regenerate → execute
4. **Add Docker Sandbox**: Isolated test execution environment
5. **Human Review Blocking**: Pause pipeline at review checkpoint
6. **Historical Learning**: Track test performance over time
7. **Coverage Tracking**: Map tests to code/requirements
8. **LangGraph Integration**: More sophisticated agent orchestration
9. **Multi-Cycle Execution**: Automatic improvement iterations
10. **Test Mutation**: Evolutionary test optimization

## Architecture Diagrams

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INPUT                              │
│  Title, Requirement, URL, Repo, Module, Mode                   │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AGENTQE PIPELINE                             │
├─────────────────────────────────────────────────────────────────┤
│  1. Application Understanding (Crawl + Analyze)                 │
│  2. Test Strategy Planning                                      │
│  3. Multi-Perspective Generation (User + Engineering)           │
│  4. Candidate Pool Merge + Dedup                                │
│  5. Test Enrichment (Risk/Cost/Complexity)                      │
│  6. ML Transformer Ranking (UNTRAINED)                          │
│  7. Adaptive Selection (Top-K)                                  │
│  8. Browser Execution (4-Stage Self-Healing)                    │
│  9. Failure Analysis                                            │
│ 10. Adaptive Quality Evaluation                                 │
│ 11. Risk Analysis                                               │
│ 12. Report Generation                                           │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DATABASE PERSISTENCE                         │
│  autonomous_runs, test_cases, logs, findings, risk, reports    │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                      UI VISUALIZATION                           │
│  Stage Progress, Live Logs, Test Results, Auto-Heal, Report    │
└─────────────────────────────────────────────────────────────────┘
```

## Component Status Matrix

| Component | Status | Production Ready | Notes |
|-----------|--------|------------------|-------|
| TestStrategyAgent | ✅ Functional | Yes | Plans test types |
| UserTestGenerator | ✅ Functional | Yes | Real selectors |
| EngineeringQAAgent | ⚠️ Stub | No | Returns 1 dummy test |
| CandidateTestPool | ✅ Functional | Yes | Dedup working |
| TestEnricher | ⚠️ Heuristic | Partial | No real history |
| TransformerTestRanker | ⚠️ Untrained | No | Random weights |
| TestFeatureExtractor | ✅ Functional | Yes | Extracts features |
| AdaptiveController | ✅ Functional | Yes | Selects top-K |
| PlaywrightAdapter | ✅ Functional | Yes | Executes tests |
| SelfHealingEngine | ✅ Functional | Yes | 4-stage recovery |
| FailureAnalysisAgent | ✅ Functional | Yes | Pattern detection |
| AdaptiveQualityAgent | ⚠️ Partial | Partial | No re-test loop |
| HumanReviewService | ⚠️ Partial | Partial | No orchestration |
| PytestRunner | ⚠️ Unused | No | Exists but not called |
| APIRunner | ⚠️ Unused | No | Exists but not called |
| SecurityRunner | ⚠️ Empty | No | Stub only |

## Conclusion

The AgentQE one-click workflow is **operational** and provides a complete end-to-end testing pipeline. While some components are still prototypes (Transformer, Engineering Agent, Re-test Loop), the core workflow is functional and produces real, actionable test results.

The system honestly represents its current capabilities through logging and does not falsely claim features that don't exist. As each component matures, the workflow will become more sophisticated while maintaining the same simple one-click user experience.
