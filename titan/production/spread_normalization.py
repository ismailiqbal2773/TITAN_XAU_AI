"""
TITAN XAU AI — Spread Unit Normalization (Sprint v2.8.7-C)
==========================================================
Canonical XAUUSD spread units are USD (float, e.g. 0.15). MT5 / broker
parquet typically exposes `spread` as integer POINTS (e.g. 15). When the
55-feature pipeline computes `spread_pct = spread / close`, the broker
variant is ~100x too large, which collapses the meta-label distribution
and breaks non-canonical broker inference.

This module provides a single reusable normalization function that is
used by:
    - titan.production.feature_stream.H1FeatureStream (load_canonical,
      load_from_mt5, push_bars, push_bar)
    - scripts/research/run_safe_parameter_discovery.py
    - scripts/research/run_meta_label_broker_diagnostic.py
    - scripts/research/run_mtf_reality_close_report.py
    - titan.tests.test_v2_8_7_c_spread_normalization.py

Rules (per Sprint v2.8.7-C spec):
    1. If `spread_usd` column already exists -> use it as-is (NEVER
       double-convert canonical data).
    2. If `spread` column exists and median(spread) > 2.0 -> treat as
       POINTS and convert: spread_usd = spread * 0.01 for XAUUSD.
    3. If `spread` column exists and median(spread) <= 2.0 -> treat as
       already-USD.
    4. If neither column exists -> default spread_usd = 0.0, mark
       unit MISSING_DEFAULT_ZERO.

Side effects on the returned DataFrame:
    - `spread_usd`  column added (always present after normalization)
    - `spread`      column overwritten with USD value (so the feature
                    pipeline can keep reading `spread` as USD)
    - `original_spread` column preserved (raw values, only added when
                    conversion was applied or `spread` existed)
    - `spread_normalized` = True marker
    - `spread_unit_detected` in {USD, POINTS_CONVERTED, MISSING_DEFAULT_ZERO}

This module NEVER sends orders, NEVER creates tokens, NEVER trades.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# XAUUSD point-to-USD conversion factor.
# The Sprint v2.8.7-C spec mandates this single universal factor for the
# XAUUSD symbol across all brokers. Most retail brokers expose XAUUSD
# with digits=2 (point=0.01), so spread_points * 0.01 = spread_usd.
# For brokers with digits=3 (point=0.001, e.g. some Exness accounts) this
# is intentionally a slight over-estimate of spread cost — safe-side.
XAUUSD_POINT_TO_USD: float = 0.01

# Threshold for distinguishing POINTS vs USD when only `spread` is present.
# If median(spread) > 2.0 we assume POINTS (a typical XAUUSD retail spread
# in USD is well below 1.0, while points spread is typically >= 10).
SPREAD_POINTS_DETECTION_THRESHOLD: float = 2.0


def normalize_xauusd_spread_to_usd(
    df: pd.DataFrame,
    symbol: str = "XAUUSD",
    source: str = "unknown",
    *,
    point_to_usd: Optional[float] = None,
    in_place: bool = False,
) -> pd.DataFrame:
    """Normalize XAUUSD spread to USD units.

    Args:
        df: Input DataFrame with OHLC columns. Must contain either
            `spread_usd` or `spread` (or neither — defaults to 0.0).
        symbol: Trading symbol. Only "XAUUSD" is supported by this
            function (other symbols raise NotImplementedError to avoid
            silent misuse).
        source: Free-text source tag (e.g. "canonical", "exness",
            "mt5_live"). Used only for logging.
        point_to_usd: Override conversion factor (defaults to
            XAUUSD_POINT_TO_USD = 0.01). Most callers should NOT pass
            this — the spec mandates 0.01 for XAUUSD.
        in_place: If True, mutate the input DataFrame. If False (default),
            return a copy.

    Returns:
        DataFrame with `spread` (USD), `spread_usd` (USD),
        `original_spread` (raw, when applicable), `spread_normalized=True`,
        and `spread_unit_detected` columns.

    Raises:
        NotImplementedError: if symbol != "XAUUSD".
    """
    if symbol != "XAUUSD":
        raise NotImplementedError(
            f"normalize_xauusd_spread_to_usd only supports XAUUSD "
            f"(got symbol={symbol!r})"
        )

    if not in_place:
        df = df.copy()

    p2u = XAUUSD_POINT_TO_USD if point_to_usd is None else float(point_to_usd)

    # Case 1: spread_usd already exists — canonical path. Never convert.
    if "spread_usd" in df.columns:
        # Ensure float dtype
        df["spread_usd"] = pd.to_numeric(df["spread_usd"], errors="coerce").fillna(0.0)
        # Mirror into `spread` so downstream feature math sees a USD column.
        df["spread"] = df["spread_usd"].astype(float)
        # Preserve original if a raw `spread` column also exists and differs.
        if "original_spread" not in df.columns:
            df["original_spread"] = df["spread_usd"].values
        df["spread_normalized"] = True
        df["spread_unit_detected"] = "USD"
        logger.debug(
            f"[spread_norm] {source}: spread_usd present ({len(df)} bars) "
            f"— used as-is (USD). median={float(df['spread_usd'].median()):.4f}"
        )
        return df

    # Case 2/3: only `spread` column — detect unit by median.
    if "spread" in df.columns:
        raw_spread = pd.to_numeric(df["spread"], errors="coerce").fillna(0.0)
        # Preserve original before any mutation
        df["original_spread"] = raw_spread.values
        median_spread = float(raw_spread.median()) if len(raw_spread) else 0.0

        if median_spread > SPREAD_POINTS_DETECTION_THRESHOLD:
            # POINTS -> USD via XAUUSD factor
            df["spread_usd"] = (raw_spread * p2u).astype(float)
            df["spread"] = df["spread_usd"].astype(float)
            df["spread_normalized"] = True
            df["spread_unit_detected"] = "POINTS_CONVERTED"
            logger.info(
                f"[spread_norm] {source}: spread detected as POINTS "
                f"(median={median_spread:.2f} > {SPREAD_POINTS_DETECTION_THRESHOLD}) — "
                f"converting with factor {p2u}. "
                f"After: median_usd={float(df['spread_usd'].median()):.4f}"
            )
        else:
            # Already USD (small values)
            df["spread_usd"] = raw_spread.astype(float)
            df["spread"] = raw_spread.astype(float)
            df["spread_normalized"] = True
            df["spread_unit_detected"] = "USD"
            logger.info(
                f"[spread_norm] {source}: spread detected as USD "
                f"(median={median_spread:.4f} <= {SPREAD_POINTS_DETECTION_THRESHOLD}) — "
                f"used as-is."
            )
        return df

    # Case 4: neither column present — default to zero, flag missing.
    df["spread_usd"] = 0.0
    df["spread"] = 0.0
    df["spread_normalized"] = True
    df["spread_unit_detected"] = "MISSING_DEFAULT_ZERO"
    logger.warning(
        f"[spread_norm] {source}: no spread column found — defaulting to 0.0 USD."
    )
    return df


def detect_spread_unit(df: pd.DataFrame) -> str:
    """Inspect a DataFrame and return the spread unit that
    `normalize_xauusd_spread_to_usd` would assign.

    Useful for audit reports / tests.
    """
    if "spread_usd" in df.columns:
        return "USD"
    if "spread" in df.columns:
        raw = pd.to_numeric(df["spread"], errors="coerce").fillna(0.0)
        if len(raw) == 0:
            return "MISSING_DEFAULT_ZERO"
        median = float(raw.median())
        if median > SPREAD_POINTS_DETECTION_THRESHOLD:
            return "POINTS_CONVERTED"
        return "USD"
    return "MISSING_DEFAULT_ZERO"


def spread_audit_row(df_raw: pd.DataFrame, df_norm: pd.DataFrame,
                     source: str, close_col: str = "close") -> dict:
    """Build a single audit row comparing raw vs normalized spread.

    Args:
        df_raw: Original DataFrame (before normalization).
        df_norm: Normalized DataFrame (after `normalize_xauusd_spread_to_usd`).
        source: Broker/source name (e.g. "exness").
        close_col: Column name for close price (default "close").

    Returns:
        Dict with raw column name, raw stats, detected unit, normalized
        stats, before/after spread_pct mean, conversion_applied flag.
    """
    import numpy as np  # local import to keep top-level light

    # Identify raw spread column
    raw_col = None
    if "spread_usd" in df_raw.columns:
        raw_col = "spread_usd"
    elif "spread" in df_raw.columns:
        raw_col = "spread"

    if raw_col is None:
        raw_median = 0.0
        raw_p95 = 0.0
        spread_pct_before_mean = 0.0
    else:
        raw_series = pd.to_numeric(df_raw[raw_col], errors="coerce").fillna(0.0)
        raw_median = float(raw_series.median()) if len(raw_series) else 0.0
        raw_p95 = float(raw_series.quantile(0.95)) if len(raw_series) else 0.0
        close_series = pd.to_numeric(df_raw.get(close_col, pd.Series([1.0] * len(df_raw))),
                                     errors="coerce").fillna(1.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            sp_before = (raw_series / close_series).replace([np.inf, -np.inf], 0.0).fillna(0.0)
        spread_pct_before_mean = float(sp_before.mean()) if len(sp_before) else 0.0

    norm_series = pd.to_numeric(df_norm.get("spread_usd", pd.Series([0.0])),
                                errors="coerce").fillna(0.0)
    norm_median = float(norm_series.median()) if len(norm_series) else 0.0
    norm_p95 = float(norm_series.quantile(0.95)) if len(norm_series) else 0.0

    close_norm = pd.to_numeric(df_norm.get(close_col, pd.Series([1.0] * len(df_norm))),
                               errors="coerce").fillna(1.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        sp_after = (norm_series / close_norm).replace([np.inf, -np.inf], 0.0).fillna(0.0)
    spread_pct_after_mean = float(sp_after.mean()) if len(sp_after) else 0.0

    detected = df_norm["spread_unit_detected"].iloc[0] if "spread_unit_detected" in df_norm.columns else "UNKNOWN"
    conversion_applied = (detected == "POINTS_CONVERTED")

    return {
        "source": source,
        "raw_spread_column": raw_col if raw_col else "(none)",
        "raw_spread_median": round(raw_median, 6),
        "raw_spread_p95": round(raw_p95, 6),
        "spread_unit_detected": detected,
        "normalized_spread_median": round(norm_median, 6),
        "normalized_spread_p95": round(norm_p95, 6),
        "spread_pct_mean_before": round(spread_pct_before_mean, 8),
        "spread_pct_mean_after": round(spread_pct_after_mean, 8),
        "conversion_applied": conversion_applied,
        "n_bars": int(len(df_raw)),
    }


__all__ = [
    "XAUUSD_POINT_TO_USD",
    "SPREAD_POINTS_DETECTION_THRESHOLD",
    "normalize_xauusd_spread_to_usd",
    "detect_spread_unit",
    "spread_audit_row",
]
