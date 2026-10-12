# Phase 4.5: Synthetic Training Data Generation and Transformer Training

## Overview

Phase 4.5 implements a synthetic data generation and Transformer training pipeline to bootstrap the AgentQE test prioritization model. This approach allows us to train the Transformer architecture without requiring real-world execution history, which will be collected in later phases (Phase 5/6).

## Why Synthetic Data?

The Transformer architecture for test prioritization exists, but there is currently no trained `transformer_ranker.pt`. We do not yet have enough real AgentQE execution history to train the model. Due to project time constraints, we bootstrap the Transformer using a synthetic but domain-constrained training dataset.

**Important:** The synthetic dataset is designed as **bootstrap data**, not as fake real-world evidence. Later, Phase 5/6 real execution data will be collected and used to retrain/fine-tune the model.

## The 9 Phase 4 Features

The synthetic generator uses the exact 9 features from Phase 4:

1. **requirement_relevance** - How directly the test exercises a stated requirement
2. **risk_relevance** - How strongly the test relates to a risk-prone area
3. **coverage** - How much meaningful application behavior the test covers
4. **api_relevance** - How strongly the test exercises API/backend behavior
5. **execution_complexity** - Execution cost/complexity (higher = more complex, penalized in prioritization)
6. **evidence_confidence** - Strength/reliability of supporting application evidence
7. **cross_modal_evidence** - Strength of agreement between DOM, accessibility, visual, network, semantic, etc.
8. **test_layer_signal** - How strongly the test's layer is appropriate for the scenario
9. **traceability_completeness** - How completely the test maps to requirements, entities, evidence, etc.

All features are normalized to [0,1].

## Synthetic Scenario Distribution

The generator creates 18 realistic software-testing scenarios with meaningful feature correlations:

### High Priority Scenarios
- **high_risk_api_regression** - High risk + high API relevance
- **authentication_security_flow** - Security-sensitive authentication tests
- **high_value_api_integration** - Critical API integration tests
- **core_user_journey** - Core user workflow tests
- **high_requirement_coverage** - Tests covering high-priority requirements

### Medium Priority Scenarios
- **high_evidence_confidence** - Tests with strong supporting evidence
- **cross_modal_ui_test** - UI tests with cross-modal evidence
- **high_coverage_regression** - Broad coverage regression tests
- **business_critical_workflow** - Business-critical workflow tests
- **edge_case_test** - Edge case and boundary tests
- **negative_error_handling** - Error handling and negative tests
- **performance_sensitive** - Performance-sensitive tests

### Low Priority Scenarios
- **low_risk_smoke_test** - Low-risk smoke tests
- **low_value_duplicate** - Low-value duplicate-like tests
- **expensive_complex_test** - Expensive/complex tests
- **weakly_traceable_test** - Tests with weak traceability
- **low_evidence_exploratory** - Low-evidence exploratory tests
- **low_priority_cosmetic** - Cosmetic/UI-only tests

Each scenario imposes sensible correlations between the nine features. For example:
- **HIGH PRIORITY**: high requirement relevance + high risk relevance + strong coverage + strong evidence + good traceability + reasonable execution complexity
- **LOW PRIORITY**: low requirement relevance + low risk + weak evidence + weak traceability + low coverage

## Target Generation

Priority targets are generated using a deterministic synthetic scoring function representing test-prioritization value. The target is influenced by the 9 features but includes realistic nonlinear interactions.

### Target Formula

```
target = base + interactions + scenario_boost + noise
```

Where:
- **base**: Weighted sum with adjusted weights (slightly different from bootstrap to avoid duplication)
- **interactions**: Nonlinear feature interactions:
  - High risk + high requirement relevance interaction
  - Strong evidence + high traceability interaction
  - Coverage diminishing returns (log-like)
  - API relevance boost for API tests
  - Cross-modal evidence boost for UI tests
  - Extremely high execution complexity penalty
- **scenario_boost**: Scenario-specific adjustment (+0.20 for security, -0.18 for cosmetic, etc.)
- **noise**: Small bounded noise [-0.02, 0.02]

The target remains in [0,1] through clipping.

**Important:** The target is a synthetic supervisory signal, NOT a claim that this is the true optimal ranking formula for real software projects.

## Dataset Size

Default: **10,000 synthetic examples**

Configurable via environment variable:
```bash
export AGENTQE_SYNTHETIC_DATASET_SIZE=10000
```

Supported sizes: 1,000, 5,000, 10,000, 25,000, 50,000

## Deterministic Seed

Default seed: **42**

Configurable via environment variable:
```bash
export AGENTQE_SYNTHETIC_SEED=42
```

