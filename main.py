"""
Demo and smoke-test entrypoint.

Canonical real-data execution lives in run_production.py. This file is kept as
an explicit demo harness only so the repository still has a lightweight local
sanity check that does not depend on live data sources.
"""

from __future__ import annotations

import argparse
import zlib

import numpy as np
import pandas as pd

from src.backtest import BacktestEngine, PerformanceAnalyzer
from src.nlp import FinancialSentimentAnalyzer, ReactionFeatureExtractor
from src.signals import ESGSignalGenerator, PortfolioConstructor
from src.signals.signal_generator import WeightDerivationMethod
from src.utils.config_loader import load_config, load_environment
from src.utils.logging_config import setup_logging
from src.utils.strategy_config import load_strategy_spec


def _build_mock_prices(
    tickers: list[str],
    dates: pd.DatetimeIndex,
    first_event_date: pd.Timestamp,
    drift_by_ticker: dict[str, float],
) -> pd.DataFrame:
    """Generate deterministic synthetic prices with sentiment-aligned post-event drift.

    DEMO/synthetic only. The per-ticker post-event drift is aligned to the same
    long/short sentiment assignment used to build the demo events so that the
    offline smoke test produces a coherent (not random) tear sheet. Uses a LOCAL
    ``np.random.default_rng`` seeded deterministically via ``zlib.crc32`` so the
    output is reproducible across processes (no global RNG mutation).
    """
    rows: list[dict] = []

    for idx, ticker in enumerate(dict.fromkeys(tickers)):
        seed = zlib.crc32(f"{ticker}:{len(dates)}".encode())
        rng = np.random.default_rng(seed)
        base_price = 80 + idx * 7
        drift = drift_by_ticker.get(ticker, 0.0)

        price = base_price
        for date in dates:
            daily_ret = rng.normal(0.0001, 0.012)
            if date >= first_event_date:
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


def _build_demo_posts(
    ticker: str,
    event_date: pd.Timestamp,
    n_posts: int,
    signed_sentiment: float,
) -> pd.DataFrame:
    """Build a synthetic social-post frame with an explicit signed sentiment.

    DEMO/synthetic only. We attach a numeric ``sentiment`` column directly so the
    offline smoke test does not depend on a text lexicon to recover direction:
    the reaction-feature extractor consumes the pre-scored ``sentiment`` column
    when present, which makes the long/short split deterministic. Posts span the
    pre-event baseline through the +3 day post-event window used by the extractor.
    A LOCAL ``np.random.default_rng`` (crc32-seeded) keeps engagement noise
    reproducible across processes without mutating the global RNG.
    """
    rng = np.random.default_rng(zlib.crc32(f"{ticker}:{event_date}".encode()))
    # Span [-2, +3] days so there is a pre-event baseline and a post-event window.
    offsets = np.linspace(-2.0, 3.0, num=n_posts)
    timestamps = [event_date + pd.Timedelta(days=float(off)) for off in offsets]
    # Small reproducible jitter around the target sentiment, sign preserved.
    jitter = rng.normal(0.0, 0.05, size=n_posts)
    sentiment = np.clip(signed_sentiment + jitter, -1.0, 1.0)

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "text": [f"DEMO synthetic post about {ticker}"] * n_posts,
            "sentiment": sentiment,
            "user_followers": rng.integers(500, 50_000, size=n_posts),
            "retweets": rng.integers(0, 25, size=n_posts),
            "likes": rng.integers(0, 120, size=n_posts),
            "ticker": ticker,
        }
    )


