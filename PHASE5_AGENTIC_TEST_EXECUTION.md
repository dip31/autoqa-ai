# Phase 5 — Agentic Test Execution

## Overview
Phase 5 introduces deterministic, ranked test execution with Playwright as the primary engine and optional Browser Use recovery. Results are persisted with full evidence (screenshots, traces, console/network logs) and exposed via JWT-protected APIs. The frontend gains a "Test Execution" tab to run prioritized suites against a local application.

## Architecture
| Layer | Responsibility |
|-------|----------------|
| **API** | `POST /api/agentqe/tests/execute`, `POST /api/agentqe/tests/execute/<id>`, `GET /api/agentqe/executions`, `GET /api/agentqe/executions/<id>` |
| **Service** | `ExecutionService` orchestrates priority-ordered batch runs, per-test planning, evidence collection, and persistence |
| **Executor (Playwright)** | Isolated browser context per test, selector ladder (role/name → test-id → label → stable attr → observed CSS → observed XPath), structured assertions, no positional selectors |
| **Executor (Browser Use)** | Optional, opt-in via `AGENTQE_BROWSER_USE_ENABLED=true`. Only engages after deterministic failure, whitelisted categories, and plan permission |
| **Planner** | Converts CandidateTest/RankedTest → ExecutionPlan (steps + assertions). Respects `automatable=false` → skipped, `base_url`, `rank_position` |
| **Evidence** | Screenshots (step + failure), full Playwright trace, console errors, network evidence, artifacts index (paths + SHA-256) |
| **Persistence** | SQLite tables: `agentqe_execution_runs`, `agentqe_executions`, `agentqe_execution_steps`, `agentqe_execution_artifacts` |

## Key Invariants
- **Sequential only** — concurrency >1 is clamped.
- **Status set**: `passed`, `failed`, `skipped`, `blocked`, `unsupported`, `timeout`, `error`
- **Failure categories**: `ELEMENT_NOT_FOUND`, `ELEMENT_NOT_INTERACTABLE`, `NAVIGATION_ERROR`, `ASSERTION_FAILED`, `TIMEOUT`, `NETWORK_ERROR`, `BROWSER_ERROR`, `UNSUPPORTED_ACTION`, `MISSING_TEST_DATA`, `EXECUTOR_ERROR`
- **Credential safety**: only synthetic/configured via `AGENTQE_EXECUTION_CREDENTIALS`; no ambient secret access
- **No Phase 6 fields**: root-cause, severity, novelty, self-healing actions are never invented
- **Ranking provenance preserved**: `rank_position`, `priority_score`, `ranking_mode`, `model_status`, `model_version`, `feature_version`, `features`, `feature_contributions` flow from Phase 4 through to results

## Configuration
Environment variables (`.env`):
```
AGENTQE_BROWSER_USE_ENABLED=false
AGENTQE_ARTIFACT_DIR=backend/data/agentqe/executions
AGENTQE_EXECUTION_CREDENTIALS={"user1": {"email": "...", "password": "..."}}
PLAYWRIGHT_BROWSER_PATH=    # optional override
AGENTQE_DEFAULT_TIMEOUT_MS=30000
```

## API Contract
### POST /api/agentqe/tests/execute
```json
{
  "tests": [ RankedTestWrapper | CandidateTest ],
  "base_url": "http://localhost:5000",
  "application_context": { ... }
}
```
Response:
```json
{
  "success": true,
  "execution_run_id": "execrun_...",
  "summary": { "total": 5, "passed": 3, "failed": 1, ... },
  "results": [ ExecutionResultDict ],
  "persisted": true,
  "skipped_inputs": [],
  "browser_use_enabled": false
}
```

### GET /api/agentqe/executions
Query: `limit`, `offset`, `status`, `test_id`, `run_id`, `from`, `to`

## Frontend: "Test Execution" Tab
Located in `frontend/src/pages/AgentQE.jsx` after "Test Prioritization".
Features:
- Base URL input (validated)
- Execute button (enabled after prioritization)
- Run summary cards (passed/failed/timeout/error/blocked/unsupported/skipped)
- Expandable result rows with:
  - Steps (action, target, selector strategy, status, error)
  - Assertions (type, expected, pass/fail)
  - Evidence counts (screenshots, console errors, trace path)
  - Ranking provenance badges (ranking_mode, model_status, feature_version, score)

## Running Phase 5 Tests
```bash
# Backend
cd backend
& ".venv/Scripts/python.exe" -m pytest tests/test_agentqe_phase5_execution.py -v

# Full regression
& ".venv/Scripts/python.exe" -m pytest tests/ -q

# Frontend build
cd frontend
npm run build
```

## Local E2E (Playwright)
```bash
cd frontend
npx playwright install
npx playwright test tests/e2e/login.spec.js
```

