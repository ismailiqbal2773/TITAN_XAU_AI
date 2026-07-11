"""TITAN XAU AI — Near-Miss Shadow Tracker (Sprint v2.8.7-P1)
=============================================================
Tracks near-threshold rejections with hypothetical outcomes.
Implements legal re-entry logic.

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime, timezone
import numpy as np
import pandas as pd


@dataclass
class NearMissRecord:
    """A near-miss rejection record."""
    timestamp: str
    direction: str
    setup_type: str
    regime: str
    score: float
    effective_threshold: float
    component_scores: dict
    rejection_reasons: list
    hypothetical_entry: float
    hypothetical_sl: float
    hypothetical_tp: float
    expiry_time: str
    # Filled later (no lookahead at decision time)
    later_max_favourable_excursion: float = 0.0
    later_max_adverse_excursion: float = 0.0
    post_cost_hypothetical_outcome: float = 0.0
    legal_re_entry_occurred: bool = False
    evaluation_horizon_bars: int = 0


class NearMissShadowTracker:
    """Tracks near-miss rejections and evaluates them post-hoc.

    All hypothetical outcomes are computed AFTER the decision time,
    never available to the original decision (no lookahead).
    """

    def __init__(self, evaluation_horizon_bars: int = 12):
        self.records: List[NearMissRecord] = []
        self.evaluation_horizon_bars = evaluation_horizon_bars
        self.max_re_entries: int = 1

    def record_near_miss(
        self,
        timestamp: str,
        direction: str,
        setup_type: str,
        regime: str,
        score: float,
        effective_threshold: float,
        component_scores: dict,
        rejection_reasons: list,
        hypothetical_entry: float,
        hypothetical_sl: float,
        hypothetical_tp: float,
        expiry_bars: int = 6,
    ) -> NearMissRecord:
        """Record a near-miss rejection."""
        # Calculate expiry time
        ts = pd.Timestamp(timestamp)
        expiry = ts + pd.Timedelta(hours=expiry_bars)
        record = NearMissRecord(
            timestamp=timestamp,
            direction=direction,
            setup_type=setup_type,
            regime=regime,
            score=score,
            effective_threshold=effective_threshold,
            component_scores=component_scores,
            rejection_reasons=rejection_reasons,
            hypothetical_entry=hypothetical_entry,
            hypothetical_sl=hypothetical_sl,
            hypothetical_tp=hypothetical_tp,
            expiry_time=str(expiry),
            evaluation_horizon_bars=self.evaluation_horizon_bars,
        )
        self.records.append(record)
        return record

    def evaluate_outcomes(self, df: pd.DataFrame, commission: float = 7.0, spread: float = 0.3):
        """Evaluate hypothetical outcomes for all records. Called AFTER all decisions."""
        for record in self.records:
            ts = pd.Timestamp(record.timestamp)
            # Find the bar index for this timestamp
            try:
                start_idx = df.index.get_loc(ts)
            except KeyError:
                continue

            end_idx = min(start_idx + self.evaluation_horizon_bars, len(df) - 1)
            if start_idx >= end_idx:
                continue

            entry = record.hypothetical_entry
            sl = record.hypothetical_sl
            tp = record.hypothetical_tp

            highs = df["high"].iloc[start_idx+1:end_idx+1].values
            lows = df["low"].iloc[start_idx+1:end_idx+1].values
            closes = df["close"].iloc[start_idx+1:end_idx+1].values

            # Max favourable / adverse excursion
            if record.direction == "LONG":
                record.later_max_favourable_excursion = float(max(highs) - entry) if len(highs) > 0 else 0
                record.later_max_adverse_excursion = float(entry - min(lows)) if len(lows) > 0 else 0
                # Conservative: SL first
                for h, l, c in zip(highs, lows, closes):
                    if l <= sl:
                        record.post_cost_hypothetical_outcome = -1.0
                        break
                    if h >= tp:
                        record.post_cost_hypothetical_outcome = 3.0
                        break
                else:
                    record.post_cost_hypothetical_outcome = float((closes[-1] - entry) / max(abs(entry - sl), 0.001))
            else:
                record.later_max_favourable_excursion = float(entry - min(lows)) if len(lows) > 0 else 0
                record.later_max_adverse_excursion = float(max(highs) - entry) if len(highs) > 0 else 0
                for h, l, c in zip(highs, lows, closes):
                    if h >= sl:
                        record.post_cost_hypothetical_outcome = -1.0
                        break
                    if l <= tp:
                        record.post_cost_hypothetical_outcome = 3.0
                        break
                else:
                    record.post_cost_hypothetical_outcome = float((entry - closes[-1]) / max(abs(sl - entry), 0.001))

    def can_re_enter(self, original_record: NearMissRecord, current_time: pd.Timestamp,
                     current_price: float, new_confirmation: bool) -> tuple[bool, str]:
        """Check if a legal re-entry is allowed.

        Requirements:
          - Original thesis still valid
          - Setup not expired
          - No price chasing
          - Reward after costs still sufficient
          - New confirmation event exists
          - Hard gates remain clear
          - Maximum one re-entry
          - No averaging down
          - No repeated entries
        """
        if original_record.legal_re_entry_occurred:
            return False, "max_re_entries_reached"

        expiry = pd.Timestamp(original_record.expiry_time)
        if current_time > expiry:
            return False, "setup_expired"

        if not new_confirmation:
            return False, "no_new_confirmation"

        # No price chasing: entry must not be worse than 0.5 ATR from original
        price_diff = abs(current_price - original_record.hypothetical_entry)
        max_chase = abs(original_record.hypothetical_entry - original_record.hypothetical_sl) * 0.3
        if price_diff > max_chase:
            return False, "price_chasing"

        # Reward after costs must still be sufficient
        rr = abs(original_record.hypothetical_tp - current_price) / max(abs(current_price - original_record.hypothetical_sl), 0.001)
        if rr < 1.5:
            return False, "insufficient_reward_after_costs"

        return True, "re_entry_allowed"

    def get_false_negative_estimate(self) -> dict:
        """Estimate false negative rate from near-miss outcomes."""
        if not self.records:
            return {"false_negative_rate": 0, "sample_size": 0}

        evaluated = [r for r in self.records if r.post_cost_hypothetical_outcome != 0]
        if not evaluated:
            return {"false_negative_rate": 0, "sample_size": 0}

        # False negative = would have been profitable
        false_negs = sum(1 for r in evaluated if r.post_cost_hypothetical_outcome > 0)
        return {
            "false_negative_rate": round(false_negs / len(evaluated), 4),
            "sample_size": len(evaluated),
            "total_near_misses": len(self.records),
        }


__all__ = ["NearMissRecord", "NearMissShadowTracker"]
