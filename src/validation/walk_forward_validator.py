"""
Walk-Forward Validation Framework for ESG Strategy

Implements proper walk-forward validation to eliminate look-ahead bias and provide
realistic out-of-sample performance estimates.

Key principles:
1. At any point t, only use data from [0, t) for training
2. Testing is done on [t, t+test_period) with an embargo gap
3. Parameters derived from training data ONLY
4. No peeking at future data for any calibration

Academic references:
- Bailey, D. H., & Lopez de Prado, M. (2014). The deflated Sharpe ratio
- Harvey, C. R., & Liu, Y. (2015). Backtesting
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Protocol, TypeAlias
from enum import Enum, auto


# Type aliases for clarity
Weight: TypeAlias = float
Score: TypeAlias = float


@dataclass(frozen=True)
class ValidationWindow:
    """
    Immutable time window for validation.

    Ensures train_end < test_start with mandatory embargo gap.
    """
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime

    def __post_init__(self) -> None:
        """Validate window integrity."""
        if self.train_end >= self.test_start:
            raise ValueError(
                f"Training must end before test starts. "
                f"train_end={self.train_end}, test_start={self.test_start}"
            )
        if self.train_start >= self.train_end:
            raise ValueError(
                f"Invalid training window: start={self.train_start}, end={self.train_end}"
            )
        if self.test_start >= self.test_end:
            raise ValueError(
                f"Invalid test window: start={self.test_start}, end={self.test_end}"
            )

    @property
    def embargo_days(self) -> int:
        """Gap between training end and test start."""
        return (self.test_start - self.train_end).days

    @property
    def train_months(self) -> float:
        """Approximate training period in months."""
        return (self.train_end - self.train_start).days / 30.0

    @property
    def test_months(self) -> float:
        """Approximate test period in months."""
        return (self.test_end - self.test_start).days / 30.0


@dataclass
class ValidationResult:
    """Results from a single validation fold."""
    window: ValidationWindow
    train_sharpe: float
    test_sharpe: float
    train_n_trades: int
    test_n_trades: int
    optimal_params: Dict
    train_return: float = 0.0
    test_return: float = 0.0
    train_max_drawdown: float = 0.0
    test_max_drawdown: float = 0.0

    @property
    def overfit_ratio(self) -> float:
        """
        Ratio of test/train Sharpe.

        <0.5 indicates severe overfitting
        0.5-0.8 indicates moderate overfitting
        >0.8 indicates reasonable generalization
        """
        if abs(self.train_sharpe) < 0.001:
            return 0.0
        return self.test_sharpe / self.train_sharpe

    @property
    def is_profitable_oos(self) -> bool:
        """Check if out-of-sample performance is positive."""
        return self.test_sharpe > 0


@dataclass
class AggregateMetrics:
    """Aggregate metrics across all validation folds.

    Includes deflated Sharpe ratio (Bailey & Lopez de Prado 2014) for
    multiple-testing-aware inference: when many folds/configurations are
    evaluated, the naively-best observed Sharpe is an upwardly biased
    estimate of the true Sharpe.
    """
    mean_train_sharpe: float
    mean_test_sharpe: float
    std_test_sharpe: float
    mean_overfit_ratio: float
    pct_profitable_oos: float
    worst_oos_sharpe: float
    best_oos_sharpe: float
    n_folds: int
    total_oos_trades: int
    deflated_sharpe: float = 0.0
    probabilistic_sharpe: float = 0.0

    def __str__(self) -> str:
        return (
            f"Walk-Forward Validation Results ({self.n_folds} folds):\n"
            f"  Mean Train Sharpe:      {self.mean_train_sharpe:.3f}\n"
            f"  Mean Test Sharpe:       {self.mean_test_sharpe:.3f} (std: {self.std_test_sharpe:.3f})\n"
            f"  Probabilistic Sharpe:   {self.probabilistic_sharpe:.2%}\n"
            f"  Deflated Sharpe:        {self.deflated_sharpe:.2%}\n"
            f"  Overfit Ratio:          {self.mean_overfit_ratio:.2f}\n"
            f"  % Profitable OOS:       {self.pct_profitable_oos:.1%}\n"
            f"  Worst OOS Sharpe:       {self.worst_oos_sharpe:.3f}\n"
            f"  Best OOS Sharpe:        {self.best_oos_sharpe:.3f}\n"
            f"  Total OOS Trades:       {self.total_oos_trades}"
        )

    @property
    def passes_minimum_criteria(self) -> bool:
        """
        Check if strategy passes minimum validation criteria.

        Criteria (tightened after refinement audit):
        1. Mean OOS Sharpe > 0 (positive expected return)
        2. Overfit ratio > 0.4 (not severely overfitted)
        3. At least 50% of folds profitable
        4. Deflated Sharpe ≥ 0.90 (≥90% confidence true SR > selection-adjusted benchmark)

        The DSR gate is the critical addition: without it, walk-forward
        validation still permits selection-bias inflation when the test
        set ends up favorable by chance.
        """
        return (
            self.mean_test_sharpe > 0 and
            self.mean_overfit_ratio > 0.4 and
            self.pct_profitable_oos >= 0.5 and
            self.deflated_sharpe >= 0.90
        )


class WeightingMethod(Enum):
    """Methods for deriving signal component weights."""
    EQUAL = auto()              # 1/n equal weights (baseline)
    INVERSE_VARIANCE = auto()   # 1/var(component) - lower variance = higher weight
    CORRELATION_BASED = auto()  # Based on correlation with forward returns


@dataclass(frozen=True)
class SignalWeights:
    """
    Immutable signal component weights.

    Ensures weights always sum to 1.0 for proper score normalization.
    """
    event_severity: Weight
    intensity: Weight
    volume: Weight
    duration: Weight
    momentum: Weight = 0.0

    def __post_init__(self) -> None:
        """Validate weights sum to 1.0."""
        total = (
            self.event_severity +
            self.intensity +
            self.volume +
            self.duration +
            self.momentum
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total:.4f}")

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary format."""
        return {
            'event_severity': self.event_severity,
            'intensity': self.intensity,
            'volume': self.volume,
            'duration': self.duration,
            'sentiment_volume_momentum': self.momentum,
        }

    @classmethod
    def from_equal_weight(cls, n_components: int = 4) -> SignalWeights:
        """Create equal-weighted configuration."""
        w = 1.0 / n_components
        return cls(event_severity=w, intensity=w, volume=w, duration=w, momentum=0.0)

    @classmethod
    def from_inverse_variance(
        cls,
        historical_features: pd.DataFrame,
        lookback_days: int = 252
    ) -> SignalWeights:
        """
        Derive weights from inverse variance of each component.

        Components with lower variance get higher weight (more stable signal).
        Uses only data available at calibration time.

        Args:
            historical_features: DataFrame with component columns
            lookback_days: Number of days to use for variance calculation
        """
        components = ['event_severity', 'intensity', 'volume', 'duration']

        # Use only most recent lookback_days
        recent_data = historical_features.tail(lookback_days)

        if len(recent_data) < 20:
            # Not enough data, fall back to equal weights
            return cls.from_equal_weight()

        # Calculate variance for each component
        variances = {}
        for c in components:
            if c in recent_data.columns:
                var = recent_data[c].var()
                # Add small epsilon to avoid division by zero
                variances[c] = max(var, 1e-6)
            else:
                variances[c] = 1.0  # Default variance

        # Inverse variance weighting
        inv_var_total = sum(1/v for v in variances.values())
        weights = {c: (1/variances[c]) / inv_var_total for c in components}

        return cls(
            event_severity=weights['event_severity'],
            intensity=weights['intensity'],
            volume=weights['volume'],
            duration=weights['duration'],
            momentum=0.0
        )

    @classmethod
    def from_correlation(
        cls,
        historical_features: pd.DataFrame,
        forward_returns: pd.Series,
        lookback_days: int = 252
    ) -> SignalWeights:
        """
        Derive weights from correlation with forward returns.

        Higher absolute correlation = higher weight.
        Uses only data available at calibration time.

        Args:
            historical_features: DataFrame with component columns
            forward_returns: Series of forward returns (t+1)
            lookback_days: Number of days for correlation calculation
        """
        components = ['event_severity', 'intensity', 'volume', 'duration']

        # Align features with returns
        recent_features = historical_features.tail(lookback_days)
        recent_returns = forward_returns.loc[recent_features.index] if hasattr(forward_returns, 'loc') else forward_returns.tail(lookback_days)

        if len(recent_features) < 20:
            return cls.from_equal_weight()

        # Calculate correlations
        correlations = {}
        for c in components:
            if c in recent_features.columns:
                corr = recent_features[c].corr(recent_returns)
                # Use absolute correlation (both positive and negative are predictive)
                correlations[c] = abs(corr) if not np.isnan(corr) else 0.01
            else:
                correlations[c] = 0.01

        # Normalize to sum to 1
        total_corr = sum(correlations.values())
        if total_corr < 0.001:
            return cls.from_equal_weight()

        weights = {c: correlations[c] / total_corr for c in components}

        return cls(
            event_severity=weights['event_severity'],
            intensity=weights['intensity'],
            volume=weights['volume'],
            duration=weights['duration'],
            momentum=0.0
        )


