"""
Twitter/X Data Fetcher
Fetches tweets related to stock tickers and ESG events using Twitter API v2
"""

import logging
import zlib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time

from src.utils.provenance import REAL, MOCK, EMPTY, tag, DataUnavailableError
from src.utils.config_loader import resolve_credential, is_unset

logger = logging.getLogger(__name__)


class TwitterFetcher:
    """
    Fetches Twitter/X data using Twitter API v2 (tweepy library)
    Supports both real API calls and mock data for testing
    """

    def __init__(self, bearer_token: Optional[str] = None, use_mock: bool = False):
        """
        Initialize Twitter fetcher

        Args:
            bearer_token: Twitter API v2 Bearer Token (or will load from TWITTER_BEARER_TOKEN env var)
            use_mock: If True, generate mock data instead of real API calls
        """
        # Load credentials from environment variables if not provided or if placeholder.
        # resolve_credential treats ${...} placeholders and empty values as unset and
        # falls back to the named env var, so both .env and process env work.
        self.bearer_token = resolve_credential(bearer_token, 'TWITTER_BEARER_TOKEN')
        self.use_mock = use_mock
        self.client = None

        if use_mock:
            # Explicit demo/test mode: caller opted in to synthetic data.
            return

        # Production mode (use_mock=False): fail closed rather than fabricating data.
        # 1. Bearer token must be present.
        if is_unset(self.bearer_token):
            raise DataUnavailableError(
                "TwitterFetcher(use_mock=False) requires a real Twitter API bearer token. "
                "Set TWITTER_BEARER_TOKEN in your environment or .env (or pass bearer_token), "
                "or construct with use_mock=True for a demo run."
            )

        # 2. The tweepy client must initialize. If not, we cannot fetch real data --
        #    raise instead of silently switching to mock.
        try:
            import tweepy
        except ImportError as e:
            raise DataUnavailableError(
                "TwitterFetcher(use_mock=False) requires the 'tweepy' package. "
                "Install it with: pip install tweepy"
            ) from e

        try:
            self.client = tweepy.Client(bearer_token=self.bearer_token, wait_on_rate_limit=True)
            logger.info("Twitter API client initialized successfully.")
        except Exception as e:
            self.client = None
            raise DataUnavailableError(
                f"TwitterFetcher(use_mock=False): failed to initialize the Twitter client: {e}. "
                f"Check the bearer token and network; refusing to fall back to mock data."
            ) from e

    def fetch_tweets_for_event(self, ticker: str, event_date: datetime,
                                 keywords: Optional[List[str]] = None,
                                 days_before: int = 10,
                                 days_after: int = 3,
                                 max_results: int = 100) -> pd.DataFrame:
        """
        Fetch tweets related to a ticker around an event date

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            event_date: Date of the ESG event
            keywords: Additional ESG keywords to search (optional)
            days_before: Days before event to collect data
            days_after: Days after event to collect data
            max_results: Maximum number of tweets to retrieve

        Returns:
            DataFrame with columns: [timestamp, text, user_followers, retweets, likes, ticker]
        """
        if self.use_mock:
            mock_df = self._generate_mock_tweets(ticker, event_date, days_before, days_after, max_results)
            return tag(mock_df, MOCK, source='twitter')

        # Build search query
        query = self._build_search_query(ticker, keywords)

        # Calculate date range
        start_time = event_date - timedelta(days=days_before)
        end_time = event_date + timedelta(days=days_after)

        try:
            tweets_data = []

            # Search tweets using Twitter API v2
            tweets = self.client.search_recent_tweets(
                query=query,
                start_time=start_time,
                end_time=end_time,
                max_results=min(max_results, 100),  # API limit is 100 per request
                tweet_fields=['created_at', 'public_metrics', 'author_id'],
                user_fields=['public_metrics'],
                expansions=['author_id']
            )

            if tweets.data is None:
                logger.warning("No tweets found for %s around %s", ticker, event_date)
                empty_df = pd.DataFrame(columns=['timestamp', 'text', 'user_followers', 'retweets', 'likes', 'ticker'])
                return tag(empty_df, EMPTY, source='twitter')

            # Create user lookup dictionary
            users = {user.id: user for user in tweets.includes.get('users', [])}

            # Extract tweet data
            for tweet in tweets.data:
                user = users.get(tweet.author_id)
                tweets_data.append({
                    'timestamp': tweet.created_at,
                    'text': tweet.text,
                    'user_followers': user.public_metrics['followers_count'] if user else 0,
                    'retweets': tweet.public_metrics['retweet_count'],
                    'likes': tweet.public_metrics['like_count'],
                    'ticker': ticker
                })

            df = pd.DataFrame(tweets_data)
            logger.info("Fetched %d tweets for %s", len(df), ticker)

            return tag(df, REAL, source='twitter')

        except Exception as e:
            # SOFT no-data: a per-event fetch failure must NOT fabricate rows on a
            # production run. Return an EMPTY tagged frame and warn so the caller can
            # skip this event; the orchestrator guard handles aborting if needed.
            logger.warning(
                "Error fetching tweets for %s around %s: %s. "
                "Returning empty result (no mock fallback).", ticker, event_date, e
            )
            empty_df = pd.DataFrame(columns=['timestamp', 'text', 'user_followers', 'retweets', 'likes', 'ticker'])
            return tag(empty_df, EMPTY, source='twitter')

    def fetch_tweets_batch(self, tickers: List[str], event_dates: Dict[str, datetime],
                            keywords: Optional[List[str]] = None,
                            days_before: int = 10,
                            days_after: int = 3,
                            max_results_per_ticker: int = 100) -> Dict[str, pd.DataFrame]:
        """
        Fetch tweets for multiple tickers/events

        Args:
            tickers: List of stock ticker symbols
            event_dates: Dictionary mapping ticker to event date
            keywords: Additional ESG keywords
            days_before: Days before event
            days_after: Days after event
            max_results_per_ticker: Max tweets per ticker

        Returns:
            Dictionary mapping ticker to DataFrame of tweets
        """
        results = {}

        for ticker in tickers:
            event_date = event_dates.get(ticker)
            if event_date is None:
                print(f"Warning: No event date for {ticker}, skipping.")
                continue

            print(f"Fetching tweets for {ticker}...")
            df = self.fetch_tweets_for_event(
                ticker=ticker,
                event_date=event_date,
                keywords=keywords,
                days_before=days_before,
                days_after=days_after,
                max_results=max_results_per_ticker
            )

            results[ticker] = df

            # Rate limiting - be nice to the API
            if not self.use_mock:
                time.sleep(1)

        return results

    def _build_search_query(self, ticker: str, keywords: Optional[List[str]] = None) -> str:
        """
        Build Twitter search query

        Args:
            ticker: Stock ticker
            keywords: Additional keywords

        Returns:
            Search query string
        """
        # Start with ticker and stock symbol
        query_parts = [f"(${ticker} OR #{ticker})"]

        # Add ESG keywords if provided
        if keywords:
            keyword_str = " OR ".join(keywords)
            query_parts.append(f"({keyword_str})")

        # Exclude retweets to get original content
        query = " ".join(query_parts) + " -is:retweet lang:en"

        return query

    def _generate_mock_tweets(self, ticker: str, event_date: datetime,
                               days_before: int = 10, days_after: int = 3,
                               n_tweets: int = 100) -> pd.DataFrame:
        """
        Generate realistic mock Twitter data for testing

        Args:
            ticker: Stock ticker
            event_date: Event date
            days_before: Days before event
            days_after: Days after event
            n_tweets: Number of tweets to generate

        Returns:
            DataFrame with mock tweet data
        """
        # Local deterministic RNG keyed on ticker (no global np.random.seed mutation,
        # stable across processes). Only reachable when use_mock=True.
        rng = np.random.default_rng(zlib.crc32(str(ticker).encode()))

        # Generate timestamps with more activity post-event
        start_date = event_date - timedelta(days=days_before)
        end_date = event_date + timedelta(days=days_after)

        # Create non-uniform distribution (more tweets after event)
        pre_event_tweets = int(n_tweets * 0.3)
        post_event_tweets = n_tweets - pre_event_tweets

        pre_timestamps = pd.date_range(start=start_date, end=event_date, periods=pre_event_tweets)
        post_timestamps = pd.date_range(start=event_date, end=end_date, periods=post_event_tweets)
        timestamps = list(pre_timestamps) + list(post_timestamps)

        # Generate realistic tweet texts with ESG themes
        esg_templates = {
            'environmental': [
                f"${ticker} faces scrutiny over carbon emissions #ESG #climate",
                f"Breaking: ${ticker} environmental violations reported",
                f"${ticker} sustainability report raises concerns",
                f"${ticker} criticized for environmental impact",
                f"${ticker} pollution incident under investigation"
            ],
            'social': [
                f"${ticker} labor practices questioned by workers",
                f"${ticker} facing allegations of workplace issues",
                f"${ticker} diversity report disappoints investors",
                f"${ticker} employee safety concerns emerge",
                f"${ticker} criticized for supply chain practices"
            ],
            'governance': [
                f"${ticker} board composition raises red flags",
                f"${ticker} executive compensation under fire",
                f"${ticker} transparency issues concern shareholders",
                f"${ticker} corporate governance questioned",
                f"${ticker} faces regulatory compliance issues"
            ],
            'positive': [
                f"${ticker} announces green initiative #sustainability",
                f"${ticker} improves ESG rating",
                f"${ticker} recognized for social responsibility"
            ]
        }

        # Mix of negative and some positive tweets
        all_templates = (
            esg_templates['environmental'] * 10 +
            esg_templates['social'] * 10 +
            esg_templates['governance'] * 10 +
            esg_templates['positive'] * 3
        )

        texts = rng.choice(all_templates, n_tweets)

        # Generate realistic engagement metrics
        # Followers: log-normal distribution (most users have few followers, some have many)
        user_followers = rng.lognormal(mean=7, sigma=2, size=n_tweets).astype(int)
        user_followers = np.clip(user_followers, 10, 1000000)

        # Retweets and likes: influenced by follower count
        base_retweets = rng.poisson(lam=5, size=n_tweets)
        follower_boost = (np.log10(user_followers) / 3).astype(int)
        retweets = base_retweets + follower_boost

        likes = retweets * rng.uniform(2, 5, n_tweets)

        # Create DataFrame
        mock_data = pd.DataFrame({
            'timestamp': timestamps,
            'text': texts,
            'user_followers': user_followers,
            'retweets': retweets.astype(int),
            'likes': likes.astype(int),
            'ticker': ticker
        })

        return mock_data

    def get_trending_esg_hashtags(self, location_id: int = 1) -> List[str]:
        """
        Get trending ESG-related hashtags

        Args:
            location_id: WOEID location ID (1 = worldwide)

        Returns:
            List of trending hashtags
        """
        if self.use_mock:
            return ['#ESG', '#climate', '#sustainability', '#corporategovernance']

        try:
            # Note: Trends endpoint requires elevated access in API v2
            print("Note: Trends endpoint requires Twitter API elevated access")
            return ['#ESG', '#climate', '#sustainability']
        except Exception as e:
            print(f"Error fetching trends: {e}")
            return ['#ESG', '#climate', '#sustainability']
