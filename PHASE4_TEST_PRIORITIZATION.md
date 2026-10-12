# Phase 4 — Test Enrichment + Transformer Prioritization

## 1. Objective

Phase 4 adds deterministic test enrichment and ranking to the AgentQE pipeline. Every `CandidateTest` produced by Phase 3 is enriched with contextual information from the Application Knowledge Model, then ranked using a deterministic bootstrap scoring system. A Transformer inference path is available for future trained weights.

## 2. Architecture

```
Phase 3 CandidateTests
        ↓
TestEnricher (enrichment/service.py)
        ↓ enriched CandidateTests with 15+ metadata fields
Phase4FeatureExtractor (prioritization/feature_extractor.py)
        ↓ 9 deterministic normalized features per test
TransformerRankerWrapper (prioritization/bootstrap_ranker.py)
        ↓ untrained → delegates to BootstrapRanker
BootstrapRanker (deterministic weighted sum)
        ↓ sorted RankedTest list with score + explanation
TestPrioritizationService (prioritization/service.py)
        ↓
POST /api/agentqe/tests/prioritize
        ↓
Frontend: "Test Prioritization" tab in AgentQE.jsx
```

## 3. Enrichment Inputs

The `TestEnricher` enriches each `CandidateTest` using:

| Source | Used for |
|--------|----------|
| `ApplicationKnowledgeModel.entities` | Resolving requirement/page/control/form/api/flow refs to known entities |
| `UnifiedApplicationModel.risk_areas` | Matching tests to risk areas by page/control overlap |
| `CandidateTest.steps` | Detecting destructive actions, data dependencies |
| `CandidateTest.api_refs` | Network dependency detection |
| `CandidateTest.page_refs` | Authentication dependency detection |

### Enriched Fields

- `enriched_requirements` — resolved requirement entities with observation status
- `enriched_pages` — resolved page entities with URL and page type
- `enriched_controls` — resolved control entities with interaction type
- `enriched_forms` — resolved form entities with fields and action
- `enriched_apis` — resolved API endpoint entities with method/path
- `enriched_flows` — resolved user flow entities with steps
- `available_modules` — modules from knowledge model
- `matched_risk_areas` — matched risk areas from unified model
- `enriched_evidence` — resolved evidence references
- `test_layer`, `test_perspective`, `source_agent` — test signals
- `requires_authentication`, `auth_pages` — auth dependency
- `action_severity` — destructive/read_only based on step keywords
- `data_dependency` — required/none based on step keywords
- `network_dependency` — required/none based on api_refs
- `estimated_complexity`, `complexity_tier` — execution complexity estimate
- `traceability_completeness`, `traceability_tier` — ref resolution fraction

### Observation Semantics

All enriched entities carry their original observation status (`observed` / `inferred` / `unknown`). Enrichment never upgrades a status. Unknown entities are recorded as `{"id": "<id>", "status": "unknown"}`.

### Enrichment Failure Isolation

If enrichment fails for one test, the error is recorded in `test.metadata["enrichment_error"]` and `test.metadata["enrichment_error_code"]`, but all other tests continue. The test remains in the pipeline with its original (unenriched) data.

## 4. Exact 9 Features

Feature version: `phase4-v1`

| # | Name | Calculation | Missing Data |
|---|------|-------------|--------------|
| 1 | `requirement_relevance` | Fraction of `requirement_refs` that resolve to known entities, weighted by priority (High=1.0, Medium=0.5, Low=0.2). If no refs → 0.0. If refs exist but no knowledge model → 0.5 (inferred). | → 0.0 |
| 2 | `risk_relevance` | Sum of severity weights for `matched_risk_areas` / max weight. Severity weights: Critical=1.0, High=0.8, Medium=0.5, Low=0.2. | → 0.0 |
| 3 | `coverage` | Normalized count of unique ref types. Pages ≤ 0.2, Controls ≤ 0.2, Forms ≤ 0.2, APIs ≤ 0.2, Flows ≤ 0.2. Max = 1.0. | → 0.0 |
| 4 | `api_relevance` | Per api_ref: base 0.5, +0.3 for observed failures, +0.2 for auth-required. Average over refs. No refs → 0.0. No knowledge model → 0.5. | → 0.0 |
| 5 | `execution_complexity` | 1 − normalized(steps × type_multiplier / 30). INVERTED: simpler = higher score. Type multipliers: UNIT=1, API=1.5, UI=2.5, INTEGRATION=3, SECURITY=3.5, PERFORMANCE=4. | → falls back to step count |
| 6 | `evidence_confidence` | Average confidence of `enriched_evidence` items. Confidence by status: observed=0.9, inferred=0.5, unknown=0.1. No evidence → 0.0. | → 0.0 |
| 7 | `cross_modal_evidence` | Count of unique modalities (dom, accessibility, visual, network) × 0.25. Max = 1.0. Modality hints from page_refs, control_refs, api_refs. | → 0.0 |
| 8 | `test_layer_signal` | Base by test_type: SECURITY=1.0, INTEGRATION=0.85, PERFORMANCE=0.8, API=0.65, UI=0.5, UNIT=0.3. +0.1 for ENGINEERING perspective. +0.15/0.05/0.0 for High/Medium/Low priority. | → 0.5 |
| 9 | `traceability_completeness` | Fraction of all refs (requirements+pages+controls+forms+apis+flows+evidence) that resolve to known entities. No refs → 0.0. No knowledge model → 0.5 (inferred). | → 0.0 |

