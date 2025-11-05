"""
Temporal Feature Extractor
Extracts features from time-windowed sentiment data (7-day aggregation based on thesis findings)

Based on research from Savarese (2019) - Politecnico di Torino
Implements temporal indicators as described in the thesis
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta


class TemporalFeatureExtractor:
    """
    Extracts temporal sentiment features using rolling windows
    Implements features from Savarese (2019) thesis
    """

    def __init__(self, window_days: int = 7):
        """
        Initialize temporal feature extractor

        Args:
            window_days: Size of temporal window in days (default 7 from thesis)
        """
        self.window_days = window_days

    def extract_temporal_features(self,
                                  sentiment_data: pd.DataFrame,
                                  event_date: datetime,
                                  date_column: str = 'timestamp',
                                  sentiment_column: str = 'sentiment_score',
                                  text_column: str = 'text') -> Dict[str, float]:
        """
        Extract temporal sentiment features for a specific event

        Features match those from Savarese (2019) thesis:
        - I_1: TPW (Total Positive Words)
        - I_2: TNW (Total Negative Words)
        - I_3: TSPN (Total Single Positive News)
        - I_4: TSNN (Total Single Negative News)
        - I_5: TNN (Total Number of News)
        - I_6: TWN (Total Words in News)
        - I_7: TNWS (Total News With Sentiment - non-neutral)
        - I_8: TNPWWHC (Total Negative Positive Words With Highest Correlation)
        - I_9: TNNWWHC (Total Negative News Words With Highest Correlation)
        - I_10: TNPWWLC (Total Negative Positive Words With Lowest Correlation)
        - I_11: TNNWWLC (Total Negative News Words With Lowest Correlation)

        Args:
            sentiment_data: DataFrame with sentiment data
            event_date: Date of the event (features extracted from window before this)
            date_column: Name of date/timestamp column
            sentiment_column: Name of sentiment score column (-1 to 1)
            text_column: Name of text column

        Returns:
            Dictionary with temporal features
        """
        # Define temporal window (window_days before event_date)
        window_start = event_date - timedelta(days=self.window_days)
        window_end = event_date

        # Filter data to window
        window_data = sentiment_data[
            (sentiment_data[date_column] >= window_start) &
            (sentiment_data[date_column] < window_end)
        ].copy()

        if len(window_data) == 0:
            return self._empty_features()

        # I_5: TNN (Total Number of News/tweets)
        total_news = len(window_data)

        # I_3 & I_4: Count positive and negative news
        # Positive: sentiment > 0.1
        # Negative: sentiment < -0.1
        # Neutral: -0.1 <= sentiment <= 0.1
        positive_news = window_data[window_data[sentiment_column] > 0.1]
        negative_news = window_data[window_data[sentiment_column] < -0.1]

        total_single_positive_news = len(positive_news)  # I_3: TSPN
        total_single_negative_news = len(negative_news)  # I_4: TSNN

        # I_7: TNWS (Total News With Sentiment - non-neutral)
        total_news_with_sentiment = total_single_positive_news + total_single_negative_news

        # I_1 & I_2: Count positive and negative words
        # For simplicity, we approximate using sentiment scores
        # In production, you'd use actual word counts from sentiment analyzer
        total_positive_words = positive_news[sentiment_column].sum() * 100  # I_1: TPW
        total_negative_words = abs(negative_news[sentiment_column].sum()) * 100  # I_2: TNW

        # I_6: TWN (Total Words in News)
        if text_column in window_data.columns:
            total_words_in_news = window_data[text_column].apply(
                lambda x: len(str(x).split()) if pd.notna(x) else 0
            ).sum()
        else:
            # Estimate based on average tweet length (140 chars ≈ 20 words)
            total_words_in_news = total_news * 20

        # Features I_8-I_11 require word correlation analyzer
        # These will be computed separately by the correlation analyzer
        # For now, we set them to 0 (will be updated when word correlations available)

        features = {
            # Basic temporal features
            'TNN': float(total_news),  # I_5
            'TSPN': float(total_single_positive_news),  # I_3
            'TSNN': float(total_single_negative_news),  # I_4
            'TNWS': float(total_news_with_sentiment),  # I_7
            'TPW': float(total_positive_words),  # I_1
            'TNW': float(total_negative_words),  # I_2
            'TWN': float(total_words_in_news),  # I_6

            # Ratios and derived features
            'sentiment_ratio': total_single_positive_news / max(total_single_negative_news, 1),
            'sentiment_coverage': total_news_with_sentiment / max(total_news, 1),

            # Average sentiment in window
            'avg_sentiment': window_data[sentiment_column].mean(),
            'std_sentiment': window_data[sentiment_column].std(),
            'max_sentiment': window_data[sentiment_column].max(),
            'min_sentiment': window_data[sentiment_column].min(),

            # Temporal dynamics
            'sentiment_trend': self._calculate_trend(window_data, sentiment_column),
            'sentiment_acceleration': self._calculate_acceleration(window_data, sentiment_column),

            # Volume metrics
            'daily_avg_volume': total_news / self.window_days,
            'volume_concentration': self._calculate_volume_concentration(window_data, date_column),

            # Placeholders for word correlation features (I_8-I_11)
            'TNPWWHC': 0.0,  # I_8 - Updated by word correlation analyzer
            'TNNWWHC': 0.0,  # I_9 - Updated by word correlation analyzer
            'TNPWWLC': 0.0,  # I_10 - Updated by word correlation analyzer
            'TNNWWLC': 0.0,  # I_11 - Updated by word correlation analyzer
        }

        return features

    def extract_temporal_features_with_word_correlations(self,
                                                         sentiment_data: pd.DataFrame,
                                                         event_date: datetime,
                                                         word_correlation_analyzer,
                                                         date_column: str = 'timestamp',
                                                         sentiment_column: str = 'sentiment_score',
                                                         text_column: str = 'text') -> Dict[str, float]:
        """
        Extract temporal features including word correlation features (I_8-I_11)

        Args:
            sentiment_data: DataFrame with sentiment data
            event_date: Date of the event
            word_correlation_analyzer: Instance of WordCorrelationAnalyzer
            date_column: Name of date column
            sentiment_column: Name of sentiment column
            text_column: Name of text column

        Returns:
            Dictionary with all temporal features including word correlations
        """
        # Get base temporal features
        features = self.extract_temporal_features(
            sentiment_data,
            event_date,
            date_column,
            sentiment_column,
            text_column
        )

        # Add word correlation features if text column available
        if text_column not in sentiment_data.columns:
            return features

        # Define temporal window
        window_start = event_date - timedelta(days=self.window_days)
        window_end = event_date

        window_data = sentiment_data[
            (sentiment_data[date_column] >= window_start) &
            (sentiment_data[date_column] < window_end)
        ].copy()

        if len(window_data) == 0:
            return features

        # Get best and worst words from correlation analyzer
        best_words = set(word_correlation_analyzer.best_words)
        worst_words = set(word_correlation_analyzer.worst_words)

        # Count correlation words in each document
        positive_best_word_count = 0  # Best words in positive sentiment news
        negative_best_word_count = 0  # Best words in negative sentiment news
        positive_worst_word_count = 0  # Worst words in positive sentiment news
        negative_worst_word_count = 0  # Worst words in negative sentiment news

        for idx, row in window_data.iterrows():
            text = str(row[text_column])
            sentiment = row[sentiment_column]

            # Extract words
            words = word_correlation_analyzer.extract_words(text)
            word_set = set(words)

            # Count best and worst words
            n_best = len(word_set & best_words)
            n_worst = len(word_set & worst_words)

            # Classify by sentiment
            if sentiment > 0.1:  # Positive news
                positive_best_word_count += n_best
                positive_worst_word_count += n_worst
            elif sentiment < -0.1:  # Negative news
                negative_best_word_count += n_best
                negative_worst_word_count += n_worst

        # I_8: TNPWWHC - Total number of positive words (high correlation) in news
        # Interpretation: Best words appearing in positive sentiment news
        features['TNPWWHC'] = float(positive_best_word_count)

        # I_9: TNNWWHC - Total number of negative words (high correlation) in news
        # Interpretation: Worst words appearing in negative sentiment news
        features['TNNWWHC'] = float(negative_worst_word_count)

        # I_10: TNPWWLC - Total number of positive words (low/negative correlation) in news
        # Interpretation: Worst words appearing in positive sentiment news (contrarian signal)
        features['TNPWWLC'] = float(positive_worst_word_count)

        # I_11: TNNWWLC - Total number of negative words (low/negative correlation) in news
        # Interpretation: Best words appearing in negative sentiment news (contrarian signal)
        features['TNNWWLC'] = float(negative_best_word_count)

        return features

    def _empty_features(self) -> Dict[str, float]:
        """Return empty feature dictionary with all features set to 0"""
        return {
            'TNN': 0.0, 'TSPN': 0.0, 'TSNN': 0.0, 'TNWS': 0.0,
            'TPW': 0.0, 'TNW': 0.0, 'TWN': 0.0,
            'sentiment_ratio': 1.0, 'sentiment_coverage': 0.0,
            'avg_sentiment': 0.0, 'std_sentiment': 0.0,
            'max_sentiment': 0.0, 'min_sentiment': 0.0,
            'sentiment_trend': 0.0, 'sentiment_acceleration': 0.0,
            'daily_avg_volume': 0.0, 'volume_concentration': 0.0,
            'TNPWWHC': 0.0, 'TNNWWHC': 0.0, 'TNPWWLC': 0.0, 'TNNWWLC': 0.0
        }

    def _calculate_trend(self, data: pd.DataFrame, value_column: str) -> float:
        """
        Calculate trend (slope) of sentiment over time window

        Args:
            data: DataFrame with time series data
            value_column: Column to calculate trend for

        Returns:
            Trend coefficient (positive = increasing, negative = decreasing)
        """
        if len(data) < 2:
            return 0.0

        # Sort by date
        data = data.sort_values('timestamp').reset_index(drop=True)

        # Simple linear regression: y = mx + b
        x = np.arange(len(data))
        y = data[value_column].values

        # Remove NaN values
        mask = ~np.isnan(y)
        x = x[mask]
        y = y[mask]

        if len(x) < 2:
            return 0.0

        # Calculate slope
        try:
            slope = np.polyfit(x, y, 1)[0]
            return float(slope)
        except:
            return 0.0

    def _calculate_acceleration(self, data: pd.DataFrame, value_column: str) -> float:
        """
        Calculate acceleration (second derivative) of sentiment

        Args:
            data: DataFrame with time series data
            value_column: Column to calculate acceleration for

        Returns:
            Acceleration coefficient
        """
        if len(data) < 3:
            return 0.0

        # Sort by date
        data = data.sort_values('timestamp').reset_index(drop=True)

        # Calculate first differences
        values = data[value_column].values
        first_diff = np.diff(values)

        # Calculate second differences (acceleration)
        second_diff = np.diff(first_diff)

        # Return mean acceleration
        return float(np.mean(second_diff)) if len(second_diff) > 0 else 0.0

    def _calculate_volume_concentration(self, data: pd.DataFrame, date_column: str) -> float:
        """
        Calculate how concentrated volume is (1 = all on one day, 0 = evenly distributed)

        Args:
            data: DataFrame with time series data
            date_column: Name of date column

        Returns:
            Volume concentration metric (0-1)
        """
        if len(data) < 2:
            return 1.0

        # Count posts per day
        daily_counts = data.groupby(data[date_column].dt.date).size()

        if len(daily_counts) < 2:
            return 1.0

        # Calculate Herfindahl index (concentration measure)
        proportions = daily_counts / daily_counts.sum()
        herfindahl = (proportions ** 2).sum()

        # Normalize: (H - 1/n) / (1 - 1/n)
        n = len(daily_counts)
        min_h = 1.0 / n
        normalized = (herfindahl - min_h) / (1.0 - min_h) if n > 1 else 0.0

        return float(normalized)

    def extract_features_batch(self,
                               sentiment_data: pd.DataFrame,
                               events: pd.DataFrame,
                               ticker_column: str = 'ticker',
                               date_column: str = 'date') -> pd.DataFrame:
        """
        Extract temporal features for a batch of events

        Args:
            sentiment_data: DataFrame with sentiment data (timestamp, ticker, text, sentiment_score)
            events: DataFrame with events (ticker, date)
            ticker_column: Name of ticker column
            date_column: Name of date column

        Returns:
            DataFrame with events and their temporal features
        """
        results = []

        for idx, event in events.iterrows():
            ticker = event[ticker_column]
            event_date = event[date_column]

            # Filter sentiment data for this ticker
            ticker_data = sentiment_data[sentiment_data['ticker'] == ticker]

            # Extract features
            features = self.extract_temporal_features(
                ticker_data,
                event_date
            )

            # Combine event info with features
            result = {
                'ticker': ticker,
                'date': event_date,
                **features
            }

            results.append(result)

        return pd.DataFrame(results)

    def get_feature_names(self) -> List[str]:
        """
        Get list of all temporal feature names

        Returns:
            List of feature names
        """
        return [
            # Core temporal indicators (from thesis)
            'TNN', 'TSPN', 'TSNN', 'TNWS', 'TPW', 'TNW', 'TWN',
            'TNPWWHC', 'TNNWWHC', 'TNPWWLC', 'TNNWWLC',

            # Derived features
            'sentiment_ratio', 'sentiment_coverage',
            'avg_sentiment', 'std_sentiment', 'max_sentiment', 'min_sentiment',
            'sentiment_trend', 'sentiment_acceleration',
            'daily_avg_volume', 'volume_concentration'
        ]

    def get_thesis_feature_names(self) -> List[str]:
        """
        Get the 11 core temporal indicator features from the thesis

        Returns:
            List of 11 feature names matching thesis notation
        """
        return [
            'TPW',      # I_1
            'TNW',      # I_2
            'TSPN',     # I_3
            'TSNN',     # I_4
            'TNN',      # I_5
            'TWN',      # I_6
            'TNWS',     # I_7
            'TNPWWHC',  # I_8
            'TNNWWHC',  # I_9
            'TNPWWLC',  # I_10
            'TNNWWLC'   # I_11
        ]
