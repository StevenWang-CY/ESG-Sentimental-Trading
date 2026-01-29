"""
Unit Tests for Walk-Forward Validation Framework

Tests ensure:
1. No look-ahead bias in validation windows
2. Proper train/test separation with embargo
3. Correct weight derivation from training data only
4. Aggregate metrics calculation
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.validation.walk_forward_validator import (
    ValidationWindow,
    ValidationResult,
    WalkForwardValidator,
    WeightOptimizer,
    SignalWeights,
    WeightingMethod,
    AggregateMetrics,
)


class TestValidationWindow:
    """Tests for ValidationWindow dataclass."""

    def test_valid_window_creation(self):
        """Test creating a valid validation window."""
        window = ValidationWindow(
            train_start=datetime(2020, 1, 1),
            train_end=datetime(2021, 1, 1),
            test_start=datetime(2021, 1, 6),  # 5-day embargo
            test_end=datetime(2021, 4, 1),
        )
        assert window.embargo_days == 5
        assert window.train_months > 11  # ~12 months

    def test_invalid_window_train_after_test(self):
        """Test that train_end >= test_start raises error."""
        with pytest.raises(ValueError, match="Training must end before test starts"):
            ValidationWindow(
                train_start=datetime(2020, 1, 1),
                train_end=datetime(2021, 1, 10),  # After test_start
                test_start=datetime(2021, 1, 5),
                test_end=datetime(2021, 4, 1),
            )

    def test_invalid_train_window(self):
        """Test that invalid training window raises error."""
        with pytest.raises(ValueError, match="Invalid training window"):
            ValidationWindow(
                train_start=datetime(2021, 1, 1),  # After train_end
                train_end=datetime(2020, 1, 1),
                test_start=datetime(2021, 1, 6),
                test_end=datetime(2021, 4, 1),
            )


class TestSignalWeights:
    """Tests for SignalWeights dataclass."""

    def test_weights_must_sum_to_one(self):
        """Test that weights must sum to 1.0."""
        # Valid weights
        weights = SignalWeights(
            event_severity=0.25,
            intensity=0.25,
            volume=0.25,
            duration=0.25,
        )
        assert abs(sum([
            weights.event_severity,
            weights.intensity,
            weights.volume,
            weights.duration,
            weights.momentum,
        ]) - 1.0) < 0.001

    def test_weights_not_summing_to_one_raises_error(self):
        """Test that weights not summing to 1.0 raises error."""
        with pytest.raises(ValueError, match="Weights must sum to 1.0"):
            SignalWeights(
                event_severity=0.3,
                intensity=0.3,
                volume=0.3,
                duration=0.3,  # Total = 1.2
            )

    def test_equal_weights(self):
        """Test equal weight creation."""
        weights = SignalWeights.from_equal_weight(n_components=4)
        assert weights.event_severity == 0.25
        assert weights.intensity == 0.25
        assert weights.volume == 0.25
        assert weights.duration == 0.25

    def test_inverse_variance_weights(self):
        """Test inverse variance weight derivation."""
        # Create sample historical data
        np.random.seed(42)
        features = pd.DataFrame({
            'event_severity': np.random.uniform(0.3, 0.7, 100),  # Low variance
            'intensity': np.random.uniform(0, 1, 100),  # Higher variance
            'volume': np.random.uniform(0.2, 0.8, 100),  # Medium variance
            'duration': np.random.uniform(0.4, 0.6, 100),  # Very low variance
        })

        weights = SignalWeights.from_inverse_variance(features, lookback_days=100)

        # Lower variance components should get higher weight
        # duration has lowest variance, should have highest weight
        assert weights.duration > weights.intensity
        # Weights should sum to 1.0
        assert abs(sum([
            weights.event_severity,
            weights.intensity,
            weights.volume,
            weights.duration,
        ]) - 1.0) < 0.001


class TestWalkForwardValidator:
    """Tests for WalkForwardValidator."""

    def test_window_generation(self):
        """Test that validation windows are generated correctly."""
        validator = WalkForwardValidator(
            min_train_months=12,
            test_months=3,
            step_months=3,
            embargo_days=5,
        )

        start = datetime(2020, 1, 1)
        end = datetime(2023, 1, 1)  # 3 years of data

        windows = validator.generate_windows(start, end)

        # Should generate multiple windows
        assert len(windows) >= 4

        # Each window should have proper ordering
        for window in windows:
            assert window.train_start == start  # Expanding window
            assert window.train_end < window.test_start
            assert window.test_start < window.test_end
            assert (window.test_start - window.train_end).days >= 5  # Embargo

    def test_no_future_data_in_training(self):
        """CRITICAL: Test that training never uses future data."""
        validator = WalkForwardValidator(
            min_train_months=12,
            test_months=3,
            step_months=3,
            embargo_days=5,
        )

        windows = validator.generate_windows(
            datetime(2020, 1, 1),
            datetime(2023, 1, 1),
        )

        for window in windows:
            # CRITICAL: Train end must be BEFORE test start
            assert window.train_end < window.test_start, \
                f"Look-ahead bias: train_end={window.train_end} >= test_start={window.test_start}"

            # CRITICAL: Embargo gap must exist
            gap_days = (window.test_start - window.train_end).days
            assert gap_days >= validator.embargo_days, \
                f"Insufficient embargo: {gap_days} days < {validator.embargo_days} required"

    def test_expanding_window(self):
        """Test that training window expands over time."""
        validator = WalkForwardValidator(
            min_train_months=12,
            test_months=3,
            step_months=3,
        )

        windows = validator.generate_windows(
            datetime(2020, 1, 1),
            datetime(2023, 1, 1),
        )

        # All windows should start from same date (expanding)
        assert all(w.train_start == windows[0].train_start for w in windows)

        # Training end should increase over time
        for i in range(1, len(windows)):
            assert windows[i].train_end > windows[i-1].train_end


class TestValidationResult:
    """Tests for ValidationResult dataclass."""

    def test_overfit_ratio_calculation(self):
        """Test overfit ratio calculation."""
        window = ValidationWindow(
            train_start=datetime(2020, 1, 1),
            train_end=datetime(2021, 1, 1),
            test_start=datetime(2021, 1, 6),
            test_end=datetime(2021, 4, 1),
        )

        result = ValidationResult(
            window=window,
            train_sharpe=1.0,
            test_sharpe=0.6,
            train_n_trades=50,
            test_n_trades=15,
            optimal_params={},
        )

        assert result.overfit_ratio == 0.6  # test/train = 0.6/1.0

    def test_overfit_ratio_zero_train_sharpe(self):
        """Test overfit ratio when train Sharpe is zero."""
        window = ValidationWindow(
            train_start=datetime(2020, 1, 1),
            train_end=datetime(2021, 1, 1),
            test_start=datetime(2021, 1, 6),
            test_end=datetime(2021, 4, 1),
        )

        result = ValidationResult(
            window=window,
            train_sharpe=0.0,
            test_sharpe=0.5,
            train_n_trades=50,
            test_n_trades=15,
            optimal_params={},
        )

        assert result.overfit_ratio == 0.0  # Avoid division by zero

    def test_is_profitable_oos(self):
        """Test out-of-sample profitability check."""
        window = ValidationWindow(
            train_start=datetime(2020, 1, 1),
            train_end=datetime(2021, 1, 1),
            test_start=datetime(2021, 1, 6),
            test_end=datetime(2021, 4, 1),
        )

        profitable = ValidationResult(
            window=window,
            train_sharpe=1.0,
            test_sharpe=0.1,  # Positive
            train_n_trades=50,
            test_n_trades=15,
            optimal_params={},
        )
        assert profitable.is_profitable_oos is True

        unprofitable = ValidationResult(
            window=window,
            train_sharpe=1.0,
            test_sharpe=-0.1,  # Negative
            train_n_trades=50,
            test_n_trades=15,
            optimal_params={},
        )
        assert unprofitable.is_profitable_oos is False


class TestAggregateMetrics:
    """Tests for aggregate metrics calculation."""

    def test_passes_minimum_criteria(self):
        """Test minimum criteria check."""
        # Passing case
        passing = AggregateMetrics(
            mean_train_sharpe=1.0,
            mean_test_sharpe=0.5,
            std_test_sharpe=0.3,
            mean_overfit_ratio=0.5,
            pct_profitable_oos=0.6,
            worst_oos_sharpe=-0.1,
            best_oos_sharpe=1.0,
            n_folds=5,
            total_oos_trades=100,
        )
        assert passing.passes_minimum_criteria is True

        # Failing case - negative OOS Sharpe
        failing_sharpe = AggregateMetrics(
            mean_train_sharpe=1.0,
            mean_test_sharpe=-0.1,  # Negative
            std_test_sharpe=0.3,
            mean_overfit_ratio=0.5,
            pct_profitable_oos=0.6,
            worst_oos_sharpe=-0.5,
            best_oos_sharpe=0.5,
            n_folds=5,
            total_oos_trades=100,
        )
        assert failing_sharpe.passes_minimum_criteria is False

        # Failing case - severe overfitting
        failing_overfit = AggregateMetrics(
            mean_train_sharpe=1.0,
            mean_test_sharpe=0.2,
            std_test_sharpe=0.3,
            mean_overfit_ratio=0.2,  # Below 0.4 threshold
            pct_profitable_oos=0.6,
            worst_oos_sharpe=-0.1,
            best_oos_sharpe=0.5,
            n_folds=5,
            total_oos_trades=100,
        )
        assert failing_overfit.passes_minimum_criteria is False


class TestWeightOptimizer:
    """Tests for weight optimization."""

    def test_equal_weights_method(self):
        """Test equal weighting method."""
        optimizer = WeightOptimizer(method=WeightingMethod.EQUAL)

        # Should return equal weights regardless of input
        weights = optimizer.optimize(
            train_signals=pd.DataFrame(),
            train_returns=pd.Series(),
        )

        assert weights.event_severity == 0.25
        assert weights.intensity == 0.25
        assert weights.volume == 0.25
        assert weights.duration == 0.25

    def test_inverse_variance_method(self):
        """Test inverse variance weighting method."""
        optimizer = WeightOptimizer(
            method=WeightingMethod.INVERSE_VARIANCE,
            lookback_days=50,
        )

        # Create sample data
        np.random.seed(42)
        signals = pd.DataFrame({
            'event_confidence': np.random.uniform(0.4, 0.6, 100),  # Low var
            'sentiment_intensity': np.random.uniform(-1, 1, 100),  # High var
            'volume_ratio': np.random.uniform(1, 5, 100),
        })

        returns = pd.Series(np.random.normal(0.001, 0.02, 100))

        weights = optimizer.optimize(signals, returns)

        # Should return valid weights
        total = (
            weights.event_severity +
            weights.intensity +
            weights.volume +
            weights.duration
        )
        assert abs(total - 1.0) < 0.001


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
