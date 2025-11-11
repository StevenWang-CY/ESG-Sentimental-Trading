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

        # 2. Intensity (sentiment magnitude - use absolute value for signal strength)
        # Strong negative sentiment indicates strong market reaction (regardless of direction)
        # The ESG event category (positive/negative) determines the trade direction
        intensity_raw = reaction_features.get('intensity', 0.0)
        intensity_normalized = abs(intensity_raw)  # Use absolute value for strength

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

        return pd.DataFrame(signals)

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
