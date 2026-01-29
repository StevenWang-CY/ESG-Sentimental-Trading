"""
Tests for FetchCoordinator, TokenBucketRateLimiter, CircuitBreaker,
enforce_schema, and signal schema validation.
"""

import time
import threading
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from src.data.fetch_coordinator import (
    FetchCoordinator,
    CoordinatedResult,
    SourceResult,
    SourceStatus,
    TokenBucketRateLimiter,
    CircuitBreaker,
    CircuitState,
    enforce_schema,
    STANDARD_COLUMNS,
)
from src.signals.signal_generator import (
    validate_signal_schema,
    enforce_signal_schema,
    SignalSchemaError,
    SIGNAL_SCHEMA,
    SIGNAL_REQUIRED_COLUMNS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_mock_fetcher(
    data: pd.DataFrame = None,
    delay: float = 0.0,
    error: Exception = None,
    error_on_attempt: int = -1,
):
    """Create a mock fetcher with configurable behavior."""
    call_count = {"n": 0}

    class MockFetcher:
        def fetch_tweets_for_event(self, ticker, event_date, keywords=None,
                                    days_before=3, days_after=7,
                                    max_results=100):
            call_count["n"] += 1
            if delay > 0:
                time.sleep(delay)
            if error and (error_on_attempt < 0 or call_count["n"] == error_on_attempt):
                raise error
            if data is not None:
                return data.copy()
            # Default: return a small valid DataFrame
            return pd.DataFrame({
                'timestamp': [event_date],
                'text': [f'Test post about {ticker}'],
                'user_followers': [10],
                'retweets': [5],
                'likes': [20],
                'ticker': [ticker],
                'sentiment': [0.5],
                'esg_relevance': [0.7],
                'esg_category': ['E'],
                'quality_score': [0.6],
            })

    mock = MockFetcher()
    mock._call_count = call_count
    return mock


def make_sample_social_df(n=5, ticker='AAPL'):
    """Create a sample social media DataFrame with standard columns."""
    base_date = datetime(2024, 6, 15)
    return pd.DataFrame({
        'timestamp': [base_date + timedelta(hours=i) for i in range(n)],
        'text': [f'Post {i} about {ticker}' for i in range(n)],
        'user_followers': np.random.randint(1, 1000, n),
        'retweets': np.random.randint(0, 50, n),
        'likes': np.random.randint(0, 100, n),
        'ticker': [ticker] * n,
        'sentiment': np.random.uniform(-1, 1, n),
        'esg_relevance': np.random.uniform(0, 1, n),
        'esg_category': np.random.choice(['E', 'S', 'G'], n),
        'quality_score': np.random.uniform(0, 1, n),
    })


def make_sample_signal_df(n=10):
    """Create a sample signal DataFrame matching the required schema."""
    base_date = datetime(2024, 6, 1)
    return pd.DataFrame({
        'ticker': ['AAPL'] * n,
        'date': [base_date + timedelta(days=i) for i in range(n)],
        'raw_score': np.random.uniform(0, 1, n),
        'z_score': np.random.uniform(-2, 2, n),
        'signal': np.tanh(np.random.uniform(-2, 2, n)),
        'quintile': np.random.choice([1, 2, 3, 4, 5], n),
        'event_category': np.random.choice(['E', 'S', 'G'], n),
        'event_confidence': np.random.uniform(0, 1, n),
        'sentiment_intensity': np.random.uniform(-1, 1, n),
        'volume_ratio': np.random.uniform(0, 5, n),
        'n_posts': np.random.randint(0, 100, n),
        'has_social_data': [True] * n,
        'confidence': np.random.uniform(0, 1, n),
    })


# ---------------------------------------------------------------------------
# TokenBucketRateLimiter Tests
# ---------------------------------------------------------------------------

class TestTokenBucketRateLimiter:
    def test_initial_burst_allows_immediate_calls(self):
        rl = TokenBucketRateLimiter(rate=1.0, burst=3)
        # Should be able to acquire burst count immediately
        assert rl.acquire(timeout=0.1) is True
        assert rl.acquire(timeout=0.1) is True
        assert rl.acquire(timeout=0.1) is True

    def test_exhausted_bucket_blocks(self):
        rl = TokenBucketRateLimiter(rate=10.0, burst=1)
        assert rl.acquire(timeout=0.1) is True
        # Second call should timeout quickly since burst is 1
        # but rate is 10/s so it refills in 0.1s
        assert rl.acquire(timeout=0.2) is True

    def test_timeout_returns_false(self):
        rl = TokenBucketRateLimiter(rate=0.1, burst=1)
        assert rl.acquire(timeout=0.1) is True
        # With rate=0.1 tokens/s, next token in 10s; timeout 0.1s should fail
        assert rl.acquire(timeout=0.1) is False

    def test_thread_safety(self):
        rl = TokenBucketRateLimiter(rate=100.0, burst=10)
        results = []

        def worker():
            for _ in range(5):
                results.append(rl.acquire(timeout=1.0))

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 20 calls should succeed with rate=100/s
        assert all(results)
        assert len(results) == 20


# ---------------------------------------------------------------------------
# CircuitBreaker Tests
# ---------------------------------------------------------------------------

class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        # Only 2 consecutive failures after reset, should still be closed
        assert cb.state == CircuitState.CLOSED

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.1)
        cb.record_failure()
        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# enforce_schema Tests
