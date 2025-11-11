"""
Reddit Data Fetcher
Fetches Reddit posts related to stock tickers and ESG events using Reddit API (PRAW)
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import time


class RedditFetcher:
    """
    Fetches Reddit data using PRAW (Python Reddit API Wrapper)
    Supports both real API calls and mock data for testing
    Compatible with TwitterFetcher interface for drop-in replacement
    """

    def __init__(self, client_id: Optional[str] = None,
                 client_secret: Optional[str] = None,
                 user_agent: Optional[str] = None,
                 use_mock: bool = False):
        """
        Initialize Reddit fetcher

        Args:
            client_id: Reddit API client ID
            client_secret: Reddit API client secret
            user_agent: User agent string (e.g., "ESG Research Bot 1.0")
            use_mock: If True, generate mock data instead of real API calls
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent or "ESG Sentiment Trading Bot 1.0"
        self.use_mock = use_mock
        self.reddit = None

        # Default subreddits for ESG/stock discussions
        # Note: r/sustainableinvesting removed (returns 404)
        self.esg_subreddits = [
            'stocks',
            'investing',
            'StockMarket',
            'wallstreetbets',
            'ESG_Investing',
            'finance',
            'SecurityAnalysis'
        ]

        if not use_mock and client_id and client_secret:
            try:
                import praw
                self.reddit = praw.Reddit(
                    client_id=client_id,
                    client_secret=client_secret,
                    user_agent=self.user_agent
                )
                print("Reddit API client initialized successfully.")
                # Test connection
                self.reddit.user.me()
                print(f"Connected to Reddit. Monitoring subreddits: {', '.join(self.esg_subreddits[:4])}")
            except ImportError:
                print("Warning: praw not installed. Install with: pip install praw")
                print("Falling back to mock data mode.")
                self.use_mock = True
            except Exception as e:
                print(f"Warning: Failed to initialize Reddit client: {e}")
                print("Falling back to mock data mode.")
                self.use_mock = True
        else:
            if not use_mock:
                print("Warning: No Reddit API credentials provided. Using mock data.")
            self.use_mock = True

    def fetch_tweets_for_event(self, ticker: str, event_date: datetime,
                                 keywords: Optional[List[str]] = None,
                                 days_before: int = 3,
                                 days_after: int = 7,
                                 max_results: int = 100) -> pd.DataFrame:
        """
        Fetch Reddit posts related to a ticker around an event date

        Note: Method name kept as 'fetch_tweets_for_event' for compatibility with TwitterFetcher interface

        Args:
            ticker: Stock ticker symbol (e.g., 'AAPL')
            event_date: Date of the ESG event
            keywords: Additional ESG keywords to search (optional)
            days_before: Days before event to collect data
            days_after: Days after event to collect data
            max_results: Maximum number of posts to retrieve

        Returns:
            DataFrame with columns: [timestamp, text, user_followers, retweets, likes, ticker]
            - user_followers: Post author's total karma
            - retweets: Number of comments (engagement metric)
            - likes: Post score (upvotes - downvotes)
        """
        if self.use_mock:
            return self._generate_mock_posts(ticker, event_date, days_before, days_after, max_results)

        # Build search query
        query = self._build_search_query(ticker, keywords)

        # Calculate date range
        start_time = event_date - timedelta(days=days_before)
        end_time = event_date + timedelta(days=days_after)

        try:
            posts_data = []

            # Search across multiple subreddits
            for subreddit_name in self.esg_subreddits:
                try:
                    subreddit = self.reddit.subreddit(subreddit_name)

                    # Search posts in this subreddit
                    # CRITICAL FIX: Increase limit significantly and sort by 'new' (time)
                    # Reddit's default search sorts by 'relevance' which may miss our date window
                    # Using sort='new' and higher limit increases chance of finding posts in date range
                    search_limit = max(100, max_results // len(self.esg_subreddits) * 10)
                    for submission in subreddit.search(query, limit=search_limit, sort='new', time_filter='all'):
                        # Convert UTC timestamp to datetime
                        post_time = datetime.fromtimestamp(submission.created_utc)

                        # Filter by date range
                        if start_time <= post_time <= end_time:
                            # Get author karma (total karma as proxy for influence)
                            try:
                                author_karma = submission.author.link_karma + submission.author.comment_karma if submission.author else 0
                            except:
                                author_karma = 0

                            posts_data.append({
                                'timestamp': post_time,
                                'text': f"{submission.title} {submission.selftext}"[:500],  # Combine title + body
                                'user_followers': author_karma,  # Use karma as proxy for followers
                                'retweets': submission.num_comments,  # Comments as engagement metric
                                'likes': submission.score,  # Post score (upvotes - downvotes)
                                'ticker': ticker,
                                'subreddit': subreddit_name
                            })

                            if len(posts_data) >= max_results:
                                break

                    if len(posts_data) >= max_results:
                        break

                except Exception as e:
                    print(f"Warning: Error searching r/{subreddit_name}: {e}")
                    continue

            if not posts_data:
                print(f"No Reddit posts found for {ticker} around {event_date}")
                return pd.DataFrame(columns=['timestamp', 'text', 'user_followers', 'retweets', 'likes', 'ticker'])

            df = pd.DataFrame(posts_data)
            print(f"Fetched {len(df)} Reddit posts for {ticker} from {len(df['subreddit'].unique())} subreddits")

            return df[['timestamp', 'text', 'user_followers', 'retweets', 'likes', 'ticker']]

        except Exception as e:
            print(f"Error fetching Reddit posts: {e}")
            print("Falling back to mock data.")
            return self._generate_mock_posts(ticker, event_date, days_before, days_after, max_results)

    def fetch_tweets_batch(self, tickers: List[str], event_dates: Dict[str, datetime],
                            keywords: Optional[List[str]] = None,
                            days_before: int = 3,
                            days_after: int = 7,
                            max_results_per_ticker: int = 100) -> Dict[str, pd.DataFrame]:
        """
        Fetch Reddit posts for multiple tickers/events

        Note: Method name kept as 'fetch_tweets_batch' for compatibility with TwitterFetcher interface

        Args:
            tickers: List of stock ticker symbols
            event_dates: Dictionary mapping ticker to event date
            keywords: Additional ESG keywords
            days_before: Days before event
            days_after: Days after event
            max_results_per_ticker: Max posts per ticker

        Returns:
            Dictionary mapping ticker to DataFrame of posts
        """
        results = {}

        for ticker in tickers:
            event_date = event_dates.get(ticker)
            if event_date is None:
                print(f"Warning: No event date for {ticker}, skipping.")
                continue

            print(f"Fetching Reddit posts for {ticker}...")
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
                time.sleep(2)  # Reddit has generous limits, but still be respectful

        return results

    def _build_search_query(self, ticker: str, keywords: Optional[List[str]] = None) -> str:
        """
        Build Reddit search query

        Args:
            ticker: Stock ticker
            keywords: Additional keywords (IGNORED - too restrictive with ESG terms)

        Returns:
            Search query string

        Note: Previously used "TICKER ESG climate sustainability" which was too restrictive.
              Now uses just the ticker to maximize recall. Reddit's search is limited,
              and requiring ESG keywords filtered out 99% of relevant posts.
              Sentiment analysis will filter for ESG-relevance later.
        """
        # FIXED: Just use ticker name - adding ESG keywords creates AND query that's too restrictive
        # Old approach: "AAPL ESG climate" → only posts mentioning ALL terms
        # New approach: "AAPL" → all posts mentioning ticker, filter by sentiment later
        return ticker

    def _generate_mock_posts(self, ticker: str, event_date: datetime,
                               days_before: int = 3, days_after: int = 7,
                               n_posts: int = 100) -> pd.DataFrame:
        """
        Generate realistic mock Reddit data for testing

        Args:
            ticker: Stock ticker
            event_date: Event date
            days_before: Days before event
            days_after: Days after event
            n_posts: Number of posts to generate

        Returns:
            DataFrame with mock post data
        """
        np.random.seed(hash(ticker) % 2**32)

        # Generate timestamps with more activity post-event
        start_date = event_date - timedelta(days=days_before)
        end_date = event_date + timedelta(days=days_after)

        # Create non-uniform distribution (more posts after event)
        pre_event_posts = int(n_posts * 0.3)
        post_event_posts = n_posts - pre_event_posts

        pre_timestamps = pd.date_range(start=start_date, end=event_date, periods=pre_event_posts)
        post_timestamps = pd.date_range(start=event_date, end=end_date, periods=post_event_posts)
        timestamps = list(pre_timestamps) + list(post_timestamps)

        # Generate realistic Reddit post texts with ESG themes
        esg_templates = {
            'environmental': [
                f"Discussion: {ticker} carbon emissions controversy",
                f"{ticker} environmental violations - what are your thoughts?",
                f"Is {ticker} doing enough for sustainability?",
                f"DD: {ticker} environmental risks analysis",
                f"{ticker} facing backlash over pollution incident"
            ],
            'social': [
                f"{ticker} labor practices - red flags?",
                f"Concerns about {ticker} workplace culture",
                f"{ticker} diversity report disappoints - DD inside",
                f"Analysis: {ticker} employee treatment issues",
                f"{ticker} supply chain ethics questioned"
            ],
            'governance': [
                f"{ticker} board changes raise concerns",
                f"Is {ticker} executive compensation excessive?",
                f"{ticker} transparency issues - thoughts?",
                f"DD: {ticker} corporate governance problems",
                f"{ticker} regulatory compliance under scrutiny"
            ],
            'positive': [
                f"{ticker} announces major ESG initiative",
                f"{ticker} ESG rating upgrade - bullish?",
                f"Impressed by {ticker} sustainability efforts"
            ]
        }

        # Mix of negative and some positive posts (heavier on negative for ESG events)
        all_templates = (
            esg_templates['environmental'] * 10 +
            esg_templates['social'] * 10 +
            esg_templates['governance'] * 10 +
            esg_templates['positive'] * 3
        )

        texts = np.random.choice(all_templates, n_posts)

        # Generate realistic engagement metrics (Reddit-style)
        # Karma: power-law distribution (most users have low karma, some have very high)
        user_karma = np.random.pareto(a=1.5, size=n_posts) * 1000
        user_karma = np.clip(user_karma, 100, 500000).astype(int)

        # Comments: Poisson distribution
        num_comments = np.random.poisson(lam=15, size=n_posts)
        num_comments = np.clip(num_comments, 0, 500)

        # Score (upvotes): correlation with karma and comments
        base_score = np.random.poisson(lam=50, size=n_posts)
        karma_boost = (np.log10(user_karma) / 5).astype(int)
        score = base_score + karma_boost + (num_comments * 0.5).astype(int)
        score = np.clip(score, 1, 10000).astype(int)

        # Create DataFrame matching TwitterFetcher output format
        mock_data = pd.DataFrame({
            'timestamp': timestamps,
            'text': texts,
            'user_followers': user_karma,  # Karma as proxy for followers
            'retweets': num_comments.astype(int),  # Comments as proxy for retweets
            'likes': score,  # Score as proxy for likes
            'ticker': ticker
        })

        return mock_data

    def get_trending_esg_topics(self) -> List[str]:
        """
        Get trending ESG-related topics from relevant subreddits

        Returns:
            List of trending ESG topics/keywords
        """
        if self.use_mock:
            return ['ESG', 'climate change', 'sustainability', 'corporate governance',
                    'carbon emissions', 'diversity']

        try:
            # Get hot posts from ESG subreddits to identify trending topics
            trending_topics = set()

            for sub_name in ['ESG_Investing', 'sustainableinvesting']:
                try:
                    subreddit = self.reddit.subreddit(sub_name)
                    for post in subreddit.hot(limit=10):
                        # Extract keywords from titles (simple approach)
                        words = post.title.lower().split()
                        for word in words:
                            if len(word) > 5:  # Filter short words
                                trending_topics.add(word)
                except:
                    continue

            return list(trending_topics)[:10]

        except Exception as e:
            print(f"Error fetching trending topics: {e}")
            return ['ESG', 'climate', 'sustainability']

    def set_subreddits(self, subreddits: List[str]):
        """
        Set custom list of subreddits to monitor

        Args:
            subreddits: List of subreddit names (without 'r/' prefix)
        """
        self.esg_subreddits = subreddits
        print(f"Updated subreddit list: {', '.join(subreddits)}")
