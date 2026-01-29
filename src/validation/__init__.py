"""
Validation Framework for ESG-Sentimental-Trading Strategy

This module implements proper walk-forward validation to eliminate look-ahead bias
and provide realistic out-of-sample performance estimates.
"""

from .walk_forward_validator import (
    ValidationWindow,
    ValidationResult,
    WalkForwardValidator,
    WeightOptimizer,
    AggregateMetrics,
)

__all__ = [
    "ValidationWindow",
    "ValidationResult",
    "WalkForwardValidator",
    "WeightOptimizer",
    "AggregateMetrics",
]