# ---------------------------------------------------------------------------

class TestEnforceSchema:
    def test_valid_df_passes_through(self):
        df = make_sample_social_df(5)
        result = enforce_schema(df)
        assert list(result.columns) == STANDARD_COLUMNS
        assert len(result) == 5

    def test_missing_columns_added(self):
        df = pd.DataFrame({'text': ['hello'], 'ticker': ['AAPL']})
        result = enforce_schema(df)
        assert list(result.columns) == STANDARD_COLUMNS
        assert result['sentiment'].iloc[0] == 0.0
        assert result['esg_relevance'].iloc[0] == 0.0

    def test_extra_columns_dropped(self):
        df = make_sample_social_df(3)
        df['extra_col'] = 'should_be_dropped'
        result = enforce_schema(df)
        assert 'extra_col' not in result.columns
        assert list(result.columns) == STANDARD_COLUMNS

    def test_empty_df_returns_correct_columns(self):
        result = enforce_schema(pd.DataFrame())
        assert list(result.columns) == STANDARD_COLUMNS
        assert len(result) == 0

    def test_type_coercion(self):
        df = pd.DataFrame({
            'timestamp': ['2024-06-15'],
            'text': [123],  # numeric, should become str
            'user_followers': ['100'],  # str, should become int
            'retweets': [None],
            'likes': [None],
            'ticker': ['AAPL'],
            'sentiment': ['0.5'],  # str, should become float
            'esg_relevance': [None],
            'esg_category': ['E'],
            'quality_score': ['0.8'],
        })
        result = enforce_schema(df)
        assert result['user_followers'].dtype in (np.int64, np.int32, int)
        assert result['sentiment'].dtype == np.float64
        assert isinstance(result['text'].iloc[0], str)


# ---------------------------------------------------------------------------
# FetchCoordinator Tests
# ---------------------------------------------------------------------------

