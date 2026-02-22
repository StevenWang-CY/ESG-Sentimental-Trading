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
                          method: str = 'quintile',
                          balance_long_short: bool = True,
                          window_days: int = 0,
                          rebalance_freq: str = 'W') -> pd.DataFrame:
        """
        Convert signals to portfolio weights

        Args:
            signals_df: DataFrame with columns [ticker, date, signal, quintile]
            method: 'quintile' or 'z_score'
            balance_long_short: If True, enforce equal long/short positions
            window_days: Rolling window in calendar days for signal accumulation.
                         When > 0, uses rolling window to accumulate non-expired
                         signals at each rebalance date. When 0, uses legacy
                         per-date grouping.
            rebalance_freq: Rebalance grid frequency ('W'=weekly, 'M'=monthly)

        Returns:
            DataFrame with columns [ticker, date, weight]
        """
        if signals_df.empty:
            return pd.DataFrame(columns=['ticker', 'date', 'weight'])

        if method == 'quintile':
            if window_days > 0:
                return self._rolling_quintile_portfolio(
                    signals_df,
                    window_days=window_days,
                    rebalance_freq=rebalance_freq,
                    balance_long_short=balance_long_short,
                )
            return self._quintile_portfolio(signals_df, balance_long_short=balance_long_short)
        elif method == 'z_score':
            return self._z_score_portfolio(signals_df)
        else:
            raise ValueError(f"Unknown method: {method}")

    def _quintile_portfolio(self, signals_df: pd.DataFrame,
                            balance_long_short: bool = True) -> pd.DataFrame:
        """
        Classic quintile approach: Long Q5, Short Q1
        CRITICAL: Weights are assigned PER DATE (not globally)

        ROOT CAUSE FIX (Dec 2025):
        - Unbalanced long/short (61 long vs 109 short) caused systematic short bias
        - Now balances positions to ensure true market neutrality
        - Takes min(n_long, n_short) positions from each side

        Args:
            signals_df: Signals DataFrame
            balance_long_short: If True, ensure equal number of longs and shorts

        Returns:
            Portfolio weights DataFrame
        """
        signals_df = signals_df.copy()

        # CRITICAL FIX: Group by date and assign weights within each date
        portfolio_list = []

        for date, group in signals_df.groupby('date'):
            # Filter by quintiles for this specific date
            long_stocks = group[group['quintile'] == 5].copy()
            short_stocks = group[group['quintile'] == 1].copy()

            n_long = len(long_stocks)
            n_short = len(short_stocks)

            # ROOT CAUSE FIX #4: Balance long/short positions
            # Academic basis: Market-neutral requires equal long/short exposure
            # Imbalanced portfolios have unintended market beta
            if balance_long_short and self.strategy_type == 'long_short':
                n_positions = min(n_long, n_short)

                if n_positions == 0:
                    # Skip this date if we can't balance
                    continue

                # Sort by confidence/signal strength and take top N from each side
                if 'confidence' in long_stocks.columns:
                    long_stocks = long_stocks.nlargest(n_positions, 'confidence')
                    short_stocks = short_stocks.nlargest(n_positions, 'confidence')
                elif 'raw_score' in long_stocks.columns:
                    long_stocks = long_stocks.nlargest(n_positions, 'raw_score')
                    short_stocks = short_stocks.nsmallest(n_positions, 'raw_score')
                else:
                    long_stocks = long_stocks.head(n_positions)
                    short_stocks = short_stocks.head(n_positions)

                n_long = n_short = n_positions

            # Long-biased weighting (130/30 style)
            # Scientific basis: Negative ESG events are priced faster due to
            # asymmetric attention (Barber & Odean 2008). Long ESG alpha
            # persists longer (Edmans 2011, Eccles et al. 2014).
            # Short dampening: 0.3x reduces short-side drag in trending markets.
            short_dampening = 0.3  # 30% short exposure vs 100% long
            if n_long > 0:
                long_stocks['weight'] = 1.0 / n_long
            if n_short > 0:
                short_stocks['weight'] = -(short_dampening / n_short)

            # Combine for this date
            if self.strategy_type == 'long_short':
                date_portfolio = pd.concat([long_stocks, short_stocks])
            elif self.strategy_type == 'long_only':
                date_portfolio = long_stocks
            elif self.strategy_type == 'short_only':
                date_portfolio = short_stocks
            else:
                date_portfolio = pd.concat([long_stocks, short_stocks])

            if not date_portfolio.empty:
                portfolio_list.append(date_portfolio)

        # Combine all dates
        if portfolio_list:
            portfolio = pd.concat(portfolio_list)

            # Log balance statistics
            long_count = (portfolio['weight'] > 0).sum()
            short_count = (portfolio['weight'] < 0).sum()
            print(f"\n📊 Portfolio Balance (after balancing):")
            print(f"  Long positions: {long_count}")
            print(f"  Short positions: {short_count}")
            print(f"  Balance ratio: {long_count/max(short_count,1):.2f}x")

            return portfolio[['ticker', 'date', 'weight']].reset_index(drop=True)
        else:
            # Return empty DataFrame with correct columns (no Q1 or Q5 signals found)
            return pd.DataFrame(columns=['ticker', 'date', 'weight'])

    def _rolling_quintile_portfolio(self, signals_df: pd.DataFrame,
                                     window_days: int = 10,
                                     rebalance_freq: str = 'W',
                                     balance_long_short: bool = True) -> pd.DataFrame:
        """
        Rolling-window quintile portfolio: accumulates non-expired signals
        into a cross-section at each rebalance date, then ranks and weights.

        Event-driven strategies maintain a "signal book" of active events.
        Cross-sectional ranking requires sufficient N; rolling windows
        provide this by treating non-expired signals as active.
        (Barber & Lyon 1997, Lyon, Barber & Tsai 1999)

        Args:
            signals_df: Signals with columns including ticker, date, raw_score,
                        sentiment_intensity, confidence
            window_days: Calendar days to look back for active signals
            rebalance_freq: 'W' (weekly) or 'M' (monthly) grid frequency
            balance_long_short: If True, enforce equal long/short positions

        Returns:
            DataFrame [ticker, date, weight] with date = rebalance grid dates
        """
        signals_df = signals_df.copy()
        signals_df['date'] = pd.to_datetime(signals_df['date'])

        # Generate rebalance grid
        min_date = signals_df['date'].min()
        max_date = signals_df['date'].max()

        freq_map = {'W': 'W-FRI', 'M': 'ME', 'D': 'B'}
        grid_freq = freq_map.get(rebalance_freq, 'W-FRI')
        rebalance_grid = pd.date_range(start=min_date, end=max_date, freq=grid_freq)

        if len(rebalance_grid) == 0:
            rebalance_grid = pd.DatetimeIndex([max_date])

        print(f"\n  Rolling Window Portfolio Construction:")
        print(f"    Window: {window_days} calendar days | Freq: {rebalance_freq}")
        print(f"    Grid points: {len(rebalance_grid)} | Raw signals: {len(signals_df)}")

        portfolio_list = []
        dates_with_positions = 0
        dates_skipped_no_balance = 0

        for rebalance_date in rebalance_grid:
            window_start = rebalance_date - pd.Timedelta(days=window_days)

            active = signals_df[
                (signals_df['date'] > window_start) &
                (signals_df['date'] <= rebalance_date)
            ].copy()

            if active.empty:
                continue

            # De-duplicate: keep most recent signal per ticker
            active = active.sort_values('date', ascending=False)
            active = active.drop_duplicates(subset='ticker', keep='first')

            n_active = len(active)

            # Re-rank the accumulated pool by raw_score
            if n_active >= 5:
                try:
                    active['quintile'] = pd.qcut(
                        active['raw_score'], q=5,
                        labels=[1, 2, 3, 4, 5], duplicates='drop',
                    ).astype(int)
                except (ValueError, TypeError):
                    active['quintile'] = 3
            elif n_active >= 3:
                scores = active['raw_score'].values
                p33 = np.percentile(scores, 33.33)
                p67 = np.percentile(scores, 66.67)
                active['quintile'] = active['raw_score'].apply(
                    lambda s: 1 if s <= p33 else (5 if s >= p67 else 3)
                ).astype(int)
            elif n_active == 2:
                ranks = active['raw_score'].rank(method='first')
                active['quintile'] = ranks.map({1.0: 1, 2.0: 5}).astype(int)
            else:
                # Single signal: use raw_score sign (already encodes direction)
                score = active['raw_score'].iloc[0]
                if score > 0:
                    active['quintile'] = 5
                elif score < 0:
                    active['quintile'] = 1
                else:
                    active['quintile'] = 3

            # FIX #9: Sign-validated quintile assignment
            # Prevent contra-directional trades after re-ranking
            mask_wrong_long = (active['quintile'] == 5) & (active['raw_score'] < 0)
            mask_wrong_short = (active['quintile'] == 1) & (active['raw_score'] > 0)
            active.loc[mask_wrong_long, 'quintile'] = 3
            active.loc[mask_wrong_short, 'quintile'] = 3

            # Select long (Q5) and short (Q1) candidates
            long_stocks = active[active['quintile'] == 5].copy()
            short_stocks = active[active['quintile'] == 1].copy()
            n_long = len(long_stocks)
            n_short = len(short_stocks)

            if balance_long_short and self.strategy_type == 'long_short':
                n_positions = min(n_long, n_short)
                if n_positions == 0:
                    dates_skipped_no_balance += 1
                    continue

                if 'confidence' in long_stocks.columns:
                    long_stocks = long_stocks.nlargest(n_positions, 'confidence')
                    short_stocks = short_stocks.nlargest(n_positions, 'confidence')
                elif 'raw_score' in long_stocks.columns:
                    long_stocks = long_stocks.nlargest(n_positions, 'raw_score')
                    short_stocks = short_stocks.nsmallest(n_positions, 'raw_score')
                else:
                    long_stocks = long_stocks.head(n_positions)
                    short_stocks = short_stocks.head(n_positions)

                n_long = n_short = n_positions

            # Long-biased weighting (130/30 style)
            # Scientific basis: Negative ESG events are priced faster due to
            # asymmetric attention. Long ESG alpha persists longer.
            short_dampening = 0.3  # 30% short exposure vs 100% long
            if n_long > 0:
                long_stocks['weight'] = 1.0 / n_long
            if n_short > 0:
                short_stocks['weight'] = -(short_dampening / n_short)

            # Combine based on strategy type
            if self.strategy_type == 'long_short':
                date_portfolio = pd.concat([long_stocks, short_stocks])
            elif self.strategy_type == 'long_only':
                date_portfolio = long_stocks
            elif self.strategy_type == 'short_only':
                date_portfolio = short_stocks
            else:
                date_portfolio = pd.concat([long_stocks, short_stocks])

            if not date_portfolio.empty:
                # Output date = grid date so engine's exact-match lookup works
                date_portfolio['date'] = rebalance_date
                portfolio_list.append(date_portfolio)
                dates_with_positions += 1

        # Combine all rebalance dates
        if portfolio_list:
            portfolio = pd.concat(portfolio_list)
            long_count = (portfolio['weight'] > 0).sum()
            short_count = (portfolio['weight'] < 0).sum()

            print(f"\n  Rolling Window Portfolio Summary:")
            print(f"    Rebalance dates with positions: {dates_with_positions}")
            print(f"    Dates skipped (no L/S balance): {dates_skipped_no_balance}")
            print(f"    Total long positions: {long_count}")
            print(f"    Total short positions: {short_count}")
            print(f"    Balance ratio: {long_count/max(short_count,1):.2f}x")
            print(f"    Avg positions per rebalance: {len(portfolio)/dates_with_positions:.1f}")

            return portfolio[['ticker', 'date', 'weight']].reset_index(drop=True)
        else:
            print(f"\n  Rolling Window Portfolio: No positions created")
            print(f"    Skipped {dates_skipped_no_balance} dates (no L/S balance)")
            print(f"    Consider increasing window_days (currently {window_days})")
            return pd.DataFrame(columns=['ticker', 'date', 'weight'])

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
            # Normalize short weights to sum to -1.0 (preserving negative sign).
            # short_sum is abs() of negatives (positive number), so divide by +short_sum.
            # Previous bug: /= -short_sum flipped negative weights to positive.
            portfolio.loc[portfolio['weight'] < 0, 'weight'] /= short_sum

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
            return {
                'n_positions': 0,
                'n_long': 0,
                'n_short': 0,
                'total_long_weight': 0.0,
                'total_short_weight': 0.0,
                'net_exposure': 0.0,
                'gross_exposure': 0.0,
                'avg_position_size': 0.0
            }

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
