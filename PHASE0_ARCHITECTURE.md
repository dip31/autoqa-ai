# Phase 0 Architecture Document
## AutoQA AI - Foundation & Architecture Preparation

---

## 1. Existing System Boundary

### 1.1 Legacy Features (Preserved, Unchanged)
| Feature | Frontend Route | Backend API | Description |
|---------|----------------|-------------|-------------|
| Dashboard | `/` | - | Overview & stats |
| Test Case Review | `/test-review` | `/review-testcase` | Manual test case review & scoring |
| Code Review | `/code-review` | `/review-code` | Code quality analysis |
| Website Testing | `/website-testing` | `/website-test` | Live website analysis |
| Test Generator | `/test-generator` | `/generate-testcase` | Requirement → test cases |
| Risk Prediction | `/risk-prediction` | `/predict-risk` | Risk scoring |
| Smart Report | `/smart-report` | `/generate-report` | Aggregated QA report |
| Autonomous QA (Standard) | `/autonomous-qa` | `/api/autonomous-qa/*` | Self-driven QA lifecycle |
| GitHub Intelligence | `/github-intelligence` | `/api/github/*` | Repo analysis |
| QA Messages | `/messages` | `/api/messages/*` | Team messaging |
| Developer Portal | (in sidebar) | `/api/dev/*` | Projects, diagrams, code, risk |

### 1.2 Existing Database Tables (Legacy)
- `users`, `test_cases`, `code_reviews`, `website_tests`, `reports`
- `chat_sessions`, `chat_messages`
- `github_analyses`

### 1.3 Existing Autonomous QA Tables (Shared)
- `autonomous_runs`, `autonomous_scope`, `autonomous_test_cases`
- `autonomous_execution_logs`, `autonomous_findings`
- `autonomous_risk_analysis`, `autonomous_reports`
- `autonomous_healing_logs`, `autonomous_repo_intelligence`

---

## 2. New Capability Boundary: AgentQE

### 2.1 Location
```
backend/agentqe/
├── agents/           # Strategy, Engineering, Adaptive, Failure, Quality
├── enrichment/       # Test metadata enrichment
├── execution/        # Playwright, Pytest, API, Security runners
├── human/            # Human review service
├── ml/               # Features, inference, transformer ranker
├── models/           # ApplicationContext, TestCase, ExecutionResult
├── orchestration/    # State management
├── pool/             # Candidate test pool & deduplication
├── storage/          # Repository abstraction
├── interfaces/       # NEW: Capability contracts (Phase 0)
├── pipeline.py       # Main orchestration
└── __init__.py
```

### 2.2 Separation Rules
- **AgentQE does NOT depend on** `agents/autonomous_agent.py` internals
- **AgentQE uses** `database.db.execute_query` for persistence (low-level utility)
- **AgentQE defines its own** data models in `agentqe/models/`
- **AgentQE exposes** `/api/agentqe/*` API namespace
- **Legacy autonomous_qa** remains at `/api/autonomous-qa/*` unchanged

### 2.3 Shared Tables (Read/Write)
| Table | AgentQE Use | Legacy Use |
|-------|-------------|------------|
| `autonomous_runs` | Primary run record | Primary run record |
| `autonomous_scope` | Scope from strategy | Scope from analysis |
| `autonomous_test_cases` | All generated candidates | Generated test cases |
| `autonomous_execution_logs` | Pipeline stage logs | Browser action logs |
| `autonomous_findings` | Failure analysis output | Findings |
| `autonomous_risk_analysis` | Risk metrics | Risk analysis |
| `autonomous_reports` | Final report | Final report |
| `autonomous_healing_logs` | Self-healing events | Healing logs |
| `autonomous_repo_intelligence` | Repo analysis | Repo intelligence |

> **Note:** Shared tables are a pragmatic Phase 0 decision. Phase 1+ may introduce dedicated AgentQE tables.

---

## 3. Common Data Models (Defined in `agentqe/models/`)

### 3.1 ApplicationContext
```python
@dataclass
class ApplicationContext:
    url: str = ""
    repo_url: str = ""
    requirement: str = ""
    module_name: str = ""
    page_data: Dict[str, Any] = field(default_factory=dict)
    repository_data: Dict[str, Any] = field(default_factory=dict)
    source_files: List[str] = field(default_factory=list)
    api_endpoints: List[str] = field(default_factory=list)
    existing_tests: List[str] = field(default_factory=list)
    technology_stack: Dict[str, Any] = field(default_factory=dict)
```

