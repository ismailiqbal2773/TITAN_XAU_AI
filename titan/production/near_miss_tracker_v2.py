"""TITAN XAU AI — Near-Miss Shadow Tracker V2 (Sprint v2.8.7-P1.1)
==================================================================
DG10: Timeframe-aware expiry; post-cost outcomes; atomic consume_re_entry.
NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime, timezone
import numpy as np
import pandas as pd

TIMEFRAME_MINUTES = {"H1": 60, "M15": 15, "M5": 5, "H4": 240, "D1": 1440}


@dataclass
class NearMissRecordV2:
    timestamp: str
    direction: str
    setup_type: str
    regime: str
    score: float
    effective_threshold: float
    component_scores: dict
    rejection_reasons: List[str]
    hypothetical_entry: float
    hypothetical_sl: float
    hypothetical_tp: float
    expiry_time: str
    rr: float
    spread: float
    commission: float
    slippage: float
    # Filled later
    later_max_favourable_excursion: float = 0.0
    later_max_adverse_excursion: float = 0.0
    post_cost_hypothetical_outcome: float = 0.0
    evaluated: bool = False
    re_entry_consumed: bool = False  # DG10: Atomic flag inside tracker


class NearMissShadowTrackerV2:
    """Tracks near-miss rejections with timeframe-aware expiry and post-cost evaluation."""

    def __init__(self, timeframe: str = "H1", evaluation_horizon_bars: int = 12,
                 commission: float = 7.0, spread: float = 0.3, slippage: float = 0.5):
        self.records: List[NearMissRecordV2] = []
        self.timeframe = timeframe
        self.evaluation_horizon_bars = evaluation_horizon_bars
        self.commission = commission
        self.spread = spread
        self.slippage = slippage

    def record_near_miss(self, timestamp: str, direction: str, setup_type: str,
                          regime: str, score: float, effective_threshold: float,
                          component_scores: dict, rejection_reasons: List[str],
                          hypothetical_entry: float, hypothetical_sl: float,
                          hypothetical_tp: float, expiry_bars: int = 6) -> NearMissRecordV2:
        """Record a near-miss with timeframe-aware expiry."""
        tf_minutes = TIMEFRAME_MINUTES.get(self.timeframe, 60)
        ts = pd.Timestamp(timestamp)
        expiry = ts + pd.Timedelta(minutes=expiry_bars * tf_minutes)
        rr = abs(hypothetical_tp - hypothetical_entry) / max(abs(hypothetical_entry - hypothetical_sl), 0.001)
        record = NearMissRecordV2(
            timestamp=timestamp, direction=direction, setup_type=setup_type,
            regime=regime, score=score, effective_threshold=effective_threshold,
            component_scores=component_scores, rejection_reasons=rejection_reasons,
            hypothetical_entry=hypothetical_entry, hypothetical_sl=hypothetical_sl,
            hypothetical_tp=hypothetical_tp, expiry_time=str(expiry),
            rr=rr, spread=self.spread, commission=self.commission, slippage=self.slippage,
        )
        self.records.append(record)
        return record

    def evaluate_outcomes(self, df: pd.DataFrame):
        """Evaluate hypothetical outcomes with post-cost calculation."""
        for record in self.records:
            if record.evaluated:
                continue
            try:
                ts = pd.Timestamp(record.timestamp)
                start_idx = df.index.get_loc(ts)
            except (KeyError, ValueError):
                continue
            end_idx = min(start_idx + self.evaluation_horizon_bars, len(df) - 1)
            if start_idx >= end_idx:
                continue

            entry = record.hypothetical_entry
            sl = record.hypothetical_sl
            tp = record.hypothetical_tp
            # Apply spread at entry and exit
            if record.direction == "LONG":
                entry_with_cost = entry + record.spread + record.slippage
                exit_spread = record.spread
            else:
                entry_with_cost = entry - record.spread - record.slippage
                exit_spread = record.spread

            highs = df["high"].iloc[start_idx+1:end_idx+1].values
            lows = df["low"].iloc[start_idx+1:end_idx+1].values
            closes = df["close"].iloc[start_idx+1:end_idx+1].values

            if record.direction == "LONG":
                record.later_max_favourable_excursion = float(max(highs) - entry) if len(highs) > 0 else 0
                record.later_max_adverse_excursion = float(entry - min(lows)) if len(lows) > 0 else 0
                sl_dist = max(abs(entry_with_cost - sl), 0.001)
                for h, l, c in zip(highs, lows, closes):
                    if l <= sl:
                        exit_price = sl - exit_spread
                        record.post_cost_hypothetical_outcome = (exit_price - entry_with_cost) / sl_dist
                        break
                    if h >= tp:
                        exit_price = tp - exit_spread
                        record.post_cost_hypothetical_outcome = (exit_price - entry_with_cost) / sl_dist
                        break
                else:
                    exit_price = closes[-1] - exit_spread
                    record.post_cost_hypothetical_outcome = (exit_price - entry_with_cost) / sl_dist
            else:
                record.later_max_favourable_excursion = float(entry - min(lows)) if len(lows) > 0 else 0
                record.later_max_adverse_excursion = float(max(highs) - entry) if len(highs) > 0 else 0
                sl_dist = max(abs(sl - entry_with_cost), 0.001)
                for h, l, c in zip(highs, lows, closes):
                    if h >= sl:
                        exit_price = sl + exit_spread
                        record.post_cost_hypothetical_outcome = (entry_with_cost - exit_price) / sl_dist
                        break
                    if l <= tp:
                        exit_price = tp + exit_spread
                        record.post_cost_hypothetical_outcome = (entry_with_cost - exit_price) / sl_dist
                        break
                else:
                    exit_price = closes[-1] + exit_spread
                    record.post_cost_hypothetical_outcome = (entry_with_cost - exit_price) / sl_dist

            # Subtract commission
            lot_size = 1.0  # Simplified
            record.post_cost_hypothetical_outcome -= record.commission * lot_size / (sl_dist * 100)
            record.evaluated = True

    def preview_re_entry_eligibility(self, record: NearMissRecordV2, current_time: pd.Timestamp,
                                       current_price: float, new_confirmation: bool,
                                       hard_gates_clear: bool = False) -> tuple[bool, str]:
        """v2.8.7-P2.1 Phase 6: Preview re-entry eligibility WITHOUT mutating the record.

        Shadow mode may call this method. It does NOT mark the record as consumed.

        Args:
            record: The near-miss record to evaluate.
            current_time: Current timestamp.
            current_price: Current price.
            new_confirmation: Whether a new market confirmation has occurred.
            hard_gates_clear: Whether hard gates have cleared. Default False
                (fail-closed). Shadow mode should pass False since shadow has
                no real hard-gates transaction.

        Returns:
            (eligible, reason) — eligible=True means a future authorized
            execution transaction COULD consume this re-entry. eligible=False
            means the record is ineligible for the given reason.
        """
        if record.re_entry_consumed:
            return False, "re_entry_already_consumed"
        if not hard_gates_clear:
            return False, "hard_gates_not_clear"
        try:
            expiry = pd.Timestamp(record.expiry_time)
            if pd.Timestamp(current_time) > expiry:
                return False, "setup_expired"
        except Exception as e:
            return False, f"expiry_check_error:{e}"
        if not new_confirmation:
            return False, "no_new_confirmation"
        try:
            price_diff = abs(float(current_price) - float(record.hypothetical_entry))
            max_chase = abs(float(record.hypothetical_entry) - float(record.hypothetical_sl)) * 0.3
            if price_diff > max_chase:
                return False, "price_chasing"
            rr = abs(float(record.hypothetical_tp) - float(current_price)) / \
                 max(abs(float(current_price) - float(record.hypothetical_sl)), 0.001)
            if rr < 1.5:
                return False, "insufficient_post_cost_reward"
        except Exception as e:
            return False, f"eligibility_check_error:{e}"
        return True, "eligible_for_re_entry"

    def consume_re_entry(self, record: NearMissRecordV2, current_time: pd.Timestamp,
                          current_price: float, new_confirmation: bool,
                          hard_gates_clear: bool = False,
                          authorized_execution_transaction: bool = False) -> tuple[bool, str]:
        """v2.8.7-P2.1 Phase 6: Atomic consume_re_entry.

        May ONLY be called during a future authorized execution transaction
        with actual hard gates, actual new confirmation, atomic
        decision/position transaction, and audit journal.

        Args:
            record: The near-miss record to consume.
            current_time: Current timestamp.
            current_price: Current price.
            new_confirmation: Whether a new market confirmation has occurred.
            hard_gates_clear: Whether hard gates have cleared. Default False
                (fail-closed).
            authorized_execution_transaction: Must be True to consume. This
                flag ensures the caller is in an actual execution transaction
                (not shadow mode).

        Returns:
            (consumed, reason). consumed=True means the record was atomically
            marked as consumed.
        """
        if not authorized_execution_transaction:
            return False, "not_in_authorized_execution_transaction"
        # Preview eligibility first (without mutating)
        eligible, reason = self.preview_re_entry_eligibility(
            record, current_time, current_price, new_confirmation, hard_gates_clear
        )
        if not eligible:
            return False, reason
        # Atomically mark consumed
        record.re_entry_consumed = True
        return True, "re_entry_consumed"

    def get_false_negative_estimate(self) -> dict:
        if not self.records:
            return {"false_negative_rate": 0, "sample_size": 0}
        evaluated = [r for r in self.records if r.evaluated]
        if not evaluated:
            return {"false_negative_rate": 0, "sample_size": 0}
        false_negs = sum(1 for r in evaluated if r.post_cost_hypothetical_outcome > 0)
        return {
            "false_negative_rate": round(false_negs / len(evaluated), 4),
            "sample_size": len(evaluated),
            "total_near_misses": len(self.records),
        }


__all__ = ["NearMissRecordV2", "NearMissShadowTrackerV2", "TIMEFRAME_MINUTES"]
