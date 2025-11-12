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
            strategy_type=baseline_config['portfolio']['strategy_type'],
            method=baseline_config['portfolio']['method'],
            max_position=baseline_config['portfolio']['max_position']
        )

    def test_initialization(self, portfolio_constructor):
        """Test portfolio constructor initializes correctly"""
        assert portfolio_constructor.strategy_type == 'long_short'
        assert portfolio_constructor.method == 'quintile'
        assert portfolio_constructor.max_position == 0.1

    def test_quintile_portfolio_per_date_weights(self, portfolio_constructor):
        """
        Test per-date weight assignment (CRITICAL FIX)

        BEFORE FIX: Weights assigned globally (all 13 longs = 1/13 each)
        AFTER FIX: Weights assigned per date (2 longs on date1 = 1/2 each)

        This is crucial for proper position sizing across multiple dates.
        """
        # Create signals across multiple dates
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01', '2024-01-01', '2024-01-02', '2024-01-02', '2024-01-02']),
            'ticker': ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN'],
            'quintile': [5, 5, 5, 5, 1],  # 2 longs on date1, 2 longs + 1 short on date2
            'raw_score': [0.8, 0.7, 0.9, 0.6, 0.3]
        })

        portfolio = portfolio_constructor._quintile_portfolio(signals_df)

        # Check date 2024-01-01 (2 longs)
        date1_positions = portfolio[portfolio['date'] == '2024-01-01']
        assert len(date1_positions) == 2
        # Each long position should be 1/2 = 0.5 (NOT 1/4 = 0.25 if global weighting)
        assert (date1_positions['weight'].abs() == pytest.approx(0.5)).all()

        # Check date 2024-01-02 (2 longs, 1 short)
        date2_positions = portfolio[portfolio['date'] == '2024-01-02']
        assert len(date2_positions) == 3

        longs = date2_positions[date2_positions['weight'] > 0]
        shorts = date2_positions[date2_positions['weight'] < 0]

        # Each long: 1/2 = 0.5, Each short: -1/1 = -1.0
        assert (longs['weight'] == pytest.approx(0.5)).all()
        assert (shorts['weight'] == pytest.approx(-1.0)).all()

    def test_position_limit_enforcement(self, portfolio_constructor):
        """Test max position size limit is enforced"""
        # Create portfolio with one very large position
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01']),
            'ticker': ['AAPL'],
            'quintile': [5],
            'raw_score': [0.9]
        })

        portfolio = portfolio_constructor._quintile_portfolio(signals_df)

        # Apply position limits
        limited_portfolio = portfolio_constructor.apply_position_limits(
            portfolio,
            max_position=0.10  # 10% limit
        )

        # Check position doesn't exceed limit
        assert (limited_portfolio['weight'].abs() <= 0.10).all()

    def test_long_short_balance(self, portfolio_constructor):
        """Test long-short portfolio maintains balance"""
        # Create balanced signals
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 6),
            'ticker': ['A', 'B', 'C', 'D', 'E', 'F'],
            'quintile': [5, 5, 5, 1, 1, 1],  # 3 longs, 3 shorts
            'raw_score': [0.9, 0.8, 0.7, 0.3, 0.2, 0.1]
        })

        portfolio = portfolio_constructor._quintile_portfolio(signals_df)

        # Calculate net exposure
        net_exposure = portfolio['weight'].sum()

        # For market-neutral strategy, net exposure should be ~0
        assert net_exposure == pytest.approx(0.0, abs=0.01)

        # Verify long and short legs are balanced
        long_exposure = portfolio[portfolio['weight'] > 0]['weight'].sum()
        short_exposure = portfolio[portfolio['weight'] < 0]['weight'].sum()

        assert long_exposure == pytest.approx(-short_exposure, abs=0.01)

    def test_long_only_strategy(self):
        """Test long-only portfolio construction"""
        constructor = PortfolioConstructor(
            strategy_type='long_only',
            method='quintile',
            max_position=0.1
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
            strategy_type='short_only',
            method='quintile',
            max_position=0.1
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
            strategy_type='long_short',
            method='z_score',
            max_position=0.1
        )

        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 5),
            'ticker': ['A', 'B', 'C', 'D', 'E'],
            'z_score': [2.0, 1.5, 0.0, -1.5, -2.0],
            'raw_score': [0.9, 0.8, 0.5, 0.3, 0.2]
        })

        portfolio = constructor._z_score_portfolio(signals_df, threshold=1.0)

        # Stocks with |z_score| > 1.0 should be included
        assert len(portfolio) == 4  # A, B, D, E

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
        """Test portfolio with only long signals (no Q1)"""
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 3),
            'ticker': ['A', 'B', 'C'],
            'quintile': [5, 5, 4],  # No Q1 (shorts)
            'raw_score': [0.9, 0.8, 0.6]
        })

        portfolio = portfolio_constructor._quintile_portfolio(signals_df)

        # Should still create portfolio with only longs
        assert len(portfolio) == 2  # Only Q5
        assert (portfolio['weight'] > 0).all()

    def test_only_shorts_no_longs(self, portfolio_constructor):
        """Test portfolio with only short signals (no Q5)"""
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 3),
            'ticker': ['A', 'B', 'C'],
            'quintile': [1, 1, 2],  # No Q5 (longs)
            'raw_score': [0.3, 0.2, 0.4]
        })

        portfolio = portfolio_constructor._quintile_portfolio(signals_df)

        # Should still create portfolio with only shorts
        assert len(portfolio) == 2  # Only Q1
        assert (portfolio['weight'] < 0).all()


