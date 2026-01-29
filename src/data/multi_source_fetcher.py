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
                 min_sources: int = 1,
                 max_retries: int = 3,
                 per_source_timeout: float = 120.0,
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
        """
        if sources is None:
            sources = ['arctic_shift', 'gdelt', 'stocktwits']

        self.sources = sources
        self.min_sources = min_sources
        self.fetchers = {}

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
                )
                print("  [Multi-Source] StockTwits: initialized")
            except Exception as e:
                print(f"  [Multi-Source] StockTwits: failed to initialize ({e})")

        if not self.fetchers:
            print("  [Multi-Source] WARNING: No sources initialized, using mock data")
            self.use_mock = True
            self._coordinator = None
        else:
            self.use_mock = False
            active = ', '.join(self.fetchers.keys())
            print(f"  [Multi-Source] Active sources: {active}")

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
                               days_before: int = 3, days_after: int = 7,
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
            return self._generate_mock_combined(
                ticker, event_date, days_before, days_after, max_results
            )

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

        if not result.quorum_met:
            print(
                f"  [Multi-Source] WARNING: Quorum not met for {ticker} "
                f"(needed {self.min_sources}, got {len(result.successful_sources)}). "
                f"Failed: {result.failed_sources}"
            )

        combined = result.combined_data

        if combined.empty:
            return pd.DataFrame(columns=STANDARD_COLUMNS)

        # Log combined results
        total = len(combined)
        esg_count = (combined['esg_relevance'] > 0).sum()
        avg_sentiment = combined['sentiment'].mean()
        source_parts = []
        for name, sr in result.source_results.items():
            source_parts.append(f"{name}:{sr.row_count}")
        sources_str = ' + '.join(source_parts)
        print(f"  Multi-Source: {total} total posts ({sources_str}) for {ticker}")
        print(f"    ESG-relevant: {esg_count}/{total} | Avg sentiment: {avg_sentiment:+.2f}")

        return combined[STANDARD_COLUMNS]

    def get_source_health(self) -> Dict[str, str]:
        """Return circuit breaker states for each source."""
        if self._coordinator is None:
            return {}
        return self._coordinator.get_source_health()

    def _generate_mock_combined(self, ticker: str, event_date: datetime,
                                 days_before: int, days_after: int,
                                 max_results: int) -> pd.DataFrame:
        """Generate mock data simulating multiple sources."""
        np.random.seed(hash(f"multi_{ticker}_{event_date}") % 2**31)
        n = min(np.random.randint(10, 30), max_results)

        sources = ['arctic_shift', 'gdelt', 'stocktwits']
        data = []
        for i in range(n):
            offset = np.random.randint(-days_before, days_after + 1)
            ts = event_date + timedelta(days=offset, hours=np.random.randint(0, 24))
            sentiment = np.random.uniform(-0.8, 0.8)
            src = np.random.choice(sources)
            data.append({
                'timestamp': ts,
                'text': f"Mock {src} post about {ticker} ESG event {i}",
                'user_followers': 1,
                'retweets': 0,
                'likes': np.random.randint(0, 100),
                'ticker': ticker,
                'sentiment': round(sentiment, 3),
                'esg_relevance': np.random.uniform(0.1, 0.8),
                'esg_category': np.random.choice(['E', 'S', 'G']),
                'quality_score': np.random.uniform(0.3, 0.9),
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
