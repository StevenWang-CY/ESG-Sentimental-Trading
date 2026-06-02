"""
Multi-Source Social Media / News Fetcher
Combines data from multiple sources for richer sentiment analysis:
  1. Arctic Shift (archived Reddit data - historical, free)
  2. GDELT (global news articles - historical, free)
  3. StockTwits (stock social media - recent only, free)

Each source has different strengths:
  - Arctic Shift: Best for historical Reddit discussion, ESG debates
  - GDELT: Best for mainstream news coverage, institutional perspective
  - StockTwits: Best for real-time retail trader sentiment

REFACTOR (Jan 2026):
  Uses FetchCoordinator for atomic synchronization across all three sources.
  All sources are fetched concurrently with rate limiting, retry with
  exponential backoff, and circuit breaker protection. A configurable quorum
  ensures we only proceed when enough sources report back successfully.
"""

import logging
import zlib

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from src.data.fetch_coordinator import (
    FetchCoordinator,
    CoordinatedResult,
    SourceStatus,
    STANDARD_COLUMNS,
    enforce_schema,
)
from src.utils.provenance import REAL, MOCK, EMPTY, tag, DataUnavailableError

logger = logging.getLogger(__name__)


class MultiSourceFetcher:
    """
    Combines Arctic Shift, GDELT, and StockTwits into a single fetcher
    with atomic synchronization via FetchCoordinator.

    Compatible interface with ArcticShiftFetcher (same fetch_tweets_for_event signature).
    Returns DataFrames with identical column format.
    """

    def __init__(self, sources: Optional[List[str]] = None,
                 enable_sentiment: bool = True,
                 arctic_shift_config: Optional[Dict] = None,
                 gdelt_config: Optional[Dict] = None,
                 stocktwits_config: Optional[Dict] = None,
                 sentiment_mode: str = 'hybrid',
                 sentiment_model_name: str = "ProsusAI/finbert",
                 strict_sentiment: bool = False,
                 min_sources: int = 1,
                 max_retries: int = 3,
                 per_source_timeout: float = 120.0,
                 use_mock: bool = False,
                 **kwargs):
        """
        Initialize multi-source fetcher.

        Args:
            sources: List of sources to use. Default: all three.
                     Options: 'arctic_shift', 'gdelt', 'stocktwits'
            enable_sentiment: If True, use FinBERT for sentiment scoring
            arctic_shift_config: Config dict for Arctic Shift fetcher
            gdelt_config: Config dict for GDELT fetcher
            stocktwits_config: Config dict for StockTwits fetcher
            min_sources: Minimum number of sources that must succeed (quorum)
            max_retries: Maximum retry attempts per source on transient failure
            per_source_timeout: Timeout in seconds for a single source
            use_mock: If True, intentional demo/test mode -- combined data is
                      synthetic and stamped MOCK. If False (production), the
                      fetcher fails closed: if no sub-source initializes it raises
                      DataUnavailableError instead of fabricating data.
        """
        if sources is None:
            sources = ['arctic_shift', 'gdelt', 'stocktwits']

        self.sources = sources
        self.min_sources = min_sources
        self.fetchers = {}
        self.use_mock = use_mock
        self._coordinator = None

        if use_mock:
            # Explicit demo/test mode: do not initialize real sub-sources; combined
            # output is synthetic and stamped MOCK at fetch time.
            logger.info("[Multi-Source] use_mock=True: serving synthetic combined data (demo mode)")
            return

        # Initialize each source
        if 'arctic_shift' in sources:
            try:
                from src.data.arctic_shift_fetcher import ArcticShiftFetcher
                config = arctic_shift_config or {}
                self.fetchers['arctic_shift'] = ArcticShiftFetcher(
                    use_mock=config.get('use_mock', False),
                    subreddits=config.get('subreddits', None),
                    request_timeout=config.get('request_timeout', 15),
                    enable_sentiment=enable_sentiment,
                    sentiment_mode=sentiment_mode,
                    sentiment_model_name=sentiment_model_name,
                    strict_sentiment=strict_sentiment,
                )
                print("  [Multi-Source] Arctic Shift: initialized")
            except Exception as e:
                print(f"  [Multi-Source] Arctic Shift: failed to initialize ({e})")

        if 'gdelt' in sources:
            try:
                from src.data.gdelt_fetcher import GDELTFetcher
                config = gdelt_config or {}
                self.fetchers['gdelt'] = GDELTFetcher(
                    use_mock=config.get('use_mock', False),
                    enable_sentiment=enable_sentiment,
                    request_timeout=config.get('request_timeout', 30),
                    max_articles=config.get('max_articles', 50),
                    sentiment_mode=sentiment_mode,
                    sentiment_model_name=sentiment_model_name,
                    strict_sentiment=strict_sentiment,
                )
                print("  [Multi-Source] GDELT: initialized")
            except Exception as e:
                print(f"  [Multi-Source] GDELT: failed to initialize ({e})")

        if 'stocktwits' in sources:
            try:
                from src.data.stocktwits_fetcher import StockTwitsFetcher
                config = stocktwits_config or {}
                self.fetchers['stocktwits'] = StockTwitsFetcher(
                    use_mock=config.get('use_mock', False),
                    enable_sentiment=enable_sentiment,
                    request_timeout=config.get('request_timeout', 15),
                    max_pages=config.get('max_pages', 5),
                    sentiment_mode=sentiment_mode,
                    sentiment_model_name=sentiment_model_name,
                    strict_sentiment=strict_sentiment,
                )
                print("  [Multi-Source] StockTwits: initialized")
            except Exception as e:
                print(f"  [Multi-Source] StockTwits: failed to initialize ({e})")

        if not self.fetchers:
            # Production fail-closed: ALL sub-sources failed to initialize. Refuse to
            # fabricate combined data; raise so the run aborts rather than reporting
            # synthetic results as real.
            raise DataUnavailableError(
                "MultiSourceFetcher(use_mock=False): no sub-source could be initialized "
                f"from {sources}. Check dependencies/credentials/network for each source, "
                "or construct with use_mock=True for a demo run."
            )

        active = ', '.join(self.fetchers.keys())
        logger.info("[Multi-Source] Active sources: %s", active)

        # Initialize the coordinator with all active fetchers
        self._coordinator = FetchCoordinator(
            fetchers=self.fetchers,
            max_retries=max_retries,
            per_source_timeout=per_source_timeout,
        )

    @property
    def last_coordinated_result(self) -> Optional[CoordinatedResult]:
        """Access the most recent CoordinatedResult for diagnostics."""
        return getattr(self, '_last_result', None)

    def fetch_tweets_for_event(self, ticker: str, event_date: datetime,
                               keywords: Optional[List[str]] = None,
                               days_before: int = 10, days_after: int = 3,
                               max_results: int = 100) -> pd.DataFrame:
        """
        Fetch social/news data from all sources with atomic synchronization.

        All sources are fetched concurrently via the FetchCoordinator. The
        coordinator enforces rate limiting, retries transient failures with
        exponential backoff, and checks a quorum threshold before returning.

        Args:
            ticker: Stock ticker symbol
            event_date: Date of ESG event
            keywords: ESG keywords (optional)
            days_before: Days before event to search
            days_after: Days after event to search
            max_results: Maximum total results across all sources

        Returns:
            Combined DataFrame with standard columns:
            [timestamp, text, user_followers, retweets, likes, ticker,
             sentiment, esg_relevance, esg_category, quality_score]
        """
        if self.use_mock:
            mock_df = self._generate_mock_combined(
                ticker, event_date, days_before, days_after, max_results
            )
            return tag(mock_df, MOCK, source='multi_source')

        # Coordinated fetch across all sources
        result: CoordinatedResult = self._coordinator.fetch_synchronized(
            ticker=ticker,
            event_date=event_date,
            keywords=keywords,
            days_before=days_before,
            days_after=days_after,
            max_results=max_results,
            min_sources=self.min_sources,
        )

        # Store for diagnostics
        self._last_result = result

        # Compute cross-source sentiment agreement
        self._last_source_metrics = self._compute_source_agreement(result)

        if not result.quorum_met:
            logger.warning(
                "[Multi-Source] Quorum not met for %s (needed %d, got %d). Failed: %s",
                ticker, self.min_sources, len(result.successful_sources), result.failed_sources
            )

        combined = result.combined_data

        # NOTE: result.combined_data comes from pd.concat inside the coordinator,
        # which drops df.attrs -- so we must (re-)stamp provenance here explicitly.
        if combined.empty:
            # Real fetch that legitimately returned no rows across all sub-sources.
            # Stamp EMPTY (not MOCK) so the orchestrator guard can abort the run
            # rather than backtesting on empty data.
            empty_df = pd.DataFrame(columns=STANDARD_COLUMNS)
            return tag(empty_df, EMPTY, source='multi_source')

        # Log combined results
        total = len(combined)
        esg_count = (combined['esg_relevance'] > 0).sum()
        avg_sentiment = combined['sentiment'].mean()
        source_parts = []
        for name, sr in result.source_results.items():
            source_parts.append(f"{name}:{sr.row_count}")
        sources_str = ' + '.join(source_parts)
        logger.info("[Multi-Source] %d total posts (%s) for %s", total, sources_str, ticker)
        logger.info(
            "[Multi-Source] ESG-relevant: %d/%d | Avg sentiment: %+.2f",
            esg_count, total, avg_sentiment
        )

        result_df = combined[STANDARD_COLUMNS]
        return tag(result_df, REAL, source='multi_source')

    @property
    def last_source_metrics(self) -> Dict:
        """Access source agreement metrics from the most recent fetch."""
        return getattr(self, '_last_source_metrics',
                       {'n_sources': 0, 'source_agreement': 0.0})

    def _compute_source_agreement(self, result: CoordinatedResult) -> Dict:
        """
        Compute cross-source sentiment agreement metrics.

        Measures whether independent sources (Reddit, GDELT, StockTwits)
        agree on sentiment direction. Agreement boosts signal confidence
        because independent corroboration is a strong quality indicator.

        Returns:
            Dict with n_sources (int) and source_agreement (float 0-1).
        """
        source_sentiments = {}
        for name, sr in result.source_results.items():
            if sr.status in (SourceStatus.SUCCESS, SourceStatus.PARTIAL) and sr.row_count > 0:
                mean_sentiment = float(sr.data['sentiment'].mean())
                source_sentiments[name] = mean_sentiment

        n_sources = len(source_sentiments)
        if n_sources < 2:
            return {'n_sources': n_sources, 'source_agreement': 0.0}

        # Check directional agreement: do sources agree on bullish/bearish?
        directions = []
        for s in source_sentiments.values():
            if s > 0.01:
                directions.append(1)
            elif s < -0.01:
                directions.append(-1)
            else:
                directions.append(0)

        # Agreement = fraction of non-neutral sources sharing the majority direction
        non_neutral = [d for d in directions if d != 0]
        if not non_neutral:
            return {'n_sources': n_sources, 'source_agreement': 0.0}

        from collections import Counter
        majority_dir = Counter(non_neutral).most_common(1)[0][0]
        agreement = sum(1 for d in non_neutral if d == majority_dir) / n_sources

        return {
            'n_sources': n_sources,
            'source_agreement': round(agreement, 3),
        }

    def get_source_health(self) -> Dict[str, str]:
        """Return circuit breaker states for each source."""
        if self._coordinator is None:
            return {}
        return self._coordinator.get_source_health()

    def _generate_mock_combined(self, ticker: str, event_date: datetime,
                                 days_before: int, days_after: int,
                                 max_results: int) -> pd.DataFrame:
        """Generate mock data simulating multiple sources.

        Only reachable when use_mock=True (explicit demo/test mode).
        """
        # Local deterministic RNG keyed on ticker+event (no global np.random.seed
        # mutation, stable across processes).
        rng = np.random.default_rng(zlib.crc32(f"multi_{ticker}_{event_date}".encode()))
        n = min(int(rng.integers(10, 30)), max_results)

        sources = ['arctic_shift', 'gdelt', 'stocktwits']
        data = []
        for i in range(n):
            offset = int(rng.integers(-days_before, days_after + 1))
            ts = event_date + timedelta(days=offset, hours=int(rng.integers(0, 24)))
            sentiment = float(rng.uniform(-0.8, 0.8))
            src = rng.choice(sources)
            data.append({
                'timestamp': ts,
                'text': f"Mock {src} post about {ticker} ESG event {i}",
                'user_followers': 1,
                'retweets': 0,
                'likes': int(rng.integers(0, 100)),
                'ticker': ticker,
                'sentiment': round(sentiment, 3),
                'esg_relevance': float(rng.uniform(0.1, 0.8)),
                'esg_category': rng.choice(['E', 'S', 'G']),
                'quality_score': float(rng.uniform(0.3, 0.9)),
            })

        return pd.DataFrame(data)

    def fetch_tweets_batch(self, tickers: List[str], event_dates: Dict[str, datetime],
                           keywords: Optional[List[str]] = None,
                           days_before: int = 3, days_after: int = 7,
                           max_results_per_ticker: int = 100) -> Dict[str, pd.DataFrame]:
        """Fetch data for multiple tickers from all sources."""
        results = {}
        for ticker in tickers:
            if ticker in event_dates:
                results[ticker] = self.fetch_tweets_for_event(
                    ticker, event_dates[ticker], keywords,
                    days_before, days_after, max_results_per_ticker
                )
        return results
