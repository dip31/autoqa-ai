# AutoQA AI — Current Project State

## 1. Purpose

AutoQA AI is a web-based QA automation platform. It combines a React frontend, a Flask/Python backend, browser-based website analysis, AI-assisted test generation, test execution, risk analysis, code review, reporting, and GitHub-related functionality.

The project currently contains an AgentQE pipeline for understanding a target application, generating candidate tests, ranking them, executing selected tests, analyzing failures, and storing execution results.

This document describes the current implementation **before adding a dedicated security-validation layer**.

## 2. Technology Stack

### Backend

- Python
- Flask 3+
- Flask-CORS
- Flask-JWT-Extended
- Bcrypt
- SQLite for local development
- MySQL/Cloud SQL support when `DB_HOST` points to a non-localhost host
- Playwright for browser automation and crawling
- Requests and HTTPX for HTTP integrations
- Groq and other AI-related integrations used by agents
- NumPy, scikit-learn, and PyTorch for ranking/ML-related functionality
- Gunicorn for deployment

Primary dependency file:

- `backend/requirements.txt`

### Frontend

- React 18
- React Router 6
- Axios
- Tailwind CSS-related UI
- Chart.js and `react-chartjs-2`
- Mermaid diagrams
- jsPDF and autoTable for report export
- `html2canvas`
- `xlsx`

Primary dependency file:

- `frontend/package.json`

## 3. High-Level Architecture

```text
React frontend
      |
      | HTTP/JSON + JWT Authorization header
      v
Flask API backend
      |
      +-- Authentication and GitHub OAuth
      +-- AI/QA agents
      +-- AgentQE pipeline
      +-- Playwright browser automation
      +-- Database repository/query layer
      |
      v
SQLite locally or MySQL/Cloud SQL in configured deployments
```

The frontend is protected by a React authentication context. The backend protects most application features with JWT requirements.

## 4. Backend API

The main Flask application is:

- `backend/app.py`

Current API areas include:

### Authentication

- `POST /auth/register`
- `POST /auth/login`
- `GET /auth/me`
- GitHub OAuth login and callback routes

### Chat and collaboration

- Chat session creation, listing, and deletion
- Chat message creation and retrieval
- Team messages and unread-count routes

### QA and AI features

- `POST /review-testcase`
- `POST /review-code`
- `POST /website-test`
- `POST /generate-testcase`
- `POST /predict-risk`
- `GET /generate-report`
- `POST /generate-report-image`

### Autonomous QA

- `POST /api/autonomous-qa/run`
- `GET /api/autonomous-qa/runs`
- `GET /api/autonomous-qa/run/<run_id>`

### Developer features

- Developer project CRUD routes
- Diagram generation
- Code generation/review
- Developer risk analysis

### AgentQE

- `POST /api/agentqe/run`
- `POST /api/agentqe/review/<run_id>`
- `POST /api/agentqe/application/understand`
- `POST /api/agentqe/tests/generate`

There is currently **no dedicated security validation API endpoint** such as `/api/agentqe/security/validate`.

## 5. Authentication and Current Security-Related Controls

### Passwords

User passwords are hashed with Bcrypt during registration. Login verifies the supplied password with Bcrypt rather than comparing plaintext values.

Relevant implementation:

- `backend/app.py`

### JWT authentication

The backend uses Flask-JWT-Extended. Access tokens are created during regular login, registration, and GitHub OAuth completion.

Most protected API routes use `@jwt_required()`.

The current access-token lifetime is configured in the Flask application.

### Frontend token handling

The frontend stores the JWT in browser `localStorage` and attaches it to API requests through Axios.

Relevant files:

- `frontend/src/api/client.js`
- `frontend/src/context/AuthContext.jsx`

This is functional for the current application, but it is a security trade-off because JavaScript-accessible tokens can be exposed if the frontend has an XSS issue. A future hardening phase could move authentication to Secure, HttpOnly cookies.

### GitHub OAuth

The application supports GitHub OAuth and stores GitHub-related identity information. The database schema includes a `github_token` field.

Relevant files:

- `backend/app.py`
- `backend/database/init_db.py`

The current codebase does not yet provide a dedicated encryption-at-rest layer for stored GitHub tokens.

### CORS

Flask-CORS is enabled in the Flask application. The current configuration is broad and should be reviewed before production deployment.