### 3.2 TestCase (CandidateTest)
```python
@dataclass
class CandidateTest:
    test_id: str
    title: str
    description: str = ""
    perspective: str = "USER"          # USER, DEVELOPER, SECURITY, PERFORMANCE
    test_type: str = "UI"              # UI, API, UNIT, SECURITY, INTEGRATION
    target: str = ""
    priority: str = "Medium"           # Critical, High, Medium, Low
    category: str = ""
    steps: List = field(default_factory=list)
    input_data: str = ""
    expected_result: str = ""
    automatable: bool = True
    blocked_reason: Optional[str] = None
    source_agent: str = ""
    metadata: Dict = field(default_factory=dict)
    # Enrichment fields
    risk_score: float = 0.5
    historical_pass_rate: float = 0.0
    historical_failure_rate: float = 0.0
    execution_cost: float = 3.0
    change_impact: float = 0.5
    coverage_gain: float = 0.5
    # ML ranking
    transformer_score: float = 0.0
    final_score: float = 0.0
```

### 3.3 ExecutionResult
```python
@dataclass
class ExecutionResult:
    test_id: str
    status: str                        # PASS, FAIL, HEALED, BLOCKED, SKIPPED
    duration_ms: float = 0.0
    error: Optional[str] = None
    coverage: float = 0.0
    healed: bool = False
    screenshot_path: Optional[str] = None
    security_findings: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### 3.4 Finding
```python
@dataclass
class Finding:
    finding_id: str
    category: str                      # FUNCTIONAL, SECURITY, PERFORMANCE, USABILITY
    severity: str                      # CRITICAL, HIGH, MEDIUM, LOW, INFO
    description: str
    evidence: Dict = field(default_factory=dict)
    source: str                        # EXECUTION, STATIC_ANALYSIS, ML_RANKER
    status: str = "OPEN"               # OPEN, TRIAGED, FIXED, WONT_FIX
```

### 3.5 Risk
```python
@dataclass
class Risk:
    risk_id: str
    area: str                          # Module/feature name
    severity: str                      # CRITICAL, HIGH, MEDIUM, LOW
    score: float                       # 0-100
    reason: str
    evidence: List[str] = field(default_factory=list)
    affected_tests: List[str] = field(default_factory=list)
```

---

## 4. Capability Interfaces (Contracts)

### 4.1 Application Understanding → ApplicationContext
```python
class IApplicationUnderstanding:
    def analyze(self, url: str, requirement: str, repo_url: str) -> ApplicationContext
```

### 4.2 Test Generation → List[TestCase]
```python
class ITestGenerator:
    def generate(self, context: ApplicationContext, strategy: Dict) -> List[CandidateTest]
```

### 4.3 Prioritization → Prioritized TestCase[]
```python
class IPrioritizer:
    def rank(self, candidates: List[CandidateTest], context: ApplicationContext) -> List[CandidateTest]
    def select(self, ranked: List[CandidateTest], budget: int) -> List[CandidateTest]
```

### 4.4 Execution → List[ExecutionResult]
```python
class ITestExecutor:
    def execute(self, tests: List[CandidateTest], context: ApplicationContext) -> List[ExecutionResult]
```

### 4.5 Failure Analysis → List[Finding]
```python
class IFailureAnalyzer:
    def analyze(self, results: List[ExecutionResult], context: ApplicationContext) -> List[Finding]
```

### 4.6 Security Validation → List[Finding]
```python
class ISecurityValidator:
    def validate(self, context: ApplicationContext, tests: List[CandidateTest]) -> List[Finding]
```

---

## 5. API Boundary

### 5.1 New Namespace: `/api/agentqe/`
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/agentqe/run` | POST | Start AgentQE pipeline |
| `/api/agentqe/run/<id>` | GET | Get run details |
| `/api/agentqe/run/<id>/review` | POST | Human review decision |
| `/api/agentqe/run/<id>/cancel` | POST | Cancel running pipeline |
| `/api/agentqe/runs` | GET | List user's AgentQE runs |

