"""
Scandal Detection and Flash Crash Circuit Breaker

Detects sudden ESG scandals from real social media data and applies
protective circuit breakers to prevent catastrophic losses.

CRITICAL: This module works with REAL data only:
- Real Reddit posts from PRAW API
- Real SEC filings from EDGAR
- Real price data from yfinance

No simulated or mock signals are used in production.

Edge Case Addressed:
- ESG scandal flash crash (e.g., fraud discovery, environmental disaster)
- Sudden sentiment collapse with volume spike
- Correlated position exposure during sector-wide events
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, FrozenSet
from enum import Enum, auto


class ScandalSeverity(Enum):
    """Severity levels for detected scandals."""
    LOW = auto()       # Minor negative news
    MEDIUM = auto()    # Significant ESG concern
    HIGH = auto()      # Major scandal
    CRITICAL = auto()  # Flash crash risk


@dataclass
class ScandalSignal:
    """
    Detected scandal signal from real social media data.

    All fields derived from actual posts, not simulated.
    """
    ticker: str
    timestamp: datetime
    severity: ScandalSeverity
    category: str  # E, S, or G
    volume_spike: float  # Multiple of normal volume
    sentiment_crash: float  # Negative sentiment magnitude
    n_posts: int  # Number of real posts analyzed
    matched_keywords: List[str] = field(default_factory=list)
    source_posts: List[str] = field(default_factory=list)  # Sample post IDs for audit

    @property
    def is_flash_crash_risk(self) -> bool:
        """Check if this could trigger flash crash."""
        return (
            self.severity in (ScandalSeverity.HIGH, ScandalSeverity.CRITICAL) and
            self.volume_spike > 5.0 and
            self.sentiment_crash < -0.7
        )

    @property
    def confidence(self) -> float:
        """Confidence score based on data quality."""
        # More posts = higher confidence
        post_confidence = min(self.n_posts / 50.0, 1.0)
        # Stronger signal = higher confidence
        signal_strength = min(abs(self.sentiment_crash) + self.volume_spike / 10.0, 1.0)
        return 0.6 * post_confidence + 0.4 * signal_strength


# Scandal keywords - these are real terms that indicate ESG problems
# Used to filter and score REAL social media posts
SCANDAL_KEYWORDS: FrozenSet[str] = frozenset([
    # Governance scandals
    'fraud', 'scandal', 'investigation', 'indictment', 'sec probe',
    'ceo arrest', 'cfo arrest', 'accounting fraud', 'embezzlement',
    'insider trading', 'class action', 'shareholder lawsuit',
    'restatement', 'material weakness', 'audit failure',

    # Environmental disasters
    'oil spill', 'chemical leak', 'pollution incident', 'epa violation',
    'environmental disaster', 'toxic waste', 'contamination',
    'emissions scandal', 'greenwashing', 'environmental fine',

    # Social scandals
    'discrimination lawsuit', 'harassment', 'labor violation',
    'workplace safety', 'osha violation', 'product recall',
    'data breach', 'privacy violation', 'whistleblower',
])


class ScandalDetector:
    """
    Real-time scandal detection from actual social media data.

    Works with REAL data sources:
    - Reddit posts via PRAW API
    - Twitter posts via API
    - SEC filings via EDGAR

    No simulated data in production.
    """

    def __init__(
        self,
        volume_spike_threshold: float = 5.0,
        sentiment_crash_threshold: float = -0.5,
        min_posts_for_detection: int = 10,
        lookback_hours: int = 24,
    ):
        """
        Initialize scandal detector.

        Args:
            volume_spike_threshold: Post volume multiple to trigger alert
            sentiment_crash_threshold: Sentiment level to trigger alert
            min_posts_for_detection: Minimum posts required for reliable detection
            lookback_hours: Hours of recent data to analyze
        """
        self.volume_spike_threshold = volume_spike_threshold
        self.sentiment_crash_threshold = sentiment_crash_threshold
        self.min_posts_for_detection = min_posts_for_detection
        self.lookback_hours = lookback_hours

        # Baseline metrics from real historical data
        self._baseline_volumes: Dict[str, float] = {}
        self._baseline_sentiment: Dict[str, float] = {}
        self._last_update: Dict[str, datetime] = {}

    def update_baselines(
        self,
        ticker: str,
        historical_posts: pd.DataFrame,
    ) -> None:
        """
        Update baseline metrics from real historical posts.

        Args:
            ticker: Stock ticker
            historical_posts: DataFrame with real posts (timestamp, sentiment columns)
        """
        if historical_posts.empty or len(historical_posts) < 20:
            return

        # Calculate baseline posting volume (posts per day)
        date_range = (
            historical_posts['timestamp'].max() -
            historical_posts['timestamp'].min()
        )
        days = max(date_range.days, 1)
        self._baseline_volumes[ticker] = len(historical_posts) / days

        # Calculate baseline sentiment
        if 'sentiment' in historical_posts.columns:
            self._baseline_sentiment[ticker] = historical_posts['sentiment'].mean()
        else:
            self._baseline_sentiment[ticker] = 0.0

        self._last_update[ticker] = datetime.now()

    def detect_scandal(
        self,
        ticker: str,
        recent_posts: pd.DataFrame,
        reference_time: Optional[datetime] = None,
    ) -> Optional[ScandalSignal]:
        """
        Detect if a scandal is occurring from real social media data.

        Args:
            ticker: Stock ticker
            recent_posts: DataFrame with recent REAL posts
                Required columns: timestamp, text, sentiment
            reference_time: Reference time for analysis (default: now)

        Returns:
            ScandalSignal if detected, None otherwise
        """
        if recent_posts.empty:
            return None

        if len(recent_posts) < self.min_posts_for_detection:
            return None

        reference_time = reference_time or datetime.now()

        # Filter to lookback window
        cutoff = reference_time - timedelta(hours=self.lookback_hours)
        window_posts = recent_posts[recent_posts['timestamp'] >= cutoff]

        if len(window_posts) < self.min_posts_for_detection:
            return None

        # Calculate volume spike
        baseline_vol = self._baseline_volumes.get(ticker, 10.0)
        hours_in_window = min(self.lookback_hours, 24)
        current_vol = len(window_posts) / (hours_in_window / 24)
        volume_spike = current_vol / max(baseline_vol, 1.0)

        # Calculate sentiment crash
        baseline_sent = self._baseline_sentiment.get(ticker, 0.0)
        current_sent = window_posts['sentiment'].mean()
        sentiment_crash = current_sent - baseline_sent

        # Check for scandal keywords in real post text
        matched_keywords = []
        scandal_post_count = 0

        for _, row in window_posts.iterrows():
            text = str(row.get('text', '')).lower()
            for keyword in SCANDAL_KEYWORDS:
                if keyword in text:
                    if keyword not in matched_keywords:
                        matched_keywords.append(keyword)
                    scandal_post_count += 1
                    break

        # Calculate severity
        severity = self._calculate_severity(
            volume_spike=volume_spike,
            sentiment_crash=sentiment_crash,
            keyword_matches=len(matched_keywords),
            scandal_post_ratio=scandal_post_count / len(window_posts),
        )

        # Only return signal if severity warrants it
        if severity == ScandalSeverity.LOW and len(matched_keywords) == 0:
            return None

        # Determine ESG category from keywords
        category = self._determine_category(matched_keywords)

        # Get sample post IDs for audit trail
        source_posts = window_posts['id'].head(5).tolist() if 'id' in window_posts.columns else []

        return ScandalSignal(
            ticker=ticker,
            timestamp=reference_time,
            severity=severity,
            category=category,
            volume_spike=volume_spike,
            sentiment_crash=sentiment_crash,
            n_posts=len(window_posts),
            matched_keywords=matched_keywords,
            source_posts=source_posts,
        )

    def _calculate_severity(
        self,
        volume_spike: float,
        sentiment_crash: float,
        keyword_matches: int,
        scandal_post_ratio: float,
    ) -> ScandalSeverity:
        """Calculate scandal severity from metrics."""
        # Composite score
        score = 0.0

        # Volume spike contribution
        if volume_spike > 10.0:
            score += 0.4
        elif volume_spike > 5.0:
            score += 0.25
        elif volume_spike > 2.5:
            score += 0.1

        # Sentiment crash contribution
        if sentiment_crash < -0.8:
            score += 0.4
        elif sentiment_crash < -0.5:
            score += 0.25
        elif sentiment_crash < -0.3:
            score += 0.1

        # Keyword contribution
        if keyword_matches >= 5:
            score += 0.2
        elif keyword_matches >= 2:
            score += 0.1

        # Map score to severity
        if score >= 0.8:
            return ScandalSeverity.CRITICAL
        elif score >= 0.5:
            return ScandalSeverity.HIGH
        elif score >= 0.3:
            return ScandalSeverity.MEDIUM
        else:
            return ScandalSeverity.LOW

    def _determine_category(self, keywords: List[str]) -> str:
        """Determine ESG category from matched keywords."""
        e_keywords = {'oil spill', 'pollution', 'epa', 'environmental', 'emissions', 'contamination'}
        s_keywords = {'discrimination', 'harassment', 'labor', 'workplace', 'osha', 'recall', 'breach'}
        g_keywords = {'fraud', 'scandal', 'sec', 'accounting', 'insider', 'lawsuit', 'indictment'}

        e_count = sum(1 for k in keywords if any(ek in k for ek in e_keywords))
        s_count = sum(1 for k in keywords if any(sk in k for sk in s_keywords))
        g_count = sum(1 for k in keywords if any(gk in k for gk in g_keywords))

        if e_count >= s_count and e_count >= g_count:
            return 'E'
        elif s_count >= g_count:
            return 'S'
        else:
            return 'G'


class FlashCrashCircuitBreaker:
    """
    Circuit breaker for flash crash scenarios.

    Protects against catastrophic losses from sudden ESG scandals
    detected in REAL social media data.

    Actions:
    1. Halt new positions in affected ticker
    2. Reduce exposure in correlated tickers
    3. Increase cash buffer
    """

    def __init__(
        self,
        max_single_day_loss: float = 0.03,  # 3% single position loss threshold
        correlation_threshold: float = 0.6,  # Correlation level for related exposure
        halt_duration_hours: int = 24,  # Default halt duration
    ):
        self.max_single_day_loss = max_single_day_loss
        self.correlation_threshold = correlation_threshold
        self.halt_duration_hours = halt_duration_hours

        self._halted_tickers: Set[str] = set()
        self._halt_expiry: Dict[str, datetime] = {}
        self._scandal_log: List[ScandalSignal] = []

    def process_scandal(
        self,
        scandal: ScandalSignal,
    ) -> Dict[str, any]:
        """
        Process detected scandal and determine actions.

        Args:
            scandal: Detected scandal signal from real data

        Returns:
            Dictionary with recommended actions
        """
        actions = {
            'halt_ticker': False,
            'reduce_exposure': False,
            'exposure_reduction': 0.0,
            'alert_level': 'INFO',
        }

        # Log scandal for audit
        self._scandal_log.append(scandal)

        if scandal.severity == ScandalSeverity.CRITICAL:
            # Critical: immediate halt
            self._halt_ticker(scandal.ticker, hours=self.halt_duration_hours * 2)
            actions['halt_ticker'] = True
            actions['reduce_exposure'] = True
            actions['exposure_reduction'] = 0.5  # Reduce all exposure by 50%
            actions['alert_level'] = 'CRITICAL'

        elif scandal.severity == ScandalSeverity.HIGH:
            # High: halt and partial exposure reduction
            self._halt_ticker(scandal.ticker, hours=self.halt_duration_hours)
            actions['halt_ticker'] = True
            actions['reduce_exposure'] = True
            actions['exposure_reduction'] = 0.25
            actions['alert_level'] = 'HIGH'

        elif scandal.severity == ScandalSeverity.MEDIUM:
            # Medium: temporary halt only
            self._halt_ticker(scandal.ticker, hours=self.halt_duration_hours // 2)
            actions['halt_ticker'] = True
            actions['alert_level'] = 'MEDIUM'

        return actions

    def _halt_ticker(self, ticker: str, hours: int) -> None:
        """Halt trading for a ticker."""
        self._halted_tickers.add(ticker)
        self._halt_expiry[ticker] = datetime.now() + timedelta(hours=hours)
        print(f"CIRCUIT BREAKER: Halted {ticker} for {hours} hours")

    def is_halted(self, ticker: str) -> bool:
        """Check if ticker is currently halted."""
        if ticker not in self._halted_tickers:
            return False

        # Check if halt has expired
        expiry = self._halt_expiry.get(ticker)
        if expiry and datetime.now() > expiry:
            self._halted_tickers.discard(ticker)
            del self._halt_expiry[ticker]
            return False

        return True

    def clear_expired_halts(self) -> List[str]:
        """Clear expired halts and return list of cleared tickers."""
        now = datetime.now()
        cleared = []

        for ticker, expiry in list(self._halt_expiry.items()):
            if now > expiry:
                self._halted_tickers.discard(ticker)
                del self._halt_expiry[ticker]
                cleared.append(ticker)

        return cleared

    def adjust_portfolio_for_halts(
        self,
        portfolio: pd.DataFrame,
        correlation_matrix: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Adjust portfolio weights based on halted tickers.

        Args:
            portfolio: Portfolio DataFrame with ticker and weight columns
            correlation_matrix: Optional correlation matrix for related exposure

        Returns:
            Adjusted portfolio
        """
        if portfolio.empty:
            return portfolio

        adjusted = portfolio.copy()

        for halted in self._halted_tickers:
            # Zero out halted ticker
            mask = adjusted['ticker'] == halted
            if mask.any():
                adjusted.loc[mask, 'weight'] = 0
                print(f"CIRCUIT BREAKER: Zeroed {halted} position")

            # Reduce correlated positions if matrix provided
            if correlation_matrix is not None and halted in correlation_matrix.columns:
                correlated = correlation_matrix[halted][
                    correlation_matrix[halted].abs() > self.correlation_threshold
                ].index

                for corr_ticker in correlated:
                    if corr_ticker != halted:
                        mask = adjusted['ticker'] == corr_ticker
                        if mask.any():
                            adjusted.loc[mask, 'weight'] *= 0.5
                            print(f"CIRCUIT BREAKER: Reduced {corr_ticker} (correlated with {halted})")

        return adjusted

    def get_scandal_report(self) -> pd.DataFrame:
        """Get report of all detected scandals."""
        if not self._scandal_log:
            return pd.DataFrame()

        return pd.DataFrame([
            {
                'ticker': s.ticker,
                'timestamp': s.timestamp,
                'severity': s.severity.name,
                'category': s.category,
                'volume_spike': s.volume_spike,
                'sentiment_crash': s.sentiment_crash,
                'n_posts': s.n_posts,
                'keywords': ', '.join(s.matched_keywords),
            }
            for s in self._scandal_log
        ])
