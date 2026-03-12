"""
Demo and smoke-test entrypoint.

Canonical real-data execution lives in run_production.py. This file is kept as
an explicit demo harness only so the repository still has a lightweight local
sanity check that does not depend on live data sources.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yaml

from src.backtest import BacktestEngine, PerformanceAnalyzer
from src.nlp import FinancialSentimentAnalyzer, ReactionFeatureExtractor
from src.signals import ESGSignalGenerator, PortfolioConstructor
from src.signals.signal_generator import WeightDerivationMethod
from src.utils.logging_config import setup_logging
from src.utils.strategy_config import load_strategy_spec


def load_config(config_path: str = "config/config.yaml") -> dict:
    """Load configuration from YAML file."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _build_mock_prices(
    tickers: list[str],
    dates: pd.DatetimeIndex,
    event_date: pd.Timestamp,
) -> pd.DataFrame:
    """Generate deterministic mock prices with post-event drift by ticker bucket."""
    rows: list[dict] = []
    midpoint = len(tickers) // 2

    for idx, ticker in enumerate(tickers):
        rng = np.random.default_rng(abs(hash((ticker, len(dates)))) % (2**32))
        base_price = 80 + idx * 7
        drift = 0.0012 if idx >= midpoint else -0.0012

        price = base_price
        for date in dates:
            daily_ret = rng.normal(0.0001, 0.012)
            if date >= event_date:
                daily_ret += drift
            price *= max(1.0 + daily_ret, 0.01)
            rows.append(
                {
                    "Date": date,
                    "ticker": ticker,
                    "Close": price,
                    "Adj Close": price,
                    "Volume": int(1_000_000 + idx * 25_000),
                }
            )

    return pd.DataFrame(rows).set_index(["Date", "ticker"]).sort_index()


