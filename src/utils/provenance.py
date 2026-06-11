"""
Data provenance and fail-closed guards for the ESG trading pipeline.

The cardinal rule of this repository: a production run must NEVER silently
consume fabricated/synthetic data. Historically every fetcher fell back to
``np.random`` data on any API/credential/network failure even when
``use_mock=False``, and the orchestrator consumed the result with no realness
check -- which is exactly how an unreproducible headline backtest can be
manufactured.

This module provides:

* :class:`DataUnavailableError` -- raised by fetchers when a production
  (``allow_mock=False``) fetch cannot obtain real data.
* :func:`tag` / :func:`get_provenance` / :func:`is_mock` -- stamp and read a
  provenance marker on a DataFrame. The marker is stored both in
  ``df.attrs`` (cheap, survives most ops) and is intended to be re-applied by
  any stage that performs ``pd.concat`` (which drops ``attrs``).
* :func:`guard_real` -- the orchestrator-side gate that aborts the run if a
  stage produced mock or empty data on a real-data run.

Provenance values:
    ``REAL``  -- obtained from the real external source.
    ``MOCK``  -- synthetic data, only ever produced behind an explicit
                 ``allow_mock=True`` flag; must be loud and recorded in run
                 metadata.
    ``EMPTY`` -- a real fetch that legitimately returned no rows.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

REAL = "real"
MOCK = "mock"
EMPTY = "empty"

PROVENANCE_KEY = "provenance"
SOURCE_KEY = "data_source"


class DataUnavailableError(RuntimeError):
    """Raised when a production fetch (``allow_mock=False``) cannot get real data.

    Fetchers raise this instead of silently fabricating synthetic data so the
    pipeline fails closed rather than reporting fabricated results as real.
    """


def tag(df: pd.DataFrame, provenance: str, source: Optional[str] = None) -> pd.DataFrame:
    """Stamp ``df`` with a provenance marker (and optional source name).

    Returns the same frame for chaining. Safe on any object; no-op if attrs
    cannot be set.
    """
    try:
        df.attrs[PROVENANCE_KEY] = provenance
        if source is not None:
            df.attrs[SOURCE_KEY] = source
    except Exception:
        pass
    return df


def get_provenance(df: pd.DataFrame, default: str = REAL) -> str:
    """Return the provenance marker on ``df`` (``REAL`` if unmarked)."""
    try:
        return df.attrs.get(PROVENANCE_KEY, default)
    except Exception:
        return default


def is_mock(df) -> bool:
    """True if ``df`` is explicitly marked as synthetic/mock data."""
    try:
        return isinstance(df, pd.DataFrame) and df.attrs.get(PROVENANCE_KEY) == MOCK
    except Exception:
        return False


def guard_real(df: pd.DataFrame, stage: str, allow_empty: bool = False) -> pd.DataFrame:
    """Abort the run if ``df`` is mock, or (unless ``allow_empty``) empty.

    Called by the orchestrator immediately after each fetch stage on a
    production (real-data) run. Raises :class:`DataUnavailableError` with an
    actionable message rather than letting synthetic/empty data flow into the
    backtest and be reported as real.
    """
    if df is None:
        raise DataUnavailableError(f"{stage}: fetch returned None (no data)")
    if is_mock(df):
        raise DataUnavailableError(
            f"{stage}: refusing to proceed -- data is synthetic/mock. "
            f"A real-data run must not consume fabricated data. Check network/"
            f"credentials, or pass allow_mock=True explicitly for a demo run."
        )
    if not allow_empty and isinstance(df, pd.DataFrame) and df.empty:
        raise DataUnavailableError(
            f"{stage}: real fetch returned zero rows. Aborting rather than "
            f"backtesting on empty data."
        )
    return df
