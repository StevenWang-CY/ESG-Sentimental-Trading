"""
Machine Learning Module
Enhanced ML models and pipelines for ESG sentiment trading

Implements research-backed techniques from Savarese (2019) thesis:
- Categorical classification (BUY/SELL/HOLD)
- Feature selection to avoid curse of dimensionality
- Random Forest and ensemble classifiers
- Complete integrated pipeline
"""

from .categorical_classifier import CategoricalSignalClassifier, EnsembleSignalClassifier
from .feature_selector import FeatureSelector, create_optimal_feature_set
from .enhanced_pipeline import EnhancedESGPipeline

__all__ = [
    'CategoricalSignalClassifier',
    'EnsembleSignalClassifier',
    'FeatureSelector',
    'create_optimal_feature_set',
    'EnhancedESGPipeline'
]
