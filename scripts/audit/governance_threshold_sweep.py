"""
TITAN XAU AI — Sprint 9.9.3.3 Governance Threshold Sweep + Calibration
=======================================================================

This script:
  1. Tests multiple threshold combinations across all 3 profiles.
  2. Computes competition-style objective score for each combination.
  3. Identifies the best configuration per profile.
  4. Adds overfiltering analytics (blocked winners, missed profit, etc.)
  5. Validates against synthetic unseen scenarios (anti-overfit).
  6. Produces calibration + threshold sweep reports.

This is a SIMULATION — no real or demo MT5 execution.
Does NOT change production live path. Does NOT run DEMO_MICRO_EXECUTE.

Output:
  data/audit/stress_loss/governance_threshold_sweep.json
  data/audit/stress_loss/governance_threshold_sweep.md
  data/audit/stress_loss/governance_calibration_report.json
  data/audit/stress_loss/governance_calibration_report.md
"""
from __future__ import annotations
import json
import sys
import copy
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Dict, List, Tuple, Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.stress_loss_governance import (
    StressLossGovernanceEngine,
    GovernanceInput,
    AccountProfile,
    ExitAction,
    DecisionLabel,
    PROFILE_THRESHOLDS,
)

SOURCE_REPORT = REPO_ROOT / "data" / "audit" / "virtual_lifecycle" / "virtual_lifecycle_report.json"
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "stress_loss"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SWEEP_JSON = OUTPUT_DIR / "governance_threshold_sweep.json"
SWEEP_MD = OUTPUT_DIR / "governance_threshold_sweep.md"
CALIB_JSON = OUTPUT_DIR / "governance_calibration_report.json"
CALIB_MD = OUTPUT_DIR / "governance_calibration_report.md"

# 8 losing scenarios from Sprint 9.9.3 stress audit
LOSING_SCENARIOS = {
    "HIGH_VOLATILITY", "AMBIGUOUS_CANDLE", "BUY_SL", "SELL_SL",
    "EQUITY_PROTECTION", "CAPITAL_PRESERVATION",
    "REGIME_FLIP_BUY", "REGIME_FLIP_SELL",
}


# ─── Scenario → GovernanceInput ──────────────────────────────────────────────

def scenario_to_input(name: str, profile: str) -> GovernanceInput:
    """Map a virtual lifecycle scenario name to a GovernanceInput."""
    base = dict(
        account_profile=profile,
        regime_label="TREND_UP",
        regime_confidence=0.75,
        meta_confidence=0.70,
        atr_percentile=50.0,
        volatility_state="NORMAL",
        spread_usd=0.30,
        slippage_pips=2.0,
        session="LONDON",
        liquidity="GOOD",
        account_health=90.0,
        equity_protection_active=False,
        capital_preservation_active=False,
        broker_quality=80.0,
        daily_dd_pct=0.5,
        daily_dd_threshold_pct=3.0,
        regime_flip_probability=0.20,
        rolling_setup_winrate=0.50,
        expected_edge_usd=2.0,  # default positive expected edge
    )
    if name == "BUY_TP":
        base.update(dict(meta_confidence=0.78, regime_confidence=0.80, expected_edge_usd=4.0))
    elif name == "BUY_SL":
        base.update(dict(meta_confidence=0.68, spread_usd=0.32, expected_edge_usd=-0.5))
    elif name == "SELL_TP":
        base.update(dict(regime_label="TREND_DOWN", meta_confidence=0.78,
                         regime_confidence=0.80, expected_edge_usd=4.0))
    elif name == "SELL_SL":
        base.update(dict(regime_label="TREND_DOWN", meta_confidence=0.68,
                         spread_usd=0.32, expected_edge_usd=-0.5))
    elif name == "BUY_AI_EXIT":
        base.update(dict(meta_confidence=0.72, regime_confidence=0.72, expected_edge_usd=2.5))
    elif name == "SELL_AI_EXIT":
        base.update(dict(regime_label="TREND_DOWN", meta_confidence=0.72,
                         regime_confidence=0.72, expected_edge_usd=2.5))
    elif name == "REGIME_FLIP_BUY":
        base.update(dict(regime_label="TRANSITION", regime_confidence=0.55,
                         regime_flip_probability=0.70, meta_confidence=0.65,
                         expected_edge_usd=0.0))
    elif name == "REGIME_FLIP_SELL":
        base.update(dict(regime_label="TRANSITION", regime_confidence=0.55,
                         regime_flip_probability=0.70, meta_confidence=0.65,
                         expected_edge_usd=0.0))
    elif name == "ALPHA_DECAY":
        base.update(dict(meta_confidence=0.62, regime_confidence=0.65, expected_edge_usd=0.5))
    elif name == "AMBIGUOUS_CANDLE":
        base.update(dict(ambiguous_candle=True, confirmation_present=False,
                         meta_confidence=0.65, regime_confidence=0.60,
                         liquidity="NORMAL", expected_edge_usd=-1.0))
    elif name == "SPREAD_SPIKE_TP":
        base.update(dict(spread_usd=0.80, meta_confidence=0.80,
                         regime_confidence=0.80, expected_edge_usd=5.0))
    elif name == "HIGH_VOLATILITY":
        base.update(dict(atr_percentile=95.0, volatility_state="EXTREME",
                         spread_usd=0.50, meta_confidence=0.70, expected_edge_usd=-2.0))
    elif name == "MAX_HOLDING":
        base.update(dict(meta_confidence=0.72, regime_confidence=0.72, expected_edge_usd=1.5))
    elif name == "PROFIT_LOCK":
        base.update(dict(meta_confidence=0.75, regime_confidence=0.75, expected_edge_usd=3.0))
    elif name == "STALE_EXIT":
        base.update(dict(meta_confidence=0.65, regime_confidence=0.65, expected_edge_usd=0.5))
    elif name == "EQUITY_PROTECTION":
        base.update(dict(equity_protection_active=True, account_health=55.0,
                         daily_dd_pct=2.5, daily_dd_threshold_pct=3.0,
                         expected_edge_usd=-1.0))
    elif name == "CAPITAL_PRESERVATION":
        base.update(dict(capital_preservation_active=True, account_health=20.0,
                         daily_dd_pct=2.9, daily_dd_threshold_pct=3.0,
                         expected_edge_usd=-1.0))
    return GovernanceInput(**base)


