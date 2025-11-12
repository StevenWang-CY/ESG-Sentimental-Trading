"""
ESG Signal Generator
Generates trading signals from ESG events and sentiment features
"""

import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional


class ESGSignalGenerator:
    """
    Generates final trading signal from event + sentiment features
    """

    def __init__(self, lookback_window: int = 252,
                 weights: Optional[Dict[str, float]] = None):
        """
        Initialize signal generator

        Args:
            lookback_window: Window for z-score normalization
            weights: Custom weights for signal components
        """
        self.lookback_window = lookback_window
        self.history = []  # Store historical scores for ranking

        # Default weights
        self.weights = weights or {
            'event_severity': 0.3,
            'intensity': 0.4,
            'volume': 0.2,
            'duration': 0.1
        }

    def compute_raw_score(self, event_features: Dict, reaction_features: Dict) -> float:
        """
        Compute composite ESG Event Shock Score

        Formula:
        Score = w1*EventSeverity + w2*Intensity + w3*Volume + w4*Duration

        Args:
            event_features: Dictionary with event detection results
            reaction_features: Dictionary with sentiment features

        Returns:
            Raw signal score
        """
        # 1. Event Severity (from event detection confidence)
        event_severity = event_features.get('confidence', 0.5)

        # 2. Intensity (sentiment magnitude with direction)
        # CRITICAL FIX: Use SIGNED sentiment to determine quintile
        # Positive sentiment → High quintile (Q5) → Long positions
        # Negative sentiment → Low quintile (Q1) → Short positions
        # This ensures sentiment-quintile alignment for long-short strategy
        intensity_raw = reaction_features.get('intensity', 0.0)
        # Normalize to [0, 1] range: map [-1, 1] sentiment to [0, 1]
        intensity_normalized = (intensity_raw + 1.0) / 2.0  # Maps -1→0, 0→0.5, +1→1

        # 3. Volume (log-normalized volume ratio)
        volume_ratio = reaction_features.get('volume_ratio', 1.0)
        volume_normalized = min(np.log1p(volume_ratio) / np.log(10), 1.0)

        # 4. Duration (normalize by max expected days)
        duration_days = reaction_features.get('duration_days', 0)
        duration_normalized = min(duration_days / 7.0, 1.0)

        # Compute weighted sum
        raw_score = (
            self.weights['event_severity'] * event_severity +
            self.weights['intensity'] * intensity_normalized +
            self.weights['volume'] * volume_normalized +
            self.weights['duration'] * duration_normalized
        )

        return raw_score

    def compute_signal(self, ticker: str, date: datetime,
                      event_features: Dict, reaction_features: Dict) -> Dict:
        """
        Convert raw score to standardized signal

        Args:
            ticker: Stock ticker
            date: Signal date
            event_features: Event detection results
            reaction_features: Sentiment reaction features

        Returns:
            Dictionary with signal components
        """
        raw_score = self.compute_raw_score(event_features, reaction_features)

        # Add to history
        self.history.append({
            'ticker': ticker,
            'date': date,
            'raw_score': raw_score
        })

        # CRITICAL FIX: For sparse ESG events, use ALL historical scores for ranking
        # (not just same-date scores). ESG events are infrequent, often 1 per date.
        # Using same-date normalization causes all signals to be neutral (z=0, Q=3).
        # Changed from: same_date_scores = [h for h in history if h['date'] == date]
        all_historical_scores = [h['raw_score'] for h in self.history]

        # Compute cross-sectional z-score using ALL historical scores
        if len(all_historical_scores) > 1:
            mean_score = np.mean(all_historical_scores)
            std_score = np.std(all_historical_scores)
            z_score = (raw_score - mean_score) / (std_score + 1e-6)
        else:
            z_score = 0.0

        # Convert to trading signal using tanh
        signal = np.tanh(z_score)  # Maps to [-1, 1]

        # Compute quintile rank using ALL historical scores
        quintile = self._compute_quintile(raw_score, all_historical_scores)

        return {
            'ticker': ticker,
            'date': date,
            'raw_score': raw_score,
            'z_score': z_score,
            'signal': signal,
            'quintile': quintile,
            'event_category': event_features.get('category', 'Unknown'),
            'event_confidence': event_features.get('confidence', 0.0),
            'sentiment_intensity': reaction_features.get('intensity', 0.0),
            'volume_ratio': reaction_features.get('volume_ratio', 1.0)
        }

    def _compute_quintile(self, score: float, all_scores: List[float]) -> int:
        """
        Assign quintile (1=lowest, 5=highest)

        Args:
            score: Score to rank
            all_scores: All scores for comparison

        Returns:
            Quintile (1-5)
        """
        if len(all_scores) < 5:
            return 3

        quintiles = np.percentile(all_scores, [20, 40, 60, 80])

        for i, threshold in enumerate(quintiles):
            if score <= threshold:
                return i + 1

        return 5

    def _apply_cross_sectional_ranking(self, signals_df: pd.DataFrame) -> pd.DataFrame:
        """
        FIX 2.1: Apply cross-sectional ranking to assign quintiles

        Groups signals by date and ranks within each date.
        For sparse data (<5 signals per date), uses tertile split:
        - Top 1/3 → Q5 (long positions)
        - Bottom 1/3 → Q1 (short positions)
        - Middle 1/3 → Q3 (neutral)

        Args:
            signals_df: DataFrame with raw signals

        Returns:
            DataFrame with corrected quintile assignments
        """
        if signals_df.empty:
            return signals_df

        # Ensure date is datetime
        signals_df['date'] = pd.to_datetime(signals_df['date'])

        def assign_quintiles_per_date(group):
            """Assign quintiles within a single date"""
            n_signals = len(group)

            if n_signals >= 5:
                # Standard quintile split (20% per quintile)
                try:
                    group['quintile'] = pd.qcut(
                        group['raw_score'],
                        q=5,
                        labels=[1, 2, 3, 4, 5],
                        duplicates='drop'
                    )
                except ValueError:
                    # Handle case where all scores are identical
                    group['quintile'] = 3
            else:
                # Tertile split for sparse data
                # Top 1/3 → Q5, Bottom 1/3 → Q1, Middle → Q3
                scores = group['raw_score'].values

                if n_signals == 1:
                    # Single signal → use sentiment to determine quintile
                    sentiment = group['sentiment_intensity'].iloc[0]
                    if sentiment > 0.1:
                        group['quintile'] = 5  # Long
                    elif sentiment < -0.1:
                        group['quintile'] = 1  # Short
                    else:
                        group['quintile'] = 3  # Neutral
                elif n_signals == 2:
                    # Two signals → one long, one short
                    group['quintile'] = group['raw_score'].rank(method='first').map({1: 1, 2: 5})
                else:
                    # 3-4 signals → tertile split
                    percentile_33 = np.percentile(scores, 33.33)
                    percentile_67 = np.percentile(scores, 66.67)

                    def assign_tertile(score):
                        if score <= percentile_33:
                            return 1  # Bottom tertile → Q1 (short)
                        elif score >= percentile_67:
                            return 5  # Top tertile → Q5 (long)
                        else:
                            return 3  # Middle tertile → Q3 (neutral)

                    group['quintile'] = group['raw_score'].apply(assign_tertile)

            return group

        # Apply cross-sectional ranking per date
        signals_df = signals_df.groupby('date', group_keys=False).apply(assign_quintiles_per_date)

        # Recompute z-scores using same-date normalization (proper cross-sectional)
        def recompute_z_scores(group):
            """Recompute z-scores within each date"""
            if len(group) > 1:
                mean_score = group['raw_score'].mean()
                std_score = group['raw_score'].std()
                group['z_score'] = (group['raw_score'] - mean_score) / (std_score + 1e-6)
                group['signal'] = np.tanh(group['z_score'])
            else:
                # Single signal → use sentiment direction
                sentiment = group['sentiment_intensity'].iloc[0]
                group['z_score'] = np.sign(sentiment) * 1.0
                group['signal'] = np.tanh(group['z_score'])
            return group

        signals_df = signals_df.groupby('date', group_keys=False).apply(recompute_z_scores)

        print(f"\n✓ Cross-sectional ranking applied:")
        print(f"  Dates with signals: {signals_df['date'].nunique()}")
        print(f"  Avg signals per date: {len(signals_df) / signals_df['date'].nunique():.1f}")

        # Show quintile distribution after cross-sectional ranking
        quintile_dist = signals_df['quintile'].value_counts().sort_index()
        print(f"  Quintile distribution after cross-sectional ranking:")
        for q, count in quintile_dist.items():
            print(f"    Q{q}: {count} signals")

        return signals_df

    def generate_signals_batch(self, events_data: List[Dict]) -> pd.DataFrame:
        """
        Generate signals for multiple events

        Args:
            events_data: List of dictionaries with event and reaction data

        Returns:
            DataFrame with all signals
        """
        signals = []

        for event_data in events_data:
            signal = self.compute_signal(
                ticker=event_data['ticker'],
                date=event_data['date'],
                event_features=event_data['event_features'],
                reaction_features=event_data['reaction_features']
            )
            signals.append(signal)

        df_signals = pd.DataFrame(signals)

        # FIX 2.1: Apply cross-sectional ranking AFTER all signals are generated
        # This ensures proper quintile assignment for market-neutral portfolios
        df_signals = self._apply_cross_sectional_ranking(df_signals)

        # CRITICAL: Validate signal quality after generation
        self.validate_signal_quality(df_signals)

        return df_signals

    def validate_signal_quality(self, signals_df: pd.DataFrame):
        """
        Validate data quality of generated signals and print warnings

        Args:
            signals_df: DataFrame with generated signals
        """
        if signals_df.empty:
            print("WARNING: No signals generated!")
            return

        print("\n" + "="*60)
        print("SIGNAL QUALITY VALIDATION")
        print("="*60)

        # 1. Check signals per month
        signals_df['date'] = pd.to_datetime(signals_df['date'])
        signals_df['year_month'] = signals_df['date'].dt.to_period('M')
        signals_per_month = signals_df.groupby('year_month').size()

        print(f"\nTotal signals generated: {len(signals_df)}")
        print(f"Date range: {signals_df['date'].min()} to {signals_df['date'].max()}")
        print(f"\nSignals per month:")
        for period, count in signals_per_month.items():
            status = "LOW" if count < 10 else "OK"
            print(f"  {period}: {count:3d} signals [{status}]")

        low_months = signals_per_month[signals_per_month < 10]
        if len(low_months) > 0:
            print(f"\nALERT: {len(low_months)} months have < 10 signals!")
            print(f"       This may reduce statistical significance of backtest results.")

        # 2. Check Reddit coverage (non-zero sentiment)
        total_signals = len(signals_df)
        non_zero_sentiment = (signals_df['sentiment_intensity'] != 0.0).sum()
        reddit_coverage = (non_zero_sentiment / total_signals) * 100

        print(f"\nReddit sentiment coverage:")
        print(f"  Signals with Reddit data: {non_zero_sentiment}/{total_signals} ({reddit_coverage:.1f}%)")

        if reddit_coverage < 60:
            print(f"\nWARNING: Reddit coverage is {reddit_coverage:.1f}% (target: >60%)")
            print(f"         {total_signals - non_zero_sentiment} signals have zero sentiment (missing Reddit data)")
            print(f"         Consider widening Reddit search window or adding fallback data sources")

        # 3. Check sentiment-quintile alignment
        # Expected: Q5 (highest quintile) should correlate with positive sentiment
        # Negative correlation suggests inversion bug in scoring logic
        correlation = signals_df[['quintile', 'sentiment_intensity']].corr().iloc[0, 1]

        print(f"\nSentiment-Quintile correlation: {correlation:.3f}")

        if correlation < 0:
            print(f"\nCRITICAL: Negative correlation detected ({correlation:.3f})!")
            print(f"          Expected: Q5 signals should have positive sentiment")
            print(f"          Actual: Q5 signals may have negative sentiment (INVERTED)")
            print(f"          This suggests a bug in quintile assignment logic")

            # Show quintile breakdown
            quintile_sentiment = signals_df.groupby('quintile')['sentiment_intensity'].agg(['mean', 'count'])
            print(f"\nQuintile sentiment breakdown:")
            print(quintile_sentiment)

        # 4. Check quintile distribution
        quintile_counts = signals_df['quintile'].value_counts().sort_index()
        print(f"\nQuintile distribution:")
        for q, count in quintile_counts.items():
            pct = (count / total_signals) * 100
            print(f"  Q{q}: {count:3d} signals ({pct:5.1f}%)")

        # Expected: roughly 20% per quintile (may vary with sparse data)
        if quintile_counts.std() > 5:
            print(f"\nNOTE: Uneven quintile distribution (std={quintile_counts.std():.1f})")
            print(f"      This is expected for sparse ESG events")

        print("="*60 + "\n")

    def get_signal_statistics(self) -> Dict:
        """
        Get statistics about generated signals

        Returns:
            Dictionary with signal statistics
        """
        if not self.history:
            return {'n_signals': 0}

        scores = [h['raw_score'] for h in self.history]

        return {
            'n_signals': len(self.history),
            'mean_score': np.mean(scores),
            'std_score': np.std(scores),
            'min_score': np.min(scores),
            'max_score': np.max(scores),
            'median_score': np.median(scores)
        }

    def clear_history(self):
        """Clear signal history"""
        self.history = []

    def set_weights(self, weights: Dict[str, float]):
        """
        Update signal weights

        Args:
            weights: New weights dictionary
        """
        self.weights.update(weights)
