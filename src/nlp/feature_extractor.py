"""
Reaction Feature Extraction
Extracts features from social media and news reactions to ESG events
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional


class ReactionFeatureExtractor:
    """
    Extracts Intensity, Volume, Duration features from sentiment-scored social data
    """

    def __init__(self, sentiment_analyzer):
        """
        Initialize feature extractor

        Args:
            sentiment_analyzer: FinancialSentimentAnalyzer instance
        """
        self.sentiment_analyzer = sentiment_analyzer

    def extract_features(self, tweets_df: pd.DataFrame, event_date: datetime) -> Dict:
        """
        Extract reaction features from social media data

        Args:
            tweets_df: DataFrame with columns [timestamp, text, user_followers, retweets, likes]
            event_date: Reference date for the event

        Returns:
            Dictionary with extracted features
        """
        if tweets_df.empty:
            return self._get_default_features()

        # Make a copy to avoid modifying original
        df = tweets_df.copy()

        # Ensure timestamp column exists and is datetime
        if 'timestamp' not in df.columns:
            print("Warning: No timestamp column found. Using current time.")
            df['timestamp'] = datetime.now()

        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Reuse pre-scored sentiment when fetchers already provide it. Only score
        # missing rows so the canonical runner has one consistent sentiment path.
        if 'sentiment' in df.columns:
            df['sentiment_score'] = pd.to_numeric(df['sentiment'], errors='coerce')
        else:
            df['sentiment_score'] = np.nan

        if df['sentiment_score'].isna().any() and 'text' in df.columns:
            missing_mask = df['sentiment_score'].isna()
            texts = df.loc[missing_mask, 'text'].fillna('').astype(str).tolist()
            sentiments = self.sentiment_analyzer.analyze_batch(texts)
            scored = [self.sentiment_analyzer.score_to_numeric(s) for s in sentiments]
            df.loc[missing_mask, 'sentiment_score'] = scored

        df['sentiment_score'] = df['sentiment_score'].fillna(0.0)

        # Calculate days since event
        df['days_since_event'] = (df['timestamp'] - event_date).dt.total_seconds() / 86400

        # Separate pre and post event data
        # CRITICAL: Cap post-event window at +3 days to prevent look-ahead bias.
        # Academic event study standard: [0, +3] day window (MacKinlay 1997).
        # Even if upstream fetcher provides wider data, we discard it here.
        MAX_POST_EVENT_DAYS = 3
        post_event = df[(df['days_since_event'] >= 0) & (df['days_since_event'] <= MAX_POST_EVENT_DAYS)]
        pre_event = df[df['days_since_event'] < 0]

        # Feature 1: INTENSITY (weighted average sentiment)
        intensity = self._calculate_intensity(post_event)

        # Feature 2: VOLUME (normalized tweet count)
        volume_ratio = self._calculate_volume_ratio(post_event, pre_event)

        # Feature 3: DURATION (days sentiment stays elevated)
        duration_days = self._calculate_duration(post_event)

        # Feature 4: AMPLIFICATION (virality score)
        amplification = self._calculate_amplification(post_event)

        # Feature 5: BASELINE DEVIATION (how unusual is this?)
        baseline_deviation = self._calculate_baseline_deviation(post_event, pre_event)

        # Feature 6: PRE-EVENT SENTIMENT DIRECTION
        # Captures sentiment build-up before the event. If negative buzz
        # precedes a bad ESG filing, this adds directional confirmation.
        pre_event_sentiment = self._calculate_pre_event_sentiment(pre_event)

        return {
            'intensity': intensity,
            'volume_ratio': volume_ratio,
            'duration_days': duration_days,
            'amplification': amplification,
            'baseline_deviation': baseline_deviation,
            'pre_event_sentiment': pre_event_sentiment,
            'n_tweets': len(df),
            'n_pre_event': len(pre_event),
            'n_post_event': len(post_event),
            'sentiment_mode': getattr(self.sentiment_analyzer, 'active_mode', 'unknown'),
        }

    def _calculate_intensity(self, post_event: pd.DataFrame) -> float:
        """Calculate weighted average sentiment intensity.

        Weights combine engagement (virality) and ESG relevance (quality_score)
        so that high-quality ESG posts contribute more to the aggregate
        sentiment, producing stronger intensity for genuine ESG events.
        """
        if post_event.empty:
            return 0.0

        # Calculate virality weight
        if all(col in post_event.columns for col in ['retweets', 'likes', 'user_followers']):
            virality = (
                post_event['retweets'].fillna(0) +
                post_event['likes'].fillna(0) / 10
            ) * np.log1p(post_event['user_followers'].fillna(1))
        else:
            virality = np.ones(len(post_event))

        # Quality boost: amplify posts with higher ESG relevance
        if 'quality_score' in post_event.columns:
            quality = post_event['quality_score'].fillna(0.5)
            weights = (virality + 1) * (quality + 0.5)
        else:
            weights = virality + 1  # Fallback: virality only

        intensity = np.average(
            post_event['sentiment_score'].fillna(0),
            weights=weights
        )

        return float(intensity)

    def _calculate_volume_ratio(self, post_event: pd.DataFrame,
                                pre_event: pd.DataFrame) -> float:
        """Calculate volume ratio (post vs pre event)
        
        FIX Issue #3: Penalize events with insufficient pre-event baseline
        instead of artificially inflating ratio by dividing by 1.
        
        Academic Basis: Volume ratio should be undefined or neutral when 
        baseline is missing (De Gruyter, 2025).
        """
        volume_post = len(post_event)

        if volume_post == 0:
            return 1.0  # No post-event data at all

        if len(pre_event) < 3:
            # Surprise/breakout event: no prior discussion baseline.
            # Use log-scaled post count as volume signal (Tetlock 2007:
            # unexpected news carries the most alpha).
            # 10 posts → 2.4, 50 posts → 3.9 (bounded, monotonic)
            return float(np.log1p(volume_post))

        volume_pre = len(pre_event)
        return volume_post / volume_pre

    def _calculate_duration(self, post_event: pd.DataFrame,
                           threshold: float = 0.2) -> int:
        """Calculate how many days sentiment stays elevated"""
        if post_event.empty or 'timestamp' not in post_event.columns:
            return 0

        # Group by day and calculate average sentiment
        post_event = post_event.copy()
        post_event['date'] = post_event['timestamp'].dt.date
        daily_sentiment = post_event.groupby('date')['sentiment_score'].mean()

        # Count days above threshold
        elevated_days = (daily_sentiment.abs() > threshold).sum()

        return int(elevated_days)

    def _calculate_amplification(self, post_event: pd.DataFrame) -> float:
        """Calculate virality/amplification score"""
        if post_event.empty:
            return 0.0

        if all(col in post_event.columns for col in ['retweets', 'likes', 'user_followers']):
            virality = (
                post_event['retweets'].fillna(0) +
                post_event['likes'].fillna(0) / 10
            ) * np.log1p(post_event['user_followers'].fillna(1))

            amplification = virality.sum() / len(post_event) if len(post_event) > 0 else 0
        else:
            amplification = 1.0

        return float(np.log1p(amplification))

    def _calculate_baseline_deviation(self, post_event: pd.DataFrame,
                                      pre_event: pd.DataFrame) -> float:
        """Calculate z-score of volume change"""
        volume_post = len(post_event)
        volume_pre = len(pre_event)

        if volume_pre == 0:
            return 0.0

        # Simple z-score (assuming std = sqrt(mean) for count data)
        baseline_std = np.sqrt(volume_pre) if volume_pre > 0 else 1
        baseline_deviation = (volume_post - volume_pre) / baseline_std

        return float(baseline_deviation)

    def _calculate_pre_event_sentiment(self, pre_event: pd.DataFrame) -> float:
        """Calculate directional sentiment from pre-event period.

        Captures sentiment build-up before the event. If negative social media
        builds up before a bad ESG filing, this provides directional confirmation.
        Returns 0.0 if fewer than 3 pre-event posts (insufficient data).
        """
        if len(pre_event) < 3:
            return 0.0

        if 'sentiment_score' not in pre_event.columns:
            return 0.0

        return float(pre_event['sentiment_score'].mean())

    def _get_default_features(self) -> Dict:
        """Return default features when no data available"""
        return {
            'intensity': 0.0,
            'volume_ratio': 1.0,
            'duration_days': 0,
            'amplification': 0.0,
            'baseline_deviation': 0.0,
            'pre_event_sentiment': 0.0,
            'n_tweets': 0,
            'n_pre_event': 0,
            'n_post_event': 0,
            'sentiment_mode': getattr(self.sentiment_analyzer, 'active_mode', 'unknown'),
        }

    def create_mock_social_data(self, ticker: str, event_date: datetime,
                               n_tweets: int = 100, sentiment_bias: str = 'negative') -> pd.DataFrame:
        """
        Create mock social media data for testing

        Args:
            ticker: Stock ticker
            event_date: Event date
            n_tweets: Number of tweets to generate
            sentiment_bias: 'positive', 'negative', or 'neutral'

        Returns:
            DataFrame with mock tweet data
        """
        np.random.seed(hash(ticker) % 2**32)

        # Generate timestamps around event date
        start_date = event_date - timedelta(days=2)
        end_date = event_date + timedelta(days=7)

        timestamps = pd.date_range(start=start_date, end=end_date, periods=n_tweets)

        # Generate mock text based on sentiment bias
        sentiment_texts = {
            'positive': [
                f"Great news for ${ticker}! Strong performance.",
                f"${ticker} looking bullish!",
                f"Impressed by ${ticker}'s latest announcement"
            ],
            'negative': [
                f"Concerning news about ${ticker}",
                f"${ticker} facing serious issues",
                f"Not good for ${ticker} shareholders"
            ],
            'neutral': [
                f"${ticker} announced updates",
                f"News about ${ticker}",
                f"${ticker} in the headlines"
            ]
        }

        texts = np.random.choice(sentiment_texts.get(sentiment_bias, sentiment_texts['neutral']), n_tweets)

        # Generate engagement metrics
        mock_data = pd.DataFrame({
            'timestamp': timestamps,
            'text': texts,
            'user_followers': np.random.lognormal(7, 2, n_tweets).astype(int),
            'retweets': np.random.poisson(5, n_tweets),
            'likes': np.random.poisson(20, n_tweets),
            'ticker': ticker
        })

        return mock_data