### 5.2 Legacy Namespace (Unchanged): `/api/autonomous-qa/`
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/autonomous-qa/run` | POST | Start standard autonomous run |
| `/api/autonomous-qa/runs` | GET | List runs |
| `/api/autonomous-qa/run/<id>` | GET | Get run details |

---

## 6. UI Entry Point

### 6.1 Existing: `/agentqe` Route
- **Component:** `frontend/src/pages/AgentQE.jsx`
- **Navigation:** Sidebar item "AgentQE ML" with magic wand icon
- **Features:** Run input form, history, real-time polling, multi-tab results view

### 6.2 Integration Points
- Uses `runAgentQE` from `api/client.js` → `/api/agentqe/run`
- Uses `getAutonomousRunDetails` → `/api/autonomous-qa/run/<id>` (shared table)
- Uses `submitAgentQEReview` → `/api/agentqe/review/<id>`

---

## 7. Persistence Strategy

### 7.1 Current Approach (Phase 0)
- Reuse existing `autonomous_*` tables via `database.db.execute_query`
- No new tables created in Phase 0
- `agentqe/storage/repository.py` provides abstraction layer

### 7.2 Future (Phase 1+)
- Dedicated tables: `agentqe_contexts`, `agentqe_test_cases`, `agentqe_executions`, `agentqe_findings`, `agentqe_risks`
- Migration strategy: additive, backward compatible

---

## 8. Dependencies

### 8.1 Current (Allowed in Phase 0)
- Flask, Flask-CORS, Flask-JWT-Extended
- SQLite / MySQL (via `database.db`)
- requests, bcrypt, python-dotenv
- PyTorch (for transformer ranker - **untrained/stub**)
- Playwright (browser execution)

### 8.2 Explicitly NOT Added (Phase 1+)
- ❌ LangGraph / LangChain
- ❌ LlamaIndex / RAG / Vector databases
- ❌ New ML frameworks
- ❌ Orchestration frameworks
- ❌ Transformer training infrastructure

---

## 9. Intentionally Deferred (Phase 1+)

| Capability | Reason |
|------------|--------|
| Transformer model training | Requires labeled data, separate Phase |
| RAG / Vector database for knowledge | Separate infrastructure decision |
| Full LangGraph orchestration | Current pipeline.py is sufficient for Phase 0 |
| Adaptive re-planning loop | Requires quality agent feedback loop |
| Security scanner implementation | Uses stub runner currently |
| Full test-generation intelligence | Currently uses legacy `_generate_rich_cases` |
| Human review workflow UI | Basic approve/replan exists |
| Multi-agent debate/consensus | Future enhancement |

---

## 10. Future Phase Integration

### Phase 1: Intelligence Layer
- Implement `IApplicationUnderstanding` with LLM-based analysis
- Replace stub `TransformerTestRanker` with trained model
- Add `agentqe/knowledge/` for RAG-based context retrieval

### Phase 2: Orchestration
- Introduce LangGraph for dynamic workflow
- Implement `IPlanner` for adaptive re-planning
- Add `agentqe/orchestration/graph.py`

### Phase 3: Security & Compliance
- Implement `ISecurityValidator` with real scanners
- Add compliance mapping (OWASP, CWE)
- Integrate with `agentqe/execution/security_runner.py`

### Phase 4: Developer Experience
- Rich test case editor in UI
- IDE plugins for test sync
- CI/CD pipeline integration

---

## 11. Validation Checklist (Phase 0 Complete When)

- [ ] Existing backend tests pass
- [ ] Existing frontend build succeeds
- [ ] All legacy APIs (`/review-testcase`, `/api/autonomous-qa/*`, etc.) respond
- [ ] All legacy pages load (Dashboard, Test Review, Code Review, etc.)
- [ ] `/agentqe` page loads and can start a run
- [ ] `/api/agentqe/run` accepts POST and returns run_id
- [ ] `agentqe.models` can be imported independently
- [ ] No circular imports between `agentqe/` and `agents/`
- [ ] No coupling: AgentQE doesn't import `autonomous_agent` internals
- [ ] Documentation created at `PHASE0_ARCHITECTURE.md`

---

## 12. Files Modified/Created in Phase 0

### Created
- `backend/agentqe/interfaces/__init__.py` - Capability contracts
- `backend/agentqe/models/finding.py` - Finding model
- `backend/agentqe/models/risk.py` - Risk model
- `backend/agentqe/models/__init__.py` - Exports all models
- `PHASE0_ARCHITECTURE.md` - This document

### Modified
- `backend/agentqe/models/context.py` - Enhanced ApplicationContext
- `backend/agentqe/models/test_case.py` - Enhanced CandidateTest
- `backend/agentqe/models/execution.py` - Enhanced ExecutionResult
- `backend/app.py` - Ensure `/api/agentqe/*` routes registered cleanly

### Preserved (No Changes)
- All legacy `agents/*.py`
- All legacy API routes in `app.py`
- All frontend pages except AgentQE (which already exists)
- Database schema (no new tables)

---

*Document Version: 1.0*  
*Phase: 0 - Foundation & Architecture Preparation*  
*Date: 2026-09-25*