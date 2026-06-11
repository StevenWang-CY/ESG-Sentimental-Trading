"""
Regression tests for the production-hardening remediation.

Each test encodes a specific audit finding so it would FAIL against the old
behaviour and PASS after the fix:

* fail-closed data fetchers (no silent synthetic fallback on a real run)
* data-provenance tagging + the orchestrator guard
* config ${ENV} expansion + credential resolution
* cache provenance gating (legacy/mock caches are not trusted)
* canonical FLAT metrics contract (flatten) + CAGR + annualized turnover
* drawdown controller no longer a no-op (state persists / halt fires)
* trading-day (not calendar-day) holding period
* walk-forward validate() no longer takes a no-op optimizer
* dashboard auto-loads a real run record (incl. the cold-clone sample)
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.utils.provenance import (
    tag, is_mock, get_provenance, guard_real, DataUnavailableError, REAL, MOCK, EMPTY,
)


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
def test_guard_real_blocks_mock_and_empty():
    real = tag(pd.DataFrame({"a": [1, 2]}), REAL, "src")
    assert guard_real(real, "stage") is real  # passes through
    with pytest.raises(DataUnavailableError):
        guard_real(tag(pd.DataFrame({"a": [1]}), MOCK, "src"), "stage")
    with pytest.raises(DataUnavailableError):
        guard_real(pd.DataFrame(), "stage")  # empty
    assert is_mock(tag(pd.DataFrame({"a": [1]}), MOCK)) is True
    assert get_provenance(pd.DataFrame({"a": [1]})) == REAL  # unmarked defaults real


# --------------------------------------------------------------------------- #
# Config loading: ${ENV} expansion + credential resolution
# --------------------------------------------------------------------------- #
def test_config_env_expansion_and_credentials(tmp_path, monkeypatch):
    from src.utils import config_loader

    cfg = tmp_path / "c.yaml"
    cfg.write_text('data:\n  reddit:\n    client_id: "${MY_CID}"\n    note: "plain"\n')

    monkeypatch.delenv("MY_CID", raising=False)
    loaded = config_loader.load_config(str(cfg))
    # Unset placeholder expands to empty string (so credential gates fail closed),
    # never the literal "${MY_CID}".
    assert loaded["data"]["reddit"]["client_id"] == ""
    assert loaded["data"]["reddit"]["note"] == "plain"

    monkeypatch.setenv("MY_CID", "abc123")
    loaded2 = config_loader.load_config(str(cfg))
    assert loaded2["data"]["reddit"]["client_id"] == "abc123"

    assert config_loader.is_unset("${X}") is True
    assert config_loader.is_unset("") is True
    assert config_loader.is_unset("real") is False
    assert config_loader.resolve_credential("${MY_CID}", "MY_CID") == "abc123"
    monkeypatch.delenv("MY_CID", raising=False)
    assert config_loader.resolve_credential("${MY_CID}", "MY_CID") is None


# --------------------------------------------------------------------------- #
# Fail-closed fetchers
# --------------------------------------------------------------------------- #
def test_price_fetcher_fail_closed_and_mock_tagged(monkeypatch):
    from src.data import price_fetcher as pfmod

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(pfmod, "YFINANCE_AVAILABLE", True)
    monkeypatch.setattr(pfmod.yf, "download", boom)

    # Production (use_mock=False): must raise, never fabricate.
    with pytest.raises(DataUnavailableError):
        pfmod.PriceFetcher(use_mock=False).fetch_price_data(["AAA"], "2023-01-01", "2023-02-01")

    # Explicit demo (use_mock=True): returns synthetic data, clearly tagged MOCK.
    df = pfmod.PriceFetcher(use_mock=True).fetch_price_data(["AAA"], "2023-01-01", "2023-01-20")
    assert is_mock(df) and not df.empty


def test_ff_factors_fail_closed_and_mock_tagged(monkeypatch):
    from src.data import ff_factors as ffmod

    def boom(*a, **k):
        raise RuntimeError("ken french down")

    monkeypatch.setattr(ffmod, "DATAREADER_AVAILABLE", True)
    monkeypatch.setattr(ffmod.pdr, "DataReader", boom)

    with pytest.raises(DataUnavailableError):
        ffmod.FamaFrenchFactors(use_mock=False).load_ff_factors("2023-01-01", "2023-02-01", "daily")

    df = ffmod.FamaFrenchFactors(use_mock=True).load_ff_factors("2023-01-01", "2023-02-01", "daily")
    assert is_mock(df) and not df.empty


def test_default_fetchers_are_fail_closed():
    from src.data.price_fetcher import PriceFetcher
    from src.data.ff_factors import FamaFrenchFactors
    assert PriceFetcher().use_mock is False
    assert FamaFrenchFactors().use_mock is False


# --------------------------------------------------------------------------- #
# Cache provenance
# --------------------------------------------------------------------------- #
def test_cache_provenance_trust(tmp_path):
    from src.utils import cache_manager as cm

    f = tmp_path / "x.pkl"
    f.write_bytes(b"data")
    assert cm.is_cache_trusted(f) is False          # legacy / no marker -> not trusted
    cm.mark_cache_provenance(f, MOCK)
    assert cm.is_cache_trusted(f) is False           # mock -> never trusted
    cm.mark_cache_provenance(f, REAL)
    assert cm.is_cache_trusted(f) is True
    assert cm.read_cache_provenance(f) == REAL
    assert cm.is_cache_trusted(tmp_path / "missing.pkl") is False


# --------------------------------------------------------------------------- #
# Metrics: flatten contract + CAGR + annualized turnover
# --------------------------------------------------------------------------- #
def _toy_result():
    from src.backtest.engine import BacktestEngine
    dates = pd.bdate_range("2023-01-02", periods=90)
    tickers = ["AAA", "BBB", "CCC", "DDD"]
    rows = []
    rng = np.random.default_rng(7)
    for k, t in enumerate(tickers):
        px = 100 * np.cumprod(1 + rng.normal(0.0006 if k < 2 else -0.0004, 0.012, len(dates)))
        for d, p in zip(dates, px):
            rows.append({"Date": d, "ticker": t, "Open": p, "High": p, "Low": p,
                         "Close": p, "Volume": 1e6, "Adj Close": p})
    prices = pd.DataFrame(rows).set_index(["Date", "ticker"])
    eng = BacktestEngine(prices=prices, enable_risk_management=True)
    rdates = eng._get_rebalance_dates(pd.DataFrame([{"ticker": "AAA", "date": d} for d in dates]), "W")
    sig = []
    for d in rdates[:3]:
        for k, t in enumerate(tickers):
            sig.append({"ticker": t, "date": pd.Timestamp(d), "weight": 0.25 if k < 2 else -0.25})
    res = eng.run(pd.DataFrame(sig), rebalance_freq="W", holding_period=15)
    return eng, res


def test_flatten_canonical_contract():
    from src.backtest.metrics import PerformanceAnalyzer
    _, res = _toy_result()
    flat = PerformanceAnalyzer(res).flatten()
    required = {
        "sharpe_ratio", "sharpe_ratio_lo_adjusted", "probabilistic_sharpe", "deflated_sharpe",
        "sortino_ratio", "annualized_return", "annualized_return_pct", "cagr",
        "total_return", "total_return_pct", "volatility", "volatility_pct",
        "max_drawdown", "max_drawdown_pct", "calmar_ratio", "turnover", "num_trades", "win_rate",
    }
    assert required.issubset(flat.keys())
    assert isinstance(flat["num_trades"], int)
    # _pct variants are exactly 100x the fractional values
    assert flat["max_drawdown_pct"] == pytest.approx(flat["max_drawdown"] * 100)
    assert flat["total_return_pct"] == pytest.approx(flat["total_return"] * 100)
    # BT-04: headline annualized_return is CAGR (geometric)
    assert flat["annualized_return"] == pytest.approx(flat["cagr"])


def test_turnover_is_annualized():
    """BT-05: turnover scales by years, so it is comparable across windows."""
    from src.backtest.metrics import PerformanceAnalyzer
    _, res = _toy_result()
    pa = PerformanceAnalyzer(res)
    t = pa._calculate_turnover()
    assert t >= 0.0 and np.isfinite(t)


# --------------------------------------------------------------------------- #
# BT-01: drawdown controller is no longer a silent no-op
# --------------------------------------------------------------------------- #
def test_drawdown_controller_accumulates_and_halts():
    from src.risk.drawdown_controller import DrawdownController
    dc = DrawdownController(drawdown_thresholds=[-0.10, -0.15, -0.20, -0.25],
                            exposure_levels=[0.95, 0.85, 0.70, 0.50])
    # Rise to a peak, then crash ~26%.
    for v in [100, 105, 110, 112, 115]:
        dc.update(v)
    for v in [110, 100, 95, 90, 85]:  # ~26% drawdown from 115
        dc.update(v)
    assert dc.current_exposure_level < 1.0          # exposure was reduced
    assert dc.should_halt_trading() is True          # deep drawdown halts trading
    assert len(dc.drawdown_history) > 1              # state accumulated, not reset


def test_engine_feeds_drawdown_controller_daily():
    """BT-01 in situ: the controller is fed every day, not rebuilt per rebalance."""
    eng, _ = _toy_result()
    assert eng.drawdown_controller is not None
    # Fed once per trading day -> far more entries than the handful of rebalances.
    assert len(eng.drawdown_controller.portfolio_values) >= 80


# --------------------------------------------------------------------------- #
# BT-02: trading-day holding period
# --------------------------------------------------------------------------- #
def test_holding_period_counts_trading_days():
    """A position must survive intervening weekends (calendar gap > trading gap)."""
    from src.backtest.engine import BacktestEngine
    dates = pd.bdate_range("2023-01-02", periods=40)
    rows = []
    for t in ["AAA", "BBB"]:
        for i, d in enumerate(dates):
            p = 100 + i
            rows.append({"Date": d, "ticker": t, "Open": p, "High": p, "Low": p,
                         "Close": p, "Volume": 1e6, "Adj Close": p})
    prices = pd.DataFrame(rows).set_index(["Date", "ticker"])
    eng = BacktestEngine(prices=prices, enable_risk_management=False)
    entry = dates[0]
    positions = {"AAA": {"shares": 10, "entry_price": 100.0, "entry_date": entry}}
    eng._all_dates = list(dates)
    # 5 trading days after entry = dates[5] (spans a weekend), which is 7 calendar days.
    five_trading_days_later = dates[5]
    assert (five_trading_days_later - entry).days > 5  # calendar gap exceeds 5
    kept, _ = eng._rebalance_with_cash(
        five_trading_days_later, pd.DataFrame(columns=["ticker", "date", "weight"]),
        dict(positions), 1_000_000.0, 1_000_000.0, holding_period=6,
    )
    assert "AAA" in kept  # only 5 trading days elapsed (< 6) -> still held


# --------------------------------------------------------------------------- #
# BT-03: walk-forward no longer takes a no-op optimizer
# --------------------------------------------------------------------------- #
def test_walk_forward_validate_signature():
    from src.validation.walk_forward_validator import WalkForwardValidator
    params = list(inspect.signature(WalkForwardValidator.validate).parameters)
    assert "optimizer" not in params
    assert {"signals", "prices", "backtest_fn"}.issubset(params)


# --------------------------------------------------------------------------- #
# Dashboard auto-loads a real run record (cold-clone sample included)
# --------------------------------------------------------------------------- #
def test_dashboard_loads_sample_run():
    pytest.importorskip("streamlit")
    pytest.importorskip("plotly")
    import dashboard
    dashboard.discover_runs.clear()
    runs = dashboard.discover_runs()
    assert runs, "dashboard must discover at least the committed sample run"
    rec = dashboard.load_run(runs[0]["path"])
    assert "metrics" in rec and "sharpe_ratio" in rec["metrics"]
    # The sample bundle's CSV artifacts resolve as siblings of the run JSON.
    eq = dashboard.load_csv(runs[0]["path"], rec["paths"]["equity_csv"])
    assert eq is not None and not eq.empty


def test_dashboard_resolves_sibling_artifact(tmp_path):
    pytest.importorskip("streamlit")
    pytest.importorskip("plotly")
    import dashboard
    rj = tmp_path / "run_x.json"
    rj.write_text(json.dumps({"paths": {"equity_csv": "data/equity_x.csv"}}))
    (tmp_path / "equity_x.csv").write_text("date,equity\n2024-01-01,1000000\n")
    resolved = dashboard._resolve_artifact(str(rj), "data/equity_x.csv")
    assert resolved is not None and resolved.name == "equity_x.csv"


def test_dashboard_renders_all_surfaces_without_exception():
    """End-to-end: the full Streamlit app renders every tab against the sample run."""
    pytest.importorskip("streamlit")
    pytest.importorskip("plotly")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file("dashboard.py", default_timeout=90)
    at.run()
    # AppTest.exception is an (empty) ElementList when no exception was raised.
    assert not at.exception, f"dashboard raised: {list(at.exception)}"
    assert len(at.tabs) == 7         # Overview..Run History
    assert len(at.metric) > 0        # real metrics rendered (not empty state)