## Database Schema (authoritative: `backend/database/init_db.py`)
```sql
CREATE TABLE agentqe_execution_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT UNIQUE NOT NULL,
  user_id INTEGER NOT NULL,
  application_id INTEGER,
  autonomous_run_id TEXT,
  total_tests INTEGER NOT NULL,
  passed INTEGER NOT NULL,
  failed INTEGER NOT NULL,
  timeout INTEGER NOT NULL,
  error INTEGER NOT NULL,
  blocked INTEGER NOT NULL,
  unsupported INTEGER NOT NULL,
  skipped INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  persisted BOOLEAN NOT NULL DEFAULT 1,
  config_json TEXT
);

CREATE TABLE agentqe_executions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  execution_id TEXT UNIQUE NOT NULL,
  run_id TEXT NOT NULL REFERENCES agentqe_execution_runs(run_id),
  test_id TEXT NOT NULL,
  test_title TEXT,
  status TEXT NOT NULL,
  executor TEXT NOT NULL,
  layer TEXT,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  duration_ms REAL,
  steps_total INTEGER,
  steps_completed INTEGER,
  failed_step INTEGER,
  assertions_total INTEGER,
  assertions_passed INTEGER,
  assertions_failed INTEGER,
  error TEXT,
  error_category TEXT,
  trace_path TEXT,
  page_url TEXT,
  start_url TEXT,
  final_url TEXT,
  rank_position INTEGER,
  priority_score REAL,
  predicted_priority REAL,
  ranking_mode TEXT,
  model_status TEXT,
  model_version TEXT,
  feature_version TEXT,
  features_json TEXT,
  feature_contributions_json TEXT,
  metadata_json TEXT
);

CREATE TABLE agentqe_execution_steps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  execution_id TEXT NOT NULL REFERENCES agentqe_executions(execution_id),
  execution_pk INTEGER NOT NULL,
  step_index INTEGER NOT NULL,
  action TEXT NOT NULL,
  target TEXT,
  status TEXT,
  selector_strategy TEXT,
  error TEXT,
  assertion_type TEXT,
  assertion_passed INTEGER,
  expected TEXT,
  duration_ms REAL,
  screenshot_path TEXT
);

CREATE TABLE agentqe_execution_artifacts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  execution_id TEXT NOT NULL REFERENCES agentqe_executions(execution_id),
  artifact_type TEXT NOT NULL,
  path TEXT NOT NULL,
  label TEXT,
  step_index INTEGER,
  sha256 TEXT,
  size_bytes INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

## Files Modified / Added
| Path | Purpose |
|------|---------|
| `backend/agentqe/models/execution.py` | Structured `ExecutionResult`, `ExecutionRunResult`, `ExecutionSummary` (back-compat positional constructor) |
| `backend/agentqe/execution/config.py` | Environment config, credential safety |
| `backend/agentqe/execution/schemas.py` | Plan, step, assertion, screenshot, status, executor enums |
| `backend/agentqe/execution/interfaces.py` | Planner, Executor, EvidenceCollector, Browser Use, Repository contracts |
| `backend/agentqe/execution/redaction.py` | Secret sanitization |
| `backend/agentqe/execution/selectors.py` | Evidence-based selector ladder |
| `backend/agentqe/execution/execution_planner.py` | Deterministic test → plan conversion |
| `backend/agentqe/execution/action_executor.py` | Deterministic Playwright action dispatch |
| `backend/agentqe/execution/evidence_collector.py` | Screenshots, traces, console, network, artifacts |
| `backend/agentqe/execution/playwright_executor.py` | Isolated per-test Playwright lifecycle |
| `backend/agentqe/execution/browser_use_executor.py` | Optional Browser Use adapter (opt-in) |
| `backend/agentqe/execution/execution_service.py` | Priority-ordered batch orchestrator + ranking provenance |
| `backend/agentqe/execution/persistence.py` | SQLite repository for runs/executions/steps/artifacts |
| `backend/database/init_db.py` | Phase 5 tables in init + migrations |
| `backend/app.py` | JWT routes + `_coerce_candidate_tests` preserving wrappers |
| `backend/tests/test_agentqe_phase5_execution.py` | 70 tests (redaction, planning, selectors, actions, executors, service, Browser Use gating, persistence, API) |
| `frontend/src/api/client.js` | `executeAgentQETests`, `executeAgentQETest`, `getAgentQEExecutions` |
| `frontend/src/pages/AgentQE.jsx` | "Test Execution" tab with summary, expandable results, evidence, provenance |
| `frontend/tests/e2e/login.spec.js` | Local login E2E fixture |

## Verification Checklist
- [x] Phase 5 test suite: **70 passed**
- [x] Full regression: **249 passed, 6 failed (pre-existing), 1 skipped**
- [x] Frontend build: **compiled successfully**
- [x] Database migrations applied (4 new tables)
- [x] API routes registered and JWT-protected
- [x] Browser Use gated by config + plan + failure whitelist
- [x] Ranking provenance survives API → Service → Result
- [x] No Phase 6 fields in API responses
- [x] Credential allow-list only; no ambient secrets