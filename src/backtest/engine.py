"""
Backtesting Engine
Simulates strategy performance on historical data with comprehensive risk management
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
                 max_drawdown_threshold: float = 0.15):
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
        """
        self.prices = prices
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_bct = slippage_bps / 10000
        self.enable_risk_management = enable_risk_management and RISK_MANAGEMENT_AVAILABLE

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
                min_positions=5  # Minimum diversification
            )
            self.drawdown_controller = DrawdownController(
                drawdown_thresholds=[-0.05, -0.10, -0.15, -0.20],
                exposure_levels=[0.9, 0.75, 0.60, 0.50]
            )
            print(f"Risk management enabled: max_pos={max_position_size:.1%}, "
                  f"target_vol={target_volatility:.1%}, max_dd={max_drawdown_threshold:.1%}")
        else:
            self.risk_manager = None
            self.drawdown_controller = None

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
        """Get rebalancing dates based on frequency"""
        signal_dates = signals['date'].unique()
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
                    # Apply transaction costs
                    cash -= abs(proceeds) * (self.commission_pct + self.slippage_bct)
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
            print(f"DEBUG:   WARNING: No signals found for {date}")
            return {}, cash

        # Apply risk management if enabled
        if self.enable_risk_management and self.risk_manager is not None:
            # Calculate returns history for volatility targeting
            if len(self.daily_returns) > 0:
                returns_series = pd.Series([r['return'] for r in self.daily_returns])
            else:
                returns_series = None

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

            # Calculate shares (accounting for transaction costs)
            if target_value > 0:
                # Long position
                shares = int(target_value / (price * (1 + self.commission_pct + self.slippage_bct)))
                cost = shares * price * (1 + self.commission_pct + self.slippage_bct)
                cash -= cost
                print(f"DEBUG:     LONG: {shares} shares @ ${price:.2f} = ${cost:,.2f}")
            else:
                # Short position (negative shares)
                shares = int(target_value / (price * (1 - self.commission_pct - self.slippage_bct)))
                proceeds = abs(shares) * price * (1 - self.commission_pct - self.slippage_bct)
                cash += proceeds
                print(f"DEBUG:     SHORT: {shares} shares @ ${price:.2f} = ${proceeds:,.2f}")

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
