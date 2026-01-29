"""
Sentiment Data Dropout Handler

Handles scenarios where real sentiment data becomes unavailable:
1. Reddit API rate limiting
2. API outages
3. Sparse ticker coverage
4. Network issues

CRITICAL: This module handles REAL data availability issues.
It does NOT generate fake/simulated data as a replacement.
Instead, it adjusts signal weights and trading behavior when real data is missing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum, auto


class DataQuality(Enum):
    """Data quality classification based on real data availability."""
    FULL = auto()       # Normal coverage (>90% of expected data)
    PARTIAL = auto()    # Moderate coverage (50-90%)
    SPARSE = auto()     # Limited coverage (20-50%)
    DROPOUT = auto()    # Minimal/no coverage (<20%)


@dataclass
class CoverageMetrics:
    """Metrics for real data coverage quality."""
    n_expected_tickers: int
    n_actual_tickers: int
    n_posts_total: int
    avg_posts_per_ticker: float
    hours_since_last_post: float
    api_errors_last_hour: int = 0

    @property
    def coverage_ratio(self) -> float:
        """Ratio of actual to expected data coverage."""
        return self.n_actual_tickers / max(self.n_expected_tickers, 1)

    @property
    def quality(self) -> DataQuality:
        """Determine overall data quality from metrics."""
        if self.coverage_ratio > 0.9 and self.avg_posts_per_ticker >= 5:
            return DataQuality.FULL
        elif self.coverage_ratio > 0.5 and self.avg_posts_per_ticker >= 3:
            return DataQuality.PARTIAL
        elif self.coverage_ratio > 0.2:
            return DataQuality.SPARSE
        else:
            return DataQuality.DROPOUT

    @property
    def is_stale(self) -> bool:
        """Check if data is stale (no recent posts)."""
        return self.hours_since_last_post > 24

    def __str__(self) -> str:
        return (
            f"CoverageMetrics:\n"
            f"  Tickers: {self.n_actual_tickers}/{self.n_expected_tickers} "
            f"({self.coverage_ratio:.1%})\n"
            f"  Total posts: {self.n_posts_total}\n"
            f"  Avg posts/ticker: {self.avg_posts_per_ticker:.1f}\n"
            f"  Hours since last post: {self.hours_since_last_post:.1f}\n"
            f"  Quality: {self.quality.name}"
        )


class SentimentDropoutHandler:
    """
    Handles sentiment data dropouts gracefully.

    CRITICAL: This handler does NOT create fake data.
    Instead, it:
    1. Adjusts signal weights when sentiment data is missing
    2. Reduces position sizes during low-coverage periods
    3. Halts new positions during complete dropout
    4. Logs all data quality issues for monitoring

    Trading behavior by data quality:
    - FULL: Normal operation with full sentiment weight
    - PARTIAL: Reduce position sizes 30%, increase min_posts threshold
    - SPARSE: Event-only trading (zero sentiment weight in scoring)
    - DROPOUT: Halt new positions, maintain existing
    """

    def __init__(
        self,
        stale_threshold_hours: float = 24.0,
        min_posts_per_ticker: int = 5,
        min_tickers_for_trading: int = 3,
    ):
        """
        Initialize dropout handler.

        Args:
            stale_threshold_hours: Hours without data before considering stale
            min_posts_per_ticker: Minimum posts for reliable sentiment
            min_tickers_for_trading: Minimum tickers with data to allow trading
        """
        self.stale_threshold_hours = stale_threshold_hours
        self.min_posts_per_ticker = min_posts_per_ticker
        self.min_tickers_for_trading = min_tickers_for_trading

        # Tracking
        self._last_good_data: Dict[str, datetime] = {}
        self._coverage_history: List[CoverageMetrics] = []
        self._api_error_count: int = 0

    def assess_coverage(
        self,
        sentiment_data: pd.DataFrame,
        expected_tickers: List[str],
        reference_time: Optional[datetime] = None,
    ) -> CoverageMetrics:
        """
        Assess current data coverage quality from real data.

        Args:
            sentiment_data: Real sentiment data from API
            expected_tickers: Tickers we expected to have data for
            reference_time: Reference time for staleness check

        Returns:
            CoverageMetrics with quality assessment
        """
        reference_time = reference_time or datetime.now()

        if sentiment_data.empty:
            metrics = CoverageMetrics(
                n_expected_tickers=len(expected_tickers),
                n_actual_tickers=0,
                n_posts_total=0,
                avg_posts_per_ticker=0.0,
                hours_since_last_post=float('inf'),
                api_errors_last_hour=self._api_error_count,
            )
        else:
            # Calculate actual coverage
            actual_tickers = sentiment_data['ticker'].nunique() if 'ticker' in sentiment_data.columns else 0

            # Check for timestamp column
            if 'timestamp' in sentiment_data.columns:
                latest_post = pd.to_datetime(sentiment_data['timestamp']).max()
                hours_since = (reference_time - latest_post).total_seconds() / 3600
            else:
                hours_since = 0.0

            metrics = CoverageMetrics(
                n_expected_tickers=len(expected_tickers),
                n_actual_tickers=actual_tickers,
                n_posts_total=len(sentiment_data),
                avg_posts_per_ticker=len(sentiment_data) / max(actual_tickers, 1),
                hours_since_last_post=hours_since,
                api_errors_last_hour=self._api_error_count,
            )

        # Track coverage history
        self._coverage_history.append(metrics)
        if len(self._coverage_history) > 100:
            self._coverage_history = self._coverage_history[-100:]

        return metrics

    def record_api_error(self) -> None:
        """Record an API error for tracking."""
        self._api_error_count += 1

    def reset_api_errors(self) -> None:
        """Reset API error count (call hourly)."""
        self._api_error_count = 0

    def should_halt_trading(self, metrics: CoverageMetrics) -> bool:
        """
        Determine if trading should be halted due to data issues.

        Args:
            metrics: Current coverage metrics

        Returns:
            True if trading should be halted
        """
        # Halt on complete dropout
        if metrics.quality == DataQuality.DROPOUT:
            return True

        # Halt if data is very stale
        if metrics.hours_since_last_post > self.stale_threshold_hours * 2:
            return True

        # Halt if not enough tickers have data
        if metrics.n_actual_tickers < self.min_tickers_for_trading:
            return True

        return False

    def get_position_size_multiplier(self, quality: DataQuality) -> float:
        """
        Get position size multiplier based on data quality.

        Lower quality = smaller positions to reduce risk.

        Args:
            quality: Current data quality level

        Returns:
            Multiplier for position sizing (0.0 to 1.0)
        """
        multipliers = {
            DataQuality.FULL: 1.0,     # Full positions
            DataQuality.PARTIAL: 0.7,  # 70% of normal
            DataQuality.SPARSE: 0.4,   # 40% of normal
            DataQuality.DROPOUT: 0.0,  # No new positions
        }
        return multipliers.get(quality, 0.0)

    def adjust_signal_weights(
        self,
        quality: DataQuality,
        base_weights: Dict[str, float],
    ) -> Dict[str, float]:
        """
        Adjust signal weights based on data quality.

        When sentiment data is unreliable, reduce sentiment weight
        and increase event-based weights.

        CRITICAL: This does NOT fill in missing data.
        It adjusts the WEIGHTING of available data.

        Args:
            quality: Current data quality
            base_weights: Original signal weights

        Returns:
            Adjusted weights that sum to 1.0
        """
        adjusted = base_weights.copy()

        if quality == DataQuality.FULL:
            # No adjustment needed
            return adjusted

        # Get sentiment-related weights
        sentiment_weight = adjusted.get('intensity', 0.0)
        momentum_weight = adjusted.get('sentiment_volume_momentum', 0.0)

        if quality == DataQuality.PARTIAL:
            # Reduce sentiment weight by 30%
            reduction = 0.3
            removed = (sentiment_weight + momentum_weight) * reduction
            adjusted['intensity'] = sentiment_weight * (1 - reduction)
            adjusted['sentiment_volume_momentum'] = momentum_weight * (1 - reduction)

            # Redistribute to more reliable components
            adjusted['event_severity'] = adjusted.get('event_severity', 0.15) + removed * 0.6
            adjusted['volume'] = adjusted.get('volume', 0.20) + removed * 0.4

        elif quality == DataQuality.SPARSE:
            # Reduce sentiment weight by 70%
            reduction = 0.7
            removed = (sentiment_weight + momentum_weight) * reduction
            adjusted['intensity'] = sentiment_weight * (1 - reduction)
            adjusted['sentiment_volume_momentum'] = momentum_weight * (1 - reduction)

            # Redistribute to event-based components
            adjusted['event_severity'] = adjusted.get('event_severity', 0.15) + removed * 0.5
            adjusted['volume'] = adjusted.get('volume', 0.20) + removed * 0.3
            adjusted['duration'] = adjusted.get('duration', 0.10) + removed * 0.2

        else:  # DROPOUT
            # Zero out sentiment weights entirely
            adjusted['intensity'] = 0.0
            adjusted['sentiment_volume_momentum'] = 0.0

            # Event-only scoring
            total_other = (
                adjusted.get('event_severity', 0.15) +
                adjusted.get('volume', 0.20) +
                adjusted.get('duration', 0.10)
            )

            if total_other > 0:
                scale = 1.0 / total_other
                adjusted['event_severity'] = adjusted.get('event_severity', 0.15) * scale
                adjusted['volume'] = adjusted.get('volume', 0.20) * scale
                adjusted['duration'] = adjusted.get('duration', 0.10) * scale

        # Normalize to sum to 1.0
        active_weights = {k: v for k, v in adjusted.items() if v > 0}
        total = sum(active_weights.values())
        if total > 0:
            for k in active_weights:
                adjusted[k] = active_weights[k] / total

        return adjusted

    def get_tickers_with_coverage(
        self,
        sentiment_data: pd.DataFrame,
    ) -> List[str]:
        """
        Get list of tickers with adequate real data coverage.

        Args:
            sentiment_data: Real sentiment data

        Returns:
            List of tickers meeting minimum data requirements
        """
        if sentiment_data.empty or 'ticker' not in sentiment_data.columns:
            return []

        # Count posts per ticker
        ticker_counts = sentiment_data.groupby('ticker').size()

        # Filter to tickers with minimum posts
        adequate = ticker_counts[ticker_counts >= self.min_posts_per_ticker]

        return adequate.index.tolist()

    def get_coverage_report(self) -> pd.DataFrame:
        """Get report of historical coverage metrics."""
        if not self._coverage_history:
            return pd.DataFrame()

        return pd.DataFrame([
            {
                'expected_tickers': m.n_expected_tickers,
                'actual_tickers': m.n_actual_tickers,
                'coverage_ratio': m.coverage_ratio,
                'total_posts': m.n_posts_total,
                'avg_posts_per_ticker': m.avg_posts_per_ticker,
                'hours_since_last': m.hours_since_last_post,
                'quality': m.quality.name,
                'api_errors': m.api_errors_last_hour,
            }
            for m in self._coverage_history
        ])


class DataQualityMonitor:
    """
    Monitors real data quality over time and alerts on issues.

    Tracks:
    - API availability
    - Data freshness
    - Coverage trends
    """

    def __init__(
        self,
        alert_threshold_hours: int = 4,
        degradation_threshold: float = 0.3,
    ):
        """
        Initialize quality monitor.

        Args:
            alert_threshold_hours: Hours of issues before alerting
            degradation_threshold: Coverage drop ratio to trigger alert
        """
        self.alert_threshold_hours = alert_threshold_hours
        self.degradation_threshold = degradation_threshold

        self._quality_history: List[tuple] = []  # (timestamp, quality)
        self._alerts: List[Dict] = []

    def record_quality(
        self,
        quality: DataQuality,
        timestamp: Optional[datetime] = None,
    ) -> Optional[Dict]:
        """
        Record data quality observation.

        Args:
            quality: Observed data quality
            timestamp: Observation time

        Returns:
            Alert dict if alert triggered, None otherwise
        """
        timestamp = timestamp or datetime.now()
        self._quality_history.append((timestamp, quality))

        # Check for sustained degradation
        alert = self._check_for_alert(timestamp)
        if alert:
            self._alerts.append(alert)

        return alert

    def _check_for_alert(self, current_time: datetime) -> Optional[Dict]:
        """Check if alert should be triggered."""
        if len(self._quality_history) < 4:
            return None

        # Look at recent history
        cutoff = current_time - timedelta(hours=self.alert_threshold_hours)
        recent = [
            (ts, q) for ts, q in self._quality_history
            if ts >= cutoff
        ]

        if len(recent) < 2:
            return None

        # Count quality levels
        qualities = [q for _, q in recent]
        dropout_count = sum(1 for q in qualities if q == DataQuality.DROPOUT)
        sparse_count = sum(1 for q in qualities if q == DataQuality.SPARSE)

        # Alert on sustained issues
        if dropout_count >= len(recent) * 0.5:
            return {
                'type': 'DATA_DROPOUT',
                'timestamp': current_time,
                'message': f'Sustained data dropout: {dropout_count}/{len(recent)} observations',
                'severity': 'HIGH',
            }

        if sparse_count >= len(recent) * 0.7:
            return {
                'type': 'SPARSE_DATA',
                'timestamp': current_time,
                'message': f'Sparse data coverage: {sparse_count}/{len(recent)} observations',
                'severity': 'MEDIUM',
            }

        return None

    def get_alerts(
        self,
        since: Optional[datetime] = None,
    ) -> List[Dict]:
        """Get alerts, optionally filtered by time."""
        if since is None:
            return self._alerts

        return [a for a in self._alerts if a['timestamp'] >= since]
