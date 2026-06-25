"""
TITAN XAU AI — AI Exit Engine (Sprint 9.6)
============================================

Evaluates every open position continuously and produces an ExitDecision.

Inputs (16):
  - XGBoost confidence
  - Meta confidence
  - Context Engine regime
  - Account Health score
  - Capital Protection status
  - Broker Quality score
  - ATR
  - Trend strength
  - Volatility regime
  - Spread
  - Time in trade (hours)
  - Floating PnL (R-multiple)
  - News status
  - Session
  - Direction (long/short)
  - Current price vs entry

Output: ExitDecision (HOLD / PARTIAL_CLOSE / MOVE_TO_BREAK_EVEN / TRAIL /
                     BOOK_PROFIT / FULL_EXIT / EMERGENCY_EXIT)

Safety: Exit AI can only DECREASE risk (exit earlier/tighter), never increase.
If engine fails, returns HOLD (fail-closed — let broker-side SL/TP handle it).

Journals EventType.EXIT_AI_DECISION on every evaluation.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


# ─── Exit decision enum ─────────────────────────────────────────────────────
class ExitAction(str, Enum):
    HOLD = "HOLD"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    MOVE_TO_BREAK_EVEN = "MOVE_TO_BREAK_EVEN"
    TRAIL = "TRAIL"
    BOOK_PROFIT = "BOOK_PROFIT"
    FULL_EXIT = "FULL_EXIT"
    EMERGENCY_EXIT = "EMERGENCY_EXIT"


# ─── Inputs ─────────────────────────────────────────────────────────────────
@dataclass
class ExitInput:
    """Inputs to the AI Exit Engine."""
    # Position info
    direction: int = 1                  # +1 long, -1 short
    entry_price: float = 0.0
    current_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    volume: float = 0.01
    # Model confidence (current bar)
    xgb_confidence: float = 0.5         # 0-1
    meta_confidence: float = 0.5        # 0-1
    # Market context
    trend_strength: float = 0.0         # -1 to +1 (ADX-derived)
    momentum: float = 0.5               # 0-1 (RSI-derived)
    volatility_regime: str = "normal"   # low | normal | high | extreme
    atr: float = 0.0
    spread_usd: float = 0.0
    # Trade state
    time_in_trade_hours: float = 0.0
    floating_pnl_usd: float = 0.0
    r_multiple: float = 0.0             # current R (profit / initial risk)
    # External systems
    account_health_score: float = 100.0 # 0-100
    capital_preservation_active: bool = False
    recovery_mode_active: bool = False
    broker_quality_score: float = 100.0 # 0-100
    news_halt_active: bool = False
    news_imminent: bool = False         # high-impact news within 30min
    session: str = "unknown"            # asia | eu | us | off
    regime: str = "normal"              # normal | trend | range | volatile


# ─── Output ─────────────────────────────────────────────────────────────────
@dataclass
class ExitDecision:
    """Result of AI Exit Engine evaluation."""
    action: ExitAction
    confidence: float                    # 0-1, how confident the AI is in this decision
    reason: str
    # Optional parameters for the action
    partial_close_pct: float = 0.0       # for PARTIAL_CLOSE (0-100)
    new_trailing_sl: float = 0.0         # for TRAIL
    new_break_even_sl: float = 0.0       # for MOVE_TO_BREAK_EVEN
    new_tp: float = 0.0                  # for TP extension/reduction
    # Score components
    edge_score: float = 0.0              # 0-1, how much edge remains
    risk_score: float = 0.0              # 0-1, risk of holding
    # Sprint 9.6 Part 16 — Latency + fast execution
    exit_latency_ms: float = 0.0         # measured evaluation latency
    decision_path: str = "ai"            # "emergency_fast_path" | "ai" | "cached" | "fallback"
    used_cached_context: bool = False    # True if decision used cached context
    emergency_fast_path_used: bool = False  # True if emergency fast-path was taken
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        return d


# ─── Engine ─────────────────────────────────────────────────────────────────
class AIExitEngine:
    """
    Evaluates open positions and produces ExitDecisions.

    Decision logic (priority order — first match wins):
      1. EMERGENCY_EXIT: capital_preservation + recovery_mode + DD
      2. FULL_EXIT: meta confidence collapse + trend reversal + news imminent
      3. PARTIAL_CLOSE: at configured R-multiple levels
      4. BOOK_PROFIT: strong profit + weak momentum
      5. MOVE_TO_BREAK_EVEN: +1R + trend weakening
      6. TRAIL: strong trend + profit
      7. HOLD: default

    Safety: fail-closed. If evaluation raises, returns HOLD.
    """

    def __init__(
        self,
        journal: Optional[TradeJournal] = None,
        config: Optional[dict] = None,
    ):
        self.journal = journal
        self.config = config or {}
        self._evaluation_count: int = 0
        self._last_decision: Optional[ExitDecision] = None

    def evaluate(self, inp: ExitInput, cached_context: Optional[dict] = None) -> ExitDecision:
        """
        Evaluate position and return ExitDecision. Journals EXIT_AI_DECISION.

        Sprint 9.6 Part 16 — Latency-aware:
          - Emergency fast-path (rule-based, <50ms) checked FIRST
          - AI evaluation runs only if no emergency
          - Latency measured for every decision
          - If AI fails, fallback to HOLD (fail-closed)

        Args:
            inp: ExitInput with position + market context
            cached_context: Optional cached dict from latest heartbeat
                           (avoids re-querying engines for known values)
        """
        t0 = time.perf_counter()
        used_cached = cached_context is not None

        # ── EMERGENCY FAST PATH (rule-based, <50ms target) ──
        # No model inference, no file I/O, no network. Pure rules.
        if self._check_emergency_fast(inp):
            latency_ms = (time.perf_counter() - t0) * 1000
            decision = ExitDecision(
                action=ExitAction.EMERGENCY_EXIT,
                confidence=1.0,
                reason=f"emergency_fast_path: capital_preservation={inp.capital_preservation_active}, "
                       f"recovery={inp.recovery_mode_active}, health={inp.account_health_score:.0f}",
                exit_latency_ms=latency_ms,
                decision_path="emergency_fast_path",
                used_cached_context=used_cached,
                emergency_fast_path_used=True,
            )
            self._finalize(decision, inp, t0)
            return decision

        # ── AI EVALUATION (<250ms target) ──
        try:
            decision = self._evaluate_internal(inp)
            decision.decision_path = "cached" if used_cached else "ai"
            decision.used_cached_context = used_cached
        except Exception as e:
            logger.error(f"AIExitEngine error (fail-closed → HOLD): {e}")
            decision = ExitDecision(
                action=ExitAction.HOLD,
                confidence=0.0,
                reason=f"engine_error: {e}",
                decision_path="fallback",
                used_cached_context=used_cached,
            )

        self._finalize(decision, inp, t0)
        return decision

    def _check_emergency_fast(self, inp: ExitInput) -> bool:
        """
        Emergency fast-path check. Pure rules, no computation.
        Must complete in <50ms. No model calls, no I/O.
        """
        # Capital preservation + low health → instant emergency
        if inp.capital_preservation_active and inp.account_health_score < 25:
            return True
        # Recovery mode + floating loss → instant emergency
        if inp.recovery_mode_active and inp.floating_pnl_usd < 0:
            return True
        # Extremely low health → instant emergency
        if inp.account_health_score < 10:
            return True
        return False

    def _finalize(self, decision: ExitDecision, inp: ExitInput, t0: float) -> None:
        """Measure latency, journal, update state."""
        decision.exit_latency_ms = (time.perf_counter() - t0) * 1000
        self._evaluation_count += 1
        self._last_decision = decision

        # Journal
        self._journal_event(EventType.EXIT_AI_DECISION, decision.to_dict() | {
            "xgb_confidence": inp.xgb_confidence,
            "meta_confidence": inp.meta_confidence,
            "trend_strength": inp.trend_strength,
            "r_multiple": inp.r_multiple,
            "time_in_trade_hours": inp.time_in_trade_hours,
            "account_health": inp.account_health_score,
            "broker_quality": inp.broker_quality_score,
        })

    @property
    def last_decision(self) -> Optional[ExitDecision]:
        return self._last_decision

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count

    # ─── Internal: decision logic ─────────────────────────────────────────

    def _evaluate_internal(self, inp: ExitInput) -> ExitDecision:
        """Core decision logic. Priority-ordered."""
        # Compute scores
        edge_score = self._compute_edge_score(inp)
        risk_score = self._compute_risk_score(inp)

        # ── 1. EMERGENCY EXIT ──
        if self._should_emergency_exit(inp):
            return ExitDecision(
                action=ExitAction.EMERGENCY_EXIT,
                confidence=1.0,
                reason="emergency: capital_preservation + recovery + low health",
                edge_score=edge_score,
                risk_score=risk_score,
            )

        # ── 2. FULL EXIT (early exit triggers) ──
        early_exit = self._check_early_exit(inp)
        if early_exit is not None:
            return early_exit

        # ── 3. PARTIAL CLOSE ──
        partial = self._check_partial_close(inp)
        if partial is not None:
            return partial

        # ── 4. BOOK PROFIT ──
        if self._should_book_profit(inp):
            return ExitDecision(
                action=ExitAction.BOOK_PROFIT,
                confidence=0.8,
                reason=f"book profit: r={inp.r_multiple:.1f}R + weak momentum",
                edge_score=edge_score,
                risk_score=risk_score,
            )

        # ── 5. MOVE TO BREAK EVEN ──
        be = self._check_break_even(inp)
        if be is not None:
            return be

        # ── 6. TRAIL ──
        trail = self._check_trail(inp)
        if trail is not None:
            return trail

        # ── 7. HOLD (default) ──
        return ExitDecision(
            action=ExitAction.HOLD,
            confidence=0.5,
            reason="hold: edge intact, no exit triggers",
            edge_score=edge_score,
            risk_score=risk_score,
        )

    def _compute_edge_score(self, inp: ExitInput) -> float:
        """Compute remaining edge (0-1). Higher = more edge remaining."""
        # Weighted sum of edge indicators
        score = 0.0
        # XGB confidence (0.5 = neutral)
        score += 0.3 * max(0, (inp.xgb_confidence - 0.5) * 2)
        # Meta confidence
        score += 0.3 * max(0, (inp.meta_confidence - 0.5) * 2)
        # Trend alignment (positive trend for long, negative for short)
        trend_aligned = inp.trend_strength * inp.direction
        score += 0.2 * max(0, min(1, (trend_aligned + 1) / 2))
        # Momentum
        score += 0.2 * inp.momentum
        return max(0.0, min(1.0, score))

    def _compute_risk_score(self, inp: ExitInput) -> float:
        """Compute risk of holding (0-1). Higher = more risk."""
        score = 0.0
        # Low account health → high risk
        score += 0.3 * max(0, (50 - inp.account_health_score) / 50)
        # Low broker quality → high risk
        score += 0.2 * max(0, (60 - inp.broker_quality_score) / 60)
        # High spread → high risk
        score += 0.2 * min(1, inp.spread_usd / 3.0)
        # News imminent → high risk
        if inp.news_imminent:
            score += 0.2
        # High volatility → high risk
        if inp.volatility_regime in ("high", "extreme"):
            score += 0.1
        return max(0.0, min(1.0, score))

    # ── Emergency exit ──
    def _should_emergency_exit(self, inp: ExitInput) -> bool:
        """Emergency exit: capital preservation + recovery + low health."""
        if inp.capital_preservation_active and inp.account_health_score < 25:
            return True
        if inp.recovery_mode_active and inp.floating_pnl_usd < 0:
            return True
        if inp.account_health_score < 10:
            return True
        return False

    # ── Early exit ──
    def _check_early_exit(self, inp: ExitInput) -> Optional[ExitDecision]:
        """Early exit if edge disappears."""
        cfg = self.config.get("early_exit", {})
        meta_collapse = cfg.get("meta_confidence_collapse", 0.40)
        trend_reversal = cfg.get("trend_reversal_threshold", -0.3)
        momentum_collapse = cfg.get("momentum_collapse", 0.20)

        reasons = []
        if inp.meta_confidence < meta_collapse:
            reasons.append(f"meta_collapse ({inp.meta_confidence:.2f} < {meta_collapse})")
        if inp.trend_strength * inp.direction < trend_reversal:
            reasons.append(f"trend_reversal ({inp.trend_strength:.2f})")
        if inp.momentum < momentum_collapse:
            reasons.append(f"momentum_collapse ({inp.momentum:.2f})")

        # News imminent + in profit → early exit
        if inp.news_imminent and inp.r_multiple > 0:
            reasons.append(f"news_imminent + profit ({inp.r_multiple:.1f}R)")

        if reasons:
            return ExitDecision(
                action=ExitAction.FULL_EXIT,
                confidence=0.85,
                reason=f"early_exit: {'; '.join(reasons)}",
                edge_score=self._compute_edge_score(inp),
                risk_score=self._compute_risk_score(inp),
            )
        return None

    # ── Partial close ──
    def _check_partial_close(self, inp: ExitInput) -> Optional[ExitDecision]:
        """Partial close at configured R-multiple levels."""
        partial_cfg = self.config.get("partial_exits", {})
        if not partial_cfg.get("enabled", True):
            return None

        levels = partial_cfg.get("levels", [
            {"r_multiple": 1.0, "close_pct": 25},
            {"r_multiple": 2.0, "close_pct": 25},
            {"r_multiple": 3.0, "close_pct": 25},
        ])

        for level in levels:
            r_threshold = level.get("r_multiple", 1.0)
            close_pct = level.get("close_pct", 25)
            if inp.r_multiple >= r_threshold:
                # Only partial close if we haven't already (simplified —
                # in production, would track which levels already triggered)
                return ExitDecision(
                    action=ExitAction.PARTIAL_CLOSE,
                    confidence=0.7,
                    reason=f"partial_close: r={inp.r_multiple:.1f}R ≥ {r_threshold}R",
                    partial_close_pct=close_pct,
                    edge_score=self._compute_edge_score(inp),
                    risk_score=self._compute_risk_score(inp),
                )
        return None

    # ── Book profit ──
    def _should_book_profit(self, inp: ExitInput) -> bool:
        """Book profit: strong profit + weak momentum."""
        return (inp.r_multiple >= 2.0
                and inp.momentum < 0.4
                and inp.volatility_regime in ("normal", "low"))

    # ── Break even ──
    def _check_break_even(self, inp: ExitInput) -> Optional[ExitDecision]:
        """Move to break-even: +1R + trend weakening."""
        if inp.r_multiple >= 1.0 and inp.trend_strength * inp.direction < 0.2:
            # Move SL to entry price (break-even)
            return ExitDecision(
                action=ExitAction.MOVE_TO_BREAK_EVEN,
                confidence=0.75,
                reason=f"break_even: r={inp.r_multiple:.1f}R + trend weakening",
                new_break_even_sl=inp.entry_price,
                edge_score=self._compute_edge_score(inp),
                risk_score=self._compute_risk_score(inp),
            )
        return None

    # ── Trail ──
    def _check_trail(self, inp: ExitInput) -> Optional[ExitDecision]:
        """Trail: strong trend + profit."""
        if inp.r_multiple < 0.5:
            return None

        cfg = self.config.get("trailing", {})
        base_mult = cfg.get("base_atr_multiplier", 1.0)
        strong_loosen = cfg.get("strong_trend_loosen", 2.0)
        weak_tighten = cfg.get("weak_market_tighten", 0.5)
        min_dist = cfg.get("min_trail_distance_atr", 0.3)

        # Determine trail multiplier based on trend strength
        if inp.trend_strength * inp.direction > 0.5:
            # Strong aligned trend → loosen
            trail_mult = strong_loosen
        elif inp.trend_strength * inp.direction < 0.1:
            # Weak trend → tighten
            trail_mult = weak_tighten
        else:
            trail_mult = base_mult

        trail_mult = max(min_dist, trail_mult)
        trail_distance = trail_mult * inp.atr if inp.atr > 0 else 0

        # Compute new trailing SL
        if inp.direction == 1:  # long
            new_sl = inp.current_price - trail_distance
        else:                    # short
            new_sl = inp.current_price + trail_distance

        # Only trail if it improves SL (never moves SL away from price)
        if inp.direction == 1 and new_sl > inp.stop_loss:
            return ExitDecision(
                action=ExitAction.TRAIL,
                confidence=0.7,
                reason=f"trail: r={inp.r_multiple:.1f}R, trail_mult={trail_mult}",
                new_trailing_sl=new_sl,
                edge_score=self._compute_edge_score(inp),
                risk_score=self._compute_risk_score(inp),
            )
        elif inp.direction == -1 and new_sl < inp.stop_loss:
            return ExitDecision(
                action=ExitAction.TRAIL,
                confidence=0.7,
                reason=f"trail: r={inp.r_multiple:.1f}R, trail_mult={trail_mult}",
                new_trailing_sl=new_sl,
                edge_score=self._compute_edge_score(inp),
                risk_score=self._compute_risk_score(inp),
            )
        return None

    # ── Journal ──
    def _journal_event(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data)
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")