def run_demo(args, config: dict, logger) -> None:
    """Run a deterministic demo aligned to the canonical strategy contract."""
    strategy_spec = load_strategy_spec(config)
    logger.info("Canonical real-data runner: run_production.py")
    logger.info("main.py is demo-only and uses explicit smoke-test overrides")

    start_date = pd.Timestamp(args.start_date)
    end_date = pd.Timestamp(args.end_date)
    if end_date <= start_date:
        raise ValueError("end-date must be after start-date")

    tickers = list(dict.fromkeys(args.tickers))
    while len(tickers) < 10:
        tickers.extend(tickers)
        tickers = list(dict.fromkeys(tickers))
        if len(tickers) >= 10:
            break
    tickers = tickers[:10]

    dates = pd.date_range(start=start_date, end=end_date, freq="B")
    if len(dates) < 40:
        raise ValueError("demo requires at least 40 business days")
    event_date = dates[min(15, len(dates) // 3)]

    prices = _build_mock_prices(tickers, dates, event_date)

    # Demo override: keep the smoke test lightweight and deterministic.
    sentiment_analyzer = FinancialSentimentAnalyzer(mode="simple", strict=False)
    feature_extractor = ReactionFeatureExtractor(sentiment_analyzer)
    signal_generator = ESGSignalGenerator(
        lookback_window=strategy_spec.signal.lookback_window,
        weights=strategy_spec.signal.weights,
        weight_method=WeightDerivationMethod.from_string(
            strategy_spec.signal.weight_derivation_method
        ),
    )

    events_data = []
    midpoint = len(tickers) // 2
    for idx, ticker in enumerate(tickers):
        sentiment_bias = "negative" if idx < midpoint else "positive"
        mock_posts = feature_extractor.create_mock_social_data(
            ticker=ticker,
            event_date=event_date.to_pydatetime(),
            n_tweets=max(strategy_spec.signal.min_posts + 5, 12),
            sentiment_bias=sentiment_bias,
        )
        reaction_features = feature_extractor.extract_features(
            mock_posts,
            event_date.to_pydatetime(),
        )
        reaction_features["volume_ratio"] = 1.5 + (idx * 0.15)
        reaction_features["duration_days"] = 2 + (idx % 4)

        events_data.append(
            {
                "ticker": ticker,
                "date": event_date.to_pydatetime(),
                "event_features": {
                    "has_event": True,
                    "category": "E" if idx % 3 == 0 else ("S" if idx % 3 == 1 else "G"),
                    "confidence": 0.45 + idx * 0.05,
                    "sentiment": sentiment_bias,
                },
                "reaction_features": reaction_features,
            }
        )

    signals_df = signal_generator.generate_signals_batch(
        events_data,
        min_posts=strategy_spec.signal.min_posts,
        require_social_data=strategy_spec.signal.require_social_data,
        min_volume_ratio=strategy_spec.signal.min_volume_ratio,
        min_intensity=strategy_spec.signal.min_intensity,
        min_confidence=strategy_spec.signal.min_confidence,
    )
    if signals_df.empty:
        raise RuntimeError("demo produced no signals")

    portfolio_constructor = PortfolioConstructor(
        strategy_type=strategy_spec.portfolio.strategy_type,
        selection_balance=strategy_spec.portfolio.selection_balance,
        exposure_model=strategy_spec.portfolio.exposure_model,
        gross_exposure_target=strategy_spec.portfolio.gross_exposure_target,
    )
    portfolio = portfolio_constructor.construct_portfolio(
        signals_df,
        method=strategy_spec.portfolio.method,
        selection_balance=strategy_spec.portfolio.selection_balance,
        exposure_model=strategy_spec.portfolio.exposure_model,
        window_days=strategy_spec.portfolio.holding_period,
        rebalance_freq=strategy_spec.portfolio.rebalance_frequency,
    )
    portfolio = portfolio_constructor.apply_position_limits(
        portfolio,
        max_position=strategy_spec.portfolio.max_position,
    )

    stats = portfolio_constructor.get_portfolio_statistics(portfolio)
    logger.info(
        "Demo portfolio: %s long, %s short, net=%.2f%% gross=%.2f%%",
        stats["n_long"],
        stats["n_short"],
        stats["net_exposure"] * 100,
        stats["gross_exposure"] * 100,
    )
    if portfolio.empty:
        raise RuntimeError("demo portfolio is empty")

    engine = BacktestEngine(
        prices=prices,
        initial_capital=config["backtest"]["initial_capital"],
        commission_pct=config["backtest"]["commission_pct"],
        slippage_bps=config["backtest"]["slippage_bps"],
        enable_risk_management=strategy_spec.risk.enabled,
        max_position_size=strategy_spec.risk.max_position_size,
        target_volatility=strategy_spec.risk.target_volatility,
        max_drawdown_threshold=strategy_spec.risk.max_drawdown_threshold,
        adaptive_drawdown_thresholds=strategy_spec.risk.adaptive_thresholds,
        leverage_limit=strategy_spec.risk.leverage_limit,
        balance_long_short=(strategy_spec.portfolio.exposure_model == "dollar_neutral"),
    )
    results = engine.run(
        signals=portfolio,
        rebalance_freq=strategy_spec.portfolio.rebalance_frequency,
        holding_period=strategy_spec.portfolio.holding_period,
    )

    logger.info("Demo final value: $%0.2f", results.get_final_value())
    logger.info("Demo total return: %.2f%%", results.get_total_return() * 100)
    PerformanceAnalyzer(results).print_tear_sheet()


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="ESG Event-Driven Alpha Strategy demo/smoke runner"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/config.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--tickers",
        type=str,
        nargs="+",
        default=["AAPL", "MSFT", "TSLA", "XOM", "JPM"],
        help="Tickers to use for the deterministic demo",
    )
    parser.add_argument(
        "--start-date",
        type=str,
        default="2024-01-02",
        help="Demo start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2024-06-28",
        help="Demo end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="demo",
        choices=["demo"],
        help="Only demo mode is supported here; use run_production.py for real runs",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    logger = setup_logging(
        log_level=config["logging"]["level"],
        log_file=config["logging"].get("log_file"),
    )

    logger.info("=" * 60)
    logger.info("ESG EVENT-DRIVEN ALPHA STRATEGY DEMO")
    logger.info("=" * 60)
    logger.info("main.py is not a production runner")
    logger.info("Use run_production.py for canonical real-data execution")
    logger.info("=" * 60)

    run_demo(args, config, logger)


if __name__ == "__main__":
    main()
