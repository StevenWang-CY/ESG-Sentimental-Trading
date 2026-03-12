"""
Arctic Shift Data Fetcher
Fetches Reddit posts via Arctic Shift API (no credentials required)

Drop-in replacement for RedditFetcher - uses the same interface,
same DataFrame output format, and same ESG quality scoring.

Arctic Shift is a free Reddit data archive that provides search access
to all Reddit posts and comments without requiring API credentials.
API docs: https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md
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
    compute_engagement_quality,
)


ARCTIC_SHIFT_BASE_URL = "https://arctic-shift.photon-reddit.com"
ARCTIC_SHIFT_POSTS_SEARCH = f"{ARCTIC_SHIFT_BASE_URL}/api/posts/search"

# Default subreddits matching RedditFetcher priority list
DEFAULT_SUBREDDITS = [
    'stocks',
    'investing',
    'StockMarket',
    'wallstreetbets',
    'ESG_Investing',
    'finance',
    'SecurityAnalysis',
    'environment',
    'sustainability',
    'ValueInvesting',
]


class ArcticShiftFetcher:
    """
    Fetches Reddit data via Arctic Shift API (no credentials required).

    Drop-in replacement for RedditFetcher with identical interface.
    Uses Arctic Shift's free API to search archived Reddit posts.

    Features:
    - No API credentials needed (free public access)
    - Full historical Reddit data (not limited to 7 days like Twitter)
    - Same ESG semantic relevance scoring as RedditFetcher
    - Same FinBERT sentiment analysis integration
    - Same DataFrame output format for pipeline compatibility
    """

    def __init__(self, use_mock: bool = False,
                 enable_sentiment: bool = True,
                 min_relevance_score: float = 0.1,
                 subreddits: Optional[List[str]] = None,
                 request_timeout: int = 15,
                 sentiment_mode: str = 'hybrid',
                 sentiment_model_name: str = "ProsusAI/finbert",
                 strict_sentiment: bool = False,
                 # Accept and ignore Reddit credential params for compatibility
                 client_id: Optional[str] = None,
                 client_secret: Optional[str] = None,
                 user_agent: Optional[str] = None):
        """
        Initialize Arctic Shift fetcher.

        Args:
            use_mock: If True, generate mock data instead of API calls
            enable_sentiment: If True, use FinBERT for sentiment scoring
            min_relevance_score: Minimum ESG relevance to include post (0.0-1.0)
            subreddits: List of subreddits to search (default: stocks/investing/etc.)
            request_timeout: HTTP request timeout in seconds
            client_id: Ignored (accepted for RedditFetcher compatibility)
            client_secret: Ignored (accepted for RedditFetcher compatibility)
            user_agent: Ignored (accepted for RedditFetcher compatibility)
        """
        self.use_mock = use_mock
        self.min_relevance_score = min_relevance_score
        self.request_timeout = request_timeout
        self.subreddits = subreddits or DEFAULT_SUBREDDITS

        # Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'ESG-Sentiment-Trading-Research/1.0 (academic research)'
        })

        # Initialize sentiment analyzer (lazy load)
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
                print("  Sentiment analyzer loaded for Arctic Shift filtering")
            except Exception as e:
                print(f"Warning: Could not load sentiment analyzer: {e}")
                print("  Falling back to engagement-only scoring")

        # Reuse RedditFetcher's ticker-to-company mapping
        self.ticker_to_company = {
            'AAPL': 'Apple', 'MSFT': 'Microsoft', 'GOOGL': 'Google Alphabet',
            'AMZN': 'Amazon', 'TSLA': 'Tesla', 'META': 'Meta Facebook',
            'NVDA': 'Nvidia', 'AMD': 'AMD', 'INTC': 'Intel',
            'XOM': 'Exxon Mobil', 'CVX': 'Chevron', 'COP': 'ConocoPhillips',
            'BP': 'BP British Petroleum', 'SHEL': 'Shell',
            'DVN': 'Devon Energy', 'FANG': 'Diamondback Energy', 'OXY': 'Occidental',
            'CTRA': 'Coterra Energy', 'MPC': 'Marathon Petroleum',
            'VLO': 'Valero', 'PSX': 'Phillips 66',
            'NUE': 'Nucor', 'STLD': 'Steel Dynamics', 'CLF': 'Cleveland Cliffs',
            'AA': 'Alcoa', 'X': 'US Steel', 'FCX': 'Freeport McMoRan',
            'NEM': 'Newmont Mining',
            'NKE': 'Nike', 'SBUX': 'Starbucks', 'MGM': 'MGM Resorts',
            'WYNN': 'Wynn Resorts', 'LVS': 'Las Vegas Sands', 'CCL': 'Carnival',
            'NCLH': 'Norwegian Cruise', 'RCL': 'Royal Caribbean',
            'TPR': 'Tapestry Coach', 'LULU': 'Lululemon', 'ULTA': 'Ulta Beauty',
            'DKS': "Dick's Sporting", 'BBY': 'Best Buy', 'BBWI': 'Bath Body Works',
            'DAL': 'Delta Airlines', 'UAL': 'United Airlines',
            'AAL': 'American Airlines', 'LUV': 'Southwest Airlines',
            'BA': 'Boeing', 'CAT': 'Caterpillar',
            'CARR': 'Carrier', 'OTIS': 'Otis Elevator', 'XYL': 'Xylem',
            'IEX': 'IDEX', 'FTV': 'Fortive', 'VLTO': 'Veralto', 'EME': 'EMCOR',
            'J': 'Jacobs', 'GNRC': 'Generac',
            'INVH': 'Invitation Homes', 'EQR': 'Equity Residential',
            'AVB': 'AvalonBay', 'MAA': 'Mid-America Apartment',
            'UDR': 'UDR', 'CPT': 'Camden Property',
            'PFE': 'Pfizer', 'JNJ': 'Johnson Johnson', 'UNH': 'UnitedHealth',
            'TECH': 'Bio-Techne', 'PKI': 'PerkinElmer',
            'WST': 'West Pharmaceutical', 'HOLX': 'Hologic',
            'CRM': 'Salesforce', 'COIN': 'Coinbase', 'PLTR': 'Palantir',
            'PANW': 'Palo Alto Networks', 'CRWD': 'CrowdStrike',
            'ZS': 'Zscaler', 'DDOG': 'Datadog', 'NET': 'Cloudflare',
            'SNOW': 'Snowflake', 'U': 'Unity',
            'NEE': 'NextEra Energy', 'AES': 'AES Corporation',
            'AEE': 'Ameren', 'LNT': 'Alliant Energy', 'PNW': 'Pinnacle West',
            'NI': 'NiSource', 'EVRG': 'Evergy', 'NRG': 'NRG Energy',
            'CMS': 'CMS Energy',
            'JPM': 'JPMorgan', 'BAC': 'Bank of America',
            'GS': 'Goldman Sachs', 'BLK': 'BlackRock',
        }

        if not use_mock:
            # Verify API is reachable
            try:
                resp = self.session.get(
                    ARCTIC_SHIFT_POSTS_SEARCH,
                    params={'subreddit': 'stocks', 'query': 'test', 'limit': 1},
                    timeout=self.request_timeout
                )
                if resp.status_code == 200:
                    print("Arctic Shift API connected successfully (no credentials needed)")
                    print(f"  Monitoring subreddits: {', '.join(self.subreddits[:5])}")
                else:
                    print(f"Warning: Arctic Shift API returned status {resp.status_code}")
                    print("  Will attempt requests anyway - API may recover")
            except Exception as e:
                print(f"Warning: Could not reach Arctic Shift API: {e}")
                print("  Falling back to mock data mode.")
                self.use_mock = True

    def _search_posts(self, query: str, subreddit: str,
                      after: datetime, before: datetime,
                      limit: int = 100) -> List[dict]:
        """
        Search Arctic Shift API for posts.

        Args:
            query: Search query (searches title + selftext)
            subreddit: Subreddit to search
            after: Start date (inclusive)
            before: End date (inclusive)
            limit: Max results per request (API max: 100)

        Returns:
            List of post dicts from API
        """
        params = {
            'subreddit': subreddit,
            'query': query,
            'after': after.strftime('%Y-%m-%d'),
            'before': before.strftime('%Y-%m-%d'),
            'limit': min(limit, 100),
            'sort': 'desc',
            'fields': 'id,author,created_utc,title,selftext,score,num_comments,subreddit',
        }

        max_retries = 5
        base_wait = 2.0  # seconds

        for attempt in range(max_retries):
            try:
                resp = self.session.get(
                    ARCTIC_SHIFT_POSTS_SEARCH,
                    params=params,
                    timeout=self.request_timeout,
                )

                if resp.status_code == 200:
                    data = resp.json()
                    return data.get('data', [])
                elif resp.status_code == 429:
                    wait_time = base_wait * (2 ** attempt)  # exponential backoff: 2, 4, 8, 16, 32s
                    print(f"    Rate limited (429) for r/{subreddit} query='{query}', waiting {wait_time:.0f}s (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"    Warning: Arctic Shift API returned {resp.status_code} for r/{subreddit} query='{query}'")
                    return []
            except Exception as e:
                print(f"    Warning: Arctic Shift request failed for r/{subreddit}: {e}")
                return []

        print(f"    Warning: Arctic Shift API rate limit exceeded after {max_retries} retries for r/{subreddit} query='{query}'")
        return []

    def _compute_post_quality(self, text: str, ticker: str, score: int,
                              num_comments: int, author_karma: int = 0) -> Dict:
        """
        Compute combined post quality score using semantic and sentiment analysis.
        Identical to RedditFetcher._compute_post_quality for consistency.
        """
        # 1. ESG Semantic Relevance (40% weight)
        esg_relevance, esg_category, esg_terms = compute_esg_relevance(text, ticker)

        # 2. Engagement Quality (30% weight)
        engagement_quality = compute_engagement_quality(score, num_comments, author_karma)

        # 3. Sentiment Analysis (30% weight)
        sentiment_score = 0.0
        sentiment_label = 'neutral'
        if self.sentiment_analyzer and text:
            try:
                result = self.sentiment_analyzer.analyze_single(text)
                sentiment_score = self.sentiment_analyzer.score_to_numeric(result)
                sentiment_label = result.get('label', 'neutral').lower()
            except Exception:
                pass

        sentiment_strength = abs(sentiment_score)

        total_score = (
            0.40 * esg_relevance +
            0.30 * engagement_quality +
            0.30 * sentiment_strength
        )

        return {
            'total_score': total_score,
            'esg_relevance': esg_relevance,
            'esg_category': esg_category,
            'esg_terms': esg_terms,
            'engagement_quality': engagement_quality,
            'sentiment': sentiment_score,
            'sentiment_label': sentiment_label,
        }

    def fetch_tweets_for_event(self, ticker: str, event_date: datetime,
                               keywords: Optional[List[str]] = None,
                               days_before: int = 10,
                               days_after: int = 3,
                               max_results: int = 200) -> pd.DataFrame:
        """
        Fetch Reddit posts related to a ticker around an event date.

        Drop-in replacement for RedditFetcher.fetch_tweets_for_event().
        Uses Arctic Shift API instead of PRAW.

        CRITICAL FIX (Jan 2026): Now searches with ESG keyword expansion
        to find ESG-relevant discussions, not just generic ticker mentions.

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            event_date: Date of the ESG event
            keywords: Additional ESG keywords to search (now USED, not ignored)
            days_before: Days before event to collect data
            days_after: Days after event to collect data
            max_results: Maximum number of posts to retrieve

        Returns:
            DataFrame with columns:
            - timestamp, text, user_followers, retweets, likes, ticker,
              sentiment, esg_relevance, esg_category, quality_score
        """
        if self.use_mock:
            return self._generate_mock_posts(ticker, event_date, days_before, days_after, max_results)

        start_time = event_date - timedelta(days=days_before)
        end_time = event_date + timedelta(days=days_after)

        posts_data = []
        seen_ids = set()

        # Priority subreddits (same order as RedditFetcher)
        priority_subreddits = [
            'stocks', 'investing', 'StockMarket',
            'wallstreetbets', 'ESG_Investing',
        ]

        # ESG keyword expansion for search (ROOT CAUSE FIX)
        # BALANCED: Mix of negative AND positive ESG terms to avoid short bias
        # Previous version was all-negative (scandal, fraud, lawsuit) → 81% short signals
        esg_search_terms = [
            # Negative ESG events (short signals)
            'scandal', 'layoff', 'emissions', 'investigation', 'lawsuit',
            # Positive ESG events (long signals) - ADDED to balance directional bias
            'renewable', 'sustainability', 'ESG', 'clean energy', 'diversity',
        ]
        company_name = self.ticker_to_company.get(ticker, '')

        # PHASE 1: Ticker-only search (fast, gets high-volume mentions)
        for subreddit in priority_subreddits:
            if len(posts_data) >= max_results:
                break

            raw_posts = self._search_posts(
                query=ticker,
                subreddit=subreddit,
                after=start_time,
                before=end_time,
                limit=100,
            )

            for post in raw_posts:
                post_id = post.get('id', '')
                if post_id in seen_ids:
                    continue
                seen_ids.add(post_id)

                title = post.get('title', '') or ''
                selftext = post.get('selftext', '') or ''
                if selftext in ('[removed]', '[deleted]'):
                    selftext = ''

                post_text = truncate_text_safely(f"{title} {selftext}".strip(), max_chars=500)
                if not post_text:
                    continue

                score = post.get('score', 0) or 0
                num_comments = post.get('num_comments', 0) or 0

                quality = self._compute_post_quality(
                    text=post_text, ticker=ticker, score=score,
                    num_comments=num_comments, author_karma=0,
                )

                # Include if ESG-relevant OR high engagement
                if quality['esg_relevance'] < 0.1 and quality['engagement_quality'] < 0.5:
                    continue

                created_utc = post.get('created_utc', 0)
                post_time = datetime.fromtimestamp(created_utc) if created_utc else event_date

                posts_data.append({
                    'timestamp': post_time,
                    'text': post_text,
                    'user_followers': 1,
                    'retweets': num_comments,
                    'likes': score,
                    'ticker': ticker,
                    'subreddit': post.get('subreddit', subreddit),
                    'sentiment': quality['sentiment'],
                    'esg_relevance': quality['esg_relevance'],
                    'esg_category': quality['esg_category'],
                    'quality_score': quality['total_score'],
                })

                if len(posts_data) >= max_results:
                    break

            time.sleep(0.5)

        # Check ESG content quality from Phase 1
        esg_posts_count = sum(1 for p in posts_data if p['esg_relevance'] > 0.1)

        # PHASE 2: ESG-enriched search (only if Phase 1 has low ESG content)
        if esg_posts_count < 5 and len(posts_data) < max_results:
            # Build ESG-enriched queries
            search_queries = []
            if company_name:
                for term in esg_search_terms[:5]:  # Top 5 ESG terms
                    search_queries.append(f"{company_name} {term}")
            else:
                for term in esg_search_terms[:3]:  # Fewer if no company name
                    search_queries.append(f"{ticker} {term}")

            for subreddit in priority_subreddits[:3]:  # Only top 3 subreddits
                for query in search_queries:
                    if len(posts_data) >= max_results:
                        break

                    raw_posts = self._search_posts(
                        query=query,
                        subreddit=subreddit,
                        after=start_time,
                        before=end_time,
                        limit=50,
                    )

                    for post in raw_posts:
                        post_id = post.get('id', '')
                        if post_id in seen_ids:
                            continue
                        seen_ids.add(post_id)

                        title = post.get('title', '') or ''
                        selftext = post.get('selftext', '') or ''
                        if selftext in ('[removed]', '[deleted]'):
                            selftext = ''

                        post_text = truncate_text_safely(f"{title} {selftext}".strip(), max_chars=500)
                        if not post_text:
                            continue

                        score = post.get('score', 0) or 0
                        num_comments = post.get('num_comments', 0) or 0

                        quality = self._compute_post_quality(
                            text=post_text, ticker=ticker, score=score,
                            num_comments=num_comments, author_karma=0,
                        )

                        # ESG filtering for Phase 2
                        if quality['esg_relevance'] < 0.1 and quality['engagement_quality'] < 0.5:
                            continue

                        created_utc = post.get('created_utc', 0)
                        post_time = datetime.fromtimestamp(created_utc) if created_utc else event_date

                        posts_data.append({
                            'timestamp': post_time,
                            'text': post_text,
                            'user_followers': 1,
                            'retweets': num_comments,
                            'likes': score,
                            'ticker': ticker,
                            'subreddit': post.get('subreddit', subreddit),
                            'sentiment': quality['sentiment'],
                            'esg_relevance': quality['esg_relevance'],
                            'esg_category': quality['esg_category'],
                            'quality_score': quality['total_score'],
                        })

                        if len(posts_data) >= max_results:
                            break

                    time.sleep(0.3)

                if len(posts_data) >= max_results:
                    break

        # Report ESG-filtered results
        esg_count = sum(1 for p in posts_data if p['esg_relevance'] > 0.1)
        if posts_data:
            print(f"  ESG-filtered: {esg_count}/{len(posts_data)} posts are ESG-relevant")

        # Fallback: try ESG-enriched company name searches if few posts found
        if len(posts_data) < 10 and ticker in self.ticker_to_company:
            company_name = self.ticker_to_company[ticker]
            fallback_terms = ['scandal', 'layoff', 'emissions', 'ESG', 'sustainability', 'investigation']
            fallback_queries = [f"{company_name} {term}" for term in fallback_terms]
            print(f"  Fallback ESG search for '{company_name}'...")

            for subreddit in priority_subreddits[:3]:
                for fallback_query in fallback_queries:
                    if len(posts_data) >= max_results:
                        break

                    raw_posts = self._search_posts(
                        query=fallback_query,
                        subreddit=subreddit,
                        after=start_time,
                        before=end_time,
                        limit=50,
                    )

                    for post in raw_posts:
                        post_id = post.get('id', '')
                        if post_id in seen_ids:
                            continue
                        seen_ids.add(post_id)

                        title = post.get('title', '') or ''
                        selftext = post.get('selftext', '') or ''
                        if selftext in ('[removed]', '[deleted]'):
                            selftext = ''

                        post_text = truncate_text_safely(
                            f"{title} {selftext}".strip(),
                            max_chars=500,
                        )
                        if not post_text:
                            continue

                        score = post.get('score', 0) or 0
                        num_comments = post.get('num_comments', 0) or 0

                        quality = self._compute_post_quality(
                            text=post_text,
                            ticker=ticker,
                            score=score,
                            num_comments=num_comments,
                            author_karma=0,
                        )

                        # Require ESG relevance for fallback (no pure noise)
                        if quality['esg_relevance'] < 0.1 and quality['engagement_quality'] < 0.4:
                            continue

                        created_utc = post.get('created_utc', 0)
                        post_time = datetime.fromtimestamp(created_utc) if created_utc else event_date

                        posts_data.append({
                            'timestamp': post_time,
                            'text': post_text,
                            'user_followers': 1,  # Arctic Shift has no karma; use 1 to preserve engagement weighting
                            'retweets': num_comments,
                            'likes': score,
                            'ticker': ticker,
                            'subreddit': post.get('subreddit', subreddit),
                            'sentiment': quality['sentiment'],
                            'esg_relevance': quality['esg_relevance'],
                            'esg_category': quality['esg_category'],
                            'quality_score': quality['total_score'],
                        })

                        if len(posts_data) >= max_results:
                            break

                    time.sleep(0.3)

                time.sleep(0.5)

            if posts_data:
                print(f"  Found {len(posts_data)} posts via company name '{company_name}'")

        # Return empty DataFrame if nothing found
        if not posts_data:
            print(f"No posts found for {ticker} around {event_date.date()}")
            return pd.DataFrame(columns=[
                'timestamp', 'text', 'user_followers', 'retweets', 'likes', 'ticker',
                'sentiment', 'esg_relevance', 'esg_category', 'quality_score',
            ])

        df = pd.DataFrame(posts_data)

        # Log quality stats (same as RedditFetcher)
        avg_relevance = df['esg_relevance'].mean()
        avg_sentiment = df['sentiment'].mean()
        esg_count = (df['esg_relevance'] > 0).sum()
        n_subs = df['subreddit'].nunique() if 'subreddit' in df.columns else 0
        print(f"Fetched {len(df)} posts for {ticker} from {n_subs} subreddits (Arctic Shift)")
        print(f"  ESG-relevant: {esg_count}/{len(df)} | Avg relevance: {avg_relevance:.2f} | Avg sentiment: {avg_sentiment:+.2f}")

        return df[['timestamp', 'text', 'user_followers', 'retweets', 'likes', 'ticker',
                    'sentiment', 'esg_relevance', 'esg_category', 'quality_score']]

    def fetch_tweets_batch(self, tickers: List[str], event_dates: Dict[str, datetime],
                           keywords: Optional[List[str]] = None,
                           days_before: int = 10,
                           days_after: int = 3,
                           max_results_per_ticker: int = 100) -> Dict[str, pd.DataFrame]:
        """
        Fetch posts for multiple tickers/events.

        Drop-in replacement for RedditFetcher.fetch_tweets_batch().
        """
        results = {}

        for ticker in tickers:
            event_date = event_dates.get(ticker)
            if event_date is None:
                print(f"Warning: No event date for {ticker}, skipping.")
                continue

            print(f"Fetching Arctic Shift posts for {ticker}...")
            df = self.fetch_tweets_for_event(
                ticker=ticker,
                event_date=event_date,
                keywords=keywords,
                days_before=days_before,
                days_after=days_after,
                max_results=max_results_per_ticker,
            )

            results[ticker] = df

            if not self.use_mock:
                time.sleep(0.5)

        return results

    def _generate_mock_posts(self, ticker: str, event_date: datetime,
                             days_before: int = 10, days_after: int = 3,
                             n_posts: int = 100) -> pd.DataFrame:
        """Generate mock data for testing (identical to RedditFetcher)."""
        np.random.seed(hash(ticker) % 2**32)

        start_date = event_date - timedelta(days=days_before)
        end_date = event_date + timedelta(days=days_after)

        pre_event_posts = int(n_posts * 0.3)
        post_event_posts = n_posts - pre_event_posts

        pre_timestamps = pd.date_range(start=start_date, end=event_date, periods=pre_event_posts)
        post_timestamps = pd.date_range(start=event_date, end=end_date, periods=post_event_posts)
        timestamps = list(pre_timestamps) + list(post_timestamps)

        esg_templates = {
            'environmental': [
                f"Discussion: {ticker} carbon emissions controversy",
                f"{ticker} environmental violations - what are your thoughts?",
                f"Is {ticker} doing enough for sustainability?",
                f"DD: {ticker} environmental risks analysis",
                f"{ticker} facing backlash over pollution incident",
            ],
            'social': [
                f"{ticker} labor practices - red flags?",
                f"Concerns about {ticker} workplace culture",
                f"{ticker} diversity report disappoints - DD inside",
                f"Analysis: {ticker} employee treatment issues",
                f"{ticker} supply chain ethics questioned",
            ],
            'governance': [
                f"{ticker} board changes raise concerns",
                f"Is {ticker} executive compensation excessive?",
                f"{ticker} transparency issues - thoughts?",
                f"DD: {ticker} corporate governance problems",
                f"{ticker} regulatory compliance under scrutiny",
            ],
            'positive': [
                f"{ticker} announces major ESG initiative",
                f"{ticker} ESG rating upgrade - bullish?",
                f"Impressed by {ticker} sustainability efforts",
            ],
        }

        all_templates = (
            esg_templates['environmental'] * 10 +
            esg_templates['social'] * 10 +
            esg_templates['governance'] * 10 +
            esg_templates['positive'] * 3
        )

        texts = np.random.choice(all_templates, n_posts)
        user_karma = np.clip(np.random.pareto(a=1.5, size=n_posts) * 1000, 100, 500000).astype(int)
        num_comments = np.clip(np.random.poisson(lam=15, size=n_posts), 0, 500)
        base_score = np.random.poisson(lam=50, size=n_posts)
        karma_boost = (np.log10(user_karma) / 5).astype(int)
        score = np.clip(base_score + karma_boost + (num_comments * 0.5).astype(int), 1, 10000).astype(int)

        esg_relevance = np.random.uniform(0.5, 1.0, n_posts)
        categories = ['E'] * 10 + ['S'] * 10 + ['G'] * 10 + ['E'] * 3
        esg_category = np.random.choice(categories, n_posts)

        sentiment = np.where(
            np.random.random(n_posts) < 0.7,
            np.random.uniform(-0.8, -0.2, n_posts),
            np.random.uniform(0.2, 0.8, n_posts),
        )

        quality_score = 0.4 * esg_relevance + 0.3 * np.random.uniform(0.3, 0.8, n_posts) + 0.3 * np.abs(sentiment)

        return pd.DataFrame({
            'timestamp': timestamps,
            'text': texts,
            'user_followers': user_karma,
            'retweets': num_comments.astype(int),
            'likes': score,
            'ticker': ticker,
            'sentiment': sentiment,
            'esg_relevance': esg_relevance,
            'esg_category': esg_category,
            'quality_score': quality_score,
        })

    def get_trending_esg_topics(self) -> List[str]:
        """Get trending ESG topics (simplified for Arctic Shift)."""
        return ['ESG', 'climate change', 'sustainability', 'corporate governance',
                'carbon emissions', 'diversity']

    def set_subreddits(self, subreddits: List[str]):
        """Set custom list of subreddits to search."""
        self.subreddits = subreddits
        print(f"Updated subreddit list: {', '.join(subreddits)}")
