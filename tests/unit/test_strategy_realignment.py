"""
Regression tests for the canonical strategy realignment.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from src.data.esg_universe import ESGSensitiveUniverse
from src.nlp.event_detector import ESGEventDetector
from src.nlp.feature_extractor import ReactionFeatureExtractor
from src.signals.signal_generator import ESGSignalGenerator
from src.utils.strategy_config import load_strategy_spec
import src.nlp.sentiment_analyzer as sentiment_module


def test_load_strategy_spec_normalizes_canonical_contract(baseline_config):
    spec = load_strategy_spec(baseline_config)

    assert spec.filing_types == ["8-K"]
    assert spec.event_confidence_threshold == pytest.approx(0.20)
    assert spec.social_window.days_before_event == 10
    assert spec.social_window.days_after_event == 3
    assert spec.social_window.max_posts_per_ticker == 500
    assert spec.sentiment.mode == "hybrid"
    assert spec.sentiment.strict is True
    assert spec.signal.lookback_window == 252
    assert spec.signal.weight_derivation_method == "inverse_variance"
    assert spec.portfolio.rebalance_frequency == "W"
    assert spec.portfolio.holding_period == 49
    assert spec.portfolio.selection_balance == "equal_count"
    assert spec.portfolio.exposure_model == "dollar_neutral"
    assert spec.portfolio.gross_exposure_target == pytest.approx(1.0)
    assert spec.risk.cash_overlay_enabled is False
    assert spec.risk.leverage_limit == pytest.approx(1.0)


def test_feature_extractor_reuses_precomputed_sentiment():
    class StubAnalyzer:
        active_mode = "hybrid"

        def __init__(self):
            self.calls = []

        def analyze_batch(self, texts):
            self.calls.append(list(texts))
            return [{"label": "negative", "score": 0.6} for _ in texts]

        @staticmethod
        def score_to_numeric(result):
            return -float(result["score"])

    analyzer = StubAnalyzer()
    extractor = ReactionFeatureExtractor(analyzer)
    event_date = datetime(2024, 1, 15)
    posts = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-01-14 09:00:00",
                    "2024-01-15 12:00:00",
                    "2024-01-16 15:00:00",
                ]
            ),
            "text": ["pre-scored", "needs model", "also pre-scored"],
            "sentiment": [0.3, None, -0.2],
            "retweets": [2, 4, 1],
            "likes": [5, 8, 3],
            "user_followers": [100, 250, 80],
        }
    )

    features = extractor.extract_features(posts, event_date)

    assert analyzer.calls == [["needs model"]]
    assert features["n_tweets"] == 3
    assert features["n_pre_event"] == 1
    assert features["n_post_event"] == 2
    assert features["sentiment_mode"] == "hybrid"


def test_hybrid_sentiment_mode_uses_advanced_analyzer(monkeypatch):
    class FakeAdvancedAnalyzer:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.use_transformer = True

        def analyze_batch(self, texts):
            return [{"adjusted_score": 0.25, "label": "positive"} for _ in texts]

        def analyze_with_features(self, text):
            return {"adjusted_score": 0.25, "label": "positive"}

        def get_model_info(self):
            return {"transformer_enabled": True}

    monkeypatch.setattr(sentiment_module, "ADVANCED_AVAILABLE", True)
    monkeypatch.setattr(sentiment_module, "AdvancedSentimentAnalyzer", FakeAdvancedAnalyzer)

    analyzer = sentiment_module.FinancialSentimentAnalyzer(mode="hybrid", strict=True)

    assert analyzer.active_mode == "hybrid"
    assert analyzer.score_to_numeric(analyzer.analyze_single("clean energy investment")) == pytest.approx(0.25)
    assert analyzer.get_model_info()["requested_mode"] == "hybrid"


def test_hybrid_sentiment_mode_fails_closed_when_unavailable(monkeypatch):
    monkeypatch.setattr(sentiment_module, "ADVANCED_AVAILABLE", False)

    with pytest.raises(RuntimeError, match="Hybrid sentiment mode requested"):
        sentiment_module.FinancialSentimentAnalyzer(mode="hybrid", strict=True)


def test_events_without_social_data_do_not_create_directional_signals(baseline_config):
    generator = ESGSignalGenerator(weights=baseline_config["signals"]["weights"])
    event = {
        "ticker": "AAPL",
        "date": datetime(2024, 1, 15),
        "event_features": {
            "category": "E",
            "confidence": 0.8,
            "sentiment": "negative",
        },
        "reaction_features": {
            "intensity": 0.0,
            "volume_ratio": 1.0,
            "duration_days": 0,
            "n_tweets": 0,
        },
    }

    strict_df = generator.generate_signals_batch(
        [event],
        min_posts=5,
        require_social_data=True,
        min_volume_ratio=0.0,
        min_intensity=0.0,
        min_confidence=0.0,
    )
    permissive_df = generator.generate_signals_batch(
        [event],
        min_posts=0,
        require_social_data=False,
        min_volume_ratio=0.0,
        min_intensity=0.0,
        min_confidence=0.0,
    )

    assert strict_df.empty
    assert len(permissive_df) == 1
    assert permissive_df.iloc[0]["raw_score"] == pytest.approx(0.0)
    assert permissive_df.iloc[0]["signal"] == pytest.approx(0.0)
    assert permissive_df.iloc[0]["quintile"] == 3


def test_esg_universe_all_is_broader_than_medium():
    universe = ESGSensitiveUniverse()

    medium = set(universe.get_esg_sensitive_nasdaq100("MEDIUM"))
    all_tickers = set(universe.get_esg_sensitive_nasdaq100("ALL"))

    assert medium
    assert len(all_tickers) > len(medium)
    assert medium.issubset(all_tickers)


def test_event_detector_captures_negative_environmental_event():
    detector = ESGEventDetector()

    result = detector.detect_event(
        "The company disclosed an EPA violation and environmental fine after an oil spill.",
        threshold=0.1,
    )

    assert result["has_event"] is True
    assert result["category"] == "E"
    assert result["sentiment"] == "negative"
    assert result["confidence"] >= 0.1
