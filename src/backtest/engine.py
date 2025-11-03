"""
Backtesting Engine
Simulates strategy performance on historical data
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional


class BacktestEngine:
    """
    Simple vectorized backtesting engine for signal-based strategies
    """

    def __init__(self, prices: pd.DataFrame, initial_capital: float = 1000000.0,
                 commission_pct: float = 0.0005, slippage_bps: float = 3):
        """
        Initialize backtest engine

        Args:
            prices: Price DataFrame with multi-index (date, ticker)
            initial_capital: Starting capital
            commission_pct: Commission as percentage (e.g., 0.0005 = 5 bps)
            slippage_bps: Slippage in basis points
        """
        self.prices = prices
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_bct = slippage_bps / 10000

        self.portfolio_value = []
        self.positions = []
        self.trades = []
        self.daily_returns = []

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

        # Get rebalancing dates
        rebalance_dates = self._get_rebalance_dates(signals, rebalance_freq)

        # Initialize tracking
        capital = self.initial_capital
        current_positions = {}
        portfolio_values = []
        returns = []

        # Get all trading dates from prices
        if isinstance(self.prices.index, pd.MultiIndex):
            all_dates = sorted(self.prices.index.get_level_values(0).unique())
        else:
            all_dates = sorted(self.prices.index.unique())

        # Simulate trading
        for i, date in enumerate(all_dates):
            # Check if we should rebalance
            if date in rebalance_dates:
                current_positions = self._rebalance(
                    date, signals, current_positions, capital
                )

            # Calculate portfolio value
            portfolio_value = self._calculate_portfolio_value(
                date, current_positions, capital
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

            # Update capital (mark-to-market)
            capital = portfolio_value

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

    def _rebalance(self, date: datetime, signals: pd.DataFrame,
                   current_positions: Dict, capital: float) -> Dict:
        """Execute rebalancing"""
        # Get target weights for this date
        target_signals = signals[signals['date'] == date]

        if target_signals.empty:
            return current_positions

        # Calculate target positions
        new_positions = {}

        for _, row in target_signals.iterrows():
            ticker = row['ticker']
            weight = row['weight']

            # Get current price
            price = self._get_price(date, ticker)

            if price is None or price <= 0:
                continue

            # Calculate target dollar amount
            target_value = capital * weight

            # Calculate shares (accounting for transaction costs)
            if target_value > 0:
                shares = int(target_value / (price * (1 + self.commission_pct + self.slippage_bct)))
            else:
                shares = int(target_value / (price * (1 - self.commission_pct - self.slippage_bct)))

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

        return new_positions

    def _calculate_portfolio_value(self, date: datetime,
                                   positions: Dict, cash: float) -> float:
        """Calculate total portfolio value"""
        total_value = 0

        for ticker, position in positions.items():
            price = self._get_price(date, ticker)
            if price:
                total_value += position['shares'] * price

        return total_value if total_value > 0 else cash

    def _get_price(self, date: datetime, ticker: str,
                   price_type: str = 'Close') -> Optional[float]:
        """Get price for ticker on date"""
        try:
            if isinstance(self.prices.index, pd.MultiIndex):
                price_data = self.prices.xs(ticker, level='ticker')
                if date in price_data.index:
                    return price_data.loc[date, price_type]
                else:
                    # Try to find nearest date
                    nearest_date = price_data.index[price_data.index >= date].min()
                    if pd.notna(nearest_date):
                        return price_data.loc[nearest_date, price_type]
            else:
                if date in self.prices.index and ticker in self.prices.columns:
                    return self.prices.loc[date, ticker]

            return None
        except:
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