## 5. Feature Normalization

All features are clipped to [0, 1] after calculation. No feature can be < 0 or > 1. Normalization is applied in `Phase4FeatureExtractor.extract()` as a final step.

## 6. Bootstrap Scoring Formula

```
bootstrap_score =
  w1 × requirement_relevance
+ w2 × risk_relevance
+ w3 × coverage
+ w4 × api_relevance
+ w5 × execution_complexity
+ w6 × evidence_confidence
+ w7 × cross_modal_evidence
+ w8 × test_layer_signal
+ w9 × traceability_completeness
```

## 7. Bootstrap Weights

These weights are **not learned**. They are heuristic defaults.

| Feature | Weight | Rationale |
|---------|--------|-----------|
| `requirement_relevance` | 0.20 | Tests covering requirements are most critical |
| `risk_relevance` | 0.15 | Tests covering risk areas prevent high-severity bugs |
| `coverage` | 0.10 | Broad coverage is good but not everything |
| `api_relevance` | 0.10 | API tests catch integration issues |
| `execution_complexity` | 0.10 | Prefer simpler tests for faster feedback |
| `evidence_confidence` | 0.10 | Well-evidenced tests are more reliable |
| `cross_modal_evidence` | 0.05 | Nice to have but not essential |
| `test_layer_signal` | 0.10 | Security/integration tests prioritized |
| `traceability_completeness` | 0.10 | Traceable tests are maintainable |
| **Sum** | **1.00** | |

Weights are validated at class instantiation. Any custom `RankingWeights` with sum ≠ 1.0 or length ≠ 9 will raise `ValueError`.

## 8. Transformer Architecture

File: `backend/agentqe/ml/transformer_ranker.py`

```
Input: 9-dimensional feature vector
  ↓ Linear(9 → 64)
  ↓ TransformerEncoder(d_model=64, nhead=4, num_layers=2, batch_first=True)
  ↓ mean pooling over sequence dimension
  ↓ Linear(64 → 32) → ReLU → Linear(32 → 1)
Output: priority score
```

## 9. Trained vs Untrained Behavior

### Untrained (current state)

- `ranking_mode = "bootstrap"`
- `model_status = "untrained"`
- Bootstrap deterministic scoring is used
- Random/untrained Transformer weights are **never** used as meaningful scores
- The UI clearly displays "Deterministic Bootstrap Ranking"

### Trained (future)

When trained weights are loaded via `TransformerRankerWrapper.load_transformer(model_path)`:
- `ranking_mode = "transformer"`
- `model_status = "trained"`
- Transformer inference is used for scoring
- This path is available but currently dormant because no training data exists yet

Training data will come from Phase 5 execution history (actual test outcomes + pass/fail labels).

## 10. Ranking Metadata

Every result includes:

```json
{
  "ranking_mode": "bootstrap",
  "model_status": "untrained",
  "model_version": "phase4-v1",
  "feature_version": "phase4-v1"
}
```

The metadata is honest about current state. No fabricated training metrics.

## 11. Explainability

Every `RankedTest` includes:
- `explanation` — human-readable string listing top contributing features
- `feature_contributions` — machine-readable `{feature_name: contribution}` dict

Example explanation:
> "High priority because the test covers high-priority requirements, targets identified risk areas, is fast to execute."

Explanations are derived from actual feature values. No attention-based explanations are claimed.

## 12. Ranked Test Model

`RankedTest` fields:
- `test` — original `CandidateTest` (with enrichment in metadata)
- `feature_vector` — `FeatureVector(feature_names, feature_values, feature_version)`
- `bootstrap_score` — weighted sum score
- `rank` — 1-indexed position (1 = highest priority)
- `ranking_mode` — "bootstrap" or "transformer"
- `model_status` — "trained" or "untrained"
- `model_version` — version string
- `explanation` — human-readable explanation
- `feature_contributions` — per-feature contributions

## 13. API

### POST /api/agentqe/tests/prioritize

Requires JWT authentication.

**Request body:**
```json
{
  "candidate_tests": [
    {
      "test_id": "TC-001",
      "title": "...",
      "test_type": "UI",
      "priority": "High",
      ...
    }
  ],
  "application_context": { ... },     // optional
  "knowledge_model": { ... },          // optional
  "unified_model": { ... },            // optional
  "rag_context": { ... },              // optional
  "execution_history": { ... },        // optional
  "repository_data": { ... }           // optional
}
```

**Response (200):**
```json
{
  "success": true,
  "ranked_tests": [...],
  "enrichment_summary": {
    "total": 10,
    "enriched": 9,
    "failed": 1
  },
  "ranking_metadata": {
    "ranking_mode": "bootstrap",
    "model_status": "untrained",
    "model_version": "phase4-v1",
    "feature_version": "phase4-v1"
  }
}
```

