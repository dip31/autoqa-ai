"""
Evaluation metrics for Phase 4.5 Transformer training.

Provides ranking-specific metrics beyond simple regression loss.
"""

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from typing import Dict, Any, List, Tuple
from scipy.stats import spearmanr, kendalltau

from agentqe.training.config import TrainingConfig
from agentqe.training.dataset import RankerDataset, SyntheticExample


class RankerEvaluator:
    """
    Evaluator for test prioritization models.
    
    Computes:
    - Regression metrics (MSE, MAE)
    - Rank correlation metrics (Spearman, Kendall)
    - Top-k overlap metrics
    """
    
    def __init__(self, config: TrainingConfig):
        """
        Initialize evaluator.
        
        Args:
            config: Training configuration
        """
        self.config = config
        self.device = config.get_device()
    
    def evaluate(
        self,
        model: nn.Module,
        test_loader: DataLoader,
        test_examples: List[SyntheticExample],
    ) -> Dict[str, float]:
        """
        Run comprehensive evaluation.
        
        Args:
            model: Trained model
            test_loader: Test data loader
            test_examples: Test examples for ranking evaluation
        
        Returns:
            Dictionary of evaluation metrics
        """
        # Get predictions
        predictions, targets = self._get_predictions(model, test_loader)
        
        # Compute metrics
        metrics = {}
        
        # Regression metrics
        metrics["mse"] = self._compute_mse(predictions, targets)
        metrics["mae"] = self._compute_mae(predictions, targets)
        
        # Rank correlation metrics
        metrics["spearman"] = self._compute_spearman(predictions, targets)
        metrics["kendall"] = self._compute_kendall(predictions, targets)
        
        # Top-k overlap metrics
        for k in [0.10, 0.20, 0.30]:
            metrics[f"top_{int(k*100)}_overlap"] = self._compute_top_k_overlap(
                predictions, targets, k
            )
        
        # Bootstrap comparison
        bootstrap_scores = self._compute_bootstrap_scores(test_examples)
        metrics["bootstrap_spearman"] = self._compute_spearman(
            bootstrap_scores, targets
        )
        metrics["bootstrap_kendall"] = self._compute_kendall(
            bootstrap_scores, targets
        )
        
        return metrics
    
    def _get_predictions(
        self,
        model: nn.Module,
        data_loader: DataLoader,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get model predictions and targets.
        
        Returns:
            (predictions, targets) tuple as numpy arrays
        """
        model.eval()
        all_predictions = []
        all_targets = []
        
        with torch.no_grad():
            for features, targets in data_loader:
                features = features.to(self.device)
                targets = targets.to(self.device)
                
                # Add sequence dimension
                features = features.unsqueeze(1)
                
                # Forward pass
                outputs = model(features)
                
                all_predictions.append(outputs.cpu().numpy())
                all_targets.append(targets.squeeze(-1).cpu().numpy())
        
        predictions = np.concatenate(all_predictions)
        targets = np.concatenate(all_targets)
        
        return predictions, targets
    
    def _compute_mse(self, predictions: np.ndarray, targets: np.ndarray) -> float:
        """Compute Mean Squared Error."""
        return float(np.mean((predictions - targets) ** 2))
    
    def _compute_mae(self, predictions: np.ndarray, targets: np.ndarray) -> float:
        """Compute Mean Absolute Error."""
        return float(np.mean(np.abs(predictions - targets)))
    
    def _compute_spearman(
        self,
        predictions: np.ndarray,
        targets: np.ndarray,
    ) -> float:
        """Compute Spearman rank correlation."""
        correlation, _ = spearmanr(predictions, targets)
        return float(correlation) if not np.isnan(correlation) else 0.0
    
    def _compute_kendall(
        self,
        predictions: np.ndarray,
        targets: np.ndarray,
    ) -> float:
        """Compute Kendall Tau rank correlation."""
        correlation, _ = kendalltau(predictions, targets)
        return float(correlation) if not np.isnan(correlation) else 0.0
    
    def _compute_top_k_overlap(
        self,
        predictions: np.ndarray,
        targets: np.ndarray,
        k_fraction: float,
    ) -> float:
        """
        Compute top-k overlap between predicted and target rankings.
        
        Args:
            predictions: Predicted priority scores
            targets: Target priority scores
            k_fraction: Fraction of top items to consider (e.g., 0.10 for top 10%)
        
        Returns:
            Jaccard overlap score [0, 1]
        """
        k = max(1, int(len(predictions) * k_fraction))
        
        # Get top-k indices
        pred_top_k = set(np.argsort(predictions)[-k:])
        target_top_k = set(np.argsort(targets)[-k:])
        
        # Compute Jaccard overlap
        intersection = len(pred_top_k & target_top_k)
        union = len(pred_top_k | target_top_k)
        
        return intersection / union if union > 0 else 0.0
    
    def _compute_bootstrap_scores(
        self,
        examples: List[SyntheticExample],
    ) -> np.ndarray:
        """
        Compute bootstrap scores for comparison.
        
        Uses the bootstrap weights from bootstrap_ranker.py.
        """
        # Bootstrap weights
        weights = np.array([
            0.20,  # requirement_relevance
            0.15,  # risk_relevance
            0.10,  # coverage
            0.10,  # api_relevance
            0.10,  # execution_complexity
            0.10,  # evidence_confidence
            0.05,  # cross_modal_evidence
            0.10,  # test_layer_signal
            0.10,  # traceability_completeness
        ])
        
        feature_names = [
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
        
        scores = []
        for example in examples:
            features = np.array([example.features[name] for name in feature_names])
            score = np.dot(features, weights)
            scores.append(score)
        
        return np.array(scores)


__all__ = ["RankerEvaluator"]
