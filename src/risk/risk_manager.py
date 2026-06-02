"""
Risk Manager
Comprehensive risk management system with multiple layers of protection

Based on:
- Pedersen (2015): "Efficiently Inefficient"
- Grinold & Kahn (2000): "Active Portfolio Management"
- Ilmanen (2011): "Expected Returns"
"""

import logging

import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


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
                 max_position_size: float = 0.10,      # 10% hard cap per position
                 max_sector_exposure: float = 0.30,     # 30% max per sector
                 target_volatility: float = 0.18,       # FIX 4.1: 18% for event-driven (was 10%)
                 max_drawdown_threshold: float = 0.15,  # 15% max drawdown trigger
                 stop_loss_pct: float = 0.10,           # 10% stop loss per position
                 min_positions: int = 5,                 # FIX 4.1: 5 for sparse ESG events (was 10)
                 leverage_limit: float = 1.0,           # Canonical neutral book gross exposure
                 balance_long_short: bool = True,       # Enforce dollar neutrality (default: True)
                 gross_exposure_target: Optional[float] = None,  # Final gross book size
                 diversification_floor: int = 2):       # Apply haircut only below this many names
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
            gross_exposure_target: Target gross exposure (sum of |weights|) the
                book is renormalized back to AFTER all risk transforms, while
                preserving dollar-neutrality. Defaults to ``leverage_limit``
                when not supplied (a dollar-neutral book has gross = leverage).
            diversification_floor: Hard floor on position count below which the
                under-diversification haircut is applied. An intentionally
                concentrated event-driven book (a handful of names) must NOT be
                silently shrunk, so the 0.8 haircut only fires when the book has
                fewer than this many positions. Default 2 (only a degenerate
                single-name book is penalized).
        """
        self.max_position_size = max_position_size
        self.max_sector_exposure = max_sector_exposure
        self.target_volatility = target_volatility
        self.max_drawdown_threshold = max_drawdown_threshold
        self.stop_loss_pct = stop_loss_pct
        self.min_positions = min_positions
        self.leverage_limit = leverage_limit
        self.balance_long_short = balance_long_short
        # Default gross target to the leverage limit (dollar-neutral => gross == leverage).
        self.gross_exposure_target = (
            gross_exposure_target if gross_exposure_target is not None else leverage_limit
        )
        self.diversification_floor = diversification_floor

        # Track portfolio state
        self.portfolio_history = []
        self.current_drawdown = 0.0
        self.peak_value = 0.0
        self.realized_volatility = None
        # Deliberate de-risk scalar applied on the most recent risk pass
        # (vol-target de-levering and drawdown reduction). The final gross
        # renormalization targets gross_exposure_target * this scalar so that
        # intentional de-risking survives while pure book-reshaping does not
        # silently bleed exposure.
        self.last_risk_scalar = 1.0
        self.last_realized_gross = 0.0
        self.last_realized_net = 0.0

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

        # Reset the deliberate de-risk scalar for this pass. Vol-target
        # de-levering and drawdown reduction multiply into it; the final gross
        # renormalization targets gross_exposure_target * last_risk_scalar.
        self.last_risk_scalar = 1.0

        # 1. Position size limits
        portfolio = self._apply_position_limits(portfolio)

        # 2. Diversification requirements
        portfolio = self._enforce_diversification(portfolio)

        # 3. Volatility targeting
        if returns_history is not None and len(returns_history) > 20:
            portfolio = self._apply_volatility_targeting(portfolio, returns_history)
            # Re-apply position limits: vol targeting can push weights above cap
            # when vol_scalar > 1.0 (target_vol > realized_vol)
            portfolio = self._apply_position_limits(portfolio)

        # 4. Drawdown-based exposure reduction
        self._update_drawdown(current_capital)
        if self.current_drawdown < -self.max_drawdown_threshold:
            portfolio = self._reduce_exposure_on_drawdown(portfolio)

        # 5. Leverage limits
        portfolio = self._apply_leverage_limits(portfolio)

        # 6. Ensure weights sum appropriately (dollar-neutral rebalance)
        portfolio = self._normalize_weights(portfolio)

        # 7. BT-06: FINAL renormalization back to the intended gross book size,
        # preserving dollar-neutrality. Earlier steps (position caps, the
        # diversification haircut, the dollar-neutral side rebalance) reshape the
        # book and can silently leave realized gross well below target; this
        # restores gross to gross_exposure_target * last_risk_scalar so that
        # deliberate de-risking survives but incidental shrinkage does not.
        portfolio = self._renormalize_to_gross_target(portfolio)

        return portfolio

    def _apply_position_limits(self, portfolio: pd.DataFrame) -> pd.DataFrame:
        """Limit individual long and short positions symmetrically."""
        portfolio = portfolio.copy()

        portfolio.loc[portfolio['weight'] > 0, 'weight'] = portfolio.loc[
            portfolio['weight'] > 0, 'weight'
        ].clip(upper=self.max_position_size)

        portfolio.loc[portfolio['weight'] < 0, 'weight'] = portfolio.loc[
            portfolio['weight'] < 0, 'weight'
        ].clip(lower=-self.max_position_size)

        return portfolio

    def _enforce_diversification(self, portfolio: pd.DataFrame) -> pd.DataFrame:
        """
        Apply an under-diversification haircut ONLY to a degenerately small book.

        Based on: Statman (1987) - "How Many Stocks Make a Diversified Portfolio?"

        The original rule shrank the book by 20% whenever the position count fell
        below ``min_positions`` (5). For this strategy that silently penalized
        intentionally-concentrated ESG event-driven baskets (2-4 names), bleeding
        gross exposure on exactly the high-conviction events the strategy is built
        to express. We instead gate the haircut on a hard ``diversification_floor``
        (default 2): the 0.8 haircut now only fires for a book with fewer than the
        floor (i.e., a degenerate single-name book), and the subsequent final
        renormalization restores the intended gross_exposure_target anyway.
        """
        if len(portfolio) < self.diversification_floor:
            # Reduce position sizes only for a degenerate (sub-floor) book.
            scale_factor = 0.8  # Reduce by 20%
            portfolio['weight'] *= scale_factor

        return portfolio

    def _apply_volatility_targeting(self,
                                    portfolio: pd.DataFrame,
                                    returns_history: pd.Series) -> pd.DataFrame:
        """
        Scale portfolio to target volatility level with a fractional-Kelly
        conviction gate.

        The textbook vol-target scalar σ_target / σ_realized ignores expected
        return entirely: in a drawdown where recent returns are negative, naive
        vol targeting will *increase* leverage, which is procyclical and
        well-documented to destroy risk-adjusted performance in crises
        (Harvey et al. 2018, JPM).

        The refined rule:

            vol_scalar = (σ_target / σ_realized)
            conviction = tanh(recent_SR / kelly_reference)        # ∈ [-1, 1]
            scaler     = vol_scalar * conviction_weight           # conviction-weighted

        where conviction_weight = max(conviction_floor, (1 + conviction)/2).

        When the strategy has been performing in-line (SR ≈ kelly_reference ≈ 1),
        conviction_weight ≈ 0.88 (close to naive target). In a severe drawdown
        (SR ≈ -2), conviction_weight collapses to the conviction_floor (default
        0.5), cutting exposure in half and avoiding the classic procyclicality.

        Formula derived from fractional Kelly (MacLean, Thorp & Ziemba 2011):
            f* = μ / σ²  →  scaled weight ∝ (μ/σ) * (1/σ) = SR/σ
        which reduces to naive vol targeting only when μ/σ (Sharpe) is constant.

        Academic basis:
        - MacLean, Thorp & Ziemba (2011) "The Kelly Capital Growth Investment
          Criterion", World Scientific.
        - Moreira & Muir (2017) "Volatility-Managed Portfolios", JFE.
        - Harvey et al. (2018) "The Impact of Volatility Targeting", JPM.
        """
        # Calculate realized volatility (20-day rolling)
        if len(returns_history) >= 20:
            recent = returns_history.tail(20)
        else:
            recent = returns_history
        realized_vol = recent.std() * np.sqrt(252)

        if realized_vol == 0 or np.isnan(realized_vol):
            return portfolio

        self.realized_volatility = realized_vol

        # Base volatility scalar
        vol_scalar = self.target_volatility / realized_vol

        # Conviction weight from recent realized Sharpe (fractional Kelly)
        mean_ret = recent.mean() * 252
        realized_sharpe = mean_ret / realized_vol if realized_vol > 0 else 0.0
        kelly_reference = 1.0  # Reference Sharpe: below this, we de-lever
        conviction = np.tanh(realized_sharpe / kelly_reference)  # ∈ [-1, 1]
        conviction_floor = 0.5
        conviction_weight = max(conviction_floor, (1.0 + conviction) / 2.0)

        scaler = vol_scalar * conviction_weight

        # Clip to prevent extreme scaling [0.3, 3.0]
        # Floor at 0.3: maintains minimum capacity during vol spikes
        # Cap at 3.0: prevents excessive leverage in low-vol environments
        scaler = float(np.clip(scaler, 0.3, 3.0))

        # Record only the DE-LEVERING portion as deliberate de-risk for the final
        # gross renormalization. A low-vol lever-up (scaler > 1.0) is allowed to
        # reshape weights here but must not push realized gross above target, so
        # the gross renorm clamps it back via min(scaler, 1.0).
        self.last_risk_scalar *= min(scaler, 1.0)

        portfolio = portfolio.copy()
        portfolio['weight'] *= scaler

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

        # Deliberate de-risk: carry into the final gross renormalization target.
        self.last_risk_scalar *= reduction_factor

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
        Normalize weights for a neutral long-short portfolio.
        """
        portfolio = portfolio.copy()

        if not self.balance_long_short:
            return portfolio

        long_sum = portfolio.loc[portfolio['weight'] > 0, 'weight'].sum()
        short_sum = portfolio.loc[portfolio['weight'] < 0, 'weight'].abs().sum()

        if long_sum == 0 or short_sum == 0:
            return portfolio.iloc[0:0].copy()

        side_target = min(long_sum, short_sum)
        portfolio.loc[portfolio['weight'] > 0, 'weight'] *= side_target / long_sum
        portfolio.loc[portfolio['weight'] < 0, 'weight'] *= side_target / short_sum

        return portfolio

    def _renormalize_to_gross_target(self, portfolio: pd.DataFrame) -> pd.DataFrame:
        """
        BT-06: Scale the book to its intended gross size while preserving
        dollar-neutrality, then log the realized gross/net exposure.

        The desired gross is ``gross_exposure_target * last_risk_scalar`` so that
        deliberate de-risking (vol-target de-levering, drawdown reduction) is
        respected, but incidental shrinkage from position caps, the
        diversification haircut, or the dollar-neutral side rebalance is undone.

        For a dollar-neutral book each side carries half the gross; when a side
        is missing the book is not tradeable and is returned empty.
        """
        portfolio = portfolio.copy()

        if portfolio.empty or 'weight' not in portfolio.columns:
            self.last_realized_gross = 0.0
            self.last_realized_net = 0.0
            return portfolio

        desired_gross = self.gross_exposure_target * self.last_risk_scalar

        long_mask = portfolio['weight'] > 0
        short_mask = portfolio['weight'] < 0
        long_sum = portfolio.loc[long_mask, 'weight'].sum()
        short_sum = portfolio.loc[short_mask, 'weight'].abs().sum()

        if self.balance_long_short:
            # Dollar-neutral: each side gets half the desired gross.
            side_target = desired_gross / 2.0
            if long_sum <= 0 or short_sum <= 0:
                # One-sided book cannot be made neutral: nothing tradeable.
                self.last_realized_gross = 0.0
                self.last_realized_net = 0.0
                return portfolio.iloc[0:0].copy()
            portfolio.loc[long_mask, 'weight'] *= side_target / long_sum
            portfolio.loc[short_mask, 'weight'] *= side_target / short_sum
        else:
            current_gross = long_sum + short_sum
            if current_gross > 0:
                portfolio['weight'] *= desired_gross / current_gross

        realized_gross = portfolio['weight'].abs().sum()
        realized_net = portfolio['weight'].sum()
        self.last_realized_gross = float(realized_gross)
        self.last_realized_net = float(realized_net)
        logger.debug(
            "BT-06 final book: realized gross=%.4f net=%.4f "
            "(target gross=%.4f, risk_scalar=%.4f, positions=%d)",
            realized_gross, realized_net, desired_gross,
            self.last_risk_scalar, len(portfolio),
        )

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
