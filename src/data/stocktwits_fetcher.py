"""
StockTwits Fetcher
Fetches stock-related social media posts via StockTwits public API (no API key required)

StockTwits is a social network for investors/traders with built-in bullish/bearish sentiment.
Free API provides recent messages per symbol with native sentiment labels.

API: https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json
Limitations:
  - No date-range filtering (returns most recent messages only)
  - Rate limit: ~200 requests/hour unauthenticated
  - Max 30 messages per request, can paginate backward with 'max' parameter
  - For backtesting, best combined with historical sources (Arctic Shift, GDELT)
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time

from src.data.reddit_fetcher import (
    truncate_text_safely,
    compute_esg_relevance,
)

STOCKTWITS_API = "https://api.stocktwits.com/api/2/streams/symbol"


class StockTwitsFetcher:
    """
    Fetches stock social messages via StockTwits public API (no API key required).

    Compatible interface with ArcticShiftFetcher/GDELTFetcher.
    Returns DataFrames with identical column format.
    """

    def __init__(self, use_mock: bool = False,
                 enable_sentiment: bool = True,
                 request_timeout: int = 15,
                 max_pages: int = 10,
                 **kwargs):
        """
        Initialize StockTwits fetcher.

        Args:
            use_mock: If True, generate mock data
            enable_sentiment: If True, use FinBERT for sentiment scoring
            request_timeout: HTTP request timeout in seconds
            max_pages: Maximum pages to paginate backward per ticker
        """
        self.use_mock = use_mock
        self.request_timeout = request_timeout
        self.max_pages = max_pages

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ESG-Sentiment-Trading-Research/1.0',
            'Accept': 'application/json',
        })

        self.sentiment_analyzer = None
        self.enable_sentiment = enable_sentiment
        if enable_sentiment:
            try:
                from src.nlp.sentiment_analyzer import FinancialSentimentAnalyzer
                self.sentiment_analyzer = FinancialSentimentAnalyzer()
            except Exception:
                pass

        if not use_mock:
            try:
                test_url = f"{STOCKTWITS_API}/AAPL.json"
                resp = self.session.get(test_url, timeout=10)
                if resp.status_code == 200:
                    print("StockTwits API connected successfully (no credentials needed)")
                elif resp.status_code == 429:
                    print("Warning: StockTwits API rate limited, will retry with backoff")
                else:
                    print(f"Warning: StockTwits API returned status {resp.status_code}")
                    self.use_mock = True
            except Exception as e:
                print(f"Warning: StockTwits API unreachable ({e}), falling back to mock")
                self.use_mock = True

    def _fetch_messages(self, ticker: str, max_id: Optional[int] = None) -> tuple:
        """
        Fetch one page of StockTwits messages for a ticker.

        Args:
            ticker: Stock ticker symbol
            max_id: Return messages with ID less than this (pagination)

        Returns:
            Tuple of (messages list, min_message_id for next page)
        """
        url = f"{STOCKTWITS_API}/{ticker}.json"
        params = {}
        if max_id:
            params['max'] = max_id

        try:
            resp = self.session.get(url, params=params, timeout=self.request_timeout)

            if resp.status_code == 429:
                # Rate limited - wait and retry once
                print(f"    StockTwits rate limited for {ticker}, waiting 60s...")
                time.sleep(60)
                resp = self.session.get(url, params=params, timeout=self.request_timeout)

            if resp.status_code == 200:
                data = resp.json()
                messages = data.get('messages', [])
                # Get the minimum ID for pagination
                min_id = None
                if messages:
                    min_id = min(m.get('id', 0) for m in messages)
                return messages, min_id
            else:
                return [], None
        except Exception:
            return [], None

    def fetch_tweets_for_event(self, ticker: str, event_date: datetime,
                               keywords: Optional[List[str]] = None,
                               days_before: int = 3, days_after: int = 7,
                               max_results: int = 100) -> pd.DataFrame:
        """
        Fetch StockTwits messages around an ESG event.

        Compatible interface with ArcticShiftFetcher.

        Note: StockTwits API only returns recent messages. For historical
        events, this will return empty and the multi-source fetcher will
        rely on other sources (Arctic Shift, GDELT).

        Args:
            ticker: Stock ticker symbol
            event_date: Date of ESG event
            keywords: ESG keywords (optional)
            days_before: Days before event to search
            days_after: Days after event to search
            max_results: Maximum number of messages

        Returns:
            DataFrame with columns matching ArcticShiftFetcher output
        """
        if self.use_mock:
            return self._generate_mock_posts(ticker, event_date, days_before, days_after, max_results)

        start_time = event_date - timedelta(days=days_before)
        end_time = event_date + timedelta(days=days_after)

        posts_data = []
        max_id = None
        pages_fetched = 0
        found_in_range = False
        passed_range = False

        # Paginate backward through messages to find ones in our date range
        while pages_fetched < self.max_pages and len(posts_data) < max_results:
            messages, next_max_id = self._fetch_messages(ticker, max_id)

            if not messages:
                break

            for msg in messages:
                # Parse timestamp
                created_at = msg.get('created_at', '')
                try:
                    # StockTwits format: "2024-07-15T10:30:00Z"
                    timestamp = datetime.strptime(created_at[:19], '%Y-%m-%dT%H:%M:%S')
                except (ValueError, IndexError):
                    continue

                # Check if message is in our date range
                if timestamp < start_time:
                    passed_range = True
                    continue
                if timestamp > end_time:
                    continue

                found_in_range = True

                body = msg.get('body', '') or ''
                post_text = truncate_text_safely(body.strip(), max_chars=500)
                if not post_text or len(post_text) < 10:
                    continue

                # Extract StockTwits native sentiment
                sentiment_data = msg.get('entities', {}).get('sentiment', {})
                st_sentiment = sentiment_data.get('basic', 'Neutral') if sentiment_data else 'Neutral'

                likes_count = 0
                likes_data = msg.get('likes', {})
                if isinstance(likes_data, dict):
                    likes_count = likes_data.get('total', 0) or 0
                elif isinstance(likes_data, (int, float)):
                    likes_count = int(likes_data)

                # Compute sentiment score
                sentiment_score = 0.0
                if self.sentiment_analyzer and post_text:
                    try:
                        result = self.sentiment_analyzer.analyze_single(post_text)
                        sentiment_score = self.sentiment_analyzer.score_to_numeric(result)
                    except Exception:
                        # Fall back to StockTwits native sentiment
                        if st_sentiment == 'Bullish':
                            sentiment_score = 0.5
                        elif st_sentiment == 'Bearish':
                            sentiment_score = -0.5
                elif st_sentiment == 'Bullish':
                    sentiment_score = 0.5
                elif st_sentiment == 'Bearish':
                    sentiment_score = -0.5

                # Compute ESG relevance
                esg_relevance, esg_category, esg_terms = compute_esg_relevance(
                    post_text, ticker
                )

                # Quality score: StockTwits users are retail investors
                engagement = min(likes_count / 20.0, 1.0)  # Normalize likes
                quality_score = 0.3 * esg_relevance + 0.3 * engagement + 0.4 * abs(sentiment_score)

                posts_data.append({
                    'timestamp': timestamp,
                    'text': post_text,
                    'user_followers': 1,
                    'retweets': 0,
                    'likes': likes_count,
                    'ticker': ticker,
                    'sentiment': sentiment_score,
                    'esg_relevance': esg_relevance,
                    'esg_category': esg_category,
                    'quality_score': quality_score,
                    'source': 'stocktwits',
                    'st_sentiment': st_sentiment,
                })

                if len(posts_data) >= max_results:
                    break

            # Stop if we've passed our date range (messages are too old)
            if passed_range:
                break

            # Stop if no more pagination
            if not next_max_id or next_max_id == max_id:
                break

            max_id = next_max_id
            pages_fetched += 1
            time.sleep(1.0)  # Rate limit: ~1 request/second (conservative)

        if not posts_data:
            return pd.DataFrame(columns=[
                'timestamp', 'text', 'user_followers', 'retweets', 'likes', 'ticker',
                'sentiment', 'esg_relevance', 'esg_category', 'quality_score',
            ])

        df = pd.DataFrame(posts_data)

        # Log results
        esg_count = (df['esg_relevance'] > 0).sum()
        avg_sentiment = df['sentiment'].mean()
        bullish = (df.get('st_sentiment', pd.Series()) == 'Bullish').sum() if 'st_sentiment' in df.columns else 0
        bearish = (df.get('st_sentiment', pd.Series()) == 'Bearish').sum() if 'st_sentiment' in df.columns else 0
        print(f"  StockTwits: {len(df)} messages for ${ticker}")
        print(f"    ESG-relevant: {esg_count}/{len(df)} | Avg sentiment: {avg_sentiment:+.2f} | Bullish: {bullish}, Bearish: {bearish}")

        return df[['timestamp', 'text', 'user_followers', 'retweets', 'likes', 'ticker',
                    'sentiment', 'esg_relevance', 'esg_category', 'quality_score']]

    def _generate_mock_posts(self, ticker: str, event_date: datetime,
                              days_before: int, days_after: int,
                              max_results: int) -> pd.DataFrame:
        """Generate mock StockTwits messages for testing."""
        np.random.seed(hash(f"st_{ticker}_{event_date}") % 2**31)
        n = min(np.random.randint(3, 15), max_results)

        data = []
        for i in range(n):
            offset = np.random.randint(-days_before, days_after + 1)
            ts = event_date + timedelta(days=offset, hours=np.random.randint(0, 24))
            sentiment = np.random.uniform(-0.8, 0.8)
            data.append({
                'timestamp': ts,
                'text': f"Mock StockTwits message about ${ticker} ESG event {i}",
                'user_followers': 1,
                'retweets': 0,
                'likes': np.random.randint(0, 30),
                'ticker': ticker,
                'sentiment': round(sentiment, 3),
                'esg_relevance': np.random.uniform(0.1, 0.8),
                'esg_category': np.random.choice(['E', 'S', 'G']),
                'quality_score': np.random.uniform(0.2, 0.7),
            })

        return pd.DataFrame(data)

    def fetch_tweets_batch(self, tickers: List[str], event_dates: Dict[str, datetime],
                           keywords: Optional[List[str]] = None,
                           days_before: int = 3, days_after: int = 7,
                           max_results_per_ticker: int = 50) -> Dict[str, pd.DataFrame]:
        """Fetch messages for multiple tickers."""
        results = {}
        for ticker in tickers:
            if ticker in event_dates:
                results[ticker] = self.fetch_tweets_for_event(
                    ticker, event_dates[ticker], keywords,
                    days_before, days_after, max_results_per_ticker
                )
        return results
