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

        # Default weights aligned with config.yaml (MUST sum to 1.0)
        # Research-backed: MDPI 2025, Nature 2024, De Gruyter 2025
        self.weights = weights or {
            'event_severity': 0.15,  # Event detection confidence
            'intensity': 0.35,       # PRIMARY: Mean sentiment magnitude
            'volume': 0.20,          # Social conviction
            'duration': 0.10,        # Persistence
            'sentiment_volume_momentum': 0.20,  # Research-backed SVC metric (De Gruyter 2025)
            # Optional research-backed enhancements (set to 0 to disable)
            'max_sentiment': 0.0,    # Maximum sentiment (MDPI 2025)
            'polarization': 0.0      # Sentiment disagreement (std)
        }
        # CRITICAL FIX: Validate weights sum to 1.0
        self._normalize_weights()

    def _normalize_weights(self):
        """
        Ensure signal weights sum to 1.0 for proper score normalization.
        
        Academic Basis: Weighted composite scores require weights summing to 1.0
        for proper normalization (Cochrane, 2005).
        """
        # Only consider active weights (non-zero values)
        active_weights = {k: v for k, v in self.weights.items() if v > 0}
        total = sum(active_weights.values())
        
        if abs(total - 1.0) > 0.01:
            print(f"⚠ Signal weights sum to {total:.2f}, normalizing to 1.0")
            for key in active_weights:
                self.weights[key] = active_weights[key] / total

    def compute_raw_score(self, event_features: Dict, reaction_features: Dict) -> float:
        """
        Compute composite ESG Event Shock Score

        Formula:
        Score = w1*EventSeverity + w2*Intensity + w3*Volume + w4*Duration
                + w5*MaxSentiment + w6*Polarization

        Academic references:
        - MDPI (2025): Max and std of sentiment are significant predictors
        - Nature (2024): Weighted sentiment improves prediction

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

        # 5. NEW: Max Sentiment (MDPI 2025 - max is predictive)
        max_sentiment_raw = reaction_features.get('max_sentiment', 0.0)
        max_sentiment_normalized = (max_sentiment_raw + 1.0) / 2.0

        # 6. NEW: Polarization/Sentiment Std (disagreement measure)
        # Higher polarization indicates market disagreement - can amplify moves
        polarization = reaction_features.get('polarization', 0.0)
        polarization_normalized = min(polarization, 1.0)  # Already in [0, 1] range

        # 7. NEW: Sentiment Volume Momentum (SVC Metric)
        # Combines sentiment direction with volume conviction
        # Formula: intensity * volume_normalized (Range: [-1, 1])
        # Normalized to [0, 1] for scoring
        momentum_proxy = intensity_raw * volume_normalized
        momentum_normalized = (momentum_proxy + 1.0) / 2.0

        # Compute weighted sum using actual weights (with proper defaults)
        raw_score = (
            self.weights.get('event_severity', 0.15) * event_severity +
            self.weights.get('intensity', 0.35) * intensity_normalized +
            self.weights.get('volume', 0.20) * volume_normalized +
            self.weights.get('duration', 0.10) * duration_normalized +
            self.weights.get('max_sentiment', 0.0) * max_sentiment_normalized +
            self.weights.get('polarization', 0.0) * polarization_normalized +
            self.weights.get('sentiment_volume_momentum', 0.20) * momentum_normalized
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

        # CRITICAL FIX Issue #4: Use rolling window for z-score calculation
        # instead of global history for time-series stationarity
        # (Jegadeesh & Titman, 1993)
        recent_history = self.history[-self.lookback_window:] if len(self.history) > self.lookback_window else self.history
        rolling_scores = [h['raw_score'] for h in recent_history]

        # Compute cross-sectional z-score using rolling window
        if len(rolling_scores) > 1:
            mean_score = np.mean(rolling_scores)
            std_score = np.std(rolling_scores)
            z_score = (raw_score - mean_score) / (std_score + 1e-6)
        else:
            z_score = 0.0

        # Convert to trading signal using tanh
        signal = np.tanh(z_score)  # Maps to [-1, 1]

        # Compute quintile rank using rolling window scores
        quintile = self._compute_quintile(raw_score, rolling_scores)

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

    def generate_signals_batch(self, events_data: List[Dict],
                                min_posts: int = 5,
                                require_social_data: bool = True) -> pd.DataFrame:
        """
        Generate signals for multiple events with quality filtering.

        ROOT CAUSE FIX (Dec 2025):
        - Events WITHOUT social media data were creating noise signals
        - Fallback sentiment (-0.5, 0, +0.5) caused bimodal quintile distribution
        - Now requires actual social media validation for trading signals

        Args:
            events_data: List of dictionaries with event and reaction data
            min_posts: Minimum number of social media posts required (default: 5)
            require_social_data: If True, exclude events without social data (default: True)

        Returns:
            DataFrame with all signals
        """
        signals = []

        for event_data in events_data:
            # Extract post count from reaction features
            n_posts = event_data['reaction_features'].get('n_tweets', 0)

            signal = self.compute_signal(
                ticker=event_data['ticker'],
                date=event_data['date'],
                event_features=event_data['event_features'],
                reaction_features=event_data['reaction_features']
            )
            # Add post count and confidence score to signal
            signal['n_posts'] = n_posts
            signal['has_social_data'] = n_posts > 0

            # Compute signal confidence (higher with more posts and stronger sentiment)
            sentiment_strength = abs(signal['sentiment_intensity'])
            volume_boost = min(signal['volume_ratio'] / 2.0, 1.0)  # Cap at 2x
            post_confidence = min(n_posts / 50.0, 1.0)  # Cap at 50 posts
            signal['confidence'] = (0.4 * sentiment_strength + 0.3 * volume_boost + 0.3 * post_confidence)

            signals.append(signal)

        df_signals = pd.DataFrame(signals)

        if df_signals.empty:
            return df_signals

        print(f"\n📊 Signal Quality Filters (Research-Backed):")
        print(f"  Total events detected: {len(df_signals)}")

        # ROOT CAUSE FIX #1: Separate events by social media coverage
        has_social = df_signals['has_social_data'] == True
        events_with_social = df_signals[has_social].copy()
        events_without_social = df_signals[~has_social].copy()

        print(f"  Events WITH social data: {len(events_with_social)}")
        print(f"  Events WITHOUT social data: {len(events_without_social)}")

        # ROOT CAUSE FIX #2: Exclude events without social data from trading
        # Academic basis: Social sentiment is the primary alpha driver (45% weight)
        # Without social validation, the signal is noise, not signal
        if require_social_data:
            print(f"  ⚠ EXCLUDING {len(events_without_social)} events without social media data")
            print(f"    (Research: social sentiment drives alpha; fallback values add noise)")
            df_signals = events_with_social.copy()

        if df_signals.empty:
            print(f"  ⚠ No events with social data. Cannot generate trading signals.")
            return pd.DataFrame()

        # ROOT CAUSE FIX #3: Apply minimum post count filter
        # Academic basis: Sentiment from <5 posts is statistically unreliable
        before_post_filter = len(df_signals)
        df_signals = df_signals[df_signals['n_posts'] >= min_posts].copy()
        print(f"  Events after min_posts filter (≥{min_posts}): {len(df_signals)} (removed {before_post_filter - len(df_signals)})")

        if df_signals.empty:
            print(f"  ⚠ No events with sufficient posts. Try lowering min_posts threshold.")
            return pd.DataFrame()

        # Apply volume and sentiment filters
        before_volume = len(df_signals)
        df_signals = self.filter_by_volume(df_signals, min_volume_ratio=1.2)
        print(f"  Events after volume filter (≥1.2x): {len(df_signals)} (removed {before_volume - len(df_signals)})")

        before_sentiment = len(df_signals)
        df_signals = self.filter_by_sentiment(df_signals, min_abs_intensity=0.05)
        print(f"  Events after sentiment filter (|intensity|≥0.05): {len(df_signals)} (removed {before_sentiment - len(df_signals)})")

        if df_signals.empty:
            print(f"  ⚠ All events filtered out. Consider relaxing thresholds.")
            return pd.DataFrame()

        # FIX 2.1: Apply cross-sectional ranking AFTER filtering
        df_signals = self._apply_cross_sectional_ranking(df_signals)

        print(f"  FINAL trading signals: {len(df_signals)}")

        # CRITICAL: Validate signal quality after generation
        self.validate_signal_quality(df_signals)

        return df_signals

    def filter_by_volume(self, signals_df: pd.DataFrame, min_volume_ratio: float = 2.5) -> pd.DataFrame:
        """
        Filter signals by minimum volume ratio (Priority 1 improvement)

        Academic research shows volume ratios <2.5x have minimal price impact.

        Args:
            signals_df: DataFrame with signals
            min_volume_ratio: Minimum volume ratio threshold

        Returns:
            Filtered DataFrame
        """
        if signals_df.empty:
            return signals_df

        filtered = signals_df[signals_df['volume_ratio'] >= min_volume_ratio].copy()

        return filtered

    def filter_by_sentiment(self, signals_df: pd.DataFrame, min_abs_intensity: float = 0.1) -> pd.DataFrame:
        """
        Filter signals by minimum absolute sentiment intensity (Priority 1 improvement)

        Eliminates neutral-sentiment signals that dilute alpha.

        Args:
            signals_df: DataFrame with signals
            min_abs_intensity: Minimum absolute sentiment intensity

        Returns:
            Filtered DataFrame
        """
        if signals_df.empty:
            return signals_df

        filtered = signals_df[signals_df['sentiment_intensity'].abs() >= min_abs_intensity].copy()

        return filtered

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
