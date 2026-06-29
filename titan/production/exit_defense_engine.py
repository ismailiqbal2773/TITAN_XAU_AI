"""
TITAN XAU AI — SL Defense Engine (Sprint 9.9.3.30)
====================================================

Reduces drawdown and protects capital. Produces SLDefenseDecision
objects that the ExitDecisionCoordinator resolves with ProfitCaptureDecision.

Rules:
  - SL engine can ONLY reduce risk (never widen beyond ATR/regime limit)
  - NEWS_SHOCK, LIQUIDITY_VACUUM, spread expansion → emergency exit or block
  - UNKNOWN regime must reduce risk
  - Fail-safe: HOLD only if no active risk; otherwise tighten/protect
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class SLAction(str, Enum):
    HOLD = "HOLD"
    MOVE_TO_BREAKEVEN = "MOVE_TO_BREAKEVEN"
    TRAIL_SL = "TRAIL_SL"
    TIGHTEN_SL = "TIGHTEN_SL"
    EMERGENCY_EXIT = "EMERGENCY_EXIT"
    NO_ACTION = "NO_ACTION"


@dataclass
class SLDefenseDecision:
    action: SLAction = SLAction.NO_ACTION
    allowed: bool = True
    new_sl: Optional[float] = None
    risk_reduction_factor: float = 1.0   # <= 1.0
    reason: str = ""
    regime: str = "UNKNOWN"
    confidence: float = 0.0
    timestamp_utc: str = ""

    def __post_init__(self):
        if self.risk_reduction_factor > 1.0:
            self.risk_reduction_factor = 1.0
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


class SLDefenseEngine:
    """Evaluates SL defense based on trade state + regime + risk context."""

    def evaluate(self,
                 entry_price: float,
                 current_price: float,
                 current_sl: float,
                 side: str,               # "BUY" or "SELL"
                 atr: float = 0.0,
                 regime: str = "UNKNOWN",
                 volatility_score: float = 0.0,
                 spread_score: float = 0.0,
                 liquidity_score: float = 1.0,
                 max_adverse_excursion: float = 0.0,
                 trade_age_seconds: float = 0.0,
                 max_trade_age_seconds: float = 0.0,
                 confidence: float = 0.0,
                 ) -> SLDefenseDecision:
        """Evaluate SL defense. Never raises — returns fail-safe on error."""
        try:
            # Calculate current R-multiple (profit/loss in ATR units)
            if side == "BUY":
                pnl = current_price - entry_price
            else:
                pnl = entry_price - current_price
            r_multiple = pnl / atr if atr > 0 else 0.0

            # ── Emergency conditions (highest priority) ──
            if regime == "NEWS_SHOCK":
                return SLDefenseDecision(
                    action=SLAction.EMERGENCY_EXIT, allowed=False,
                    risk_reduction_factor=0.0,
                    reason="NEWS_SHOCK — emergency exit",
                    regime=regime, confidence=confidence,
                )
            if regime == "LIQUIDITY_VACUUM":
                return SLDefenseDecision(
                    action=SLAction.EMERGENCY_EXIT, allowed=False,
                    risk_reduction_factor=0.0,
                    reason="LIQUIDITY_VACUUM — emergency exit",
                    regime=regime, confidence=confidence,
                )
            if spread_score > 0.85:
                return SLDefenseDecision(
                    action=SLAction.EMERGENCY_EXIT, allowed=False,
                    risk_reduction_factor=0.2,
                    reason=f"Severe spread expansion ({spread_score:.2f}) — emergency exit",
                    regime=regime, confidence=confidence,
                )

            # ── Stale trade protection ──
            if max_trade_age_seconds > 0 and trade_age_seconds > max_trade_age_seconds:
                return SLDefenseDecision(
                    action=SLAction.EMERGENCY_EXIT, allowed=False,
                    risk_reduction_factor=0.3,
                    reason=f"Stale trade ({trade_age_seconds:.0f}s > {max_trade_age_seconds:.0f}s) — emergency exit",
                    regime=regime, confidence=confidence,
                )

            # ── Max adverse excursion ──
            if max_adverse_excursion > 0 and atr > 0:
                mae_r = max_adverse_excursion / atr
                if mae_r > 2.0:
                    return SLDefenseDecision(
                        action=SLAction.EMERGENCY_EXIT, allowed=False,
                        risk_reduction_factor=0.3,
                        reason=f"MAE {mae_r:.1f}R > 2.0R — emergency exit",
                        regime=regime, confidence=confidence,
                    )

            # ── High volatility risk compression ──
            if volatility_score > 0.7 or regime == "HIGH_VOLATILITY":
                # Tighten SL to 0.5 ATR
                new_sl = self._compute_tightened_sl(entry_price, side, atr, factor=0.5)
                return SLDefenseDecision(
                    action=SLAction.TIGHTEN_SL, allowed=True,
                    new_sl=new_sl, risk_reduction_factor=0.5,
                    reason=f"High volatility ({volatility_score:.2f}) — tighten SL to 0.5 ATR",
                    regime=regime, confidence=confidence,
                )

            # ── Trailing SL (trade in profit >= 1.5R) — check before breakeven ──
            if r_multiple >= 1.5:
                trail_sl = self._compute_trailing_sl(current_price, side, atr, factor=1.0)
                # Never widen — only tighten
                if side == "BUY" and (current_sl is None or trail_sl > current_sl):
                    return SLDefenseDecision(
                        action=SLAction.TRAIL_SL, allowed=True,
                        new_sl=trail_sl, risk_reduction_factor=0.7,
                        reason=f"Profit {r_multiple:.1f}R >= 1.5R — trail SL at 1 ATR",
                        regime=regime, confidence=confidence,
                    )
                elif side == "SELL" and (current_sl is None or trail_sl < current_sl):
                    return SLDefenseDecision(
                        action=SLAction.TRAIL_SL, allowed=True,
                        new_sl=trail_sl, risk_reduction_factor=0.7,
                        reason=f"Profit {r_multiple:.1f}R >= 1.5R — trail SL at 1 ATR",
                        regime=regime, confidence=confidence,
                    )

            # ── Breakeven trigger (1R <= profit < 1.5R) ──
            if r_multiple >= 1.0 and current_sl != entry_price:
                return SLDefenseDecision(
                    action=SLAction.MOVE_TO_BREAKEVEN, allowed=True,
                    new_sl=entry_price, risk_reduction_factor=0.8,
                    reason=f"Profit {r_multiple:.1f}R >= 1R — move to breakeven",
                    regime=regime, confidence=confidence,
                )

            # ── Spread expansion (moderate) — tighten ──
            if spread_score > 0.6:
                new_sl = self._compute_tightened_sl(entry_price, side, atr, factor=0.7)
                return SLDefenseDecision(
                    action=SLAction.TIGHTEN_SL, allowed=True,
                    new_sl=new_sl, risk_reduction_factor=0.7,
                    reason=f"Spread expansion ({spread_score:.2f}) — tighten SL",
                    regime=regime, confidence=confidence,
                )

            # ── UNKNOWN regime — reduce risk ──
            if regime == "UNKNOWN":
                new_sl = self._compute_tightened_sl(entry_price, side, atr, factor=0.8)
                return SLDefenseDecision(
                    action=SLAction.TIGHTEN_SL, allowed=True,
                    new_sl=new_sl, risk_reduction_factor=0.5,
                    reason="UNKNOWN regime — fail-safe risk reduction",
                    regime=regime, confidence=confidence,
                )

            # ── Normal: hold ──
            return SLDefenseDecision(
                action=SLAction.HOLD, allowed=True,
                risk_reduction_factor=1.0,
                reason="No risk triggers — hold",
                regime=regime, confidence=confidence,
            )
        except Exception:
            return SLDefenseDecision(
                action=SLAction.TIGHTEN_SL, allowed=True,
                risk_reduction_factor=0.5,
                reason="SL defense exception — fail-safe tighten",
                regime=regime, confidence=confidence,
            )

    def _compute_tightened_sl(self, entry: float, side: str,
                               atr: float, factor: float) -> float:
        """Compute tightened SL at factor * ATR from entry."""
        if atr <= 0:
            return entry
        distance = atr * factor
        if side == "BUY":
            return entry - distance
        else:
            return entry + distance

    def _compute_trailing_sl(self, current: float, side: str,
                              atr: float, factor: float) -> float:
        """Compute trailing SL at factor * ATR behind current price."""
        if atr <= 0:
            return current
        distance = atr * factor
        if side == "BUY":
            return current - distance
        else:
            return current + distance
