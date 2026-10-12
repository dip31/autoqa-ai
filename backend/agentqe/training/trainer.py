"""
Transformer training pipeline for Phase 4.5.

Handles model training, checkpointing, and early stopping.
"""

import os
import json
import time
from typing import Dict, Any, Optional, Tuple
import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from datetime import datetime

from agentqe.ml.transformer_ranker import TransformerTestRanker
from agentqe.training.config import TrainingConfig
from agentqe.training.dataset import DatasetSplit, RankerDataset


class TransformerTrainer:
    """
    Trainer for the Transformer test ranker.
    
    Handles:
    - Model initialization
    - Training loop with early stopping
    - Model checkpointing
    - Metadata tracking
    """
    
    def __init__(self, config: TrainingConfig):
        """
        Initialize trainer.
        
        Args:
            config: Training configuration
        """
        self.config = config
        self.device = config.get_device()
        
        # Initialize model
        self.model = TransformerTestRanker(
            input_dim=config.input_dim,
            d_model=config.d_model,
            nhead=config.nhead,
            num_layers=config.num_layers,
        ).to(self.device)
        
        # Initialize loss function
        if config.loss_function == "mse":
            self.criterion = nn.MSELoss()
        elif config.loss_function == "smooth_l1":
            self.criterion = nn.SmoothL1Loss()
        else:
            raise ValueError(f"Unknown loss function: {config.loss_function}")
        
        # Initialize optimizer
        self.optimizer = optim.Adam(
            self.model.parameters(),
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
        )
        
        # Training state
        self.best_val_loss = float("inf")
        self.patience_counter = 0
        self.training_history = {
            "train_losses": [],
            "val_losses": [],
            "epochs": [],
        }
    
    def train(
        self,
        train_loader: DataLoader,
        val_loader: DataLoader,
    ) -> Dict[str, Any]:
        """
        Train the model with early stopping.
        
        Args:
            train_loader: Training data loader
            val_loader: Validation data loader
        
        Returns:
            Training history dictionary
        """
        print(f"Training on device: {self.device}")
        print(f"Model architecture: {self.config.input_dim} -> {self.config.d_model} -> 32 -> 1")
        print(f"Parameters: {sum(p.numel() for p in self.model.parameters()):,}")
        
        start_time = time.time()
        
        for epoch in range(self.config.epochs):
            # Train epoch
            train_loss = self._train_epoch(train_loader)
            
            # Validate
            val_loss = self._validate(val_loader)
            
            # Record history
            self.training_history["train_losses"].append(train_loss)
            self.training_history["val_losses"].append(val_loss)
            self.training_history["epochs"].append(epoch)
            
            print(
                f"Epoch {epoch+1}/{self.config.epochs} - "
                f"Train Loss: {train_loss:.6f} - "
                f"Val Loss: {val_loss:.6f}"
            )
            
            # Early stopping check
            if self._check_early_stopping(val_loss):
                print(f"Early stopping at epoch {epoch+1}")
                break
            
            # Save best model
            if val_loss < self.best_val_loss:
                self.best_val_loss = val_loss
                self._save_checkpoint()
        
        training_time = time.time() - start_time
        print(f"Training completed in {training_time:.2f} seconds")
        
        return self.training_history
    
    def _train_epoch(self, train_loader: DataLoader) -> float:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0.0
        num_batches = 0
        
        for features, targets in train_loader:
            # Move to device
            features = features.to(self.device)
            targets = targets.to(self.device)
            
            # Add sequence dimension (batch_size, 1, 9)
            features = features.unsqueeze(1)
            
            # Forward pass
            self.optimizer.zero_grad()
            outputs = self.model(features)
            loss = self.criterion(outputs, targets.squeeze(-1))
            
            # Backward pass
            loss.backward()
            self.optimizer.step()
            
            total_loss += loss.item()
            num_batches += 1
        
        return total_loss / num_batches if num_batches > 0 else 0.0
    
    def _validate(self, val_loader: DataLoader) -> float:
        """Validate the model."""
        self.model.eval()
        total_loss = 0.0
        num_batches = 0
        
        with torch.no_grad():
            for features, targets in val_loader:
                # Move to device
                features = features.to(self.device)
                targets = targets.to(self.device)
                
                # Add sequence dimension
                features = features.unsqueeze(1)
                
                # Forward pass
                outputs = self.model(features)
                loss = self.criterion(outputs, targets.squeeze(-1))
                
                total_loss += loss.item()
                num_batches += 1
        
        return total_loss / num_batches if num_batches > 0 else 0.0
    
    def _check_early_stopping(self, val_loss: float) -> bool:
        """Check if early stopping should trigger."""
        if val_loss < self.best_val_loss - self.config.early_stopping_min_delta:
            self.patience_counter = 0
            return False
        else:
            self.patience_counter += 1
            if self.patience_counter >= self.config.early_stopping_patience:
                return True
            return False
    
    def _save_checkpoint(self) -> None:
        """Save model checkpoint."""
        os.makedirs(self.config.model_output_dir, exist_ok=True)
        
        torch.save(
            self.model.state_dict(),
            self.config.model_path,
        )
    
    def save_metadata(
        self,
        test_loss: float,
        split_sizes: Tuple[int, int, int],
    ) -> None:
        """
        Save training metadata to JSON file.
        
        Args:
            test_loss: Final test loss
            split_sizes: (train_size, val_size, test_size) tuple
        """
        metadata = {
            **self.config.to_dict(),
            "training_timestamp": datetime.utcnow().isoformat(),
            "final_train_loss": self.training_history["train_losses"][-1],
            "final_val_loss": self.training_history["val_losses"][-1],
            "test_loss": test_loss,
            "train_size": split_sizes[0],
            "val_size": split_sizes[1],
            "test_size": split_sizes[2],
            "total_epochs_trained": len(self.training_history["epochs"]),
            "best_val_loss": self.best_val_loss,
            "device": str(self.device),
        }
        
        with open(self.config.metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        
        print(f"Metadata saved to {self.config.metadata_path}")
    
    def evaluate(self, test_loader: DataLoader) -> float:
        """
        Evaluate model on test set.
        
        Args:
            test_loader: Test data loader
        
        Returns:
            Test loss
        """
        test_loss = self._validate(test_loader)
        print(f"Test Loss: {test_loss:.6f}")
        return test_loss


def main():
    """CLI entry point for training."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Train AgentQE Transformer ranker")
    parser.add_argument(
        "--dataset-size",
        type=int,
        default=10000,
        help="Number of synthetic examples to generate",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=30,
        help="Number of training epochs",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Training batch size",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.001,
        help="Learning rate",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Device to use for training",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for model and metadata",
    )
    
    args = parser.parse_args()
    
    # Create config
    config = TrainingConfig(
        dataset_size=args.dataset_size,
        seed=args.seed,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        device=args.device,
    )
    
    if args.output_dir:
        config.model_output_dir = args.output_dir
    
    # Import dataset manager
    from agentqe.training.dataset import DatasetManager
    from agentqe.training.evaluator import RankerEvaluator
    
    # Generate dataset
    print(f"Generating {config.dataset_size} synthetic examples...")
    dataset_manager = DatasetManager(config)
    split = dataset_manager.generate_and_split()
    
    print(f"Train: {len(split.train)}, Val: {len(split.val)}, Test: {len(split.test)}")
    
    # Create dataloaders
    train_loader, val_loader, test_loader = dataset_manager.create_dataloaders(split)
    
    # Train model
    trainer = TransformerTrainer(config)
    history = trainer.train(train_loader, val_loader)
    
    # Evaluate
    test_loss = trainer.evaluate(test_loader)
    
    # Save metadata
    trainer.save_metadata(test_loss, (len(split.train), len(split.val), len(split.test)))
    
    # Run detailed evaluation
    print("\nRunning detailed evaluation...")
    evaluator = RankerEvaluator(config)
    metrics = evaluator.evaluate(trainer.model, test_loader, split.test)
    
    print("\n=== Evaluation Metrics ===")
    for metric_name, value in metrics.items():
        print(f"{metric_name}: {value:.6f}")
    
    print(f"\nModel saved to {config.model_path}")
    print(f"Metadata saved to {config.metadata_path}")


if __name__ == "__main__":
    main()