## 6. Database and Persistence

The database abstraction is:

- `backend/database/db.py`

Database behavior:

- Uses SQLite when `DB_HOST` is absent or set to `localhost`.
- Uses MySQL when `DB_HOST` points to another host.
- Uses parameterized query placeholders and converts SQLite-style placeholders for MySQL.

The local database file is created under the backend database directory.

The schema includes tables for areas such as:

- Users
- Chat sessions and messages
- Test cases
- Code reviews
- Website tests
- Autonomous QA runs
- Autonomous execution logs
- AgentQE scope and review data

The schema initialization code is:

- `backend/database/init_db.py`

## 7. AgentQE Pipeline

The primary AgentQE orchestration code is:

- `backend/agentqe/pipeline.py`

The current pipeline is intended to perform the following stages:

1. Load the autonomous QA run.
2. Create an application context.
3. Generate a test strategy.
4. Crawl and analyze the target application.
5. Generate user-focused test cases with selectors.
6. Generate engineering-focused tests.
7. Merge and deduplicate candidate tests.
8. Enrich tests with risk, cost, history, and change-impact metadata.
9. Rank tests with the ML/transformer ranking components.
10. Select tests within the execution budget.
11. Execute selected tests through the existing browser execution pipeline.
12. Analyze failures.
13. Perform adaptive quality evaluation.
14. Store logs, reviews, and results.

The pipeline currently uses the legacy `_crawl_page()` call in its main run path for the crawl-and-generate stage. The newer multi-page `ApplicationCrawler` is used by the application-understanding capability and is available as a richer crawl implementation.

## 8. AgentQE Capability Contracts

The AgentQE interfaces and data contracts are defined in:

- `backend/agentqe/interfaces/__init__.py`

Important data models include:

- `ApplicationContext`
- `CandidateTest`
- `ExecutionResult`
- `Finding`
- `Risk`

The interface file already declares:

```python
class ISecurityValidator(ABC):
    def validate(
        self,
        context: ApplicationContext,
        tests: List[CandidateTest]
    ) -> List[Finding]:
        ...
```

This means the project has a planned extension point for security validation. However:

- No concrete security-validator implementation is currently present.
- No security validator is registered in the capability registry.
- The main AgentQE pipeline does not currently execute security validation as a separate stage.
- Existing `Finding` and `ExecutionResult` models have fields that can support security-related findings, but they are not yet a complete security-reporting system.

## 9. Application Understanding and Crawling

The application-understanding implementation is:

- `backend/agentqe/agents/application_understanding_agent.py`

It accepts a target URL, repository URL, requirement text, module name, and optional crawl configuration.

### Primary multi-page crawler

The bounded crawler is:

- `backend/agentqe/crawler/application_crawler.py`

It uses Python Playwright with a headless Chromium browser and a single browser context for the crawl.

The crawler uses breadth-first traversal with hard limits for:

- Maximum pages
- Maximum depth
- Overall crawl timeout
- Per-page navigation timeout
- Same-domain-only traversal

It discovers and structures:

- Page titles
- Page types
- Links and navigation edges
- Forms
- Inputs
- Buttons
- Main text and content summaries
- Login/search/cart/product indicators
- DOM information
- Accessibility tree information
- Network activity and observed API endpoints
- Screenshot metadata

Configuration is defined in:

- `backend/agentqe/crawler/crawl_config.py`

Result structures are defined in:

- `backend/agentqe/crawler/crawl_result.py`

### Legacy single-page crawler

The codebase also contains a legacy `_crawl_page()` implementation in:

- `backend/agents/autonomous_agent.py`

The main AgentQE pipeline currently calls this legacy path during its crawl-and-generate stage. The application-understanding agent calls the bounded multi-page crawler and falls back to the legacy single-page crawler if the newer crawler is unavailable or fails.

### Visual understanding

The crawler can capture viewport or full-page screenshots. The screenshots are stored as visual evidence.

The current project does **not** use:

- OmniParser
- A dedicated visual UI parser
- Screenshot-to-element grounding
- AI-based visual layout interpretation

The current UI understanding is primarily DOM-, accessibility-, text-, and network-based.

## 10. Test Generation, Ranking, and Execution

### Test generation

The project generates tests from requirements and crawled application data. Tests can contain:

- Test ID
- Title
- Description/objective
- Category
- Priority
- Steps
- Input data
- Expected result
- Automatable flag
- Selector
- Browser action

### Candidate pooling

Candidate tests from different perspectives are merged and deduplicated through:

- `backend/agentqe/pool/candidate_pool.py`

### Enrichment and ranking

Tests can be enriched with:

- Risk score
- Execution cost
- Historical pass/failure rate
- Change impact
- Coverage gain

Relevant components include:

- `backend/agentqe/enrichment/enricher.py`
- `backend/agentqe/ml/features.py`
- `backend/agentqe/ml/inference.py`
- `backend/agentqe/ml/transformer_ranker.py`

### Browser execution

Playwright is also used for executing generated UI tests. The adapter is:

- `backend/agentqe/execution/playwright_adapter.py`

The existing execution pipeline supports browser creation, actions, screenshots, and failure handling/self-healing behavior through the autonomous-agent implementation.

## 11. Frontend

The frontend entry point is:

- `frontend/src/App.jsx`

Current authenticated pages include:

- Dashboard
- Test case review
- Code review
- Website testing
- Test generator
- Risk prediction
- Smart report
- AgentQE
- Autonomous QA
- GitHub intelligence
- Messages

Authentication pages include:

- Login
- Register

The frontend uses:

- `AuthContext` for user/token state
- Axios client interceptors for JWT headers and unauthorized handling
- React Router for navigation
- Protected layout routing for authenticated pages

## 12. Existing Tests

The backend contains tests for AgentQE functionality, including:

- Crawler behavior with mocked Playwright
- URL normalization
- Page classification
- Application understanding
- AgentQE phase behavior
- Test generation and execution-related models

Important test files include:

- `backend/tests/test_agentqe_phase15a.py`
- `backend/tests/test_application_understanding.py`
- `backend/tests/test_agentqe_phase2.py`

The crawler tests mock Playwright and do not require live network calls for their unit-test scenarios.

## 13. Current Security Validation Status

The current project has basic application security controls, but it does not yet have a dedicated security-testing layer.

### Present today

- Bcrypt password hashing
- JWT-protected API routes
- Parameterized database queries in the database access layer
- Local/remote database separation behavior
- Existing `Finding` model
- Existing `ISecurityValidator` interface
- Browser-based application crawling
- Screenshot and accessibility evidence

### Not present today

- Dedicated AgentQE security-validation runner
- Target allowlist for security checks
- Safe attack simulation configuration
- Security-specific finding categories and evidence model
- Security headers/cookie validation
- Authorization boundary validation
- Bounded reflected-input/injection indicator checks
- Rate-limit validation
- TLS validation report
- Security findings dashboard or dedicated endpoint
- Authenticated encryption for stored GitHub tokens
- Automated security regression suite
- Formal security report export

## 14. Current Limitations and Technical Debt

1. The root README describes an older project structure and older setup assumptions. The implementation contains a larger AgentQE architecture than the README currently documents.
2. The README describes MySQL as the main setup path, while the current database layer defaults to SQLite for local development.
3. The main AgentQE pipeline and the newer application-understanding capability do not yet use one unified crawler path.
4. Screenshot capture exists, but screenshot visual interpretation is not implemented.
5. OmniParser is not installed or integrated.
6. The security-validator interface exists without an active implementation.
7. The JWT configuration contains a development fallback secret and should be hardened before production use.
8. Frontend JWT storage in `localStorage` is convenient but has XSS exposure.
9. GitHub token storage requires a deliberate secret-protection strategy.
10. CORS configuration should be narrowed for production deployment.
11. Security checks must be restricted to explicitly authorized targets before any attack-simulation feature is added.

## 15. Recommended Next Planning Step

Before implementation, define a security-validation design that:

1. Uses the existing `ISecurityValidator` and `Finding` contracts where appropriate.
2. Adds a bounded security runner under `backend/agentqe/security/`.
3. Restricts execution to approved local or lab targets.
4. Runs only non-destructive checks.
5. Produces reproducible evidence and severity/confidence values.
6. Integrates with AgentQE as a separate stage rather than mixing security logic into crawling.
7. Adds a dedicated API endpoint only after the security report schema and safety policy are agreed.
8. Demonstrates secure cryptography practices using standard algorithms rather than custom encryption.

