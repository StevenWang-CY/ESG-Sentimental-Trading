"""
Parameter Regime Change Detection and Adaptation

Detects when market conditions change enough to invalidate calibrated parameters.
Triggers recalibration when detected.

CRITICAL: Works with REAL market data only.
Detection is based on actual returns, not simulated scenarios.

Monitors:
1. Rolling Sharpe ratio degradation
2. Signal-return correlation breakdown
3. Volatility regime shifts
4. Factor exposure drift
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from enum import Enum, auto
from scipy import stats


class RegimeType(Enum):
    """Market regime classification."""
    NORMAL = auto()
    HIGH_VOLATILITY = auto()
    LOW_VOLATILITY = auto()
    TREND_UP = auto()
    TREND_DOWN = auto()
    CRISIS = auto()


@dataclass
class RegimeChangeSignal:
    """Signal indicating regime change detected."""
    timestamp: datetime
    old_regime: RegimeType
    new_regime: RegimeType
    confidence: float
    affected_parameters: List[str]
    metrics: Dict[str, float]

    def __str__(self) -> str:
        return (
            f"Regime Change Detected at {self.timestamp}:\n"
            f"  {self.old_regime.name} → {self.new_regime.name}\n"
            f"  Confidence: {self.confidence:.2%}\n"
            f"  Affected parameters: {', '.join(self.affected_parameters)}"
        )


class RegimeChangeDetector:
    """
    Detects when parameters need recalibration due to regime change.

    CRITICAL: All detection is based on REAL market data.
    No simulated scenarios are used.

    Monitors:
    1. Rolling Sharpe ratio degradation
    2. Factor exposure drift
    3. Signal-return correlation breakdown
    4. Volatility regime shifts
    """

    def __init__(
        self,
        lookback_short: int = 63,   # ~3 months for recent behavior
        lookback_long: int = 252,   # ~1 year for baseline
        change_threshold: float = 2.0,  # Standard deviations for significance
        min_observations: int = 30,
    ):
        """
        Initialize regime detector.

        Args:
            lookback_short: Short window for recent metrics
            lookback_long: Long window for baseline comparison
            change_threshold: Z-score threshold for significance
            min_observations: Minimum data points required
        """
        self.lookback_short = lookback_short
        self.lookback_long = lookback_long
        self.change_threshold = change_threshold
        self.min_observations = min_observations

        # History tracking
        self._sharpe_history: List[float] = []
        self._correlation_history: List[float] = []
        self._volatility_history: List[float] = []
        self._current_regime: RegimeType = RegimeType.NORMAL
        self._regime_changes: List[RegimeChangeSignal] = []

    def check_for_regime_change(
        self,
        returns: pd.Series,
        signals: Optional[pd.Series] = None,
        historical_sharpe: Optional[float] = None,
        historical_correlation: Optional[float] = None,
    ) -> Optional[RegimeChangeSignal]:
        """
        Check for regime change based on real market data.

        Args:
            returns: Real daily returns series
            signals: Optional signal series for correlation check
            historical_sharpe: Baseline Sharpe ratio (from training)
            historical_correlation: Baseline signal-return correlation

        Returns:
            RegimeChangeSignal if change detected, None otherwise
        """
        if len(returns) < self.min_observations:
            return None

        affected_params = []
        metrics = {}

        # 1. Check Sharpe degradation
        sharpe_degraded, sharpe_z = self._check_sharpe_degradation(
            returns,
            historical_sharpe or 0.5,
        )
        metrics['sharpe_z_score'] = sharpe_z
        if sharpe_degraded:
            affected_params.extend(['signal_weights', 'position_sizing'])

        # 2. Check correlation breakdown
        if signals is not None:
            corr_breakdown, corr_z = self._check_correlation_breakdown(
                signals,
                returns,
                historical_correlation or 0.1,
            )
            metrics['correlation_z_score'] = corr_z
            if corr_breakdown:
                affected_params.extend(['signal_weights', 'feature_selection'])

        # 3. Check volatility regime shift
        vol_shifted, new_vol_regime = self._check_volatility_regime(returns)
        metrics['volatility_regime'] = new_vol_regime.name
        if vol_shifted:
            affected_params.extend(['volatility_target', 'drawdown_thresholds'])

        # Determine if regime has changed
        new_regime = self._determine_regime(returns, vol_shifted, new_vol_regime)

        if new_regime != self._current_regime and len(affected_params) > 0:
            # Calculate confidence
            confidence = self._calculate_confidence(metrics, affected_params)

            signal = RegimeChangeSignal(
                timestamp=datetime.now(),
                old_regime=self._current_regime,
                new_regime=new_regime,
                confidence=confidence,
                affected_parameters=list(set(affected_params)),
                metrics=metrics,
            )

            self._regime_changes.append(signal)
            self._current_regime = new_regime

            return signal

        return None

    def _check_sharpe_degradation(
        self,
        returns: pd.Series,
        historical_sharpe: float,
    ) -> Tuple[bool, float]:
        """
        Check if recent Sharpe ratio has degraded significantly.

        Args:
            returns: Real returns series
            historical_sharpe: Baseline Sharpe from training period

        Returns:
            (is_degraded, z_score)
        """
        if len(returns) < self.lookback_short:
            return False, 0.0

        # Calculate recent Sharpe
        recent = returns.tail(self.lookback_short)
        recent_sharpe = (recent.mean() / recent.std()) * np.sqrt(252) if recent.std() > 0 else 0.0

        # Track history
        self._sharpe_history.append(recent_sharpe)
        if len(self._sharpe_history) > self.lookback_long:
            self._sharpe_history = self._sharpe_history[-self.lookback_long:]

        if len(self._sharpe_history) < 10:
            return False, 0.0

        # Calculate z-score of recent Sharpe vs history
        sharpe_mean = np.mean(self._sharpe_history)
        sharpe_std = np.std(self._sharpe_history)

        if sharpe_std < 0.001:
            return False, 0.0

        z_score = (recent_sharpe - sharpe_mean) / sharpe_std

        # Degradation if significantly below historical mean
        is_degraded = z_score < -self.change_threshold

        return is_degraded, z_score

    def _check_correlation_breakdown(
        self,
        signals: pd.Series,
        returns: pd.Series,
        historical_correlation: float,
    ) -> Tuple[bool, float]:
        """
        Check if signal-return correlation has broken down.

        Uses Fisher z-transform for correlation comparison.

        Args:
            signals: Signal series
            returns: Returns series (should be t+1 relative to signals)
            historical_correlation: Baseline correlation

        Returns:
            (is_breakdown, z_score)
        """
        if len(signals) != len(returns) or len(signals) < self.lookback_short:
            return False, 0.0

        # Calculate recent correlation
        recent_signals = signals.tail(self.lookback_short)
        recent_returns = returns.tail(self.lookback_short)

        recent_corr = recent_signals.corr(recent_returns)

        if np.isnan(recent_corr):
            return False, 0.0

        # Track history
        self._correlation_history.append(recent_corr)
        if len(self._correlation_history) > self.lookback_long:
            self._correlation_history = self._correlation_history[-self.lookback_long:]

        # Fisher z-transform for correlation comparison
        z_historical = np.arctanh(np.clip(historical_correlation, -0.99, 0.99))
        z_recent = np.arctanh(np.clip(recent_corr, -0.99, 0.99))

        # Standard error of difference
        n = self.lookback_short
        se = np.sqrt(2 / (n - 3))

        z_diff = (z_historical - z_recent) / se

        # Breakdown if significant drop in correlation
        is_breakdown = z_diff > self.change_threshold

        return is_breakdown, z_diff

    def _check_volatility_regime(
        self,
        returns: pd.Series,
    ) -> Tuple[bool, RegimeType]:
        """
        Check for volatility regime shift.

        Args:
            returns: Real returns series

        Returns:
            (is_shifted, new_regime)
        """
        if len(returns) < self.lookback_long:
            return False, RegimeType.NORMAL

        # Calculate recent and long-term volatility
        recent = returns.tail(self.lookback_short)
        long_term = returns.tail(self.lookback_long)

        recent_vol = recent.std() * np.sqrt(252)
        long_vol = long_term.std() * np.sqrt(252)

        # Track history
        self._volatility_history.append(recent_vol)
        if len(self._volatility_history) > self.lookback_long:
            self._volatility_history = self._volatility_history[-self.lookback_long:]

        # Calculate ratio
        vol_ratio = recent_vol / long_vol if long_vol > 0 else 1.0

        # Determine regime
        if vol_ratio > 1.5:
            new_regime = RegimeType.HIGH_VOLATILITY
            is_shifted = True
        elif vol_ratio < 0.6:
            new_regime = RegimeType.LOW_VOLATILITY
            is_shifted = True
        else:
            new_regime = RegimeType.NORMAL
            is_shifted = False

        return is_shifted, new_regime

    def _determine_regime(
        self,
        returns: pd.Series,
        vol_shifted: bool,
        vol_regime: RegimeType,
    ) -> RegimeType:
        """Determine overall market regime."""
        if len(returns) < self.lookback_short:
            return RegimeType.NORMAL

        recent = returns.tail(self.lookback_short)

        # Check for crisis (high vol + negative returns)
        recent_return = recent.sum()
        recent_vol = recent.std() * np.sqrt(252)

        if recent_return < -0.15 and recent_vol > 0.30:
            return RegimeType.CRISIS

        # Check for strong trends
        if recent_return > 0.10:
            return RegimeType.TREND_UP
        elif recent_return < -0.10:
            return RegimeType.TREND_DOWN

        # Default to volatility-based regime
        if vol_shifted:
            return vol_regime

        return RegimeType.NORMAL

    def _calculate_confidence(
        self,
        metrics: Dict[str, float],
        affected_params: List[str],
    ) -> float:
        """Calculate confidence in regime change detection."""
        confidence = 0.0

        # Higher z-scores = higher confidence
        if 'sharpe_z_score' in metrics:
            confidence += min(abs(metrics['sharpe_z_score']) / 4.0, 0.3)

        if 'correlation_z_score' in metrics:
            confidence += min(abs(metrics['correlation_z_score']) / 4.0, 0.3)

        # More affected parameters = higher confidence
        confidence += min(len(affected_params) / 6.0, 0.3)

        return min(confidence + 0.1, 1.0)  # Base confidence of 10%

    def should_recalibrate(
        self,
        returns: pd.Series,
        signals: Optional[pd.Series] = None,
        historical_sharpe: Optional[float] = None,
        historical_correlation: Optional[float] = None,
    ) -> Tuple[bool, List[str]]:
        """
        Determine if parameters need recalibration.

        Args:
            returns: Real returns series
            signals: Optional signal series
            historical_sharpe: Baseline Sharpe ratio
            historical_correlation: Baseline correlation

        Returns:
            (should_recalibrate, list_of_affected_parameters)
        """
        signal = self.check_for_regime_change(
            returns=returns,
            signals=signals,
            historical_sharpe=historical_sharpe,
            historical_correlation=historical_correlation,
        )

        if signal is not None:
            print(signal)
            return True, signal.affected_parameters

        return False, []

    def get_current_regime(self) -> RegimeType:
        """Get current detected regime."""
        return self._current_regime

    def get_regime_history(self) -> List[RegimeChangeSignal]:
        """Get history of regime changes."""
        return self._regime_changes

    def get_diagnostics(self) -> Dict:
        """Get diagnostic information about detector state."""
        return {
            'current_regime': self._current_regime.name,
            'n_regime_changes': len(self._regime_changes),
            'sharpe_history_len': len(self._sharpe_history),
            'correlation_history_len': len(self._correlation_history),
            'volatility_history_len': len(self._volatility_history),
            'recent_sharpe': self._sharpe_history[-1] if self._sharpe_history else None,
            'recent_correlation': self._correlation_history[-1] if self._correlation_history else None,
            'recent_volatility': self._volatility_history[-1] if self._volatility_history else None,
        }