The seed ensures reproducibility:
- Same seed → identical dataset
- Different seed → different dataset

## Train/Validation/Test Split

- **Training**: 70%
- **Validation**: 15%
- **Test**: 15%

The split is **scenario-aware** to avoid leakage:
- Examples from the same scenario are kept together in one split
- This prevents near-duplicates across train and test
- Split is deterministic for a given seed

## Transformer Architecture

The existing Transformer architecture is reused without modification:

```
9 input features (batch_size, 1, 9)
→ Linear(9 → 64)
→ Transformer Encoder
   - d_model = 64
   - nhead = 4
   - num_layers = 2
   - batch_first = True
→ Mean pooling over sequence dimension
→ Linear(64 → 32)
→ ReLU
→ Linear(32 → 1)
→ priority score (batch_size,)
```

**Tensor Shapes:**
- Input: (batch_size, 1, 9)
- After projection: (batch_size, 1, 64)
- After encoder: (batch_size, 1, 64)
- After pooling: (batch_size, 64)
- After ranking head: (batch_size, 1)
- Final output: (batch_size,)

The 9 features are treated as a coherent vector (sequence length 1), which is appropriate since they represent a single test's feature vector. The Transformer can still learn nonlinear feature interactions through self-attention.

## Training Configuration

Default hyperparameters:

- **Loss function**: MSELoss (configurable: SmoothL1Loss)
- **Optimizer**: Adam
- **Learning rate**: 0.001
- **Weight decay**: 1e-5
- **Batch size**: 32
- **Epochs**: 30
- **Early stopping patience**: 5
- **Early stopping min delta**: 1e-4
- **Device**: CPU (auto-detects CUDA if available)

Configurable via CLI arguments or environment variables.

## Evaluation Metrics

The evaluator computes both regression and ranking-specific metrics:

### Regression Metrics
- **MSE** (Mean Squared Error)
- **MAE** (Mean Absolute Error)

### Rank Correlation Metrics
- **Spearman rank correlation**
- **Kendall Tau rank correlation**

### Top-k Overlap Metrics
- **Top 10% overlap** (Jaccard similarity between top 10% of predicted vs target rankings)
- **Top 20% overlap**
- **Top 30% overlap**

### Baseline Comparison
- **Bootstrap Spearman** - Rank correlation of bootstrap weights against synthetic targets
- **Bootstrap Kendall** - Kendall correlation of bootstrap weights against synthetic targets

The goal is to determine whether the model learns the ordering, not merely numeric regression.

## Model Artifacts

### Model Checkpoint
**Location**: `backend/agentqe/models/transformer_ranker.pt`

Contains the trained Transformer state dict.

### Metadata
**Location**: `backend/agentqe/models/transformer_ranker_metadata.json`

Contains:
- model_version
- training_data_type
- feature_count
- features (list of 9 feature names)
- dataset_size
- seed
- train/val/test split sizes
- architecture details
- training hyperparameters
- final train/val/test losses
- training timestamp
- device used

### Dataset (Optional)
**Location**: `backend/data/agentqe/training/synthetic_ranker_dataset.jsonl`

JSONL format with one example per line. Can be regenerated from seed.

## How to Train

### Basic Training

```bash
cd backend
python -m agentqe.training.trainer
```

### With Custom Parameters

```bash
python -m agentqe.training.trainer \
    --dataset-size 10000 \
    --seed 42 \
    --epochs 30 \
    --batch-size 32 \
    --learning-rate 0.001 \
    --device auto
```

### Environment Variables

```bash
export AGENTQE_SYNTHETIC_DATASET_SIZE=10000
export AGENTQE_SYNTHETIC_SEED=42
python -m agentqe.training.trainer
```

### Dataset Generation Only

```bash
python -m agentqe.training.synthetic_generator
```

This generates a persisted dataset at `backend/data/agentqe/training/synthetic_ranker_dataset.jsonl`.

## How the Trained Model is Loaded

The `TransformerRankerWrapper` in `bootstrap_ranker.py` automatically attempts to load the trained model on initialization:

1. Checks multiple default paths for `transformer_ranker.pt`
2. Validates model architecture (input_dim=9, d_model=64)
3. Loads metadata if available
4. Sets `ranking_mode = "transformer"` and `model_status = "trained"`

If loading fails (missing file, incompatible architecture, etc.), the wrapper safely falls back to bootstrap ranking.

## Bootstrap Fallback

When the trained model is unavailable or loading fails:

- `ranking_mode = "bootstrap"`
- `model_status = "untrained"`
- Uses deterministic weighted sum of 9 features
- Bootstrap weights (sum to 1.0):
  - requirement_relevance: 0.20
  - risk_relevance: 0.15
  - coverage: 0.10
  - api_relevance: 0.10
  - execution_complexity: 0.10
  - evidence_confidence: 0.10
  - cross_modal_evidence: 0.05
  - test_layer_signal: 0.10
  - traceability_completeness: 0.10

The fallback is deterministic and never uses random weights.

## Future Real-Data Training Design

### Phase 5: Real Test Execution
- Collect actual test execution history
- Record execution results, duration, failures

### Phase 6: Failure Analysis
- Collect defect/finding information
- Record severity, risk, novelty, coverage
- Identify tests that discovered meaningful defects

### Phase 6+: Retraining/Fine-Tuning
- Combine synthetic bootstrap data + real AgentQE execution data
- Retrain/fine-tune the Transformer
- Model version: `agentqe-transformer-real-v2`

Eventually, real data should dominate training. The model architecture is designed to make replacing the synthetic dataset straightforward.

### Dataset Schema Compatibility

The dataset schema is designed to support both synthetic and real data:

**Synthetic Dataset:**
- 9 features (synthetic)
- priority_target (synthetic)
- scenario (synthetic category)
- test_layer (synthetic)

**Real Execution Dataset (future):**
- 9 features (from Phase4FeatureExtractor)
- execution_result (pass/fail)
- execution_duration
- failure_information
- defect_severity
- risk
- novelty
- coverage
- discovered_defect (boolean)

Both can feed the same training pipeline through a common dataset abstraction.

## Limitations

1. **Synthetic targets are not real-world truth** - The synthetic priority targets are a supervisory signal for training, not evidence of real-world prioritization performance.

2. **Scenario coverage is limited** - The 18 scenarios cover common patterns but may not represent all real-world testing situations.

3. **Feature correlations are simplified** - Real-world feature interactions are more complex than the synthetic correlations.

4. **No execution history** - The synthetic data does not include actual execution results, which will be critical for real-world prioritization.

5. **Bootstrap data only** - This is intended as a temporary bootstrap. Real execution data from Phase 5/6 will be necessary for production-quality prioritization.

6. **No external validation** - The model is evaluated against synthetic targets, not against real human expert rankings or actual defect discovery rates.

## Testing

Comprehensive tests are in `backend/tests/test_agentqe_training.py`:

1. Synthetic generator produces requested number of examples
2. Same seed produces identical dataset
3. Different seed produces different dataset
4. All 9 features exist
5. All features are [0,1]
6. Targets are [0,1]
7. Scenario distribution is valid
8. Target generation is deterministic for fixed seed
9. Train/validation/test split sizes are correct
10. No split leakage (scenario-aware splitting)
11. Dataset tensors have correct dimensions
12. Transformer forward pass works
13. Training completes on CPU
14. Model checkpoint is saved
15. Metadata is saved
16. Saved model can be loaded
17. TransformerRankerWrapper detects trained model
18. ranking_mode becomes "transformer"
19. Missing/corrupt model falls back to bootstrap
20. Existing Phase 4 tests continue to pass
21. Legacy AutoQA tests continue to pass

Run tests:
```bash
cd backend
pytest tests/test_agentqe_training.py -v
```

## No External Dependencies

This implementation:
- Does NOT require an external LLM API
- Does NOT require external datasets
- Does NOT require GPU (CPU training supported)
- Does NOT modify legacy AutoQA behavior
- Does NOT introduce LangGraph, Browser Use, or LlamaIndex changes
- Does NOT change Phase 1/1.5 evidence models

## Acceptance Criteria

- [x] Existing Phase 4 tests pass
- [x] Synthetic dataset can be generated offline
- [x] 10,000 examples can be generated quickly
- [x] Dataset is reproducible with seed 42
- [x] All examples contain exactly 9 features
- [x] Features are normalized [0,1]
- [x] Targets are [0,1]
- [x] Targets are meaningful and not random
- [x] Dataset splits are deterministic
- [x] Existing Transformer architecture is reused/verified
- [x] Transformer trains successfully on CPU
- [x] transformer_ranker.pt is produced
- [x] metadata JSON is produced
- [x] Evaluation metrics are produced
- [x] TransformerRankerWrapper loads the model
- [x] ranking_mode changes to "transformer" when trained weights exist
- [x] Bootstrap fallback still works
- [x] Existing API behavior is preserved
- [x] Legacy AutoQA remains untouched
- [x] No external API is required
- [x] No external dataset is required
- [x] Documentation is added
- [x] Tests are added and passing