def run_demo(args, config: dict, logger) -> None:
    """Run a deterministic demo aligned to the canonical strategy contract."""
    strategy_spec = load_strategy_spec(config)
    logger.info("Canonical real-data runner: run_production.py")
    logger.info("main.py is demo-only and uses explicit smoke-test overrides")

    start_date = pd.Timestamp(args.start_date)
    end_date = pd.Timestamp(args.end_date)
    if end_date <= start_date:
        raise ValueError("end-date must be after start-date")

    # INFRA-01: deterministic ticker expansion that allows repeats (no infinite
    # loop). The unique names drive the demo cross-section; the expansion only
    # widens the synthetic price universe.
    base = list(dict.fromkeys(args.tickers))
    tickers = (base * ((10 // max(len(base), 1)) + 1))[:10]
    universe = list(dict.fromkeys(tickers))

    # A long/short demo needs at least two distinct names per side. If the caller
    # supplied too few unique tickers, pad with clearly-labelled synthetic DEMO
    # names so the offline smoke test always forms a balanced book.
    min_universe = 4
    if len(universe) < min_universe:
        logger.info(
            "DEMO: padding universe from %d to %d names with synthetic DEMO tickers",
            len(universe),
            min_universe,
        )
        filler = 1
        while len(universe) < min_universe:
            synthetic = f"DEMO{filler}"
            if synthetic not in universe:
                universe.append(synthetic)
            filler += 1
        tickers = universe[:]

    # INFRA-02: demo-only smoke-test overrides. The canonical 49-calendar-day
    # holding window over a short demo range yields no balanced book, so the
    # OFFLINE DEMO path uses a longer date range and a short holding window and
    # spreads several balanced event "waves" across time. This is clearly
    # synthetic and must never be read as a production result.
    demo_holding_period = 14  # calendar days (smoke-test window)
    demo_rebalance_freq = "W"
    n_waves = 4
    min_business_days = 60
    logger.info(
        "DEMO (synthetic, offline): holding_period=%d days, rebalance=%s, waves=%d "
        "-- NOT a production result; use run_production.py for real data",
        demo_holding_period,
        demo_rebalance_freq,
        n_waves,
    )

    dates = pd.date_range(start=start_date, end=end_date, freq="B")
    if len(dates) < min_business_days:
        # Extend the range deterministically so the smoke test always has enough
        # room for the rolling window and several event waves.
        end_date = start_date + pd.Timedelta(days=int(min_business_days * 1.6))
        dates = pd.date_range(start=start_date, end=end_date, freq="B")
        logger.info(
            "DEMO: extended date range to %s -> %s for a stable smoke test",
            dates[0].date(),
            dates[-1].date(),
        )

    # Balanced long/short assignment over the unique universe: alternate the
    # synthetic sentiment so each event wave deterministically contains both
    # bearish (short) and bullish (long) names.
    sentiment_by_ticker = {
        ticker: ("negative" if idx % 2 == 0 else "positive")
        for idx, ticker in enumerate(universe)
    }
    drift_by_ticker = {
        ticker: (-0.0014 if bias == "negative" else 0.0014)
        for ticker, bias in sentiment_by_ticker.items()
    }

    # Event waves spread across the range so the weekly rebalance grid sees a
    # populated, balanced cross-section at multiple points.
    wave_positions = np.linspace(10, len(dates) - 10, num=n_waves)
    wave_dates = [dates[int(round(pos))] for pos in wave_positions]
    first_event_date = wave_dates[0]

    prices = _build_mock_prices(tickers, dates, first_event_date, drift_by_ticker)

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
    n_posts = max(strategy_spec.signal.min_posts + 5, 12)
    for wave_idx, wave_date in enumerate(wave_dates):
        for idx, ticker in enumerate(universe):
            sentiment_bias = sentiment_by_ticker[ticker]
            signed_sentiment = -0.6 if sentiment_bias == "negative" else 0.6
            mock_posts = _build_demo_posts(
                ticker=ticker,
                event_date=wave_date,
                n_posts=n_posts,
                signed_sentiment=signed_sentiment,
            )
            reaction_features = feature_extractor.extract_features(
                mock_posts,
                wave_date.to_pydatetime(),
            )
            reaction_features["volume_ratio"] = 1.5 + (idx * 0.15)
            reaction_features["duration_days"] = 2 + (idx % 4)

            events_data.append(
                {
                    "ticker": ticker,
                    "date": wave_date.to_pydatetime(),
                    "event_features": {
                        "has_event": True,
                        "category": (
                            "E" if idx % 3 == 0 else ("S" if idx % 3 == 1 else "G")
                        ),
                        "confidence": 0.45 + (idx % 5) * 0.05,
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
        window_days=demo_holding_period,
        rebalance_freq=demo_rebalance_freq,
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
        rebalance_freq=demo_rebalance_freq,
        holding_period=10,  # DEMO: ~10 trading days, matched to the smoke window
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

    load_environment()
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
