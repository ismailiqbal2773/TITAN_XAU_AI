"""
TITAN XAU AI — Sprint 9.9.3.2 Stress Loss Mitigation Governance Engine
=======================================================================

Institutional-grade decision layer that sits BEFORE any trade is sent
(in dry-run, virtual-lifecycle, or future live paths) and DURING active
trade management (every heartbeat).

It does NOT replace the strategy. It does NOT call mt5.order_send.
It does NOT change production live path. It is a fail-closed gate that
can only BLOCK trades, REDUCE risk, or EXIT earlier — never increase.

Safety invariants:
  - Only DECREASES risk (never increases lot, never adds positions)
  - No martingale, no grid, no averaging, no lot escalation
  - Fail-closed: missing/invalid inputs → NO_TRADE
  - Every decision returns an explainable audit trail
  - Configurable per account profile:
      RETAIL_SAFE
      PROP_FIRM_STRICT
      INSTITUTIONAL_CAPITAL_PROTECTION  (strictest)
  - Institutional mode prefers fewer/higher-quality trades, lower DD,
    higher consistency, explainable risk decisions, capital preservation first.

Inputs (GovernanceInput):
  - regime_label, regime_confidence
  - meta_confidence (alpha strength)
  - atr_percentile, volatility_state (LOW/NORMAL/HIGH/EXTREME)
  - spread_usd, slippage_pips
  - session (ASIA/LONDON/NY/OVERLAP/OFF), liquidity (GOOD/NORMAL/POOR)
  - account_health (0-100)
  - equity_protection_active, capital_preservation_active
  - regime_flip_probability (0-1)
  - current_r_multiple (for open-trade management)
  - mfe, mae (for open-trade management)
  - open_trade_side (BUY/SELL/None)
  - setup_id, rolling_setup_winrate (0-1, optional)
  - broker_quality (0-100)
  - daily_dd_pct, daily_dd_threshold_pct (for early protection)
  - candles_in_trade (for follow-through timeout)
  - confirmation_present (for ambiguous-candle override)
  - ambiguous_candle (bool)

Outputs (GovernanceDecision):
  - allow_trade: bool
  - risk_multiplier: float (0.0 to 1.0)
  - decision_label: ALLOW / REDUCE_RISK / NO_TRADE / EXIT
  - exit_action: HOLD / MOVE_BE / PARTIAL_CLOSE / TIGHT_TRAIL / CLOSE / REDUCE
  - entry_reason / block_reason
  - exit_reason
  - audit: dict (full explainability)
  - account_profile: str
  - governance_score: float (0-100)
  - institutional_approval: bool
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


# ─── Account profiles ─────────────────────────────────────────────────────────

class AccountProfile(str, Enum):
    RETAIL_SAFE = "RETAIL_SAFE"
    PROP_FIRM_STRICT = "PROP_FIRM_STRICT"
    INSTITUTIONAL_CAPITAL_PROTECTION = "INSTITUTIONAL_CAPITAL_PROTECTION"


# Per-profile thresholds. INSTITUTIONAL is always at least as strict as
# PROP_FIRM_STRICT, which is always at least as strict as RETAIL_SAFE.
PROFILE_THRESHOLDS: Dict[str, Dict[str, Any]] = {
    AccountProfile.RETAIL_SAFE.value: {
        "min_meta_confidence": 0.65,
        "min_meta_confidence_block": 0.55,  # Sprint 9.9.3.3: hard block below
        "min_meta_confidence_throttle": 0.65,  # throttle zone
        "min_regime_confidence": 0.55,
        "max_spread_usd": 1.00,
        "max_spread_usd_block": 1.50,  # Sprint 9.9.3.3: hard block
        "max_atr_percentile_block": 95,         # block above
        "max_atr_percentile_throttle": 85,      # 3-tier: throttle zone
        "max_atr_percentile_warn": 85,          # legacy alias = throttle
        "meta_required_in_throttle_vol": 0.70,
        "meta_required_in_warn_vol": 0.70,      # legacy alias
        "risk_multiplier_in_throttle_vol": 0.75,
        "risk_multiplier_in_warn_vol": 0.75,    # legacy alias
        "max_regime_flip_prob": 0.65,
        "max_regime_flip_prob_block": 0.80,  # Sprint 9.9.3.3: hard block
        "max_regime_flip_prob_throttle": 0.65,  # 3-tier
        "min_account_health": 50,
        "min_account_health_block": 30,  # Sprint 9.9.3.3: hard block
        "min_broker_quality": 60,
        "min_broker_quality_block": 40,  # Sprint 9.9.3.3: hard block
        "min_rolling_setup_winrate": 0.30,
        "be_at_r": 0.5,
        "partial_25_at_r": 0.5,
        "partial_50_at_r": 1.0,
        "tight_trail_at_r": 1.5,
        "early_close_no_followthrough_r": 0.3,
        "early_close_no_followthrough_candles": 5,
        "early_invalidation_r": -0.3,
        "max_daily_dd_pct_of_threshold": 0.80,
        # Sprint 9.9.3.3: expected edge buffer (in $) — block if expected_edge < cost_buffer
        "cost_buffer_usd": 0.50,
    },
    AccountProfile.PROP_FIRM_STRICT.value: {
        "min_meta_confidence": 0.70,
        "min_meta_confidence_block": 0.65,  # Sprint 9.9.3.3: hard block below
        "min_meta_confidence_throttle": 0.70,  # throttle zone
        "min_regime_confidence": 0.60,
        "max_spread_usd": 0.50,
        "max_spread_usd_block": 0.80,  # Sprint 9.9.3.3: hard block
        "max_atr_percentile_block": 95,         # 3-tier: hard block above 95
        "max_atr_percentile_throttle": 90,      # 3-tier: throttle 90-95 (require meta>=0.80, mult<=0.25)
        "max_atr_percentile_warn": 80,          # 3-tier: warn 80-90 (require meta>=0.75, mult<=0.50)
        "meta_required_in_throttle_vol": 0.80,
        "meta_required_in_warn_vol": 0.75,
        "risk_multiplier_in_throttle_vol": 0.25,
        "risk_multiplier_in_warn_vol": 0.50,
        "max_regime_flip_prob": 0.60,
        "max_regime_flip_prob_block": 0.75,  # Sprint 9.9.3.3: hard block
        "max_regime_flip_prob_throttle": 0.60,  # 3-tier
        "min_account_health": 60,
        "min_account_health_block": 40,  # Sprint 9.9.3.3: hard block
        "min_broker_quality": 70,
        "min_broker_quality_block": 50,  # Sprint 9.9.3.3: hard block
        "min_rolling_setup_winrate": 0.35,
        "be_at_r": 0.5,
        "partial_25_at_r": 0.5,
        "partial_50_at_r": 1.0,
        "tight_trail_at_r": 1.5,
        "early_close_no_followthrough_r": 0.3,
        "early_close_no_followthrough_candles": 4,
        "early_invalidation_r": -0.3,
        "max_daily_dd_pct_of_threshold": 0.60,
        # Sprint 9.9.3.3: expected edge buffer
        "cost_buffer_usd": 0.50,
    },
    AccountProfile.INSTITUTIONAL_CAPITAL_PROTECTION.value: {
        "min_meta_confidence": 0.75,
        "min_meta_confidence_block": 0.70,  # Sprint 9.9.3.3: hard block below
        "min_meta_confidence_throttle": 0.75,  # throttle zone
        "min_regime_confidence": 0.70,
        "max_spread_usd": 0.40,
        "max_spread_usd_block": 0.60,  # Sprint 9.9.3.3: hard block
        "max_atr_percentile_block": 95,
        "max_atr_percentile_throttle": 90,
        "max_atr_percentile_warn": 75,
        "meta_required_in_throttle_vol": 0.82,
        "meta_required_in_warn_vol": 0.78,
        "risk_multiplier_in_throttle_vol": 0.25,
        "risk_multiplier_in_warn_vol": 0.50,
        "max_regime_flip_prob": 0.55,
        "max_regime_flip_prob_block": 0.70,  # Sprint 9.9.3.3: hard block
        "max_regime_flip_prob_throttle": 0.55,  # 3-tier
        "min_account_health": 75,
        "min_account_health_block": 60,  # Sprint 9.9.3.3: hard block
        "min_broker_quality": 80,
        "min_broker_quality_block": 60,  # Sprint 9.9.3.3: hard block
        "min_rolling_setup_winrate": 0.40,
        "be_at_r": 0.5,
        "partial_25_at_r": 0.5,
        "partial_50_at_r": 1.0,
        "tight_trail_at_r": 1.5,
        "early_close_no_followthrough_r": 0.3,
        "early_close_no_followthrough_candles": 3,
        "early_invalidation_r": -0.25,
        "max_daily_dd_pct_of_threshold": 0.50,
        # Sprint 9.9.3.3: expected edge buffer (tighter for institutional)
        "cost_buffer_usd": 0.60,
    },
}


# ─── Exit actions ─────────────────────────────────────────────────────────────

class ExitAction(str, Enum):
    HOLD = "HOLD"
    MOVE_BE = "MOVE_BE"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    TIGHT_TRAIL = "TIGHT_TRAIL"
    CLOSE = "CLOSE"
    REDUCE = "REDUCE"


class DecisionLabel(str, Enum):
    ALLOW = "ALLOW"
    REDUCE_RISK = "REDUCE_RISK"
    NO_TRADE = "NO_TRADE"
    EXIT = "EXIT"


# ─── Inputs / Outputs ─────────────────────────────────────────────────────────

@dataclass
class GovernanceInput:
    # Regime
    regime_label: str = "UNKNOWN"
    regime_confidence: float = 0.0
    regime_flip_probability: float = 0.0

    # Alpha
    meta_confidence: float = 0.0

    # Volatility
    atr_percentile: float = 50.0
    volatility_state: str = "NORMAL"  # LOW/NORMAL/HIGH/EXTREME

    # Costs
    spread_usd: float = 0.30
    slippage_pips: float = 2.0

    # Session / liquidity
    session: str = "OFF"  # ASIA/LONDON/NY/OVERLAP/OFF
    liquidity: str = "NORMAL"  # GOOD/NORMAL/POOR

    # Account state
    account_health: float = 100.0
    equity_protection_active: bool = False
    capital_preservation_active: bool = False
    broker_quality: float = 80.0

    # Daily DD
    daily_dd_pct: float = 0.0
    daily_dd_threshold_pct: float = 3.0

    # Open trade (None if no open trade)
    open_trade_side: Optional[str] = None  # BUY/SELL/None
    current_r_multiple: float = 0.0
    mfe: float = 0.0
    mae: float = 0.0
    candles_in_trade: int = 0

    # Setup tracking
    setup_id: str = "default"
    rolling_setup_winrate: Optional[float] = None
    confirmation_present: bool = False
    ambiguous_candle: bool = False

    # Sprint 9.9.3.3: Expected edge (estimated $ PnL per trade based on signal strength)
    # Used to differentiate "weak alpha with negative expected edge" (block) from
    # "weak alpha but positive expected edge after costs" (allow with throttle).
    expected_edge_usd: float = 0.0

    # Profile
    account_profile: str = AccountProfile.PROP_FIRM_STRICT.value


@dataclass
class GovernanceDecision:
    allow_trade: bool
    risk_multiplier: float
    decision_label: str
    exit_action: str
    entry_reason: str
    block_reason: str
    exit_reason: str
    governance_score: float
    institutional_approval: bool
    account_profile: str
    audit: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ─── Score weights ────────────────────────────────────────────────────────────

SCORE_WEIGHTS = {
    "regime_validity": 0.15,
    "alpha_strength": 0.20,
    "volatility_safety": 0.15,
    "cost_safety": 0.10,
    "session_liquidity_safety": 0.10,
    "account_health": 0.10,
    "protection_state": 0.10,
    "regime_transition_risk": 0.10,
}


# ─── Governance engine ────────────────────────────────────────────────────────

class StressLossGovernanceEngine:
    """
    Decision layer that returns a GovernanceDecision for a given
    GovernanceInput. Stateless between calls — all state must be
    passed in via GovernanceInput.

    Usage:
        engine = StressLossGovernanceEngine()
        decision = engine.evaluate_entry(GovernanceInput(...))
        if not decision.allow_trade:
            # skip trade
        else:
            # use decision.risk_multiplier

        # During trade:
        mgmt = engine.evaluate_management(GovernanceInput(...))
        if mgmt.exit_action != "HOLD":
            # apply exit_action
    """

    def __init__(self, account_profile: str = AccountProfile.PROP_FIRM_STRICT.value):
        if account_profile not in PROFILE_THRESHOLDS:
            raise ValueError(
                f"Unknown account profile: {account_profile}. "
                f"Valid: {list(PROFILE_THRESHOLDS.keys())}"
            )
        self.account_profile = account_profile
        self.thresholds = PROFILE_THRESHOLDS[account_profile]

    # ─── Public API ───────────────────────────────────────────────────────────

    def evaluate_entry(self, inp: GovernanceInput) -> GovernanceDecision:
        """Evaluate whether a new trade should be allowed."""
        # Fail-closed on invalid inputs
        fail_closed = self._fail_closed_check(inp)
        if fail_closed is not None:
            return fail_closed

        audit: Dict[str, Any] = {
            "phase": "entry",
            "profile": self.account_profile,
            "checks": [],
            "score_components": {},
        }

        # Score components (each 0-100)
        score_components = self._compute_score_components(inp, audit)
        governance_score = self._weighted_score(score_components)
        audit["score_components"] = score_components
        audit["governance_score"] = round(governance_score, 2)

        # Block reasons (collected, fail-closed: any block → NO_TRADE)
        block_reasons: List[str] = []

        # A. HIGH_VOLATILITY entry blocks
        self._check_high_volatility_entry(inp, block_reasons, audit)
        # B. AMBIGUOUS_CANDLE entry blocks
        self._check_ambiguous_candle_entry(inp, block_reasons, audit)
        # C. BUY_SL / SELL_SL baseline entry blocks
        self._check_baseline_entry(inp, block_reasons, audit)
        # D. EQUITY_PROTECTION entry blocks
        self._check_equity_protection_entry(inp, block_reasons, audit)
        # E. CAPITAL_PRESERVATION entry blocks
        self._check_capital_preservation_entry(inp, block_reasons, audit)
        # F. REGIME_FLIP entry blocks
        self._check_regime_flip_entry(inp, block_reasons, audit)
        # Global account health / broker quality / setup winrate
        self._check_account_state_entry(inp, block_reasons, audit)
        # Daily DD early-disable
        self._check_daily_dd_entry(inp, block_reasons, audit)

        # Determine risk multiplier
        risk_multiplier = self._compute_risk_multiplier(inp, audit)

        # Decide
        if block_reasons:
            allow = False
            decision_label = DecisionLabel.NO_TRADE.value
            entry_reason = ""
            block_reason = "; ".join(block_reasons)
            risk_multiplier = 0.0
        elif risk_multiplier < 1.0:
            allow = True
            decision_label = DecisionLabel.REDUCE_RISK.value
            entry_reason = f"trade allowed with reduced risk ({risk_multiplier:.2f})"
            block_reason = ""
        else:
            allow = True
            decision_label = DecisionLabel.ALLOW.value
            entry_reason = "all governance checks passed"
            block_reason = ""

        # Institutional approval: stricter — require score >= 70 AND no blocks
        # AND risk_multiplier >= 0.50 (don't allow extremely reduced trades either)
        institutional_approval = (
            allow
            and governance_score >= 70.0
            and risk_multiplier >= 0.50
            and inp.meta_confidence >= 0.75
            and inp.regime_confidence >= 0.70
        )

        return GovernanceDecision(
            allow_trade=allow,
            risk_multiplier=round(risk_multiplier, 4),
            decision_label=decision_label,
            exit_action=ExitAction.HOLD.value,
            entry_reason=entry_reason,
            block_reason=block_reason,
            exit_reason="",
            governance_score=round(governance_score, 2),
            institutional_approval=institutional_approval,
            account_profile=self.account_profile,
            audit=audit,
        )

    def evaluate_management(self, inp: GovernanceInput) -> GovernanceDecision:
        """Evaluate exit action for an open trade."""
        # Fail-closed
        fail_closed = self._fail_closed_check(inp)
        if fail_closed is not None:
            # On fail-closed in management, EXIT (close) for safety
            return GovernanceDecision(
                allow_trade=False,
                risk_multiplier=0.0,
                decision_label=DecisionLabel.EXIT.value,
                exit_action=ExitAction.CLOSE.value,
                entry_reason="",
                block_reason="fail-closed: invalid governance inputs",
                exit_reason="fail-closed: closing for safety due to invalid inputs",
                governance_score=0.0,
                institutional_approval=False,
                account_profile=self.account_profile,
                audit={"phase": "management", "fail_closed": True},
            )

        audit: Dict[str, Any] = {
            "phase": "management",
            "profile": self.account_profile,
            "checks": [],
            "current_r": inp.current_r_multiple,
            "mfe": inp.mfe,
            "mae": inp.mae,
        }

        r = inp.current_r_multiple
        th = self.thresholds

        # Order matters: protection states first (highest priority)
        # D. EQUITY_PROTECTION management
        action, reason = self._mgmt_equity_protection(inp, audit)
        if action != ExitAction.HOLD.value:
            return self._mgmt_decision(action, reason, inp, audit)

        # E. CAPITAL_PRESERVATION management
        action, reason = self._mgmt_capital_preservation(inp, audit)
        if action != ExitAction.HOLD.value:
            return self._mgmt_decision(action, reason, inp, audit)

        # F. REGIME_FLIP management
        action, reason = self._mgmt_regime_flip(inp, audit)
        if action != ExitAction.HOLD.value:
            return self._mgmt_decision(action, reason, inp, audit)

        # A. HIGH_VOLATILITY management (volatility shock against trade)
        action, reason = self._mgmt_high_volatility(inp, audit)
        if action != ExitAction.HOLD.value:
            return self._mgmt_decision(action, reason, inp, audit)

        # B. AMBIGUOUS_CANDLE management (no follow-through)
        action, reason = self._mgmt_ambiguous_candle(inp, audit)
        if action != ExitAction.HOLD.value:
            return self._mgmt_decision(action, reason, inp, audit)

        # C. BUY_SL/SELL_SL early invalidation
        action, reason = self._mgmt_baseline_invalidation(inp, audit)
        if action != ExitAction.HOLD.value:
            return self._mgmt_decision(action, reason, inp, audit)

        # Global profit protection ladder
        action, reason = self._mgmt_profit_ladder(inp, audit)
        if action != ExitAction.HOLD.value:
            return self._mgmt_decision(action, reason, inp, audit)

        # Default: HOLD
        return self._mgmt_decision(ExitAction.HOLD.value, "", inp, audit)

    # ─── Fail-closed ──────────────────────────────────────────────────────────

    def _fail_closed_check(self, inp: GovernanceInput) -> Optional[GovernanceDecision]:
        """Return a NO_TRADE decision if inputs are invalid. Else None."""
        invalid_reasons: List[str] = []
        if inp is None:
            invalid_reasons.append("input is None")
        else:
            if not isinstance(inp.meta_confidence, (int, float)) or inp.meta_confidence < 0:
                invalid_reasons.append("meta_confidence invalid")
            if not isinstance(inp.regime_confidence, (int, float)) or inp.regime_confidence < 0:
                invalid_reasons.append("regime_confidence invalid")
            if not isinstance(inp.atr_percentile, (int, float)) or inp.atr_percentile < 0 or inp.atr_percentile > 100:
                invalid_reasons.append("atr_percentile out of range")
            if not isinstance(inp.spread_usd, (int, float)) or inp.spread_usd < 0:
                invalid_reasons.append("spread_usd invalid")
            if not isinstance(inp.account_health, (int, float)) or inp.account_health < 0 or inp.account_health > 100:
                invalid_reasons.append("account_health out of range")
            if not isinstance(inp.regime_flip_probability, (int, float)) or inp.regime_flip_probability < 0 or inp.regime_flip_probability > 1:
                invalid_reasons.append("regime_flip_probability out of range")
            if not isinstance(inp.broker_quality, (int, float)) or inp.broker_quality < 0 or inp.broker_quality > 100:
                invalid_reasons.append("broker_quality out of range")

        if invalid_reasons:
            return GovernanceDecision(
                allow_trade=False,
                risk_multiplier=0.0,
                decision_label=DecisionLabel.NO_TRADE.value,
                exit_action=ExitAction.CLOSE.value if inp and inp.open_trade_side else ExitAction.HOLD.value,
                entry_reason="",
                block_reason="fail-closed: " + "; ".join(invalid_reasons),
                exit_reason="fail-closed: " + "; ".join(invalid_reasons),
                governance_score=0.0,
                institutional_approval=False,
                account_profile=self.account_profile,
                audit={"phase": "entry_or_management", "fail_closed": True,
                       "invalid_reasons": invalid_reasons},
            )
        return None

    # ─── Entry checks ─────────────────────────────────────────────────────────

    def _check_high_volatility_entry(self, inp: GovernanceInput,
                                     block_reasons: List[str], audit: Dict):
        """Sprint 9.9.3.3: 3-tier decision for HIGH_VOLATILITY.

        Tier 1 (block): ATR > max_atr_percentile_block (e.g., 95) → hard block.
        Tier 2 (throttle): ATR in (max_atr_percentile_throttle, block] (e.g., 90-95)
            → allow only if meta >= meta_required_in_throttle_vol (0.80) AND
              risk_multiplier <= risk_multiplier_in_throttle_vol (0.25).
        Tier 3 (warn): ATR in (max_atr_percentile_warn, throttle] (e.g., 80-90)
            → allow if meta >= meta_required_in_warn_vol (0.75) AND
              risk_multiplier <= risk_multiplier_in_warn_vol (0.50).
        Below warn: no special handling (normal governance).
        """
        th = self.thresholds
        check = {"name": "high_volatility_entry", "passed": True, "detail": ""}

        atr_block = th["max_atr_percentile_block"]
        atr_throttle = th.get("max_atr_percentile_throttle", th["max_atr_percentile_warn"])
        atr_warn = th["max_atr_percentile_warn"]

        if inp.atr_percentile > atr_block:
            # Tier 1: hard block
            check["passed"] = False
            check["detail"] = (f"ATR {inp.atr_percentile} > {atr_block} (hard block)")
            block_reasons.append(f"HIGH_VOLATILITY: ATR {inp.atr_percentile} > "
                                 f"{atr_block} — hard block")
        elif inp.atr_percentile > atr_throttle:
            # Tier 2: throttle — require very high meta + low spread
            meta_req = th.get("meta_required_in_throttle_vol",
                              th["meta_required_in_warn_vol"])
            if inp.meta_confidence < meta_req:
                check["passed"] = False
                check["detail"] = (f"ATR {inp.atr_percentile} in throttle zone; "
                                   f"meta {inp.meta_confidence} < {meta_req}")
                block_reasons.append(
                    f"HIGH_VOLATILITY: meta {inp.meta_confidence} < "
                    f"{meta_req} in throttle vol (ATR {inp.atr_percentile})")
            if inp.spread_usd > 0.40:
                check["passed"] = False
                check["detail"] += (f"; spread {inp.spread_usd} > 0.40 in throttle vol")
                block_reasons.append(
                    f"HIGH_VOLATILITY: spread {inp.spread_usd} > 0.40 in throttle vol")
            else:
                check["detail"] = (f"ATR {inp.atr_percentile} in throttle zone; "
                                   f"meta {inp.meta_confidence} >= {meta_req} OK")
        elif inp.atr_percentile > atr_warn:
            # Tier 3: warn — require higher meta
            meta_req = th["meta_required_in_warn_vol"]
            if inp.meta_confidence < meta_req:
                check["passed"] = False
                check["detail"] = (f"ATR {inp.atr_percentile} in warn zone; "
                                   f"meta {inp.meta_confidence} < {meta_req}")
                block_reasons.append(
                    f"HIGH_VOLATILITY: meta {inp.meta_confidence} < "
                    f"{meta_req} in warn vol")
            if inp.spread_usd > 0.40:
                check["passed"] = False
                check["detail"] += (f"; spread {inp.spread_usd} > 0.40 in warn vol")
                block_reasons.append(
                    f"HIGH_VOLATILITY: spread {inp.spread_usd} > 0.40 in warn vol")
            else:
                check["detail"] = (f"ATR {inp.atr_percentile} in warn zone; "
                                   f"meta {inp.meta_confidence} >= {meta_req} OK")
        audit["checks"].append(check)

    def _check_ambiguous_candle_entry(self, inp: GovernanceInput,
                                      block_reasons: List[str], audit: Dict):
        th = self.thresholds
        check = {"name": "ambiguous_candle_entry", "passed": True, "detail": ""}
        if inp.ambiguous_candle:
            # Default no-trade; allow only with strong confirmation
            strong_signal = (
                inp.meta_confidence >= 0.75
                and inp.regime_confidence >= 0.70
                and inp.spread_usd <= th["max_spread_usd"]
                and inp.liquidity in ("GOOD", "NORMAL")
                and inp.confirmation_present
            )
            if not strong_signal:
                check["passed"] = False
                missing = []
                if inp.meta_confidence < 0.75:
                    missing.append(f"meta {inp.meta_confidence} < 0.75")
                if inp.regime_confidence < 0.70:
                    missing.append(f"regime_conf {inp.regime_confidence} < 0.70")
                if inp.spread_usd > th["max_spread_usd"]:
                    missing.append(f"spread {inp.spread_usd} > {th['max_spread_usd']}")
                if inp.liquidity not in ("GOOD", "NORMAL"):
                    missing.append(f"liquidity {inp.liquidity} not GOOD/NORMAL")
                if not inp.confirmation_present:
                    missing.append("no confirmation")
                check["detail"] = "ambiguous candle requires: " + ", ".join(missing)
                block_reasons.append(
                    f"AMBIGUOUS_CANDLE: blocked — missing: {', '.join(missing)}")
        audit["checks"].append(check)

    def _check_baseline_entry(self, inp: GovernanceInput,
                              block_reasons: List[str], audit: Dict):
        """Sprint 9.9.3.3: 3-tier baseline checks with expected edge.

        Tier 1 (hard block):
          - spread > max_spread_usd_block
          - meta < min_meta_confidence_block
          - broker_quality < min_broker_quality_block

        Tier 2 (throttle — allow with reduced risk only if expected_edge positive):
          - spread > max_spread_usd (normal cap)
          - meta < min_meta_confidence (normal min)

        Tier 3 (allow): all checks pass normally.
        """
        th = self.thresholds
        check = {"name": "baseline_entry", "passed": True, "detail": ""}

        # ── Tier 1: hard blocks ──
        # Spread hard block
        spread_block = th.get("max_spread_usd_block", th["max_spread_usd"] * 1.5)
        if inp.spread_usd > spread_block:
            check["passed"] = False
            check["detail"] = (f"spread {inp.spread_usd} > {spread_block} (hard block)")
            block_reasons.append(
                f"BASELINE: spread {inp.spread_usd} > {spread_block} — hard block")
            audit["checks"].append(check)
            return

        # Meta hard block
        meta_block = th.get("min_meta_confidence_block", 0.0)
        if inp.meta_confidence < meta_block:
            check["passed"] = False
            check["detail"] = (f"meta {inp.meta_confidence} < {meta_block} (hard block)")
            block_reasons.append(
                f"BASELINE: meta {inp.meta_confidence} < {meta_block} — hard block")
            audit["checks"].append(check)
            return

        # Broker quality hard block
        broker_block = th.get("min_broker_quality_block", 0.0)
        if inp.broker_quality < broker_block:
            check["passed"] = False
            check["detail"] = (f"broker_quality {inp.broker_quality} < "
                               f"{broker_block} (hard block)")
            block_reasons.append(
                f"BASELINE: broker_quality {inp.broker_quality} < "
                f"{broker_block} — hard block")
            audit["checks"].append(check)
            return

        # ── Tier 2: throttle (allow with reduced risk if expected edge positive) ──
        # If spread > normal cap but expected_edge > cost_buffer AND profile allows
        # (RETAIL_SAFE allows; PROP_FIRM_STRICT/INSTITUTIONAL also allow if edge clearly positive)
        cost_buffer = th.get("cost_buffer_usd", 0.50)
        if inp.spread_usd > th["max_spread_usd"]:
            # Check expected edge after costs
            if inp.expected_edge_usd > cost_buffer:
                check["detail"] = (f"spread {inp.spread_usd} > {th['max_spread_usd']} "
                                   f"but expected_edge {inp.expected_edge_usd} > "
                                   f"cost_buffer {cost_buffer} — throttle (allow)")
                # Don't block — risk_multiplier will be reduced
            else:
                check["passed"] = False
                check["detail"] = (f"spread {inp.spread_usd} > {th['max_spread_usd']} "
                                   f"AND expected_edge {inp.expected_edge_usd} < "
                                   f"cost_buffer {cost_buffer} — block")
                block_reasons.append(
                    f"BASELINE: spread {inp.spread_usd} > {th['max_spread_usd']} "
                    f"AND expected_edge < {cost_buffer} — block")
                audit["checks"].append(check)
                return

        # If meta below normal min but above hard block:
        # allow only if expected_edge positive AND profile is RETAIL_SAFE
        # OR expected_edge strongly positive (>= 2x cost_buffer) for stricter profiles
        if inp.meta_confidence < th["min_meta_confidence"]:
            strong_edge = inp.expected_edge_usd >= (2.0 * cost_buffer)
            if inp.account_profile == AccountProfile.RETAIL_SAFE.value:
                if inp.expected_edge_usd > cost_buffer:
                    check["detail"] = (f"meta {inp.meta_confidence} < "
                                       f"{th['min_meta_confidence']} but "
                                       f"expected_edge > cost_buffer (RETAIL_SAFE) — throttle")
                else:
                    check["passed"] = False
                    check["detail"] = (f"meta {inp.meta_confidence} < "
                                       f"{th['min_meta_confidence']} AND expected_edge "
                                       f"{inp.expected_edge_usd} < cost_buffer {cost_buffer}")
                    block_reasons.append(
                        f"BASELINE: meta {inp.meta_confidence} < "
                        f"{th['min_meta_confidence']} AND expected_edge < "
                        f"{cost_buffer} — block")
                    audit["checks"].append(check)
                    return
            elif strong_edge:
                check["detail"] = (f"meta {inp.meta_confidence} < "
                                   f"{th['min_meta_confidence']} but strong expected_edge "
                                   f"{inp.expected_edge_usd} >= {2.0*cost_buffer} — throttle")
            else:
                check["passed"] = False
                check["detail"] = (f"meta {inp.meta_confidence} < "
                                   f"{th['min_meta_confidence']} AND expected_edge "
                                   f"{inp.expected_edge_usd} < {2.0*cost_buffer} (strong)")
                block_reasons.append(
                    f"BASELINE: meta {inp.meta_confidence} < "
                    f"{th['min_meta_confidence']} AND no strong edge — block")
                audit["checks"].append(check)
                return

        # Broker quality throttle
        if inp.broker_quality < th["min_broker_quality"]:
            check["detail"] = (f"broker_quality {inp.broker_quality} < "
                               f"{th['min_broker_quality']} — throttle (risk reduced)")
            # Don't block — risk_multiplier will be reduced

        audit["checks"].append(check)

    def _check_equity_protection_entry(self, inp: GovernanceInput,
                                       block_reasons: List[str], audit: Dict):
        check = {"name": "equity_protection_entry", "passed": True, "detail": ""}
        if inp.equity_protection_active:
            check["passed"] = False
            check["detail"] = "equity_protection_active=True — no new trades"
            block_reasons.append(
                "EQUITY_PROTECTION: zone active — no new trades")
        audit["checks"].append(check)

    def _check_capital_preservation_entry(self, inp: GovernanceInput,
                                          block_reasons: List[str], audit: Dict):
        check = {"name": "capital_preservation_entry", "passed": True, "detail": ""}
        if inp.capital_preservation_active:
            check["passed"] = False
            check["detail"] = "capital_preservation_active=True — no new trades"
            block_reasons.append(
                "CAPITAL_PRESERVATION: active — no new trades / no recovery trade")
        audit["checks"].append(check)

    def _check_regime_flip_entry(self, inp: GovernanceInput,
                                 block_reasons: List[str], audit: Dict):
        """Sprint 9.9.3.3: 3-tier REGIME_FLIP.

        Tier 1 (hard block): regime_flip_probability > max_regime_flip_prob_block (0.75)
        Tier 2 (throttle): regime_flip_probability > max_regime_flip_prob (0.60)
            → allow with reduced risk only if confirmation_present AND
              expected_edge > cost_buffer
        Tier 3 (allow): below throttle threshold
        """
        th = self.thresholds
        check = {"name": "regime_flip_entry", "passed": True, "detail": ""}
        block_threshold = th.get("max_regime_flip_prob_block", 0.75)
        throttle_threshold = th["max_regime_flip_prob"]
        cost_buffer = th.get("cost_buffer_usd", 0.50)

        if inp.regime_flip_probability > block_threshold:
            # Hard block
            check["passed"] = False
            check["detail"] = (f"regime_flip_probability {inp.regime_flip_probability} > "
                               f"{block_threshold} (hard block)")
            block_reasons.append(
                f"REGIME_FLIP: probability {inp.regime_flip_probability} > "
                f"{block_threshold} — hard block")
        elif inp.regime_flip_probability > throttle_threshold:
            # Throttle: require confirmation + positive expected edge
            if not inp.confirmation_present:
                check["passed"] = False
                check["detail"] = (f"flip prob {inp.regime_flip_probability} > "
                                   f"{throttle_threshold} AND no confirmation — block")
                block_reasons.append(
                    f"REGIME_FLIP: prob {inp.regime_flip_probability} > "
                    f"{throttle_threshold} AND no confirmation — block")
            elif inp.expected_edge_usd <= cost_buffer:
                check["passed"] = False
                check["detail"] = (f"flip prob {inp.regime_flip_probability} > "
                                   f"{throttle_threshold} AND expected_edge "
                                   f"{inp.expected_edge_usd} <= cost_buffer {cost_buffer}")
                block_reasons.append(
                    f"REGIME_FLIP: prob {inp.regime_flip_probability} > "
                    f"{throttle_threshold} AND expected_edge <= {cost_buffer} — block")
            else:
                check["detail"] = (f"flip prob {inp.regime_flip_probability} > "
                                   f"{throttle_threshold} but confirmed + "
                                   f"expected_edge > cost_buffer — throttle (allow reduced)")
        audit["checks"].append(check)

    def _check_account_state_entry(self, inp: GovernanceInput,
                                   block_reasons: List[str], audit: Dict):
        """Sprint 9.9.3.3: 3-tier account health checks.

        Tier 1 (hard block): account_health < min_account_health_block (e.g., 40)
        Tier 2 (throttle): account_health < min_account_health (e.g., 60)
            → block unless expected_edge strongly positive
        Tier 3 (allow): account_health >= min_account_health
        """
        th = self.thresholds
        check = {"name": "account_state_entry", "passed": True, "detail": ""}
        health_block = th.get("min_account_health_block", 0)
        health_throttle = th["min_account_health"]
        cost_buffer = th.get("cost_buffer_usd", 0.50)

        # Tier 1: hard block
        if inp.account_health < health_block:
            check["passed"] = False
            check["detail"] = (f"account_health {inp.account_health} < "
                               f"{health_block} (hard block)")
            block_reasons.append(
                f"ACCOUNT: health {inp.account_health} < "
                f"{health_block} — hard block")
            audit["checks"].append(check)
            return

        # Tier 2: throttle
        if inp.account_health < health_throttle:
            strong_edge = inp.expected_edge_usd >= (2.0 * cost_buffer)
            if not strong_edge:
                check["passed"] = False
                check["detail"] = (f"account_health {inp.account_health} < "
                                   f"{health_throttle} AND no strong expected_edge "
                                   f"(need >= {2.0*cost_buffer})")
                block_reasons.append(
                    f"ACCOUNT: health {inp.account_health} < "
                    f"{health_throttle} AND no strong edge — block")
                audit["checks"].append(check)
                return
            else:
                check["detail"] = (f"account_health {inp.account_health} < "
                                   f"{health_throttle} but strong expected_edge — throttle")

        # Setup winrate
        if (inp.rolling_setup_winrate is not None
                and inp.rolling_setup_winrate < th["min_rolling_setup_winrate"]):
            check["passed"] = False
            check["detail"] += (f"; rolling_setup_winrate {inp.rolling_setup_winrate} < "
                                f"{th['min_rolling_setup_winrate']}")
            block_reasons.append(
                f"SETUP: rolling winrate {inp.rolling_setup_winrate} < "
                f"{th['min_rolling_setup_winrate']} — setup disabled")
        audit["checks"].append(check)

    def _check_daily_dd_entry(self, inp: GovernanceInput,
                              block_reasons: List[str], audit: Dict):
        th = self.thresholds
        check = {"name": "daily_dd_entry", "passed": True, "detail": ""}
        ratio = (inp.daily_dd_pct / inp.daily_dd_threshold_pct
                 if inp.daily_dd_threshold_pct > 0 else 0.0)
        if ratio > th["max_daily_dd_pct_of_threshold"]:
            check["passed"] = False
            check["detail"] = (f"daily_dd {inp.daily_dd_pct}% is "
                               f"{ratio*100:.1f}% of threshold "
                               f"{inp.daily_dd_threshold_pct}% > "
                               f"{th['max_daily_dd_pct_of_threshold']*100:.0f}%")
            block_reasons.append(
                f"DAILY_DD: {ratio*100:.1f}% of threshold > "
                f"{th['max_daily_dd_pct_of_threshold']*100:.0f}% — no new trades")
        audit["checks"].append(check)

    # ─── Risk multiplier ──────────────────────────────────────────────────────

    def _compute_risk_multiplier(self, inp: GovernanceInput, audit: Dict) -> float:
        """Compute risk multiplier. Always <= 1.0, can only DECREASE risk.

        Sprint 9.9.3.3: 3-tier throttle integration.
        """
        th = self.thresholds
        mult = 1.0
        reasons = []

        # 3-tier volatility throttle
        atr_block = th["max_atr_percentile_block"]
        atr_throttle = th.get("max_atr_percentile_throttle", th["max_atr_percentile_warn"])
        atr_warn = th["max_atr_percentile_warn"]

        # Throttle zone (between throttle and block): heavy reduction
        if atr_throttle < inp.atr_percentile <= atr_block:
            mult_throttle = th.get("risk_multiplier_in_throttle_vol", 0.25)
            mult = min(mult, mult_throttle)
            reasons.append(f"throttle vol (ATR {inp.atr_percentile}) → {mult_throttle}")
        # Warn zone (between warn and throttle): moderate reduction
        elif atr_warn < inp.atr_percentile <= atr_throttle:
            mult_warn = th["risk_multiplier_in_warn_vol"]
            mult = min(mult, mult_warn)
            reasons.append(f"warn vol (ATR {inp.atr_percentile}) → {mult_warn}")

        # Regime transition (flip prob > throttle but <= block) → reduce to 0.50
        flip_throttle = th["max_regime_flip_prob"]
        if inp.regime_flip_probability > flip_throttle:
            mult = min(mult, 0.50)
            reasons.append(f"regime flip risk (prob {inp.regime_flip_probability}) → 0.50")

        # Capital preservation (should already be blocked, but safety)
        if inp.capital_preservation_active:
            mult = 0.0
            reasons.append("capital_preservation_active → 0.0")

        # Equity protection (should already be blocked, but safety)
        if inp.equity_protection_active:
            mult = 0.0
            reasons.append("equity_protection_active → 0.0")

        # Account health below 70 → reduce
        if inp.account_health < 70:
            mult = min(mult, 0.50)
            reasons.append(f"health {inp.account_health} < 70 → 0.50")
        elif inp.account_health < 85:
            mult = min(mult, 0.75)
            reasons.append(f"health {inp.account_health} < 85 → 0.75")

        # Broker quality below 70 → reduce
        if inp.broker_quality < th["min_broker_quality"]:
            mult = min(mult, 0.50)
            reasons.append(f"broker_quality {inp.broker_quality} < "
                           f"{th['min_broker_quality']} → 0.50")

        # Poor liquidity → reduce
        if inp.liquidity == "POOR":
            mult = min(mult, 0.50)
            reasons.append("poor liquidity → 0.50")

        # Off session → reduce
        if inp.session == "OFF":
            mult = min(mult, 0.50)
            reasons.append("off session → 0.50")

        # Sprint 9.9.3.3: Spread above normal cap → additional reduction
        if inp.spread_usd > th["max_spread_usd"]:
            mult = min(mult, 0.50)
            reasons.append(f"spread {inp.spread_usd} > {th['max_spread_usd']} → 0.50")

        # Sprint 9.9.3.3: Meta below normal min → additional reduction
        if inp.meta_confidence < th["min_meta_confidence"]:
            mult = min(mult, 0.25)
            reasons.append(f"meta {inp.meta_confidence} < "
                           f"{th['min_meta_confidence']} → 0.25")

        audit["risk_multiplier"] = mult
        audit["risk_multiplier_reasons"] = reasons
        return mult

    # ─── Management (open-trade) checks ───────────────────────────────────────

    def _mgmt_equity_protection(self, inp: GovernanceInput,
                                audit: Dict) -> tuple[str, str]:
        if not inp.equity_protection_active:
            return ExitAction.HOLD.value, ""
        # Existing profitable trades: lock profit
        if inp.current_r_multiple > 0.3:
            audit["checks"].append({
                "name": "mgmt_equity_protection", "passed": True,
                "detail": f"profitable {inp.current_r_multiple}R — lock profit"})
            return ExitAction.PARTIAL_CLOSE.value, "equity_protection: lock profit on +R trade"
        # Near BE: close at BE
        if -0.1 <= inp.current_r_multiple <= 0.3:
            audit["checks"].append({
                "name": "mgmt_equity_protection", "passed": True,
                "detail": f"near BE {inp.current_r_multiple}R — close at BE"})
            return ExitAction.CLOSE.value, "equity_protection: close near-BE trade at BE"
        # Losing trades: reduce exposure
        if inp.current_r_multiple < -0.1:
            audit["checks"].append({
                "name": "mgmt_equity_protection", "passed": True,
                "detail": f"losing {inp.current_r_multiple}R — reduce exposure"})
            return ExitAction.REDUCE.value, "equity_protection: reduce exposure on losing trade"
        return ExitAction.HOLD.value, ""

    def _mgmt_capital_preservation(self, inp: GovernanceInput,
                                   audit: Dict) -> tuple[str, str]:
        if not inp.capital_preservation_active:
            return ExitAction.HOLD.value, ""
        # No recovery trade; manage defensively
        if inp.current_r_multiple >= -0.1:
            audit["checks"].append({
                "name": "mgmt_capital_preservation", "passed": True,
                "detail": f"trade at {inp.current_r_multiple}R — defensive close"})
            return ExitAction.CLOSE.value, "capital_preservation: defensive close (no recovery trade)"
        else:
            audit["checks"].append({
                "name": "mgmt_capital_preservation", "passed": True,
                "detail": f"losing {inp.current_r_multiple}R — reduce"})
            return ExitAction.REDUCE.value, "capital_preservation: reduce losing trade"
        return ExitAction.HOLD.value, ""

    def _mgmt_regime_flip(self, inp: GovernanceInput,
                          audit: Dict) -> tuple[str, str]:
        th = self.thresholds
        if inp.regime_flip_probability <= th["max_regime_flip_prob"]:
            return ExitAction.HOLD.value, ""
        # Flip against open trade
        # If trade in profit: tight trail or close profit
        if inp.current_r_multiple > 0.5:
            audit["checks"].append({
                "name": "mgmt_regime_flip", "passed": True,
                "detail": f"flip {inp.regime_flip_probability} + profit {inp.current_r_multiple}R — tight trail"})
            return ExitAction.TIGHT_TRAIL.value, "regime_flip: tight trail on profitable trade"
        # Near BE: close at BE
        if -0.1 <= inp.current_r_multiple <= 0.5:
            audit["checks"].append({
                "name": "mgmt_regime_flip", "passed": True,
                "detail": f"flip + near-BE {inp.current_r_multiple}R — close at BE"})
            return ExitAction.CLOSE.value, "regime_flip: close at BE"
        # Losing and flip against: reduce 50%
        if inp.current_r_multiple < -0.1:
            audit["checks"].append({
                "name": "mgmt_regime_flip", "passed": True,
                "detail": f"flip + losing {inp.current_r_multiple}R — reduce 50%"})
            return ExitAction.REDUCE.value, "regime_flip: reduce 50% on losing trade"
        return ExitAction.HOLD.value, ""

    def _mgmt_high_volatility(self, inp: GovernanceInput,
                              audit: Dict) -> tuple[str, str]:
        th = self.thresholds
        # If volatility shock expands against trade (ATR now > block threshold),
        # close or reduce
        if inp.atr_percentile > th["max_atr_percentile_block"]:
            if inp.current_r_multiple < 0:
                audit["checks"].append({
                    "name": "mgmt_high_volatility", "passed": True,
                    "detail": f"vol shock {inp.atr_percentile} + losing — close"})
                return ExitAction.CLOSE.value, "high_volatility: vol shock + losing — close"
            else:
                audit["checks"].append({
                    "name": "mgmt_high_volatility", "passed": True,
                    "detail": f"vol shock {inp.atr_percentile} + profit — reduce"})
                return ExitAction.REDUCE.value, "high_volatility: vol shock + profit — reduce"
        return ExitAction.HOLD.value, ""

    def _mgmt_ambiguous_candle(self, inp: GovernanceInput,
                               audit: Dict) -> tuple[str, str]:
        th = self.thresholds
        if not inp.ambiguous_candle:
            return ExitAction.HOLD.value, ""
        # If no follow-through within configured candles, close early
        if (inp.candles_in_trade >= th["early_close_no_followthrough_candles"]
                and inp.current_r_multiple < th["early_close_no_followthrough_r"]):
            audit["checks"].append({
                "name": "mgmt_ambiguous_candle", "passed": True,
                "detail": (f"no follow-through: {inp.candles_in_trade} candles, "
                           f"R={inp.current_r_multiple} — early close")})
            return ExitAction.CLOSE.value, "ambiguous_candle: no follow-through — early close"
        return ExitAction.HOLD.value, ""

    def _mgmt_baseline_invalidation(self, inp: GovernanceInput,
                                    audit: Dict) -> tuple[str, str]:
        th = self.thresholds
        # If trade moves quickly to -0.3R with weak follow-through, early invalidation
        if (inp.current_r_multiple <= th["early_invalidation_r"]
                and inp.candles_in_trade <= 2
                and inp.mae > 0):
            audit["checks"].append({
                "name": "mgmt_baseline_invalidation", "passed": True,
                "detail": (f"early invalidation: R={inp.current_r_multiple}, "
                           f"candles={inp.candles_in_trade} — close")})
            return ExitAction.CLOSE.value, "baseline: early invalidation — close"
        # If trade fails to reach +0.3R within time limit, early close
        if (inp.candles_in_trade >= th["early_close_no_followthrough_candles"]
                and inp.current_r_multiple < th["early_close_no_followthrough_r"]):
            audit["checks"].append({
                "name": "mgmt_baseline_invalidation", "passed": True,
                "detail": (f"no follow-through: {inp.candles_in_trade} candles, "
                           f"R={inp.current_r_multiple} < {th['early_close_no_followthrough_r']} — close")})
            return ExitAction.CLOSE.value, "baseline: no follow-through — early close"
        return ExitAction.HOLD.value, ""

    def _mgmt_profit_ladder(self, inp: GovernanceInput,
                            audit: Dict) -> tuple[str, str]:
        """Global R-based profit protection ladder."""
        th = self.thresholds
        r = inp.current_r_multiple

        # +1.5R: tight trail
        if r >= th["tight_trail_at_r"]:
            audit["checks"].append({
                "name": "mgmt_profit_ladder", "passed": True,
                "detail": f"R={r} >= {th['tight_trail_at_r']} — tight trail"})
            return ExitAction.TIGHT_TRAIL.value, f"profit_ladder: R={r} — tight trail"
        # +1.0R: 50% partial + BE
        if r >= th["partial_50_at_r"]:
            audit["checks"].append({
                "name": "mgmt_profit_ladder", "passed": True,
                "detail": f"R={r} >= {th['partial_50_at_r']} — 50% partial + BE"})
            return ExitAction.PARTIAL_CLOSE.value, f"profit_ladder: R={r} — 50% partial + BE"
        # +0.5R: 25% partial + BE (or -0.1R)
        if r >= th["partial_25_at_r"]:
            audit["checks"].append({
                "name": "mgmt_profit_ladder", "passed": True,
                "detail": f"R={r} >= {th['partial_25_at_r']} — 25% partial + BE"})
            return ExitAction.MOVE_BE.value, f"profit_ladder: R={r} — move BE + 25% partial"
        # +0.3R: check follow-through (prepare, but HOLD)
        if r >= 0.3:
            audit["checks"].append({
                "name": "mgmt_profit_ladder", "passed": True,
                "detail": f"R={r} >= 0.3 — monitoring follow-through"})
            return ExitAction.HOLD.value, ""
        return ExitAction.HOLD.value, ""

    def _mgmt_decision(self, action: str, reason: str,
                       inp: GovernanceInput, audit: Dict) -> GovernanceDecision:
        if action == ExitAction.HOLD.value:
            label = DecisionLabel.ALLOW.value
            allow = True
            risk_mult = 1.0
        elif action in (ExitAction.CLOSE.value, ExitAction.REDUCE.value,
                        ExitAction.PARTIAL_CLOSE.value):
            label = DecisionLabel.EXIT.value
            allow = False
            risk_mult = 0.0 if action == ExitAction.CLOSE.value else 0.5
        else:  # MOVE_BE, TIGHT_TRAIL
            label = DecisionLabel.ALLOW.value
            allow = True
            risk_mult = 1.0
        # Compute score for audit
        score_components = self._compute_score_components(inp, audit)
        governance_score = self._weighted_score(score_components)
        audit["score_components"] = score_components
        audit["governance_score"] = round(governance_score, 2)

        return GovernanceDecision(
            allow_trade=allow,
            risk_multiplier=round(risk_mult, 4),
            decision_label=label,
            exit_action=action,
            entry_reason="",
            block_reason="",
            exit_reason=reason,
            governance_score=round(governance_score, 2),
            institutional_approval=False,  # management decisions don't need this
            account_profile=self.account_profile,
            audit=audit,
        )

    # ─── Score computation ────────────────────────────────────────────────────

    def _compute_score_components(self, inp: GovernanceInput,
                                  audit: Dict) -> Dict[str, float]:
        th = self.thresholds
        components: Dict[str, float] = {}

        # regime_validity (0-100)
        rc = max(0.0, min(1.0, inp.regime_confidence))
        # Penalty if regime is UNKNOWN or TRANSITION
        regime_label_lc = (inp.regime_label or "").upper()
        if regime_label_lc in ("UNKNOWN", "TRANSITION", "MIXED"):
            rc *= 0.6
        components["regime_validity"] = round(rc * 100, 2)

        # alpha_strength (0-100)
        mc = max(0.0, min(1.0, inp.meta_confidence))
        # If meta below threshold for profile, hard penalty
        if mc < th["min_meta_confidence"]:
            mc *= 0.4
        components["alpha_strength"] = round(mc * 100, 2)

        # volatility_safety (0-100) — higher ATR = lower score
        atr = inp.atr_percentile
        if atr > th["max_atr_percentile_block"]:
            vol_score = 10.0
        elif atr > th["max_atr_percentile_warn"]:
            vol_score = 40.0
        elif atr > 60:
            vol_score = 70.0
        else:
            vol_score = 100.0
        components["volatility_safety"] = vol_score

        # cost_safety (0-100) — higher spread = lower score
        spread = inp.spread_usd
        if spread > th["max_spread_usd"]:
            cost_score = 10.0
        elif spread > 0.40:
            cost_score = 50.0
        elif spread > 0.30:
            cost_score = 75.0
        else:
            cost_score = 100.0
        # Slippage penalty
        if inp.slippage_pips > 5:
            cost_score -= 20
        components["cost_safety"] = max(0.0, cost_score)

        # session_liquidity_safety (0-100)
        sess_score = 100.0
        if inp.session == "OFF":
            sess_score -= 50
        elif inp.session in ("ASIA",):
            sess_score -= 20
        if inp.liquidity == "POOR":
            sess_score -= 40
        elif inp.liquidity == "NORMAL":
            sess_score -= 10
        components["session_liquidity_safety"] = max(0.0, sess_score)

        # account_health (0-100) — direct
        components["account_health"] = max(0.0, min(100.0, inp.account_health))

        # protection_state (0-100) — penalty if any protection active
        prot_score = 100.0
        if inp.capital_preservation_active:
            prot_score = 0.0
        elif inp.equity_protection_active:
            prot_score = 20.0
        elif inp.account_health < 70:
            prot_score = 50.0
        # Daily DD penalty
        if inp.daily_dd_threshold_pct > 0:
            dd_ratio = inp.daily_dd_pct / inp.daily_dd_threshold_pct
            if dd_ratio > th["max_daily_dd_pct_of_threshold"]:
                prot_score = min(prot_score, 20.0)
            elif dd_ratio > 0.5:
                prot_score = min(prot_score, 60.0)
        components["protection_state"] = prot_score

        # regime_transition_risk (0-100) — higher flip prob = lower score
        flip = max(0.0, min(1.0, inp.regime_flip_probability))
        components["regime_transition_risk"] = round((1.0 - flip) * 100, 2)

        return components

    def _weighted_score(self, components: Dict[str, float]) -> float:
        total = 0.0
        for k, w in SCORE_WEIGHTS.items():
            total += w * components.get(k, 0.0)
        return round(total, 2)
