"""
ESG Event-Driven Strategy Monitoring Dashboard
================================================

A connected Streamlit dashboard that reads the REAL artifacts produced by a
``run_production.py`` run -- never hardcoded demo metrics. Every surface is
driven by the canonical machine-readable run record
(``results/runs/run_*.json``) and the per-run CSVs it references
(signals / portfolio / equity series).

Surfaces:
    1. Overview       -- pipeline health, last refresh, data provenance, key metrics
    2. Performance    -- equity curve, underwater drawdown, benchmark, exposure
    3. Holdings       -- current portfolio weights, long/short split, gross/net
    4. Signals        -- per-signal explorer (what drove each signal)
    5. Proposed Orders-- weight deltas between the last two rebalances (review/export)
    6. Validation     -- post-backtest checks vs the canonical strategy_config
    7. Run History    -- browse / compare prior runs; reproducibility metadata

Every surface handles loading / empty / error / stale-data / failed-run states.
Run with:  streamlit run dashboard.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Load .env so any env-driven config resolves, and import the canonical config
# loader + validator (single source of truth -- no copied threshold literals).
from src.utils.config_loader import load_config, load_environment
from src.utils.strategy_config import load_strategy_spec

try:
    from scripts.validate_backtest import BacktestValidator, ValidationCriteria
    VALIDATOR_AVAILABLE = True
except Exception:  # pragma: no cover - dashboard still renders without it
    VALIDATOR_AVAILABLE = False

load_environment()

# Directories searched for run records. The committed sample bundle guarantees
# the dashboard is populated on a cold clone (before any real run exists).
RUN_DIRS = [Path("results/runs"), Path("examples/sample_run")]
STALE_AFTER_HOURS = 24

st.set_page_config(
    page_title="ESG Strategy Monitoring",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------- #
# Data loading (all real artifacts; no hardcoded metrics)
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def load_app_config() -> Dict:
    try:
        return load_config("config/config.yaml")
    except Exception:
        return {}


@st.cache_data(show_spinner=False)
def discover_runs() -> List[Dict]:
    """Find all run records across RUN_DIRS, newest first.

    Returns a list of {path, run_id, mtime, status, generated_at} summaries.
    """
    runs: List[Dict] = []
    seen = set()
    for d in RUN_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.glob("run_*.json")):
            try:
                rec = json.loads(p.read_text())
            except Exception:
                continue
            rid = rec.get("run_id", p.stem)
            if rid in seen:
                continue
            seen.add(rid)
            runs.append({
                "path": str(p),
                "run_id": rid,
                "mtime": p.stat().st_mtime,
                "status": rec.get("status", "UNKNOWN"),
                "generated_at": rec.get("generated_at"),
                "start_date": rec.get("start_date"),
                "end_date": rec.get("end_date"),
                "is_sample": "examples/sample_run" in str(p),
            })
    runs.sort(key=lambda r: r["mtime"], reverse=True)
    return runs


@st.cache_data(show_spinner=False)
def load_run(path: str) -> Dict:
    return json.loads(Path(path).read_text())


def _resolve_artifact(run_path: str, rel_path: Optional[str]) -> Optional[Path]:
    """Resolve a CSV path from a run record.

    Tries the literal path first (live runs write to data/), then falls back to
    a file of the same name next to the run JSON (the committed sample bundle
    keeps its CSVs alongside the JSON).
    """
    if not rel_path:
        return None
    p = Path(rel_path)
    if p.exists():
        return p
    sibling = Path(run_path).parent / p.name
    if sibling.exists():
        return sibling
    return None


@st.cache_data(show_spinner=False)
def load_csv(run_path: str, rel_path: Optional[str]) -> Optional[pd.DataFrame]:
    resolved = _resolve_artifact(run_path, rel_path)
    if resolved is None:
        return None
    try:
        return pd.read_csv(resolved)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Small UI helpers
# --------------------------------------------------------------------------- #
def _status_badge(status: str) -> str:
    return {
        "COMPLETE": "✅ COMPLETE",
        "VALIDATION_FAILED": "⚠️ VALIDATION FAILED",
        "FACTOR_ANALYSIS_INVALID": "🚨 FACTOR ANALYSIS INVALID",
        "FAILED": "🚨 FAILED",
    }.get(status, f"❔ {status}")


def _hours_since(iso_or_mtime) -> Optional[float]:
    try:
        if isinstance(iso_or_mtime, (int, float)):
            ts = datetime.fromtimestamp(iso_or_mtime)
        else:
            ts = datetime.fromisoformat(str(iso_or_mtime))
        return (datetime.now() - ts.replace(tzinfo=None)).total_seconds() / 3600.0
    except Exception:
        return None


def render_provenance_banner(run: Dict) -> None:
    prov = run.get("data_provenance", {})
    price_prov = prov.get("prices")
    factor_prov = prov.get("factors")
    if run.get("allow_mock") or price_prov == "mock" or factor_prov == "mock":
        st.warning(
            "🧪 **DEMO / SYNTHETIC DATA** — this run used mock data "
            f"(prices: `{price_prov}`, factors: `{factor_prov}`). "
            "Metrics are illustrative only and must NOT be treated as real "
            "performance. Re-run with real data sources for production figures."
        )


def render_stale_banner(run: Dict, run_path: str) -> None:
    hrs = _hours_since(run.get("generated_at")) or _hours_since(Path(run_path).stat().st_mtime)
    if hrs is not None and hrs > STALE_AFTER_HOURS:
        st.info(f"🕒 Stale data: this run was generated {hrs/24:.1f} days ago "
                f"({STALE_AFTER_HOURS}h staleness threshold).")


def empty_state(message: str, hint: str = "") -> None:
    st.info(f"**Nothing to show yet.** {message}")
    if hint:
        st.caption(hint)


# --------------------------------------------------------------------------- #
# Surfaces
# --------------------------------------------------------------------------- #
def surface_overview(run: Dict, run_path: str, spec) -> None:
    st.header("📈 Overview")
    render_provenance_banner(run)
    render_stale_banner(run, run_path)

    prov = run.get("data_provenance", {})
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Run status", _status_badge(run.get("status", "UNKNOWN")))
    c2.metric("Generated", str(run.get("generated_at", "—")))
    c3.metric("Period", f"{run.get('start_date','?')} → {run.get('end_date','?')}")
    c4.metric("Git commit", run.get("git_commit", "—"))

    st.subheader("Key performance metrics")
    m = run.get("metrics", {})
    g1, g2, g3, g4, g5, g6 = st.columns(6)
    g1.metric("Sharpe", f"{m.get('sharpe_ratio', float('nan')):.2f}")
    g2.metric("Sortino", f"{m.get('sortino_ratio', float('nan')):.2f}")
    g3.metric("Total return", f"{m.get('total_return_pct', float('nan')):.2f}%")
    g4.metric("Max drawdown", f"{m.get('max_drawdown_pct', float('nan')):.2f}%")
    g5.metric("Turnover (ann.)", f"{m.get('turnover', float('nan')):.2f}x")
    g6.metric("Trades", f"{int(m.get('num_trades', 0))}")

    st.subheader("Pipeline health")
    h1, h2, h3, h4 = st.columns(4)
    h1.metric("Events detected", prov.get("n_events", "—"))
    h2.metric("Signals", prov.get("n_signals", "—"))
    h3.metric("Positions", prov.get("n_positions", "—"))
    h4.metric("Social source", prov.get("social_source", "—"))
    st.caption(
        f"Data provenance — prices: `{prov.get('prices','?')}`, "
        f"factors: `{prov.get('factors','?')}`. Factor analysis: "
        f"`{run.get('factor_status','?')}`."
    )

    factor = run.get("factor", {})
    if factor:
        st.subheader("Factor regression (Fama-French + Momentum)")
        f1, f2, f3, f4 = st.columns(4)
        f1.metric("Annualized alpha", f"{factor.get('alpha_annual', 0.0)*100:.2f}%")
        f2.metric("Alpha t-stat", f"{factor.get('alpha_tstat', 0.0):.2f}")
        f3.metric("Alpha p-value", f"{factor.get('alpha_pvalue', 1.0):.3f}")
        f4.metric("R²", f"{factor.get('r_squared', 0.0):.2f}")
        st.caption(f"Covariance: {factor.get('cov_type', 'OLS')}, "
                   f"N={factor.get('n_observations', 0)}, "
                   f"factors provenance: `{factor.get('factors_provenance','?')}`")


def surface_performance(run: Dict, run_path: str) -> None:
    st.header("📉 Performance")
    eq = load_csv(run_path, run.get("paths", {}).get("equity_csv"))
    if eq is None or eq.empty:
        empty_state("No equity series found for this run.",
                    "run_production.py writes data/equity_<dates>.csv after the backtest.")
        return
    if "date" in eq.columns:
        eq["date"] = pd.to_datetime(eq["date"])
        eq = eq.set_index("date")

    # Equity curve (+ benchmark if present)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq.index, y=eq["equity"], name="Strategy equity", mode="lines"))
    if "benchmark_cum" in eq.columns and eq["benchmark_cum"].notna().any():
        base = eq["equity"].iloc[0]
        fig.add_trace(go.Scatter(x=eq.index, y=eq["benchmark_cum"] * base,
                                 name="Benchmark (scaled)", mode="lines",
                                 line=dict(dash="dot")))
    fig.update_layout(title="Equity curve", height=360, margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)

    # Underwater drawdown
    if "drawdown" in eq.columns:
        dd = go.Figure()
        dd.add_trace(go.Scatter(x=eq.index, y=eq["drawdown"] * 100, name="Drawdown",
                                fill="tozeroy", mode="lines", line=dict(color="#d62728")))
        dd.update_layout(title="Underwater drawdown (%)", height=260, margin=dict(t=40, b=20))
        st.plotly_chart(dd, use_container_width=True)

    col1, col2 = st.columns(2)
    if "daily_return" in eq.columns:
        hist = go.Figure(go.Histogram(x=eq["daily_return"] * 100, nbinsx=40))
        hist.update_layout(title="Daily return distribution (%)", height=300, margin=dict(t=40, b=20))
        col1.plotly_chart(hist, use_container_width=True)
    if {"gross_exposure", "net_exposure"}.issubset(eq.columns):
        ex = go.Figure()
        ex.add_trace(go.Scatter(x=eq.index, y=eq["gross_exposure"], name="Gross", mode="lines"))
        ex.add_trace(go.Scatter(x=eq.index, y=eq["net_exposure"], name="Net", mode="lines"))
        ex.update_layout(title="Exposure over time", height=300, margin=dict(t=40, b=20))
        col2.plotly_chart(ex, use_container_width=True)


def surface_holdings(run: Dict, run_path: str) -> None:
    st.header("📦 Holdings")
    pf = load_csv(run_path, run.get("paths", {}).get("portfolio_csv"))
    if pf is None or pf.empty or "weight" not in pf.columns:
        empty_state("No portfolio file found for this run.",
                    "run_production.py writes data/portfolio_<dates>.csv during construction.")
        return
    if "date" in pf.columns:
        pf["date"] = pd.to_datetime(pf["date"])
        latest = pf["date"].max()
        st.caption(f"Latest rebalance date: **{latest.date()}**")
        current = pf[pf["date"] == latest].copy()
    else:
        current = pf.copy()

    longs = current[current["weight"] > 0]
    shorts = current[current["weight"] < 0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Positions", len(current))
    c2.metric("Long / Short", f"{len(longs)} / {len(shorts)}")
    c3.metric("Gross exposure", f"{current['weight'].abs().sum():.2%}")
    c4.metric("Net exposure", f"{current['weight'].sum():.2%}")

    show = current.sort_values("weight", ascending=False)[["ticker", "weight"]]
    show["side"] = show["weight"].apply(lambda w: "LONG" if w > 0 else "SHORT")
    show["weight_pct"] = (show["weight"] * 100).round(3)
    st.dataframe(show[["ticker", "side", "weight_pct"]], use_container_width=True, hide_index=True)

    fig = go.Figure(go.Bar(x=show["ticker"], y=show["weight_pct"],
                           marker_color=["#2ca02c" if w > 0 else "#d62728" for w in show["weight"]]))
    fig.update_layout(title="Position weights (%)", height=320, margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)


def surface_signals(run: Dict, run_path: str) -> None:
    st.header("🔎 Signal explorer")
    sig = load_csv(run_path, run.get("paths", {}).get("signals_csv"))
    if sig is None or sig.empty:
        empty_state("No signals file found for this run.",
                    "run_production.py writes data/signals_<dates>.csv after signal generation.")
        return

    tickers = ["(all)"] + sorted(sig["ticker"].dropna().unique().tolist()) if "ticker" in sig else ["(all)"]
    pick = st.selectbox("Filter by ticker", tickers)
    view = sig if pick == "(all)" else sig[sig["ticker"] == pick]
    st.dataframe(view, use_container_width=True, hide_index=True)

    if "event_category" in sig.columns:
        counts = sig["event_category"].value_counts()
        fig = go.Figure(go.Pie(labels=counts.index.tolist(), values=counts.values.tolist(), hole=0.4))
        fig.update_layout(title="ESG event category distribution (from real signals)",
                          height=320, margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Signal drivers")
    if pick != "(all)" and not view.empty:
        row = view.iloc[0]
        drivers = {k: row[k] for k in [
            "raw_score", "z_score", "quintile", "signal", "sentiment_intensity",
            "volume_ratio", "n_posts", "event_confidence", "event_category", "has_social_data",
        ] if k in view.columns}
        st.json({k: (float(v) if isinstance(v, (int, float)) else str(v)) for k, v in drivers.items()})
        st.caption("Trace: raw_score → z_score → quintile → final signal, driven by "
                   "sentiment_intensity / volume_ratio / event_confidence.")
    else:
        st.caption("Select a single ticker above to inspect the fields that produced its signal.")


def surface_orders(run: Dict, run_path: str) -> None:
    st.header("🧾 Proposed orders")
    st.caption("Target-weight deltas between the two most recent rebalance dates. "
               "**Review / export only — this does not execute trades.**")
    pf = load_csv(run_path, run.get("paths", {}).get("portfolio_csv"))
    if pf is None or pf.empty or "weight" not in pf.columns or "date" not in pf.columns:
        empty_state("Need a dated portfolio file with at least two rebalance dates to derive orders.")
        return
    pf["date"] = pd.to_datetime(pf["date"])
    dates = sorted(pf["date"].unique())
    if len(dates) < 2:
        # Single rebalance: every position is a new order from a flat book.
        latest = pf[pf["date"] == dates[-1]][["ticker", "weight"]].rename(columns={"weight": "target_weight"})
        latest["prev_weight"] = 0.0
        orders = latest
    else:
        prev = pf[pf["date"] == dates[-2]][["ticker", "weight"]].rename(columns={"weight": "prev_weight"})
        cur = pf[pf["date"] == dates[-1]][["ticker", "weight"]].rename(columns={"weight": "target_weight"})
        orders = pd.merge(cur, prev, on="ticker", how="outer").fillna(0.0)
        st.caption(f"Comparing {pd.Timestamp(dates[-2]).date()} → {pd.Timestamp(dates[-1]).date()}")

    orders["delta_weight"] = orders["target_weight"] - orders["prev_weight"]
    orders = orders[orders["delta_weight"].abs() > 1e-9].copy()
    orders["action"] = orders["delta_weight"].apply(lambda d: "BUY/COVER" if d > 0 else "SELL/SHORT")
    orders = orders.sort_values("delta_weight", key=lambda s: s.abs(), ascending=False)
    if orders.empty:
        empty_state("No weight changes between the last two rebalances — no orders to propose.")
        return
    st.dataframe(orders[["ticker", "action", "prev_weight", "target_weight", "delta_weight"]],
                 use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Download proposed orders (CSV)",
        data=orders.to_csv(index=False).encode("utf-8"),
        file_name=f"proposed_orders_{run.get('end_date','run')}.csv",
        mime="text/csv",
    )


def surface_validation(run: Dict, spec, config: Dict) -> None:
    st.header("✅ Validation")
    st.caption("Post-backtest checks against the canonical strategy_config "
               "(thresholds derived from src/utils/strategy_config, not hardcoded).")
    if not VALIDATOR_AVAILABLE:
        st.error("Validator unavailable (scripts.validate_backtest import failed).")
        return
    metrics = run.get("metrics", {})
    if not metrics:
        empty_state("No metrics in this run to validate.")
        return
    try:
        criteria = ValidationCriteria.from_strategy_spec(config) if config else ValidationCriteria()
        validator = BacktestValidator(config_path="config/config.yaml", criteria=criteria)
        passed, issues = validator.validate_backtest_results(metrics)
    except Exception as e:
        st.error(f"Validation could not run: {e}")
        return

    if passed:
        st.success("✅ Post-backtest validation PASSED (no critical errors).")
    else:
        st.error("🚨 Post-backtest validation FAILED — critical issues below.")
    # Show the run's own recorded validation issues too (from run_production).
    recorded = run.get("validation", {})
    if recorded:
        st.caption(f"Run-recorded validation: passed={recorded.get('passed')}, "
                   f"{len(recorded.get('issues', []))} issue(s).")
    for issue in issues:
        (st.error if issue.startswith("❌") else st.warning)(issue)
    if not issues:
        st.info("All post-backtest checks passed within thresholds.")

    st.subheader("Canonical thresholds")
    st.json({
        "min_sharpe": criteria.min_sharpe,
        "target_sharpe": criteria.target_sharpe,
        "max_turnover_annualized": criteria.max_turnover,
        "max_drawdown_critical_pct": criteria.max_drawdown_critical,
        "holding_period_max": criteria.max_holding_period,
        "confidence_threshold_min": criteria.min_confidence_threshold,
    })


def surface_run_history(runs: List[Dict]) -> None:
    st.header("🗂️ Run history & reproducibility")
    if not runs:
        empty_state("No runs found.")
        return
    table = pd.DataFrame([{
        "run_id": r["run_id"],
        "status": r["status"],
        "period": f"{r.get('start_date','?')}→{r.get('end_date','?')}",
        "generated_at": r.get("generated_at"),
        "sample": r["is_sample"],
    } for r in runs])
    st.dataframe(table, use_container_width=True, hide_index=True)

    st.subheader("Compare two runs")
    ids = [r["run_id"] for r in runs]
    if len(ids) >= 2:
        c1, c2 = st.columns(2)
        a = c1.selectbox("Run A", ids, index=0)
        b = c2.selectbox("Run B", ids, index=1)
        ra = load_run(next(r["path"] for r in runs if r["run_id"] == a))
        rb = load_run(next(r["path"] for r in runs if r["run_id"] == b))
        keys = ["sharpe_ratio", "sortino_ratio", "total_return_pct", "max_drawdown_pct",
                "turnover", "num_trades"]
        cmp = pd.DataFrame({
            "metric": keys,
            a: [ra.get("metrics", {}).get(k) for k in keys],
            b: [rb.get("metrics", {}).get(k) for k in keys],
        })
        st.dataframe(cmp, use_container_width=True, hide_index=True)
    else:
        st.caption("Need at least two runs to compare.")


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    st.title("📊 ESG Event-Driven Strategy Monitoring")
    st.caption("Connected to real run artifacts produced by `run_production.py`. "
               "No hardcoded demo metrics.")

    config = load_app_config()
    try:
        spec = load_strategy_spec(config) if config else None
    except Exception:
        spec = None

    runs = discover_runs()
    with st.sidebar:
        st.header("Run selector")
        if st.button("🔄 Refresh"):
            st.cache_data.clear()
            st.rerun()
        if not runs:
            st.warning("No runs found.")
        else:
            labels = [f"{'🧪 ' if r['is_sample'] else ''}{r['run_id']} [{r['status']}]" for r in runs]
            idx = st.selectbox("Select a run", range(len(runs)), format_func=lambda i: labels[i])
            selected = runs[idx]
            st.caption(f"Source: `{selected['path']}`")

    if not runs:
        st.warning("**No run records found.** The dashboard renders real data only.")
        st.markdown(
            "Produce one with:\n\n"
            "```bash\n"
            "python run_production.py --start-date 2024-01-01 --end-date 2024-06-30 \\\n"
            "    --universe esg_nasdaq100 --social-source multi_source\n"
            "```\n"
            "or run the offline demo: add `--allow-mock` (clearly synthetic). "
            "A committed sample run lives under `examples/sample_run/`."
        )
        return

    run = load_run(selected["path"])
    run_path = selected["path"]

    tabs = st.tabs(["Overview", "Performance", "Holdings", "Signals",
                    "Proposed Orders", "Validation", "Run History"])
    with tabs[0]:
        surface_overview(run, run_path, spec)
    with tabs[1]:
        surface_performance(run, run_path)
    with tabs[2]:
        surface_holdings(run, run_path)
    with tabs[3]:
        surface_signals(run, run_path)
    with tabs[4]:
        surface_orders(run, run_path)
    with tabs[5]:
        surface_validation(run, spec, config)
    with tabs[6]:
        surface_run_history(runs)


if __name__ == "__main__":
    main()
