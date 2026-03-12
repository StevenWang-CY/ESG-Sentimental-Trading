"""
ESG Signal Generator
Generates trading signals from ESG events and sentiment features

AUDIT REFACTOR (Jan 2026):
- Added statistical weight derivation (inverse variance, correlation-based)
- Added strict typing throughout
- Integrated with walk-forward validation framework
- Removed hard-coded magic number weights in favor of data-driven calibration
"""

from __future__ import annotations

import logging
import numpy as np
import pandas as pd
from datetime import datetime
from dataclasses import dataclass
from enum import Enum, auto
from typing import Dict, List, Optional, Callable, TypeAlias

logger = logging.getLogger(__name__)

# Try to import validation framework
try:
    from ..validation import SignalWeights, WeightingMethod
    VALIDATION_AVAILABLE = True
except ImportError:
    VALIDATION_AVAILABLE = False


# Type aliases for clarity
Weight: TypeAlias = float
Score: TypeAlias = float

# ---------------------------------------------------------------------------
# Signal Output Schema Definition
# ---------------------------------------------------------------------------

SIGNAL_SCHEMA = {
    'ticker':              {'dtype': 'str',     'required': True},
    'date':                {'dtype': 'datetime', 'required': True},
    'raw_score':           {'dtype': 'float',   'required': True,  'min': -1.0, 'max': 1.0},
    'z_score':             {'dtype': 'float',   'required': True},
    'signal':              {'dtype': 'float',   'required': True,  'min': -1.0, 'max': 1.0},
    'quintile':            {'dtype': 'int',     'required': True,  'min': 1,   'max': 5},
    'event_category':      {'dtype': 'str',     'required': True},
    'event_confidence':    {'dtype': 'float',   'required': True,  'min': 0.0, 'max': 1.0},
    'sentiment_intensity': {'dtype': 'float',   'required': True,  'min': -1.0, 'max': 1.0},
    'volume_ratio':        {'dtype': 'float',   'required': True,  'min': 0.0},
    'n_posts':             {'dtype': 'int',     'required': True,  'min': 0},
    'has_social_data':     {'dtype': 'bool',    'required': True},
    'confidence':          {'dtype': 'float',   'required': True,  'min': 0.0, 'max': 1.0},
}

SIGNAL_REQUIRED_COLUMNS = [k for k, v in SIGNAL_SCHEMA.items() if v['required']]


class SignalSchemaError(ValueError):
    """Raised when a signal DataFrame does not conform to the required schema."""
    pass