class WeightOptimizer:
    """
    Optimizer for signal weights using only training data.

    CRITICAL: Never uses test data for optimization.
    """

    def __init__(
        self,
        method: WeightingMethod = WeightingMethod.INVERSE_VARIANCE,
        lookback_days: int = 252
    ):
        self.method = method
        self.lookback_days = lookback_days

    def optimize(
        self,
        train_signals: pd.DataFrame,
        train_returns: pd.Series,
    ) -> SignalWeights:
        """
        Optimize weights using training data ONLY.

        Args:
            train_signals: Training signals with feature columns
            train_returns: Training period returns

        Returns:
            Optimized SignalWeights
        """
        if self.method == WeightingMethod.EQUAL:
            return SignalWeights.from_equal_weight()

        # Extract features from signals
        feature_columns = ['event_confidence', 'sentiment_intensity', 'volume_ratio']

        if not all(col in train_signals.columns for col in feature_columns):
            print("Warning: Missing feature columns, using equal weights")
            return SignalWeights.from_equal_weight()

        # Create features DataFrame
        features = pd.DataFrame({
            'event_severity': train_signals['event_confidence'].values,
            'intensity': (train_signals['sentiment_intensity'].values + 1) / 2,  # Normalize to [0,1]
            'volume': np.minimum(np.log1p(train_signals['volume_ratio'].values) / np.log(10), 1.0),
            'duration': train_signals.get('duration_days', pd.Series([3.5] * len(train_signals))).values / 7.0,
        }, index=train_signals.index if hasattr(train_signals, 'index') else None)

        if self.method == WeightingMethod.INVERSE_VARIANCE:
            return SignalWeights.from_inverse_variance(
                features,
                self.lookback_days
            )

        elif self.method == WeightingMethod.CORRELATION_BASED:
            return SignalWeights.from_correlation(
                features,
                train_returns,
                self.lookback_days
            )

        raise ValueError(f"Unknown weighting method: {self.method}")


