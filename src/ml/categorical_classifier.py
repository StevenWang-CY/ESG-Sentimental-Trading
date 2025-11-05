"""
Categorical Classification for Trading Signals
Implements BUY/SELL/HOLD classification approach from Savarese (2019) thesis

Converts continuous price predictions to categorical trading signals:
- BUY: Expected return > +1%
- HOLD: Expected return between -1% and +1%
- SELL: Expected return < -1%
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.naive_bayes import MultinomialNB
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, TimeSeriesSplit
from sklearn.metrics import classification_report, confusion_matrix, accuracy_score
import pickle


class CategoricalSignalClassifier:
    """
    Categorical classification for trading signals
    Classifies events into BUY/SELL/HOLD based on expected price movement
    """

    def __init__(self,
                 model_type: str = 'random_forest',
                 buy_threshold: float = 0.01,
                 sell_threshold: float = -0.01,
                 **model_kwargs):
        """
        Initialize categorical classifier

        Args:
            model_type: 'random_forest', 'svm', 'naive_bayes', or 'mlp'
            buy_threshold: Return threshold for BUY signal (default +1%)
            sell_threshold: Return threshold for SELL signal (default -1%)
            **model_kwargs: Additional parameters for the model
        """
        self.model_type = model_type
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

        # Initialize model
        self.model = self._create_model(model_type, model_kwargs)
        self.scaler = StandardScaler()

        # Store feature names for later use
        self.feature_names: List[str] = []

        # Model metadata
        self.is_trained = False
        self.training_score = None
        self.validation_score = None

    def _create_model(self, model_type: str, model_kwargs: Dict):
        """Create sklearn model based on type"""
        if model_type == 'random_forest':
            # Default hyperparameters from thesis
            default_params = {
                'n_estimators': 100,
                'max_depth': 10,
                'min_samples_split': 5,
                'min_samples_leaf': 2,
                'random_state': 42,
                'n_jobs': -1
            }
            default_params.update(model_kwargs)
            return RandomForestClassifier(**default_params)

        elif model_type == 'svm':
            default_params = {
                'C': 1.0,
                'kernel': 'rbf',
                'gamma': 'scale',
                'random_state': 42
            }
            default_params.update(model_kwargs)
            return SVC(**default_params)

        elif model_type == 'naive_bayes':
            # For Multinomial NB, we need to ensure positive features
            default_params = {
                'alpha': 1.0
            }
            default_params.update(model_kwargs)
            return MultinomialNB(**default_params)

        elif model_type == 'mlp':
            default_params = {
                'hidden_layer_sizes': (100, 50),
                'activation': 'relu',
                'solver': 'adam',
                'max_iter': 500,
                'random_state': 42
            }
            default_params.update(model_kwargs)
            return MLPClassifier(**default_params)

        else:
            raise ValueError(f"Unknown model type: {model_type}")

    def create_labels(self, returns: pd.Series) -> pd.Series:
        """
        Create categorical labels from returns

        Args:
            returns: Series of forward returns

        Returns:
            Series of labels: 0 (SELL), 1 (HOLD), 2 (BUY)
        """
        labels = pd.Series(index=returns.index, dtype=int)

        # BUY: return > buy_threshold
        labels[returns > self.buy_threshold] = 2

        # HOLD: sell_threshold <= return <= buy_threshold
        labels[(returns >= self.sell_threshold) & (returns <= self.buy_threshold)] = 1

        # SELL: return < sell_threshold
        labels[returns < self.sell_threshold] = 0

        return labels

    def fit(self,
            X: pd.DataFrame,
            y: pd.Series,
            validation_split: float = 0.2) -> Dict[str, float]:
        """
        Train the classifier

        Args:
            X: Feature matrix
            y: Target returns (will be converted to labels)
            validation_split: Fraction of data for validation

        Returns:
            Dictionary with training metrics
        """
        # Store feature names
        self.feature_names = list(X.columns)

        # Create categorical labels from returns
        labels = self.create_labels(y)

        # Split data
        X_train, X_val, y_train, y_val = train_test_split(
            X, labels, test_size=validation_split, random_state=42
        )

        # Scale features (except for Naive Bayes which needs positive values)
        if self.model_type != 'naive_bayes':
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_val_scaled = self.scaler.transform(X_val)
        else:
            # For Naive Bayes, ensure all features are positive
            X_train_scaled = X_train - X_train.min() + 1e-6
            X_val_scaled = X_val - X_train.min() + 1e-6

        # Train model
        print(f"\nTraining {self.model_type} classifier...")
        print(f"  Training samples: {len(X_train)}")
        print(f"  Validation samples: {len(X_val)}")
        print(f"  Features: {len(self.feature_names)}")

        # Class distribution
        train_dist = y_train.value_counts().sort_index()
        print(f"\nTraining label distribution:")
        print(f"  SELL (0):  {train_dist.get(0, 0)} ({train_dist.get(0, 0)/len(y_train)*100:.1f}%)")
        print(f"  HOLD (1):  {train_dist.get(1, 0)} ({train_dist.get(1, 0)/len(y_train)*100:.1f}%)")
        print(f"  BUY (2):   {train_dist.get(2, 0)} ({train_dist.get(2, 0)/len(y_train)*100:.1f}%)")

        self.model.fit(X_train_scaled, y_train)

        # Evaluate
        train_pred = self.model.predict(X_train_scaled)
        val_pred = self.model.predict(X_val_scaled)

        self.training_score = accuracy_score(y_train, train_pred)
        self.validation_score = accuracy_score(y_val, val_pred)

        print(f"\nTraining accuracy: {self.training_score:.4f}")
        print(f"Validation accuracy: {self.validation_score:.4f}")

        # Print classification report
        print("\nValidation Classification Report:")
        print(classification_report(y_val, val_pred,
                                   target_names=['SELL', 'HOLD', 'BUY'],
                                   zero_division=0))

        self.is_trained = True

        return {
            'training_accuracy': self.training_score,
            'validation_accuracy': self.validation_score,
            'n_train': len(X_train),
            'n_val': len(X_val),
            'n_features': len(self.feature_names)
        }

    def fit_time_series(self,
                       X: pd.DataFrame,
                       y: pd.Series,
                       n_splits: int = 5) -> Dict[str, float]:
        """
        Train with time series cross-validation (expanding window)

        Args:
            X: Feature matrix
            y: Target returns
            n_splits: Number of time series splits

        Returns:
            Dictionary with cross-validation metrics
        """
        # Store feature names
        self.feature_names = list(X.columns)

        # Create categorical labels
        labels = self.create_labels(y)

        # Time series split
        tscv = TimeSeriesSplit(n_splits=n_splits)

        scores = []
        print(f"\nTime Series Cross-Validation ({n_splits} splits):")

        for fold, (train_idx, val_idx) in enumerate(tscv.split(X), 1):
            X_train = X.iloc[train_idx]
            X_val = X.iloc[val_idx]
            y_train = labels.iloc[train_idx]
            y_val = labels.iloc[val_idx]

            # Scale features
            if self.model_type != 'naive_bayes':
                X_train_scaled = self.scaler.fit_transform(X_train)
                X_val_scaled = self.scaler.transform(X_val)
            else:
                X_train_scaled = X_train - X_train.min() + 1e-6
                X_val_scaled = X_val - X_train.min() + 1e-6

            # Train
            self.model.fit(X_train_scaled, y_train)

            # Evaluate
            val_pred = self.model.predict(X_val_scaled)
            score = accuracy_score(y_val, val_pred)
            scores.append(score)

            print(f"  Fold {fold}: {score:.4f} (train: {len(train_idx)}, val: {len(val_idx)})")

        mean_score = np.mean(scores)
        std_score = np.std(scores)

        print(f"\nCross-validation accuracy: {mean_score:.4f} ± {std_score:.4f}")

        self.validation_score = mean_score
        self.is_trained = True

        return {
            'cv_accuracy_mean': mean_score,
            'cv_accuracy_std': std_score,
            'fold_scores': scores
        }

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predict class labels

        Args:
            X: Feature matrix

        Returns:
            Array of predicted labels (0=SELL, 1=HOLD, 2=BUY)
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")

        # Scale features
        if self.model_type != 'naive_bayes':
            X_scaled = self.scaler.transform(X)
        else:
            X_scaled = X - X.min() + 1e-6

        return self.model.predict(X_scaled)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """
        Predict class probabilities

        Args:
            X: Feature matrix

        Returns:
            Array of shape (n_samples, 3) with probabilities for [SELL, HOLD, BUY]
        """
        if not self.is_trained:
            raise ValueError("Model must be trained before prediction")

        # Check if model supports predict_proba
        if not hasattr(self.model, 'predict_proba'):
            raise ValueError(f"{self.model_type} does not support probability predictions")

        # Scale features
        if self.model_type != 'naive_bayes':
            X_scaled = self.scaler.transform(X)
        else:
            X_scaled = X - X.min() + 1e-6

        return self.model.predict_proba(X_scaled)

    def predict_signals(self, X: pd.DataFrame) -> pd.DataFrame:
        """
        Predict trading signals with probabilities

        Args:
            X: Feature matrix

        Returns:
            DataFrame with columns: signal, signal_name, prob_sell, prob_hold, prob_buy
        """
        predictions = self.predict(X)

        result = pd.DataFrame(index=X.index)
        result['signal'] = predictions
        result['signal_name'] = result['signal'].map({0: 'SELL', 1: 'HOLD', 2: 'BUY'})

        # Add probabilities if available
        if hasattr(self.model, 'predict_proba'):
            probas = self.predict_proba(X)
            result['prob_sell'] = probas[:, 0]
            result['prob_hold'] = probas[:, 1]
            result['prob_buy'] = probas[:, 2]
            result['confidence'] = probas.max(axis=1)

        return result

    def get_feature_importance(self, top_n: int = 20) -> pd.DataFrame:
        """
        Get feature importance (for tree-based models)

        Args:
            top_n: Number of top features to return

        Returns:
            DataFrame with feature importances
        """
        if not self.is_trained:
            raise ValueError("Model must be trained first")

        if not hasattr(self.model, 'feature_importances_'):
            raise ValueError(f"{self.model_type} does not support feature importance")

        importance = pd.DataFrame({
            'feature': self.feature_names,
            'importance': self.model.feature_importances_
        }).sort_values('importance', ascending=False)

        return importance.head(top_n)

    def save_model(self, filepath: str):
        """Save trained model to disk"""
        model_data = {
            'model': self.model,
            'scaler': self.scaler,
            'model_type': self.model_type,
            'buy_threshold': self.buy_threshold,
            'sell_threshold': self.sell_threshold,
            'feature_names': self.feature_names,
            'is_trained': self.is_trained,
            'training_score': self.training_score,
            'validation_score': self.validation_score
        }

        with open(filepath, 'wb') as f:
            pickle.dump(model_data, f)

        print(f"Model saved to {filepath}")

    def load_model(self, filepath: str):
        """Load trained model from disk"""
        with open(filepath, 'rb') as f:
            model_data = pickle.load(f)

        self.model = model_data['model']
        self.scaler = model_data['scaler']
        self.model_type = model_data['model_type']
        self.buy_threshold = model_data['buy_threshold']
        self.sell_threshold = model_data['sell_threshold']
        self.feature_names = model_data['feature_names']
        self.is_trained = model_data['is_trained']
        self.training_score = model_data.get('training_score')
        self.validation_score = model_data.get('validation_score')

        print(f"Model loaded from {filepath}")
        print(f"  Model type: {self.model_type}")
        print(f"  Features: {len(self.feature_names)}")
        print(f"  Validation accuracy: {self.validation_score:.4f}")


class EnsembleSignalClassifier:
    """
    Ensemble of multiple classifiers for robust predictions
    Combines Random Forest, SVM, and MLP predictions
    """

    def __init__(self,
                 buy_threshold: float = 0.01,
                 sell_threshold: float = -0.01):
        """
        Initialize ensemble classifier

        Args:
            buy_threshold: Return threshold for BUY signal
            sell_threshold: Return threshold for SELL signal
        """
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

        # Create base classifiers
        self.classifiers = {
            'random_forest': CategoricalSignalClassifier(
                'random_forest', buy_threshold, sell_threshold
            ),
            'svm': CategoricalSignalClassifier(
                'svm', buy_threshold, sell_threshold
            ),
            'mlp': CategoricalSignalClassifier(
                'mlp', buy_threshold, sell_threshold
            )
        }

        self.is_trained = False
        self.weights = None  # Weighted voting based on validation performance

    def fit(self, X: pd.DataFrame, y: pd.Series, validation_split: float = 0.2):
        """Train all base classifiers"""
        print("\n" + "="*70)
        print("TRAINING ENSEMBLE CLASSIFIER")
        print("="*70)

        scores = {}

        for name, classifier in self.classifiers.items():
            print(f"\n--- Training {name} ---")
            metrics = classifier.fit(X, y, validation_split)
            scores[name] = metrics['validation_accuracy']

        # Calculate weights based on validation accuracy
        total_score = sum(scores.values())
        self.weights = {name: score/total_score for name, score in scores.items()}

        print("\n" + "="*70)
        print("ENSEMBLE WEIGHTS (based on validation accuracy):")
        for name, weight in self.weights.items():
            print(f"  {name}: {weight:.4f} (accuracy: {scores[name]:.4f})")
        print("="*70)

        self.is_trained = True

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """Predict using weighted voting"""
        if not self.is_trained:
            raise ValueError("Ensemble must be trained first")

        # Get predictions from all classifiers
        predictions = {}
        for name, classifier in self.classifiers.items():
            predictions[name] = classifier.predict(X)

        # Weighted voting
        weighted_votes = np.zeros((len(X), 3))  # 3 classes

        for name, preds in predictions.items():
            weight = self.weights[name]
            for i, pred in enumerate(preds):
                weighted_votes[i, pred] += weight

        # Final prediction: argmax of weighted votes
        final_predictions = weighted_votes.argmax(axis=1)

        return final_predictions

    def predict_signals(self, X: pd.DataFrame) -> pd.DataFrame:
        """Predict trading signals with ensemble voting"""
        predictions = self.predict(X)

        result = pd.DataFrame(index=X.index)
        result['signal'] = predictions
        result['signal_name'] = result['signal'].map({0: 'SELL', 1: 'HOLD', 2: 'BUY'})

        # Add individual classifier predictions
        for name, classifier in self.classifiers.items():
            result[f'{name}_signal'] = classifier.predict(X)

        return result
