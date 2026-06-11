"""
GDELT News Fetcher
Fetches global news articles via GDELT DOC API (no credentials required)

GDELT (Global Database of Events, Language, and Tone) is a free,
open-access database monitoring global news from 2015+.
It provides article tone/sentiment, source URLs, and full text snippets.

API docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-version-2/
"""

import logging
import zlib

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time
import urllib.parse

from src.data.reddit_fetcher import (
    truncate_text_safely,
    compute_esg_relevance,
)
from src.utils.provenance import REAL, MOCK, EMPTY, tag

logger = logging.getLogger(__name__)

GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"

# Standard output column schema shared by all sentiment/news fetchers.
STANDARD_COLUMNS = [
    'timestamp', 'text', 'user_followers', 'retweets', 'likes', 'ticker',
    'sentiment', 'esg_relevance', 'esg_category', 'quality_score',
]


class GDELTFetcher:
    """
    Fetches news articles via GDELT DOC API (no credentials required).

    Compatible interface with ArcticShiftFetcher/RedditFetcher.
    Returns DataFrames with identical column format.
    """

    def __init__(self, use_mock: bool = False,
                 enable_sentiment: bool = True,
                 request_timeout: int = 30,
                 max_articles: int = 50,
                 sentiment_mode: str = 'hybrid',
                 sentiment_model_name: str = "ProsusAI/finbert",
                 strict_sentiment: bool = False,
                 **kwargs):
        """
        Initialize GDELT fetcher.

        Args:
            use_mock: If True, generate mock data
            enable_sentiment: If True, use FinBERT for sentiment scoring
            request_timeout: HTTP request timeout in seconds
            max_articles: Maximum articles per query
        """
        self.use_mock = use_mock
        self.request_timeout = request_timeout
        self.max_articles = max_articles

        # DATA-06: GDELT artlist mode does not return a per-article numeric
        # 'tone' field, so the tone-based sentiment fallback is unreachable.
        # When the FinBERT analyzer is absent we leave sentiment at a documented
        # neutral 0.0 and emit a single warning (gated by this flag).
        self._tone_fallback_warned = False

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ESG-Sentiment-Trading-Research/1.0'
        })

        self.sentiment_analyzer = None
        self.enable_sentiment = enable_sentiment
        if enable_sentiment:
            try:
                from src.nlp.sentiment_analyzer import FinancialSentimentAnalyzer
                self.sentiment_analyzer = FinancialSentimentAnalyzer(
                    model_name=sentiment_model_name,
                    mode=sentiment_mode,
                    strict=strict_sentiment,
                )
            except Exception:
                pass

        # Ticker to company name mapping for better search
        self.ticker_to_company = {
            'AAPL': 'Apple', 'MSFT': 'Microsoft', 'GOOGL': 'Google',
            'AMZN': 'Amazon', 'TSLA': 'Tesla', 'META': 'Meta',
            'NVDA': 'Nvidia', 'AMD': 'AMD', 'INTC': 'Intel',
            'XOM': 'Exxon', 'CVX': 'Chevron', 'COP': 'ConocoPhillips',
            'BP': 'BP', 'SHEL': 'Shell', 'NKE': 'Nike',
            'SBUX': 'Starbucks', 'CCL': 'Carnival', 'BA': 'Boeing',
            'DAL': 'Delta Airlines', 'LUV': 'Southwest Airlines',
            'JPM': 'JPMorgan', 'BAC': 'Bank of America', 'GS': 'Goldman Sachs',
            'DIS': 'Disney', 'NFLX': 'Netflix', 'ABNB': 'Airbnb',
            'UBER': 'Uber', 'LYFT': 'Lyft', 'RIVN': 'Rivian',
            'F': 'Ford', 'GM': 'General Motors', 'TGT': 'Target',
            'WMT': 'Walmart', 'COST': 'Costco', 'HD': 'Home Depot',
            'PFE': 'Pfizer', 'JNJ': 'Johnson Johnson', 'UNH': 'UnitedHealth',
            'CRM': 'Salesforce', 'COIN': 'Coinbase', 'PLTR': 'Palantir',
            'NEE': 'NextEra Energy', 'BLK': 'BlackRock',
        }

        if not use_mock:
            # A failed/non-200 probe must NOT flip us into mock mode on a
            # production fetch. Log and continue; per-event fetches fail closed
            # on their own by returning EMPTY-stamped frames.
            try:
                test_url = f"{GDELT_DOC_API}?query=test&format=json&maxrecords=1&mode=artlist"
                resp = self.session.get(test_url, timeout=10)
                if resp.status_code == 200:
                    print("GDELT DOC API connected successfully (no credentials needed)")
                else:
                    logger.warning(
                        "GDELT API returned status %s during init probe. "
                        "Continuing in real-data mode; per-event fetches will "
                        "return empty if the API stays unavailable.",
                        resp.status_code
                    )
            except Exception as e:
                logger.warning(
                    "GDELT API unreachable during init probe: %s. Continuing in "
                    "real-data mode; per-event fetches will return empty if the "
                    "API stays unreachable.", e
                )

    def _search_articles(self, query: str, start_date: datetime,
                         end_date: datetime, max_records: int = 50) -> List[Dict]:
        """
        Search GDELT DOC API for news articles.

        Args:
            query: Search query (company name + ESG terms)
            start_date: Start of date range
            end_date: End of date range
            max_records: Maximum number of articles

        Returns:
            List of article dictionaries
        """
        # GDELT date format: YYYYMMDDHHMMSS
        start_str = start_date.strftime('%Y%m%d%H%M%S')
        end_str = end_date.strftime('%Y%m%d%H%M%S')

        params = {
            'query': query,
            'format': 'json',
            'mode': 'artlist',
            'maxrecords': min(max_records, 250),
            'startdatetime': start_str,
            'enddatetime': end_str,
            'sort': 'toneasc',  # Sort by tone to get diverse sentiment
        }

        try:
            resp = self.session.get(
                GDELT_DOC_API,
                params=params,
                timeout=self.request_timeout
            )

            if resp.status_code == 200:
                data = resp.json()
                articles = data.get('articles', [])
                return articles
            else:
                return []
        except Exception as e:
            return []

    def fetch_tweets_for_event(self, ticker: str, event_date: datetime,
                               keywords: Optional[List[str]] = None,
                               days_before: int = 10, days_after: int = 3,
                               max_results: int = 100) -> pd.DataFrame:
        """
        Fetch news articles around an ESG event.

        Compatible interface with ArcticShiftFetcher.

        Args:
            ticker: Stock ticker symbol
            event_date: Date of ESG event
            keywords: ESG keywords (optional)
            days_before: Days before event to search
            days_after: Days after event to search
            max_results: Maximum number of articles

        Returns:
            DataFrame with columns matching ArcticShiftFetcher output
        """
        if self.use_mock:
            # Intentional demo/test mode: synthetic data, loudly stamped MOCK.
            mock_df = self._generate_mock_posts(
                ticker, event_date, days_before, days_after, max_results
            )
            return tag(mock_df, MOCK, source='gdelt_mock')

        start_time = event_date - timedelta(days=days_before)
        end_time = event_date + timedelta(days=days_after)

        posts_data = []
        seen_urls = set()

        company_name = self.ticker_to_company.get(ticker, ticker)

        # ESG search queries - balanced positive/negative
        esg_queries = [
            f'"{company_name}" ESG',
            f'"{company_name}" sustainability',
            f'"{company_name}" emissions climate',
            f'"{company_name}" scandal lawsuit investigation',
            f'"{company_name}" renewable clean energy',
            f'"{company_name}" diversity labor',
        ]

        # Also search by ticker for well-known tickers
        if len(ticker) <= 4 and ticker != company_name:
            esg_queries.append(f'{ticker} stock ESG')

        for query in esg_queries:
            if len(posts_data) >= max_results:
                break

            articles = self._search_articles(
                query=query,
                start_date=start_time,
                end_date=end_time,
                max_records=self.max_articles,
            )

            for article in articles:
                url = article.get('url', '')
                if url in seen_urls:
                    continue
                seen_urls.add(url)

                title = article.get('title', '') or ''
                seendate = article.get('seendate', '')
                domain = article.get('domain', '')
                language = article.get('language', '')
                source_country = article.get('sourcecountry', '')

                # Skip non-English articles
                if language and language.lower() not in ('english', ''):
                    continue

                post_text = truncate_text_safely(title.strip(), max_chars=500)
                if not post_text or len(post_text) < 20:
                    continue

                # Parse date
                try:
                    if seendate:
                        timestamp = datetime.strptime(seendate[:14], '%Y%m%d%H%M%S')
                    else:
                        timestamp = event_date
                except (ValueError, IndexError):
                    timestamp = event_date

                # Compute ESG relevance
                esg_relevance, esg_category, esg_terms = compute_esg_relevance(
                    post_text, ticker
                )

                # Compute sentiment.
                # DATA-06: GDELT's artlist mode does NOT return a per-article
                # numeric 'tone' field (tone is only available in tonechart /
                # timelinevoltone modes), so there is no usable tone-based
                # fallback here. GDELT sentiment therefore REQUIRES the FinBERT
                # analyzer; when it is absent we leave sentiment at a documented
                # neutral 0.0 and warn exactly once.
                sentiment_score = 0.0
                if self.sentiment_analyzer and post_text:
                    try:
                        result = self.sentiment_analyzer.analyze_single(post_text)
                        sentiment_score = self.sentiment_analyzer.score_to_numeric(result)
                    except Exception as e:
                        # Analyzer present but failed on this article: neutral 0.0.
                        logger.warning(
                            "GDELT: sentiment analysis failed for an article "
                            "(%s); using neutral 0.0", e
                        )
                        sentiment_score = 0.0
                elif not self._tone_fallback_warned:
                    logger.warning(
                        "GDELT tone fallback is unavailable in artlist mode "
                        "(no per-article 'tone' field); article sentiment will "
                        "default to neutral 0.0 because the FinBERT analyzer is "
                        "not loaded."
                    )
                    self._tone_fallback_warned = True

                # Quality score based on source domain reputation
                source_quality = 0.5
                high_quality_domains = [
                    'reuters.com', 'bloomberg.com', 'wsj.com', 'ft.com',
                    'cnbc.com', 'bbc.com', 'nytimes.com', 'washingtonpost.com',
                    'theguardian.com', 'apnews.com', 'marketwatch.com',
                ]
                if any(d in (domain or '') for d in high_quality_domains):
                    source_quality = 0.9

                quality_score = 0.4 * esg_relevance + 0.3 * source_quality + 0.3 * abs(sentiment_score)

                posts_data.append({
                    'timestamp': timestamp,
                    'text': post_text,
                    'user_followers': 1,
                    'retweets': 0,
                    'likes': int(source_quality * 100),
                    'ticker': ticker,
                    'sentiment': sentiment_score,
                    'esg_relevance': esg_relevance,
                    'esg_category': esg_category,
                    'quality_score': quality_score,
                    'source': 'gdelt',
                    'domain': domain,
                })

                if len(posts_data) >= max_results:
                    break

            time.sleep(0.5)  # Rate limit: ~2 requests/second

        # SOFT no-data: a real fetch that legitimately returned no articles.
        # Return an EMPTY-stamped frame with the standard schema; never fabricate.
        if not posts_data:
            logger.warning("GDELT: no articles found for %s", ticker)
            empty = pd.DataFrame(columns=STANDARD_COLUMNS)
            return tag(empty, EMPTY, source='gdelt')

        df = pd.DataFrame(posts_data)

        # Log results
        esg_count = (df['esg_relevance'] > 0).sum()
        avg_sentiment = df['sentiment'].mean()
        n_domains = df['domain'].nunique() if 'domain' in df.columns else 0
        print(f"  GDELT: {len(df)} articles from {n_domains} sources for {ticker}")
        print(f"    ESG-relevant: {esg_count}/{len(df)} | Avg sentiment: {avg_sentiment:+.2f}")

        result = df[STANDARD_COLUMNS]
        return tag(result, REAL, source='gdelt')

    def _generate_mock_posts(self, ticker: str, event_date: datetime,
                              days_before: int, days_after: int,
                              max_results: int) -> pd.DataFrame:
        """Generate mock news articles for testing.

        Only reachable when use_mock=True. Uses a LOCAL deterministic generator
        (no global np.random.seed mutation) keyed on ticker+event via crc32.
        """
        rng = np.random.default_rng(zlib.crc32(f"{ticker}_{event_date}".encode()))
        n = min(int(rng.integers(5, 20)), max_results)

        data = []
        for i in range(n):
            offset = int(rng.integers(-days_before, days_after + 1))
            ts = event_date + timedelta(days=offset, hours=int(rng.integers(0, 24)))
            sentiment = rng.uniform(-0.8, 0.8)
            data.append({
                'timestamp': ts,
                'text': f"Mock GDELT article about {ticker} ESG event {i}",
                'user_followers': 1,
                'retweets': 0,
                'likes': int(rng.integers(50, 100)),
                'ticker': ticker,
                'sentiment': round(sentiment, 3),
                'esg_relevance': rng.uniform(0.1, 0.8),
                'esg_category': rng.choice(['E', 'S', 'G']),
                'quality_score': rng.uniform(0.3, 0.9),
            })

        return pd.DataFrame(data)

    def fetch_tweets_batch(self, tickers: List[str], event_dates: Dict[str, datetime],
                           keywords: Optional[List[str]] = None,
                           days_before: int = 10, days_after: int = 3,
                           max_results_per_ticker: int = 50) -> Dict[str, pd.DataFrame]:
        """Fetch articles for multiple tickers."""
        results = {}
        for ticker in tickers:
            if ticker in event_dates:
                results[ticker] = self.fetch_tweets_for_event(
                    ticker, event_dates[ticker], keywords,
                    days_before, days_after, max_results_per_ticker
                )
        return results
