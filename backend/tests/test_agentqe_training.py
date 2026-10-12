"""
Phase 4.5 — Synthetic Training Data Generation and Transformer Training Tests.

Tests for synthetic data generation, dataset management, training, and evaluation.
"""

import pytest
import numpy as np
import torch
import os
import json
import tempfile
import shutil
from unittest.mock import patch, MagicMock

from agentqe.training.config import TrainingConfig
from agentqe.training.synthetic_generator import SyntheticDataGenerator, SyntheticExample
from agentqe.training.dataset import RankerDataset, DatasetManager, DatasetSplit
from agentqe.training.trainer import TransformerTrainer
from agentqe.training.evaluator import RankerEvaluator


class TestTrainingConfig:
    """Tests for TrainingConfig."""
    
    def test_default_config(self):
        """Default configuration should be valid."""
        config = TrainingConfig()
        assert config.dataset_size == 10000
        assert config.seed == 42
        assert config.epochs == 30
        assert config.batch_size == 32
        assert config.input_dim == 9
        assert len(config.feature_names) == 9
    
    def test_splits_sum_to_one(self):
        """Train/val/test splits must sum to 1.0."""
        config = TrainingConfig()
        total = config.train_split + config.val_split + config.test_split
        assert abs(total - 1.0) < 0.001
    
    def test_invalid_splits_raises_error(self):
        """Invalid split configuration should raise ValueError."""
        with pytest.raises(ValueError):
            TrainingConfig(train_split=0.5, val_split=0.3, test_split=0.1)  # Sum = 0.9
    
    def test_dataset_size_minimum(self):
        """Dataset size must be at least 100."""
        with pytest.raises(ValueError):
            TrainingConfig(dataset_size=50)
    
    def test_feature_count_mismatch_raises_error(self):
        """Feature count must match input_dim."""
        with pytest.raises(ValueError):
            TrainingConfig(feature_names=["a", "b"], input_dim=9)
    
    def test_config_to_dict(self):
        """Config should serialize to dictionary."""
        config = TrainingConfig()
        d = config.to_dict()
        assert "model_version" in d
        assert "feature_count" in d
        assert "architecture" in d
        assert d["feature_count"] == 9