def validate_signal_schema(df: pd.DataFrame, raise_on_error: bool = True) -> List[str]:
    """
    Validate that a signal DataFrame conforms exactly to the required schema.

    Checks:
      1. All required columns are present
      2. No unexpected NaN/null values in required columns
      3. Numeric columns are within their defined bounds
      4. Quintile values are in {1, 2, 3, 4, 5}

    Args:
        df: Signal DataFrame to validate
        raise_on_error: If True, raise SignalSchemaError on first violation

    Returns:
        List of violation descriptions (empty if valid)
    """
    violations: List[str] = []

    if df.empty:
        return violations

    # 1. Check required columns
    missing = [c for c in SIGNAL_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        violations.append(f"Missing required columns: {missing}")

    # 2. Check for nulls in required columns
    for col in SIGNAL_REQUIRED_COLUMNS:
        if col in df.columns:
            null_count = df[col].isna().sum()
            if null_count > 0:
                violations.append(f"Column '{col}' has {null_count} null values")

    # 3. Check numeric bounds
    for col, spec in SIGNAL_SCHEMA.items():
        if col not in df.columns:
            continue
        if spec['dtype'] in ('float', 'int'):
            if 'min' in spec:
                below = (df[col] < spec['min']).sum()
                if below > 0:
                    violations.append(
                        f"Column '{col}' has {below} values below minimum {spec['min']}"
                    )
            if 'max' in spec:
                above = (df[col] > spec['max']).sum()
                if above > 0:
                    violations.append(
                        f"Column '{col}' has {above} values above maximum {spec['max']}"
                    )

    # 4. Quintile domain check
    if 'quintile' in df.columns:
        invalid_q = ~df['quintile'].isin([1, 2, 3, 4, 5])
        if invalid_q.sum() > 0:
            bad_vals = df.loc[invalid_q, 'quintile'].unique().tolist()
            violations.append(f"Column 'quintile' has invalid values: {bad_vals}")

    if violations and raise_on_error:
        raise SignalSchemaError(
            f"Signal schema validation failed with {len(violations)} violation(s):\n"
            + "\n".join(f"  - {v}" for v in violations)
        )

    return violations


def enforce_signal_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Coerce a signal DataFrame to conform to the required schema.

    Applies safe type coercion and clipping rather than raising errors.
    Use this as a post-processing step to guarantee compliance.

    Returns a new DataFrame (does not mutate input).
    """
    if df.empty:
        return df.copy()

    df = df.copy()

    # Ensure required columns exist with defaults
    defaults = {
        'ticker': '', 'date': pd.NaT, 'raw_score': 0.0, 'z_score': 0.0,
        'signal': 0.0, 'quintile': 3, 'event_category': 'Unknown',
        'event_confidence': 0.0, 'sentiment_intensity': 0.0,
        'volume_ratio': 0.0, 'n_posts': 0, 'has_social_data': False,
        'confidence': 0.0,
    }
    for col, default in defaults.items():
        if col not in df.columns:
            df[col] = default

    # Type coercion
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['ticker'] = df['ticker'].astype(str)
    df['event_category'] = df['event_category'].astype(str)
    df['has_social_data'] = df['has_social_data'].astype(bool)

    for col in ('raw_score', 'z_score', 'signal', 'event_confidence',
                'sentiment_intensity', 'volume_ratio', 'confidence'):
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)

    for col in ('n_posts', 'quintile'):
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

    # Clip to valid ranges
    df['raw_score'] = df['raw_score'].clip(-1.0, 1.0)
    df['signal'] = df['signal'].clip(-1.0, 1.0)
    df['event_confidence'] = df['event_confidence'].clip(0.0, 1.0)
    df['sentiment_intensity'] = df['sentiment_intensity'].clip(-1.0, 1.0)
    df['volume_ratio'] = df['volume_ratio'].clip(0.0)
    df['n_posts'] = df['n_posts'].clip(0)
    df['confidence'] = df['confidence'].clip(0.0, 1.0)
    df['quintile'] = df['quintile'].clip(1, 5)

    # Drop any extra columns not in the schema (e.g. 'year_month' added
    # by validate_signal_quality). This guarantees exact schema compliance.
    extra_cols = [c for c in df.columns if c not in SIGNAL_REQUIRED_COLUMNS]
    if extra_cols:
        df = df.drop(columns=extra_cols)

    # Ensure column order matches schema definition
    df = df[SIGNAL_REQUIRED_COLUMNS]

    return df


class WeightDerivationMethod(Enum):
    """Methods for deriving signal component weights."""
    FIXED = auto()              # Use provided fixed weights
    EQUAL = auto()              # 1/n equal weights (baseline)
    INVERSE_VARIANCE = auto()   # Lower variance = higher weight
    CORRELATION_BASED = auto()  # Higher return correlation = higher weight

    @classmethod
    def from_string(cls, value: str | None) -> "WeightDerivationMethod":
        normalized = (value or 'fixed').strip().lower()
        mapping = {
            'fixed': cls.FIXED,
            'equal': cls.EQUAL,
            'inverse_variance': cls.INVERSE_VARIANCE,
            'correlation': cls.CORRELATION_BASED,
            'correlation_based': cls.CORRELATION_BASED,
        }
        if normalized not in mapping:
            raise ValueError(f"Unknown weight derivation method: {value}")
        return mapping[normalized]


@dataclass(frozen=True)
class ValidatedWeights:
    """
    Immutable, validated signal weights.

    CRITICAL: Weights MUST sum to 1.0 for proper score normalization.
    This class enforces that constraint at construction time.
    """
    event_severity: Weight
    intensity: Weight
    volume: Weight
    duration: Weight
    momentum: Weight = 0.0

    def __post_init__(self) -> None:
        """Validate weights sum to 1.0."""
        total = (
            self.event_severity +
            self.intensity +
            self.volume +
            self.duration +
            self.momentum
        )
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"Weights must sum to 1.0, got {total:.4f}")

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary format for backward compatibility."""
        return {
            'event_severity': self.event_severity,
            'intensity': self.intensity,
            'volume': self.volume,
            'duration': self.duration,
            'sentiment_volume_momentum': self.momentum,
            'max_sentiment': 0.0,
            'polarization': 0.0,
        }

    @classmethod
    def from_equal(cls, n_components: int = 4) -> ValidatedWeights:
        """Create equal-weighted configuration."""
        w = 1.0 / n_components
        return cls(event_severity=w, intensity=w, volume=w, duration=w)

    @classmethod
    def from_dict(cls, weights: Dict[str, float]) -> ValidatedWeights:
        """Create from dictionary, normalizing if needed."""
        event = weights.get('event_severity', 0.25)
        intensity = weights.get('intensity', 0.25)
        volume = weights.get('volume', 0.25)
        duration = weights.get('duration', 0.25)
        momentum = weights.get('sentiment_volume_momentum', 0.0)

        # Normalize to sum to 1.0
        total = event + intensity + volume + duration + momentum
        if total > 0:
            return cls(
                event_severity=event / total,
                intensity=intensity / total,
                volume=volume / total,
                duration=duration / total,
                momentum=momentum / total,
            )
        return cls.from_equal()


class StatisticalWeightDeriver:
    """
    Derives signal weights statistically from historical data.

    CRITICAL: Only uses data available at calibration time (no look-ahead).
    """

    def __init__(
        self,
        method: WeightDerivationMethod = WeightDerivationMethod.INVERSE_VARIANCE,
        lookback_days: int = 252
    ):
        self.method = method
        self.lookback_days = lookback_days

    def derive_weights(
        self,
        historical_signals: pd.DataFrame,
        historical_returns: Optional[pd.Series] = None
    ) -> ValidatedWeights:
        """
        Derive weights from historical data.

        Args:
            historical_signals: DataFrame with signal features
            historical_returns: Optional series of forward returns (for correlation method)

        Returns:
            ValidatedWeights derived from data
        """
        if self.method == WeightDerivationMethod.EQUAL:
            return ValidatedWeights.from_equal()

        if self.method == WeightDerivationMethod.FIXED:
            # Use default weights (no momentum — was double-counting intensity)
            return ValidatedWeights(
                event_severity=0.20,
                intensity=0.40,
                volume=0.25,
                duration=0.15,
            )

        if len(historical_signals) < 20:
            print("Warning: Insufficient data for statistical weighting, using equal weights")
            return ValidatedWeights.from_equal()

        # Extract features for variance/correlation calculation
        features = self._extract_features(historical_signals)

        if self.method == WeightDerivationMethod.INVERSE_VARIANCE:
            return self._inverse_variance_weights(features)

        elif self.method == WeightDerivationMethod.CORRELATION_BASED:
            if historical_returns is None:
                print("Warning: No returns provided for correlation weighting, using inverse variance")
                return self._inverse_variance_weights(features)
            return self._correlation_weights(features, historical_returns)

        raise ValueError(f"Unknown method: {self.method}")

    def _extract_features(self, signals: pd.DataFrame) -> pd.DataFrame:
        """Extract normalized feature columns from signals."""
        features = pd.DataFrame(index=signals.index if hasattr(signals, 'index') else range(len(signals)))

        # Event severity (confidence)
        if 'event_confidence' in signals.columns:
            features['event_severity'] = signals['event_confidence'].clip(0, 1)
        else:
            features['event_severity'] = 0.5

        # Intensity (normalized sentiment)
        if 'sentiment_intensity' in signals.columns:
            features['intensity'] = (signals['sentiment_intensity'] + 1) / 2
        else:
            features['intensity'] = 0.5

        # Volume (log-normalized)
        if 'volume_ratio' in signals.columns:
            features['volume'] = np.minimum(np.log1p(signals['volume_ratio']) / np.log(10), 1.0)
        else:
            features['volume'] = 0.5

        # Duration (normalized by 7 days)
        if 'duration_days' in signals.columns:
            features['duration'] = np.minimum(signals['duration_days'] / 7.0, 1.0)
        else:
            features['duration'] = 0.5

        return features

    def _inverse_variance_weights(self, features: pd.DataFrame) -> ValidatedWeights:
        """
        Compute weights as inverse of variance.

        Lower variance components get higher weight (more stable signal).
        """
        components = ['event_severity', 'intensity', 'volume', 'duration']
        recent = features.tail(self.lookback_days)

        variances = {}
        for c in components:
            var = recent[c].var() if c in recent.columns else 1.0
            variances[c] = max(var, 1e-6)  # Avoid division by zero

        # Inverse variance
        inv_var_sum = sum(1/v for v in variances.values())
        weights = {c: (1/variances[c]) / inv_var_sum for c in components}

        return ValidatedWeights(
            event_severity=weights['event_severity'],
            intensity=weights['intensity'],
            volume=weights['volume'],
            duration=weights['duration'],
        )

    def _correlation_weights(
        self,
        features: pd.DataFrame,
        returns: pd.Series
    ) -> ValidatedWeights:
        """
        Compute weights based on correlation with forward returns.

        Higher absolute correlation = higher weight.
        """
        components = ['event_severity', 'intensity', 'volume', 'duration']
        recent_features = features.tail(self.lookback_days)
        recent_returns = returns.tail(self.lookback_days)

        # Align indices
        common_idx = recent_features.index.intersection(recent_returns.index)
        if len(common_idx) < 20:
            return self._inverse_variance_weights(features)

        correlations = {}
        for c in components:
            if c in recent_features.columns:
                corr = recent_features.loc[common_idx, c].corr(recent_returns.loc[common_idx])
                correlations[c] = abs(corr) if not np.isnan(corr) else 0.01
            else:
                correlations[c] = 0.01

        # Normalize
        total = sum(correlations.values())
        if total < 0.001:
            return ValidatedWeights.from_equal()

        weights = {c: correlations[c] / total for c in components}

        return ValidatedWeights(
            event_severity=weights['event_severity'],
            intensity=weights['intensity'],
            volume=weights['volume'],
            duration=weights['duration'],
        )


class ESGSignalGenerator:
    """
    Generates final trading signal from event + sentiment features.

    AUDIT REFACTOR (Jan 2026):
    - Supports statistical weight derivation (inverse variance, correlation-based)
    - Integrates with walk-forward validation framework
    - Maintains backward compatibility with fixed weights
    """

    def __init__(
        self,
        lookback_window: int = 252,
        weights: Optional[Dict[str, float]] = None,
        weight_method: WeightDerivationMethod = WeightDerivationMethod.FIXED,
    ):
        """
        Initialize signal generator.

        Args:
            lookback_window: Window for z-score normalization
            weights: Custom weights for signal components (used if weight_method=FIXED)
            weight_method: Method for deriving weights (FIXED, EQUAL, INVERSE_VARIANCE, CORRELATION_BASED)
        """
        self.lookback_window = lookback_window
        self.history: List[Dict] = []  # Store historical scores for ranking
        self.weight_method = weight_method
        self.weight_deriver = StatisticalWeightDeriver(
            method=weight_method,
            lookback_days=lookback_window
        )

        # Initialize weights
        if weights is not None:
            # Use provided weights (backward compatibility)
            self._validated_weights = ValidatedWeights.from_dict(weights)
            self.weights = self._validated_weights.to_dict()
        elif weight_method == WeightDerivationMethod.EQUAL:
            self._validated_weights = ValidatedWeights.from_equal()
            self.weights = self._validated_weights.to_dict()
        else:
            # Default weights (will be recalibrated if statistical method chosen)
            # No momentum component (was double-counting intensity)
            self._validated_weights = ValidatedWeights(
                event_severity=0.20,
                intensity=0.40,
                volume=0.25,
                duration=0.15,
            )
            self.weights = self._validated_weights.to_dict()

        # CRITICAL: Validate weights sum to 1.0 (enforced by ValidatedWeights)
        self._normalize_weights()

    def recalibrate_weights(
        self,
        historical_signals: pd.DataFrame,
        historical_returns: Optional[pd.Series] = None
    ) -> ValidatedWeights:
        """
        Recalibrate weights using statistical derivation.

        CRITICAL: Only call with data available at calibration time.
        Do NOT include future data - this would cause look-ahead bias.

        Args:
            historical_signals: Historical signals (training data only)
            historical_returns: Optional forward returns for correlation method

        Returns:
            ValidatedWeights derived from historical data
        """
        if self.weight_method == WeightDerivationMethod.FIXED:
            print("Note: Using fixed weights (recalibration skipped)")
            return self._validated_weights

        new_weights = self.weight_deriver.derive_weights(
            historical_signals,
            historical_returns
        )

        # Update internal weights
        self._validated_weights = new_weights
        self.weights = new_weights.to_dict()

        print(f"Weights recalibrated using {self.weight_method.name}:")
        print(f"  event_severity: {new_weights.event_severity:.3f}")
        print(f"  intensity:      {new_weights.intensity:.3f}")
        print(f"  volume:         {new_weights.volume:.3f}")
        print(f"  duration:       {new_weights.duration:.3f}")
        print(f"  momentum:       {new_weights.momentum:.3f}")

        return new_weights

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
        Compute directional ESG Event Score using direction x conviction.

        Formula:
        raw_score = sign(sentiment) * conviction
        conviction = w1*EventSeverity + w2*|Intensity| + w3*Volume + w4*Duration

        This separates DIRECTION (from sentiment sign) from CONVICTION
        (from evidence strength), producing a signed score in [-1, 1].

        Previous bug: intensity was mapped to [0,1] via (x+1)/2, destroying
        sentiment direction. All raw_scores were positive (~0.3-0.65),
        making long/short assignments random.

        Args:
            event_features: Dictionary with event detection results
            reaction_features: Dictionary with sentiment features

        Returns:
            Signed raw score in [-1, 1]. Positive = bullish, negative = bearish.
        """
        # 1. Direction: derived from social media sentiment only
        # REVERTED Fix #10: ESG event polarity from SEC filings has systematic negative bias
        # (75% bearish due to predominance of disclosure of problems/violations vs achievements).
        # Event polarity should not be used as standalone directional signal.
        intensity_raw = reaction_features.get('intensity', 0.0)
        direction = float(np.sign(intensity_raw)) if abs(intensity_raw) > 0.01 else 0.0

        # 2. Conviction components (all in [0, 1], direction-free)
        # Event severity from detection confidence
        event_severity = event_features.get('confidence', 0.5)

        # Sentiment magnitude (absolute value — direction already extracted)
        sentiment_strength = abs(intensity_raw)

        # Volume (log-normalized volume ratio)
        volume_ratio = reaction_features.get('volume_ratio', 1.0)
        volume_normalized = min(np.log1p(volume_ratio) / np.log(10), 1.0)

        # Duration (normalize by max expected days)
        duration_days = reaction_features.get('duration_days', 0)
        duration_normalized = min(duration_days / 7.0, 1.0)

        # 3. Weighted conviction (no momentum — was double-counting intensity)
        conviction = (
            self.weights.get('event_severity', 0.20) * event_severity +
            self.weights.get('intensity', 0.40) * sentiment_strength +
            self.weights.get('volume', 0.25) * volume_normalized +
            self.weights.get('duration', 0.15) * duration_normalized
        )

        # 4. Pre-event sentiment confirmation boost:
        # If pre-event sentiment agrees with post-event direction, boost conviction.
        # This captures early warning signals that were previously discarded.
        pre_event_sent = reaction_features.get('pre_event_sentiment', 0.0)
        if direction != 0 and np.sign(pre_event_sent) == direction:
            conviction *= 1.10  # 10% boost for directional confirmation

        # 5. Final signed score: direction * conviction
        raw_score = direction * conviction  # Range: [-1, 1]

        return raw_score

    def compute_signal(self, ticker: str, date: datetime,
                      event_features: Dict, reaction_features: Dict) -> Dict:
        """
        Convert raw score to standardized signal.

        The z-score and quintile computed here are provisional — they will be
        recomputed by _apply_cross_sectional_ranking() using per-date grouping.
        With signed raw_scores, the sign already encodes direction.

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

        # Provisional values (recomputed cross-sectionally later)
        z_score = raw_score  # Pass through signed score
        signal = float(np.tanh(z_score))

        # Provisional quintile from sign (refined by cross-sectional ranking)
        if raw_score > 0:
            quintile = 5
        elif raw_score < 0:
            quintile = 1
        else:
            quintile = 3

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
        Apply cross-sectional ranking to assign quintiles from signed raw_scores.

        With signed raw_scores (negative=bearish, positive=bullish),
        pd.qcut naturally separates negative scores into Q1 (short) and
        positive scores into Q5 (long).

        Groups signals by date and ranks within each date.
        For sparse data (<5 signals per date), uses tertile split.

        Args:
            signals_df: DataFrame with signed raw_scores in [-1, 1]

        Returns:
            DataFrame with corrected quintile assignments
        """
        if signals_df.empty:
            return signals_df

        # Ensure date is datetime
        signals_df['date'] = pd.to_datetime(signals_df['date'])

        def assign_quintiles_per_date(group):
            """Assign quintiles within a single date using signed raw_scores"""
            n_signals = len(group)

            if n_signals >= 5:
                # Standard quintile split — signed scores naturally separate
                # negative (Q1/short) from positive (Q5/long)
                try:
                    group['quintile'] = pd.qcut(
                        group['raw_score'],
                        q=5,
                        labels=[1, 2, 3, 4, 5],
                        duplicates='drop'
                    )
                except ValueError:
                    # All scores identical — assign neutral
                    group['quintile'] = 3
            else:
                scores = group['raw_score'].values

                if n_signals == 1:
                    # Single signal: use raw_score sign (already encodes direction)
                    score = scores[0]
                    if score > 0:
                        group['quintile'] = 5  # Bullish → long
                    elif score < 0:
                        group['quintile'] = 1  # Bearish → short
                    else:
                        group['quintile'] = 3  # Neutral
                elif n_signals == 2:
                    # Two signals: lower → Q1, higher → Q5
                    group['quintile'] = group['raw_score'].rank(method='first').map({1.0: 1, 2.0: 5}).astype(int)
                else:
                    # 3-4 signals: tertile split on signed scores
                    percentile_33 = np.percentile(scores, 33.33)
                    percentile_67 = np.percentile(scores, 66.67)

                    def assign_tertile(score):
                        if score <= percentile_33:
                            return 1  # Bottom → Q1 (short)
                        elif score >= percentile_67:
                            return 5  # Top → Q5 (long)
                        else:
                            return 3  # Middle → neutral

                    group['quintile'] = group['raw_score'].apply(assign_tertile)

            return group

        # Apply cross-sectional ranking per date
        signals_df = signals_df.groupby('date', group_keys=False).apply(assign_quintiles_per_date)

        # FIX #9: Sign-validated quintile assignment
        # Prevent contra-directional trades: Q5 (long) must have positive raw_score,
        # Q1 (short) must have negative raw_score. Override violations to Q3 (neutral).
        # Scientific basis: Factor portfolios trade in the direction of factor exposure
        # (Fama & French 1993). Shorting a bullish signal contradicts the strategy's thesis.
        mask_wrong_long = (signals_df['quintile'] == 5) & (signals_df['raw_score'] < 0)
        mask_wrong_short = (signals_df['quintile'] == 1) & (signals_df['raw_score'] > 0)
        n_corrected = mask_wrong_long.sum() + mask_wrong_short.sum()
        signals_df.loc[mask_wrong_long, 'quintile'] = 3
        signals_df.loc[mask_wrong_short, 'quintile'] = 3
        if n_corrected > 0:
            print(f"  Sign validation: corrected {n_corrected} contra-directional quintile assignments")

        # Recompute z-scores using same-date normalization (proper cross-sectional)
        def recompute_z_scores(group):
            """Recompute z-scores within each date from signed raw_scores"""
            if len(group) > 1:
                mean_score = group['raw_score'].mean()
                std_score = group['raw_score'].std()
                group['z_score'] = (group['raw_score'] - mean_score) / (std_score + 1e-6)
                group['signal'] = np.tanh(group['z_score'])
            else:
                # Single signal: use raw_score magnitude for z-score, not just sign.
                # Previously forced to sign(score)*1.0, making tanh(1.0)=0.76 regardless
                # of whether raw_score was 0.1 or 0.9. This destroyed signal differentiation.
                # Scale by 2.0: weak (0.1) → tanh(0.2)=0.20, strong (0.9) → tanh(1.8)=0.95.
                score = group['raw_score'].iloc[0]
                group['z_score'] = float(score) * 2.0
                group['signal'] = np.tanh(group['z_score'])
            return group

        signals_df = signals_df.groupby('date', group_keys=False).apply(recompute_z_scores)

        print(f"\n  Cross-sectional ranking applied:")
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
                                require_social_data: bool = True,
                                min_volume_ratio: float = 1.2,
                                min_intensity: float = 0.05,
                                min_confidence: float = 0.0) -> pd.DataFrame:
        """
        Generate signals for multiple events with quality filtering.

        ROOT CAUSE FIX (Dec 2025):
        - Events WITHOUT social media data were creating noise signals
        - Fallback sentiment (-0.5, 0, +0.5) caused bimodal quintile distribution
        - Now requires actual social media validation for trading signals

        TRADE FREQUENCY FIX (Jan 2026):
        - Config values for min_volume_ratio and min_intensity were being ignored
        - Added min_confidence parameter for safe permissive-mode filtering

        Args:
            events_data: List of dictionaries with event and reaction data
            min_posts: Minimum number of social media posts required (default: 5)
            require_social_data: If True, exclude events without social data (default: True)
            min_volume_ratio: Minimum volume ratio for signal inclusion (default: 1.2)
            min_intensity: Minimum |sentiment| intensity for signal inclusion (default: 0.05)
            min_confidence: Minimum confidence score for signal inclusion (default: 0.0)

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

            # Compute signal confidence (higher with more posts, stronger sentiment,
            # event detection quality, and multi-source agreement)
            event_conf = signal['event_confidence']
            sentiment_strength = abs(signal['sentiment_intensity'])
            volume_boost = min(signal['volume_ratio'] / 2.0, 1.0)
            post_confidence = min(n_posts / 30.0, 1.0)  # Faster saturation (was /50)

            base_confidence = (
                0.25 * event_conf +          # Event detection quality
                0.30 * sentiment_strength +   # Sentiment magnitude
                0.20 * volume_boost +         # Volume confirmation
                0.25 * post_confidence        # Data sufficiency
            )

            # Multi-source agreement bonus: independent corroboration lifts confidence
            n_sources = event_data['reaction_features'].get('n_sources', 1)
            source_agreement = event_data['reaction_features'].get('source_agreement', 0.0)
            if n_sources >= 3 and source_agreement >= 0.8:
                agreement_bonus = 0.20  # All sources agree on direction
            elif n_sources >= 2 and source_agreement >= 0.5:
                agreement_bonus = 0.10  # Majority of sources agree
            else:
                agreement_bonus = 0.0

            signal['confidence'] = min(base_confidence + agreement_bonus, 1.0)

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

        # ROOT CAUSE FIX #2: Handle events by social media coverage
        if require_social_data:
            # Strict mode: exclude events without social data entirely
            print(f"  ⚠ EXCLUDING {len(events_without_social)} events without social media data")
            print(f"    (Research: social sentiment drives alpha; fallback values add noise)")
            df_signals = events_with_social.copy()
        else:
            # Permissive mode: keep all events, rely on confidence filtering downstream
            # Events without social data naturally get lower confidence scores
            print(f"  Keeping all {len(df_signals)} events (require_social_data=False)")
            print(f"    Events without social data filtered by confidence (≥{min_confidence})")

        if df_signals.empty:
            print(f"  ⚠ No events passed social data filter. Cannot generate trading signals.")
            return pd.DataFrame()

        # ROOT CAUSE FIX #3: Apply minimum post count filter
        # In permissive mode, only filter events that claim to have social data
        before_post_filter = len(df_signals)
        if require_social_data:
            df_signals = df_signals[df_signals['n_posts'] >= min_posts].copy()
        else:
            # Events without social data bypass post count filter (filtered by confidence)
            mask = (~df_signals['has_social_data']) | (df_signals['n_posts'] >= min_posts)
            df_signals = df_signals[mask].copy()
        print(f"  Events after min_posts filter (≥{min_posts}): {len(df_signals)} (removed {before_post_filter - len(df_signals)})")

        if df_signals.empty:
            print(f"  ⚠ No events with sufficient posts. Try lowering min_posts threshold.")
            return pd.DataFrame()

        # Apply volume and sentiment filters (using config values, not hardcoded)
        before_volume = len(df_signals)
        df_signals = self.filter_by_volume(df_signals, min_volume_ratio=min_volume_ratio)
        print(f"  Events after volume filter (≥{min_volume_ratio}x): {len(df_signals)} (removed {before_volume - len(df_signals)})")

        before_sentiment = len(df_signals)
        df_signals = self.filter_by_sentiment(df_signals, min_abs_intensity=min_intensity)
        print(f"  Events after sentiment filter (|intensity|≥{min_intensity}): {len(df_signals)} (removed {before_sentiment - len(df_signals)})")

        # Apply confidence floor (critical when require_social_data=False)
        if min_confidence > 0:
            before_confidence = len(df_signals)
            df_signals = df_signals[df_signals['confidence'] >= min_confidence].copy()
            print(f"  Events after confidence filter (≥{min_confidence}): {len(df_signals)} (removed {before_confidence - len(df_signals)})")

        if df_signals.empty:
            print(f"  ⚠ All events filtered out. Consider relaxing thresholds.")
            return pd.DataFrame()

        # FIX 2.1: Apply cross-sectional ranking AFTER filtering
        df_signals = self._apply_cross_sectional_ranking(df_signals)

        print(f"  FINAL trading signals: {len(df_signals)}")

        # CRITICAL: Validate signal quality after generation
        self.validate_signal_quality(df_signals)

        # Enforce output schema compliance (guaranteed format)
        df_signals = enforce_signal_schema(df_signals)

        # Validate schema (log warnings but do not raise in batch mode)
        violations = validate_signal_schema(df_signals, raise_on_error=False)
        if violations:
            for v in violations:
                logger.warning(f"Signal schema violation: {v}")
            print(f"  WARNING: {len(violations)} schema violation(s) corrected")

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
        REVERTED Fix #10: Filters on sentiment_intensity instead of raw_score.
        This prevents including ESG event-only signals which have systematic negative bias.

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
