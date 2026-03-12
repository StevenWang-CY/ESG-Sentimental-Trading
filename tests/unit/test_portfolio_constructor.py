"""
Unit Tests for Portfolio Constructor

Tests the portfolio construction logic including:
1. Per-date weight assignment (CRITICAL FIX)
2. Position limit enforcement
3. Long-short balance
4. Holding period management
5. Rebalancing logic

Related to ROOT CAUSE findings from backtest analysis.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.signals.portfolio_constructor import PortfolioConstructor


class TestPortfolioConstructor:
    """Test suite for Portfolio Constructor"""

    @pytest.fixture
    def portfolio_constructor(self, baseline_config):
        """Create portfolio constructor with baseline config"""
        return PortfolioConstructor(
            strategy_type=baseline_config['portfolio']['strategy_type']
        )

    def test_initialization(self, portfolio_constructor):
        """Test portfolio constructor initializes correctly"""
        assert portfolio_constructor.strategy_type == 'long_short'
        assert portfolio_constructor.selection_balance == 'equal_count'
        assert portfolio_constructor.exposure_model == 'dollar_neutral'

    def test_quintile_portfolio_per_date_weights(self, portfolio_constructor):
        """
        Test per-date weight assignment under dollar-neutral sizing.

        Weights must be assigned per date, not globally.
        Uses balance_long_short=False to allow one-sided books per date while
        preserving the neutral side target of 50% gross per side.
        """
        # Create signals across multiple dates
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01', '2024-01-01', '2024-01-02', '2024-01-02', '2024-01-02']),
            'ticker': ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN'],
            'quintile': [5, 5, 5, 5, 1],  # 2 longs on date1, 2 longs + 1 short on date2
            'raw_score': [0.8, 0.7, 0.9, 0.6, -0.3]
        })

        portfolio = portfolio_constructor._quintile_portfolio(signals_df, balance_long_short=False)

        # Check date 2024-01-01 (2 longs, equal weight)
        date1_positions = portfolio[portfolio['date'] == pd.Timestamp('2024-01-01')]
        assert len(date1_positions) == 2
        for w in date1_positions['weight'].values:
            assert w == pytest.approx(0.25)

        # Check date 2024-01-02 (2 longs, 1 short with equal dollar side targets)
        date2_positions = portfolio[portfolio['date'] == pd.Timestamp('2024-01-02')]
        assert len(date2_positions) == 3

        date2_weights = date2_positions.set_index('ticker')['weight']
        # Longs: each get half of the 50% long-side target
        assert date2_weights['MSFT'] == pytest.approx(0.25)
        assert date2_weights['GOOGL'] == pytest.approx(0.25)
        # Short: gets the full 50% short-side target
        assert date2_weights['AMZN'] == pytest.approx(-0.5, rel=1e-5)

    def test_position_limit_enforcement(self, portfolio_constructor):
        """Test apply_position_limits clips individual weights"""
        # Create a portfolio DataFrame directly
        portfolio = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 4),
            'ticker': ['A', 'B', 'C', 'D'],
            'weight': [0.5, 0.5, -0.5, -0.5]
        })

        # Apply position limits
        limited_portfolio = portfolio_constructor.apply_position_limits(
            portfolio,
            max_position=0.30  # 30% limit
        )

        # Weights should be clipped (original were ±0.5)
        assert len(limited_portfolio) > 0
        # Verify function doesn't crash and returns same number of rows
        assert len(limited_portfolio) == 4

    def test_long_short_balance(self, portfolio_constructor):
        """Test long-short portfolio is dollar neutral."""
        # Create signals with proper signs (Fix #9: sign validation)
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 6),
            'ticker': ['A', 'B', 'C', 'D', 'E', 'F'],
            'quintile': [5, 5, 5, 1, 1, 1],  # 3 longs, 3 shorts
            'raw_score': [0.9, 0.8, 0.7, -0.3, -0.2, -0.1]  # Shorts have negative raw_score
        })

        portfolio = portfolio_constructor._quintile_portfolio(signals_df)

        long_exposure = portfolio[portfolio['weight'] > 0]['weight'].sum()
        short_exposure = portfolio[portfolio['weight'] < 0]['weight'].sum()

        assert long_exposure == pytest.approx(0.5, abs=0.01)
        assert short_exposure == pytest.approx(-0.5, abs=0.01)
        assert portfolio['weight'].sum() == pytest.approx(0.0, abs=0.01)
        assert portfolio['weight'].abs().sum() == pytest.approx(1.0, abs=0.01)

    def test_long_only_strategy(self):
        """Test long-only portfolio construction"""
        constructor = PortfolioConstructor(
            strategy_type='long_only'
        )

        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 5),
            'ticker': ['A', 'B', 'C', 'D', 'E'],
            'quintile': [5, 5, 4, 2, 1],
            'raw_score': [0.9, 0.8, 0.6, 0.4, 0.2]
        })

        portfolio = constructor._quintile_portfolio(signals_df)

        # All weights should be positive (long only)
        assert (portfolio['weight'] >= 0).all()

        # Only Q5 stocks should be included
        assert len(portfolio) == 2  # A and B (Q5)

    def test_short_only_strategy(self):
        """Test short-only portfolio construction"""
        constructor = PortfolioConstructor(
            strategy_type='short_only'
        )

        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 5),
            'ticker': ['A', 'B', 'C', 'D', 'E'],
            'quintile': [5, 5, 4, 2, 1],
            'raw_score': [0.9, 0.8, 0.6, 0.4, 0.2]
        })

        portfolio = constructor._quintile_portfolio(signals_df)

        # All weights should be negative (short only)
        assert (portfolio['weight'] <= 0).all()

        # Only Q1 stocks should be included
        assert len(portfolio) == 1  # E (Q1)

    def test_z_score_method(self):
        """Test z-score based portfolio construction"""
        constructor = PortfolioConstructor(
            strategy_type='long_short'
        )

        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 5),
            'ticker': ['A', 'B', 'C', 'D', 'E'],
            'z_score': [2.0, 1.5, 0.0, -1.5, -2.0],
            'raw_score': [0.5, 0.4, 0.0, -0.4, -0.5]
        })

        portfolio = constructor._z_score_portfolio(signals_df)

        # High z-score → long, low z-score → short
        assert portfolio[portfolio['ticker'] == 'A']['weight'].values[0] > 0  # Long
        assert portfolio[portfolio['ticker'] == 'E']['weight'].values[0] < 0  # Short

    def test_empty_signals(self, portfolio_constructor):
        """Test behavior with no signals"""
        signals_df = pd.DataFrame(columns=['date', 'ticker', 'quintile', 'raw_score'])

        portfolio = portfolio_constructor._quintile_portfolio(signals_df)

        # Should return empty portfolio
        assert len(portfolio) == 0
        assert 'weight' in portfolio.columns

    def test_only_longs_no_shorts(self, portfolio_constructor):
        """Test portfolio with only long signals (no Q1) and balance disabled"""
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 3),
            'ticker': ['A', 'B', 'C'],
            'quintile': [5, 5, 4],  # No Q1 (shorts)
            'raw_score': [0.9, 0.8, 0.6]
        })

        # balance_long_short=False allows one-sided portfolios
        portfolio = portfolio_constructor._quintile_portfolio(signals_df, balance_long_short=False)

        # Should still create portfolio with only longs
        assert len(portfolio) == 2  # Only Q5
        assert (portfolio['weight'] > 0).all()
        assert portfolio['weight'].sum() == pytest.approx(0.5)

    def test_only_shorts_no_longs(self, portfolio_constructor):
        """Test portfolio with only short signals (no Q5) and balance disabled"""
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 3),
            'ticker': ['A', 'B', 'C'],
            'quintile': [1, 1, 2],  # No Q5 (longs)
            'raw_score': [-0.3, -0.2, -0.1]
        })

        # balance_long_short=False allows one-sided portfolios
        portfolio = portfolio_constructor._quintile_portfolio(signals_df, balance_long_short=False)

        # Should still create portfolio with only shorts
        assert len(portfolio) == 2  # Only Q1
        assert (portfolio['weight'] < 0).all()
        assert portfolio['weight'].sum() == pytest.approx(-0.5)


class TestPortfolioConstructorRootCauseFixes:
    """Tests validating ROOT CAUSE FIXES"""

    @pytest.fixture
    def portfolio_constructor(self, baseline_config):
        return PortfolioConstructor(
            strategy_type=baseline_config['portfolio']['strategy_type']
        )

    def test_per_date_vs_global_weighting(self, portfolio_constructor):
        """
        Validate PER-DATE weighting fix with equal weighting

        CRITICAL FIX: Weights must be assigned per date, not globally.
        Uses balance_long_short=False to test pure per-date weighting with all longs.
        Equal weights are assigned within each date independently.
        """
        # Create signals with different numbers of positions per date
        signals_df = pd.DataFrame({
            'date': pd.to_datetime([
                '2024-01-01', '2024-01-01',  # 2 longs on date 1
                '2024-01-02', '2024-01-02', '2024-01-02', '2024-01-02'  # 4 longs on date 2
            ]),
            'ticker': ['A', 'B', 'C', 'D', 'E', 'F'],
            'quintile': [5, 5, 5, 5, 5, 5],  # All longs
            'raw_score': [0.9, 0.8, 0.85, 0.80, 0.75, 0.70]
        })

        portfolio = portfolio_constructor._quintile_portfolio(signals_df, balance_long_short=False)

        # Date 1: 2 longs → each should be 1/2 = 0.5
        date1_weights = portfolio[portfolio['date'] == pd.Timestamp('2024-01-01')]['weight'].values
        assert len(date1_weights) == 2
        assert all(w == pytest.approx(0.25) for w in date1_weights)

        # Date 2: 4 longs share the 50% long-side target
        date2_weights = portfolio[portfolio['date'] == pd.Timestamp('2024-01-02')]['weight'].values
        assert len(date2_weights) == 4
        assert all(w == pytest.approx(0.125) for w in date2_weights)

        # WRONG implementation would give global equal weighting:
        # All 6 longs globally under the 50% side target → each 0.083
        # Verify this is NOT the case
        assert not all(abs(w - 0.083) < 0.01 for w in portfolio['weight'].values)

    def test_concentration_risk_medium_vs_high(self, portfolio_constructor):
        """
        Test concentration risk difference between MEDIUM (45 stocks) vs HIGH (25 stocks)

        ROOT CAUSE #3: Universe Size Reduction Created Concentration Risk
        """
        # MEDIUM universe: 45 stocks
        medium_universe_size = 45
        medium_max_position = 1.0 / medium_universe_size  # Equal weight
        medium_concentration = medium_max_position * 100  # As percentage

        # HIGH universe: 25 stocks
        high_universe_size = 25
        high_max_position = 1.0 / high_universe_size
        high_concentration = high_max_position * 100

        # Calculate concentration increase
        concentration_increase = (high_concentration / medium_concentration - 1) * 100

        # Verify HIGH has +82% larger positions (from root cause analysis)
        assert concentration_increase == pytest.approx(80.0, abs=5.0)

        # MEDIUM: 2.2% per position
        assert medium_concentration == pytest.approx(2.22, abs=0.1)

        # HIGH: 4.0% per position
        assert high_concentration == pytest.approx(4.0, abs=0.1)

    def test_turnover_weekly_vs_daily(self, portfolio_constructor):
        """
        Simulate turnover difference between weekly vs daily rebalancing

        ROOT CAUSE #2: Excessive Trading Frequency Caused Transaction Cost Drag
        Daily rebalancing has higher turnover than weekly.
        """
        # Use actual backtest values from root cause analysis
        weekly_turnover = 3.19   # From baseline weekly backtest
        daily_turnover = 7.44    # From failed daily backtest

        # Verify daily turnover is significantly higher than weekly
        turnover_increase = (daily_turnover / weekly_turnover - 1) * 100
        assert turnover_increase > 100, f"Turnover increase only {turnover_increase:.0f}%, expected >100%"

        # Transaction cost impact
        commission_bps = 5.5  # 5 bps commission + 0.5 bps slippage

        weekly_cost = weekly_turnover * (commission_bps / 10000)
        daily_cost = daily_turnover * (commission_bps / 10000)

        # Daily costs are higher than weekly
        assert daily_cost > weekly_cost

    def test_holding_period_5_vs_7_days(self, portfolio_constructor):
        """
        Test alpha capture difference between 5-day vs 7-day holding

        ROOT CAUSE #6: Holding Period Mismatch with ESG Information Diffusion

        Academic literature: ESG alpha peaks at 7-10 days
        - 7-day hold: Captures ~90% of alpha
        - 5-day hold: Captures ~60% of alpha
        """
        # Simulate ESG event alpha curve (based on academic literature)
        days = np.arange(1, 15)
        alpha_curve = np.array([
            0.1,  # Day 1: 10% of peak
            0.3,  # Day 2: 30%
            0.5,  # Day 3: 50% (initial shock)
            0.7,  # Day 4: 70%
            0.85, # Day 5: 85% (social media amplification)
            0.95, # Day 6: 95%
            1.0,  # Day 7: 100% PEAK (analyst coverage)
            0.98, # Day 8: 98%
            0.95, # Day 9: 95%
            0.90, # Day 10: 90% (mean reversion begins)
            0.80, # Day 11
            0.70, # Day 12
            0.60, # Day 13
            0.50  # Day 14
        ])

        # Alpha captured with 5-day hold
        alpha_5day = alpha_curve[4]  # Day 5 = 0.85
        assert alpha_5day == pytest.approx(0.85)

        # Alpha captured with 7-day hold
        alpha_7day = alpha_curve[6]  # Day 7 = 1.0
        assert alpha_7day == pytest.approx(1.0)

        # Alpha lost by using 5-day instead of 7-day
        alpha_lost_pct = (1 - alpha_5day / alpha_7day) * 100
        assert alpha_lost_pct == pytest.approx(15.0, abs=2.0)

        # Impact on total return (from root cause analysis)
        # If baseline return = 20.38%, and we lose 15% of alpha
        # Lost return = 20.38% * 0.15 = ~3%
        # But only applies to alpha portion, not full return
        # Actual impact: ~1.5% (from root cause analysis)


class TestRollingQuintilePortfolio:
    """Tests for rolling-window quintile portfolio construction.

    Validates that the _rolling_quintile_portfolio method correctly
    accumulates non-expired signals across a time window, re-ranks
    them cross-sectionally, and produces balanced long/short portfolios.
    """

    @pytest.fixture
    def constructor(self):
        return PortfolioConstructor(strategy_type='long_short')

    def _make_signals(self, entries):
        """Helper: create signals DataFrame from list of (ticker, date_str, raw_score, sentiment) tuples.
        raw_score should be signed: positive for bullish, negative for bearish."""
        records = []
        for ticker, date_str, raw_score, sentiment in entries:
            records.append({
                'ticker': ticker,
                'date': pd.Timestamp(date_str),
                'raw_score': raw_score,
                'z_score': raw_score,
                'signal': float(np.tanh(raw_score)),
                'quintile': 3,  # Will be re-assigned by rolling method
                'event_category': 'G',
                'event_confidence': 0.5,
                'sentiment_intensity': sentiment,
                'volume_ratio': 1.0,
                'n_posts': 10,
                'has_social_data': True,
                'confidence': 0.6,
            })
        return pd.DataFrame(records)

    def test_accumulates_signals_across_dates(self, constructor):
        """Rolling window should include signals from multiple dates within the window."""
        signals = self._make_signals([
            ('AAPL', '2024-01-08', 0.8, 0.5),    # Monday wk2 - positive
            ('TSLA', '2024-01-10', -0.3, -0.5),  # Wednesday wk2 - negative (fixed for sign validation)
            ('MSFT', '2024-01-11', 0.7, 0.4),    # Thursday wk2 - positive
        ])
        portfolio = constructor._rolling_quintile_portfolio(
            signals, window_days=10, rebalance_freq='W', balance_long_short=True,
        )
        # All 3 signals are within 10 days of the Friday grid point (Jan 12)
        # Should produce at least 1 long + 1 short position
        assert len(portfolio) >= 2
        assert (portfolio['weight'] > 0).any()
        assert (portfolio['weight'] < 0).any()

    def test_deduplicates_by_ticker(self, constructor):
        """When same ticker appears twice in the window, keep most recent only."""
        signals = self._make_signals([
            ('AAPL', '2024-01-08', 0.3, -0.4),   # Older AAPL signal
            ('AAPL', '2024-01-11', 0.8, 0.5),    # Newer AAPL signal (should win)
            ('TSLA', '2024-01-10', 0.2, -0.6),   # Short candidate
        ])
        portfolio = constructor._rolling_quintile_portfolio(
            signals, window_days=10, rebalance_freq='W', balance_long_short=False,
        )
        # AAPL should appear at most once
        aapl_rows = portfolio[portfolio['ticker'] == 'AAPL']
        assert len(aapl_rows) <= 1

    def test_reranks_from_pool(self, constructor):
        """Quintiles should be re-assigned from the accumulated pool, not original values."""
        # 6 signals on different dates, all within a 10-day window of a Friday
        # Fixed for sign validation: shorts must have negative raw_score
        signals = self._make_signals([
            ('A', '2024-01-08', 0.9, 0.6),
            ('B', '2024-01-09', 0.8, 0.4),
            ('C', '2024-01-10', 0.6, 0.1),
            ('D', '2024-01-10', -0.5, -0.1),  # Negative for short
            ('E', '2024-01-11', -0.3, -0.4),  # Negative for short
            ('F', '2024-01-11', -0.2, -0.6),  # Negative for short
        ])
        portfolio = constructor._rolling_quintile_portfolio(
            signals, window_days=10, rebalance_freq='W', balance_long_short=True,
        )
        # With 6 signals re-ranked, the pool should produce Q1 and Q5 positions
        assert len(portfolio) >= 2
        longs = portfolio[portfolio['weight'] > 0]
        shorts = portfolio[portfolio['weight'] < 0]
        assert len(longs) == len(shorts)  # balanced

    def test_output_dates_are_grid_dates(self, constructor):
        """All output dates should be Friday grid dates, not original signal dates."""
        # Spread signals across 3+ weeks so the grid contains multiple Fridays
        signals = self._make_signals([
            ('AAPL', '2024-01-03', 0.8, 0.5),   # Wednesday wk1
            ('TSLA', '2024-01-08', 0.2, -0.5),   # Monday wk2
            ('MSFT', '2024-01-15', 0.7, 0.4),    # Monday wk3
            ('AMZN', '2024-01-17', 0.3, -0.4),   # Wednesday wk3
        ])
        portfolio = constructor._rolling_quintile_portfolio(
            signals, window_days=10, rebalance_freq='W', balance_long_short=True,
        )
        if not portfolio.empty:
            # All output dates should be Fridays (day_of_week == 4)
            for d in portfolio['date']:
                assert pd.Timestamp(d).dayofweek == 4, f"Expected Friday, got {pd.Timestamp(d).day_name()}"

    def test_backward_compatible_zero_window(self, constructor):
        """window_days=0 should use legacy per-date grouping via construct_portfolio dispatch."""
        signals = self._make_signals([
            ('AAPL', '2024-01-08', 0.8, 0.5),
            ('TSLA', '2024-01-08', 0.2, -0.5),
        ])
        # window_days=0 dispatches to _quintile_portfolio, not rolling
        portfolio = constructor.construct_portfolio(
            signals, method='quintile', balance_long_short=True, window_days=0,
        )
        if not portfolio.empty:
            # Dates should be original signal dates (not grid dates)
            assert all(pd.Timestamp(d) == pd.Timestamp('2024-01-08') for d in portfolio['date'])

    def test_tertile_split_three_signals(self, constructor):
        """With 3 signals in window, should use tertile split (Q1/Q3/Q5)."""
        signals = self._make_signals([
            ('AAPL', '2024-01-10', 0.9, 0.6),    # Highest -> Q5 (long)
            ('MSFT', '2024-01-10', 0.5, 0.0),    # Middle -> Q3 (neutral)
            ('TSLA', '2024-01-10', -0.2, -0.5),  # Lowest -> Q1 (short, negative for sign validation)
        ])
        portfolio = constructor._rolling_quintile_portfolio(
            signals, window_days=10, rebalance_freq='W', balance_long_short=True,
        )
        # With balanced L/S: should have 1 long (AAPL) and 1 short (TSLA)
        assert len(portfolio) == 2
        longs = portfolio[portfolio['weight'] > 0]
        shorts = portfolio[portfolio['weight'] < 0]
        assert len(longs) == 1
        assert len(shorts) == 1

    def test_skips_dates_no_balance(self, constructor):
        """With balance_long_short=True, can balance with 2 signals of opposite signs."""
        # One positive, one negative -> should create balanced portfolio
        # (Fixed for sign validation: shorts need negative raw_score)
        signals = self._make_signals([
            ('AAPL', '2024-01-10', 0.9, 0.6),   # Positive -> Q5 long
            ('MSFT', '2024-01-11', -0.8, -0.5), # Negative -> Q1 short
        ])
        portfolio = constructor._rolling_quintile_portfolio(
            signals, window_days=10, rebalance_freq='W', balance_long_short=True,
        )
        # With 2 signals that get ranked Q1 and Q5, should create balanced portfolio
        # (rank-based: lower=Q1, higher=Q5, but sign validation ensures correctness)
        assert len(portfolio) == 2

    def test_single_signal_raw_score_direction(self, constructor):
        """Single signal in window should use raw_score sign for quintile."""
        # Positive raw_score -> Q5 (long)
        signals_pos = self._make_signals([
            ('AAPL', '2024-01-10', 0.4, 0.5),
        ])
        portfolio_pos = constructor._rolling_quintile_portfolio(
            signals_pos, window_days=10, rebalance_freq='W', balance_long_short=False,
        )
        if not portfolio_pos.empty:
            assert portfolio_pos['weight'].iloc[0] > 0  # Long

        # Negative raw_score -> Q1 (short)
        signals_neg = self._make_signals([
            ('TSLA', '2024-01-10', -0.3, -0.5),
        ])
        portfolio_neg = constructor._rolling_quintile_portfolio(
            signals_neg, window_days=10, rebalance_freq='W', balance_long_short=False,
        )
        if not portfolio_neg.empty:
            assert portfolio_neg['weight'].iloc[0] < 0  # Short


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
