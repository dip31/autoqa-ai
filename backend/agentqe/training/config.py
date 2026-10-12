"""
Training configuration for Phase 4.5 synthetic data training.
"""

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TrainingConfig:
    """
    Configuration for synthetic data generation and Transformer training.
    
    All parameters are configurable via environment variables or constructor arguments.
    """
    
    # Dataset configuration
    dataset_size: int = field(default_factory=lambda: int(
        os.getenv("AGENTQE_SYNTHETIC_DATASET_SIZE", "10000")
    ))
    seed: int = field(default_factory=lambda: int(
        os.getenv("AGENTQE_SYNTHETIC_SEED", "42")
    ))
    
    # Train/validation/test split (must sum to 1.0)
    train_split: float = 0.70
    val_split: float = 0.15
    test_split: float = 0.15
    
    # Training hyperparameters
    epochs: int = 30
    batch_size: int = 32
    learning_rate: float = 0.001
    weight_decay: float = 1e-5
    
    # Model architecture (must match TransformerTestRanker)
    input_dim: int = 9
    d_model: int = 64
    nhead: int = 4
    num_layers: int = 2
    
    # Training settings
    loss_function: str = "mse"  # "mse" or "smooth_l1"
    early_stopping_patience: int = 5
    early_stopping_min_delta: float = 1e-4
    
    # Device configuration
    device: str = "auto"  # "auto", "cpu", "cuda"
    
    # Output paths
    model_output_dir: str = "backend/agentqe/models"
    model_filename: str = "transformer_ranker.pt"
    metadata_filename: str = "transformer_ranker_metadata.json"
    dataset_output_dir: str = "backend/data/agentqe/training"
    dataset_filename: str = "synthetic_ranker_dataset.jsonl"
    
    # Feature names (must match Phase4FeatureExtractor.FEATURE_NAMES)
    feature_names: list = field(default_factory=lambda: [
        "requirement_relevance",
        "risk_relevance",
        "coverage",
        "api_relevance",
        "execution_complexity",
        "evidence_confidence",
        "cross_modal_evidence",
        "test_layer_signal",
        "traceability_completeness",
    ])
    
    # Model versioning
    model_version: str = "agentqe-transformer-bootstrap-v1"
    training_data_type: str = "synthetic"
    
    def __post_init__(self):
        """Validate configuration."""
        # Validate splits sum to 1.0
        total_split = self.train_split + self.val_split + self.test_split
        if abs(total_split - 1.0) > 0.001:
            raise ValueError(f"Train/val/test splits must sum to 1.0, got {total_split}")
        
        # Validate dataset size
        if self.dataset_size < 100:
            raise ValueError(f"Dataset size must be at least 100, got {self.dataset_size}")
        
        # Validate feature count
        if len(self.feature_names) != self.input_dim:
            raise ValueError(
                f"Feature count mismatch: {len(self.feature_names)} features vs input_dim={self.input_dim}"
            )
    
    @property
    def model_path(self) -> str:
        """Full path to model checkpoint."""
        return os.path.join(self.model_output_dir, self.model_filename)
    
    @property
    def metadata_path(self) -> str:
        """Full path to metadata file."""
        return os.path.join(self.model_output_dir, self.metadata_filename)
    
    @property
    def dataset_path(self) -> str:
        """Full path to dataset file."""
        return os.path.join(self.dataset_output_dir, self.dataset_filename)
    
    def get_device(self):
        """Get torch device based on configuration."""
        if self.device == "auto":
            import torch
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        elif self.device == "cuda":
            import torch
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA requested but not available")
            return torch.device("cuda")
        else:
            import torch
            return torch.device("cpu")
    
    def to_dict(self) -> dict:
        """Convert configuration to dictionary for metadata."""
        return {
            "model_version": self.model_version,
            "training_data_type": self.training_data_type,
            "feature_count": self.input_dim,
            "features": self.feature_names,
            "dataset_size": self.dataset_size,
            "seed": self.seed,
            "train_split": self.train_split,
            "val_split": self.val_split,
            "test_split": self.test_split,
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "weight_decay": self.weight_decay,
            "loss_function": self.loss_function,
            "early_stopping_patience": self.early_stopping_patience,
            "architecture": {
                "input_dim": self.input_dim,
                "d_model": self.d_model,
                "nhead": self.nhead,
                "num_layers": self.num_layers,
            },
        }


__all__ = ["TrainingConfig"]
