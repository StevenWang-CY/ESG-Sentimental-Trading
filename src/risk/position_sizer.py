"""
Position Sizer
Advanced position sizing based on Kelly Criterion and signal confidence

Based on:
- Kelly (1956): "A New Interpretation of Information Rate"
- Thorp (2006): "The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market"
- Poundstone (2005): "Fortune's Formula"
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional


class PositionSizer:
    """
    Determines optimal position sizes using Kelly Criterion
    and confidence-weighted allocation
    """

    def __init__(self,
                 kelly_fraction: float = 0.25,      # Use 1/4 Kelly (conservative)
                 min_signal_strength: float = 0.3,  # Minimum signal to trade
                 confidence_scaling: bool = True):   # Scale by signal confidence
        """
        Initialize position sizer

        Args:
            kelly_fraction: Fraction of Kelly to use (0.25 = "quarter Kelly")
            min_signal_strength: Minimum signal strength to take position
            confidence_scaling: Whether to scale positions by confidence
        """
        self.kelly_fraction = kelly_fraction
        self.min_signal_strength = min_signal_strength
        self.confidence_scaling = confidence_scaling

    def calculate_position_sizes(self,
                                signals_df: pd.DataFrame,
                                expected_returns: Optional[pd.Series] = None,
                                volatilities: Optional[pd.Series] = None) -> pd.DataFrame:
        """
        Calculate optimal position sizes

        Args:
            signals_df: DataFrame with signals and confidence scores
            expected_returns: Expected return for each ticker (optional)
            volatilities: Volatility estimates for each ticker (optional)

        Returns:
            DataFrame with optimal position sizes
        """
        signals_df = signals_df.copy()

        # Filter weak signals
        strong_signals = signals_df[
            signals_df['raw_score'].abs() >= self.min_signal_strength
        ].copy()

        if strong_signals.empty:
            return pd.DataFrame(columns=['ticker', 'weight'])

        # Calculate base weights using Kelly Criterion
        if expected_returns is not None and volatilities is not None:
            strong_signals['kelly_weight'] = self._kelly_criterion(
                expected_returns,
                volatilities
            )
        else:
            # Use signal strength as proxy
            strong_signals['kelly_weight'] = strong_signals['raw_score']

        # Scale by confidence if enabled
        if self.confidence_scaling and 'event_confidence' in strong_signals.columns:
            strong_signals['kelly_weight'] *= strong_signals['event_confidence']

        # Apply Kelly fraction (typically 0.25 for safety)
        strong_signals['weight'] = strong_signals['kelly_weight'] * self.kelly_fraction

        # Normalize to sum to 1 for each side (long/short)
        strong_signals = self._normalize_by_side(strong_signals)

        return strong_signals[['ticker', 'weight']]

    def _kelly_criterion(self,
                        expected_returns: pd.Series,
                        volatilities: pd.Series) -> pd.Series:
        """
        Kelly Criterion: f* = μ / σ²

        Where:
        - f* is the optimal fraction to bet
        - μ is expected excess return
        - σ² is variance of returns
        """
        # Avoid division by zero
        volatilities = volatilities.replace(0, np.nan)

        # Kelly formula
        kelly_weights = expected_returns / (volatilities ** 2)

        # Cap extreme values
        kelly_weights = kelly_weights.clip(-2, 2)

        return kelly_weights.fillna(0)

    def _normalize_by_side(self, signals_df: pd.DataFrame) -> pd.DataFrame:
        """Normalize weights separately for long and short positions"""
        signals_df = signals_df.copy()

        # Separate long and short
        long_mask = signals_df['weight'] > 0
        short_mask = signals_df['weight'] < 0

        # Normalize longs to sum to 1
        long_sum = signals_df.loc[long_mask, 'weight'].sum()
        if long_sum > 0:
            signals_df.loc[long_mask, 'weight'] /= long_sum

        # Normalize shorts to sum to -1
        short_sum = signals_df.loc[short_mask, 'weight'].sum()
        if short_sum < 0:
            signals_df.loc[short_mask, 'weight'] /= abs(short_sum)

        return signals_df

    def adjust_for_liquidity(self,
                            positions: pd.DataFrame,
                            avg_volumes: pd.Series,
                            capital: float,
                            max_volume_participation: float = 0.05) -> pd.DataFrame:
        """
        Adjust position sizes based on liquidity constraints

        Ensures no position exceeds X% of average daily volume

        Args:
            positions: DataFrame with position weights
            avg_volumes: Average daily trading volume per ticker
            capital: Total capital
            max_volume_participation: Max % of daily volume (0.05 = 5%)
        """
        positions = positions.copy()

        for idx, row in positions.iterrows():
            ticker = row['ticker']
            target_weight = row['weight']

            if ticker not in avg_volumes.index:
                continue

            # Calculate dollar position size
            position_size = abs(target_weight) * capital

            # Calculate maximum tradeable size (X% of daily volume)
            max_tradeable = avg_volumes[ticker] * max_volume_participation

            # Reduce position if it exceeds liquidity limit
            if position_size > max_tradeable:
                liquidity_scalar = max_tradeable / position_size
                positions.loc[idx, 'weight'] *= liquidity_scalar

        return positions

    def calculate_optimal_leverage(self,
                                  sharpe_ratio: float,
                                  max_leverage: float = 2.0) -> float:
        """
        Calculate optimal leverage based on Sharpe ratio

        Formula: optimal_leverage = Sharpe / (2 * target_vol)
        Typical range: 1.0 to 2.0x

        Args:
            sharpe_ratio: Strategy Sharpe ratio
            max_leverage: Maximum allowed leverage

        Returns:
            Optimal leverage multiplier
        """
        # Conservative formula: leverage = Sharpe / 2
        # This assumes target vol of ~10%
        optimal_lev = sharpe_ratio / 2

        # Cap at maximum
        optimal_lev = min(optimal_lev, max_leverage)

        # Minimum of 0.5x (don't go below half capital)
        optimal_lev = max(optimal_lev, 0.5)

        return optimal_lev