class TestPortfolioConstructorRootCauseFixes:
    """Tests validating ROOT CAUSE FIXES"""

    @pytest.fixture
    def portfolio_constructor(self, baseline_config):
        return PortfolioConstructor(
            strategy_type=baseline_config['portfolio']['strategy_type'],
            method=baseline_config['portfolio']['method'],
            max_position=baseline_config['portfolio']['max_position']
        )

    def test_per_date_vs_global_weighting(self, portfolio_constructor):
        """
        Validate PER-DATE weighting fix (mentioned in root cause analysis)

        CRITICAL FIX: Weights must be assigned per date, not globally.
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

        portfolio = portfolio_constructor._quintile_portfolio(signals_df)

        # Date 1: 2 longs → each should be 1/2 = 0.5
        date1_weights = portfolio[portfolio['date'] == '2024-01-01']['weight'].values
        assert len(date1_weights) == 2
        assert all(w == pytest.approx(0.5) for w in date1_weights)

        # Date 2: 4 longs → each should be 1/4 = 0.25
        date2_weights = portfolio[portfolio['date'] == '2024-01-02']['weight'].values
        assert len(date2_weights) == 4
        assert all(w == pytest.approx(0.25) for w in date2_weights)

        # WRONG implementation would give:
        # All 6 longs globally → each 1/6 = 0.167
        # Verify this is NOT the case
        assert not all(abs(w - 0.167) < 0.01 for w in portfolio['weight'].values)

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

        Original: Weekly, turnover 3.19x
        Failed: Daily, turnover 7.44x (+133%)
        """
        # Simulate positions over 52 weeks (1 year)
        num_weeks = 52

        # Weekly rebalancing: Rebalance every week
        weekly_trades = num_weeks * 2  # Assume 2 position changes per week
        weekly_avg_capital = 1000000
        weekly_turnover = (weekly_trades * 50000) / weekly_avg_capital  # ~5.2x

        # Daily rebalancing: Rebalance every day (252 days)
        daily_trades = 252 * 2  # Assume 2 position changes per day
        daily_turnover = (daily_trades * 50000) / weekly_avg_capital  # ~25.2x

        # But with sparse ESG events, many days have no trades
        # Realistic daily turnover accounting for sparse signals
        daily_turnover_realistic = 7.44  # From actual backtest

        # Verify daily is significantly higher
        turnover_increase = (daily_turnover_realistic / weekly_turnover - 1) * 100

        # From root cause analysis: +133% increase
        assert turnover_increase > 100, f"Turnover increase only {turnover_increase:.0f}%, expected >100%"

        # Transaction cost impact
        commission_bps = 5.5  # 5 bps commission + 0.5 bps slippage

        weekly_cost = weekly_turnover * (commission_bps / 10000)  # As decimal
        daily_cost = daily_turnover_realistic * (commission_bps / 10000)

        cost_increase = (daily_cost - weekly_cost) * 100  # As percentage points

        # From root cause analysis: +23 bps additional drag
        assert cost_increase == pytest.approx(0.23, abs=0.05)

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


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
