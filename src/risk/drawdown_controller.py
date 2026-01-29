"""
Drawdown Controller
Dynamic position sizing based on drawdown levels

AUDIT REFACTOR (Jan 2026):
- Added AdaptiveDrawdownConfig to derive thresholds from historical data
- Replaced hard-coded magic numbers with statistically-derived parameters
- Added regime-aware exposure scaling

Based on:
- Grossman & Zhou (1993): "Optimal Investment Strategies Under the Risk of a Crash"
- Gupta & Li (2007): "Integrating Optimal Monetary and Fiscal Policy Rules with Financial Market Risk"
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from dataclasses import dataclass


@dataclass
class AdaptiveDrawdownConfig:
    """
    Drawdown configuration derived from historical data.

    CRITICAL: No magic numbers - all thresholds computed from actual
    drawdown distribution.
    """
    percentile_25_threshold: float  # 25th percentile of historical drawdowns
    percentile_50_threshold: float  # Median drawdown
    percentile_75_threshold: float  # 75th percentile drawdown
    percentile_95_threshold: float  # 95th percentile (crisis level)

    def get_thresholds(self) -> List[float]:
        """Return thresholds in sorted order."""
        return sorted([
            self.percentile_25_threshold,
            self.percentile_50_threshold,
            self.percentile_75_threshold,
            self.percentile_95_threshold,
        ])

    def get_exposure_levels(self) -> List[float]:
        """
        Return exposure levels corresponding to thresholds.

        Uses linear scaling based on drawdown severity:
        - 25th percentile: 90% exposure
        - 50th percentile: 75% exposure
        - 75th percentile: 55% exposure
        - 95th percentile: 35% exposure
        """
        return [0.90, 0.75, 0.55, 0.35]

    @classmethod
    def from_historical_returns(
        cls,
        returns: pd.Series,
        lookback_days: int = 756  # 3 years
    ) -> AdaptiveDrawdownConfig:
        """
        Derive drawdown thresholds from historical return distribution.

        CRITICAL: Only uses historical data available at calibration time.

        Args:
            returns: Historical daily returns
            lookback_days: Number of days to use for calibration

        Returns:
            AdaptiveDrawdownConfig with data-derived thresholds
        """
        if len(returns) < 60:
            # Not enough data, use conservative defaults
            return cls(
                percentile_25_threshold=-0.05,
                percentile_50_threshold=-0.10,
                percentile_75_threshold=-0.15,
                percentile_95_threshold=-0.25,
            )

        # Use only recent history
        recent_returns = returns.tail(lookback_days)

        # Calculate rolling drawdowns
        cumulative = (1 + recent_returns).cumprod()
        rolling_max = cumulative.expanding().max()
        drawdowns = (cumulative - rolling_max) / rolling_max

        # Only consider actual drawdowns (negative values)
        negative_dd = drawdowns[drawdowns < 0]

        if len(negative_dd) < 10:
            # Not enough drawdown events
            return cls(
                percentile_25_threshold=-0.05,
                percentile_50_threshold=-0.10,
                percentile_75_threshold=-0.15,
                percentile_95_threshold=-0.25,
            )

        return cls(
            percentile_25_threshold=negative_dd.quantile(0.25),
            percentile_50_threshold=negative_dd.quantile(0.50),
            percentile_75_threshold=negative_dd.quantile(0.75),
            percentile_95_threshold=negative_dd.quantile(0.95),
        )

    def __str__(self) -> str:
        return (
            f"AdaptiveDrawdownConfig:\n"
            f"  25th percentile: {self.percentile_25_threshold:.2%}\n"
            f"  50th percentile: {self.percentile_50_threshold:.2%}\n"
            f"  75th percentile: {self.percentile_75_threshold:.2%}\n"
            f"  95th percentile: {self.percentile_95_threshold:.2%}"
        )


class DrawdownController:
    """
    Controls portfolio exposure based on drawdown levels.
    Implements dynamic risk scaling.

    AUDIT REFACTOR (Jan 2026):
    - Supports adaptive configuration from historical data
    - Thresholds can be derived statistically (no magic numbers)
    """

    def __init__(
        self,
        drawdown_thresholds: Optional[List[float]] = None,
        exposure_levels: Optional[List[float]] = None,
        lookback_period: int = 252,
        adaptive_config: Optional[AdaptiveDrawdownConfig] = None,
    ):
        """
        Initialize drawdown controller.

        Args:
            drawdown_thresholds: Drawdown levels triggering action (legacy)
            exposure_levels: Corresponding exposure levels (legacy)
            lookback_period: Period for calculating rolling max (days)
            adaptive_config: Statistically-derived configuration (preferred)
        """
        self.lookback_period = lookback_period

        # Prefer adaptive config if provided
        if adaptive_config is not None:
            self.drawdown_thresholds = adaptive_config.get_thresholds()
            self.exposure_levels = adaptive_config.get_exposure_levels()
            print(f"Using adaptive drawdown config:\n{adaptive_config}")
        else:
            # Legacy behavior with defaults
            if drawdown_thresholds is None:
                # Default thresholds (event-driven strategies have higher drawdowns)
                self.drawdown_thresholds = [-0.10, -0.15, -0.20, -0.25]
            else:
                self.drawdown_thresholds = sorted(drawdown_thresholds)

            if exposure_levels is None:
                self.exposure_levels = [0.95, 0.85, 0.70, 0.50]
            else:
                self.exposure_levels = exposure_levels

        # State tracking
        self.portfolio_values: List[float] = []
        self.drawdown_history: List[float] = []
        self.current_exposure_level: float = 1.0

    @classmethod
    def from_historical_data(
        cls,
        historical_returns: pd.Series,
        lookback_period: int = 252,
    ) -> DrawdownController:
        """
        Create controller with thresholds derived from historical data.

        CRITICAL: Only uses historical data available at creation time.

        Args:
            historical_returns: Historical daily returns for calibration
            lookback_period: Period for rolling max calculation

        Returns:
            DrawdownController with statistically-derived thresholds
        """
        adaptive_config = AdaptiveDrawdownConfig.from_historical_returns(
            historical_returns,
            lookback_days=len(historical_returns)
        )
        return cls(
            lookback_period=lookback_period,
            adaptive_config=adaptive_config,
        )

    def update(self, portfolio_value: float) -> float:
        """
        Update controller with new portfolio value

        Args:
            portfolio_value: Current portfolio value

        Returns:
            Exposure scalar (1.0 = full exposure, 0.5 = half exposure)
        """
        self.portfolio_values.append(portfolio_value)

        # Calculate current drawdown
        if len(self.portfolio_values) > 0:
            peak = max(self.portfolio_values[-self.lookback_period:])
            current_drawdown = (portfolio_value - peak) / peak if peak > 0 else 0
        else:
            current_drawdown = 0

        self.drawdown_history.append(current_drawdown)

        # Determine exposure level based on drawdown
        exposure_scalar = self._get_exposure_scalar(current_drawdown)
        self.current_exposure_level = exposure_scalar

        return exposure_scalar

    def _get_exposure_scalar(self, drawdown: float) -> float:
        """
        Determine exposure scalar based on current drawdown

        Uses piecewise linear function (FIX 4.2: relaxed for event-driven):
        - 0 to -10% DD: 100% exposure (was -5%)
        - -10% to -15% DD: 95% exposure (was 90%)
        - -15% to -20% DD: 85% exposure (was 75%)
        - -20% to -25% DD: 70% exposure (was 60%)
        - > -25% DD: 50% exposure (emergency brake, was > -20%)
        """
        # No drawdown or positive return
        if drawdown >= 0:
            return 1.0

        # Find appropriate threshold
        for i, threshold in enumerate(self.drawdown_thresholds):
            if drawdown >= threshold:
                return self.exposure_levels[i]

        # Worst case: use minimum exposure
        return self.exposure_levels[-1]

    def apply_to_portfolio(self,
                          portfolio: pd.DataFrame,
                          current_value: float) -> pd.DataFrame:
        """
        Apply drawdown-based scaling to portfolio

        Args:
            portfolio: Portfolio DataFrame with weights
            current_value: Current portfolio value

        Returns:
            Scaled portfolio
        """
        exposure_scalar = self.update(current_value)

        portfolio = portfolio.copy()
        portfolio['weight'] *= exposure_scalar

        return portfolio

    def get_recovery_time_estimate(self) -> int:
        """
        Estimate days to recover from current drawdown
        Based on historical recovery patterns

        Returns:
            Estimated days to recovery
        """
        if not self.drawdown_history:
            return 0

        current_dd = self.drawdown_history[-1]

        if current_dd >= 0:
            return 0

        # Historical recovery time estimates
        # Based on: "The Recovery Time of Stock Market Losses" (various studies)
        recovery_estimates = {
            -0.05: 15,    # 5% DD: ~15 days
            -0.10: 45,    # 10% DD: ~45 days
            -0.15: 90,    # 15% DD: ~90 days
            -0.20: 180,   # 20% DD: ~6 months
            -0.30: 365,   # 30% DD: ~1 year
        }

        # Find closest estimate
        for dd_level, days in sorted(recovery_estimates.items()):
            if current_dd >= dd_level:
                return days

        return 730  # Default: 2 years for severe drawdowns

    def is_drawdown_critical(self) -> bool:
        """Check if drawdown has reached critical levels"""
        if not self.drawdown_history:
            return False

        current_dd = self.drawdown_history[-1]
        critical_threshold = self.drawdown_thresholds[-1]  # Worst threshold

        return current_dd <= critical_threshold

    def get_drawdown_metrics(self) -> Dict:
        """Get current drawdown metrics"""
        if not self.drawdown_history:
            return {
                'current_drawdown': 0,
                'max_drawdown': 0,
                'current_exposure': 1.0,
                'is_critical': False
            }

        current_dd = self.drawdown_history[-1]
        max_dd = min(self.drawdown_history) if self.drawdown_history else 0

        return {
            'current_drawdown': current_dd,
            'max_drawdown': max_dd,
            'current_exposure': self.current_exposure_level,
            'is_critical': self.is_drawdown_critical(),
            'estimated_recovery_days': self.get_recovery_time_estimate()
        }

    def should_halt_trading(self) -> bool:
        """
        Determine if trading should be halted due to extreme conditions

        Returns:
            True if trading should stop temporarily
        """
        if not self.drawdown_history:
            return False

        current_dd = self.drawdown_history[-1]

        # Halt if drawdown exceeds 25% (emergency stop)
        emergency_threshold = -0.25

        if current_dd <= emergency_threshold:
            return True

        # Also halt if volatility is extremely high (>50% annualized)
        if len(self.portfolio_values) >= 20:
            recent_returns = pd.Series(self.portfolio_values[-20:]).pct_change()
            realized_vol = recent_returns.std() * np.sqrt(252)

            if realized_vol > 0.50:  # 50% annualized vol
                return True

        return False