class WalkForwardValidator:
    """
    Walk-forward validation with expanding window.

    Key principle: At any point t, we only use data from [0, t) for training.
    Testing is done on [t, t+test_period) with an embargo gap.

    This ensures:
    1. No future data leakage in parameter optimization
    2. Realistic out-of-sample performance estimates
    3. Detection of overfitting through train/test performance comparison
    """

    def __init__(
        self,
        min_train_months: int = 12,
        test_months: int = 3,
        step_months: int = 3,
        embargo_days: int = 5,
    ):
        """
        Initialize walk-forward validator.

        Args:
            min_train_months: Minimum training period in months
            test_months: Test period length in months
            step_months: Step size between folds in months
            embargo_days: Gap between train and test to prevent leakage
        """
        self.min_train_months = min_train_months
        self.test_months = test_months
        self.step_months = step_months
        self.embargo_days = embargo_days

    def generate_windows(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> List[ValidationWindow]:
        """
        Generate expanding window validation splits.

        Uses expanding window (not rolling) to maximize training data
        while maintaining strict temporal ordering.

        Args:
            start_date: Earliest date in dataset
            end_date: Latest date in dataset

        Returns:
            List of ValidationWindow objects
        """
        windows = []

        # Calculate initial train end
        train_end = start_date + timedelta(days=self.min_train_months * 30)

        while True:
            # Calculate test window
            test_start = train_end + timedelta(days=self.embargo_days)
            test_end = test_start + timedelta(days=self.test_months * 30)

            # Stop if test window exceeds data range
            if test_end > end_date:
                break

            windows.append(ValidationWindow(
                train_start=start_date,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end
            ))

            # Expand training window
            train_end += timedelta(days=self.step_months * 30)

        return windows

    def validate(
        self,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
        optimizer: WeightOptimizer,
        backtest_fn: Callable,
    ) -> List[ValidationResult]:
        """
        Run walk-forward validation.

        Args:
            signals: All signals with date column
            prices: Price data for backtesting
            optimizer: Weight optimizer to use
            backtest_fn: Function that runs backtest and returns (sharpe, n_trades, total_return, max_dd)

        Returns:
            List of ValidationResult for each time window
        """
        # Ensure date column is datetime
        signals = signals.copy()
        signals['date'] = pd.to_datetime(signals['date'])

        # Get date range
        start_date = signals['date'].min()
        end_date = signals['date'].max()

        # Generate windows
        windows = self.generate_windows(start_date, end_date)

        if not windows:
            raise ValueError(
                f"Cannot generate validation windows. "
                f"Data range ({start_date} to {end_date}) is too short for "
                f"min_train_months={self.min_train_months} + test_months={self.test_months}"
            )

        print(f"\nWalk-Forward Validation: {len(windows)} folds")
        print(f"  Training: {self.min_train_months}+ months (expanding)")
        print(f"  Testing:  {self.test_months} months")
        print(f"  Embargo:  {self.embargo_days} days")

        results = []

        for i, window in enumerate(windows):
            print(f"\n--- Fold {i+1}/{len(windows)} ---")
            print(f"  Train: {window.train_start.date()} to {window.train_end.date()}")
            print(f"  Test:  {window.test_start.date()} to {window.test_end.date()}")

            # Split data - CRITICAL: no future data in training
            train_signals = signals[
                (signals['date'] >= window.train_start) &
                (signals['date'] < window.train_end)
            ].copy()

            test_signals = signals[
                (signals['date'] >= window.test_start) &
                (signals['date'] < window.test_end)
            ].copy()

            print(f"  Train signals: {len(train_signals)}")
            print(f"  Test signals:  {len(test_signals)}")

            if len(train_signals) < 10:
                print(f"  SKIPPING: Insufficient training signals")
                continue

            if len(test_signals) < 5:
                print(f"  SKIPPING: Insufficient test signals")
                continue

            # Optimize on training data ONLY
            # Get returns for training period (for correlation-based weighting)
            train_mask = (
                (prices.index.get_level_values(0) >= window.train_start) &
                (prices.index.get_level_values(0) < window.train_end)
            ) if isinstance(prices.index, pd.MultiIndex) else (
                (prices.index >= window.train_start) &
                (prices.index < window.train_end)
            )

            train_returns = pd.Series([0.0])  # Placeholder if returns not available

            optimal_weights = optimizer.optimize(train_signals, train_returns)
            print(f"  Optimal weights: {optimal_weights.to_dict()}")

            # Backtest on training data
            train_sharpe, train_n_trades, train_return, train_dd = backtest_fn(
                train_signals, prices, optimal_weights.to_dict(),
                window.train_start, window.train_end
            )

            # Backtest on test data with SAME weights (no re-optimization)
            test_sharpe, test_n_trades, test_return, test_dd = backtest_fn(
                test_signals, prices, optimal_weights.to_dict(),
                window.test_start, window.test_end
            )

            print(f"  Train Sharpe: {train_sharpe:.3f} ({train_n_trades} trades)")
            print(f"  Test Sharpe:  {test_sharpe:.3f} ({test_n_trades} trades)")
            print(f"  Overfit Ratio: {test_sharpe/train_sharpe:.2f}" if train_sharpe != 0 else "  Overfit Ratio: N/A")

            results.append(ValidationResult(
                window=window,
                train_sharpe=train_sharpe,
                test_sharpe=test_sharpe,
                train_n_trades=train_n_trades,
                test_n_trades=test_n_trades,
                optimal_params=optimal_weights.to_dict(),
                train_return=train_return,
                test_return=test_return,
                train_max_drawdown=train_dd,
                test_max_drawdown=test_dd,
            ))

        return results

    def compute_aggregate_metrics(
        self,
        results: List[ValidationResult]
    ) -> AggregateMetrics:
        """
        Compute aggregate validation metrics.

        Args:
            results: List of ValidationResult from each fold

        Returns:
            AggregateMetrics with summary statistics
        """
        if not results:
            raise ValueError("No validation results to aggregate")

        train_sharpes = [r.train_sharpe for r in results]
        test_sharpes = [r.test_sharpe for r in results]
        overfit_ratios = [r.overfit_ratio for r in results if r.train_sharpe != 0]

        mean_test_sharpe = float(np.mean(test_sharpes))
        std_test_sharpe = float(np.std(test_sharpes, ddof=1)) if len(test_sharpes) > 1 else 0.0

        # --- Probabilistic Sharpe & Deflated Sharpe --------------------------
        # Bailey & Lopez de Prado (2012, 2014). Here we treat each fold's
        # test-Sharpe as one observation; variance across folds proxies the
        # estimation variance. This answers: given that we ran N folds, how
        # likely is it that the realized average is not noise?
        from scipy import stats as _stats
        n_folds = len(test_sharpes)

        if n_folds >= 2 and std_test_sharpe > 0:
            # Probabilistic Sharpe (benchmark = 0): P(true SR > 0 | observed SR)
            # PSR = Φ( SR * sqrt(n-1) ) under Gaussian approximation.
            # Using SR_mean and cross-fold variance as the Sharpe estimate.
            t_stat = mean_test_sharpe / (std_test_sharpe / np.sqrt(n_folds))
            probabilistic_sharpe = float(_stats.norm.cdf(t_stat))

            # Deflated Sharpe: adjust benchmark for selection from N trials.
            # Expected max of N SRs under null (order statistic approximation).
            euler_mascheroni = 0.5772156649
            max_z = (
                (1.0 - euler_mascheroni) * _stats.norm.ppf(1.0 - 1.0 / n_folds) +
                euler_mascheroni * _stats.norm.ppf(1.0 - 1.0 / (n_folds * np.e))
            )
            sr_benchmark = std_test_sharpe * max_z
            t_stat_deflated = (mean_test_sharpe - sr_benchmark) / (std_test_sharpe / np.sqrt(n_folds))
            deflated_sharpe = float(_stats.norm.cdf(t_stat_deflated))
        else:
            probabilistic_sharpe = 1.0 if mean_test_sharpe > 0 else 0.0
            deflated_sharpe = 0.5  # Insufficient data for deflation

        return AggregateMetrics(
            mean_train_sharpe=float(np.mean(train_sharpes)),
            mean_test_sharpe=mean_test_sharpe,
            std_test_sharpe=std_test_sharpe,
            mean_overfit_ratio=float(np.mean(overfit_ratios)) if overfit_ratios else 0.0,
            pct_profitable_oos=sum(1 for s in test_sharpes if s > 0) / len(test_sharpes),
            worst_oos_sharpe=float(min(test_sharpes)),
            best_oos_sharpe=float(max(test_sharpes)),
            n_folds=n_folds,
            total_oos_trades=sum(r.test_n_trades for r in results),
            deflated_sharpe=deflated_sharpe,
            probabilistic_sharpe=probabilistic_sharpe,
        )


def create_backtest_function(
    BacktestEngine,
    initial_capital: float = 1_000_000,
    commission_pct: float = 0.0005,
    slippage_bps: float = 3.0,
    rebalance_freq: str = 'W',
    holding_period: int = 49,
    enable_risk_management: bool = False,
    max_position_size: float = 0.10,
    target_volatility: float = 0.18,
    max_drawdown_threshold: float = 0.15,
    adaptive_drawdown_thresholds: bool = True,
    leverage_limit: float = 1.0,
    balance_long_short: bool = True,
) -> Callable:
    """
    Create a backtest function compatible with walk-forward validation.

    Args:
        BacktestEngine: The backtest engine class to use
        initial_capital: Starting capital
        commission_pct: Commission percentage
        slippage_bps: Slippage in basis points

    Returns:
        Callable that runs backtest and returns (sharpe, n_trades, total_return, max_dd)
    """
    def backtest_fn(
        signals: pd.DataFrame,
        prices: pd.DataFrame,
        weights: Dict,
        start_date: datetime,
        end_date: datetime,
    ) -> tuple:
        """Run backtest and return metrics."""
        try:
            # Filter prices to date range
            if isinstance(prices.index, pd.MultiIndex):
                date_mask = (
                    (prices.index.get_level_values(0) >= start_date) &
                    (prices.index.get_level_values(0) <= end_date)
                )
            else:
                date_mask = (prices.index >= start_date) & (prices.index <= end_date)

            period_prices = prices[date_mask]

            if period_prices.empty:
                return 0.0, 0, 0.0, 0.0

            # Run backtest
            engine = BacktestEngine(
                prices=period_prices,
                initial_capital=initial_capital,
                commission_pct=commission_pct,
                slippage_bps=slippage_bps,
                enable_risk_management=enable_risk_management,
                max_position_size=max_position_size,
                target_volatility=target_volatility,
                max_drawdown_threshold=max_drawdown_threshold,
                adaptive_drawdown_thresholds=adaptive_drawdown_thresholds,
                leverage_limit=leverage_limit,
                balance_long_short=balance_long_short,
            )

            result = engine.run(
                signals,
                rebalance_freq=rebalance_freq,
                holding_period=holding_period,
            )

            # Calculate metrics
            returns = result.get_daily_returns()

            if len(returns) < 2:
                return 0.0, 0, 0.0, 0.0

            # Sharpe ratio (annualized)
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0.0

            # Number of trades
            n_trades = len(result.trades) if hasattr(result, 'trades') else 0

            # Total return
            total_return = result.get_total_return()

            # Max drawdown
            equity = result.get_equity_curve()
            if len(equity) > 0:
                rolling_max = equity.expanding().max()
                drawdown = (equity - rolling_max) / rolling_max
                max_dd = drawdown.min()
            else:
                max_dd = 0.0

            return sharpe, n_trades, total_return, max_dd

        except Exception as e:
            print(f"Backtest error: {e}")
            return 0.0, 0, 0.0, 0.0

    return backtest_fn
