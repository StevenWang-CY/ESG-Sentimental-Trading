"""
Enhanced ML Pipeline
Integrates all improvements from Savarese (2019) thesis:
1. Word-level correlation analysis
2. Temporal window features (7-day aggregation)
3. ESG-specific sentiment dictionaries
4. Categorical classification (BUY/SELL/HOLD)
5. Random Forest Classifier
6. Feature selection to avoid curse of dimensionality

This pipeline combines the ESG event detection with advanced NLP and ML techniques
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Import our new modules
from .categorical_classifier import CategoricalSignalClassifier, EnsembleSignalClassifier
from .feature_selector import FeatureSelector, create_optimal_feature_set
from ..nlp.word_correlation_analyzer import WordCorrelationAnalyzer, ESGWordCorrelationAnalyzer
from ..nlp.temporal_feature_extractor import TemporalFeatureExtractor
from ..nlp.esg_sentiment_dictionaries import ESGSentimentDictionaries


class EnhancedESGPipeline:
    """
    End-to-end pipeline for ESG sentiment-based trading
    Implements thesis improvements for better performance
    """

    def __init__(self,
                 model_type: str = 'random_forest',
                 max_features: int = 15,
                 temporal_window_days: int = 7,
                 buy_threshold: float = 0.01,
                 sell_threshold: float = -0.01):
        """
        Initialize enhanced pipeline

        Args:
            model_type: 'random_forest', 'svm', 'mlp', or 'ensemble'
            max_features: Maximum features to use (default 15, close to thesis optimal)
            temporal_window_days: Days of sentiment history to aggregate (default 7 from thesis)
            buy_threshold: Return threshold for BUY signal (default +1%)
            sell_threshold: Return threshold for SELL signal (default -1%)
        """
        self.model_type = model_type
        self.max_features = max_features
        self.temporal_window_days = temporal_window_days
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

        # Initialize components
        self.word_correlation_analyzer = ESGWordCorrelationAnalyzer()
        self.temporal_feature_extractor = TemporalFeatureExtractor(window_days=temporal_window_days)
        self.esg_dictionaries = ESGSentimentDictionaries()
        self.feature_selector = FeatureSelector(max_features=max_features)

        # Classifier (created during training)
        if model_type == 'ensemble':
            self.classifier = EnsembleSignalClassifier(buy_threshold, sell_threshold)
        else:
            self.classifier = CategoricalSignalClassifier(
                model_type, buy_threshold, sell_threshold
            )

        self.is_trained = False

    def extract_all_features(self,
                            events: pd.DataFrame,
                            sentiment_data: pd.DataFrame,
                            text_data: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """
        Extract comprehensive feature set from events and sentiment data

        Args:
            events: DataFrame with columns [date, ticker, event_category, event_confidence]
            sentiment_data: DataFrame with [timestamp, ticker, text, sentiment_score]
            text_data: Optional additional text data for word correlation

        Returns:
            DataFrame with all features
        """
        print("\n" + "="*70)
        print("EXTRACTING FEATURES")
        print("="*70)

        all_features = []

        for idx, event in events.iterrows():
            ticker = event['ticker']
            event_date = event['date']
            event_category = event.get('event_category', 'unknown')
            event_confidence = event.get('event_confidence', 0.5)

            # Filter sentiment data for this ticker
            ticker_sentiment = sentiment_data[sentiment_data['ticker'] == ticker].copy()

            # 1. TEMPORAL FEATURES (7-day window)
            if self.word_correlation_analyzer.word_correlations:
                temporal_features = self.temporal_feature_extractor.extract_temporal_features_with_word_correlations(
                    ticker_sentiment,
                    event_date,
                    self.word_correlation_analyzer
                )
            else:
                temporal_features = self.temporal_feature_extractor.extract_temporal_features(
                    ticker_sentiment,
                    event_date
                )

            # 2. ESG DICTIONARY FEATURES
            window_start = event_date - timedelta(days=self.temporal_window_days)
            window_end = event_date

            window_text = ticker_sentiment[
                (ticker_sentiment['timestamp'] >= window_start) &
                (ticker_sentiment['timestamp'] < window_end)
            ]['text'].tolist()

            aggregated_text = ' '.join([str(t) for t in window_text])

            esg_scores = self.esg_dictionaries.score_text(aggregated_text, category=event_category)

            # 3. WORD CORRELATION FEATURES
            if self.word_correlation_analyzer.word_correlations:
                word_corr_scores = self.word_correlation_analyzer.score_text(aggregated_text)
            else:
                word_corr_scores = {
                    'correlation_score': 0.0,
                    'n_best_words': 0,
                    'n_worst_words': 0
                }

            # 4. EVENT FEATURES
            event_features = {
                'event_confidence': event_confidence,
                'event_category_E': 1 if event_category == 'environmental' else 0,
                'event_category_S': 1 if event_category == 'social' else 0,
                'event_category_G': 1 if event_category == 'governance' else 0,
            }

            combined_features = {
                'ticker': ticker,
                'date': event_date,
                **temporal_features,
                **{f'esg_{k}': v for k, v in esg_scores.items()},
                **{f'word_corr_{k}': v for k, v in word_corr_scores.items()},
                **event_features
            }

            all_features.append(combined_features)

        features_df = pd.DataFrame(all_features)

        print(f"\nExtracted {len(features_df.columns) - 2} features for {len(features_df)} events")

        return features_df

    def train(self,
             events: pd.DataFrame,
             sentiment_data: pd.DataFrame,
             price_data: pd.DataFrame,
             validation_split: float = 0.2,
             use_time_series_cv: bool = True) -> Dict:
        """Train the complete pipeline"""
        print("\n" + "="*70)
        print("ENHANCED ESG PIPELINE - TRAINING")
        print("="*70)

        # Extract features
        features_df = self.extract_all_features(events, sentiment_data)

        # Merge with returns
        features_with_returns = pd.merge(
            features_df,
            price_data[['date', 'ticker', 'return_1d']],
            on=['date', 'ticker'],
            how='inner'
        )

        feature_cols = [c for c in features_with_returns.columns
                       if c not in ['ticker', 'date', 'return_1d']]

        X = features_with_returns[feature_cols]
        y = features_with_returns['return_1d']

        # Feature selection
        selected_features = self.feature_selector.select_ensemble(X, y, min_votes=2)
        X_selected = X[selected_features]

        # Train classifier
        if use_time_series_cv:
            metrics = self.classifier.fit_time_series(X_selected, y, n_splits=5)
        else:
            metrics = self.classifier.fit(X_selected, y, validation_split)

        self.is_trained = True

        return {
            'n_features_selected': len(selected_features),
            'selected_features': selected_features,
            **metrics
        }

    def predict(self, events: pd.DataFrame, sentiment_data: pd.DataFrame) -> pd.DataFrame:
        """Generate trading signals"""
        if not self.is_trained:
            raise ValueError("Pipeline must be trained first")

        features_df = self.extract_all_features(events, sentiment_data)
        feature_cols = [c for c in features_df.columns if c not in ['ticker', 'date']]
        X = features_df[feature_cols]
        X_selected = X[self.feature_selector.selected_features]

        signals = self.classifier.predict_signals(X_selected)

        result = pd.DataFrame({
            'ticker': features_df['ticker'],
            'date': features_df['date'],
            'signal': signals['signal'],
            'signal_name': signals['signal_name']
        })

        if 'prob_buy' in signals.columns:
            result['prob_buy'] = signals['prob_buy']
            result['confidence'] = signals['confidence']

        return result

    def save_pipeline(self, directory: str):
        """Save pipeline"""
        import os
        import pickle

        os.makedirs(directory, exist_ok=True)

        if self.word_correlation_analyzer.word_correlations:
            self.word_correlation_analyzer.save_model(
                os.path.join(directory, 'word_correlations.pkl')
            )

        self.classifier.save_model(os.path.join(directory, 'classifier.pkl'))

        with open(os.path.join(directory, 'feature_selector.pkl'), 'wb') as f:
            pickle.dump(self.feature_selector, f)

        print(f"Pipeline saved to {directory}")

    def load_pipeline(self, directory: str):
        """Load pipeline"""
        import os
        import pickle

        if os.path.exists(os.path.join(directory, 'word_correlations.pkl')):
            self.word_correlation_analyzer.load_model(
                os.path.join(directory, 'word_correlations.pkl')
            )

        self.classifier.load_model(os.path.join(directory, 'classifier.pkl'))

        with open(os.path.join(directory, 'feature_selector.pkl'), 'rb') as f:
            self.feature_selector = pickle.load(f)

        self.is_trained = True
        print(f"Pipeline loaded from {directory}")
