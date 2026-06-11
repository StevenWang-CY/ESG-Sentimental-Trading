# Sample run bundle (SYNTHETIC / DEMO ONLY)

This directory contains a small, committed example of the artifacts a single
`run_production.py` run produces, so that `streamlit run dashboard.py` is
populated immediately on a cold clone — **before** you have executed a real
run (the live `results/runs/` and `data/*.csv` outputs are git-ignored).

> ⚠️ **The numbers here are synthetic.** This bundle was generated with
> `--allow-mock`, i.e. against fabricated price / factor / social data. It is
> labelled `data_provenance: mock` and the dashboard renders a prominent
> "DEMO / SYNTHETIC DATA" banner for it. The run intentionally shows
> `status: VALIDATION_FAILED` (a market-neutral strategy on random-walk mock
> prices has no edge) — it exists to exercise every dashboard surface,
> **not** to represent real performance.

## Files

| File | Produced by | Consumed by |
|------|-------------|-------------|
| `run_*.json` | `run_production.py` (canonical run record) | dashboard, `scripts/validate_backtest.py` |
| `signals_*.csv` | signal generation | dashboard Signal Explorer |
| `portfolio_*.csv` | portfolio construction | dashboard Holdings / Proposed Orders |
| `equity_*.csv` | backtest engine (per-period series) | dashboard Performance |
| `tearsheet_*.txt` | `PerformanceAnalyzer.save_tear_sheet` | human-readable reference |

## Reproduce / replace with a real run

```bash
# Real data (requires network; multi_source needs no credentials):
python run_production.py --start-date 2024-01-01 --end-date 2024-12-31 \
    --universe esg_nasdaq100 --social-source multi_source

# Or regenerate this synthetic bundle offline:
python run_production.py --start-date 2024-01-01 --end-date 2024-06-30 \
    --universe custom --tickers AAPL MSFT TSLA XOM JPM NKE SBUX CVX KO PEP NEE DUK \
    --allow-mock --force-refresh
```

A real run writes its record to `results/runs/`, which the dashboard prefers
over this sample automatically.
