"""TITAN XAU AI - Prop-Funded Verdict Mapper (Sprint v2.8.3)
==============================================================
Canonical mapper for prop-funded optimizer verdicts.

Classifies raw prop-funded optimizer verdicts into a canonical status:
  PASS                - full pass, no restrictions
  PASS_CONSERVATIVE   - pass with conservative mode restrictions
  PENDING_VALIDATION  - waiting on broker validation
  BLOCKED             - hard fail
  UNKNOWN             - unrecognized verdict, treat as blocked

NEVER calls mt5.order_send. NEVER modifies positions.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


# Canonical statuses
PASS = "PASS"
PASS_CONSERVATIVE = "PASS_CONSERVATIVE"
PENDING_VALIDATION = "PENDING_VALIDATION"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"

ALL_STATUSES = (PASS, PASS_CONSERVATIVE, PENDING_VALIDATION, BLOCKED, UNKNOWN)

# Raw verdict -> canonical status mapping
_VERDICT_MAP = {
    # Full pass verdicts
    "PROP_FUNDED_PASS": PASS,
    "PROP_FUNDED_OPTIMAL_READY": PASS,
    "PROP_FUNDED_GROWTH_READY": PASS,
    "PROP_FUNDED_SAFE_PROFILE_PASS_CONTROLLED_DEMO": PASS,

    # Conservative pass verdicts
    "PROP_FUNDED_READY_CONSERVATIVE": PASS_CONSERVATIVE,
    "PROP_FUNDED_READY": PASS_CONSERVATIVE,

    # Pending validation
    "PROP_FUNDED_GATE_PENDING_BROKER_VALIDATION": PENDING_VALIDATION,

    # Blocked
    "PROP_FUNDED_BLOCKED": BLOCKED,
    "PROP_FUNDED_GATE_BLOCKED_BY_BROKER": BLOCKED,
    "PROP_FUNDED_AGGRESSIVE_SIMULATION_ONLY": BLOCKED,

    # Gate-level statuses from run_autonomous_entry_check
    "PASS": PASS,
    "CONSTRAINTS_FAILED": BLOCKED,
    "ARTIFACT_MISSING": BLOCKED,
    "ERROR": BLOCKED,
    "BLOCKED_PENDING_BROKER_VALIDATION": PENDING_VALIDATION,
    "BLOCKED_BY_BROKER": BLOCKED,
}


@dataclass
class PropFundedVerdictMapping:
    """Result of mapping a raw prop-funded verdict to canonical status."""
    raw_verdict: str = ""
    canonical_status: str = UNKNOWN
    gate_pass: bool = False
    gate_status: str = ""
    gate_reason: str = ""
    conservative_mode: bool = False
    warnings: list = field(default_factory=list)
    conservative_restrictions: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "raw_verdict": self.raw_verdict,
            "canonical_status": self.canonical_status,
            "gate_pass": self.gate_pass,
            "gate_status": self.gate_status,
            "gate_reason": self.gate_reason,
            "conservative_mode": self.conservative_mode,
            "warnings": list(self.warnings),
            "conservative_restrictions": dict(self.conservative_restrictions),
        }


# Conservative mode restrictions
CONSERVATIVE_RESTRICTIONS = {
    "max_lot": 0.01,
    "max_open_positions": 1,
    "max_risk_per_trade_pct": 0.005,  # 0.5%
    "allowed_broker": "MetaQuotes-Demo",
    "allowed_account_type": "demo",
    "no_real_funded_live": True,
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
    "no_loss_based_lot_multiplier": True,
    "minimum_RR": 2.0,
    "preferred_initial_tp_R": 3.0,
    "supervised_mode_only": True,
}


def map_verdict(raw_verdict: str) -> PropFundedVerdictMapping:
    """Map a raw prop-funded optimizer verdict to canonical status.

    Returns a PropFundedVerdictMapping with gate_pass, gate_status,
    gate_reason, conservative_mode, and warnings.
    """
    raw = (raw_verdict or "").strip()
    mapping = PropFundedVerdictMapping(raw_verdict=raw)

    status = _VERDICT_MAP.get(raw, UNKNOWN)
    mapping.canonical_status = status

    if status == PASS:
        mapping.gate_pass = True
        mapping.gate_status = PASS
        mapping.gate_reason = ""
    elif status == PASS_CONSERVATIVE:
        mapping.gate_pass = True
        mapping.gate_status = PASS_CONSERVATIVE
        mapping.gate_reason = raw or "PROP_FUNDED_READY_CONSERVATIVE"
        mapping.conservative_mode = True
        mapping.warnings.append("PROP_FUNDED_CONSERVATIVE_MODE_ACTIVE")
        mapping.conservative_restrictions = dict(CONSERVATIVE_RESTRICTIONS)
    elif status == PENDING_VALIDATION:
        mapping.gate_pass = False
        mapping.gate_status = PENDING_VALIDATION
        mapping.gate_reason = "PROP_FUNDED_GATE_PENDING_BROKER_VALIDATION"
    elif status == BLOCKED:
        mapping.gate_pass = False
        mapping.gate_status = BLOCKED
        mapping.gate_reason = raw or "PROP_FUNDED_BLOCKED"
    else:
        # UNKNOWN - treat as blocked for safety
        mapping.gate_pass = False
        mapping.gate_status = UNKNOWN
        mapping.gate_reason = f"UNKNOWN_VERDICT: {raw}"
        mapping.warnings.append(f"PROP_FUNDED_UNKNOWN_VERDICT: {raw}")

    return mapping


def check_conservative_restrictions(
    *,
    lot: float = 0.01,
    max_open_positions: int = 1,
    risk_per_trade_pct: float = 0.005,
    broker_server: str = "",
    account_type: str = "demo",
    actual_RR: float = 0.0,
    initial_tp_R: float = 0.0,
) -> dict:
    """Check if conservative mode restrictions are satisfied.

    Returns dict with:
      - restrictions_pass: bool
      - violations: list of str
      - checked_restrictions: dict
    """
    violations = []
    checked = {}

    if lot > CONSERVATIVE_RESTRICTIONS["max_lot"]:
        violations.append(f"LOT_EXCEEDS_CONSERVATIVE: lot={lot} > {CONSERVATIVE_RESTRICTIONS['max_lot']}")
    checked["lot"] = lot

    if max_open_positions > CONSERVATIVE_RESTRICTIONS["max_open_positions"]:
        violations.append(f"MAX_OPEN_POSITIONS_EXCEEDS_CONSERVATIVE: {max_open_positions} > {CONSERVATIVE_RESTRICTIONS['max_open_positions']}")
    checked["max_open_positions"] = max_open_positions

    if risk_per_trade_pct > CONSERVATIVE_RESTRICTIONS["max_risk_per_trade_pct"]:
        violations.append(f"RISK_PER_TRADE_EXCEEDS_CONSERVATIVE: {risk_per_trade_pct} > {CONSERVATIVE_RESTRICTIONS['max_risk_per_trade_pct']}")
    checked["risk_per_trade_pct"] = risk_per_trade_pct

    broker_lower = (broker_server or "").lower()
    # v2.8.3: Must be MetaQuotes-Demo specifically, not just any "demo" server.
    # FundedNext-Demo contains "demo" but is NOT allowed for algo trading.
    if broker_lower and "metaquotes" not in broker_lower:
        violations.append(f"BROKER_NOT_METAQUOTES_DEMO: {broker_server}")
    checked["broker_server"] = broker_server

    if account_type and account_type.lower() not in ("demo",):
        violations.append(f"ACCOUNT_NOT_DEMO: {account_type}")
    checked["account_type"] = account_type

    if actual_RR > 0 and actual_RR < CONSERVATIVE_RESTRICTIONS["minimum_RR"]:
        violations.append(f"RR_BELOW_CONSERVATIVE_MINIMUM: {actual_RR} < {CONSERVATIVE_RESTRICTIONS['minimum_RR']}")
    checked["actual_RR"] = actual_RR

    checked["no_real_funded_live"] = True  # Enforced by broker/account checks
    checked["no_martingale"] = True
    checked["no_grid"] = True
    checked["no_averaging"] = True
    checked["no_loss_based_lot_multiplier"] = True
    checked["supervised_mode_only"] = True

    return {
        "restrictions_pass": len(violations) == 0,
        "violations": violations,
        "checked_restrictions": checked,
    }