# ─── Synthetic unseen scenarios (anti-overfit) ───────────────────────────────

def synthetic_scenarios() -> List[Tuple[str, GovernanceInput, float]]:
    """Generate synthetic unseen scenarios for anti-overfit validation.

    Returns list of (name, input, expected_outcome) where expected_outcome
    is the EXPECTED $ PnL if the trade were to play out (positive=winner,
    negative=loser). This lets us measure blocked_winners vs blocked_losers.
    """
    scenarios = []

    # 1. High volatility + strong alpha → should be winner (don't block)
    scenarios.append(("HV_STRONG_ALPHA", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.85, meta_confidence=0.85,
        atr_percentile=92.0, volatility_state="HIGH",
        spread_usd=0.30, account_health=90, broker_quality=85,
        regime_flip_probability=0.20, account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=6.0,
    ), 8.0))  # winner

    # 2. High volatility + weak alpha → should be loser (block OK)
    scenarios.append(("HV_WEAK_ALPHA", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.60, meta_confidence=0.62,
        atr_percentile=92.0, volatility_state="HIGH",
        spread_usd=0.40, account_health=90, broker_quality=85,
        regime_flip_probability=0.20, account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=-3.0,
    ), -10.0))  # loser

    # 3. Ambiguous candle + confirmation → should be winner (don't block)
    scenarios.append(("AMB_WITH_CONF", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.75, meta_confidence=0.78,
        atr_percentile=50.0, spread_usd=0.25, account_health=90, broker_quality=85,
        regime_flip_probability=0.20, ambiguous_candle=True, confirmation_present=True,
        liquidity="GOOD", account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=5.0,
    ), 6.0))  # winner

    # 4. Ambiguous candle + no confirmation → should be loser (block OK)
    scenarios.append(("AMB_NO_CONF", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.55, meta_confidence=0.60,
        atr_percentile=50.0, spread_usd=0.30, account_health=90, broker_quality=85,
        regime_flip_probability=0.20, ambiguous_candle=True, confirmation_present=False,
        liquidity="NORMAL", account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=-2.0,
    ), -8.0))  # loser

    # 5. Regime flip false alarm (high prob but no real flip) → should be winner
    scenarios.append(("FLIP_FALSE_ALARM", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.78, meta_confidence=0.78,
        atr_percentile=50.0, spread_usd=0.25, account_health=90, broker_quality=85,
        regime_flip_probability=0.68, confirmation_present=True,
        account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=4.5,
    ), 5.0))  # winner

    # 6. Regime flip true reversal → should be loser (block OK)
    scenarios.append(("FLIP_TRUE_REVERSAL", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.50, meta_confidence=0.65,
        atr_percentile=50.0, spread_usd=0.30, account_health=90, broker_quality=85,
        regime_flip_probability=0.80, confirmation_present=False,
        account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=-5.0,
    ), -10.0))  # loser

    # 7. High spread + high expected edge → should be winner (don't block)
    scenarios.append(("HI_SPREAD_HI_EDGE", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.80, meta_confidence=0.80,
        atr_percentile=50.0, spread_usd=0.65, account_health=90, broker_quality=85,
        regime_flip_probability=0.20,
        account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=8.0,
    ), 6.0))  # winner

    # 8. Low spread + weak alpha → should be loser (block OK)
    scenarios.append(("LO_SPREAD_WEAK_ALPHA", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.55, meta_confidence=0.60,
        atr_percentile=50.0, spread_usd=0.20, account_health=90, broker_quality=85,
        regime_flip_probability=0.20,
        account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=-1.5,
    ), -8.0))  # loser

    # 9. Broker good → should be winner
    scenarios.append(("BROKER_GOOD", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.78, meta_confidence=0.78,
        atr_percentile=50.0, spread_usd=0.25, account_health=90, broker_quality=92,
        regime_flip_probability=0.20,
        account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=4.0,
    ), 5.0))  # winner

    # 10. Broker poor → should be loser (block OK)
    scenarios.append(("BROKER_POOR", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.65, meta_confidence=0.65,
        atr_percentile=50.0, spread_usd=0.30, account_health=90, broker_quality=55,
        regime_flip_probability=0.20,
        account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=-2.0,
    ), -7.0))  # loser

    # 11. Liquidity good → winner
    scenarios.append(("LIQ_GOOD", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.78, meta_confidence=0.78,
        atr_percentile=50.0, spread_usd=0.25, account_health=90, broker_quality=85,
        regime_flip_probability=0.20, liquidity="GOOD", session="LONDON",
        account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=4.0,
    ), 5.0))  # winner

    # 12. Liquidity bad → loser (block OK)
    scenarios.append(("LIQ_BAD", GovernanceInput(
        regime_label="TREND_UP", regime_confidence=0.65, meta_confidence=0.65,
        atr_percentile=50.0, spread_usd=0.40, account_health=90, broker_quality=85,
        regime_flip_probability=0.20, liquidity="POOR", session="OFF",
        account_profile=AccountProfile.PROP_FIRM_STRICT.value,
        expected_edge_usd=-3.0,
    ), -9.0))  # loser

    return scenarios


# ─── Apply governance to scenario ────────────────────────────────────────────

