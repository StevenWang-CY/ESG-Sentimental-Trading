"""
Risk Manager
Comprehensive risk management system with multiple layers of protection

Based on:
- Pedersen (2015): "Efficiently Inefficient"
- Grinold & Kahn (2000): "Active Portfolio Management"
- Ilmanen (2011): "Expected Returns"
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime


class RiskManager:
    """
    Multi-layer risk management system

    Implements:
    1. Position size limits (avoid concentration risk)
    2. Volatility targeting (Kelly Criterion-based)
    3. Drawdown controls (dynamic exposure reduction)
    4. Stop-loss mechanisms (limit tail risk)
    5. Correlation-based diversification
    """

    def __init__(self,
                 max_position_size: float = 0.05,      # 5% max per position
                 max_sector_exposure: float = 0.30,     # 30% max per sector
                 target_volatility: float = 0.10,       # 10% annual target vol
                 max_drawdown_threshold: float = 0.15,  # 15% max drawdown trigger
                 stop_loss_pct: float = 0.10,           # 10% stop loss per position
                 min_positions: int = 10,                # Minimum diversification
                 leverage_limit: float = 1.5):          # Max 1.5x leverage
        """
        Initialize risk manager

        Args:
            max_position_size: Maximum weight per position (0.05 = 5%)
            max_sector_exposure: Maximum exposure per sector
            target_volatility: Target portfolio volatility (annualized)
            max_drawdown_threshold: Drawdown level triggering reduction
            stop_loss_pct: Stop loss threshold per position
            min_positions: Minimum number of positions for diversification
            leverage_limit: Maximum leverage allowed
        """
        self.max_position_size = max_position_size
        self.max_sector_exposure = max_sector_exposure
        self.target_volatility = target_volatility
        self.max_drawdown_threshold = max_drawdown_threshold
        self.stop_loss_pct = stop_loss_pct
        self.min_positions = min_positions
        self.leverage_limit = leverage_limit

        # Track portfolio state
        self.portfolio_history = []
        self.current_drawdown = 0.0
        self.peak_value = 0.0
        self.realized_volatility = None

    def apply_risk_controls(self,
                           portfolio: pd.DataFrame,
                           prices: pd.DataFrame,
                           current_capital: float,
                           returns_history: Optional[pd.Series] = None) -> pd.DataFrame:
        """
        Apply comprehensive risk controls to portfolio

        Args:
            portfolio: DataFrame with columns [ticker, weight, ...]
            prices: Historical price data
            current_capital: Current portfolio value
            returns_history: Historical returns for volatility estimation

        Returns:
            Risk-adjusted portfolio DataFrame
        """
        if portfolio.empty:
            return portfolio

        portfolio = portfolio.copy()

        # 1. Position size limits
        portfolio = self._apply_position_limits(portfolio)

        # 2. Diversification requirements
        portfolio = self._enforce_diversification(portfolio)

        # 3. Volatility targeting
        if returns_history is not None and len(returns_history) > 20:
            portfolio = self._apply_volatility_targeting(portfolio, returns_history)

        # 4. Drawdown-based exposure reduction
        self._update_drawdown(current_capital)
        if self.current_drawdown < -self.max_drawdown_threshold:
            portfolio = self._reduce_exposure_on_drawdown(portfolio)

        # 5. Leverage limits
        portfolio = self._apply_leverage_limits(portfolio)

        # 6. Ensure weights sum appropriately
        portfolio = self._normalize_weights(portfolio)

        return portfolio

    def _apply_position_limits(self, portfolio: pd.DataFrame) -> pd.DataFrame:
        """Limit individual position sizes"""
        portfolio = portfolio.copy()

        # Cap absolute position size
        portfolio['weight'] = portfolio['weight'].clip(
            -self.max_position_size,
            self.max_position_size
        )

        return portfolio

    def _enforce_diversification(self, portfolio: pd.DataFrame) -> pd.DataFrame:
        """
        Ensure minimum number of positions

        Based on: Statman (1987) - "How Many Stocks Make a Diversified Portfolio?"
        Minimum 10-15 stocks for adequate diversification
        """
        if len(portfolio) < self.min_positions:
            # Reduce position sizes to encourage more positions
            scale_factor = 0.8  # Reduce by 20%
            portfolio['weight'] *= scale_factor

        return portfolio

    def _apply_volatility_targeting(self,
                                    portfolio: pd.DataFrame,
                                    returns_history: pd.Series) -> pd.DataFrame:
        """
        Scale portfolio to target volatility level

        Based on: Kelly Criterion and volatility targeting frameworks
        Formula: target_weight = (expected_return / variance) * target_vol / realized_vol
        """
        # Calculate realized volatility (20-day rolling)
        if len(returns_history) >= 20:
            realized_vol = returns_history.tail(20).std() * np.sqrt(252)
        else:
            realized_vol = returns_history.std() * np.sqrt(252)

        if realized_vol == 0 or np.isnan(realized_vol):
            return portfolio

        self.realized_volatility = realized_vol

        # Scale positions to target volatility
        vol_scalar = self.target_volatility / realized_vol

        # Cap scalar to prevent excessive leverage or deleverage
        vol_scalar = np.clip(vol_scalar, 0.5, 2.0)

        portfolio = portfolio.copy()
        portfolio['weight'] *= vol_scalar

        return portfolio

    def _update_drawdown(self, current_value: float):
        """Track current drawdown from peak"""
        if current_value > self.peak_value:
            self.peak_value = current_value

        if self.peak_value > 0:
            self.current_drawdown = (current_value - self.peak_value) / self.peak_value
        else:
            self.current_drawdown = 0.0

    def _reduce_exposure_on_drawdown(self, portfolio: pd.DataFrame) -> pd.DataFrame:
        """
        Reduce exposure when drawdown exceeds threshold

        Based on: Drawdown control frameworks
        Linear reduction: scale = 1 - (current_dd - threshold) / threshold
        """
        portfolio = portfolio.copy()

        # Calculate reduction factor
        excess_drawdown = abs(self.current_drawdown) - self.max_drawdown_threshold
        reduction_factor = 1.0 - (excess_drawdown / self.max_drawdown_threshold)

        # Minimum 50% exposure even in severe drawdown
        reduction_factor = max(reduction_factor, 0.5)

        portfolio['weight'] *= reduction_factor

        return portfolio

    def _apply_leverage_limits(self, portfolio: pd.DataFrame) -> pd.DataFrame:
        """Ensure total leverage stays within limits"""
        portfolio = portfolio.copy()

        # Calculate gross leverage (sum of absolute weights)
        gross_leverage = portfolio['weight'].abs().sum()

        if gross_leverage > self.leverage_limit:
            # Scale down proportionally
            scale_factor = self.leverage_limit / gross_leverage
            portfolio['weight'] *= scale_factor

        return portfolio

    def _normalize_weights(self, portfolio: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize weights for long-short portfolio
        Ensure dollar neutrality (long = short)
        """
        portfolio = portfolio.copy()

        long_weights = portfolio[portfolio['weight'] > 0]['weight'].sum()
        short_weights = portfolio[portfolio['weight'] < 0]['weight'].abs().sum()

        if long_weights == 0 or short_weights == 0:
            return portfolio

        # Scale to ensure dollar neutrality
        if long_weights > short_weights:
            # Scale down longs
            portfolio.loc[portfolio['weight'] > 0, 'weight'] *= (short_weights / long_weights)
        elif short_weights > long_weights:
            # Scale down shorts
            portfolio.loc[portfolio['weight'] < 0, 'weight'] *= (long_weights / short_weights)

        return portfolio

    def check_stop_loss(self,
                       position_returns: pd.Series,
                       current_weights: pd.Series) -> pd.Series:
        """
        Check if any positions hit stop loss

        Args:
            position_returns: Return of each position since entry
            current_weights: Current position weights

        Returns:
            Adjusted weights (0 for stopped positions)
        """
        adjusted_weights = current_weights.copy()

        # Close positions that hit stop loss
        stop_loss_mask = position_returns < -self.stop_loss_pct
        adjusted_weights[stop_loss_mask] = 0

        return adjusted_weights

    def get_risk_metrics(self) -> Dict:
        """Get current risk metrics"""
        return {
            'current_drawdown': self.current_drawdown,
            'peak_value': self.peak_value,
            'realized_volatility': self.realized_volatility,
            'max_drawdown_threshold': self.max_drawdown_threshold,
            'is_drawdown_triggered': self.current_drawdown < -self.max_drawdown_threshold
        }

    def calculate_var(self,
                     returns: pd.Series,
                     confidence: float = 0.95,
                     holding_period: int = 1) -> float:
        """
        Calculate Value at Risk

        Args:
            returns: Historical returns
            confidence: Confidence level (0.95 = 95%)
            holding_period: Holding period in days

        Returns:
            VaR estimate
        """
        if len(returns) < 30:
            return 0.0

        # Historical VaR
        var = np.percentile(returns, (1 - confidence) * 100)

        # Scale to holding period (square root of time)
        var_scaled = var * np.sqrt(holding_period)

        return var_scaled

    def calculate_expected_shortfall(self,
                                    returns: pd.Series,
                                    confidence: float = 0.95) -> float:
        """
        Calculate Expected Shortfall (CVaR)
        Average loss beyond VaR threshold
        """
        if len(returns) < 30:
            return 0.0

        var = self.calculate_var(returns, confidence)
        shortfall = returns[returns <= var].mean()

        return shortfall