class TestFetchCoordinator:
    def test_all_sources_succeed(self):
        fetchers = {
            'source_a': make_mock_fetcher(),
            'source_b': make_mock_fetcher(),
            'source_c': make_mock_fetcher(),
        }
        coord = FetchCoordinator(fetchers=fetchers, max_retries=1)
        result = coord.fetch_synchronized(
            ticker='AAPL',
            event_date=datetime(2024, 6, 15),
            min_sources=3,
        )
        assert result.quorum_met is True
        assert result.is_valid is True
        assert len(result.successful_sources) == 3
        assert len(result.failed_sources) == 0
        assert not result.combined_data.empty
        assert list(result.combined_data.columns) == STANDARD_COLUMNS

    def test_quorum_met_with_partial_failure(self):
        fetchers = {
            'source_a': make_mock_fetcher(),
            'source_b': make_mock_fetcher(error=ConnectionError("network down")),
            'source_c': make_mock_fetcher(),
        }
        coord = FetchCoordinator(fetchers=fetchers, max_retries=0)
        result = coord.fetch_synchronized(
            ticker='AAPL',
            event_date=datetime(2024, 6, 15),
            min_sources=2,
        )
        assert result.quorum_met is True
        assert len(result.successful_sources) == 2
        assert 'source_b' in result.failed_sources

    def test_quorum_not_met(self):
        fetchers = {
            'source_a': make_mock_fetcher(error=ConnectionError("fail")),
            'source_b': make_mock_fetcher(error=TimeoutError("timeout")),
            'source_c': make_mock_fetcher(),
        }
        coord = FetchCoordinator(fetchers=fetchers, max_retries=0)
        result = coord.fetch_synchronized(
            ticker='AAPL',
            event_date=datetime(2024, 6, 15),
            min_sources=3,
        )
        assert result.quorum_met is False
        assert len(result.successful_sources) == 1

    def test_concurrent_execution(self):
        """Verify sources are fetched concurrently, not sequentially."""
        delay = 0.3
        fetchers = {
            'source_a': make_mock_fetcher(delay=delay),
            'source_b': make_mock_fetcher(delay=delay),
            'source_c': make_mock_fetcher(delay=delay),
        }
        coord = FetchCoordinator(fetchers=fetchers, max_retries=0)
        start = time.monotonic()
        result = coord.fetch_synchronized(
            ticker='AAPL',
            event_date=datetime(2024, 6, 15),
            min_sources=3,
        )
        elapsed = time.monotonic() - start
        # If truly concurrent, total should be ~0.3s not ~0.9s
        assert elapsed < delay * 2.0
        assert result.quorum_met is True

    def test_retry_on_transient_failure(self):
        """Verify that a source that fails once gets retried."""
        call_count = {"n": 0}

        class FlakeyFetcher:
            def fetch_tweets_for_event(self, **kwargs):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise ConnectionError("transient failure")
                return pd.DataFrame({
                    'timestamp': [datetime(2024, 6, 15)],
                    'text': ['recovered'],
                    'user_followers': [1],
                    'retweets': [0],
                    'likes': [0],
                    'ticker': ['AAPL'],
                    'sentiment': [0.5],
                    'esg_relevance': [0.5],
                    'esg_category': ['E'],
                    'quality_score': [0.5],
                })

        fetchers = {'flakey': FlakeyFetcher()}
        coord = FetchCoordinator(
            fetchers=fetchers,
            max_retries=2,
            backoff_base=0.1,
        )
        result = coord.fetch_synchronized(
            ticker='AAPL',
            event_date=datetime(2024, 6, 15),
            min_sources=1,
        )
        assert result.quorum_met is True
        sr = result.source_results['flakey']
        assert sr.status == SourceStatus.SUCCESS
        assert sr.retry_count == 1  # succeeded on second attempt

    def test_circuit_breaker_skips_open_source(self):
        fetchers = {
            'broken': make_mock_fetcher(error=ConnectionError("fail")),
        }
        coord = FetchCoordinator(
            fetchers=fetchers,
            max_retries=0,
            circuit_failure_threshold=1,
        )
        # First call trips the breaker
        r1 = coord.fetch_synchronized(
            ticker='AAPL', event_date=datetime(2024, 6, 15), min_sources=0
        )
        assert r1.source_results['broken'].status == SourceStatus.FAILED

        # Second call should be blocked by circuit breaker
        r2 = coord.fetch_synchronized(
            ticker='AAPL', event_date=datetime(2024, 6, 15), min_sources=0
        )
        assert r2.source_results['broken'].status == SourceStatus.CIRCUIT_OPEN

    def test_deduplication_across_sources(self):
        """Identical text from different sources should be deduplicated."""
        same_df = pd.DataFrame({
            'timestamp': [datetime(2024, 6, 15)],
            'text': ['Identical text about AAPL ESG controversy'],
            'user_followers': [10],
            'retweets': [5],
            'likes': [20],
            'ticker': ['AAPL'],
            'sentiment': [0.5],
            'esg_relevance': [0.7],
            'esg_category': ['E'],
            'quality_score': [0.6],
        })
        fetchers = {
            'source_a': make_mock_fetcher(data=same_df),
            'source_b': make_mock_fetcher(data=same_df),
        }
        coord = FetchCoordinator(fetchers=fetchers, max_retries=0)
        result = coord.fetch_synchronized(
            ticker='AAPL', event_date=datetime(2024, 6, 15), min_sources=1,
        )
        # Should be deduplicated to 1 row
        assert len(result.combined_data) == 1

    def test_output_schema_enforced(self):
        """Output must always have exactly STANDARD_COLUMNS."""
        df_extra_cols = make_sample_social_df(3)
        df_extra_cols['bonus'] = 'extra'
        fetchers = {'src': make_mock_fetcher(data=df_extra_cols)}
        coord = FetchCoordinator(fetchers=fetchers, max_retries=0)
        result = coord.fetch_synchronized(
            ticker='AAPL', event_date=datetime(2024, 6, 15), min_sources=1,
        )
        assert list(result.combined_data.columns) == STANDARD_COLUMNS

    def test_source_health_reporting(self):
        fetchers = {
            'a': make_mock_fetcher(),
            'b': make_mock_fetcher(),
        }
        coord = FetchCoordinator(fetchers=fetchers)
        health = coord.get_source_health()
        assert health == {'a': 'CLOSED', 'b': 'CLOSED'}

    def test_empty_fetchers_dict(self):
        """Empty fetchers dict must not crash (no ThreadPoolExecutor(max_workers=0))."""
        coord = FetchCoordinator(fetchers={}, max_retries=0)
        result = coord.fetch_synchronized(
            ticker='AAPL',
            event_date=datetime(2024, 6, 15),
            min_sources=0,
        )
        assert result.quorum_met is True  # 0 >= 0
        assert result.combined_data.empty
        assert result.source_results == {}

    def test_empty_fetchers_quorum_not_met(self):
        """Empty fetchers with min_sources > 0 correctly reports quorum failure."""
        coord = FetchCoordinator(fetchers={}, max_retries=0)
        result = coord.fetch_synchronized(
            ticker='AAPL',
            event_date=datetime(2024, 6, 15),
            min_sources=1,
        )
        assert result.quorum_met is False

    def test_as_completed_timeout_handled(self):
        """A very slow source that exceeds the coordinator timeout
        should not crash the coordinator."""
        class SlowFetcher:
            def fetch_tweets_for_event(self, **kwargs):
                time.sleep(10)  # way longer than timeout
                return pd.DataFrame()

        coord = FetchCoordinator(
            fetchers={'slow': SlowFetcher()},
            max_retries=0,
            per_source_timeout=0.5,
        )
        result = coord.fetch_synchronized(
            ticker='AAPL',
            event_date=datetime(2024, 6, 15),
            min_sources=0,
        )
        # Should not crash. Source either timed out or is still running.
        assert isinstance(result, CoordinatedResult)

    def test_thread_safe_jitter(self):
        """Multiple concurrent sources with retries must not corrupt
        numpy random state (uses stdlib random instead)."""
        fetchers = {}
        for i in range(5):
            call_count = {"n": 0}
            class FlakeyN:
                _cc = call_count
                def fetch_tweets_for_event(self, **kwargs):
                    self._cc["n"] += 1
                    if self._cc["n"] <= 1:
                        raise ConnectionError("transient")
                    return pd.DataFrame({
                        'timestamp': [datetime(2024, 6, 15)],
                        'text': [f'post'],
                        'user_followers': [1], 'retweets': [0], 'likes': [0],
                        'ticker': ['AAPL'], 'sentiment': [0.1],
                        'esg_relevance': [0.5], 'esg_category': ['E'],
                        'quality_score': [0.5],
                    })
            fetchers[f'src_{i}'] = FlakeyN()

        coord = FetchCoordinator(
            fetchers=fetchers, max_retries=2, backoff_base=0.05,
        )
        result = coord.fetch_synchronized(
            ticker='AAPL', event_date=datetime(2024, 6, 15), min_sources=3,
        )
        # All should succeed after retry
        assert len(result.successful_sources) == 5


