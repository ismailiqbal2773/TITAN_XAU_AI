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
        "min_regime_confidence": 0.55,
        "max_spread_usd": 1.00,
        "max_atr_percentile_block": 95,         # block above
        "max_atr_percentile_warn": 85,          # require higher meta above
        "meta_required_in_warn_vol": 0.70,
        "risk_multiplier_in_warn_vol": 0.75,
        "max_regime_flip_prob": 0.65,
        "min_account_health": 50,
        "min_broker_quality": 60,
        "min_rolling_setup_winrate": 0.30,
        "be_at_r": 0.5,
        "partial_25_at_r": 0.5,
        "partial_50_at_r": 1.0,
        "tight_trail_at_r": 1.5,
        "early_close_no_followthrough_r": 0.3,
        "early_close_no_followthrough_candles": 5,
        "early_invalidation_r": -0.3,
        "max_daily_dd_pct_of_threshold": 0.80,
    },
    AccountProfile.PROP_FIRM_STRICT.value: {
        "min_meta_confidence": 0.70,
        "min_regime_confidence": 0.60,
        "max_spread_usd": 0.50,
        "max_atr_percentile_block": 92,
        "max_atr_percentile_warn": 80,
        "meta_required_in_warn_vol": 0.75,
        "risk_multiplier_in_warn_vol": 0.50,
        "max_regime_flip_prob": 0.60,
        "min_account_health": 60,
        "min_broker_quality": 70,
        "min_rolling_setup_winrate": 0.35,
        "be_at_r": 0.5,
        "partial_25_at_r": 0.5,
        "partial_50_at_r": 1.0,
        "tight_trail_at_r": 1.5,
        "early_close_no_followthrough_r": 0.3,
        "early_close_no_followthrough_candles": 4,
        "early_invalidation_r": -0.3,
        "max_daily_dd_pct_of_threshold": 0.60,
    },
    AccountProfile.INSTITUTIONAL_CAPITAL_PROTECTION.value: {
        "min_meta_confidence": 0.75,
        "min_regime_confidence": 0.70,
        "max_spread_usd": 0.40,
        "max_atr_percentile_block": 90,
        "max_atr_percentile_warn": 75,
        "meta_required_in_warn_vol": 0.78,
        "risk_multiplier_in_warn_vol": 0.50,
        "max_regime_flip_prob": 0.55,
        "min_account_health": 75,
        "min_broker_quality": 80,
        "min_rolling_setup_winrate": 0.40,
        "be_at_r": 0.5,
        "partial_25_at_r": 0.5,
        "partial_50_at_r": 1.0,
        "tight_trail_at_r": 1.5,
        "early_close_no_followthrough_r": 0.3,
        "early_close_no_followthrough_candles": 3,
        "early_invalidation_r": -0.25,
        "max_daily_dd_pct_of_threshold": 0.50,
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
        th = self.thresholds
        check = {"name": "high_volatility_entry", "passed": True, "detail": ""}
        if inp.atr_percentile > th["max_atr_percentile_block"]:
            check["passed"] = False
            check["detail"] = (f"ATR percentile {inp.atr_percentile} > "
                               f"{th['max_atr_percentile_block']} (block)")
            block_reasons.append(f"HIGH_VOLATILITY: ATR {inp.atr_percentile} > "
                                 f"{th['max_atr_percentile_block']} — block")
        elif inp.atr_percentile > th["max_atr_percentile_warn"]:
            # Require higher meta + tighter spread + reduced risk
            if inp.meta_confidence < th["meta_required_in_warn_vol"]:
                check["passed"] = False
                check["detail"] = (f"ATR {inp.atr_percentile} in warn zone; "
                                   f"meta {inp.meta_confidence} < "
                                   f"{th['meta_required_in_warn_vol']}")
                block_reasons.append(
                    f"HIGH_VOLATILITY: meta {inp.meta_confidence} < "
                    f"{th['meta_required_in_warn_vol']} in warn vol")
            if inp.spread_usd > 0.40:
                check["passed"] = False
                check["detail"] += (f"; spread {inp.spread_usd} > 0.40 in warn vol")
                block_reasons.append(
                    f"HIGH_VOLATILITY: spread {inp.spread_usd} > 0.40 in warn vol")
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
        th = self.thresholds
        check = {"name": "baseline_entry", "passed": True, "detail": ""}
        # Spread block
        if inp.spread_usd > th["max_spread_usd"]:
            check["passed"] = False
            check["detail"] = f"spread {inp.spread_usd} > {th['max_spread_usd']}"
            block_reasons.append(
                f"BASELINE: spread {inp.spread_usd} > {th['max_spread_usd']} — block")
        # Meta block
        elif inp.meta_confidence < th["min_meta_confidence"]:
            check["passed"] = False
            check["detail"] = (f"meta {inp.meta_confidence} < "
                               f"{th['min_meta_confidence']}")
            block_reasons.append(
                f"BASELINE: meta {inp.meta_confidence} < "
                f"{th['min_meta_confidence']} — block")
        # Broker quality
        elif inp.broker_quality < th["min_broker_quality"]:
            check["passed"] = False
            check["detail"] = (f"broker_quality {inp.broker_quality} < "
                               f"{th['min_broker_quality']}")
            block_reasons.append(
                f"BASELINE: broker_quality {inp.broker_quality} < "
                f"{th['min_broker_quality']} — block")
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
        th = self.thresholds
        check = {"name": "regime_flip_entry", "passed": True, "detail": ""}
        if inp.regime_flip_probability > th["max_regime_flip_prob"]:
            check["passed"] = False
            check["detail"] = (f"regime_flip_probability {inp.regime_flip_probability} > "
                               f"{th['max_regime_flip_prob']}")
            block_reasons.append(
                f"REGIME_FLIP: probability {inp.regime_flip_probability} > "
                f"{th['max_regime_flip_prob']} — no new trade")
        audit["checks"].append(check)

    def _check_account_state_entry(self, inp: GovernanceInput,
                                   block_reasons: List[str], audit: Dict):
        th = self.thresholds
        check = {"name": "account_state_entry", "passed": True, "detail": ""}
        if inp.account_health < th["min_account_health"]:
            check["passed"] = False
            check["detail"] = (f"account_health {inp.account_health} < "
                               f"{th['min_account_health']}")
            block_reasons.append(
                f"ACCOUNT: health {inp.account_health} < "
                f"{th['min_account_health']} — no new trades")
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
        """Compute risk multiplier. Always <= 1.0, can only DECREASE risk."""
        th = self.thresholds
        mult = 1.0
        reasons = []

        # High volatility warn zone → reduce
        if (th["max_atr_percentile_warn"] < inp.atr_percentile
                <= th["max_atr_percentile_block"]):
            mult = min(mult, th["risk_multiplier_in_warn_vol"])
            reasons.append(f"warn vol → {th['risk_multiplier_in_warn_vol']}")

        # Regime transition (flip prob > 0.40) → reduce to 0.50
        if inp.regime_flip_probability > 0.40:
            mult = min(mult, 0.50)
            reasons.append(f"regime flip risk → 0.50")

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
        if inp.broker_quality < 70:
            mult = min(mult, 0.50)
            reasons.append(f"broker_quality {inp.broker_quality} < 70 → 0.50")

        # Poor liquidity → reduce
        if inp.liquidity == "POOR":
            mult = min(mult, 0.50)
            reasons.append("poor liquidity → 0.50")

        # Off session → reduce
        if inp.session == "OFF":
            mult = min(mult, 0.50)
            reasons.append("off session → 0.50")

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
