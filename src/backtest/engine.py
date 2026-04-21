"""
Backtesting Engine
Simulates strategy performance on historical data with comprehensive risk management.

Academic references for transaction cost modeling:
- Almgren, R., Thum, C., Hauptmann, E., & Li, H. (2005) "Direct Estimation of
  Equity Market Impact", Risk. Square-root market impact law for equities:
  impact_bps = η * σ * sqrt(Q / V), where Q is trade size, V is daily volume.
- Almgren, R. & Chriss, N. (2000) "Optimal Execution of Portfolio Transactions",
  Journal of Risk. Temporary + permanent market impact decomposition.
- D'Avolio, G. (2002) "The market for borrowing stock", JFE. Short borrow
  cost averages 1-2% annualized for easy-to-borrow names, higher for specials.
- Engelberg, Reed & Ringgenberg (2018) "Short-selling risk", JF.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

try:
    from risk import RiskManager, DrawdownController
    RISK_MANAGEMENT_AVAILABLE = True
except ImportError:
    RISK_MANAGEMENT_AVAILABLE = False
    print("Warning: Risk management modules not available")


class BacktestEngine:
    """
    Simple vectorized backtesting engine for signal-based strategies
    """

    def __init__(self, prices: pd.DataFrame, initial_capital: float = 1000000.0,
                 commission_pct: float = 0.0005, slippage_bps: float = 3,
                 enable_risk_management: bool = True,
                 max_position_size: float = 0.10,
                 target_volatility: float = 0.12,
                 max_drawdown_threshold: float = 0.15,
                 adaptive_drawdown_thresholds: bool = True,
                 leverage_limit: float = 1.0,
                 balance_long_short: bool = True,
                 cash_benchmark_returns: Optional[pd.Series] = None,
                 regime_aware_equitization: bool = False,
                 bear_equitization_pct: float = 0.40,
                 sma_lookback: int = 100,
                 use_market_impact_model: bool = True,
                 impact_coefficient: float = 0.10,
                 default_adv_pct: float = 0.01,
                 volume_data: Optional[pd.DataFrame] = None,
                 annual_borrow_cost: float = 0.0040,
                 annual_margin_rate: float = 0.0,
                 borrow_cost_by_ticker: Optional[Dict[str, float]] = None):
        """
        Initialize backtest engine with risk management

        Args:
            prices: Price DataFrame with multi-index (date, ticker)
            initial_capital: Starting capital
            commission_pct: Commission as percentage (e.g., 0.0005 = 5 bps)
            slippage_bps: Slippage in basis points
            enable_risk_management: Enable comprehensive risk controls
            max_position_size: Maximum single position size (10%)
            target_volatility: Target portfolio volatility (12% annualized)
            max_drawdown_threshold: Maximum acceptable drawdown (15%)
            balance_long_short: Enforce dollar neutrality (default: True)
            cash_benchmark_returns: Daily returns for cash equitization (e.g., SPY).
                When provided, idle cash earns the benchmark return instead of 0%.
            regime_aware_equitization: If True, reduce equitization in bear regime
                (Faber 2007, Ang 2014). Default: False.
            bear_equitization_pct: Fraction of SPY return applied in bear regime
                (0.40 = 40% of SPY return). Only used if regime_aware_equitization=True.
            sma_lookback: SMA lookback period for regime detection (trading days).
                100-day recommended (Zakamulin 2014). Default: 100.
            use_market_impact_model: Enable Almgren-Chriss square-root market
                impact on top of static slippage (default True). When False,
                only the constant slippage_bps is applied.
            impact_coefficient: Almgren-Chriss η coefficient in
                impact = η * σ * sqrt(Q/V). Empirical US equity range 0.05-0.15
                (Almgren et al. 2005 Table 3). Default 0.10.
            default_adv_pct: If no volume data is supplied, assume the trade
                represents this fraction of daily volume (default 1%). Used to
                impute sqrt(Q/V) ≈ sqrt(default_adv_pct).
            volume_data: Optional DataFrame of daily volume data (same index
                shape as `prices`). When provided, participation rate is
                computed exactly from trade size / 20-day average volume.
            annual_borrow_cost: Annualized stock-borrow fee charged daily on
                the absolute market value of short positions (D'Avolio 2002
                median ≈ 0.40% for easy-to-borrow). Default 40 bps/year.
            annual_margin_rate: Annualized financing rate on long gross
                exposure above cash (for leveraged books). Default 0% since
                base case is dollar-neutral with net cash ≈ initial capital.
            borrow_cost_by_ticker: Optional per-ticker overrides for hard-to-
                borrow names (e.g., {'GME': 0.50}). Falls back to
                annual_borrow_cost when missing.
        """
        self.prices = prices
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_bps = slippage_bps / 10000
        self.enable_risk_management = enable_risk_management and RISK_MANAGEMENT_AVAILABLE
        self.balance_long_short = balance_long_short
        self.cash_benchmark_returns = cash_benchmark_returns
        self.regime_aware_equitization = regime_aware_equitization
        self.bear_equitization_pct = bear_equitization_pct
        self.sma_lookback = sma_lookback
        self.adaptive_drawdown_thresholds = adaptive_drawdown_thresholds
        self.use_market_impact_model = use_market_impact_model
        self.impact_coefficient = impact_coefficient
        self.default_adv_pct = default_adv_pct
        self.volume_data = volume_data
        self.annual_borrow_cost = annual_borrow_cost
        self.annual_margin_rate = annual_margin_rate
        self.borrow_cost_by_ticker = borrow_cost_by_ticker or {}
        self._trading_days_per_year = 252

        self.portfolio_value = []
        self.positions = []
        self.trades = []
        self.daily_returns = []
        self.cash = initial_capital  # Track cash separately

        # Initialize risk management
        if self.enable_risk_management:
            self.risk_manager = RiskManager(
                max_position_size=max_position_size,
                target_volatility=target_volatility,
                max_drawdown_threshold=max_drawdown_threshold,
                min_positions=2,  # Concentrated ESG event-driven (matches config)
                leverage_limit=leverage_limit,
                balance_long_short=self.balance_long_short
            )
            self.drawdown_controller = DrawdownController(
                drawdown_thresholds=[-0.10, -0.15, -0.20, -0.25],
                exposure_levels=[0.95, 0.85, 0.70, 0.50]
            )
            print(f"Risk management enabled: max_pos={max_position_size:.1%}, "
                  f"target_vol={target_volatility:.1%}, max_dd={max_drawdown_threshold:.1%}")
        else:
            self.risk_manager = None
            self.drawdown_controller = None

    def _is_bull_regime(self, date) -> bool:
        """
        Determine market regime using SMA of SPY price index.
        Bull = SPY cumulative price above N-day SMA. Bear = below.

        Uses only past data available at decision time (no look-ahead bias).

        Academic basis:
        - Faber (2007) "A Quantitative Approach to Tactical Asset Allocation"
        - Ang (2014) "Asset Management", Chapter 14
        """
        if self.cash_benchmark_returns is None:
            return True  # Default to bull if no benchmark data

        sma_lookback = self.sma_lookback

        # Get all benchmark returns up to current date
        available_returns = self.cash_benchmark_returns[
            self.cash_benchmark_returns.index <= date
        ]

        if len(available_returns) < sma_lookback:
            return True  # Not enough data, default to bull (conservative)

        # Compute cumulative price index from returns
        price_index = (1 + available_returns).cumprod()

        # Current price vs N-day SMA
        sma = price_index.tail(sma_lookback).mean()
        current_price = price_index.iloc[-1]

        return current_price >= sma

    def _estimate_realized_volatility(self, date: datetime, ticker: str,
                                      lookback: int = 20) -> float:
        """
        Estimate ticker-level daily realized volatility from the past
        `lookback` trading days (excluding the current date). Falls back to
        a 2% daily vol prior when history is insufficient.

        Used as σ in the Almgren-Chriss impact formula:
            impact_bps = 10000 * η * σ_daily * sqrt(participation_rate)
        """
        try:
            if not isinstance(self.prices.index, pd.MultiIndex):
                return 0.02  # Fallback: 2% daily vol

            if isinstance(self.prices.columns, pd.MultiIndex):
                mask = self.prices.index.get_level_values('ticker') == ticker
                ticker_prices = self.prices[mask]
                if ('Close', ticker) in self.prices.columns:
                    px = ticker_prices[('Close', ticker)]
                else:
                    return 0.02
            else:
                try:
                    ticker_prices = self.prices.xs(ticker, level='ticker')
                    px = ticker_prices['Close']
                except (KeyError, ValueError):
                    return 0.02

            # Restrict to history strictly before the trade date (anti look-ahead)
            px = px.sort_index()
            past_dates = [d for d in px.index.get_level_values(0) if d < date] if isinstance(px.index, pd.MultiIndex) else [d for d in px.index if d < date]
            if not past_dates:
                return 0.02
            recent = px.loc[past_dates[-lookback:]] if len(past_dates) >= 2 else px
            if len(recent) < 5:
                return 0.02
            rets = np.log(recent.astype(float)).diff().dropna()
            vol = rets.std()
            if pd.isna(vol) or vol <= 0:
                return 0.02
            return float(vol)
        except Exception:
            return 0.02

    def _compute_slippage_rate(self, date: datetime, ticker: str,
                               trade_value: float) -> float:
        """
        Compute total slippage rate (round-trip one-way) for a single trade.

        Total = static_slippage + market_impact

        Market impact (Almgren et al. 2005):
            impact_rate = η * σ_daily * sqrt(participation_rate)
        where participation_rate = |trade_notional| / (ADV * avg_price)
        approximated by `default_adv_pct` when volume data is unavailable.
        """
        base = self.slippage_bps  # fractional (e.g., 0.0003 for 3 bps)
        if not self.use_market_impact_model:
            return base

        sigma = self._estimate_realized_volatility(date, ticker)

        # Participation rate: fall back to the prior when volume data is absent
        participation = self.default_adv_pct
        if self.volume_data is not None and isinstance(self.volume_data, pd.DataFrame):
            try:
                if (date, ticker) in self.volume_data.index:
                    adv = float(self.volume_data.loc[(date, ticker)])
                    px = self._get_price(date, ticker) or 1.0
                    dollar_adv = adv * px
                    if dollar_adv > 0:
                        participation = abs(trade_value) / dollar_adv
            except Exception:
                participation = self.default_adv_pct

        # Cap participation rate at 100% to avoid unrealistic impact
        participation = min(max(participation, 1e-6), 1.0)
        impact_rate = self.impact_coefficient * sigma * np.sqrt(participation)

        # Cap total slippage at 200 bps per trade (safety rail)
        total = base + impact_rate
        return float(np.clip(total, 0.0, 0.02))

    def _accrue_short_borrow_cost(self, date: datetime, positions: Dict,
                                  cash: float) -> float:
        """
        Accrue one day of stock-borrow fees on the absolute market value of
        short positions. D'Avolio (2002) documents a median 0.40%/year borrow
        for easy-to-borrow names with a long tail of specials.
        """
        if not positions or self.annual_borrow_cost <= 0:
            return cash

        daily_rate_default = self.annual_borrow_cost / self._trading_days_per_year
        short_cost = 0.0
        for ticker, position in positions.items():
            if position['shares'] >= 0:
                continue
            price = self._get_price(date, ticker)
            if not price or price <= 0:
                continue
            market_value = abs(position['shares']) * price
            rate_annual = self.borrow_cost_by_ticker.get(ticker, self.annual_borrow_cost)
            daily_rate = rate_annual / self._trading_days_per_year
            short_cost += market_value * daily_rate

        return cash - short_cost

    def run(self, signals: pd.DataFrame, rebalance_freq: str = 'W',
            holding_period: int = 10) -> 'BacktestResult':
        """
        Run backtest

        Args:
            signals: DataFrame with columns [ticker, date, weight]
            rebalance_freq: Rebalancing frequency ('D', 'W', 'M')
            holding_period: Days to hold positions

        Returns:
            BacktestResult object
        """
        if signals.empty:
            print("No signals provided. Creating empty result.")
            return self._create_empty_result()

        # Prepare data
        signals = signals.copy()
        signals['date'] = pd.to_datetime(signals['date'])

        # Get all trading dates from prices
        if isinstance(self.prices.index, pd.MultiIndex):
            all_dates = sorted(self.prices.index.get_level_values(0).unique())
        else:
            all_dates = sorted(self.prices.index.unique())

        # CRITICAL FIX: Remove NaT values which can break date comparison
        all_dates = [d for d in all_dates if pd.notna(d)]
        
        if not all_dates:
            print("ERROR: No valid dates in price data.")
            return self._create_empty_result()

        # CRITICAL FIX: Filter signals to only include dates within price data range
        # This prevents 0 trades when signals exist outside backtest window
        price_start = all_dates[0]
        price_end = all_dates[-1]

        original_signal_count = len(signals)
        signals = signals[(signals['date'] >= price_start) & (signals['date'] <= price_end)].copy()
        filtered_count = original_signal_count - len(signals)

        if filtered_count > 0:
            print(f"\nWARNING: Filtered out {filtered_count} signals outside price data range")
            print(f"  Price range: {price_start} to {price_end}")

        if signals.empty:
            print("ERROR: No signals within price data range. Backtest cannot proceed.")
            return self._create_empty_result()

        # Get rebalancing dates
        rebalance_dates = self._get_rebalance_dates(signals, rebalance_freq)
        print(f"\nDEBUG: Backtest setup:")
        print(f"  Total signals/positions in portfolio: {len(signals)}")
        print(f"  Unique rebalance dates: {len(rebalance_dates)}")
        print(f"  Rebalance dates: {rebalance_dates[:5]}")

        # Initialize tracking
        cash = self.initial_capital
        current_positions = {}
        portfolio_values = []
        returns = []

        print(f"  Price data dates: {len(all_dates)} (from {all_dates[0]} to {all_dates[-1]})")

        # Simulate trading
        rebalance_count = 0
        for i, date in enumerate(all_dates):
            # Cash equitization: idle cash earns benchmark return (e.g., SPY).
            # Portable alpha framework (Pedersen 2015 "Efficiently Inefficient"):
            # Strategy return = market return + ESG alpha overlay.
            if self.cash_benchmark_returns is not None and i > 0:
                benchmark_ret = self.cash_benchmark_returns.get(date, 0.0)
                if self.regime_aware_equitization and not self._is_bull_regime(date):
                    # Bear regime: partial equitization (Ang 2014, Faber 2007)
                    cash *= (1 + benchmark_ret * self.bear_equitization_pct)
                else:
                    cash *= (1 + benchmark_ret)

            # Daily short-borrow fee accrual (D'Avolio 2002).
            # Charge before rebalancing so liquidations use post-fee cash.
            if i > 0 and current_positions:
                cash = self._accrue_short_borrow_cost(date, current_positions, cash)

            # Calculate current portfolio value BEFORE rebalancing
            portfolio_value_before = self._calculate_portfolio_value_correct(
                date, current_positions, cash
            )

            # Check if we should rebalance
            if date in rebalance_dates:
                rebalance_count += 1
                print(f"DEBUG: Rebalancing #{rebalance_count} on {date}")
                current_positions, cash = self._rebalance_with_cash(
                    date, signals, current_positions, cash, portfolio_value_before, holding_period
                )
                print(f"DEBUG:   Created {len(current_positions)} positions, {len(self.trades)} total trades")

            # Calculate portfolio value AFTER rebalancing
            portfolio_value = self._calculate_portfolio_value_correct(
                date, current_positions, cash
            )

            portfolio_values.append({
                'date': date,
                'value': portfolio_value
            })

            # Calculate return
            if i > 0:
                prev_value = portfolio_values[i-1]['value']
                ret = (portfolio_value - prev_value) / prev_value if prev_value > 0 else 0
                returns.append({'date': date, 'return': ret})
                self.daily_returns.append({'date': date, 'return': ret})

        # Create result
        result = BacktestResult(
            portfolio_values=pd.DataFrame(portfolio_values),
            returns=pd.DataFrame(returns),
            trades=pd.DataFrame(self.trades),
            positions=pd.DataFrame(self.positions),
            initial_capital=self.initial_capital
        )

        return result

    def _get_rebalance_dates(self, signals: pd.DataFrame, freq: str) -> List[datetime]:
        """
        Get rebalancing dates based on frequency

        CRITICAL FIX (v2): Generate a FULL weekly/monthly grid, not just weeks with signals.
        Previous bug: Only generated dates for weeks WITH signals, causing gaps of 40-90 days
        where positions couldn't be liquidated (holding period was 10 days but positions
        were held 49-91 days due to missing rebalance dates).

        The fix generates a continuous grid from first signal to last signal + buffer,
        using actual trading dates (not calendar dates) to avoid holiday mismatches.

        Args:
            signals: DataFrame with 'date' column
            freq: Rebalancing frequency ('D'=daily, 'W'=weekly, 'M'=monthly)

        Returns:
            List of rebalancing dates
        """
        signal_dates = pd.to_datetime(signals['date'].unique())

        if freq == 'D':
            return sorted(signal_dates)

        # Get all trading dates from price data for full grid generation
        if isinstance(self.prices.index, pd.MultiIndex):
            all_trading_dates = sorted(self.prices.index.get_level_values(0).unique())
        else:
            all_trading_dates = sorted(self.prices.index.unique())
        all_trading_dates = pd.DatetimeIndex([d for d in all_trading_dates if pd.notna(d)])

        # Grid spans from first signal date to last signal date + 4 weeks buffer
        # Buffer ensures final positions get liquidated after their holding period expires
        min_date = signal_dates.min()
        max_signal_date = signal_dates.max()
        buffer_end = max_signal_date + pd.Timedelta(days=28)
        max_date = min(buffer_end, all_trading_dates.max())

        # Filter to trading dates within range
        mask = (all_trading_dates >= min_date) & (all_trading_dates <= max_date)
        range_dates = all_trading_dates[mask]

        if len(range_dates) == 0:
            return sorted(signal_dates)

        if freq == 'W':
            # Weekly: last trading day of each ISO week
            trading_df = pd.DataFrame({'date': range_dates})
            trading_df['week'] = trading_df['date'].dt.to_period('W')
            rebalance_dates = trading_df.groupby('week')['date'].max().tolist()
            return sorted(rebalance_dates)
        elif freq == 'M':
            # Monthly: last trading day of each month
            trading_df = pd.DataFrame({'date': range_dates})
            trading_df['month'] = trading_df['date'].dt.to_period('M')
            rebalance_dates = trading_df.groupby('month')['date'].max().tolist()
            return sorted(rebalance_dates)
        else:
            print(f"WARNING: Unknown rebalance frequency '{freq}', defaulting to signal dates")
            return sorted(signal_dates)

    def _rebalance_with_cash(self, date: datetime, signals: pd.DataFrame,
                             current_positions: Dict, cash: float,
                             portfolio_value: float, holding_period: int = 10) -> tuple:
        """Execute rebalancing with proper cash tracking and holding period management"""
        # CRITICAL FIX: Only liquidate positions past their holding period
        # This allows multiple positions to be held simultaneously (core of event-driven strategy)
        positions_to_keep = {}

        for ticker, position in list(current_positions.items()):
            entry_date = position['entry_date']
            days_held = (date - entry_date).days

            # Check if position should be liquidated (past holding period)
            if days_held >= holding_period:
                price = self._get_price(date, ticker)
                if price:
                    # Liquidate expired position
                    proceeds = position['shares'] * price
                    # For longs: get cash back; For shorts: pay cash to cover
                    cash += proceeds
                    # Apply transaction costs with dynamic slippage
                    slippage_rate = self._compute_slippage_rate(
                        date, ticker, abs(proceeds)
                    )
                    cash -= abs(proceeds) * (self.commission_pct + slippage_rate)
                    print(f"DEBUG:   Liquidated {ticker} after {days_held} days (holding period: {holding_period})")
            else:
                # Keep position (still within holding period)
                positions_to_keep[ticker] = position
                print(f"DEBUG:   Keeping {ticker} (held for {days_held}/{holding_period} days)")

        # Start with positions we're keeping
        current_positions = positions_to_keep

        # Get target weights for this date
        target_signals = signals[signals['date'] == date].copy()

        print(f"DEBUG:   Found {len(target_signals)} signals for {date}")
        if target_signals.empty:
            # CRITICAL FIX: Return kept positions, NOT empty dict
            # Previous bug: returned ({}, cash) which dropped all active positions
            # that were within their holding period. This caused positions to vanish
            # on rebalance dates without new signals.
            print(f"DEBUG:   No new signals for {date}, keeping {len(positions_to_keep)} active positions")
            return positions_to_keep, cash

        # Apply risk management if enabled
        if self.enable_risk_management and self.risk_manager is not None:
            # Calculate returns history for volatility targeting
            if len(self.daily_returns) > 0:
                returns_series = pd.Series([r['return'] for r in self.daily_returns])
            else:
                returns_series = None

            if (
                self.adaptive_drawdown_thresholds and
                returns_series is not None and
                len(returns_series) >= 60 and
                self.drawdown_controller is not None
            ):
                self.drawdown_controller = DrawdownController.from_historical_data(
                    returns_series
                )

            # Apply comprehensive risk controls
            target_signals = self.risk_manager.apply_risk_controls(
                portfolio=target_signals,
                prices=self.prices,
                current_capital=portfolio_value,
                returns_history=returns_series
            )

            # Apply drawdown-based exposure reduction
            if self.drawdown_controller is not None:
                target_signals = self.drawdown_controller.apply_to_portfolio(
                    portfolio=target_signals,
                    current_value=portfolio_value
                )

            # Check for trading halt conditions
            if self.drawdown_controller.should_halt_trading():
                print(f"WARNING: Trading halted at {date} due to extreme conditions!")
                print(f"Drawdown metrics: {self.drawdown_controller.get_drawdown_metrics()}")
                return {}, cash  # Exit all positions

        # Calculate target positions using portfolio value (not just cash)
        new_positions = {}

        print(f"DEBUG:   Target signals after risk management:")
        for idx, row in target_signals.iterrows():
            print(f"DEBUG:     {row['ticker']}: weight={row['weight']:.4f}")

        for _, row in target_signals.iterrows():
            ticker = row['ticker']

            # FIX 5.1: Prevent duplicate positions for the same ticker
            # If ticker already has an active position (within holding period), skip it
            if ticker in current_positions:
                print(f"DEBUG:     SKIPPED - {ticker} already has an active position")
                continue

            weight = row['weight']

            # Get current price
            price = self._get_price(date, ticker)

            print(f"DEBUG:   Processing {ticker}: weight={weight:.4f}, price={price}, portfolio_value={portfolio_value:,.2f}")

            # CRITICAL FIX: Also check for NaN prices (can cause ValueError when converting to int)
            if price is None or pd.isna(price) or price <= 0:
                print(f"DEBUG:     REJECTED - Invalid price: {price}")
                continue

            # Calculate target dollar amount based on portfolio value
            target_value = portfolio_value * weight

            print(f"DEBUG:     Target value: ${target_value:,.2f}")

            # Dynamic slippage: static + Almgren-Chriss square-root impact
            slippage_rate = self._compute_slippage_rate(
                date, ticker, abs(target_value)
            )

            # Calculate shares (accounting for transaction costs)
            if target_value > 0:
                # Long position - FIX Issue #8: Use round() instead of int() truncation
                shares = round(target_value / (price * (1 + self.commission_pct + slippage_rate)))
                if shares == 0 and target_value > price * 0.5:
                    shares = 1  # Minimum 1 share if target covers at least half a share
                cost = shares * price * (1 + self.commission_pct + slippage_rate)
                cash -= cost
                print(f"DEBUG:     LONG: {shares} shares @ ${price:.2f} = ${cost:,.2f} (slippage={slippage_rate*10000:.1f}bps)")
            else:
                # Short position (negative shares) - also use round() for consistency
                shares = round(target_value / (price * (1 - self.commission_pct - slippage_rate)))
                if shares == 0 and target_value < -price * 0.5:
                    shares = -1  # Minimum 1 share short if target covers at least half a share
                proceeds = abs(shares) * price * (1 - self.commission_pct - slippage_rate)
                cash += proceeds
                print(f"DEBUG:     SHORT: {shares} shares @ ${price:.2f} = ${proceeds:,.2f} (slippage={slippage_rate*10000:.1f}bps)")

            if shares != 0:
                new_positions[ticker] = {
                    'shares': shares,
                    'entry_price': price,
                    'entry_date': date
                }

                # Record trade
                self.trades.append({
                    'date': date,
                    'ticker': ticker,
                    'shares': shares,
                    'price': price,
                    'value': shares * price
                })
                print(f"DEBUG:     ✓ Position created")
            else:
                print(f"DEBUG:     REJECTED - Shares = 0")

        # Merge kept positions with new positions
        current_positions.update(new_positions)
        print(f"DEBUG:   Total positions after rebalance: {len(current_positions)} (kept: {len(positions_to_keep)}, new: {len(new_positions)})")

        return current_positions, cash

    def _calculate_portfolio_value_correct(self, date: datetime,
                                           positions: Dict, cash: float) -> float:
        """
        Calculate total portfolio value correctly

        For long-short:
        Net Liquidation Value = Cash + Long Market Value - Short Market Value
        """
        long_value = 0
        short_value = 0

        for ticker, position in positions.items():
            price = self._get_price(date, ticker)
            if price and price > 0:
                market_value = position['shares'] * price
                if position['shares'] > 0:
                    # Long position contributes positively
                    long_value += market_value
                else:
                    # Short position is a liability (negative shares)
                    short_value += abs(market_value)

        # Net Liquidation Value
        total_value = cash + long_value - short_value

        return total_value

    def _calculate_portfolio_value(self, date: datetime,
                                   positions: Dict, cash: float) -> float:
        """
        Calculate total portfolio value including cash and positions

        For long-short strategies:
        - Cash starts at initial_capital
        - Long positions: cash decreases by purchase amount, increases by sale proceeds
        - Short positions: cash increases by short proceeds, decreases by cover amount
        - Portfolio value = cash + sum(long position values) - sum(short position values)
        """
        # Calculate position values
        long_value = 0
        short_value = 0

        for ticker, position in positions.items():
            price = self._get_price(date, ticker)
            if price:
                position_value = position['shares'] * price
                if position['shares'] > 0:
                    long_value += position_value
                else:
                    short_value += abs(position_value)  # Short positions are negative shares

        # For long-short: total value = initial capital + P&L from both long and short
        # P&L from longs = current_long_value - cash_spent_on_longs
        # P&L from shorts = cash_from_shorts - cost_to_cover_shorts
        # Simplified: track net liquidation value
        total_value = cash + long_value - short_value

        return total_value

    def _get_price(self, date: datetime, ticker: str,
                   price_type: str = 'Close') -> Optional[float]:
        """Get price for ticker on date"""
        try:
            if isinstance(self.prices.index, pd.MultiIndex):
                # CRITICAL FIX: Handle hierarchical column structure from yfinance
                # Check if columns are MultiIndex (e.g., ('Close', 'AAPL'))
                if isinstance(self.prices.columns, pd.MultiIndex):
                    # Access price using hierarchical column structure
                    # Try to get exact date match first
                    if (date, ticker) in self.prices.index:
                        price = self.prices.loc[(date, ticker), (price_type, ticker)]
                        if pd.notna(price):
                            return float(price)

                    # If no exact match, use forward-fill (most recent past price)
                    ticker_mask = self.prices.index.get_level_values('ticker') == ticker
                    ticker_data = self.prices[ticker_mask]
                    date_mask = ticker_data.index.get_level_values('Date') <= date
                    past_data = ticker_data[date_mask]

                    if len(past_data) > 0:
                        latest_date = past_data.index.get_level_values('Date').max()
                        price = self.prices.loc[(latest_date, ticker), (price_type, ticker)]
                        if pd.notna(price):
                            return float(price)
                else:
                    # Simple column structure
                    price_data = self.prices.xs(ticker, level='ticker')
                    if date in price_data.index:
                        result = price_data.loc[date, price_type]
                        # Handle case where result is a Series (multiple rows for same date)
                        if isinstance(result, pd.Series):
                            return float(result.iloc[0])
                        return float(result)
                    else:
                        # FIXED: Use most recent PAST price (forward-fill) to prevent look-ahead bias
                        # Never use future prices for trading decisions
                        past_dates = price_data.index[price_data.index <= date]
                        if len(past_dates) > 0:
                            nearest_date = past_dates.max()  # Most recent past date
                            result = price_data.loc[nearest_date, price_type]
                            if isinstance(result, pd.Series):
                                return float(result.iloc[0])
                            return float(result)
            else:
                if date in self.prices.index and ticker in self.prices.columns:
                    return float(self.prices.loc[date, ticker])

            return None
        except Exception as e:
            print(f"ERROR in _get_price({date}, {ticker}): {e}")
            return None

    def _create_empty_result(self) -> 'BacktestResult':
        """Create empty backtest result"""
        return BacktestResult(
            portfolio_values=pd.DataFrame(columns=['date', 'value']),
            returns=pd.DataFrame(columns=['date', 'return']),
            trades=pd.DataFrame(columns=['date', 'ticker', 'shares', 'price', 'value']),
            positions=pd.DataFrame(),
            initial_capital=self.initial_capital
        )


class BacktestResult:
    """
    Container for backtest results
    """

    def __init__(self, portfolio_values: pd.DataFrame, returns: pd.DataFrame,
                 trades: pd.DataFrame, positions: pd.DataFrame,
                 initial_capital: float):
        """
        Initialize backtest result

        Args:
            portfolio_values: DataFrame with portfolio values over time
            returns: DataFrame with daily returns
            trades: DataFrame with all trades
            positions: DataFrame with position history
            initial_capital: Initial capital
        """
        self.portfolio_values = portfolio_values
        self.returns = returns
        self.trades = trades
        self.positions = positions
        self.initial_capital = initial_capital

        # Calculate summary statistics
        if not returns.empty:
            self.returns_series = returns.set_index('date')['return']
        else:
            self.returns_series = pd.Series(dtype=float)

    def get_final_value(self) -> float:
        """Get final portfolio value"""
        if self.portfolio_values.empty:
            return self.initial_capital
        return self.portfolio_values.iloc[-1]['value']

    def get_total_return(self) -> float:
        """Get total return"""
        final_value = self.get_final_value()
        return (final_value - self.initial_capital) / self.initial_capital

    def get_equity_curve(self) -> pd.Series:
        """Get equity curve as Series"""
        if self.portfolio_values.empty:
            return pd.Series(dtype=float)
        return self.portfolio_values.set_index('date')['value']

    def get_daily_returns(self) -> pd.Series:
        """Get daily returns as Series

        Returns:
            pd.Series: Daily returns indexed by date
        """
        return self.returns_series
