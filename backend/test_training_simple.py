"""
Simple test runner for training module without conftest dependencies.
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from agentqe.training.config import TrainingConfig
from agentqe.training.synthetic_generator import SyntheticDataGenerator
from agentqe.training.dataset import RankerDataset, DatasetManager
from agentqe.training.trainer import TransformerTrainer
from agentqe.training.evaluator import RankerEvaluator
from agentqe.prioritization.bootstrap_ranker import TransformerRankerWrapper

def test_config():
    print("Testing TrainingConfig...")
    config = TrainingConfig()
    assert config.dataset_size == 10000
    assert config.seed == 42
    assert len(config.feature_names) == 9
    print("✓ TrainingConfig OK")

def test_generator():
    print("Testing SyntheticDataGenerator...")
    gen = SyntheticDataGenerator(seed=42)
    examples = gen.generate(100)
    assert len(examples) == 100
    for ex in examples:
        assert len(ex.features) == 9
        assert 0.0 <= ex.priority_target <= 1.0
    print("✓ SyntheticDataGenerator OK")

def test_dataset():
    print("Testing RankerDataset...")
    gen = SyntheticDataGenerator(seed=42)
    examples = gen.generate(50)
    dataset = RankerDataset(examples)
    assert len(dataset) == 50
    features, target = dataset[0]
    assert features.shape[0] == 9
    print("✓ RankerDataset OK")

def test_dataset_manager():
    print("Testing DatasetManager...")
    config = TrainingConfig(dataset_size=1000, seed=42)
    manager = DatasetManager(config)
    split = manager.generate_and_split()
    total = len(split.train) + len(split.val) + len(split.test)
    assert total == 1000
    print("✓ DatasetManager OK")

def test_model_loading():
    print("Testing TransformerRankerWrapper model loading...")
    wrapper = TransformerRankerWrapper()
    # Should attempt to load the trained model
    print(f"  ranking_mode: {wrapper.ranking_mode}")
    print(f"  model_status: {wrapper.model_status}")
    print("✓ TransformerRankerWrapper OK")

def test_metadata_file():
    print("Testing metadata file exists...")
    import os
    metadata_path = "backend/agentqe/models/transformer_ranker_metadata.json"
    model_path = "backend/agentqe/models/transformer_ranker.pt"
    assert os.path.exists(model_path), f"Model not found at {model_path}"
    assert os.path.exists(metadata_path), f"Metadata not found at {metadata_path}"
    print("✓ Model artifacts exist")

if __name__ == "__main__":
    print("Running simple training tests...\n")
    try:
        test_config()
        test_generator()
        test_dataset()
        test_dataset_manager()
        test_metadata_file()
        test_model_loading()
        print("\n✅ All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
