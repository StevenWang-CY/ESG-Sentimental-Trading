"""
FetchCoordinator - Atomic Multi-Source Data Synchronization

Coordinates concurrent data fetching from multiple API sources with:
  1. Atomic synchronization barrier (all sources complete or timeout)
  2. Token-bucket rate limiting per source
  3. Exponential backoff with jitter on transient failures
  4. Circuit breaker pattern to avoid hammering degraded sources
  5. Structured result reporting per source

Usage:
    coordinator = FetchCoordinator(fetchers={
        'arctic_shift': arctic_shift_fetcher,
        'gdelt': gdelt_fetcher,
        'stocktwits': stocktwits_fetcher,
    })
    result = coordinator.fetch_synchronized(
        ticker='AAPL', event_date=datetime(2024, 6, 15),
        min_sources=2,  # require at least 2 sources to succeed
    )
    if result.is_valid:
        combined_df = result.combined_data
"""

from __future__ import annotations

import logging
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, Future, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Callable, Dict, List, Optional, Protocol

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums & Data Structures
# ---------------------------------------------------------------------------

class SourceStatus(Enum):
    """Outcome status for a single source fetch."""
    SUCCESS = auto()
    PARTIAL = auto()       # returned data but fewer than expected
    FAILED = auto()        # all retries exhausted
    RATE_LIMITED = auto()  # gave up due to rate limiting
    TIMEOUT = auto()       # exceeded per-source timeout
    CIRCUIT_OPEN = auto()  # skipped because circuit breaker is open


@dataclass(frozen=True)
class SourceResult:
    """Immutable result from a single source fetch attempt."""
    source_name: str
    status: SourceStatus
    data: pd.DataFrame
    latency_ms: float
    retry_count: int
    error: Optional[str] = None
    row_count: int = 0

    def __post_init__(self):
        object.__setattr__(self, 'row_count', len(self.data))


@dataclass
class CoordinatedResult:
    """
    Aggregated result from all sources after synchronization.

    Attributes:
        source_results: per-source results
        combined_data: deduplicated, schema-validated DataFrame
        quorum_met: True if min_sources threshold was reached
        total_latency_ms: wall-clock time for the entire coordinated fetch
    """
    source_results: Dict[str, SourceResult] = field(default_factory=dict)
    combined_data: pd.DataFrame = field(default_factory=lambda: pd.DataFrame())
    quorum_met: bool = False
    total_latency_ms: float = 0.0

    @property
    def is_valid(self) -> bool:
        """True if quorum was met and combined data is non-empty."""
        return self.quorum_met and not self.combined_data.empty

    @property
    def successful_sources(self) -> List[str]:
        return [
            name for name, r in self.source_results.items()
            if r.status in (SourceStatus.SUCCESS, SourceStatus.PARTIAL)
        ]

    @property
    def failed_sources(self) -> List[str]:
        return [
            name for name, r in self.source_results.items()
            if r.status not in (SourceStatus.SUCCESS, SourceStatus.PARTIAL)
        ]

    def summary(self) -> str:
        lines = [f"CoordinatedResult  quorum_met={self.quorum_met}  "
                 f"total_rows={len(self.combined_data)}  "
                 f"latency={self.total_latency_ms:.0f}ms"]
        for name, r in self.source_results.items():
            lines.append(
                f"  {name:16s}  status={r.status.name:14s}  "
                f"rows={r.row_count:4d}  retries={r.retry_count}  "
                f"latency={r.latency_ms:.0f}ms"
                + (f"  error={r.error}" if r.error else "")
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Rate Limiter (Token Bucket)
# ---------------------------------------------------------------------------

class TokenBucketRateLimiter:
    """
    Thread-safe token-bucket rate limiter.

    Args:
        rate: tokens added per second
        burst: maximum bucket capacity
    """

    def __init__(self, rate: float = 2.0, burst: int = 5):
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def acquire(self, timeout: float = 30.0) -> bool:
        """
        Block until a token is available or timeout.

        Returns:
            True if token acquired, False if timed out.
        """
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return True
            if time.monotonic() >= deadline:
                return False
            # Sleep a small interval before retrying
            time.sleep(min(0.1, 1.0 / self._rate))

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last_refill = now


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------

class CircuitState(Enum):
    CLOSED = auto()    # normal operation
    OPEN = auto()      # failing, reject calls
    HALF_OPEN = auto() # testing if recovered


class CircuitBreaker:
    """
    Per-source circuit breaker.

    Opens after `failure_threshold` consecutive failures.
    After `recovery_timeout` seconds, transitions to half-open to probe.
    A single success in half-open resets to closed.
    """

    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 120.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if (self._last_failure_time is not None and
                        time.monotonic() - self._last_failure_time >= self.recovery_timeout):
                    self._state = CircuitState.HALF_OPEN
            return self._state

    def allow_request(self) -> bool:
        s = self.state
        return s in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self):
        with self._lock:
            self._consecutive_failures = 0
            self._state = CircuitState.CLOSED

    def record_failure(self):
        with self._lock:
            self._consecutive_failures += 1
            self._last_failure_time = time.monotonic()
            if self._consecutive_failures >= self.failure_threshold:
                self._state = CircuitState.OPEN


