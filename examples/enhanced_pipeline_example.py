"""
Example: Enhanced ESG Pipeline with Thesis Improvements

Demonstrates the new ML pipeline with improvements from Savarese (2019) thesis:
1. Word-level correlation analysis
2. Temporal window features (7-day aggregation)
3. ESG-specific sentiment dictionaries
4. Categorical classification (BUY/SELL/HOLD)
5. Random Forest Classifier
6. Feature selection

This example shows how to train and use the enhanced pipeline.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from src.ml.enhanced_pipeline import EnhancedESGPipeline


def create_synthetic_data():
    """
    Create synthetic data for demonstration
    In production, this would come from real SEC filings, Twitter, and price data
    """
    np.random.seed(42)

    # Create 50 synthetic ESG events over 6 months
    tickers = ['AAPL', 'TSLA', 'AMZN', 'META', 'MSFT', 'GOOGL', 'NVDA', 'SBUX']
    categories = ['environmental', 'social', 'governance']

    start_date = datetime(2024, 1, 1)
    events = []

    for i in range(50):
        events.append({
            'date': start_date + timedelta(days=i * 3),
            'ticker': np.random.choice(tickers),
            'event_category': np.random.choice(categories),
            'event_confidence': np.random.uniform(0.5, 1.0)
        })

    events_df = pd.DataFrame(events)

    # Create synthetic sentiment data (tweets around events)
    sentiment_data = []

    for _, event in events_df.iterrows():
        ticker = event['ticker']
        event_date = event['date']

        # Generate 20-50 tweets in 7-day window before event
        n_tweets = np.random.randint(20, 50)

        for j in range(n_tweets):
            days_before = np.random.randint(0, 7)
            tweet_date = event_date - timedelta(days=days_before, hours=np.random.randint(0, 24))

            # Sentiment score influenced by event category
            if event['event_category'] == 'environmental':
                base_sentiment = np.random.normal(-0.2, 0.3)  # Slightly negative on average
                text_templates = [
                    f"{ticker} environmental concerns raised",
                    f"Climate impact of {ticker} questioned",
                    f"{ticker} carbon emissions report",
                    f"Renewable energy investments by {ticker}",
                    f"{ticker} sustainability efforts"
                ]
            elif event['event_category'] == 'social':
                base_sentiment = np.random.normal(-0.3, 0.3)  # More negative
                text_templates = [
                    f"{ticker} labor dispute ongoing",
                    f"Workers at {ticker} raise concerns",
                    f"{ticker} workplace conditions",
                    f"Diversity initiatives at {ticker}",
                    f"{ticker} community investment"
                ]
            else:  # governance
                base_sentiment = np.random.normal(-0.25, 0.3)
                text_templates = [
                    f"{ticker} board changes announced",
                    f"Governance issues at {ticker}",
                    f"{ticker} executive compensation",
                    f"Transparency improvements at {ticker}",
                    f"{ticker} shareholder meeting"
                ]

            sentiment_data.append({
                'timestamp': tweet_date,
                'ticker': ticker,
                'text': np.random.choice(text_templates),
                'sentiment_score': np.clip(base_sentiment, -1, 1),
                'user_followers': np.random.randint(100, 100000),
                'retweets': np.random.randint(0, 1000),
                'likes': np.random.randint(0, 5000)
            })

    sentiment_df = pd.DataFrame(sentiment_data)

    # Create synthetic price data with returns
    # Returns influenced by event category and sentiment
    price_data = []

    for _, event in events_df.iterrows():
        ticker = event['ticker']
        event_date = event['date']

        # Calculate average sentiment in 7 days before event
        pre_event_sentiment = sentiment_df[
            (sentiment_df['ticker'] == ticker) &
            (sentiment_df['timestamp'] >= event_date - timedelta(days=7)) &
            (sentiment_df['timestamp'] < event_date)
        ]['sentiment_score'].mean()

        if pd.isna(pre_event_sentiment):
            pre_event_sentiment = 0

        # Next-day return influenced by sentiment and event
        base_return = np.random.normal(0, 0.02)  # 2% daily vol
        sentiment_effect = pre_event_sentiment * 0.01  # Sentiment contributes to return

        return_1d = base_return + sentiment_effect

        price_data.append({
            'date': event_date,
            'ticker': ticker,
            'return_1d': return_1d,
            'return_5d': return_1d * 3 + np.random.normal(0, 0.01),  # 5-day return
            'return_10d': return_1d * 5 + np.random.normal(0, 0.02)  # 10-day return
        })

    price_df = pd.DataFrame(price_data)

    return events_df, sentiment_df, price_df


def main():
    """
    Main example workflow
    """
    print("="*80)
    print("ENHANCED ESG PIPELINE EXAMPLE")
    print("="*80)

    # 1. CREATE SYNTHETIC DATA
    print("\n[1/5] Creating synthetic data...")
    events_df, sentiment_df, price_df = create_synthetic_data()

    print(f"  Events: {len(events_df)}")
    print(f"  Sentiment data: {len(sentiment_df)} tweets")
    print(f"  Price data: {len(price_df)} days")

    # 2. INITIALIZE PIPELINE
    print("\n[2/5] Initializing enhanced pipeline...")

    # Try Random Forest first (best performer in thesis)
    pipeline = EnhancedESGPipeline(
        model_type='random_forest',
        max_features=15,  # Close to thesis optimal of 10-11
        temporal_window_days=7,  # From thesis
        buy_threshold=0.01,  # +1%
        sell_threshold=-0.01  # -1%
    )

    print(f"  Model: {pipeline.model_type}")
    print(f"  Max features: {pipeline.max_features}")
    print(f"  Temporal window: {pipeline.temporal_window_days} days")
    print(f"  Thresholds: BUY > {pipeline.buy_threshold:.1%}, SELL < {pipeline.sell_threshold:.1%}")

    # 3. TRAIN PIPELINE
    print("\n[3/5] Training pipeline...")

    # Split data: 70% train, 30% test
    train_size = int(len(events_df) * 0.7)
    train_events = events_df.iloc[:train_size]
    test_events = events_df.iloc[train_size:]

    try:
        metrics = pipeline.train(
            events=train_events,
            sentiment_data=sentiment_df,
            price_data=price_df,
            use_time_series_cv=True
        )

        print("\n" + "="*80)
        print("TRAINING METRICS")
        print("="*80)
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                print(f"  {key}: {value}")
            elif isinstance(value, list) and len(value) <= 20:
                print(f"  {key}: {value}")

    except Exception as e:
        print(f"\nWarning: Training failed with error: {e}")
        print("This is expected with synthetic data. In production, use real data.")
        print("\nContinuing with demonstration of other features...")

    # 4. DEMONSTRATE INDIVIDUAL COMPONENTS
    print("\n[4/5] Demonstrating individual components...")

    # Word Correlation Analyzer
    print("\n--- Word Correlation Analysis ---")
    from src.nlp.word_correlation_analyzer import ESGWordCorrelationAnalyzer

    word_analyzer = ESGWordCorrelationAnalyzer()

    sample_texts = [
        "The company announced major carbon emissions reduction initiative",
        "Labor dispute escalates with union negotiations failing",
        "Board approves executive compensation reform package",
        "Environmental lawsuit filed over pollution violations",
        "Strong diversity and inclusion program launched"
    ]

    print("\nSample text analysis:")
    for text in sample_texts[:2]:
        score = word_analyzer.score_text(text)
        print(f"  Text: '{text[:60]}...'")
        print(f"  Correlation score: {score['correlation_score']:.4f}")

    # ESG Sentiment Dictionaries
    print("\n--- ESG Sentiment Dictionaries ---")
    from src.nlp.esg_sentiment_dictionaries import ESGSentimentDictionaries

    esg_dict = ESGSentimentDictionaries()
    esg_dict.print_summary()

    print("\nSample text scoring:")
    for text in sample_texts[:2]:
        scores = esg_dict.score_text(text)
        print(f"  Text: '{text[:60]}...'")
        print(f"  Polarity: {scores['polarity']:.3f}, Subjectivity: {scores['subjectivity']:.3f}")

    # Temporal Feature Extractor
    print("\n--- Temporal Feature Extraction ---")
    from src.nlp.temporal_feature_extractor import TemporalFeatureExtractor

    temporal_extractor = TemporalFeatureExtractor(window_days=7)

    # Extract features for first event
    first_event = events_df.iloc[0]
    event_sentiment = sentiment_df[sentiment_df['ticker'] == first_event['ticker']]

    features = temporal_extractor.extract_temporal_features(
        event_sentiment,
        first_event['date']
    )

    print(f"\nTemporal features for {first_event['ticker']} event on {first_event['date'].date()}:")
    for key, value in list(features.items())[:10]:  # Show first 10
        print(f"  {key}: {value:.4f}")

    # Feature Selection
    print("\n--- Feature Selection ---")
    from src.ml.feature_selector import FeatureSelector

    # Create sample feature matrix
    X_sample = pd.DataFrame(np.random.randn(100, 30), columns=[f'feature_{i}' for i in range(30)])
    y_sample = pd.Series(np.random.randn(100))

    selector = FeatureSelector(max_features=15)

    print("\nComparing feature selection methods:")
    try:
        selected = selector.select_by_random_forest(X_sample, y_sample)
        print(f"  Random Forest selected: {len(selected)} features")
    except Exception as e:
        print(f"  Random Forest: {e}")

    # 5. SAVE PIPELINE (if trained)
    print("\n[5/5] Saving pipeline...")
    if pipeline.is_trained:
        pipeline.save_pipeline('./models/enhanced_pipeline')
        print("  ✓ Pipeline saved to ./models/enhanced_pipeline")
    else:
        print("  ⚠ Pipeline not trained, skipping save")

    # SUMMARY
    print("\n" + "="*80)
    print("EXAMPLE COMPLETE")
    print("="*80)
    print("\nKey Improvements from Thesis:")
    print("  ✓ Word-level correlation analysis")
    print("  ✓ Temporal window features (7-day aggregation)")
    print("  ✓ ESG-specific sentiment dictionaries (300+ terms)")
    print("  ✓ Categorical classification (BUY/SELL/HOLD)")
    print("  ✓ Random Forest Classifier (best performer in thesis)")
    print("  ✓ Feature selection to avoid curse of dimensionality")
    print("\nNext Steps:")
    print("  1. Replace synthetic data with real SEC filings + Twitter data")
    print("  2. Train word correlations on historical data")
    print("  3. Run full backtest on ESG-sensitive NASDAQ-100 universe")
    print("  4. Compare performance vs. baseline model")
    print("="*80)


if __name__ == '__main__':
    main()
