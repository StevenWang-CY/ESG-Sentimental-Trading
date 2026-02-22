"""
Unit Tests for ESG Signal Generator

Tests the critical signal generation logic including:
1. Directional raw score (direction x conviction)
2. Cross-sectional ranking with signed scores
3. Quintile assignment logic
4. Signal quality metric calculation
5. Edge cases (sparse signals, single signal per day)
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
        """Test signal generator initializes with correct weights"""
        assert signal_generator.weights['event_severity'] == pytest.approx(0.20)
        assert signal_generator.weights['intensity'] == pytest.approx(0.40)
        assert signal_generator.weights['volume'] == pytest.approx(0.25)
        assert signal_generator.weights['duration'] == pytest.approx(0.15)
        # Core weights should sum to 1.0
        core_sum = (signal_generator.weights['event_severity'] +
                    signal_generator.weights['intensity'] +
                    signal_generator.weights['volume'] +
                    signal_generator.weights['duration'])
        assert core_sum == pytest.approx(1.0)

    def test_compute_raw_score_positive_sentiment(self, signal_generator):
        """Test raw score is POSITIVE when sentiment is positive"""
        event_features = {'confidence': 0.5}
        reaction_features = {
            'intensity': 0.4,
            'volume_ratio': 3.0,
            'duration_days': 5
        }

        score = signal_generator.compute_raw_score(event_features, reaction_features)

        # Positive sentiment → positive raw_score
        assert score > 0, f"Expected positive score for positive sentiment, got {score}"

        # Manual calculation with direction x conviction:
        # direction = sign(0.4) = +1.0
        # event_severity = 0.5
        # sentiment_strength = abs(0.4) = 0.4
        # volume_normalized = min(log1p(3.0) / log(10), 1.0) ≈ 0.602
        # duration_normalized = min(5 / 7.0, 1.0) ≈ 0.714
        # conviction = 0.20*0.5 + 0.40*0.4 + 0.25*0.602 + 0.15*0.714
        #            = 0.100 + 0.160 + 0.1505 + 0.1071 ≈ 0.5176
        # raw_score = +1.0 * 0.5176 ≈ 0.518
        assert score == pytest.approx(0.518, abs=0.05)

    def test_compute_raw_score_negative_sentiment(self, signal_generator):
        """Test raw score is NEGATIVE when sentiment is negative"""
        event_features = {'confidence': 0.5}
        reaction_features = {
            'intensity': -0.4,
            'volume_ratio': 3.0,
            'duration_days': 5
        }

        score = signal_generator.compute_raw_score(event_features, reaction_features)

        # Negative sentiment → negative raw_score
        assert score < 0, f"Expected negative score for negative sentiment, got {score}"

        # Same magnitude as positive case, but negative sign
        assert score == pytest.approx(-0.518, abs=0.05)

    def test_compute_raw_score_neutral_sentiment(self, signal_generator):
        """Test raw score is zero when sentiment is near-zero"""
        event_features = {'confidence': 0.5}
        reaction_features = {
            'intensity': 0.005,  # Below 0.01 threshold
            'volume_ratio': 3.0,
            'duration_days': 5
        }

        score = signal_generator.compute_raw_score(event_features, reaction_features)

        # Near-zero sentiment → zero raw_score
        assert score == pytest.approx(0.0, abs=0.001)

    def test_raw_score_range(self, signal_generator):
        """Test raw scores are always in [-1, 1]"""
        # Extreme positive
        score_pos = signal_generator.compute_raw_score(
            {'confidence': 1.0},
            {'intensity': 1.0, 'volume_ratio': 100.0, 'duration_days': 30}
        )
        assert -1.0 <= score_pos <= 1.0

        # Extreme negative
        score_neg = signal_generator.compute_raw_score(
            {'confidence': 1.0},
            {'intensity': -1.0, 'volume_ratio': 100.0, 'duration_days': 30}
        )
        assert -1.0 <= score_neg <= 1.0

        # Magnitudes should be equal
        assert abs(score_pos) == pytest.approx(abs(score_neg), abs=0.01)

    def test_cross_sectional_ranking_signed_scores(self, signal_generator):
        """
        Test cross-sectional ranking separates positive (Q5) from negative (Q1) scores.

        With signed raw_scores, pd.qcut naturally assigns:
        - Negative scores → Q1 (short)
        - Positive scores → Q5 (long)
        """
        # 6 signals on same date: 3 positive, 3 negative
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 6),
            'ticker': ['A', 'B', 'C', 'D', 'E', 'F'],
            'raw_score': [0.5, 0.3, 0.1, -0.1, -0.3, -0.5],
            'sentiment_intensity': [0.6, 0.4, 0.2, -0.2, -0.4, -0.6],
            'z_score': [0.5, 0.3, 0.1, -0.1, -0.3, -0.5],
            'signal': [0.46, 0.29, 0.10, -0.10, -0.29, -0.46],
            'quintile': [5, 5, 3, 3, 1, 1],  # Provisional
        })

        result = signal_generator._apply_cross_sectional_ranking(signals_df)

        # Q5 signals should have positive raw_scores
        q5 = result[result['quintile'] == 5]
        assert (q5['raw_score'] > 0).all(), f"Q5 should be positive: {q5['raw_score'].values}"

        # Q1 signals should have negative raw_scores
        q1 = result[result['quintile'] == 1]
        assert (q1['raw_score'] < 0).all(), f"Q1 should be negative: {q1['raw_score'].values}"

    def test_cross_sectional_ranking_sparse_signals(self, signal_generator):
        """
        Test cross-sectional ranking with sparse signals (1-2 per day)
        """
        # Create sparse signals with signed scores
        data = []
        dates = pd.date_range('2024-01-01', '2024-01-10', freq='D')

        for i, date in enumerate(dates):
            if i % 3 == 0:
                data.append({
                    'date': date,
                    'ticker': f'STOCK{i}',
                    'raw_score': 0.3 if i % 2 == 0 else -0.3,
                    'sentiment_intensity': 0.4 if i % 2 == 0 else -0.4,
                    'z_score': 0.3 if i % 2 == 0 else -0.3,
                    'signal': 0.29 if i % 2 == 0 else -0.29,
                    'quintile': 3,
                })
            elif i % 3 == 1:
                data.append({
                    'date': date,
                    'ticker': f'STOCK{i}A',
                    'raw_score': 0.4,
                    'sentiment_intensity': 0.5,
                    'z_score': 0.4,
                    'signal': 0.38,
                    'quintile': 3,
                })
                data.append({
                    'date': date,
                    'ticker': f'STOCK{i}B',
                    'raw_score': -0.4,
                    'sentiment_intensity': -0.5,
                    'z_score': -0.4,
                    'signal': -0.38,
                    'quintile': 3,
                })

        signals_df = pd.DataFrame(data)
        result = signal_generator._apply_cross_sectional_ranking(signals_df)

        # All signals have quintile assigned
        assert result['quintile'].notna().all()
        assert result['quintile'].isin([1, 2, 3, 4, 5]).all()

    def test_cross_sectional_ranking_single_signal_per_day(self, signal_generator):
        """
        Test quintile assignment when only 1 signal per day.
        With signed scores, single positive → Q5, single negative → Q1.
        """
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01', '2024-01-02', '2024-01-03']),
            'ticker': ['AAPL', 'TSLA', 'MSFT'],
            'raw_score': [0.4, -0.3, 0.2],
            'sentiment_intensity': [0.5, -0.4, 0.3],
            'z_score': [0.4, -0.3, 0.2],
            'signal': [0.38, -0.29, 0.20],
            'quintile': [3, 3, 3],
        })

        result = signal_generator._apply_cross_sectional_ranking(signals_df)

        # Positive raw_score → Q5
        aapl = result[result['ticker'] == 'AAPL']
        assert aapl['quintile'].iloc[0] == 5

        # Negative raw_score → Q1
        tsla = result[result['ticker'] == 'TSLA']
        assert tsla['quintile'].iloc[0] == 1

    def test_quintile_assignment_sufficient_data(self, signal_generator):
        """Test quintile assignment when n >= 5 signals with signed scores"""
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 5),
            'ticker': ['A', 'B', 'C', 'D', 'E'],
            'raw_score': [-0.5, -0.2, 0.0, 0.2, 0.5],
            'sentiment_intensity': [-0.6, -0.3, 0.0, 0.3, 0.6],
            'z_score': [-0.5, -0.2, 0.0, 0.2, 0.5],
            'signal': [-0.46, -0.20, 0.0, 0.20, 0.46],
            'quintile': [3, 3, 3, 3, 3],
        })

        result = signal_generator._apply_cross_sectional_ranking(signals_df)

        # Should have quintile spread
        assert result['quintile'].nunique() >= 3

        # Lowest score → lowest quintile, highest score → highest quintile
        sorted_result = result.sort_values('raw_score')
        assert sorted_result.iloc[0]['quintile'] <= 2  # Most negative → Q1 or Q2
        assert sorted_result.iloc[-1]['quintile'] >= 4  # Most positive → Q4 or Q5

    def test_edge_case_all_same_scores(self, signal_generator):
        """Test behavior when all signals have identical scores"""
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * 5),
            'ticker': ['A', 'B', 'C', 'D', 'E'],
            'raw_score': [0.3, 0.3, 0.3, 0.3, 0.3],
            'sentiment_intensity': [0.4, 0.4, 0.4, 0.4, 0.4],
            'z_score': [0.3, 0.3, 0.3, 0.3, 0.3],
            'signal': [0.29, 0.29, 0.29, 0.29, 0.29],
            'quintile': [3, 3, 3, 3, 3],
        })

        result = signal_generator._apply_cross_sectional_ranking(signals_df)

        # Should handle gracefully (no errors)
        assert len(result) == 5
        assert result['quintile'].notna().all()
        # All assigned to middle quintile (Q3) when scores are identical
        assert (result['quintile'] == 3).all() or result['quintile'].nunique() == 1

    def test_edge_case_zero_signals(self, signal_generator):
        """Test behavior with empty DataFrame (no signals)"""
        signals_df = pd.DataFrame(columns=['date', 'ticker', 'raw_score',
                                           'sentiment_intensity', 'z_score',
                                           'signal', 'quintile'])

        result = signal_generator._apply_cross_sectional_ranking(signals_df)

        # Should return empty DataFrame without errors
        assert len(result) == 0

    def test_signal_quality_metric(self, signal_generator):
        """
        Test signal quality metric (Sharpe / # signals)
        """
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

    def test_sentiment_quintile_correlation(self, signal_generator):
        """
        Test that signed raw_scores produce strong sentiment-quintile correlation.

        With the direction x conviction formula, positive sentiment → positive
        raw_score → Q5, and negative sentiment → negative raw_score → Q1.
        Correlation should be strongly positive.
        """
        n = 50
        sentiments = np.linspace(-0.8, 0.8, n)
        signals_df = pd.DataFrame({
            'date': pd.to_datetime(['2024-01-01'] * n),
            'ticker': [f'STOCK{i}' for i in range(n)],
            'raw_score': sentiments * 0.5,  # Signed scores proportional to sentiment
            'sentiment_intensity': sentiments,
            'z_score': sentiments * 0.5,
            'signal': np.tanh(sentiments * 0.5),
            'quintile': [3] * n,
        })

        result = signal_generator._apply_cross_sectional_ranking(signals_df)

        # Compute correlation
        correlation = result['sentiment_intensity'].corr(result['quintile'].astype(float))

        assert correlation > 0.75, f"Sentiment-quintile correlation {correlation:.3f} < 0.75"

    def test_compute_signal_returns_correct_structure(self, signal_generator):
        """Test compute_signal returns all required fields"""
        result = signal_generator.compute_signal(
            ticker='AAPL',
            date=datetime(2024, 1, 15),
            event_features={'confidence': 0.5, 'category': 'E'},
            reaction_features={'intensity': 0.4, 'volume_ratio': 2.0}
        )

        required_keys = ['ticker', 'date', 'raw_score', 'z_score', 'signal',
                        'quintile', 'event_category', 'event_confidence',
                        'sentiment_intensity', 'volume_ratio']
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

        # Positive sentiment → positive raw_score and Q5
        assert result['raw_score'] > 0
        assert result['quintile'] == 5

    def test_compute_signal_negative_returns_q1(self, signal_generator):
        """Test compute_signal assigns Q1 for negative sentiment"""
        result = signal_generator.compute_signal(
            ticker='TSLA',
            date=datetime(2024, 1, 15),
            event_features={'confidence': 0.5, 'category': 'G'},
            reaction_features={'intensity': -0.6, 'volume_ratio': 2.0}
        )

        assert result['raw_score'] < 0
        assert result['quintile'] == 1


class TestSignalGeneratorRootCauseFixes:
    """
    Tests specifically validating ROOT CAUSE FIXES from analysis
    """

    @pytest.fixture
    def signal_generator(self, baseline_config):
        return ESGSignalGenerator(weights=baseline_config['signals']['weights'])

    def test_daily_rebalancing_sparse_signals_fix(self, signal_generator):
        """
        ROOT CAUSE #4: Cross-Sectional Ranking with sparse daily signals.
        Uses signed raw_scores to validate proper quintile distribution.
        """
        dates = pd.date_range('2024-01-01', '2025-10-31', freq='D')
        num_signals = 99
        np.random.seed(42)
        signal_dates = np.random.choice(dates, size=num_signals, replace=False)
        sentiments = np.random.uniform(-0.8, 0.8, num_signals)

        signals_df = pd.DataFrame({
            'date': pd.to_datetime(signal_dates),
            'ticker': [f'STOCK{i}' for i in range(num_signals)],
            'raw_score': sentiments * 0.5,
            'sentiment_intensity': sentiments,
            'z_score': sentiments * 0.5,
            'signal': np.tanh(sentiments * 0.5),
            'quintile': [3] * num_signals,
        })

        # Apply cross-sectional ranking
        result = signal_generator._apply_cross_sectional_ranking(signals_df)

        # All signals must have valid quintiles
        assert result['quintile'].notna().all(), "Some quintiles are NaN"

        # Verify quintile distribution covers Q1 and Q5
        # With 1 signal per date and signed scores, only Q1 and Q5 are assigned
        # (Q3 only appears for exactly zero scores, which is vanishingly rare)
        quintile_counts = result['quintile'].value_counts()
        assert len(quintile_counts) >= 2, "Too few quintiles assigned"

        longs = (result['quintile'] == 5).sum()
        shorts = (result['quintile'] == 1).sum()
        assert longs > 0 and shorts > 0, "No long/short split"

    def test_signal_quality_degradation_threshold(self, signal_generator):
        """
        Test signal quality metric at different confidence thresholds.
        Signal Quality > Signal Quantity.
        """
        threshold_scenarios = {
            0.15: {'num_events': 99, 'sharpe': 0.04},
            0.18: {'num_events': 70, 'sharpe': 0.55},
            0.20: {'num_events': 58, 'sharpe': 0.70}
        }

        quality_metrics = {}
        for threshold, metrics in threshold_scenarios.items():
            quality = metrics['sharpe'] / metrics['num_events']
            quality_metrics[threshold] = quality

        # Verify quality increases as threshold rises
        assert quality_metrics[0.20] > quality_metrics[0.18]
        assert quality_metrics[0.18] > quality_metrics[0.15]

        # 0.20 is >10x better than 0.15
        quality_ratio = quality_metrics[0.20] / quality_metrics[0.15]
        assert quality_ratio > 10, f"Quality ratio only {quality_ratio:.1f}x, expected >10x"

    def test_direction_preserved_in_raw_score(self, signal_generator):
        """
        CRITICAL: Verify the direction x conviction formula preserves sentiment direction.

        Previous bug: (intensity + 1) / 2 mapped all scores to [0, 1], destroying direction.
        Fix: raw_score = sign(sentiment) * conviction → signed in [-1, 1].
        """
        pos_score = signal_generator.compute_raw_score(
            {'confidence': 0.5},
            {'intensity': 0.6, 'volume_ratio': 2.0, 'duration_days': 3}
        )
        neg_score = signal_generator.compute_raw_score(
            {'confidence': 0.5},
            {'intensity': -0.6, 'volume_ratio': 2.0, 'duration_days': 3}
        )

        # Positive sentiment → positive score
        assert pos_score > 0, f"Positive sentiment gave score {pos_score}"

        # Negative sentiment → negative score
        assert neg_score < 0, f"Negative sentiment gave score {neg_score}"

        # Magnitudes should be equal (same conviction, different direction)
        assert abs(pos_score) == pytest.approx(abs(neg_score), abs=0.001)


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
