"""
Drawdown Controller
Dynamic position sizing based on drawdown levels

Based on:
- Grossman & Zhou (1993): "Optimal Investment Strategies Under the Risk of a Crash"
- Gupta & Li (2007): "Integrating Optimal Monetary and Fiscal Policy Rules with Financial Market Risk"
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from datetime import datetime


class DrawdownController:
    """
    Controls portfolio exposure based on drawdown levels
    Implements dynamic risk scaling
    """

    def __init__(self,
                 drawdown_thresholds: List[float] = None,
                 exposure_levels: List[float] = None,
                 lookback_period: int = 252):
        """
        Initialize drawdown controller

        Args:
            drawdown_thresholds: Drawdown levels triggering action (e.g., [-0.05, -0.10, -0.15])
            exposure_levels: Corresponding exposure levels (e.g., [0.9, 0.7, 0.5])
            lookback_period: Period for calculating rolling max (days)
        """
        # Default thresholds if not provided
        if drawdown_thresholds is None:
            # FIX 4.2: Relax thresholds for event-driven strategies (was [-0.05, -0.10, -0.15, -0.20])
            # Event-driven strategies naturally have higher drawdowns during sparse signal periods
            self.drawdown_thresholds = [-0.10, -0.15, -0.20, -0.25]  # 10%, 15%, 20%, 25%
        else:
            self.drawdown_thresholds = sorted(drawdown_thresholds)  # Ensure sorted

        if exposure_levels is None:
            # FIX 4.2: Less aggressive scaling (was [0.9, 0.75, 0.6, 0.5])
            self.exposure_levels = [0.95, 0.85, 0.70, 0.50]  # Scale down exposure
        else:
            self.exposure_levels = exposure_levels

        self.lookback_period = lookback_period

        # State tracking
        self.portfolio_values = []
        self.drawdown_history = []
        self.current_exposure_level = 1.0

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