class TestSyntheticDataGenerator:
    """Tests for SyntheticDataGenerator."""
    
    def test_generator_initializes_with_seed(self):
        """Generator should initialize with seed."""
        gen = SyntheticDataGenerator(seed=42)
        assert gen.seed == 42
    
    def test_generates_requested_number_of_examples(self):
        """Generator should produce exactly requested number of examples."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(100)
        assert len(examples) == 100
    
    def test_same_seed_produces_identical_dataset(self):
        """Same seed should produce identical examples."""
        gen1 = SyntheticDataGenerator(seed=42)
        gen2 = SyntheticDataGenerator(seed=42)
        
        examples1 = gen1.generate(50)
        examples2 = gen2.generate(50)
        
        assert len(examples1) == len(examples2)
        for ex1, ex2 in zip(examples1, examples2):
            assert ex1.id == ex2.id
            assert ex1.scenario == ex2.scenario
            assert ex1.features == ex2.features
            assert ex1.priority_target == ex2.priority_target
    
    def test_different_seed_produces_different_dataset(self):
        """Different seed should produce different examples."""
        gen1 = SyntheticDataGenerator(seed=42)
        gen2 = SyntheticDataGenerator(seed=123)
        
        examples1 = gen1.generate(50)
        examples2 = gen2.generate(50)
        
        # At least some examples should differ
        differences = sum(
            1 for ex1, ex2 in zip(examples1, examples2)
            if ex1.priority_target != ex2.priority_target
        )
        assert differences > 0
    
    def test_all_9_features_exist(self):
        """Each example must have exactly 9 features."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(10)
        
        for example in examples:
            assert len(example.features) == 9
            for feature_name in gen.FEATURE_NAMES:
                assert feature_name in example.features
    
    def test_features_normalized_0_1(self):
        """All feature values must be in [0, 1]."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(100)
        
        for example in examples:
            for feature_name, value in example.features.items():
                assert 0.0 <= value <= 1.0, f"Feature {feature_name} = {value}"
    
    def test_targets_normalized_0_1(self):
        """All priority targets must be in [0, 1]."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(100)
        
        for example in examples:
            assert 0.0 <= example.priority_target <= 1.0
    
    def test_scenario_distribution_valid(self):
        """Scenario distribution must sum to 1.0."""
        gen = SyntheticDataGenerator(seed=42)
        
        with pytest.raises(ValueError):
            gen.generate(10, scenario_distribution=[0.5, 0.3])  # Sum = 0.8
    
    def test_target_generation_deterministic(self):
        """Target generation should be deterministic for fixed seed."""
        gen = SyntheticDataGenerator(seed=42)
        examples1 = gen.generate(10)
        examples2 = gen.generate(10)
        
        for ex1, ex2 in zip(examples1, examples2):
            assert ex1.priority_target == ex2.priority_target
    
    def test_save_and_load_dataset(self):
        """Dataset should save and load correctly."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(10)
        
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_dataset.jsonl")
            gen.save_dataset(examples, output_path)
            
            assert os.path.exists(output_path)
            
            loaded_examples = gen.load_dataset(output_path)
            assert len(loaded_examples) == len(examples)
            
            for orig, loaded in zip(examples, loaded_examples):
                assert orig.id == loaded.id
                assert orig.features == loaded.features
                assert orig.priority_target == loaded.priority_target


class TestRankerDataset:
    """Tests for RankerDataset PyTorch Dataset."""
    
    def test_dataset_initialization(self):
        """Dataset should initialize with examples."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(10)
        dataset = RankerDataset(examples)
        
        assert len(dataset) == 10
    
    def test_dataset_returns_correct_shape(self):
        """Dataset should return correct tensor shapes."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(10)
        dataset = RankerDataset(examples)
        
        features, target = dataset[0]
        
        assert features.shape == (9,)
        assert target.shape == (1,)
        assert features.dtype == torch.float32
        assert target.dtype == torch.float32
    
    def test_dataset_validates_features(self):
        """Dataset should validate feature structure."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(10)
        
        # Remove a feature from one example
        examples[0].features.pop("requirement_relevance")
        
        with pytest.raises(ValueError):
            RankerDataset(examples)
    
    def test_dataset_validates_feature_range(self):
        """Dataset should validate feature values are in [0,1]."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(10)
        
        # Set a feature out of range
        examples[0].features["requirement_relevance"] = 1.5
        
        with pytest.raises(ValueError):
            RankerDataset(examples)
    
    def test_dataset_validates_target_range(self):
        """Dataset should validate target is in [0,1]."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(10)
        
        # Set target out of range
        examples[0].priority_target = 1.5
        
        with pytest.raises(ValueError):
            RankerDataset(examples)
    
    def test_get_feature_matrix(self):
        """get_feature_matrix should return correct shape."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(10)
        dataset = RankerDataset(examples)
        
        matrix = dataset.get_feature_matrix()
        
        assert matrix.shape == (10, 9)
        assert matrix.dtype == np.float32
    
    def test_get_targets(self):
        """get_targets should return correct shape."""
        gen = SyntheticDataGenerator(seed=42)
        examples = gen.generate(10)
        dataset = RankerDataset(examples)
        
        targets = dataset.get_targets()
        
        assert targets.shape == (10,)
        assert targets.dtype == np.float32


class TestDatasetManager:
    """Tests for DatasetManager."""
    
    def test_generate_and_split(self):
        """DatasetManager should generate and split dataset."""
        config = TrainingConfig(dataset_size=1000, seed=42)
        manager = DatasetManager(config)
        
        split = manager.generate_and_split()
        
        assert isinstance(split, DatasetSplit)
        assert len(split.train) + len(split.val) + len(split.test) == 1000
    
    def test_split_sizes_correct(self):
        """Split sizes should match configuration."""
        config = TrainingConfig(dataset_size=1000, seed=42)
        manager = DatasetManager(config)
        
        split = manager.generate_and_split()
        
        total = len(split.train) + len(split.val) + len(split.test)
        assert abs(len(split.train) / total - 0.70) < 0.05
        assert abs(len(split.val) / total - 0.15) < 0.05
        assert abs(len(split.test) / total - 0.15) < 0.05
    
    def test_split_deterministic(self):
        """Split should be deterministic for same seed."""
        config = TrainingConfig(dataset_size=1000, seed=42)
        manager1 = DatasetManager(config)
        manager2 = DatasetManager(config)
        
        split1 = manager1.generate_and_split()
        split2 = manager2.generate_and_split()
        
        assert len(split1.train) == len(split2.train)
        assert len(split1.val) == len(split2.val)
        assert len(split1.test) == len(split2.test)
    
    def test_no_split_leakage(self):
        """Scenarios should not leak across splits."""
        config = TrainingConfig(dataset_size=1000, seed=42)
        manager = DatasetManager(config)
        
        split = manager.generate_and_split()
        
        # Get scenarios in each split
        train_scenarios = {ex.scenario for ex in split.train}
        val_scenarios = {ex.scenario for ex in split.val}
        test_scenarios = {ex.scenario for ex in split.test}
        
        # No scenario should appear in more than one split
        assert len(train_scenarios & val_scenarios) == 0
        assert len(train_scenarios & test_scenarios) == 0
        assert len(val_scenarios & test_scenarios) == 0
    
    def test_create_dataloaders(self):
        """Dataloaders should be created correctly."""
        config = TrainingConfig(dataset_size=100, seed=42, batch_size=10)
        manager = DatasetManager(config)
        
        split = manager.generate_and_split()
        train_loader, val_loader, test_loader = manager.create_dataloaders(split)
        
        # Check that dataloaders work
        for features, targets in train_loader:
            assert features.shape[0] <= 10  # batch size
            assert features.shape[1] == 9
            break
    
    def test_save_and_load_split(self):
        """Split should save and load correctly."""
        config = TrainingConfig(dataset_size=100, seed=42)
        manager = DatasetManager(config)
        
        split = manager.generate_and_split()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            manager.save_split(split, tmpdir)
            
            assert os.path.exists(os.path.join(tmpdir, "train.jsonl"))
            assert os.path.exists(os.path.join(tmpdir, "val.jsonl"))
            assert os.path.exists(os.path.join(tmpdir, "test.jsonl"))
            
            loaded_split = manager.load_split(tmpdir)
            
            assert len(loaded_split.train) == len(split.train)
            assert len(loaded_split.val) == len(split.val)
            assert len(loaded_split.test) == len(split.test)


class TestTransformerTrainer:
    """Tests for TransformerTrainer."""
    
    def test_trainer_initialization(self):
        """Trainer should initialize correctly."""
        config = TrainingConfig(dataset_size=100, seed=42)
        trainer = TransformerTrainer(config)
        
        assert trainer.model is not None
        assert trainer.device is not None
        assert trainer.criterion is not None
        assert trainer.optimizer is not None
    
    def test_model_architecture_correct(self):
        """Model architecture should match config."""
        config = TrainingConfig(dataset_size=100, seed=42)
        trainer = TransformerTrainer(config)
        
        assert trainer.model.input_projection.in_features == 9
        assert trainer.model.input_projection.out_features == 64
    
    def test_training_on_cpu(self):
        """Training should work on CPU."""
        config = TrainingConfig(dataset_size=100, seed=42, epochs=2, batch_size=10, device="cpu")
        manager = DatasetManager(config)
        split = manager.generate_and_split()
        train_loader, val_loader, _ = manager.create_dataloaders(split)
        
        trainer = TransformerTrainer(config)
        history = trainer.train(train_loader, val_loader)
        
        assert "train_losses" in history
        assert "val_losses" in history
        assert len(history["train_losses"]) > 0
    
    def test_model_checkpoint_saved(self):
        """Model checkpoint should be saved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = TrainingConfig(
                dataset_size=100,
                seed=42,
                epochs=2,
                batch_size=10,
                model_output_dir=tmpdir,
            )
            manager = DatasetManager(config)
            split = manager.generate_and_split()
            train_loader, val_loader, _ = manager.create_dataloaders(split)
            
            trainer = TransformerTrainer(config)
            trainer.train(train_loader, val_loader)
            
            assert os.path.exists(config.model_path)
    
    def test_metadata_saved(self):
        """Metadata should be saved."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = TrainingConfig(
                dataset_size=100,
                seed=42,
                epochs=2,
                batch_size=10,
                model_output_dir=tmpdir,
            )
            manager = DatasetManager(config)
            split = manager.generate_and_split()
            train_loader, val_loader, test_loader = manager.create_dataloaders(split)
            
            trainer = TransformerTrainer(config)
            trainer.train(train_loader, val_loader)
            test_loss = trainer.evaluate(test_loader)
            trainer.save_metadata(test_loss, (len(split.train), len(split.val), len(split.test)))
            
            assert os.path.exists(config.metadata_path)
            
            with open(config.metadata_path, "r") as f:
                metadata = json.load(f)
            
            assert "model_version" in metadata
            assert "training_timestamp" in metadata
            assert "final_train_loss" in metadata
            assert "final_val_loss" in metadata
            assert "test_loss" in metadata
    
    def test_early_stopping(self):
        """Early stopping should trigger when validation loss doesn't improve."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = TrainingConfig(
                dataset_size=100,
                seed=42,
                epochs=20,
                batch_size=10,
                early_stopping_patience=3,
                model_output_dir=tmpdir,
            )
            manager = DatasetManager(config)
            split = manager.generate_and_split()
            train_loader, val_loader, _ = manager.create_dataloaders(split)
            
            trainer = TransformerTrainer(config)
            history = trainer.train(train_loader, val_loader)
            
            # Should stop early due to patience
            assert len(history["epochs"]) < 20