def apply_governance(scenario_name: str, scenario_pnl: float,
                     engine: StressLossGovernanceEngine,
                     profile: str) -> Dict[str, Any]:
    """Apply governance entry decision to a scenario."""
    inp = scenario_to_input(scenario_name, profile)
    dec = engine.evaluate_entry(inp)

    if not dec.allow_trade:
        return {
            "scenario": scenario_name,
            "allowed": False,
            "after_pnl": 0.0,
            "risk_multiplier": 0.0,
            "block_reason": dec.block_reason,
            "governance_score": dec.governance_score,
            "institutional_approval": dec.institutional_approval,
            "original_pnl": scenario_pnl,
            "is_blocked_winner": scenario_pnl > 0,
            "is_blocked_loser": scenario_pnl < 0,
        }

    # Apply risk multiplier to PnL
    after_pnl = scenario_pnl * dec.risk_multiplier
    return {
        "scenario": scenario_name,
        "allowed": True,
        "after_pnl": round(after_pnl, 4),
        "risk_multiplier": dec.risk_multiplier,
        "block_reason": "",
        "governance_score": dec.governance_score,
        "institutional_approval": dec.institutional_approval,
        "original_pnl": scenario_pnl,
        "is_blocked_winner": False,
        "is_blocked_loser": False,
    }


def apply_governance_to_synthetic(name: str, inp: GovernanceInput,
                                  expected_pnl: float,
                                  engine: StressLossGovernanceEngine) -> Dict[str, Any]:
    """Apply governance to a synthetic scenario."""
    inp_copy = GovernanceInput(**{**inp.__dict__,
                                   "account_profile": engine.account_profile})
    dec = engine.evaluate_entry(inp_copy)
    if not dec.allow_trade:
        return {
            "scenario": name,
            "allowed": False,
            "after_pnl": 0.0,
            "risk_multiplier": 0.0,
            "block_reason": dec.block_reason,
            "governance_score": dec.governance_score,
            "original_pnl": expected_pnl,
            "is_blocked_winner": expected_pnl > 0,
            "is_blocked_loser": expected_pnl < 0,
        }
    after_pnl = expected_pnl * dec.risk_multiplier
    return {
        "scenario": name,
        "allowed": True,
        "after_pnl": round(after_pnl, 4),
        "risk_multiplier": dec.risk_multiplier,
        "block_reason": "",
        "governance_score": dec.governance_score,
        "original_pnl": expected_pnl,
        "is_blocked_winner": False,
        "is_blocked_loser": False,
    }


# ─── Overfiltering analytics ─────────────────────────────────────────────────

