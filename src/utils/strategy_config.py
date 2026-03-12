"""
Canonical strategy runtime configuration.

Normalizes repo configuration into a single runtime contract so runners,
validation helpers, and tests stop drifting on windows, weighting, exposure,
and risk semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


DEFAULT_SIGNAL_WEIGHTS = {
    'event_severity': 0.20,
    'intensity': 0.40,
    'volume': 0.25,
    'duration': 0.15,
    'sentiment_volume_momentum': 0.0,
}


@dataclass(frozen=True)
class SocialWindowSpec:
    days_before_event: int = 10
    days_after_event: int = 3
    max_posts_per_ticker: int = 500
    source: str = 'multi_source'


@dataclass(frozen=True)
class SentimentSpec:
    mode: str = 'hybrid'
    model_name: str = 'ProsusAI/finbert'
    batch_size: int = 32
    strict: bool = True


@dataclass(frozen=True)
class SignalSpec:
    lookback_window: int = 252
    weight_derivation_method: str = 'inverse_variance'
    weights: Dict[str, float] | None = None
    min_intensity: float = 0.05
    min_volume_ratio: float = 0.0
    min_posts: int = 5
    require_social_data: bool = True
    min_confidence: float = 0.0


@dataclass(frozen=True)
class PortfolioSpec:
    strategy_type: str = 'long_short'
    method: str = 'quintile'
    rebalance_frequency: str = 'W'
    holding_period: int = 49
    selection_balance: str = 'equal_count'
    exposure_model: str = 'dollar_neutral'
    gross_exposure_target: float = 1.0
    max_position: float = 0.08

    @property
    def side_exposure_target(self) -> float:
        """Target gross exposure per side for a neutral book."""
        if self.exposure_model == 'dollar_neutral':
            return self.gross_exposure_target / 2.0
        return self.gross_exposure_target


@dataclass(frozen=True)
class RiskSpec:
    enabled: bool = True
    max_position_size: float = 0.10
    min_positions: int = 2
    target_volatility: float = 0.18
    max_drawdown_threshold: float = 0.15
    adaptive_thresholds: bool = True
    leverage_limit: float = 1.0
    cash_overlay_enabled: bool = False
    regime_aware_equitization: bool = False
    bear_equitization_pct: float = 0.40
    sma_lookback: int = 100


@dataclass(frozen=True)
class ValidationSpec:
    enabled: bool = True
    min_train_months: int = 12
    test_months: int = 3
    step_months: int = 3
    embargo_days: int = 5


@dataclass(frozen=True)
class StrategyRuntimeSpec:
    filing_types: List[str]
    event_confidence_threshold: float
    social_window: SocialWindowSpec
    sentiment: SentimentSpec
    signal: SignalSpec
    portfolio: PortfolioSpec
    risk: RiskSpec
    validation: ValidationSpec


def _normalize_filing_types(raw_types: List[str] | None) -> List[str]:
    """Canonical trading path is 8-K driven; other filings stay research-only."""
    if not raw_types:
        return ['8-K']
    normalized = [str(f).upper() for f in raw_types]
    return ['8-K'] if '8-K' in normalized else ['8-K']


def _resolve_selection_balance(config: Dict[str, Any], portfolio_cfg: Dict[str, Any]) -> str:
    if portfolio_cfg.get('selection_balance'):
        return str(portfolio_cfg['selection_balance'])

    legacy_portfolio = portfolio_cfg.get('balance_long_short')
    legacy_signal = (
        config.get('signals', {})
        .get('quality_filters', {})
        .get('balance_long_short')
    )
    if legacy_portfolio is False or legacy_signal is False:
        return 'none'
    return 'equal_count'


def load_strategy_spec(config: Dict[str, Any]) -> StrategyRuntimeSpec:
    """
    Normalize strategy config into a canonical runtime contract.
    """
    data_cfg = config.get('data', {})
    social_cfg = data_cfg.get('social_media', {})
    nlp_cfg = config.get('nlp', {})
    sentiment_cfg = nlp_cfg.get('sentiment_analyzer', {})
    signals_cfg = config.get('signals', {})
    quality_cfg = signals_cfg.get('quality_filters', {})
    portfolio_cfg = config.get('portfolio', {})
    risk_cfg = config.get('risk_management', {})
    validation_cfg = config.get('validation', {})
    cash_cfg = risk_cfg.get('cash_equitization', {})

    weights = dict(DEFAULT_SIGNAL_WEIGHTS)
    weights.update(signals_cfg.get('weights', {}))

    portfolio_spec = PortfolioSpec(
        strategy_type=portfolio_cfg.get('strategy_type', 'long_short'),
        method=portfolio_cfg.get('method', 'quintile'),
        rebalance_frequency=portfolio_cfg.get('rebalance_frequency', 'W'),
        holding_period=int(portfolio_cfg.get('holding_period', 49)),
        selection_balance=_resolve_selection_balance(config, portfolio_cfg),
        exposure_model=portfolio_cfg.get('exposure_model', 'dollar_neutral'),
        gross_exposure_target=float(portfolio_cfg.get('gross_exposure_target', 1.0)),
        max_position=float(portfolio_cfg.get('max_position', 0.08)),
    )

    return StrategyRuntimeSpec(
        filing_types=_normalize_filing_types(data_cfg.get('sec', {}).get('filing_types')),
        event_confidence_threshold=float(
            nlp_cfg.get('event_detector', {}).get('confidence_threshold', 0.25)
        ),
        social_window=SocialWindowSpec(
            days_before_event=int(social_cfg.get('days_before_event', 10)),
            days_after_event=int(social_cfg.get('days_after_event', 3)),
            max_posts_per_ticker=int(social_cfg.get('max_posts_per_ticker', 500)),
            source=str(social_cfg.get('source', 'multi_source')),
        ),
        sentiment=SentimentSpec(
            mode=str(sentiment_cfg.get('mode', 'hybrid')),
            model_name=str(sentiment_cfg.get('model', 'ProsusAI/finbert')),
            batch_size=int(sentiment_cfg.get('batch_size', 32)),
            strict=bool(sentiment_cfg.get('strict', True)),
        ),
        signal=SignalSpec(
            lookback_window=int(signals_cfg.get('lookback_window', 252)),
            weight_derivation_method=str(
                signals_cfg.get('weight_derivation_method', 'inverse_variance')
            ),
            weights=weights,
            min_intensity=float(quality_cfg.get('min_intensity', 0.05)),
            min_volume_ratio=float(quality_cfg.get('min_volume_ratio', 0.0)),
            min_posts=int(quality_cfg.get('min_posts', 5)),
            require_social_data=bool(quality_cfg.get('require_social_data', True)),
            min_confidence=float(quality_cfg.get('min_confidence', 0.0)),
        ),
        portfolio=portfolio_spec,
        risk=RiskSpec(
            enabled=bool(risk_cfg.get('enabled', True)),
            max_position_size=float(risk_cfg.get('max_position_size', 0.10)),
            min_positions=int(risk_cfg.get('min_positions', 2)),
            target_volatility=float(risk_cfg.get('target_volatility', 0.18)),
            max_drawdown_threshold=float(risk_cfg.get('max_drawdown_threshold', 0.15)),
            adaptive_thresholds=bool(risk_cfg.get('adaptive_thresholds', True)),
            leverage_limit=float(risk_cfg.get('leverage_limit', portfolio_spec.gross_exposure_target)),
            cash_overlay_enabled=bool(cash_cfg.get('enabled', False)),
            regime_aware_equitization=bool(cash_cfg.get('regime_aware', False)),
            bear_equitization_pct=float(cash_cfg.get('bear_equitization_pct', 0.40)),
            sma_lookback=int(cash_cfg.get('sma_lookback', 100)),
        ),
        validation=ValidationSpec(
            enabled=bool(validation_cfg.get('enabled', True)),
            min_train_months=int(validation_cfg.get('min_train_months', 12)),
            test_months=int(validation_cfg.get('test_months', 3)),
            step_months=int(validation_cfg.get('step_months', 3)),
            embargo_days=int(validation_cfg.get('embargo_days', 5)),
        ),
    )