class TestRankerEvaluator:
    """Tests for RankerEvaluator."""
    
    def test_evaluator_initialization(self):
        """Evaluator should initialize correctly."""
        config = TrainingConfig(dataset_size=100, seed=42)
        evaluator = RankerEvaluator(config)
        
        assert evaluator.config is not None
    
    def test_evaluate_returns_metrics(self):
        """Evaluate should return all expected metrics."""
        config = TrainingConfig(dataset_size=100, seed=42, epochs=2, batch_size=10)
        manager = DatasetManager(config)
        split = manager.generate_and_split()
        train_loader, val_loader, test_loader = manager.create_dataloaders(split)
        
        trainer = TransformerTrainer(config)
        trainer.train(train_loader, val_loader)
        
        evaluator = RankerEvaluator(config)
        metrics = evaluator.evaluate(trainer.model, test_loader, split.test)
        
        expected_metrics = [
            "mse", "mae", "spearman", "kendall",
            "top_10_overlap", "top_20_overlap", "top_30_overlap",
            "bootstrap_spearman", "bootstrap_kendall",
        ]
        
        for metric in expected_metrics:
            assert metric in metrics
    
    def test_mse_calculation(self):
        """MSE should be calculated correctly."""
        config = TrainingConfig(dataset_size=100, seed=42)
        evaluator = RankerEvaluator(config)
        
        predictions = np.array([0.5, 0.6, 0.7])
        targets = np.array([0.5, 0.6, 0.7])
        
        mse = evaluator._compute_mse(predictions, targets)
        assert mse == 0.0
    
    def test_mae_calculation(self):
        """MAE should be calculated correctly."""
        config = TrainingConfig(dataset_size=100, seed=42)
        evaluator = RankerEvaluator(config)
        
        predictions = np.array([0.5, 0.6, 0.7])
        targets = np.array([0.4, 0.6, 0.8])
        
        mae = evaluator._compute_mae(predictions, targets)
        assert abs(mae - 0.0667) < 0.01
    
    def test_top_k_overlap(self):
        """Top-k overlap should be calculated correctly."""
        config = TrainingConfig(dataset_size=100, seed=42)
        evaluator = RankerEvaluator(config)
        
        predictions = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
        targets = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
        
        overlap = evaluator._compute_top_k_overlap(predictions, targets, 0.10)
        assert overlap == 1.0  # Perfect overlap


