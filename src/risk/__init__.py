"""
Risk Management Modules
Implements comprehensive risk controls for the strategy

AUDIT REFACTOR (Jan 2026):
- Added AdaptiveDrawdownConfig for statistically-derived thresholds
- Added ScandalDetector and FlashCrashCircuitBreaker for edge cases
- Added SentimentDropoutHandler for data quality issues
- Added RegimeChangeDetector for parameter recalibration triggers
"""

from .risk_manager import RiskManager
from .position_sizer import PositionSizer
from .drawdown_controller import DrawdownController, AdaptiveDrawdownConfig
from .scandal_detector import (
    ScandalDetector,
    FlashCrashCircuitBreaker,
    ScandalSignal,
    ScandalSeverity,
)
from .dropout_handler import (
    SentimentDropoutHandler,
    DataQuality,
    CoverageMetrics,
    DataQualityMonitor,
)
from .regime_detector import (
    RegimeChangeDetector,
    RegimeType,
    RegimeChangeSignal,
)

__all__ = [
    # Core risk management
    'RiskManager',
    'PositionSizer',
    'DrawdownController',
    'AdaptiveDrawdownConfig',
    # Scandal detection (edge case)
    'ScandalDetector',
    'FlashCrashCircuitBreaker',
    'ScandalSignal',
    'ScandalSeverity',
    # Data dropout handling (edge case)
    'SentimentDropoutHandler',
    'DataQuality',
    'CoverageMetrics',
    'DataQualityMonitor',
    # Regime change detection
    'RegimeChangeDetector',
    'RegimeType',
    'RegimeChangeSignal',
]
