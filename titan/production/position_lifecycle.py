"""
TITAN XAU AI — Position Lifecycle Engine (Sprint 9.9.3.31)
============================================================

Evaluates open position state and produces PositionLifecycleStatus.
Connected to ExitIntentBridge which feeds SL Defense + Profit Capture +
Exit Decision Coordinator.

Never imports MetaTrader5. Never sends orders.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class PositionState(str, Enum):
    NEW = "NEW"
    OPEN = "OPEN"
    IN_PROFIT = "IN_PROFIT"
    AT_BREAKEVEN = "AT_BREAKEVEN"
    PARTIALLY_CLOSED = "PARTIALLY_CLOSED"
    TRAILING = "TRAILING"
    PROTECTED = "PROTECTED"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED = "CLOSED"
    STUCK = "STUCK"
    UNKNOWN = "UNKNOWN"


@dataclass
class PositionSnapshot:
    """Snapshot of an open position at a point in time."""
    symbol: str = "XAUUSD"
    side: str = "BUY"              # BUY / SELL
    entry_price: float = 0.0
    current_price: float = 0.0
    volume: float = 0.01
    initial_sl: float = 0.0
    current_sl: float = 0.0
    current_tp: float = 0.0
    unrealized_pnl: float = 0.0
    pnl_r: float = 0.0            # profit/loss in R multiples
    age_seconds: float = 0.0
    spread_points: float = 0.0
    atr: float = 0.0
    regime: str = "UNKNOWN"
    model_confidence: float = 0.0
    meta_confidence: float = 0.0
    broker: str = "UNKNOWN"
    ticket: int = 0
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


@dataclass
class PositionLifecycleStatus:
    """Result of lifecycle evaluation."""
    state: PositionState = PositionState.UNKNOWN
    safe_to_hold: bool = True
    risk_level: str = "LOW"        # LOW / MEDIUM / HIGH / CRITICAL
    pnl_r: float = 0.0
    protection_level: str = "NONE" # NONE / BREAKEVEN / TRAILING / PROTECTED
    needs_exit_review: bool = True
    reason: str = ""
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


# Stale position threshold (seconds)
STALE_POSITION_THRESHOLD = 7200  # 2 hours


class PositionLifecycleEngine:
    """Evaluates position lifecycle state from snapshots.

    Never raises — returns UNKNOWN with safe defaults on any error.
    """

    def evaluate(self, snapshot: PositionSnapshot) -> PositionLifecycleStatus:
        """Evaluate a position snapshot and return lifecycle status."""
        try:
            # Validate essential fields
            if snapshot.entry_price <= 0 or snapshot.current_price <= 0:
                return self._fail_safe("Missing entry/current price")

            if snapshot.ticket == 0:
                return self._fail_safe("Missing ticket")

            pnl_r = snapshot.pnl_r
            age = snapshot.age_seconds

            # ── Stuck position detection ──
            if age > STALE_POSITION_THRESHOLD:
                return PositionLifecycleStatus(
                    state=PositionState.STUCK,
                    safe_to_hold=False,
                    risk_level="CRITICAL",
                    pnl_r=pnl_r,
                    protection_level="NONE",
                    needs_exit_review=True,
                    reason=f"Position age {age:.0f}s > {STALE_POSITION_THRESHOLD}s — stuck",
                )

            # ── Exit pending ──
            # (Set externally when an exit order was sent but not yet confirmed)

            # ── Partially closed ──
            # (Detected by volume reduction — caller would need to compare
            #  initial vs current volume. For now, this is a placeholder.)

            # ── AT_BREAKEVEN ──
            if snapshot.current_sl > 0 and self._is_at_breakeven(snapshot):
                return PositionLifecycleStatus(
                    state=PositionState.AT_BREAKEVEN,
                    safe_to_hold=True,
                    risk_level="LOW",
                    pnl_r=pnl_r,
                    protection_level="BREAKEVEN",
                    needs_exit_review=True,
                    reason=f"SL at breakeven, pnl={pnl_r:.1f}R",
                )

            # ── TRAILING ──
            if snapshot.current_sl > 0 and self._is_trailing(snapshot):
                return PositionLifecycleStatus(
                    state=PositionState.TRAILING,
                    safe_to_hold=True,
                    risk_level="LOW",
                    pnl_r=pnl_r,
                    protection_level="TRAILING",
                    needs_exit_review=True,
                    reason=f"Trailing SL active, pnl={pnl_r:.1f}R",
                )

            # ── IN_PROFIT ──
            if pnl_r > 0:
                protection = "NONE"
                if snapshot.current_sl > 0 and snapshot.current_sl != snapshot.initial_sl:
                    protection = "PROTECTED"
                return PositionLifecycleStatus(
                    state=PositionState.IN_PROFIT,
                    safe_to_hold=True,
                    risk_level="LOW",
                    pnl_r=pnl_r,
                    protection_level=protection,
                    needs_exit_review=True,
                    reason=f"In profit {pnl_r:.1f}R",
                )

            # ── PROTECTED (SL moved from initial but not at BE) ──
            if snapshot.current_sl > 0 and snapshot.current_sl != snapshot.initial_sl:
                return PositionLifecycleStatus(
                    state=PositionState.PROTECTED,
                    safe_to_hold=True,
                    risk_level="MEDIUM",
                    pnl_r=pnl_r,
                    protection_level="PROTECTED",
                    needs_exit_review=True,
                    reason="SL modified from initial — protected",
                )

            # ── NEW (very young position) ──
            if age < 60:
                return PositionLifecycleStatus(
                    state=PositionState.NEW,
                    safe_to_hold=True,
                    risk_level="MEDIUM",
                    pnl_r=pnl_r,
                    protection_level="NONE",
                    needs_exit_review=True,
                    reason=f"New position, age={age:.0f}s",
                )

            # ── OPEN (normal, no special state) ──
            risk = "MEDIUM" if pnl_r < -0.5 else "LOW"
            return PositionLifecycleStatus(
                state=PositionState.OPEN,
                safe_to_hold=True,
                risk_level=risk,
                pnl_r=pnl_r,
                protection_level="NONE",
                needs_exit_review=True,
                reason=f"Open position, pnl={pnl_r:.1f}R",
            )

        except Exception as e:
            return self._fail_safe(f"Lifecycle exception: {e}")

    def _is_at_breakeven(self, s: PositionSnapshot) -> bool:
        """Check if SL is at or very near entry price."""
        if s.entry_price <= 0 or s.current_sl <= 0:
            return False
        tolerance = max(s.atr * 0.1, 0.5) if s.atr > 0 else 0.5
        return abs(s.current_sl - s.entry_price) <= tolerance

    def _is_trailing(self, s: PositionSnapshot) -> bool:
        """Check if SL has been moved above entry (BUY) or below entry (SELL)."""
        if s.current_sl <= 0 or s.entry_price <= 0:
            return False
        if s.side == "BUY":
            return s.current_sl > s.entry_price
        else:
            return s.current_sl < s.entry_price

    def _fail_safe(self, reason: str) -> PositionLifecycleStatus:
        return PositionLifecycleStatus(
            state=PositionState.UNKNOWN,
            safe_to_hold=False,
            risk_level="HIGH",
            needs_exit_review=True,
            reason=reason,
        )