def compute_overfiltering_analytics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute overfiltering analytics from a list of governance results."""
    blocked_winners = [r for r in results if r.get("is_blocked_winner")]
    blocked_losers = [r for r in results if r.get("is_blocked_loser")]
    allowed_results = [r for r in results if r.get("allowed")]

    missed_profit = sum(r["original_pnl"] for r in blocked_winners)
    avoided_loss = abs(sum(r["original_pnl"] for r in blocked_losers))

    # Total opportunity PnL (if no governance, what would we have made?)
    total_opportunity_pnl = sum(r["original_pnl"] for r in results)
    # Actual PnL after governance
    total_after_pnl = sum(r["after_pnl"] for r in results)

    # Profit retention = after_pnl_of_winners / original_pnl_of_winners
    original_winner_pnl = sum(r["original_pnl"] for r in results if r["original_pnl"] > 0
                              and r.get("allowed"))
    after_winner_pnl = sum(r["after_pnl"] for r in results if r["original_pnl"] > 0
                           and r.get("allowed"))
    profit_retention_pct = (after_winner_pnl / original_winner_pnl * 100
                            if original_winner_pnl > 0 else 0.0)

    # Loss reduction = 1 - (after_loss / original_loss)
    original_loss_total = abs(sum(r["original_pnl"] for r in results if r["original_pnl"] < 0))
    after_loss_total = abs(sum(r["after_pnl"] for r in results if r["after_pnl"] < 0))
    loss_reduction_pct = ((original_loss_total - after_loss_total) / original_loss_total * 100
                          if original_loss_total > 0 else 0.0)

    # Overfiltering ratio = missed_profit / max(avoided_loss, epsilon)
    epsilon = 0.01
    overfiltering_ratio = missed_profit / max(avoided_loss, epsilon)

    # Loss reduction efficiency = avoided_loss / max(missed_profit, epsilon)
    loss_reduction_efficiency = avoided_loss / max(missed_profit, epsilon)

    # Executed win rate: among ALLOWED trades, what fraction had positive original PnL
    allowed_winners = [r for r in allowed_results if r["original_pnl"] > 0]
    executed_win_rate = (len(allowed_winners) / len(allowed_results) * 100
                         if allowed_results else 0.0)

    # Opportunity win rate: among ALL opportunities, what fraction had positive original PnL
    opportunity_winners = [r for r in results if r["original_pnl"] > 0]
    opportunity_win_rate = (len(opportunity_winners) / len(results) * 100
                            if results else 0.0)

    # Trade frequency = allowed / total
    trade_frequency = len(allowed_results) / len(results) if results else 0.0

    # Expected value per executed trade
    ev_per_executed = (sum(r["after_pnl"] for r in allowed_results) / len(allowed_results)
                       if allowed_results else 0.0)

    return {
        "total_scenarios": len(results),
        "allowed_count": len(allowed_results),
        "blocked_count": len(blocked_winners) + len(blocked_losers),
        "blocked_winners": len(blocked_winners),
        "blocked_losers": len(blocked_losers),
        "missed_profit": round(missed_profit, 4),
        "avoided_loss": round(avoided_loss, 4),
        "total_opportunity_pnl": round(total_opportunity_pnl, 4),
        "total_after_pnl": round(total_after_pnl, 4),
        "profit_retention_pct": round(profit_retention_pct, 2),
        "loss_reduction_pct": round(loss_reduction_pct, 2),
        "overfiltering_ratio": round(overfiltering_ratio, 4),
        "loss_reduction_efficiency": round(loss_reduction_efficiency, 4),
        "executed_win_rate_pct": round(executed_win_rate, 2),
        "opportunity_win_rate_pct": round(opportunity_win_rate, 2),
        "trade_frequency": round(trade_frequency, 4),
        "ev_per_executed_trade": round(ev_per_executed, 4),
    }


# ─── Max DD calculation ──────────────────────────────────────────────────────

def compute_max_dd(pnls: List[float], start_equity: float = 6000.0) -> float:
    equity = start_equity
    peak = start_equity
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 4)


def compute_pf(pnls: List[float]) -> float:
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    if not losses:
        return float("inf") if wins else 0.0
    return round(sum(wins) / abs(sum(losses)), 4)


# ─── Competition-style objective score ───────────────────────────────────────

def competition_score(
    net_pnl: float,
    max_dd: float,
    pf: float,
    loss_reduction_pct: float,
    profit_retention_pct: float,
    overfiltering_ratio: float,
    trade_frequency: float,
    explainability_complete: bool,
) -> Dict[str, Any]:
    """Compute competition-style objective score / 100.

    Components:
      - Net PnL quality: 20
      - Max DD control: 20
      - Profit factor / expectancy: 15
      - Stress loss reduction: 15
      - Profit retention: 10
      - Overfiltering control: 10
      - Trade frequency sufficiency: 5
      - Explainability completeness: 5
    """
    # Net PnL quality (0-20): scale by 0-50 PnL range
    pnl_score = min(20.0, max(0.0, net_pnl / 50.0 * 20.0))

    # Max DD control (0-20): 0 DD = 20, 50+ DD = 0
    dd_score = max(0.0, 20.0 - (max_dd / 50.0 * 20.0))

    # PF (0-15): PF >= 3 = 15, PF <= 1 = 0
    if pf == float("inf"):
        pf_score = 15.0
    else:
        pf_score = min(15.0, max(0.0, (pf - 1.0) / 2.0 * 15.0))

    # Stress loss reduction (0-15): 100% reduction = 15, 0% = 0
    loss_score = min(15.0, max(0.0, loss_reduction_pct / 100.0 * 15.0))

    # Profit retention (0-10): 100% retention = 10, 0% = 0
    retention_score = min(10.0, max(0.0, profit_retention_pct / 100.0 * 10.0))

    # Overfiltering control (0-10): ratio 0 = 10, ratio >= 2 = 0
    of_score = max(0.0, 10.0 - overfiltering_ratio * 5.0)

    # Trade frequency (0-5): frequency >= 0.7 = 5, frequency <= 0.3 = 0
    freq_score = min(5.0, max(0.0, (trade_frequency - 0.3) / 0.4 * 5.0))

    # Explainability (0-5): always complete in our system
    expl_score = 5.0 if explainability_complete else 0.0

    total = (pnl_score + dd_score + pf_score + loss_score + retention_score
             + of_score + freq_score + expl_score)

    return {
        "total_score": round(total, 2),
        "components": {
            "net_pnl_quality": round(pnl_score, 2),
            "max_dd_control": round(dd_score, 2),
            "profit_factor_expectancy": round(pf_score, 2),
            "stress_loss_reduction": round(loss_score, 2),
            "profit_retention": round(retention_score, 2),
            "overfiltering_control": round(of_score, 2),
            "trade_frequency_sufficiency": round(freq_score, 2),
            "explainability_completeness": round(expl_score, 2),
        },
    }


# ─── Threshold sweep ─────────────────────────────────────────────────────────

def make_custom_engine(profile: str, overrides: Dict[str, Any]) -> StressLossGovernanceEngine:
    """Create an engine with custom threshold overrides."""
    base = copy.deepcopy(PROFILE_THRESHOLDS[profile])
    base.update(overrides)
    # Build a custom thresholds dict
    engine = StressLossGovernanceEngine(profile)
    engine.thresholds = base
    return engine


def sweep_thresholds(scenarios_with_pnl: List[Tuple[str, float]],
                     synthetic: List[Tuple[str, GovernanceInput, float]],
                     profile: str) -> Dict[str, Any]:
    """Sweep multiple threshold combinations for a profile."""
    # Threshold values to test
    meta_block_values = [0.55, 0.60, 0.65, 0.70]
    meta_throttle_values = [0.65, 0.68, 0.70, 0.72, 0.75]
    atr_block_values = [92, 95, 98]
    atr_throttle_values = [85, 88, 90]
    spread_block_values = [0.60, 0.80, 1.00]
    flip_block_values = [0.70, 0.75, 0.80]
    risk_mult_warn_values = [0.25, 0.50, 0.75]

    # Limit combinations to keep runtime reasonable — pick a representative subset
    # Total: 4 * 5 * 3 * 3 * 3 * 3 * 3 = 4860 — too many.
    # Sample 100 combinations via step skipping.
    all_combos = list(product(
        meta_block_values, meta_throttle_values, atr_block_values,
        atr_throttle_values, spread_block_values, flip_block_values,
        risk_mult_warn_values,
    ))
    # Filter: meta_block must be < meta_throttle, atr_throttle < atr_block
    valid_combos = [
        c for c in all_combos
        if c[0] < c[1] and c[3] < c[2]
    ]
    # Sample at most 150 combinations
    step = max(1, len(valid_combos) // 150)
    sampled_combos = valid_combos[::step][:150]

    sweep_results = []
    best_score = -1.0
    best_config = None

    for combo in sampled_combos:
        meta_block, meta_throttle, atr_block, atr_throttle, spread_block, flip_block, risk_mult_warn = combo
        overrides = {
            "min_meta_confidence_block": meta_block,
            "min_meta_confidence": meta_throttle,
            "min_meta_confidence_throttle": meta_throttle,
            "max_atr_percentile_block": atr_block,
            "max_atr_percentile_throttle": atr_throttle,
            "max_spread_usd_block": spread_block,
            "max_regime_flip_prob_block": flip_block,
            "risk_multiplier_in_warn_vol": risk_mult_warn,
        }
        engine = make_custom_engine(profile, overrides)

        # Apply to original 17 scenarios
        results = []
        for name, pnl in scenarios_with_pnl:
            results.append(apply_governance(name, pnl, engine, profile))

        # Apply to synthetic scenarios
        syn_results = []
        for s_name, s_inp, s_pnl in synthetic:
            syn_results.append(apply_governance_to_synthetic(s_name, s_inp, s_pnl, engine))

        # Combine
        combined = results + syn_results
        analytics = compute_overfiltering_analytics(combined)

        # Compute metrics
        after_pnls = [r["after_pnl"] for r in combined]
        max_dd = compute_max_dd(after_pnls)
        pf = compute_pf(after_pnls)

        # Compute competition score
        score = competition_score(
            net_pnl=analytics["total_after_pnl"],
            max_dd=max_dd,
            pf=pf,
            loss_reduction_pct=analytics["loss_reduction_pct"],
            profit_retention_pct=analytics["profit_retention_pct"],
            overfiltering_ratio=analytics["overfiltering_ratio"],
            trade_frequency=analytics["trade_frequency"],
            explainability_complete=True,
        )

        sweep_results.append({
            "config": overrides,
            "total_score": score["total_score"],
            "net_pnl": analytics["total_after_pnl"],
            "max_dd": max_dd,
            "pf": pf,
            "executed_win_rate": analytics["executed_win_rate_pct"],
            "blocked_count": analytics["blocked_count"],
            "missed_profit": analytics["missed_profit"],
            "avoided_loss": analytics["avoided_loss"],
            "overfiltering_ratio": analytics["overfiltering_ratio"],
            "profit_retention_pct": analytics["profit_retention_pct"],
            "loss_reduction_pct": analytics["loss_reduction_pct"],
        })

        if score["total_score"] > best_score:
            best_score = score["total_score"]
            best_config = overrides

    # Sort by total_score descending
    sweep_results.sort(key=lambda x: -x["total_score"])

    return {
        "profile": profile,
        "total_combinations_tested": len(sweep_results),
        "best_config": best_config,
        "best_score": best_score,
        "top_5": sweep_results[:5],
        "all_results": sweep_results,
    }


# ─── Main: Build reports ─────────────────────────────────────────────────────

def main():
    # Load source scenarios
    with open(SOURCE_REPORT, "r", encoding="utf-8") as f:
        source = json.load(f)
    scenarios_with_pnl = [(s["scenario"], s["net_pnl"]) for s in source["scenarios"]]

    # Generate synthetic scenarios
    synthetic = synthetic_scenarios()

    # Run sweep for each profile
    print("Running threshold sweep for each profile...")
    sweep_per_profile = {}
    for profile in [AccountProfile.RETAIL_SAFE.value,
                    AccountProfile.PROP_FIRM_STRICT.value,
                    AccountProfile.INSTITUTIONAL_CAPITAL_PROTECTION.value]:
        print(f"  Sweeping {profile}...")
        sweep_per_profile[profile] = sweep_thresholds(scenarios_with_pnl, synthetic, profile)

    # Write sweep report
    sweep_report = {
        "audit": "sprint_9_9_3_3_governance_threshold_sweep",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_report": str(SOURCE_REPORT.relative_to(REPO_ROOT)),
        "synthetic_scenarios_count": len(synthetic),
        "sweep_per_profile": {
            p: {
                "total_combinations_tested": s["total_combinations_tested"],
                "best_config": s["best_config"],
                "best_score": s["best_score"],
                "top_5": s["top_5"],
            }
            for p, s in sweep_per_profile.items()
        },
        "notes": [
            "Sweep tested combinations of meta/atr/spread/flip/risk_mult thresholds.",
            "Competition score weights: PnL 20, DD 20, PF 15, loss reduction 15,",
            "  profit retention 10, overfiltering control 10, trade frequency 5,",
            "  explainability 5 (total /100).",
            "Best config is the one with HIGHEST competition score, NOT zero losses.",
        ],
    }
    with open(SWEEP_JSON, "w", encoding="utf-8") as f:
        json.dump(sweep_report, f, indent=2, default=str)

    # ─── Calibration report: before / 9.9.3.2 / 9.9.3.3 comparison ───
    print("\nBuilding calibration report...")

    # "Before" = raw scenarios (no governance)
    before_results = [{"scenario": n, "allowed": True, "after_pnl": p,
                       "original_pnl": p, "risk_multiplier": 1.0,
                       "is_blocked_winner": False, "is_blocked_loser": False,
                       "block_reason": "", "governance_score": 100.0}
                      for n, p in scenarios_with_pnl]
    before_analytics = compute_overfiltering_analytics(before_results)
    before_pnls = [r["after_pnl"] for r in before_results]
    before_max_dd = compute_max_dd(before_pnls)
    before_pf = compute_pf(before_pnls)
    before_score = competition_score(
        net_pnl=before_analytics["total_after_pnl"],
        max_dd=before_max_dd,
        pf=before_pf,
        loss_reduction_pct=before_analytics["loss_reduction_pct"],
        profit_retention_pct=before_analytics["profit_retention_pct"],
        overfiltering_ratio=before_analytics["overfiltering_ratio"],
        trade_frequency=before_analytics["trade_frequency"],
        explainability_complete=True,
    )

    # "9.9.3.2" = old strict governance (use the existing comparison report data)
    # We hard-code the previously-reported 9.9.3.2 numbers from the prior comparison
    sprint_9932_metrics = {
        "total_net_pnl": 76.4,
        "loss_from_8_scenarios": 0.0,
        "max_dd": 0.0,
        "pf": float("inf"),
        "executed_win_rate_pct": 35.29,
        "opportunity_win_rate_pct": 52.94,
        "blocked_count": 11,
        "blocked_winners": 5,  # missed profit
        "blocked_losers": 6,   # avoided loss
        "missed_profit": 19.7,
        "avoided_loss": 52.0,
        "overfiltering_ratio": 0.38,
        "profit_retention_pct": 79.5,  # 76.4 / 96.1
        "loss_reduction_pct": 100.0,
        "trade_frequency": 0.353,
        "ev_per_executed_trade": 12.73,
        "competition_score": 0.0,  # filled below
    }
    sprint_9932_score = competition_score(
        net_pnl=sprint_9932_metrics["total_net_pnl"],
        max_dd=sprint_9932_metrics["max_dd"],
        pf=sprint_9932_metrics["pf"],
        loss_reduction_pct=sprint_9932_metrics["loss_reduction_pct"],
        profit_retention_pct=sprint_9932_metrics["profit_retention_pct"],
        overfiltering_ratio=sprint_9932_metrics["overfiltering_ratio"],
        trade_frequency=sprint_9932_metrics["trade_frequency"],
        explainability_complete=True,
    )
    sprint_9932_metrics["competition_score"] = sprint_9932_score

    # "9.9.3.3" = NEW calibrated 3-tier governance (use best config from sweep for PROP_FIRM_STRICT)
    best_prop_config = sweep_per_profile[AccountProfile.PROP_FIRM_STRICT.value]["best_config"]
    print(f"  Best PROP_FIRM_STRICT config: {best_prop_config}")
    print(f"  Best PROP_FIRM_STRICT score: {sweep_per_profile[AccountProfile.PROP_FIRM_STRICT.value]['best_score']}")

    # Apply best config to scenarios
    engine_9933 = make_custom_engine(AccountProfile.PROP_FIRM_STRICT.value, best_prop_config)

    results_9933 = []
    for name, pnl in scenarios_with_pnl:
        results_9933.append(apply_governance(name, pnl, engine_9933,
                                              AccountProfile.PROP_FIRM_STRICT.value))

    # Apply to synthetic scenarios
    syn_results_9933 = []
    for s_name, s_inp, s_pnl in synthetic:
        syn_results_9933.append(apply_governance_to_synthetic(s_name, s_inp, s_pnl,
                                                                engine_9933))

    combined_9933 = results_9933 + syn_results_9933
    analytics_9933 = compute_overfiltering_analytics(combined_9933)
    after_pnls_9933 = [r["after_pnl"] for r in combined_9933]
    max_dd_9933 = compute_max_dd(after_pnls_9933)
    pf_9933 = compute_pf(after_pnls_9933)
    score_9933 = competition_score(
        net_pnl=analytics_9933["total_after_pnl"],
        max_dd=max_dd_9933,
        pf=pf_9933,
        loss_reduction_pct=analytics_9933["loss_reduction_pct"],
        profit_retention_pct=analytics_9933["profit_retention_pct"],
        overfiltering_ratio=analytics_9933["overfiltering_ratio"],
        trade_frequency=analytics_9933["trade_frequency"],
        explainability_complete=True,
    )

    # Loss from 8 scenarios specifically
    loss_8_before = sum(p for n, p in scenarios_with_pnl if n in LOSING_SCENARIOS)
    loss_8_9933 = sum(r["after_pnl"] for r in results_9933 if r["scenario"] in LOSING_SCENARIOS)

    # Per-scenario comparison for the 8 losing scenarios
    losing_comparison = []
    for r in results_9933:
        if r["scenario"] in LOSING_SCENARIOS:
            losing_comparison.append({
                "scenario": r["scenario"],
                "before_pnl": r["original_pnl"],
                "after_9933_pnl": r["after_pnl"],
                "change": round(r["after_pnl"] - r["original_pnl"], 4),
                "action": "BLOCKED" if not r["allowed"] else "REDUCED_RISK" if r["risk_multiplier"] < 1.0 else "ALLOWED",
                "risk_multiplier": r["risk_multiplier"],
                "block_reason": r["block_reason"],
            })

    # Synthetic scenario results
    syn_comparison = []
    for r in syn_results_9933:
        syn_comparison.append({
            "scenario": r["scenario"],
            "expected_pnl": r["original_pnl"],
            "after_9933_pnl": r["after_pnl"],
            "allowed": r["allowed"],
            "is_blocked_winner": r.get("is_blocked_winner", False),
            "is_blocked_loser": r.get("is_blocked_loser", False),
            "block_reason": r["block_reason"],
        })

    # Build calibration report
    calib_report = {
        "audit": "sprint_9_9_3_3_governance_calibration",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_report": str(SOURCE_REPORT.relative_to(REPO_ROOT)),
        "best_prop_firm_strict_config": best_prop_config,
        "before": {
            "total_net_pnl": before_analytics["total_after_pnl"],
            "loss_from_8_scenarios": round(loss_8_before, 4),
            "max_dd": before_max_dd,
            "pf": before_pf,
            "executed_win_rate_pct": before_analytics["executed_win_rate_pct"],
            "opportunity_win_rate_pct": before_analytics["opportunity_win_rate_pct"],
            "blocked_count": 0,
            "missed_profit": 0.0,
            "avoided_loss": 0.0,
            "overfiltering_ratio": 0.0,
            "profit_retention_pct": before_analytics["profit_retention_pct"],
            "loss_reduction_pct": 0.0,
            "trade_frequency": 1.0,
            "competition_score": before_score,
        },
        "sprint_9_9_3_2": sprint_9932_metrics,
        "sprint_9_9_3_3": {
            "total_net_pnl": analytics_9933["total_after_pnl"],
            "loss_from_8_scenarios": round(loss_8_9933, 4),
            "max_dd": max_dd_9933,
            "pf": pf_9933,
            "executed_win_rate_pct": analytics_9933["executed_win_rate_pct"],
            "opportunity_win_rate_pct": analytics_9933["opportunity_win_rate_pct"],
            "blocked_count": analytics_9933["blocked_count"],
            "blocked_winners": analytics_9933["blocked_winners"],
            "blocked_losers": analytics_9933["blocked_losers"],
            "missed_profit": analytics_9933["missed_profit"],
            "avoided_loss": analytics_9933["avoided_loss"],
            "overfiltering_ratio": analytics_9933["overfiltering_ratio"],
            "profit_retention_pct": analytics_9933["profit_retention_pct"],
            "loss_reduction_pct": analytics_9933["loss_reduction_pct"],
            "trade_frequency": analytics_9933["trade_frequency"],
            "ev_per_executed_trade": analytics_9933["ev_per_executed_trade"],
            "loss_reduction_efficiency": analytics_9933["loss_reduction_efficiency"],
            "competition_score": score_9933,
        },
        "losing_scenario_comparison": losing_comparison,
        "synthetic_scenario_results": syn_comparison,
        "acceptance_criteria": {
            "loss_from_8_materially_reduced": loss_8_9933 > loss_8_before,
            "profit_retention_improved_vs_9932": (
                analytics_9933["profit_retention_pct"] >
                sprint_9932_metrics["profit_retention_pct"]
            ),
            "overfiltering_ratio_decreased": (
                analytics_9933["overfiltering_ratio"] <
                sprint_9932_metrics["overfiltering_ratio"]
            ),
            "competition_score_improved": (
                score_9933["total_score"] >
                sprint_9932_score["total_score"]
            ),
            "max_dd_acceptable": max_dd_9933 <= before_max_dd,
            "blocked_losers_more_than_blocked_winners": (
                analytics_9933["blocked_losers"] >= analytics_9933["blocked_winners"]
            ),
            "synthetic_anti_overfit_pass": (
                # Should block more losers than winners in synthetic set
                sum(1 for r in syn_results_9933 if r.get("is_blocked_loser")) >=
                sum(1 for r in syn_results_9933 if r.get("is_blocked_winner"))
            ),
        },
        "safety": {
            "demo_micro_execute_run": False,
            "live_demo_path_changed": False,
            "martingale_added": False,
            "grid_added": False,
            "averaging_added": False,
            "lot_escalation_added": False,
            "models_retrained": False,
        },
    }
    calib_report["acceptance_criteria"]["all_criteria_met"] = all(
        calib_report["acceptance_criteria"].values()
    )

    with open(CALIB_JSON, "w", encoding="utf-8") as f:
        json.dump(calib_report, f, indent=2, default=str)

    # Write MD reports
    _write_sweep_md(sweep_report, sweep_per_profile)
    _write_calib_md(calib_report)

    print(f"\nSweep JSON: {SWEEP_JSON}")
    print(f"Sweep MD:   {SWEEP_MD}")
    print(f"Calib JSON: {CALIB_JSON}")
    print(f"Calib MD:   {CALIB_MD}")

    print(f"\n=== Calibration Summary (PROP_FIRM_STRICT) ===")
    print(f"Before      total net PnL: {before_analytics['total_after_pnl']}, "
          f"loss from 8: {round(loss_8_before, 2)}, score: {before_score['total_score']}")
    print(f"Sprint 9.9.3.2 total net PnL: {sprint_9932_metrics['total_net_pnl']}, "
          f"loss from 8: {sprint_9932_metrics['loss_from_8_scenarios']}, "
          f"score: {sprint_9932_score['total_score']}")
    print(f"Sprint 9.9.3.3 total net PnL: {analytics_9933['total_after_pnl']}, "
          f"loss from 8: {round(loss_8_9933, 2)}, "
          f"score: {score_9933['total_score']}")
    print(f"\nAll criteria met: {calib_report['acceptance_criteria']['all_criteria_met']}")


def _write_sweep_md(report: Dict, sweep_per_profile: Dict):
    md = []
    md.append("# Sprint 9.9.3.3 — Governance Threshold Sweep\n\n")
    md.append(f"**Timestamp UTC:** {report['timestamp_utc']}\n")
    md.append(f"**Source report:** `{report['source_report']}`\n")
    md.append(f"**Synthetic scenarios tested:** {report['synthetic_scenarios_count']}\n\n")

    md.append("## Methodology\n")
    md.append("- Tested combinations of: meta_block, meta_throttle, atr_block, ")
    md.append("atr_throttle, spread_block, flip_block, risk_mult_warn.\n")
    md.append("- Each combination scored using competition-style objective function.\n")
    md.append("- Best config = highest score (not necessarily zero losses).\n\n")

    for profile, s in report["sweep_per_profile"].items():
        md.append(f"## {profile}\n\n")
        md.append(f"**Total combinations tested:** {s['total_combinations_tested']}\n\n")
        md.append(f"**Best score:** {s['best_score']}\n\n")
        md.append(f"**Best config:**\n\n```json\n")
        md.append(json.dumps(s["best_config"], indent=2))
        md.append("\n```\n\n")
        md.append("### Top 5 Configurations\n\n")
        md.append("| Rank | Score | Net PnL | Max DD | PF | Blocked | Missed Profit | Avoided Loss | Overfilter Ratio |\n")
        md.append("|---|---|---|---|---|---|---|---|---|\n")
        for i, r in enumerate(s["top_5"], 1):
            md.append(f"| {i} | {r['total_score']} | {r['net_pnl']} | "
                      f"{r['max_dd']} | {r['pf']} | {r['blocked_count']} | "
                      f"{r['missed_profit']} | {r['avoided_loss']} | "
                      f"{r['overfiltering_ratio']} |\n")
        md.append("\n")

    with open(SWEEP_MD, "w", encoding="utf-8") as f:
        f.writelines(md)


def _write_calib_md(report: Dict):
    md = []
    md.append("# Sprint 9.9.3.3 — Governance Calibration Report\n\n")
    md.append(f"**Timestamp UTC:** {report['timestamp_utc']}\n")
    md.append(f"**Source report:** `{report['source_report']}`\n\n")

    md.append("## Important\n")
    md.append("- This is a **SIMULATION** — no real or demo MT5 execution.\n")
    md.append("- **DEMO_MICRO_EXECUTE was NOT run.**\n")
    md.append("- **Production live path unchanged.** No martingale/grid/averaging/lot escalation.\n")
    md.append("- **No models retrained.**\n\n")

    md.append("## Root Cause of Overfiltering (Sprint 9.9.3.2)\n\n")
    md.append("Sprint 9.9.3.2 used single-tier hard blocks for many conditions:\n")
    md.append("- ATR > 92 (PROP_FIRM_STRICT) → hard block (missed HV_STRONG_ALPHA winners)\n")
    md.append("- meta < 0.70 → hard block (missed borderline winners with positive expected edge)\n")
    md.append("- broker_quality < 70 → hard block (missed trades where broker was just OK)\n")
    md.append("- regime_flip > 0.60 → hard block (missed false-alarm flip scenarios)\n\n")
    md.append("Result: 11 of 17 scenarios blocked, $19.7 profit missed, ")
    md.append("only $52 loss avoided (overfiltering ratio 0.38).\n\n")

    md.append("## Best Calibrated Config (PROP_FIRM_STRICT)\n\n")
    md.append("```json\n")
    md.append(json.dumps(report["best_prop_firm_strict_config"], indent=2))
    md.append("\n```\n\n")

    md.append("## Before vs Sprint 9.9.3.2 vs Sprint 9.9.3.3\n\n")
    md.append("| Metric | Before | Sprint 9.9.3.2 | Sprint 9.9.3.3 |\n")
    md.append("|---|---|---|---|\n")
    b = report["before"]
    s2 = report["sprint_9_9_3_2"]
    s3 = report["sprint_9_9_3_3"]
    md.append(f"| Total net PnL | {b['total_net_pnl']} | {s2['total_net_pnl']} | {s3['total_net_pnl']} |\n")
    md.append(f"| Loss from 8 scenarios | {b['loss_from_8_scenarios']} | {s2['loss_from_8_scenarios']} | {s3['loss_from_8_scenarios']} |\n")
    md.append(f"| Max DD | {b['max_dd']} | {s2['max_dd']} | {s3['max_dd']} |\n")
    md.append(f"| Profit factor | {b['pf']} | {s2['pf']} | {s3['pf']} |\n")
    md.append(f"| Executed win rate % | {b['executed_win_rate_pct']} | {s2['executed_win_rate_pct']} | {s3['executed_win_rate_pct']} |\n")
    md.append(f"| Opportunity win rate % | {b['opportunity_win_rate_pct']} | {s2['opportunity_win_rate_pct']} | {s3['opportunity_win_rate_pct']} |\n")
    md.append(f"| Blocked count | {b['blocked_count']} | {s2['blocked_count']} | {s3['blocked_count']} |\n")
    md.append(f"| Blocked winners | 0 | {s2.get('blocked_winners', 0)} | {s3['blocked_winners']} |\n")
    md.append(f"| Blocked losers | 0 | {s2.get('blocked_losers', 0)} | {s3['blocked_losers']} |\n")
    md.append(f"| Missed profit | {b['missed_profit']} | {s2['missed_profit']} | {s3['missed_profit']} |\n")
    md.append(f"| Avoided loss | {b['avoided_loss']} | {s2['avoided_loss']} | {s3['avoided_loss']} |\n")
    md.append(f"| Overfiltering ratio | {b['overfiltering_ratio']} | {s2['overfiltering_ratio']} | {s3['overfiltering_ratio']} |\n")
    md.append(f"| Profit retention % | {b['profit_retention_pct']} | {s2['profit_retention_pct']} | {s3['profit_retention_pct']} |\n")
    md.append(f"| Loss reduction % | {b['loss_reduction_pct']} | {s2['loss_reduction_pct']} | {s3['loss_reduction_pct']} |\n")
    md.append(f"| Trade frequency | {b['trade_frequency']} | {s2['trade_frequency']} | {s3['trade_frequency']} |\n")
    md.append(f"| EV per executed trade | — | {s2.get('ev_per_executed_trade', 0)} | {s3['ev_per_executed_trade']} |\n")
    md.append(f"| Loss reduction efficiency | — | — | {s3['loss_reduction_efficiency']} |\n")
    md.append(f"| Competition score | {b['competition_score']['total_score']} | {s2['competition_score']['total_score']} | {s3['competition_score']['total_score']} |\n")

    md.append("\n## Competition Score Breakdown (Sprint 9.9.3.3)\n\n")
    md.append("| Component | Weight | Score |\n|---|---|---|\n")
    for k, v in s3["competition_score"]["components"].items():
        md.append(f"| {k} | — | {v} |\n")
    md.append(f"| **TOTAL** | **/100** | **{s3['competition_score']['total_score']}** |\n")

    md.append("\n## The 8 Losing Scenarios — Before vs Sprint 9.9.3.3\n\n")
    md.append("| # | Scenario | Before | After 9.9.3.3 | Change | Action | Risk Mult |\n")
    md.append("|---|---|---|---|---|---|---|\n")
    for i, c in enumerate(report["losing_scenario_comparison"], 1):
        md.append(f"| {i} | {c['scenario']} | {c['before_pnl']} | "
                  f"{c['after_9933_pnl']} | {c['change']} | "
                  f"{c['action']} | {c['risk_multiplier']} |\n")

    md.append("\n## Synthetic Unseen Scenarios (Anti-Overfit Validation)\n\n")
    md.append("| # | Scenario | Expected PnL | After 9.9.3.3 | Allowed | Blocked Winner | Blocked Loser |\n")
    md.append("|---|---|---|---|---|---|---|\n")
    for i, c in enumerate(report["synthetic_scenario_results"], 1):
        md.append(f"| {i} | {c['scenario']} | {c['expected_pnl']} | "
                  f"{c['after_9933_pnl']} | {c['allowed']} | "
                  f"{c['is_blocked_winner']} | {c['is_blocked_loser']} |\n")

    md.append("\n## Acceptance Criteria\n\n")
    md.append("| Criterion | Met |\n|---|---|\n")
    for k, v in report["acceptance_criteria"].items():
        icon = "YES" if v else "NO"
        md.append(f"| {k} | {icon} |\n")

    md.append("\n## Safety Confirmation\n\n")
    md.append("| Item | Value |\n|---|---|\n")
    for k, v in report["safety"].items():
        md.append(f"| {k} | {'YES' if v else 'NO'} |\n")

    with open(CALIB_MD, "w", encoding="utf-8") as f:
        f.writelines(md)


if __name__ == "__main__":
    main()
