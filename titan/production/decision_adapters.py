"""TITAN XAU AI — Decision Adapters (v2.8.7-P2.2)
==================================================

Two adapters that wrap CanonicalDecisionEngine:
  - HistoricalAdapter: for backtest/replay (uses stored bars, no freshness check)
  - ShadowAdapter: for live MT5 shadow (uses live data, freshness check)

Both adapters construct a DecisionContext and call CanonicalDecisionEngine.evaluate().
Decision logic is IDENTICAL — only data sourcing differs.

Phase 4 parity invariant:
    Given identical bars, probabilities, InstrumentSpec, account state, and
    configuration, HistoricalAdapter and ShadowAdapter produce IDENTICAL
    CanonicalDecision outputs (modulo adapter_mode field).

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
import numpy as np
import pandas as pd

from titan.production.canonical_decision_engine import (
    CanonicalDecisionEngine, DecisionContext, CanonicalDecision,
)
from titan.production.instrument_valuation import InstrumentSpec
from titan.production.corrected_adaptive_threshold_v2 import SafetyStateV2
from titan.production.near_miss_tracker_v2 import NearMissShadowTrackerV2


@dataclass
class HistoricalAdapter:
    """Adapter for backtest/replay mode.

    Constructs DecisionContext from stored bars and pre-computed inferences.
    Calls CanonicalDecisionEngine for every entry decision.
    """
    instrument: InstrumentSpec
    config: Dict[str, Any]
    safety_state: SafetyStateV2
    equity: float
    equity_peak: float
    daily_peak: float
    daily_start_equity: float
    existing_daily_open_risk: float = 0.0
    existing_total_open_risk: float = 0.0
    existing_combined_risk: float = 0.0
    loss_streak: int = 0

    def evaluate_bar(self, df: pd.DataFrame, i: int,
                     alpha_proba: float, meta_proba: float,
                     atr_value: float, entry_price: float,
                     spread: float, timestamp: str,
                     alpha_dist: Optional[np.ndarray] = None,
                     meta_dist: Optional[np.ndarray] = None) -> CanonicalDecision:
        """Evaluate a single bar through the canonical engine.

        Uses df.iloc[max(0, i-100):i+1] as the window for regime/setup scanning.
        Skips freshness check (historical mode).
        """
        # Use a window of bars for regime/setup (not the full df)
        window_start = max(0, i - 100)
        df_window = df.iloc[window_start:i + 1].copy()
        # Ensure 'spread' column exists for regime classifier and setup scanner
        if "spread" not in df_window.columns and "spread_usd" in df_window.columns:
            df_window["spread"] = df_window["spread_usd"]
        # Ensure 'volume' column exists for regime classifier
        if "volume" not in df_window.columns and "tick_volume" in df_window.columns:
            df_window["volume"] = df_window["tick_volume"]

        # Use provided distributions or fallback to single value
        if alpha_dist is None:
            alpha_dist = np.array([alpha_proba])
        if meta_dist is None:
            meta_dist = np.array([meta_proba])

        ctx = DecisionContext(
            df=df_window,
            alpha_proba=alpha_proba, meta_proba=meta_proba,
            alpha_probas_recent=alpha_dist,
            meta_probas_recent=meta_dist,
            atr_value=atr_value,
            instrument=self.instrument,
            config=self.config,
            safety_state=self.safety_state,
            equity=self.equity, equity_peak=self.equity_peak,
            daily_peak=self.daily_peak, daily_start_equity=self.daily_start_equity,
            existing_daily_open_risk=self.existing_daily_open_risk,
            existing_total_open_risk=self.existing_total_open_risk,
            existing_combined_risk=self.existing_combined_risk,
            loss_streak=self.loss_streak,
            adapter_mode="historical",
            near_miss_tracker=None,
            spread=spread, entry_price=entry_price,
            timestamp=timestamp,
            skip_freshness_check=True,
        )
        engine = CanonicalDecisionEngine()
        return engine.evaluate(ctx)


@dataclass
class ShadowAdapter:
    """Adapter for live MT5 shadow mode.

    Constructs DecisionContext from live MT5 data and model inferences.
    Calls CanonicalDecisionEngine for the current bar.
    """
    instrument: InstrumentSpec
    config: Dict[str, Any]
    safety_state: SafetyStateV2
    equity: float
    equity_peak: float
    daily_peak: float
    daily_start_equity: float
    existing_daily_open_risk: float = 0.0
    existing_total_open_risk: float = 0.0
    existing_combined_risk: float = 0.0
    loss_streak: int = 0
    near_miss_tracker: Optional[NearMissShadowTrackerV2] = None

    def evaluate_bar(self, df: pd.DataFrame,
                     alpha_proba: float, meta_proba: float,
                     atr_value: float, entry_price: float,
                     spread: float, timestamp: str,
                     alpha_probas_recent: np.ndarray,
                     meta_probas_recent: np.ndarray) -> CanonicalDecision:
        """Evaluate the current bar through the canonical engine.

        Uses the full df (live data window) for regime/setup scanning.
        Freshness check is enabled (shadow mode).
        """
        ctx = DecisionContext(
            df=df,
            alpha_proba=alpha_proba, meta_proba=meta_proba,
            alpha_probas_recent=alpha_probas_recent,
            meta_probas_recent=meta_probas_recent,
            atr_value=atr_value,
            instrument=self.instrument,
            config=self.config,
            safety_state=self.safety_state,
            equity=self.equity, equity_peak=self.equity_peak,
            daily_peak=self.daily_peak, daily_start_equity=self.daily_start_equity,
            existing_daily_open_risk=self.existing_daily_open_risk,
            existing_total_open_risk=self.existing_total_open_risk,
            existing_combined_risk=self.existing_combined_risk,
            loss_streak=self.loss_streak,
            adapter_mode="shadow",
            near_miss_tracker=self.near_miss_tracker,
            spread=spread, entry_price=entry_price,
            timestamp=timestamp,
            skip_freshness_check=False,
        )
        engine = CanonicalDecisionEngine()
        return engine.evaluate(ctx)


__all__ = ["HistoricalAdapter", "ShadowAdapter"]