# ---------------------------------------------------------------------------
# Fetcher Protocol
# ---------------------------------------------------------------------------

class SentimentFetcher(Protocol):
    """Protocol that all source fetchers must satisfy."""

    def fetch_tweets_for_event(
        self,
        ticker: str,
        event_date: datetime,
        keywords: Optional[List[str]] = None,
        days_before: int = 3,
        days_after: int = 7,
        max_results: int = 100,
    ) -> pd.DataFrame: ...


# ---------------------------------------------------------------------------
# Standard Output Schema
# ---------------------------------------------------------------------------

STANDARD_COLUMNS = [
    'timestamp', 'text', 'user_followers', 'retweets', 'likes',
    'ticker', 'sentiment', 'esg_relevance', 'esg_category', 'quality_score',
]

COLUMN_DEFAULTS = {
    'timestamp': pd.NaT,
    'text': '',
    'user_followers': 0,
    'retweets': 0,
    'likes': 0,
    'ticker': '',
    'sentiment': 0.0,
    'esg_relevance': 0.0,
    'esg_category': 'Unknown',
    'quality_score': 0.0,
}


def enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enforce the standard output schema on a DataFrame.

    - Adds missing columns with defaults
    - Drops extra columns
    - Coerces types
    - Returns a copy to avoid mutation

    This guarantees downstream code always receives the exact expected columns.
    """
    if df.empty:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    df = df.copy()

    # Add missing columns
    for col in STANDARD_COLUMNS:
        if col not in df.columns:
            df[col] = COLUMN_DEFAULTS[col]

    # Select and order
    df = df[STANDARD_COLUMNS].copy()

    # Type coercion (safe)
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    for num_col in ('user_followers', 'retweets', 'likes'):
        df[num_col] = pd.to_numeric(df[num_col], errors='coerce').fillna(0).astype(int)
    for float_col in ('sentiment', 'esg_relevance', 'quality_score'):
        df[float_col] = pd.to_numeric(df[float_col], errors='coerce').fillna(0.0)
    df['ticker'] = df['ticker'].astype(str)
    df['text'] = df['text'].astype(str)
    df['esg_category'] = df['esg_category'].astype(str)

    return df


# ---------------------------------------------------------------------------
# FetchCoordinator
# ---------------------------------------------------------------------------

class FetchCoordinator:
    """
    Coordinates concurrent fetching from multiple API sources with atomic
    synchronization, rate limiting, retry with backoff, and circuit breaking.

    Args:
        fetchers: mapping of source_name -> fetcher instance
        rate_limits: per-source rate limits as {name: (rate, burst)}
        max_retries: maximum retry attempts per source on transient failure
        per_source_timeout: timeout in seconds for a single source (all retries)
        backoff_base: base wait time for exponential backoff (seconds)
        backoff_max: maximum backoff wait (seconds)
    """

    def __init__(
        self,
        fetchers: Dict[str, SentimentFetcher],
        rate_limits: Optional[Dict[str, tuple]] = None,
        max_retries: int = 3,
        per_source_timeout: float = 120.0,
        backoff_base: float = 2.0,
        backoff_max: float = 60.0,
        circuit_failure_threshold: int = 3,
        circuit_recovery_timeout: float = 120.0,
    ):
        self.fetchers = dict(fetchers)
        self.max_retries = max_retries
        self.per_source_timeout = per_source_timeout
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

        # Per-source rate limiters
        default_rates = {
            'arctic_shift': (2.0, 5),
            'gdelt': (2.0, 5),
            'stocktwits': (0.2, 3),  # ~200 req/hour = 0.055/s, conservative
        }
        self._rate_limiters: Dict[str, TokenBucketRateLimiter] = {}
        for name in self.fetchers:
            rate_config = (rate_limits or {}).get(name, default_rates.get(name, (1.0, 3)))
            self._rate_limiters[name] = TokenBucketRateLimiter(
                rate=rate_config[0], burst=rate_config[1]
            )

        # Per-source circuit breakers
        self._circuit_breakers: Dict[str, CircuitBreaker] = {
            name: CircuitBreaker(
                failure_threshold=circuit_failure_threshold,
                recovery_timeout=circuit_recovery_timeout,
            )
            for name in self.fetchers
        }

    def fetch_synchronized(
        self,
        ticker: str,
        event_date: datetime,
        keywords: Optional[List[str]] = None,
        days_before: int = 3,
        days_after: int = 7,
        max_results: int = 100,
        min_sources: int = 1,
    ) -> CoordinatedResult:
        """
        Fetch from all sources concurrently with atomic synchronization.

        All sources are launched in parallel. The coordinator waits for ALL
        sources to complete (or timeout/fail), then checks the quorum.

        Args:
            ticker: stock ticker
            event_date: date of the ESG event
            keywords: optional ESG keywords
            days_before: days before event to search
            days_after: days after event to search
            max_results: total max results across all sources
            min_sources: minimum number of sources that must succeed (quorum)

        Returns:
            CoordinatedResult with per-source status and combined data
        """
        wall_start = time.monotonic()

        per_source_max = max(max_results // max(len(self.fetchers), 1), 20)

        # Launch all sources concurrently
        source_results: Dict[str, SourceResult] = {}

        if not self.fetchers:
            # No sources configured - return empty result immediately
            return CoordinatedResult(
                source_results={},
                combined_data=pd.DataFrame(columns=STANDARD_COLUMNS),
                quorum_met=(min_sources <= 0),
                total_latency_ms=(time.monotonic() - wall_start) * 1000,
            )

        with ThreadPoolExecutor(
            max_workers=len(self.fetchers),
            thread_name_prefix="fetch",
        ) as executor:
            future_to_source: Dict[Future, str] = {}
            for source_name, fetcher in self.fetchers.items():
                future = executor.submit(
                    self._fetch_single_source,
                    source_name=source_name,
                    fetcher=fetcher,
                    ticker=ticker,
                    event_date=event_date,
                    keywords=keywords,
                    days_before=days_before,
                    days_after=days_after,
                    max_results=per_source_max,
                )
                future_to_source[future] = source_name

            # Wait for ALL futures (atomic barrier).
            # as_completed raises FuturesTimeoutError if the overall
            # deadline is exceeded before all futures report back.
            try:
                for future in as_completed(future_to_source, timeout=self.per_source_timeout + 10):
                    source_name = future_to_source[future]
                    try:
                        result = future.result(timeout=5)
                        source_results[source_name] = result
                    except Exception as exc:
                        source_results[source_name] = SourceResult(
                            source_name=source_name,
                            status=SourceStatus.FAILED,
                            data=pd.DataFrame(columns=STANDARD_COLUMNS),
                            latency_ms=0.0,
                            retry_count=0,
                            error=f"Future exception: {exc}",
                        )
            except FuturesTimeoutError:
                logger.warning(
                    "FetchCoordinator: as_completed timed out; "
                    "some sources did not finish in time."
                )

        # Handle any sources that didn't produce a future result
        for source_name in self.fetchers:
            if source_name not in source_results:
                source_results[source_name] = SourceResult(
                    source_name=source_name,
                    status=SourceStatus.TIMEOUT,
                    data=pd.DataFrame(columns=STANDARD_COLUMNS),
                    latency_ms=self.per_source_timeout * 1000,
                    retry_count=0,
                    error="Source did not complete within timeout",
                )

        # Check quorum
        successful_count = sum(
            1 for r in source_results.values()
            if r.status in (SourceStatus.SUCCESS, SourceStatus.PARTIAL)
        )
        quorum_met = successful_count >= min_sources

        # Combine data from all successful sources
        combined = self._combine_results(source_results, max_results)

        wall_elapsed = (time.monotonic() - wall_start) * 1000

        result = CoordinatedResult(
            source_results=source_results,
            combined_data=combined,
            quorum_met=quorum_met,
            total_latency_ms=wall_elapsed,
        )

        # Log summary
        logger.info(result.summary())
        print(result.summary())

        return result

    def _fetch_single_source(
        self,
        source_name: str,
        fetcher: SentimentFetcher,
        ticker: str,
        event_date: datetime,
        keywords: Optional[List[str]],
        days_before: int,
        days_after: int,
        max_results: int,
    ) -> SourceResult:
        """
        Fetch from a single source with retry, rate limiting, and circuit breaking.
        """
        start = time.monotonic()

        # Circuit breaker check
        cb = self._circuit_breakers[source_name]
        if not cb.allow_request():
            return SourceResult(
                source_name=source_name,
                status=SourceStatus.CIRCUIT_OPEN,
                data=pd.DataFrame(columns=STANDARD_COLUMNS),
                latency_ms=(time.monotonic() - start) * 1000,
                retry_count=0,
                error=f"Circuit breaker OPEN for {source_name}",
            )

        rl = self._rate_limiters[source_name]
        last_error: Optional[str] = None

        for attempt in range(self.max_retries + 1):
            # Rate limit gate
            if not rl.acquire(timeout=self.per_source_timeout):
                return SourceResult(
                    source_name=source_name,
                    status=SourceStatus.RATE_LIMITED,
                    data=pd.DataFrame(columns=STANDARD_COLUMNS),
                    latency_ms=(time.monotonic() - start) * 1000,
                    retry_count=attempt,
                    error="Rate limiter timeout",
                )

            try:
                df = fetcher.fetch_tweets_for_event(
                    ticker=ticker,
                    event_date=event_date,
                    keywords=keywords,
                    days_before=days_before,
                    days_after=days_after,
                    max_results=max_results,
                )

                # Enforce schema on the result
                df = enforce_schema(df)

                # Determine status
                if df.empty:
                    status = SourceStatus.PARTIAL
                else:
                    status = SourceStatus.SUCCESS

                cb.record_success()

                return SourceResult(
                    source_name=source_name,
                    status=status,
                    data=df,
                    latency_ms=(time.monotonic() - start) * 1000,
                    retry_count=attempt,
                )

            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                cb.record_failure()

                if attempt < self.max_retries:
                    # Exponential backoff with jitter
                    backoff = min(
                        self.backoff_base * (2 ** attempt),
                        self.backoff_max,
                    )
                    # random.random() is thread-safe (unlike np.random.random())
                    jitter = backoff * 0.1 * (2 * random.random() - 1)  # +/- 10%
                    wait = max(backoff + jitter, 0.5)
                    logger.warning(
                        f"[{source_name}] attempt {attempt + 1}/{self.max_retries + 1} "
                        f"failed: {last_error}. Retrying in {wait:.1f}s"
                    )
                    time.sleep(wait)

        # All retries exhausted
        return SourceResult(
            source_name=source_name,
            status=SourceStatus.FAILED,
            data=pd.DataFrame(columns=STANDARD_COLUMNS),
            latency_ms=(time.monotonic() - start) * 1000,
            retry_count=self.max_retries,
            error=last_error,
        )

    def _combine_results(
        self,
        source_results: Dict[str, SourceResult],
        max_results: int,
    ) -> pd.DataFrame:
        """
        Combine and deduplicate results from all successful sources.
        Enforces the standard output schema on the final result.
        """
        dfs = []
        for name, result in source_results.items():
            if result.status in (SourceStatus.SUCCESS, SourceStatus.PARTIAL):
                if not result.data.empty:
                    df = result.data.copy()
                    df['_source'] = name
                    dfs.append(df)

        if not dfs:
            return pd.DataFrame(columns=STANDARD_COLUMNS)

        combined = pd.concat(dfs, ignore_index=True)

        # Deduplicate by text similarity (first 100 chars, lowered)
        combined['_text_key'] = combined['text'].str[:100].str.lower().str.strip()
        combined = combined.drop_duplicates(subset=['_text_key'], keep='first')
        combined = combined.drop(columns=['_text_key', '_source'], errors='ignore')

        # Sort by timestamp
        combined = combined.sort_values('timestamp').reset_index(drop=True)

        # Trim to max_results, keeping highest quality
        if len(combined) > max_results:
            combined = combined.nlargest(max_results, 'quality_score')
            combined = combined.sort_values('timestamp').reset_index(drop=True)

        # Final schema enforcement
        combined = enforce_schema(combined)

        return combined

    def get_source_health(self) -> Dict[str, str]:
        """Return current circuit breaker state for each source."""
        return {
            name: cb.state.name
            for name, cb in self._circuit_breakers.items()
        }

    def reset_circuit_breakers(self):
        """Reset all circuit breakers to closed state."""
        for name in self._circuit_breakers:
            self._circuit_breakers[name] = CircuitBreaker(
                failure_threshold=self._circuit_breakers[name].failure_threshold,
                recovery_timeout=self._circuit_breakers[name].recovery_timeout,
            )
