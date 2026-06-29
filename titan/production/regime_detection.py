"""
TITAN XAU AI — Production Regime Detection Foundation (Sprint 9.9.3.28)
=======================================================================

Wraps/extends the existing titan/regime/engine.py RegimeEngine with:
  - Extended regime types (TREND_UP, TREND_DOWN, RANGE, HIGH_VOLATILITY,
    LOW_VOLATILITY, NEWS_SHOCK, SPREAD_EXPANSION, LIQUIDITY_VACUUM,
    SESSION_ASIA, SESSION_LONDON, SESSION_NEW_YORK, GOLD_IMPULSE, UNKNOWN)
  - RegimeStatus object with risk_multiplier, allow_new_trade, block_reason
  - Decision rules that can ONLY reduce risk or block (never increase)
  - Fail-safe: failed detection → UNKNOWN with safe risk reduction
  - Hook points/TODOs for ContextEngine, TradeLoop, DynamicRiskEngine,
    MetaCalibration, AI Exit, BrokerCompatibilityMatrix, dashboard

This is NON-BLOCKING foundation — production trading behavior is NOT
changed yet. Regime can only reduce risk or block unsafe trades.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class RegimeType(str, Enum):
    """Extended regime types for production decision context."""
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    NEWS_SHOCK = "NEWS_SHOCK"
    SPREAD_EXPANSION = "SPREAD_EXPANSION"
    LIQUIDITY_VACUUM = "LIQUIDITY_VACUUM"
    SESSION_ASIA = "SESSION_ASIA"
    SESSION_LONDON = "SESSION_LONDON"
    SESSION_NEW_YORK = "SESSION_NEW_YORK"
    GOLD_IMPULSE = "GOLD_IMPULSE"
    UNKNOWN = "UNKNOWN"


# Session by UTC hour ranges (approximate)
_SESSION_RANGES = {
    RegimeType.SESSION_ASIA: (0, 8),        # 00:00–08:00 UTC
    RegimeType.SESSION_LONDON: (7, 16),     # 07:00–16:00 UTC
    RegimeType.SESSION_NEW_YORK: (12, 21),  # 12:00–21:00 UTC
}


@dataclass
class RegimeStatus:
    """Production regime status with decision context.

    risk_multiplier is ALWAYS <= 1.0 (regime can only reduce risk, never increase).
    """
    primary_regime: RegimeType = RegimeType.UNKNOWN
    secondary_regimes: list[RegimeType] = field(default_factory=list)
    confidence: float = 0.0              # 0.0–1.0
    volatility_score: float = 0.0        # 0.0–1.0 (higher = more volatile)
    trend_score: float = 0.0             # -1.0 (down) to +1.0 (up)
    range_score: float = 0.0             # 0.0–1.0 (higher = more rangy)
    spread_score: float = 0.0            # 0.0–1.0 (higher = wider spread)
    liquidity_score: float = 0.0         # 0.0–1.0 (higher = more liquid)
    session: Optional[RegimeType] = None
    risk_multiplier: float = 1.0         # ALWAYS <= 1.0
    allow_new_trade: bool = True
    block_reason: Optional[str] = None
    timestamp_utc: str = ""

    def __post_init__(self):
        # Enforce risk_multiplier <= 1.0
        if self.risk_multiplier > 1.0:
            self.risk_multiplier = 1.0
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


# ─── Decision rules ──────────────────────────────────────────────────────────

_REGIME_DECISIONS = {
    RegimeType.TREND_UP: {
        "risk_multiplier": 1.0,
        "allow_new_trade": True,
        "block_reason": None,
        "note": "Trend up — normal risk allowed",
    },
    RegimeType.TREND_DOWN: {
        "risk_multiplier": 1.0,
        "allow_new_trade": True,
        "block_reason": None,
        "note": "Trend down — normal risk allowed",
    },
    RegimeType.RANGE: {
        "risk_multiplier": 0.7,
        "allow_new_trade": True,
        "block_reason": None,
        "note": "Range — reduce confidence, require stronger meta approval",
    },
    RegimeType.HIGH_VOLATILITY: {
        "risk_multiplier": 0.5,
        "allow_new_trade": True,
        "block_reason": None,
        "note": "High volatility — reduce risk, tighter execution checks",
    },
    RegimeType.LOW_VOLATILITY: {
        "risk_multiplier": 0.8,
        "allow_new_trade": True,
        "block_reason": None,
        "note": "Low volatility — reduce trade frequency",
    },
    RegimeType.NEWS_SHOCK: {
        "risk_multiplier": 0.0,
        "allow_new_trade": False,
        "block_reason": "News shock detected — new trades blocked",
        "note": "News shock — block new trade",
    },
    RegimeType.SPREAD_EXPANSION: {
        "risk_multiplier": 0.3,
        "allow_new_trade": False,
        "block_reason": "Spread expansion — new trades blocked, reduce risk",
        "note": "Spread expansion — block or reduce risk",
    },
    RegimeType.LIQUIDITY_VACUUM: {
        "risk_multiplier": 0.0,
        "allow_new_trade": False,
        "block_reason": "Liquidity vacuum — new trades blocked",
        "note": "Liquidity vacuum — block new trade",
    },
    RegimeType.GOLD_IMPULSE: {
        "risk_multiplier": 0.6,
        "allow_new_trade": True,
        "block_reason": None,
        "note": "Gold impulse — allow only if confidence is strong",
    },
    RegimeType.SESSION_ASIA: {
        "risk_multiplier": 0.8,
        "allow_new_trade": True,
        "block_reason": None,
        "note": "Asia session — slightly reduced risk",
    },
    RegimeType.SESSION_LONDON: {
        "risk_multiplier": 1.0,
        "allow_new_trade": True,
        "block_reason": None,
        "note": "London session — normal risk",
    },
    RegimeType.SESSION_NEW_YORK: {
        "risk_multiplier": 1.0,
        "allow_new_trade": True,
        "block_reason": None,
        "note": "New York session — normal risk",
    },
    RegimeType.UNKNOWN: {
        "risk_multiplier": 0.5,
        "allow_new_trade": True,
        "block_reason": None,
        "note": "Unknown regime — fail-safe risk reduction, do not increase risk",
    },
}


def _get_session() -> Optional[RegimeType]:
    """Detect current trading session by UTC hour."""
    hour = datetime.now(timezone.utc).hour
    for session_type, (start, end) in _SESSION_RANGES.items():
        if start <= hour < end:
            return session_type
    return None


def detect_regime(
    trend_score: float = 0.0,
    volatility_score: float = 0.0,
    range_score: float = 0.0,
    spread_score: float = 0.0,
    liquidity_score: float = 1.0,
    confidence: float = 0.0,
    detect_session: bool = True,
) -> RegimeStatus:
    """Detect regime from scores and return a RegimeStatus.

    All scores are 0.0–1.0 (trend_score is -1.0 to +1.0).
    This function NEVER raises — on any error, returns UNKNOWN safely.

    The risk_multiplier is ALWAYS <= 1.0. Regime can only reduce risk.
    """
    try:
        # Determine primary regime
        primary = RegimeType.UNKNOWN
        secondary = []

        # Check blocking conditions first (highest priority)
        if spread_score > 0.8:
            primary = RegimeType.SPREAD_EXPANSION
        elif liquidity_score < 0.2:
            primary = RegimeType.LIQUIDITY_VACUUM
        elif volatility_score > 0.85:
            primary = RegimeType.NEWS_SHOCK
        elif volatility_score > 0.7:
            primary = RegimeType.HIGH_VOLATILITY
            if range_score > 0.6:
                secondary.append(RegimeType.RANGE)
        elif volatility_score < 0.2:
            primary = RegimeType.LOW_VOLATILITY
        elif range_score > 0.6:
            primary = RegimeType.RANGE
        elif abs(trend_score) > 0.5 and volatility_score > 0.5:
            # Gold impulse: strong trend + elevated volatility (but not extreme)
            primary = RegimeType.GOLD_IMPULSE
        elif trend_score > 0.3:
            primary = RegimeType.TREND_UP
        elif trend_score < -0.3:
            primary = RegimeType.TREND_DOWN

        # Add session as secondary
        session = None
        if detect_session:
            session = _get_session()
            if session and session != primary:
                secondary.append(session)

        # Get decision for primary regime
        decision = _REGIME_DECISIONS.get(primary, _REGIME_DECISIONS[RegimeType.UNKNOWN])
        risk_mult = decision["risk_multiplier"]

        # Apply secondary regime reductions (take the minimum)
        for sec in secondary:
            sec_decision = _REGIME_DECISIONS.get(sec, {})
            sec_risk = sec_decision.get("risk_multiplier", 1.0)
            if sec_risk < risk_mult:
                risk_mult = sec_risk
            if not sec_decision.get("allow_new_trade", True):
                decision = sec_decision  # blocking secondary overrides

        # Enforce risk_multiplier <= 1.0
        risk_mult = min(risk_mult, 1.0)

        return RegimeStatus(
            primary_regime=primary,
            secondary_regimes=secondary,
            confidence=confidence,
            volatility_score=volatility_score,
            trend_score=trend_score,
            range_score=range_score,
            spread_score=spread_score,
            liquidity_score=liquidity_score,
            session=session,
            risk_multiplier=risk_mult,
            allow_new_trade=decision["allow_new_trade"],
            block_reason=decision.get("block_reason"),
        )
    except Exception:
        # Fail-safe: return UNKNOWN with safe risk reduction
        return RegimeStatus(
            primary_regime=RegimeType.UNKNOWN,
            risk_multiplier=0.5,
            allow_new_trade=True,
            block_reason=None,
        )


def get_regime_decision(regime: RegimeType) -> dict:
    """Get the decision rules for a specific regime type."""
    return dict(_REGIME_DECISIONS.get(regime, _REGIME_DECISIONS[RegimeType.UNKNOWN]))


def get_all_regime_decisions() -> dict:
    """Return all regime decision rules."""
    return {r.value: dict(d) for r, d in _REGIME_DECISIONS.items()}


# ─── Integration hook points (TODOs for future wiring) ────────────────────────

# TODO Sprint 9.9.4+: Wire into ContextEngine
#   context_engine.register_regime_provider(detect_regime)

# TODO Sprint 9.9.4+: Wire into TradeLoop
#   trade_loop.add_pre_trade_check(lambda: regime_status.allow_new_trade)

# TODO Sprint 9.9.4+: Wire into DynamicRiskEngine
#   dynamic_risk.set_regime_multiplier(regime_status.risk_multiplier)

# TODO Sprint 9.9.4+: Wire into MetaCalibration
#   meta_calibration.adjust_confidence_threshold(regime_status.primary_regime)

# TODO Sprint 9.9.4+: Wire into AI Exit Intelligence
#   ai_exit.set_regime_context(regime_status)

# TODO Sprint 9.9.4+: Wire into BrokerCompatibilityMatrix
#   broker_matrix.update_regime(regime_status.primary_regime)

# TODO Sprint 9.9.4+: Wire into future dashboard
#   dashboard.set_regime_display(regime_status)
