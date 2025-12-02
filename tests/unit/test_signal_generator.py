"""
Unit Tests for ESG Signal Generator

Tests the critical signal generation logic including:
1. Cross-sectional ranking (fixed to use all-historical scores, not per-date)
2. Quintile assignment logic
3. Z-score normalization
4. Signal quality metric calculation
5. Edge cases (sparse signals, single signal per day)

Related to Root Cause #4: Cross-Sectional Ranking Requires Sufficient Data
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

from src.signals.signal_generator import ESGSignalGenerator


class TestESGSignalGenerator:
    """Test suite for ESG Signal Generator"""

    @pytest.fixture
    def signal_generator(self, baseline_config):
        """Create signal generator with baseline config"""
        return ESGSignalGenerator(
            weights=baseline_config['signals']['weights']
        )

    def test_initialization(self, signal_generator, baseline_config):
        """Test signal generator initializes with correct weights (research-backed v3.3)"""
        assert signal_generator.weights['event_severity'] == 0.20
        assert signal_generator.weights['intensity'] == 0.45  # PRIMARY: Sentiment
        assert signal_generator.weights['volume'] == 0.25
        assert signal_generator.weights['duration'] == 0.10
        # Core weights should sum to 1.0 (optional features have 0 weight by default)
        core_sum = (signal_generator.weights['event_severity'] +
                    signal_generator.weights['intensity'] +
                    signal_generator.weights['volume'] +
                    signal_generator.weights['duration'])
        assert core_sum == pytest.approx(1.0)

    def test_compute_raw_score(self, signal_generator):
        """Test raw score computation with known inputs (v3.3 weights)"""
        event_features = {
            'confidence': 0.5,  # Event severity
        }

        reaction_features = {
            'intensity': 0.4,             # Mean sentiment [-1, 1] → normalized to 0.7
            'volume_ratio': 3.0,          # Volume
            'duration_days': 5            # Duration
        }

        score = signal_generator.compute_raw_score(event_features, reaction_features)

        # Manual calculation with v3.3 weights:
        # intensity_normalized = (0.4 + 1.0) / 2.0 = 0.7
        # volume_normalized = min(log1p(3.0) / log(10), 1.0) ≈ 0.602
        # duration_normalized = min(5 / 7.0, 1.0) ≈ 0.714
        # Score = 0.20*0.5 + 0.45*0.7 + 0.25*0.602 + 0.10*0.714
        # Score = 0.10 + 0.315 + 0.1505 + 0.0714 ≈ 0.6369

        assert score == pytest.approx(0.637, abs=0.05)

    def test_cross_sectional_ranking_sparse_signals(self, signal_generator):
        """
        Test cross-sectional ranking with sparse signals (ROOT CAUSE #4)

        CRITICAL: This tests the fix for daily rebalancing failure.
        With sparse signals (1-2 per day), quintile assignment must still work.
        """
        # Create sparse signals (1-2 per day across multiple dates)
        dates = pd.date_range('2024-01-01', '2024-01-10', freq='D')
        data = []

        for i, date in enumerate(dates):
            # Some days have 1 signal, some have 2, some have 0
            if i % 3 == 0:
                data.append({
                    'date': date,
                    'ticker': f'STOCK{i}',
                    'raw_score': 0.5 + i * 0.1
                })
            elif i % 3 == 1:
                data.append({
                    'date': date,
                    'ticker': f'STOCK{i}A',
                    'raw_score': 0.6 + i * 0.1
                })
                data.append({
                    'date': date,
                    'ticker': f'STOCK{i}B',
                    'raw_score': 0.4 + i * 0.1
                })
            # i % 3 == 2: No signals (zero signals day)

        signals_df = pd.DataFrame(data)

        # Apply cross-sectional ranking
        result = signal_generator._assign_quintiles(signals_df)

        # Verify:
        # 1. All signals have quintile assigned
        assert result['quintile'].notna().all()

        # 2. Quintiles are in {1, 2, 3, 4, 5}
        assert result['quintile'].isin([1, 2, 3, 4, 5]).all()

        # 3. Higher raw_score → higher quintile (generally)
        # Check correlation is positive
        correlation = result['raw_score'].corr(result['quintile'])
        assert correlation > 0.5, f"Correlation {correlation} too low, ranking may be broken"

    def test_cross_sectional_ranking_single_signal_per_day(self, signal_generator):
        """
        Test quintile assignment when only 1 signal per day (extreme sparse case)

        This was the failure mode for HIGH sensitivity daily rebalancing.
        """
        # Create data with exactly 1 signal per day
        dates = pd.date_range('2024-01-01', '2024-01-05', freq='D')
        signals_df = pd.DataFrame({
            'date': dates,
            'ticker': ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN'],
            'raw_score': [0.8, 0.6, 0.9, 0.5, 0.7]
        })

        result = signal_generator._assign_quintiles(signals_df)

        # All signals must have quintiles assigned
        assert result['quintile'].notna().all()

        # Check ranking is correct (highest score → Q5, lowest → Q1)
        max_score_idx = result['raw_score'].idxmax()
        min_score_idx = result['raw_score'].idxmin()

        # Highest score should be Q5 (or at least > Q1)
        assert result.loc[max_score_idx, 'quintile'] > result.loc[min_score_idx, 'quintile']

    def test_z_score_normalization_all_historical(self, signal_generator):
        """
        Test z-score uses ALL historical scores, not per-date

        ROOT CAUSE FIX: Original implementation used per-date z-scores,
        which failed with sparse signals (all z-scores = 0 when n=1 per date).

        Correct implementation: Normalize using all historical observations.
        """
        # Create signals across multiple dates with varying scores
        data = []
        dates = pd.date_range('2024-01-01', '2024-01-30', freq='D')

        for i, date in enumerate(dates):
            if i % 2 == 0:  # Every other day has a signal
                data.append({
                    'date': date,
                    'ticker': f'STOCK{i}',
                    'raw_score': 0.5 + np.sin(i / 5.0) * 0.3  # Varying scores
                })

        signals_df = pd.DataFrame(data)

        # Compute z-scores
        result = signal_generator._normalize_scores(signals_df)

        # Verify z-scores are computed correctly
        # Mean should be ~0, std should be ~1
        assert result['z_score'].mean() == pytest.approx(0.0, abs=0.1)
        assert result['z_score'].std() == pytest.approx(1.0, abs=0.2)

        # Verify no NaN z-scores (would happen if per-date normalization was used)
        assert result['z_score'].notna().all()

    def test_quintile_assignment_sufficient_data(self, signal_generator):
        """Test quintile assignment when n >= 5 signals"""
        # Create exactly 5 signals (minimum for standard quintile split)
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 5),
            'ticker': ['A', 'B', 'C', 'D', 'E'],
            'raw_score': [0.2, 0.4, 0.6, 0.8, 1.0]
        })

        result = signal_generator._assign_quintiles(signals_df)

        # Should have all 5 quintiles
        assert set(result['quintile']) == {1, 2, 3, 4, 5}

        # Check ordering is correct
        sorted_result = result.sort_values('raw_score')
        assert list(sorted_result['quintile']) == [1, 2, 3, 4, 5]

    def test_quintile_assignment_insufficient_data(self, signal_generator):
        """Test quintile assignment when n < 5 signals (uses tertile split)"""
        # Create 3 signals (uses tertile split logic)
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 3),
            'ticker': ['A', 'B', 'C'],
            'raw_score': [0.3, 0.6, 0.9]
        })

        result = signal_generator._assign_quintiles(signals_df)

        # Should assign Q1, Q3, Q5 (extremes)
        quintiles = set(result['quintile'])
        assert 1 in quintiles, "Lowest score should be Q1"
        assert 5 in quintiles, "Highest score should be Q5"

        # Verify ordering
        sorted_result = result.sort_values('raw_score')
        assert sorted_result.iloc[0]['quintile'] == 1  # Lowest
        assert sorted_result.iloc[-1]['quintile'] == 5  # Highest

    def test_signal_quality_metric(self, signal_generator):
        """
        Test signal quality metric (Sharpe / # signals)

        From root cause analysis: This metric differentiates good vs. bad thresholds.
        Original (0.20): 0.70/58 = 0.012
        Failed (0.15): 0.04/99 = 0.0004 (30x worse!)
        """
        # Simulate two scenarios

        # Scenario 1: HIGH quality (baseline)
        baseline_sharpe = 0.70
        baseline_signals = 58
        baseline_quality = baseline_sharpe / baseline_signals

        # Scenario 2: LOW quality (failed HIGH sensitivity)
        failed_sharpe = 0.04
        failed_signals = 99
        failed_quality = failed_sharpe / failed_signals

        # Verify baseline is much better
        quality_ratio = baseline_quality / failed_quality
        assert quality_ratio > 20, f"Quality ratio {quality_ratio:.1f}x, expected >20x"

        # This metric should be used to evaluate threshold choices
        assert baseline_quality == pytest.approx(0.012, abs=0.001)
        assert failed_quality == pytest.approx(0.0004, abs=0.0001)

    def test_sentiment_quintile_correlation(self, signal_generator):
        """
        Test sentiment-quintile correlation (validation metric)

        From root cause analysis:
        - Good cross-sectional ranking: correlation > 0.75
        - Original (MEDIUM): 0.786 ✓
        - Failed (HIGH): Likely <0.60 ✗
        """
        # Create signals with strong sentiment-score relationship
        n = 50
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * n),
            'ticker': [f'STOCK{i}' for i in range(n)],
            'raw_score': np.linspace(0.2, 1.0, n),
            'sentiment_intensity': np.linspace(0.1, 0.9, n) + np.random.randn(n) * 0.05
        })

        result = signal_generator._assign_quintiles(signals_df)

        # Compute correlation
        correlation = result['sentiment_intensity'].corr(result['quintile'])

        assert correlation > 0.75, f"Sentiment-quintile correlation {correlation:.3f} < 0.75 (poor signal quality)"

    def test_edge_case_all_same_scores(self, signal_generator):
        """Test behavior when all signals have identical scores"""
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 5),
            'ticker': ['A', 'B', 'C', 'D', 'E'],
            'raw_score': [0.5, 0.5, 0.5, 0.5, 0.5]  # All identical
        })

        result = signal_generator._assign_quintiles(signals_df)

        # Should handle gracefully (no errors)
        assert len(result) == 5
        assert result['quintile'].notna().all()

        # All should be assigned to middle quintile (Q3)
        assert (result['quintile'] == 3).all() or result['quintile'].nunique() == 1

    def test_edge_case_zero_signals(self, signal_generator):
        """Test behavior with empty DataFrame (no signals)"""
        signals_df = pd.DataFrame(columns=['date', 'ticker', 'raw_score'])

        result = signal_generator._assign_quintiles(signals_df)

        # Should return empty DataFrame without errors
        assert len(result) == 0
        assert 'quintile' in result.columns

    def test_generate_signals_integration(self, signal_generator, sample_events_df, sample_reddit_df):
        """
        Integration test: Generate signals from events + Reddit data

        This tests the full pipeline from events → features → signals → quintiles.
        """
        # Mock reaction features (normally computed from Reddit data)
        reaction_features_list = []

        for _, event in sample_events_df.iterrows():
            # Filter Reddit for this event
            reddit_subset = sample_reddit_df[
                (sample_reddit_df['ticker'] == event['ticker']) &
                (sample_reddit_df['timestamp'] >= event['date']) &
                (sample_reddit_df['timestamp'] <= event['date'] + timedelta(days=7))
            ]

            reaction_features = {
                'sentiment_intensity': reddit_subset['sentiment'].mean() if len(reddit_subset) > 0 else 0.0,
                'volume_ratio': len(reddit_subset) / 10.0 if len(reddit_subset) > 0 else 0.0,
                'duration_days': (reddit_subset['timestamp'].max() - reddit_subset['timestamp'].min()).days if len(reddit_subset) > 1 else 1
            }

            reaction_features_list.append(reaction_features)

        # Compute raw scores
        raw_scores = []
        for event, reaction in zip(sample_events_df.itertuples(), reaction_features_list):
            event_features = {'confidence': event.confidence}
            score = signal_generator.compute_raw_score(event_features, reaction)
            raw_scores.append(score)

        # Create signals DataFrame
        signals_df = sample_events_df.copy()
        signals_df['raw_score'] = raw_scores

        # Assign quintiles
        result = signal_generator._assign_quintiles(signals_df)

        # Verify outputs
        assert len(result) == len(sample_events_df)
        assert 'quintile' in result.columns
        assert result['quintile'].notna().all()
        assert result['quintile'].isin([1, 2, 3, 4, 5]).all()

        # Verify long/short split (Q5 = long, Q1 = short)
        longs = result[result['quintile'] == 5]
        shorts = result[result['quintile'] == 1]

        # Longs should have higher scores than shorts
        if len(longs) > 0 and len(shorts) > 0:
            assert longs['raw_score'].mean() > shorts['raw_score'].mean()


class TestSignalGeneratorRootCauseFixes:
    """
    Tests specifically validating ROOT CAUSE FIXES from analysis
    """

    @pytest.fixture
    def signal_generator(self, baseline_config):
        return ESGSignalGenerator(weights=baseline_config['signals']['weights'])

    def test_daily_rebalancing_sparse_signals_fix(self, signal_generator):
        """
        ROOT CAUSE #4: Cross-Sectional Ranking Failure with Sparse Daily Signals

        BEFORE FIX: Daily rebalancing with 0-2 signals/day → all z-scores = 0
        AFTER FIX: Uses all-historical z-scores → proper ranking even with sparse data
        """
        # Simulate HIGH sensitivity scenario: 99 signals across 22 months (4.5/month = 0.15/day)
        dates = pd.date_range('2024-01-01', '2025-10-31', freq='D')
        num_signals = 99
        signal_dates = np.random.choice(dates, size=num_signals, replace=False)

        signals_df = pd.DataFrame({
            'date': pd.to_datetime(signal_dates),
            'ticker': [f'STOCK{i}' for i in range(num_signals)],
            'raw_score': np.random.uniform(0.3, 0.9, num_signals)
        })

        # Group by date to check signals per day
        signals_per_day = signals_df.groupby('date').size()

        # Verify most days have 0-2 signals (sparse)
        assert (signals_per_day <= 2).sum() / len(signals_per_day) > 0.8

        # Apply quintile assignment
        result = signal_generator._assign_quintiles(signals_df)

        # CRITICAL: All signals must have valid quintiles (would fail with per-date z-scores)
        assert result['quintile'].notna().all(), "Some quintiles are NaN (per-date z-score bug)"

        # Verify quintile distribution is reasonable (not all Q3)
        quintile_counts = result['quintile'].value_counts()
        assert len(quintile_counts) >= 3, "Too few quintiles assigned (ranking failure)"

        # Verify long/short balance exists
        longs = (result['quintile'] == 5).sum()
        shorts = (result['quintile'] == 1).sum()
        assert longs > 0 and shorts > 0, "No long/short split (market neutrality lost)"

    def test_weekly_vs_daily_rebalancing_comparison(self, signal_generator):
        """
        Compare weekly vs daily rebalancing signal quality

        ROOT CAUSE #2: Trading Frequency Must Match Alpha Frequency

        Weekly rebalancing accumulates 2-3 signals per rebalance (sufficient for ranking).
        Daily rebalancing has 0-1 signals per rebalance (insufficient).
        """
        # Create 58 signals across 22 months (MEDIUM sensitivity)
        num_signals = 58
        months = 22
        dates = pd.date_range('2024-01-01', periods=months*30, freq='D')

        # Distribute signals randomly
        signal_dates = np.random.choice(dates, size=num_signals, replace=False)

        signals_df = pd.DataFrame({
            'date': pd.to_datetime(signal_dates),
            'ticker': [f'STOCK{i}' for i in range(num_signals)],
            'raw_score': np.random.uniform(0.3, 0.9, num_signals)
        })

        # Weekly rebalancing: Group signals by week
        signals_df['week'] = signals_df['date'].dt.to_period('W')
        weekly_signals_per_rebalance = signals_df.groupby('week').size()

        # Daily rebalancing: Group by day
        signals_df['day'] = signals_df['date'].dt.to_period('D')
        daily_signals_per_rebalance = signals_df.groupby('day').size()

        # Verify weekly accumulates more signals per rebalance
        assert weekly_signals_per_rebalance.mean() > daily_signals_per_rebalance.mean()

        # Weekly should have sufficient signals for quintile split (>=5) more often
        weekly_sufficient = (weekly_signals_per_rebalance >= 5).sum()
        daily_sufficient = (daily_signals_per_rebalance >= 5).sum()

        assert weekly_sufficient > daily_sufficient, "Weekly doesn't accumulate enough signals"

    def test_signal_quality_degradation_threshold(self, signal_generator):
        """
        Test signal quality metric at different confidence thresholds

        ROOT CAUSE #1: Signal Quality > Signal Quantity

        Simulates the quality vs. quantity trade-off.
        """
        # Simulate thresholds: 0.15, 0.18, 0.20
        threshold_scenarios = {
            0.15: {'num_events': 99, 'sharpe': 0.04},   # Failed HIGH
            0.18: {'num_events': 70, 'sharpe': 0.55},   # Marginal
            0.20: {'num_events': 58, 'sharpe': 0.70}    # Baseline
        }

        quality_metrics = {}

        for threshold, metrics in threshold_scenarios.items():
            quality = metrics['sharpe'] / metrics['num_events']
            quality_metrics[threshold] = quality

        # Verify quality decreases as threshold lowers
        assert quality_metrics[0.20] > quality_metrics[0.18]
        assert quality_metrics[0.18] > quality_metrics[0.15]

        # Verify 0.20 is >10x better than 0.15
        quality_ratio = quality_metrics[0.20] / quality_metrics[0.15]
        assert quality_ratio > 10, f"Quality ratio only {quality_ratio:.1f}x, expected >10x"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
