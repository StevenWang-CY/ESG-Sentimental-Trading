"""
Runtime-path smoke and regression tests.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime

import pandas as pd
import pytest

import run_production
from src.backtest.engine import BacktestEngine, BacktestResult
from src.backtest.metrics import PerformanceAnalyzer
from src.validation.walk_forward_validator import create_backtest_function


def _make_price_panel(dates, tickers):
    rows = []
    for ticker in tickers:
        base = 100.0 if ticker == "AAA" else 80.0
        for idx, date in enumerate(dates):
            price = base + idx * (1.5 if ticker == "AAA" else -0.8)
            rows.append(
                {
                    "date": date,
                    "ticker": ticker,
                    "Close": price,
                    "Adj Close": price,
                    "Volume": 1_000_000,
                }
            )
    return pd.DataFrame(rows).set_index(["date", "ticker"]).sort_index()


def test_backtest_engine_runs_dollar_neutral_smoke():
    dates = pd.date_range("2024-01-01", periods=8, freq="B")
    prices = _make_price_panel(dates, ["AAA", "BBB"])
    signals = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "AAA", "BBB"],
            "date": [dates[0], dates[0], dates[4], dates[4]],
            "weight": [0.5, -0.5, 0.5, -0.5],
        }
    )

    engine = BacktestEngine(
        prices=prices,
        initial_capital=1_000_000,
        enable_risk_management=False,
    )
    result = engine.run(signals=signals, rebalance_freq="D", holding_period=3)

    assert not result.trades.empty
    assert len(result.trades) >= 4
    assert len(result.get_daily_returns()) > 0
    assert result.get_final_value() > 0


def test_performance_analyzer_generates_metrics():
    returns = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-02", periods=5, freq="B"),
            "return": [0.01, -0.004, 0.006, 0.002, 0.005],
        }
    )
    portfolio_values = pd.DataFrame(
        {
            "date": returns["date"],
            "value": [1_000_000, 1_010_000, 1_005_960, 1_011_996, 1_014_020],
        }
    )
    trades = pd.DataFrame(
        {
            "date": [returns["date"].iloc[0]],
            "ticker": ["AAA"],
            "shares": [100],
            "price": [100.0],
            "value": [10_000.0],
        }
    )
    result = BacktestResult(
        portfolio_values=portfolio_values,
        returns=returns,
        trades=trades,
        positions=pd.DataFrame(),
        initial_capital=1_000_000,
    )

    metrics = PerformanceAnalyzer(result).generate_tear_sheet()

    assert metrics["returns"]["annualized_return"] == pytest.approx(metrics["returns"]["cagr"])
    assert metrics["trading"]["num_trades"] == 1
    assert metrics["risk"]["volatility"] >= 0.0
    assert metrics["summary"]["final_value"] == pytest.approx(result.get_final_value())


def test_create_backtest_function_uses_runtime_parameters():
    captured = {}

    class FakeResult:
        def __init__(self):
            self.trades = pd.DataFrame([{"value": 10_000.0}])

        @staticmethod
        def get_daily_returns():
            return pd.Series([0.01, -0.005, 0.007], index=pd.date_range("2024-01-01", periods=3))

        @staticmethod
        def get_total_return():
            return 0.12

        @staticmethod
        def get_equity_curve():
            return pd.Series([1_000_000, 1_010_000, 1_020_000], index=pd.date_range("2024-01-01", periods=3))

    class FakeEngine:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def run(self, signals, rebalance_freq, holding_period):
            captured["run"] = {
                "signals": signals.copy(),
                "rebalance_freq": rebalance_freq,
                "holding_period": holding_period,
            }
            return FakeResult()

    backtest_fn = create_backtest_function(
        FakeEngine,
        rebalance_freq="W",
        holding_period=49,
        enable_risk_management=True,
        max_position_size=0.10,
        target_volatility=0.18,
        max_drawdown_threshold=0.15,
        adaptive_drawdown_thresholds=True,
        leverage_limit=1.0,
        balance_long_short=True,
    )

    prices = _make_price_panel(pd.date_range("2024-01-01", periods=5, freq="B"), ["AAA", "BBB"])
    signals = pd.DataFrame({"ticker": ["AAA"], "date": [pd.Timestamp("2024-01-03")], "weight": [0.5]})

    sharpe, n_trades, total_return, max_dd = backtest_fn(
        signals=signals,
        prices=prices,
        weights={},
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 1, 10),
    )

    assert captured["init"]["enable_risk_management"] is True
    assert captured["init"]["max_position_size"] == pytest.approx(0.10)
    assert captured["init"]["leverage_limit"] == pytest.approx(1.0)
    assert captured["init"]["balance_long_short"] is True
    assert captured["run"]["rebalance_freq"] == "W"
    assert captured["run"]["holding_period"] == 49
    assert n_trades == 1
    assert total_return == pytest.approx(0.12)
    assert sharpe != 0.0
    assert max_dd == pytest.approx(0.0)


def test_run_production_smoke_uses_canonical_runtime_contract(monkeypatch, tmp_path, baseline_config):
    config = copy.deepcopy(baseline_config)
    config["logging"] = {"level": "INFO", "log_file": None}
    config["data"]["sec"].update({"company_name": "Test", "email": "test@example.com"})
    config["data"]["multi_source"] = {"sources": ["arctic_shift", "gdelt", "stocktwits"]}

    captured = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        run_production,
        "setup_logging",
        lambda **kwargs: logging.getLogger("run-production-test"),
    )
    monkeypatch.setattr(run_production, "load_config", lambda path: config)
    monkeypatch.setattr(run_production, "validate_social_media_config", lambda cfg: (True, "multi_source"))

    class FakeUniverseFetcher:
        @staticmethod
        def get_esg_sensitive_nasdaq100(sensitivity):
            return ["AAA", "BBB"]

    class FakeSECDownloader:
        def __init__(self, **kwargs):
            pass

        @staticmethod
        def fetch_filings(tickers, filing_type, start_date, end_date):
            return [
                {
                    "ticker": tickers[0],
                    "date": "2024-01-12",
                    "filing_type": filing_type,
                    "text": "The company disclosed an oil spill and environmental fine.",
                }
            ]

    class FakePriceFetcher:
        @staticmethod
        def fetch_price_data(tickers, start_date, end_date):
            dates = pd.date_range(start_date, end_date, freq="B")
            return _make_price_panel(dates, tickers)

    class FakeFamaFrenchFactors:
        @staticmethod
        def load_ff_factors(start_date, end_date, frequency):
            return pd.DataFrame({"Mkt-RF": [0.0]}, index=pd.date_range(start_date, periods=1))

    class FakeSECFilingParser:
        @staticmethod
        def extract_text(file_path):
            return "The company disclosed an oil spill and environmental fine."

        @staticmethod
        def extract_esg_relevant_sections(text, filing_type=None):
            return text

    class FakeTextCleaner:
        @staticmethod
        def clean_for_sentiment_analysis(text):
            return text

    class FakeEventDetector:
        @staticmethod
        def detect_event(text, threshold=0.0):
            return {
                "has_event": True,
                "category": "E",
                "confidence": 0.6,
                "sentiment": "negative",
            }

    class FakeSentimentAnalyzer:
        def __init__(self, model_name, mode, batch_size, strict):
            captured["sentiment_init"] = {
                "model_name": model_name,
                "mode": mode,
                "batch_size": batch_size,
                "strict": strict,
            }
            self.requested_mode = mode
            self.active_mode = mode

    class FakeReactionFeatureExtractor:
        def __init__(self, analyzer):
            self.analyzer = analyzer

        @staticmethod
        def extract_features(posts_df, event_date):
            return {
                "intensity": -0.4,
                "volume_ratio": 1.8,
                "duration_days": 2,
                "n_tweets": 12,
                "n_pre_event": 3,
                "n_post_event": 9,
                "sentiment_mode": "hybrid",
            }

        @staticmethod
        def _get_default_features():
            return {
                "intensity": 0.0,
                "volume_ratio": 1.0,
                "duration_days": 0,
                "n_tweets": 0,
                "n_pre_event": 0,
                "n_post_event": 0,
                "sentiment_mode": "hybrid",
            }

    class FakeMultiSourceFetcher:
        def __init__(self, **kwargs):
            captured["multi_source_init"] = kwargs
            self.last_source_metrics = {"n_sources": 3, "source_agreement": 1.0}

        @staticmethod
        def fetch_tweets_for_event(ticker, event_date, keywords, days_before, days_after, max_results):
            return pd.DataFrame(
                {
                    "timestamp": [event_date],
                    "text": ["environmental backlash"],
                    "sentiment": [-0.4],
                }
            )

    class FakeSignalGenerator:
        def __init__(self, **kwargs):
            captured["signal_generator_init"] = kwargs

        @staticmethod
        def generate_signals_batch(events_data, **kwargs):
            captured["signal_generator_batch"] = kwargs
            return pd.DataFrame(
                {
                    "ticker": ["AAA", "BBB"],
                    "date": pd.to_datetime(["2024-01-12", "2024-01-12"]),
                    "raw_score": [0.4, -0.4],
                    "z_score": [1.0, -1.0],
                    "signal": [0.76, -0.76],
                    "quintile": [5, 1],
                    "event_category": ["E", "E"],
                    "event_confidence": [0.6, 0.6],
                    "sentiment_intensity": [0.4, -0.4],
                    "volume_ratio": [1.8, 1.7],
                    "n_posts": [12, 11],
                    "has_social_data": [True, True],
                    "confidence": [0.8, 0.8],
                }
            )

    class FakePortfolioConstructor:
        def __init__(self, **kwargs):
            captured["portfolio_init"] = kwargs

        @staticmethod
        def construct_portfolio(signals_df, **kwargs):
            captured["portfolio_construct"] = kwargs
            return pd.DataFrame(
                {
                    "ticker": ["AAA", "BBB"],
                    "date": pd.to_datetime(["2024-01-12", "2024-01-12"]),
                    "weight": [0.5, -0.5],
                }
            )

        @staticmethod
        def apply_position_limits(portfolio, max_position):
            captured["portfolio_limit"] = max_position
            return portfolio

        @staticmethod
        def get_portfolio_statistics(portfolio):
            return {
                "n_positions": 2,
                "n_long": 1,
                "n_short": 1,
                "net_exposure": 0.0,
                "gross_exposure": 1.0,
            }

    class FakeResult:
        @staticmethod
        def get_final_value():
            return 1_025_000.0

        @staticmethod
        def get_total_return():
            return 0.025

        @staticmethod
        def get_daily_returns():
            return pd.Series([0.01, -0.005, 0.007], index=pd.date_range("2024-01-01", periods=3))

    class FakeBacktestEngine:
        def __init__(self, **kwargs):
            captured["backtest_init"] = kwargs

        @staticmethod
        def run(signals, rebalance_freq, holding_period):
            captured["backtest_run"] = {
                "signals": signals.copy(),
                "rebalance_freq": rebalance_freq,
                "holding_period": holding_period,
            }
            return FakeResult()

    class FakePerformanceAnalyzer:
        def __init__(self, results):
            pass

        @staticmethod
        def print_tear_sheet():
            return None

    class FakeFactorAnalysis:
        @staticmethod
        def load_factors(factors):
            return None

        @staticmethod
        def run_regression(returns):
            return {
                "alpha_annualized": 0.01,
                "alpha_tstat": 1.0,
                "alpha_pvalue": 0.2,
                "coefficients": {"mkt_rf": 0.0},
            }

    monkeypatch.setattr(run_production, "UniverseFetcher", FakeUniverseFetcher)
    monkeypatch.setattr(run_production, "SECDownloader", FakeSECDownloader)
    monkeypatch.setattr(run_production, "PriceFetcher", FakePriceFetcher)
    monkeypatch.setattr(run_production, "FamaFrenchFactors", FakeFamaFrenchFactors)
    monkeypatch.setattr(run_production, "SECFilingParser", FakeSECFilingParser)
    monkeypatch.setattr(run_production, "TextCleaner", FakeTextCleaner)
    monkeypatch.setattr(run_production, "ESGEventDetector", FakeEventDetector)
    monkeypatch.setattr(run_production, "FinancialSentimentAnalyzer", FakeSentimentAnalyzer)
    monkeypatch.setattr(run_production, "ReactionFeatureExtractor", FakeReactionFeatureExtractor)
    monkeypatch.setattr(run_production, "MultiSourceFetcher", FakeMultiSourceFetcher)
    monkeypatch.setattr(run_production, "ESGSignalGenerator", FakeSignalGenerator)
    monkeypatch.setattr(run_production, "PortfolioConstructor", FakePortfolioConstructor)
    monkeypatch.setattr(run_production, "BacktestEngine", FakeBacktestEngine)
    monkeypatch.setattr(run_production, "PerformanceAnalyzer", FakePerformanceAnalyzer)
    monkeypatch.setattr(run_production, "FactorAnalysis", FakeFactorAnalysis)
    monkeypatch.setattr(
        run_production.sys,
        "argv",
        [
            "run_production.py",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-02-15",
            "--max-tickers",
            "2",
        ],
    )

    run_production.main()

    assert captured["sentiment_init"]["mode"] == "hybrid"
    assert captured["signal_generator_init"]["weights"] == config["signals"]["weights"]
    assert captured["signal_generator_init"]["lookback_window"] == 252
    assert captured["signal_generator_init"]["weight_method"].name == "INVERSE_VARIANCE"
    assert captured["signal_generator_batch"]["require_social_data"] is True
    assert captured["portfolio_init"]["selection_balance"] == "equal_count"
    assert captured["portfolio_init"]["exposure_model"] == "dollar_neutral"
    assert captured["portfolio_construct"]["window_days"] == 49
    assert captured["portfolio_construct"]["rebalance_freq"] == "W"
    assert captured["portfolio_limit"] == pytest.approx(0.10)
    assert captured["backtest_init"]["balance_long_short"] is True
    assert captured["backtest_init"]["cash_benchmark_returns"] is None
    assert captured["backtest_init"]["adaptive_drawdown_thresholds"] is True
    assert captured["backtest_run"]["rebalance_freq"] == "W"
    assert captured["backtest_run"]["holding_period"] == 49
