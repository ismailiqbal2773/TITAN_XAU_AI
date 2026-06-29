"""
TITAN XAU AI — Profit Capture Engine (Sprint 9.9.3.30)
========================================================

Maximizes profit from winners without increasing downside risk.
Produces ProfitCaptureDecision objects for the ExitDecisionCoordinator.

Rules:
  - Can extend TP only when SL defense says risk is controlled (safe_to_hold)
  - Partial close preserves runner position
  - Range regime favors faster profit taking
  - Trend aligned with trade → allow winners to run
  - Gold impulse extends TP only with high confidence
  - Never increases lot size
  - Never disables SL protection
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class ProfitAction(str, Enum):
    HOLD = "HOLD"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    EXTEND_TP = "EXTEND_TP"
    TRAIL_TP = "TRAIL_TP"
    LOCK_PROFIT = "LOCK_PROFIT"
    TAKE_PROFIT = "TAKE_PROFIT"
    NO_ACTION = "NO_ACTION"


@dataclass
class ProfitCaptureDecision:
    action: ProfitAction = ProfitAction.NO_ACTION
    allowed: bool = True
    partial_close_pct: float = 0.0    # 0.0–1.0
    new_tp: Optional[float] = None
    tp_extension_factor: float = 1.0  # > 1.0 extends TP further
    profit_lock_level: Optional[float] = None
    reason: str = ""
    regime: str = "UNKNOWN"
    confidence: float = 0.0
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


class ProfitCaptureEngine:
    """Evaluates profit capture based on trade state + regime."""

    def evaluate(self,
                 entry_price: float,
                 current_price: float,
                 current_tp: float,
                 side: str,
                 atr: float = 0.0,
                 regime: str = "UNKNOWN",
                 r_multiple: float = 0.0,
                 confidence: float = 0.0,
                 safe_to_hold: bool = True,
                 trade_age_seconds: float = 0.0,
                 ) -> ProfitCaptureDecision:
        """Evaluate profit capture. Never raises."""
        try:
            if not safe_to_hold:
                return ProfitCaptureDecision(
                    action=ProfitAction.NO_ACTION, allowed=False,
                    reason="SL defense says not safe to hold — profit capture disabled",
                    regime=regime, confidence=confidence,
                )

            # ── Range regime: faster profit taking ──
            if regime == "RANGE":
                if r_multiple >= 1.0:
                    return ProfitCaptureDecision(
                        action=ProfitAction.TAKE_PROFIT, allowed=True,
                        reason=f"Range regime + {r_multiple:.1f}R — take profit",
                        regime=regime, confidence=confidence,
                    )
                if r_multiple >= 0.5:
                    return ProfitCaptureDecision(
                        action=ProfitAction.PARTIAL_CLOSE, allowed=True,
                        partial_close_pct=0.5,
                        reason=f"Range regime + {r_multiple:.1f}R — partial close 50%",
                        regime=regime, confidence=confidence,
                    )

            # ── Weak momentum: book profit ──
            if regime in ("LOW_VOLATILITY", "UNKNOWN") and r_multiple >= 0.8:
                return ProfitCaptureDecision(
                    action=ProfitAction.PARTIAL_CLOSE, allowed=True,
                    partial_close_pct=0.25,
                    reason=f"Weak momentum ({regime}) + {r_multiple:.1f}R — book 25%",
                    regime=regime, confidence=confidence,
                )

            # ── Strong trend aligned with trade: extend TP (before partial closes) ──
            trend_aligned = (
                (regime == "TREND_UP" and side == "BUY") or
                (regime == "TREND_DOWN" and side == "SELL")
            )
            if trend_aligned and r_multiple > 0 and safe_to_hold:
                ext_factor = 1.5
                new_tp = self._extend_tp(current_tp, side, atr, ext_factor)
                return ProfitCaptureDecision(
                    action=ProfitAction.EXTEND_TP, allowed=True,
                    new_tp=new_tp, tp_extension_factor=ext_factor,
                    reason=f"Strong trend ({regime}) aligned — extend TP x{ext_factor}",
                    regime=regime, confidence=confidence,
                )

            # ── Gold impulse: extend TP only with high confidence ──
            if regime == "GOLD_IMPULSE" and confidence > 0.7 and r_multiple > 0:
                ext_factor = 1.3
                new_tp = self._extend_tp(current_tp, side, atr, ext_factor)
                return ProfitCaptureDecision(
                    action=ProfitAction.EXTEND_TP, allowed=True,
                    new_tp=new_tp, tp_extension_factor=ext_factor,
                    reason=f"Gold impulse + high confidence ({confidence:.2f}) — extend TP x{ext_factor}",
                    regime=regime, confidence=confidence,
                )

            # ── Partial closes at +1R, +2R, +3R ──
            if r_multiple >= 3.0:
                return ProfitCaptureDecision(
                    action=ProfitAction.PARTIAL_CLOSE, allowed=True,
                    partial_close_pct=0.25,
                    profit_lock_level=current_price,
                    reason=f"Profit {r_multiple:.1f}R >= 3R — lock profit, close 25%",
                    regime=regime, confidence=confidence,
                )
            if r_multiple >= 2.0:
                return ProfitCaptureDecision(
                    action=ProfitAction.PARTIAL_CLOSE, allowed=True,
                    partial_close_pct=0.25,
                    reason=f"Profit {r_multiple:.1f}R >= 2R — partial close 25%",
                    regime=regime, confidence=confidence,
                )
            if r_multiple >= 1.0:
                return ProfitCaptureDecision(
                    action=ProfitAction.LOCK_PROFIT, allowed=True,
                    profit_lock_level=entry_price,
                    reason=f"Profit {r_multiple:.1f}R >= 1R — lock profit at breakeven",
                    regime=regime, confidence=confidence,
                )

            # ── Time-based profit decay (long-held trade with small profit) ──
            if trade_age_seconds > 3600 and 0 < r_multiple < 0.5:
                return ProfitCaptureDecision(
                    action=ProfitAction.TAKE_PROFIT, allowed=True,
                    reason=f"Time decay ({trade_age_seconds:.0f}s) + small profit ({r_multiple:.1f}R) — take profit",
                    regime=regime, confidence=confidence,
                )

            # ── Default: hold ──
            return ProfitCaptureDecision(
                action=ProfitAction.HOLD, allowed=True,
                reason="No profit capture trigger — hold",
                regime=regime, confidence=confidence,
            )
        except Exception:
            return ProfitCaptureDecision(
                action=ProfitAction.NO_ACTION, allowed=False,
                reason="Profit capture exception — fail-safe no action",
                regime=regime, confidence=confidence,
            )

    def _extend_tp(self, current_tp: float, side: str,
                    atr: float, factor: float) -> float:
        """Extend TP further from entry by factor * ATR."""
        if atr <= 0 or current_tp <= 0:
            return current_tp
        extension = atr * factor
        if side == "BUY":
            return current_tp + extension
        else:
            return current_tp - extension