# ---------------------------------------------------------------------------
# Signal Schema Validation Tests
# ---------------------------------------------------------------------------

class TestSignalSchemaValidation:
    def test_valid_df_passes(self):
        df = make_sample_signal_df(10)
        violations = validate_signal_schema(df, raise_on_error=False)
        assert violations == []

    def test_missing_column_detected(self):
        df = make_sample_signal_df(5)
        df = df.drop(columns=['quintile'])
        violations = validate_signal_schema(df, raise_on_error=False)
        assert any('quintile' in v for v in violations)

    def test_raises_on_violation(self):
        df = make_sample_signal_df(5)
        df = df.drop(columns=['ticker'])
        with pytest.raises(SignalSchemaError):
            validate_signal_schema(df, raise_on_error=True)

    def test_null_values_detected(self):
        df = make_sample_signal_df(5)
        df.loc[0, 'raw_score'] = None
        violations = validate_signal_schema(df, raise_on_error=False)
        assert any('raw_score' in v and 'null' in v for v in violations)

    def test_out_of_bounds_detected(self):
        df = make_sample_signal_df(5)
        df.loc[0, 'signal'] = 1.5  # max is 1.0
        df.loc[1, 'raw_score'] = -0.1  # min is 0.0
        violations = validate_signal_schema(df, raise_on_error=False)
        assert any('signal' in v for v in violations)
        assert any('raw_score' in v for v in violations)

    def test_invalid_quintile_detected(self):
        df = make_sample_signal_df(5)
        df.loc[0, 'quintile'] = 7
        violations = validate_signal_schema(df, raise_on_error=False)
        assert any('quintile' in v for v in violations)

    def test_empty_df_passes(self):
        df = pd.DataFrame()
        violations = validate_signal_schema(df, raise_on_error=False)
        assert violations == []


