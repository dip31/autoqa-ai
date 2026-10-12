"""
Phase 4.5 — Synthetic Training Data Generation and Transformer Training.

This module provides:
- Synthetic data generation for bootstrap Transformer training
- Dataset management with train/validation/test splits
- Transformer training pipeline
- Evaluation metrics for ranking models
"""

from agentqe.training.config import TrainingConfig
from agentqe.training.synthetic_generator import SyntheticDataGenerator
from agentqe.training.dataset import RankerDataset, DatasetSplit
from agentqe.training.trainer import TransformerTrainer
from agentqe.training.evaluator import RankerEvaluator

__all__ = [
    "TrainingConfig",
    "SyntheticDataGenerator",
    "RankerDataset",
    "DatasetSplit",
    "TransformerTrainer",
    "RankerEvaluator",
]
