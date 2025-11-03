"""
Portfolio Constructor
Converts signals to portfolio weights for trading
"""

import pandas as pd
import numpy as np
from typing import Optional


class PortfolioConstructor:
    """
    Converts signals to portfolio weights
    """

    def __init__(self, strategy_type: str = 'long_short'):
        """
        Initialize portfolio constructor

        Args:
            strategy_type: 'long_short', 'long_only', or 'short_only'
        """
        self.strategy_type = strategy_type

    def construct_portfolio(self, signals_df: pd.DataFrame,
                          method: str = 'quintile') -> pd.DataFrame:
        """
        Convert signals to portfolio weights

        Args:
            signals_df: DataFrame with columns [ticker, date, signal, quintile]
            method: 'quintile' or 'z_score'

        Returns:
            DataFrame with columns [ticker, date, weight]
        """
        if signals_df.empty:
            return pd.DataFrame(columns=['ticker', 'date', 'weight'])

        if method == 'quintile':
            return self._quintile_portfolio(signals_df)
        elif method == 'z_score':
            return self._z_score_portfolio(signals_df)
        else:
            raise ValueError(f"Unknown method: {method}")

    def _quintile_portfolio(self, signals_df: pd.DataFrame) -> pd.DataFrame:
        """
        Classic quintile approach: Long Q5, Short Q1

        Args:
            signals_df: Signals DataFrame

        Returns:
            Portfolio weights DataFrame
        """
        signals_df = signals_df.copy()

        # Filter by quintiles
        long_stocks = signals_df[signals_df['quintile'] == 5]
        short_stocks = signals_df[signals_df['quintile'] == 1]

        # Calculate equal weights
        long_weight = 1.0 / len(long_stocks) if len(long_stocks) > 0 else 0
        short_weight = -1.0 / len(short_stocks) if len(short_stocks) > 0 else 0

        # Assign weights
        long_stocks = long_stocks.copy()
        short_stocks = short_stocks.copy()

        long_stocks['weight'] = long_weight
        short_stocks['weight'] = short_weight

        # Combine
        if self.strategy_type == 'long_short':
            portfolio = pd.concat([long_stocks, short_stocks])
        elif self.strategy_type == 'long_only':
            portfolio = long_stocks
        elif self.strategy_type == 'short_only':
            portfolio = short_stocks
        else:
            portfolio = pd.concat([long_stocks, short_stocks])

        return portfolio[['ticker', 'date', 'weight']].reset_index(drop=True)

    def _z_score_portfolio(self, signals_df: pd.DataFrame) -> pd.DataFrame:
        """
        Continuous weighting by z-score

        Args:
            signals_df: Signals DataFrame

        Returns:
            Portfolio weights DataFrame
        """
        signals_df = signals_df.copy()

        # Use z_score as raw weight
        signals_df['raw_weight'] = signals_df['z_score']

        # Normalize to dollar-neutral
        long_sum = signals_df[signals_df['raw_weight'] > 0]['raw_weight'].sum()
        short_sum = signals_df[signals_df['raw_weight'] < 0]['raw_weight'].abs().sum()

        def normalize_weight(x):
            if x > 0 and long_sum > 0:
                return x / long_sum
            elif x < 0 and short_sum > 0:
                return x / short_sum
            else:
                return 0.0

        signals_df['weight'] = signals_df['raw_weight'].apply(normalize_weight)

        # Filter by strategy type
        if self.strategy_type == 'long_only':
            signals_df = signals_df[signals_df['weight'] > 0]
        elif self.strategy_type == 'short_only':
            signals_df = signals_df[signals_df['weight'] < 0]

        return signals_df[['ticker', 'date', 'weight']].reset_index(drop=True)

    def apply_position_limits(self, portfolio: pd.DataFrame,
                             max_position: float = 0.1) -> pd.DataFrame:
        """
        Apply position size limits

        Args:
            portfolio: Portfolio DataFrame
            max_position: Maximum position size (as fraction of total)

        Returns:
            Portfolio with position limits applied
        """
        portfolio = portfolio.copy()

        # Cap individual positions
        portfolio['weight'] = portfolio['weight'].clip(-max_position, max_position)

        # Renormalize to maintain dollar neutrality
        long_sum = portfolio[portfolio['weight'] > 0]['weight'].sum()
        short_sum = portfolio[portfolio['weight'] < 0]['weight'].abs().sum()

        if long_sum > 0:
            portfolio.loc[portfolio['weight'] > 0, 'weight'] /= long_sum
        if short_sum > 0:
            portfolio.loc[portfolio['weight'] < 0, 'weight'] /= -short_sum

        return portfolio

    def get_portfolio_statistics(self, portfolio: pd.DataFrame) -> dict:
        """
        Calculate portfolio statistics

        Args:
            portfolio: Portfolio DataFrame

        Returns:
            Dictionary with statistics
        """
        if portfolio.empty:
            return {'n_positions': 0}

        long_positions = portfolio[portfolio['weight'] > 0]
        short_positions = portfolio[portfolio['weight'] < 0]

        return {
            'n_positions': len(portfolio),
            'n_long': len(long_positions),
            'n_short': len(short_positions),
            'total_long_weight': long_positions['weight'].sum(),
            'total_short_weight': short_positions['weight'].sum(),
            'net_exposure': portfolio['weight'].sum(),
            'gross_exposure': portfolio['weight'].abs().sum(),
            'avg_position_size': portfolio['weight'].abs().mean()
        }

    def rebalance_portfolio(self, current_portfolio: pd.DataFrame,
                           target_portfolio: pd.DataFrame,
                           turnover_limit: Optional[float] = None) -> pd.DataFrame:
        """
        Rebalance from current to target portfolio

        Args:
            current_portfolio: Current portfolio weights
            target_portfolio: Target portfolio weights
            turnover_limit: Maximum turnover allowed (optional)

        Returns:
            New portfolio after rebalancing
        """
        if current_portfolio.empty:
            return target_portfolio

        # Merge current and target
        merged = pd.merge(
            current_portfolio[['ticker', 'weight']].rename(columns={'weight': 'current_weight'}),
            target_portfolio[['ticker', 'weight']].rename(columns={'weight': 'target_weight'}),
            on='ticker',
            how='outer'
        ).fillna(0)

        # Calculate turnover
        merged['trade'] = merged['target_weight'] - merged['current_weight']
        turnover = merged['trade'].abs().sum() / 2  # Divide by 2 for one-sided turnover

        # Apply turnover limit if specified
        if turnover_limit and turnover > turnover_limit:
            scale_factor = turnover_limit / turnover
            merged['trade'] *= scale_factor
            merged['new_weight'] = merged['current_weight'] + merged['trade']
        else:
            merged['new_weight'] = merged['target_weight']

        # Return new portfolio
        new_portfolio = merged[merged['new_weight'] != 0][['ticker', 'new_weight']]
        new_portfolio = new_portfolio.rename(columns={'new_weight': 'weight'})

        return new_portfolio