class TestEnforceSignalSchema:
    def test_clips_out_of_range(self):
        df = make_sample_signal_df(3)
        df.loc[0, 'signal'] = 5.0
        df.loc[1, 'raw_score'] = -2.0
        df.loc[2, 'quintile'] = 0
        result = enforce_signal_schema(df)
        assert result['signal'].max() <= 1.0
        assert result['raw_score'].min() >= 0.0
        assert result['quintile'].min() >= 1

    def test_adds_missing_columns(self):
        df = pd.DataFrame({'ticker': ['AAPL'], 'date': [datetime(2024, 1, 1)]})
        result = enforce_signal_schema(df)
        for col in SIGNAL_REQUIRED_COLUMNS:
            assert col in result.columns

    def test_does_not_mutate_input(self):
        df = make_sample_signal_df(3)
        original_val = df['signal'].iloc[0]
        df_copy = df.copy()
        enforce_signal_schema(df)
        assert df['signal'].iloc[0] == original_val
        pd.testing.assert_frame_equal(df, df_copy)

    def test_handles_string_numerics(self):
        df = pd.DataFrame({
            'ticker': ['AAPL'],
            'date': ['2024-01-01'],
            'raw_score': ['0.5'],
            'z_score': ['1.2'],
            'signal': ['0.3'],
            'quintile': ['3'],
            'event_category': ['E'],
            'event_confidence': ['0.8'],
            'sentiment_intensity': ['-0.2'],
            'volume_ratio': ['2.0'],
            'n_posts': ['15'],
            'has_social_data': [True],
            'confidence': ['0.7'],
        })
        result = enforce_signal_schema(df)
        assert result['raw_score'].dtype == np.float64
        assert result['quintile'].dtype in (np.int64, np.int32, int)

    def test_strips_extra_columns(self):
        """Extra columns (like year_month from validate_signal_quality)
        must be stripped to guarantee exact schema compliance."""
        df = make_sample_signal_df(3)
        df['year_month'] = '2024-06'
        df['_internal'] = 999
        result = enforce_signal_schema(df)
        assert 'year_month' not in result.columns
        assert '_internal' not in result.columns
        assert list(result.columns) == SIGNAL_REQUIRED_COLUMNS

    def test_column_order_matches_schema(self):
        """Output column order must exactly match SIGNAL_REQUIRED_COLUMNS."""
        df = make_sample_signal_df(3)
        # Shuffle columns
        shuffled = df[list(reversed(df.columns))]
        result = enforce_signal_schema(shuffled)
        assert list(result.columns) == SIGNAL_REQUIRED_COLUMNS


# ---------------------------------------------------------------------------
# CoordinatedResult Tests
# ---------------------------------------------------------------------------

class TestCoordinatedResult:
    def test_summary_format(self):
        r = CoordinatedResult(
            source_results={
                'a': SourceResult('a', SourceStatus.SUCCESS,
                                  make_sample_social_df(3), 100.0, 0),
                'b': SourceResult('b', SourceStatus.FAILED,
                                  pd.DataFrame(columns=STANDARD_COLUMNS),
                                  200.0, 2, error='timeout'),
            },
            combined_data=make_sample_social_df(3),
            quorum_met=True,
            total_latency_ms=300.0,
        )
        summary = r.summary()
        assert 'quorum_met=True' in summary
        assert 'SUCCESS' in summary
        assert 'FAILED' in summary
        assert 'timeout' in summary

    def test_is_valid_requires_quorum_and_data(self):
        r1 = CoordinatedResult(quorum_met=True, combined_data=make_sample_social_df(1))
        assert r1.is_valid is True

        r2 = CoordinatedResult(quorum_met=False, combined_data=make_sample_social_df(1))
        assert r2.is_valid is False

        r3 = CoordinatedResult(quorum_met=True, combined_data=pd.DataFrame())
        assert r3.is_valid is False
