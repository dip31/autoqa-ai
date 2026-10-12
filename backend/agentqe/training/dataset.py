"""
Dataset management for Phase 4.5 Transformer training.

Handles train/validation/test splits and PyTorch Dataset implementation.
"""

import json
import os
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
import numpy as np
import torch
from torch.utils.data import Dataset, DataLoader, random_split

from agentqe.training.synthetic_generator import SyntheticDataGenerator, SyntheticExample
from agentqe.training.config import TrainingConfig


@dataclass
class DatasetSplit:
    """Container for train/validation/test splits."""
    train: List[SyntheticExample]
    val: List[SyntheticExample]
    test: List[SyntheticExample]
    
    def __len__(self) -> Tuple[int, int, int]:
        return len(self.train), len(self.val), len(self.test)


class RankerDataset(Dataset):
    """
    PyTorch Dataset for test prioritization training.
    
    Each example contains:
    - 9 feature values (normalized [0,1])
    - Priority target (normalized [0,1])
    """
    
    FEATURE_NAMES = [
        "requirement_relevance",
        "risk_relevance",
        "coverage",
        "api_relevance",
        "execution_complexity",
        "evidence_confidence",
        "cross_modal_evidence",
        "test_layer_signal",
        "traceability_completeness",
    ]
    
    def __init__(self, examples: List[SyntheticExample]):
        """
        Initialize dataset.
        
        Args:
            examples: List of SyntheticExample objects
        """
        self.examples = examples
        self._validate_examples()
    
    def _validate_examples(self):
        """Validate that all examples have correct structure."""
        for example in self.examples:
            # Check all 9 features exist
            for feature_name in self.FEATURE_NAMES:
                if feature_name not in example.features:
                    raise ValueError(f"Missing feature: {feature_name}")
            
            # Check feature values are in [0,1]
            for feature_name, value in example.features.items():
                if not (0.0 <= value <= 1.0):
                    raise ValueError(
                        f"Feature {feature_name} out of range [0,1]: {value}"
                    )
            
            # Check target is in [0,1]
            if not (0.0 <= example.priority_target <= 1.0):
                raise ValueError(
                    f"Target out of range [0,1]: {example.priority_target}"
                )
    
    def __len__(self) -> int:
        return len(self.examples)
    
    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Get a single example.
        
        Returns:
            (features, target) tuple
            - features: torch.Tensor of shape (9,)
            - target: torch.Tensor of shape (1,)
        """
        example = self.examples[idx]
        
        # Extract features in correct order
        feature_values = [example.features[name] for name in self.FEATURE_NAMES]
        features = torch.tensor(feature_values, dtype=torch.float32)
        
        # Extract target
        target = torch.tensor([example.priority_target], dtype=torch.float32)
        
        return features, target
    
    def get_feature_matrix(self) -> np.ndarray:
        """Get all features as numpy array (n_samples, 9)."""
        matrix = np.array([
            [example.features[name] for name in self.FEATURE_NAMES]
            for example in self.examples
        ], dtype=np.float32)
        return matrix
    
    def get_targets(self) -> np.ndarray:
        """Get all targets as numpy array (n_samples,)."""
        return np.array([example.priority_target for example in self.examples], dtype=np.float32)


class DatasetManager:
    """
    Manages dataset generation, splitting, and loading.
    
    Provides deterministic train/validation/test splits with no leakage.
    """
    
    def __init__(self, config: TrainingConfig):
        """
        Initialize dataset manager.
        
        Args:
            config: Training configuration
        """
        self.config = config
        self.generator = SyntheticDataGenerator(seed=config.seed)
    
    def generate_and_split(
        self,
        num_examples: Optional[int] = None,
    ) -> DatasetSplit:
        """
        Generate synthetic dataset and split into train/val/test.
        
        Args:
            num_examples: Number of examples to generate (uses config if None)
        
        Returns:
            DatasetSplit with train/val/test examples
        """
        if num_examples is None:
            num_examples = self.config.dataset_size
        
        # Generate examples
        examples = self.generator.generate(num_examples)
        
        # Split deterministically
        split = self._split_examples(examples)
        
        return split
    
    def _split_examples(self, examples: List[SyntheticExample]) -> DatasetSplit:
        """
        Split examples into train/val/test deterministically.
        
        Uses scenario-aware splitting to avoid leakage:
        - Examples from same scenario are kept together in one split
        - This prevents near-duplicates across splits
        """
        # Group examples by scenario
        scenario_groups = {}
        for example in examples:
            scenario = example.scenario
            if scenario not in scenario_groups:
                scenario_groups[scenario] = []
            scenario_groups[scenario].append(example)
        
        # Shuffle scenario groups deterministically
        scenario_names = list(scenario_groups.keys())
        rng = np.random.RandomState(self.config.seed)
        rng.shuffle(scenario_names)
        
        # Allocate scenarios to splits
        num_scenarios = len(scenario_names)
        train_end = int(num_scenarios * self.config.train_split)
        val_end = train_end + int(num_scenarios * self.config.val_split)
        
        train_scenarios = scenario_names[:train_end]
        val_scenarios = scenario_names[train_end:val_end]
        test_scenarios = scenario_names[val_end:]
        
        # Collect examples for each split
        train_examples = []
        val_examples = []
        test_examples = []
        
        for scenario in train_scenarios:
            train_examples.extend(scenario_groups[scenario])
        for scenario in val_scenarios:
            val_examples.extend(scenario_groups[scenario])
        for scenario in test_scenarios:
            test_examples.extend(scenario_groups[scenario])
        
        # Shuffle examples within each split deterministically
        rng.shuffle(train_examples)
        rng.shuffle(val_examples)
        rng.shuffle(test_examples)
        
        return DatasetSplit(
            train=train_examples,
            val=val_examples,
            test=test_examples,
        )
    
    def create_dataloaders(
        self,
        split: DatasetSplit,
    ) -> Tuple[DataLoader, DataLoader, DataLoader]:
        """
        Create PyTorch DataLoaders for train/val/test splits.
        
        Args:
            split: DatasetSplit with examples
        
        Returns:
            (train_loader, val_loader, test_loader) tuple
        """
        train_dataset = RankerDataset(split.train)
        val_dataset = RankerDataset(split.val)
        test_dataset = RankerDataset(split.test)
        
        train_loader = DataLoader(
            train_dataset,
            batch_size=self.config.batch_size,
            shuffle=True,
            num_workers=0,  # Windows compatibility
        )
        
        val_loader = DataLoader(
            val_dataset,
            batch_size=self.config.batch_size,
            shuffle=False,
            num_workers=0,
        )
        
        test_loader = DataLoader(
            test_dataset,
            batch_size=self.config.batch_size,
            shuffle=False,
            num_workers=0,
        )
        
        return train_loader, val_loader, test_loader
    
    def save_split(self, split: DatasetSplit, output_dir: str) -> None:
        """
        Save dataset split to JSONL files.
        
        Args:
            split: DatasetSplit to save
            output_dir: Directory to save files
        """
        os.makedirs(output_dir, exist_ok=True)
        
        self.generator.save_dataset(
            split.train,
            os.path.join(output_dir, "train.jsonl"),
        )
        self.generator.save_dataset(
            split.val,
            os.path.join(output_dir, "val.jsonl"),
        )
        self.generator.save_dataset(
            split.test,
            os.path.join(output_dir, "test.jsonl"),
        )
    
    def load_split(self, input_dir: str) -> DatasetSplit:
        """
        Load dataset split from JSONL files.
        
        Args:
            input_dir: Directory containing train/val/test.jsonl
        
        Returns:
            DatasetSplit with loaded examples
        """
        train = self.generator.load_dataset(os.path.join(input_dir, "train.jsonl"))
        val = self.generator.load_dataset(os.path.join(input_dir, "val.jsonl"))
        test = self.generator.load_dataset(os.path.join(input_dir, "test.jsonl"))
        
        return DatasetSplit(train=train, val=val, test=test)


__all__ = [
    "RankerDataset",
    "DatasetSplit",
    "DatasetManager",
]