**Error responses:**
- `401` — missing or invalid JWT
- `400` — `candidate_tests` not provided
- `500` — unhandled service error

### GET /api/agentqe/application/query

Returns `405 Method Not Allowed`. This endpoint is POST-only.

### POST /api/agentqe/application/query

Requires JWT authentication.

**Request body:**
```json
{
  "query": "login authentication",
  "top_k": 5
}
```

**Error responses:**
- `401` — missing or invalid JWT
- `400` — `query` field missing, or RAG index not ready
- `405` — GET method used

## 14. Frontend

The Phase 4 UI is integrated into the existing `AgentQE.jsx` page as the "Test Prioritization" tab.

Features:
- Shows ranking mode badge ("Deterministic Bootstrap Ranking" when untrained)
- Shows model version and feature version
- Summary stats: total tests, enriched count, failed enrichment, ranking mode
- Ranked test table with: rank, test ID, title, layer, source agent, score, explanation
- Feature contributions detail for top 3 tests (visual bar display)
- Bootstrap weights reference table
- Prioritize Tests button (requires tests from Test Generation tab first)

## 15. Tests

### Phase 4 Tests (tests/test_agentqe_phase4.py)

- 9 feature extractor tests (exact count, names, normalization, determinism, individual features)
- 7 bootstrap ranker tests (weights, determinism, ranking mode, explanation, contributions)
- 3 enrichment tests (observation semantics, failure isolation, added fields)
- 4 prioritization service tests (empty list, metadata, ranking metadata, determinism)
- 3 API tests (auth, missing input, success structure)

### API Tests (tests/test_agentqe_api.py)

- 4 RAG query tests (GET→405, unauthenticated→401, malformed→400, valid)
- 5 test generation tests (auth, missing context, success, partial failure, complete failure)
- 3 Groq model configuration tests (centralized config, both generators same, no stale refs)
- 2 prioritization endpoint tests (auth, missing input)

## 16. Groq Model Configuration Fix

**Issue:** `llama-3.1-70b-versatile` was decommissioned by Groq.

**Resolution:**
- Centralized in `backend/agentqe/generation/config.py`
- Default: `llama-3.1-8b-instant` (currently supported)
- Override via env var: `AGENTQE_GROQ_MODEL`
- Both `UserTestGenerator` and `EngineeringTestGenerator` use `GroqTestGenerationModel` which reads from this central config
- No stale hardcoded model references remain in production code
- Generation errors are structured (`MODEL_DECOMMISSIONED`, `BAD_REQUEST`, `RATE_LIMITED`, etc.)

## 17. RAG Query Authentication / Validation

- `GET /api/agentqe/application/query` → `405` (POST-only, by Flask design)
- `POST` without JWT → `401`
- `POST` with valid JWT but missing `query` field → `400` with `"Query is required"`
- `POST` with valid JWT but RAG index not ready → `400` with `"RAG index is not ready"`
- `POST` valid → `200` with `results` array of `RetrievalResult` dicts

Authentication is never disabled. JWT secret comes from `SECRET_KEY` env var.

## 18. Generation Error Handling

| Scenario | HTTP Status | `status` field |
|----------|-------------|----------------|
| Both generators succeed | `200` | `"success"` |
| One generator succeeds | `207` | `"partial_failure"` |
| Both generators fail | `500` | `"failed"` |

The `generators` array in the response always shows per-agent status. API keys, JWTs, and stack traces are never included in error responses.

## 19. Known Limitations

1. Transformer has no trained weights. Bootstrap ranking is deterministic but not learned from historical outcomes.
2. `cross_modal_evidence` is partially estimated from ref types when no explicit evidence modality is recorded.
3. `matched_risk_areas` matching is by page/control set intersection. More sophisticated NLP matching is not implemented.
4. `evidence_confidence` returns 0.0 when no enriched_evidence metadata exists (unknown).
5. `CrawlConfig.max_pages` default changed from 20 to 3 in the crawler; a pre-existing Phase 1.5 test (`TestCrawlConfig::test_defaults`) reflects this change — not introduced by Phase 4.

## 20. Future Transformer Training Path

1. Phase 5 executes the ranked tests via Playwright
2. Execution results (pass/fail, error type, timing) are collected as `ExecutionResult` objects
3. Feature vectors + labels are accumulated as historical training data
4. A training script (not yet implemented) trains `TransformerTestRanker` on this data
5. Trained weights saved to `models/transformer_ranker.pt`
6. `TransformerRankerWrapper.load_transformer("models/transformer_ranker.pt")` loads them
7. `ranking_mode` switches to `"transformer"`, `model_status` to `"trained"`
8. The bootstrap ranker remains as fallback if weights fail to load

## 21. Relationship to Phase 5

Phase 4 output (`ranked_tests` sorted by priority) feeds directly into Phase 5 test execution. Phase 5 will:
- Execute tests in priority order
- Collect `ExecutionResult` objects
- Use execution history to improve Phase 4 rankings in future runs