class TestTransformerRankerWrapperIntegration:
    """Integration tests for TransformerRankerWrapper with trained model."""
    
    def test_wrapper_loads_trained_model(self):
        """Wrapper should load trained model if available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Train and save model
            config = TrainingConfig(
                dataset_size=100,
                seed=42,
                epochs=2,
                batch_size=10,
                model_output_dir=tmpdir,
            )
            manager = DatasetManager(config)
            split = manager.generate_and_split()
            train_loader, val_loader, test_loader = manager.create_dataloaders(split)
            
            trainer = TransformerTrainer(config)
            trainer.train(train_loader, val_loader)
            test_loss = trainer.evaluate(test_loader)
            trainer.save_metadata(test_loss, (len(split.train), len(split.val), len(split.test)))
            
            # Now test wrapper loading
            from agentqe.prioritization.bootstrap_ranker import TransformerRankerWrapper
            
            wrapper = TransformerRankerWrapper()
            loaded = wrapper.load_transformer(config.model_path)
            
            assert loaded is True
            assert wrapper._transformer_loaded is True
            assert wrapper.model_status == "trained"
    
    def test_wrapper_falls_back_to_bootstrap(self):
        """Wrapper should fall back to bootstrap if model not available."""
        from agentqe.prioritization.bootstrap_ranker import TransformerRankerWrapper
        
        wrapper = TransformerRankerWrapper()
        
        # Try to load non-existent model
        loaded = wrapper.load_transformer("/nonexistent/path/model.pt")
        
        assert loaded is False
        assert wrapper._transformer_loaded is False
        assert wrapper.model_status == "untrained"
    
    def test_wrapper_validates_model_architecture(self):
        """Wrapper should validate model architecture."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a model with wrong architecture
            import torch
            import torch.nn as nn
            
            class WrongModel(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.input_projection = nn.Linear(5, 64)  # Wrong input dim
            
            wrong_model = WrongModel()
            model_path = os.path.join(tmpdir, "wrong_model.pt")
            torch.save(wrong_model.state_dict(), model_path)
            
            from agentqe.prioritization.bootstrap_ranker import TransformerRankerWrapper
            
            wrapper = TransformerRankerWrapper()
            loaded = wrapper.load_transformer(model_path)
            
            assert loaded is False
            assert wrapper._transformer_loaded is False
    
    def test_ranking_mode_changes_with_trained_model(self):
        """ranking_mode should be 'transformer' when model is loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Train and save model
            config = TrainingConfig(
                dataset_size=100,
                seed=42,
                epochs=2,
                batch_size=10,
                model_output_dir=tmpdir,
            )
            manager = DatasetManager(config)
            split = manager.generate_and_split()
            train_loader, val_loader, test_loader = manager.create_dataloaders(split)
            
            trainer = TransformerTrainer(config)
            trainer.train(train_loader, val_loader)
            test_loss = trainer.evaluate(test_loader)
            trainer.save_metadata(test_loss, (len(split.train), len(split.val), len(split.test)))
            
            from agentqe.prioritization.bootstrap_ranker import TransformerRankerWrapper
            
            wrapper = TransformerRankerWrapper()
            wrapper.load_transformer(config.model_path)
            
            assert wrapper.ranking_mode == "transformer"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
