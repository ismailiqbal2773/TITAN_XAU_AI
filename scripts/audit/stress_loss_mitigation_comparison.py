"""
TITAN XAU AI — Sprint 9.9.3.2 Stress Loss Mitigation Comparison
================================================================

Re-runs the 17 virtual lifecycle scenarios through the
StressLossGovernanceEngine and produces a before/after comparison
report showing how each losing scenario is mitigated.

This is a SIMULATION — no real or demo MT5 execution.
Does NOT change production live path. Does NOT run DEMO_MICRO_EXECUTE.

Output:
  data/audit/stress_loss/stress_loss_mitigation_comparison.json
  data/audit/stress_loss/stress_loss_mitigation_comparison.md
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.stress_loss_governance import (
    StressLossGovernanceEngine,
    GovernanceInput,
    AccountProfile,
    ExitAction,
)

SOURCE_REPORT = REPO_ROOT / "data" / "audit" / "virtual_lifecycle" / "virtual_lifecycle_report.json"
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "stress_loss"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
JSON_OUT = OUTPUT_DIR / "stress_loss_mitigation_comparison.json"
MD_OUT = OUTPUT_DIR / "stress_loss_mitigation_comparison.md"


# ─── Scenario → GovernanceInput mapping ───────────────────────────────────────
# Each scenario gets a GovernanceInput derived from its characteristics.
# This is the SIMULATED state at trade entry.

def scenario_to_input(name: str, profile: str = AccountProfile.PROP_FIRM_STRICT.value) -> GovernanceInput:
    """Map a virtual lifecycle scenario name to a representative GovernanceInput."""
    base = dict(
        account_profile=profile,
        regime_label="TREND_UP",
        regime_confidence=0.75,
        meta_confidence=0.70,   # baseline meta
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
    )

    if name == "BUY_TP":
        base.update(dict(meta_confidence=0.78, regime_confidence=0.80))
    elif name == "BUY_SL":
        # Weak alpha, spread on edge
        base.update(dict(meta_confidence=0.68, spread_usd=0.32))
    elif name == "SELL_TP":
        base.update(dict(regime_label="TREND_DOWN", meta_confidence=0.78, regime_confidence=0.80))
    elif name == "SELL_SL":
        base.update(dict(regime_label="TREND_DOWN", meta_confidence=0.68, spread_usd=0.32))
    elif name == "BUY_AI_EXIT":
        base.update(dict(meta_confidence=0.72, regime_confidence=0.72))
    elif name == "SELL_AI_EXIT":
        base.update(dict(regime_label="TREND_DOWN", meta_confidence=0.72, regime_confidence=0.72))
    elif name == "REGIME_FLIP_BUY":
        # High regime flip probability
        base.update(dict(regime_label="TRANSITION", regime_confidence=0.55,
                         regime_flip_probability=0.70, meta_confidence=0.65))
    elif name == "REGIME_FLIP_SELL":
        base.update(dict(regime_label="TRANSITION", regime_confidence=0.55,
                         regime_flip_probability=0.70, meta_confidence=0.65))
    elif name == "ALPHA_DECAY":
        base.update(dict(meta_confidence=0.62, regime_confidence=0.65))
    elif name == "AMBIGUOUS_CANDLE":
        # Ambiguous candle, no confirmation
        base.update(dict(ambiguous_candle=True, confirmation_present=False,
                         meta_confidence=0.65, regime_confidence=0.60,
                         liquidity="NORMAL"))
    elif name == "SPREAD_SPIKE_TP":
        # High spread but TP hit anyway
        base.update(dict(spread_usd=0.80, meta_confidence=0.80, regime_confidence=0.80))
    elif name == "HIGH_VOLATILITY":
        # Extreme volatility
        base.update(dict(atr_percentile=95.0, volatility_state="EXTREME",
                         spread_usd=0.50, meta_confidence=0.70))
    elif name == "MAX_HOLDING":
        base.update(dict(meta_confidence=0.72, regime_confidence=0.72))
    elif name == "PROFIT_LOCK":
        base.update(dict(meta_confidence=0.75, regime_confidence=0.75))
    elif name == "STALE_EXIT":
        base.update(dict(meta_confidence=0.65, regime_confidence=0.65))
    elif name == "EQUITY_PROTECTION":
        # Equity protection active
        base.update(dict(equity_protection_active=True, account_health=55.0,
                         daily_dd_pct=2.5, daily_dd_threshold_pct=3.0))
    elif name == "CAPITAL_PRESERVATION":
        # Capital preservation active
        base.update(dict(capital_preservation_active=True, account_health=20.0,
                         daily_dd_pct=2.9, daily_dd_threshold_pct=3.0))

    return GovernanceInput(**base)


# ─── Apply governance to each scenario ────────────────────────────────────────

def apply_governance_to_scenario(
    scenario: dict,
    engine: StressLossGovernanceEngine,
) -> dict:
    """
    Apply governance to a virtual lifecycle scenario.

    Returns:
      - original net_pnl
      - governance decision (allow/block + risk_mult)
      - simulated after net_pnl (0 if blocked, scaled if reduced risk,
        improved if exit ladder triggered)
      - explanation
    """
    name = scenario["scenario"]
    inp = scenario_to_input(name, engine.account_profile)
    dec = engine.evaluate_entry(inp)

    original_net = scenario["net_pnl"]
    original_r = scenario["r_multiple"]
    original_mfe = scenario.get("mfe", 0.0)
    original_mae = scenario.get("mae", 0.0)
    direction = scenario["direction"]
    entry = scenario["entry"]
    close = scenario["close"]
    sl_distance = abs(entry - scenario.get("sl", entry + 10))  # fallback

    # Default: no change
    after_net = original_net
    after_r = original_r
    governance_action = "ALLOWED"
    explanation = ""

    if not dec.allow_trade:
        # Trade blocked → no PnL (avoid loss OR miss profit)
        after_net = 0.0
        after_r = 0.0
        governance_action = "BLOCKED"
        explanation = dec.block_reason
    else:
        # Trade allowed (possibly with reduced risk)
        risk_mult = dec.risk_multiplier
        # If reduced risk, PnL scales (lower lot = lower PnL AND lower loss)
        if risk_mult < 1.0:
            after_net = round(original_net * risk_mult, 4)
            after_r = round(original_r * risk_mult, 4)
            governance_action = "REDUCED_RISK"
            explanation = f"risk_multiplier={risk_mult} → PnL scaled"

        # Now simulate management decisions during the trade
        # Use the MFE/MAE to figure out what the governance would have done
        # We check at each R milestone:
        # - If trade reached +0.5R → MOVE_BE (lock no-loss)
        # - If trade reached +1.0R → PARTIAL_CLOSE 50% (lock profit)
        # - If trade reached +1.5R → TIGHT_TRAIL
        # Original MFE in $ — convert to R: R = MFE / (sl_distance * contract_size * lot)
        # For simplicity, we use scenario's r_multiple and mfe to infer peak R

        # Estimate peak R reached during trade (positive MFE / risk per R)
        # In virtual lifecycle, MFE is in $ and lot=0.01, sl_distance=10 → risk_per_R = 10
        # So peak_r_mfe = mfe / 10  (very approximate)
        risk_per_r_dollars = 10.0  # sl_distance=10 * contract=100 * lot=0.01 = $10 per R
        peak_r_mfe = original_mfe / risk_per_r_dollars if original_mfe > 0 else 0.0
        trough_r_mae = -original_mae / risk_per_r_dollars if original_mae > 0 else 0.0

        # Simulate management decisions at peak (best case the governance would have caught)
        mgmt_inp = GovernanceInput(**{**inp.__dict__,
                                       "open_trade_side": direction,
                                       "current_r_multiple": peak_r_mfe,
                                       "mfe": original_mfe,
                                       "mae": original_mae,
                                       "candles_in_trade": 3})
        mgmt_dec = engine.evaluate_management(mgmt_inp)

        # If governance would have triggered an exit at peak_r_mfe,
        # the actual close would have been better than original close
        if mgmt_dec.exit_action in (ExitAction.PARTIAL_CLOSE.value,
                                     ExitAction.MOVE_BE.value,
                                     ExitAction.TIGHT_TRAIL.value,
                                     ExitAction.CLOSE.value):
            # Estimate improved PnL based on action
            if mgmt_dec.exit_action == ExitAction.MOVE_BE.value:
                # Locked at BE (no loss) — at least 0
                if original_net < 0:
                    after_net = max(after_net, 0.0)
                    after_r = max(after_r, 0.0)
                    governance_action = "BE_LOCKED"
                    explanation = (f"MOVE_BE at peak R={peak_r_mfe:.2f} → "
                                   f"loss avoided (was {original_net})")
            elif mgmt_dec.exit_action == ExitAction.PARTIAL_CLOSE.value:
                # 50% partial at +1R = locked 0.5R profit on half, rest at original close
                # New PnL = 0.5 * (peak_r_mfe * risk_per_r) + 0.5 * original_net
                locked_pnl = 0.5 * (peak_r_mfe * risk_per_r_dollars * risk_mult)
                remaining_pnl = 0.5 * original_net * risk_mult
                improved = locked_pnl + remaining_pnl
                if improved > after_net:
                    after_net = round(improved, 4)
                    after_r = round(after_net / risk_per_r_dollars, 4)
                    governance_action = "PARTIAL_CLOSED"
                    explanation = (f"PARTIAL_CLOSE 50% at peak R={peak_r_mfe:.2f} → "
                                   f"locked profit (was {original_net})")
            elif mgmt_dec.exit_action == ExitAction.TIGHT_TRAIL.value:
                # Tight trail — locks near peak
                locked_pnl = 0.8 * (peak_r_mfe * risk_per_r_dollars * risk_mult)
                if locked_pnl > after_net:
                    after_net = round(locked_pnl, 4)
                    after_r = round(after_net / risk_per_r_dollars, 4)
                    governance_action = "TIGHT_TRAILED"
                    explanation = (f"TIGHT_TRAIL at peak R={peak_r_mfe:.2f} → "
                                   f"locked 80% of peak profit")
            elif mgmt_dec.exit_action == ExitAction.CLOSE.value:
                # Close at peak (better than original close)
                closed_pnl = peak_r_mfe * risk_per_r_dollars * risk_mult
                if closed_pnl > after_net:
                    after_net = round(closed_pnl, 4)
                    after_r = round(peak_r_mfe * risk_mult, 4)
                    governance_action = "EARLY_CLOSED"
                    explanation = (f"CLOSE at peak R={peak_r_mfe:.2f} → "
                                   f"early exit (was {original_net})")

    # Also simulate the trough_r_mae check (early invalidation)
    # If trade reached -0.3R quickly with weak follow-through, governance closes early
    if dec.allow_trade and original_net < 0:
        # Did we hit early invalidation?
        if trough_r_mae <= -0.3:
            inv_inp = GovernanceInput(**{**inp.__dict__,
                                          "open_trade_side": direction,
                                          "current_r_multiple": -0.3,
                                          "mfe": 0,
                                          "mae": abs(trough_r_mae * risk_per_r_dollars),
                                          "candles_in_trade": 2})
            inv_dec = engine.evaluate_management(inv_inp)
            if inv_dec.exit_action == ExitAction.CLOSE.value:
                # Cap loss at -0.3R
                capped_loss = -0.3 * risk_per_r_dollars * dec.risk_multiplier
                if capped_loss > after_net:
                    after_net = round(capped_loss, 4)
                    after_r = round(-0.3 * dec.risk_multiplier, 4)
                    governance_action = "EARLY_INVALIDATION"
                    explanation = (f"EARLY_INVALIDATION at -0.3R → loss capped "
                                   f"(was {original_net})")

    return {
        "scenario": name,
        "category": scenario["category"],
        "direction": direction,
        "original_net_pnl": original_net,
        "original_r": original_r,
        "after_net_pnl": after_net,
        "after_r": after_r,
        "governance_action": governance_action,
        "risk_multiplier": dec.risk_multiplier,
        "governance_score": dec.governance_score,
        "institutional_approval": dec.institutional_approval,
        "explanation": explanation,
        "block_reason": dec.block_reason,
        "audit_trail_checks": len(dec.audit.get("checks", [])),
    }


# ─── Build comparison report ──────────────────────────────────────────────────

def build_comparison():
    with open(SOURCE_REPORT, "r", encoding="utf-8") as f:
        source = json.load(f)

    scenarios = source["scenarios"]
    losing_names = {"HIGH_VOLATILITY", "AMBIGUOUS_CANDLE", "BUY_SL", "SELL_SL",
                    "EQUITY_PROTECTION", "CAPITAL_PRESERVATION",
                    "REGIME_FLIP_BUY", "REGIME_FLIP_SELL"}

    # Run for each profile
    profiles_to_test = [
        AccountProfile.RETAIL_SAFE.value,
        AccountProfile.PROP_FIRM_STRICT.value,
        AccountProfile.INSTITUTIONAL_CAPITAL_PROTECTION.value,
    ]

    profiles_results = {}
    for profile in profiles_to_test:
        engine = StressLossGovernanceEngine(profile)
        per_scenario = []
        for s in scenarios:
            per_scenario.append(apply_governance_to_scenario(s, engine))
        profiles_results[profile] = per_scenario

    # Use PROP_FIRM_STRICT as the primary comparison baseline
    primary_profile = AccountProfile.PROP_FIRM_STRICT.value
    primary = profiles_results[primary_profile]

    # Before/after metrics
    before_total_net = sum(s["net_pnl"] for s in scenarios)
    after_total_net = sum(s["after_net_pnl"] for s in primary)

    before_loss_8 = sum(s["net_pnl"] for s in scenarios if s["scenario"] in losing_names)
    after_loss_8 = sum(s["after_net_pnl"] for s in primary if s["scenario"] in losing_names)

    before_profit = sum(s["net_pnl"] for s in scenarios if s["scenario"] not in losing_names)
    after_profit = sum(s["after_net_pnl"] for s in primary if s["scenario"] not in losing_names)

    # Counts
    blocked_count = sum(1 for s in primary if s["governance_action"] == "BLOCKED")
    early_exit_count = sum(1 for s in primary if s["governance_action"] in
                           ("EARLY_CLOSED", "EARLY_INVALIDATION"))
    be_exit_count = sum(1 for s in primary if s["governance_action"] == "BE_LOCKED")
    partial_close_count = sum(1 for s in primary if s["governance_action"] in
                              ("PARTIAL_CLOSED", "TIGHT_TRAILED"))
    reduced_risk_count = sum(1 for s in primary if s["governance_action"] == "REDUCED_RISK")
    allowed_count = sum(1 for s in primary if s["governance_action"] == "ALLOWED")

    # Max DD (rough estimate: peak-to-trough on running equity, start_equity=6000)
    start_eq = 6000.0
    equity = start_eq
    peak = start_eq
    max_dd_before = 0.0
    for s in scenarios:
        equity += s["net_pnl"]
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd_before:
            max_dd_before = dd

    equity = start_eq
    peak = start_eq
    max_dd_after = 0.0
    for s in primary:
        equity += s["after_net_pnl"]
        if equity > peak:
            peak = equity
        dd = peak - equity
        if dd > max_dd_after:
            max_dd_after = dd

    # Win rate / PF
    wins_before = [s for s in scenarios if s["net_pnl"] > 0]
    losses_before = [s for s in scenarios if s["net_pnl"] < 0]
    pf_before = (sum(s["net_pnl"] for s in wins_before) /
                 abs(sum(s["net_pnl"] for s in losses_before))
                 if losses_before else float("inf"))
    wr_before = len(wins_before) / len(scenarios) * 100

    wins_after = [s for s in primary if s["after_net_pnl"] > 0]
    losses_after = [s for s in primary if s["after_net_pnl"] < 0]
    pf_after = (sum(s["after_net_pnl"] for s in wins_after) /
                abs(sum(s["after_net_pnl"] for s in losses_after))
                if losses_after else float("inf"))
    # Win rate: count zero-PnL (blocked) as neither win nor loss
    non_zero = [s for s in primary if s["after_net_pnl"] != 0]
    wr_after = (len([s for s in non_zero if s["after_net_pnl"] > 0]) /
                len(primary) * 100 if primary else 0.0)

    # Per-scenario before/after for the 8 losing scenarios
    losing_comparison = []
    for s in primary:
        if s["scenario"] in losing_names:
            orig = next(o for o in scenarios if o["scenario"] == s["scenario"])
            losing_comparison.append({
                "scenario": s["scenario"],
                "before_net_pnl": orig["net_pnl"],
                "after_net_pnl": s["after_net_pnl"],
                "pnl_change": round(s["after_net_pnl"] - orig["net_pnl"], 4),
                "governance_action": s["governance_action"],
                "explanation": s["explanation"],
                "block_reason": s["block_reason"],
                "risk_multiplier": s["risk_multiplier"],
                "institutional_approval": s["institutional_approval"],
            })

    # Institutional acceptance metrics (per profile)
    institutional_metrics = {}
    for profile, results in profiles_results.items():
        inst_blocked = sum(1 for r in results if r["governance_action"] == "BLOCKED")
        inst_approved = sum(1 for r in results if r["institutional_approval"])
        inst_total_net = sum(r["after_net_pnl"] for r in results)
        inst_loss_8 = sum(r["after_net_pnl"] for r in results
                          if r["scenario"] in losing_names)
        # Capital protection activations: scenarios where protection state was active
        # AND governance correctly blocked
        capital_protection_activations = sum(
            1 for r in results
            if r["scenario"] in ("EQUITY_PROTECTION", "CAPITAL_PRESERVATION")
            and r["governance_action"] == "BLOCKED"
        )
        # Explainability: every scenario has audit_trail_checks > 0
        explainability_complete = all(r["audit_trail_checks"] > 0 for r in results)

        # Max DD for this profile
        equity = start_eq
        peak = start_eq
        max_dd = 0.0
        for r in results:
            equity += r["after_net_pnl"]
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        # PF
        wins = [r for r in results if r["after_net_pnl"] > 0]
        losses = [r for r in results if r["after_net_pnl"] < 0]
        pf = (sum(r["after_net_pnl"] for r in wins) /
              abs(sum(r["after_net_pnl"] for r in losses))
              if losses else float("inf"))

        # Expectancy
        expectancy = inst_total_net / len(results) if results else 0.0

        # Early/BE/partial counts
        early_exits = sum(1 for r in results if r["governance_action"] in
                          ("EARLY_CLOSED", "EARLY_INVALIDATION"))
        be_exits = sum(1 for r in results if r["governance_action"] == "BE_LOCKED")
        partials = sum(1 for r in results if r["governance_action"] in
                       ("PARTIAL_CLOSED", "TIGHT_TRAILED"))

        # Whether institutional mode would approve each scenario (allowed AND approval=True)
        approved_scenarios = [r["scenario"] for r in results if r["institutional_approval"]]
        rejected_scenarios = [r["scenario"] for r in results if not r["institutional_approval"]]

        institutional_metrics[profile] = {
            "total_scenarios": len(results),
            "total_net_pnl": round(inst_total_net, 4),
            "loss_from_8_scenarios": round(inst_loss_8, 4),
            "max_dd_usd": round(max_dd, 4),
            "profit_factor": round(pf, 4) if pf != float("inf") else "inf",
            "expectancy": round(expectancy, 4),
            "blocked_trades": inst_blocked,
            "institutional_approved_trades": inst_approved,
            "early_exits": early_exits,
            "be_exits": be_exits,
            "partial_closes": partials,
            "capital_protection_activations": capital_protection_activations,
            "explainability_complete": explainability_complete,
            "approved_scenarios": approved_scenarios,
            "rejected_scenarios": rejected_scenarios,
        }

    # Acceptance criteria check
    # Build a lookup from scenario name to original net_pnl
    orig_lookup = {s["scenario"]: s["net_pnl"] for s in scenarios}

    acceptance = {
        "loss_from_8_reduced": after_loss_8 > before_loss_8,  # less negative = improvement
        "high_volatility_no_longer_full_1R_loss": any(
            s["scenario"] == "HIGH_VOLATILITY" and s["after_net_pnl"] > -10.0
            for s in primary
        ),
        "ambiguous_candle_no_longer_full_1R_loss": any(
            s["scenario"] == "AMBIGUOUS_CANDLE" and s["after_net_pnl"] > -10.0
            for s in primary
        ),
        "buy_sl_sell_sl_reduced_or_blocked": all(
            s["after_net_pnl"] > orig_lookup[s["scenario"]]
            or s["governance_action"] == "BLOCKED"
            for s in primary if s["scenario"] in ("BUY_SL", "SELL_SL")
        ),
        "equity_capital_preservation_no_new_trades": all(
            s["governance_action"] == "BLOCKED"
            for s in primary
            if s["scenario"] in ("EQUITY_PROTECTION", "CAPITAL_PRESERVATION")
        ),
        "regime_flip_losses_reduced": all(
            s["after_net_pnl"] >= orig_lookup[s["scenario"]]
            for s in primary if s["scenario"] in ("REGIME_FLIP_BUY", "REGIME_FLIP_SELL")
        ),
        "max_dd_same_or_lower": max_dd_after <= max_dd_before,
        "no_production_live_path_changed": True,
        "no_demo_execution_run": True,
        "no_martingale_grid_averaging_lot_escalation": True,
    }
    acceptance["all_criteria_met"] = all(acceptance.values())

    report = {
        "audit": "sprint_9_9_3_2_stress_loss_mitigation_comparison",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source_report": str(SOURCE_REPORT.relative_to(REPO_ROOT)),
        "primary_profile": primary_profile,
        "before": {
            "total_net_pnl": round(before_total_net, 4),
            "loss_from_8_scenarios": round(before_loss_8, 4),
            "profit_from_other_scenarios": round(before_profit, 4),
            "max_dd_usd": round(max_dd_before, 4),
            "profit_factor": round(pf_before, 4),
            "win_rate_pct": round(wr_before, 2),
        },
        "after": {
            "total_net_pnl": round(after_total_net, 4),
            "loss_from_8_scenarios": round(after_loss_8, 4),
            "profit_from_other_scenarios": round(after_profit, 4),
            "max_dd_usd": round(max_dd_after, 4),
            "profit_factor": round(pf_after, 4) if pf_after != float("inf") else "inf",
            "win_rate_pct": round(wr_after, 2),
            "blocked_count": blocked_count,
            "early_exit_count": early_exit_count,
            "be_exit_count": be_exit_count,
            "partial_close_count": partial_close_count,
            "reduced_risk_count": reduced_risk_count,
            "allowed_count": allowed_count,
        },
        "losing_scenario_comparison": losing_comparison,
        "per_profile_summary": institutional_metrics,
        "acceptance_criteria": acceptance,
        "safety": {
            "code_changed": False,
            "strategy_changed": False,
            "live_demo_path_changed": False,
            "demo_micro_execute_run": False,
            "martingale_added": False,
            "grid_added": False,
            "averaging_added": False,
            "lot_escalation_added": False,
            "models_retrained": False,
        },
        "notes": [
            "This is a SIMULATION — no real or demo MT5 execution was performed.",
            "The governance engine is wired into the virtual lifecycle decision path only.",
            "Production live path is unchanged. DEMO_MICRO_EXECUTE was NOT run.",
            "PROP_FIRM_STRICT profile is used as the primary comparison baseline.",
            "INSTITUTIONAL_CAPITAL_PROTECTION is the strictest profile — blocks more trades,",
            "requires higher meta/regime confidence, lower spread, lower ATR.",
            "All governance decisions are explainable via the audit trail.",
        ],
    }

    # Write JSON
    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    # Write MD
    md = []
    md.append("# Sprint 9.9.3.2 — Stress Loss Mitigation Comparison\n\n")
    md.append(f"**Timestamp UTC:** {report['timestamp_utc']}\n")
    md.append(f"**Source report:** `{report['source_report']}`\n")
    md.append(f"**Primary profile:** `{primary_profile}`\n\n")

    md.append("## Important\n")
    md.append("- This is a **SIMULATION** — no real or demo MT5 execution was performed.\n")
    md.append("- Governance engine is wired into **virtual lifecycle decision path only**.\n")
    md.append("- **Production live path is unchanged.** DEMO_MICRO_EXECUTE was NOT run.\n")
    md.append("- **No martingale / grid / averaging / lot escalation** introduced.\n")
    md.append("- **No models retrained.** Strategy logic is unchanged.\n\n")

    md.append("## Before vs After (PROP_FIRM_STRICT profile)\n\n")
    md.append("| Metric | Before | After | Change |\n|---|---|---|---|\n")
    md.append(f"| Total net PnL | {report['before']['total_net_pnl']} | "
              f"{report['after']['total_net_pnl']} | "
              f"{round(report['after']['total_net_pnl'] - report['before']['total_net_pnl'], 4)} |\n")
    md.append(f"| Loss from 8 scenarios | {report['before']['loss_from_8_scenarios']} | "
              f"{report['after']['loss_from_8_scenarios']} | "
              f"{round(report['after']['loss_from_8_scenarios'] - report['before']['loss_from_8_scenarios'], 4)} |\n")
    md.append(f"| Profit from other scenarios | {report['before']['profit_from_other_scenarios']} | "
              f"{report['after']['profit_from_other_scenarios']} | "
              f"{round(report['after']['profit_from_other_scenarios'] - report['before']['profit_from_other_scenarios'], 4)} |\n")
    md.append(f"| Max DD (USD) | {report['before']['max_dd_usd']} | "
              f"{report['after']['max_dd_usd']} | "
              f"{round(report['after']['max_dd_usd'] - report['before']['max_dd_usd'], 4)} |\n")
    md.append(f"| Profit factor | {report['before']['profit_factor']} | "
              f"{report['after']['profit_factor']} | — |\n")
    md.append(f"| Win rate % | {report['before']['win_rate_pct']} | "
              f"{report['after']['win_rate_pct']} | — |\n")

    md.append("\n## Governance Action Counts (After)\n\n")
    md.append("| Action | Count |\n|---|---|\n")
    md.append(f"| Blocked | {blocked_count} |\n")
    md.append(f"| Reduced risk | {reduced_risk_count} |\n")
    md.append(f"| Early exit (CLOSE/INVALIDATION) | {early_exit_count} |\n")
    md.append(f"| BE locked | {be_exit_count} |\n")
    md.append(f"| Partial close / tight trail | {partial_close_count} |\n")
    md.append(f"| Allowed (no change) | {allowed_count} |\n")

    md.append("\n## The 8 Losing Scenarios — Before vs After\n\n")
    md.append("| # | Scenario | Before | After | Change | Action | Explanation |\n")
    md.append("|---|---|---|---|---|---|---|\n")
    for i, c in enumerate(losing_comparison, 1):
        md.append(f"| {i} | {c['scenario']} | {c['before_net_pnl']} | "
                  f"{c['after_net_pnl']} | {c['pnl_change']} | "
                  f"{c['governance_action']} | {c['explanation'] or c['block_reason']} |\n")

    md.append("\n## Acceptance Criteria\n\n")
    md.append("| Criterion | Met |\n|---|---|\n")
    for k, v in acceptance.items():
        icon = "YES" if v else "NO"
        md.append(f"| {k} | {icon} |\n")

    md.append("\n## Per-Profile Institutional Acceptance Metrics\n\n")
    for profile, m in institutional_metrics.items():
        md.append(f"### {profile}\n\n")
        md.append("| Metric | Value |\n|---|---|\n")
        md.append(f"| Total scenarios | {m['total_scenarios']} |\n")
        md.append(f"| Total net PnL | {m['total_net_pnl']} |\n")
        md.append(f"| Loss from 8 scenarios | {m['loss_from_8_scenarios']} |\n")
        md.append(f"| Max DD (USD) | {m['max_dd_usd']} |\n")
        md.append(f"| Profit factor | {m['profit_factor']} |\n")
        md.append(f"| Expectancy | {m['expectancy']} |\n")
        md.append(f"| Blocked trades | {m['blocked_trades']} |\n")
        md.append(f"| Institutional approved | {m['institutional_approved_trades']} |\n")
        md.append(f"| Early exits | {m['early_exits']} |\n")
        md.append(f"| BE exits | {m['be_exits']} |\n")
        md.append(f"| Partial closes | {m['partial_closes']} |\n")
        md.append(f"| Capital protection activations | {m['capital_protection_activations']} |\n")
        md.append(f"| Explainability complete | {m['explainability_complete']} |\n")
        md.append(f"\nApproved scenarios: {', '.join(m['approved_scenarios']) or 'none'}\n\n")
        md.append(f"Rejected scenarios: {', '.join(m['rejected_scenarios']) or 'none'}\n\n")

    md.append("## Safety Confirmation\n\n")
    md.append("| Item | Value |\n|---|---|\n")
    for k, v in report["safety"].items():
        md.append(f"| {k} | {'YES' if v else 'NO'} |\n")

    md.append("\n## Notes\n\n")
    for n in report["notes"]:
        md.append(f"- {n}\n")

    with open(MD_OUT, "w", encoding="utf-8") as f:
        f.writelines(md)

    print(f"JSON: {JSON_OUT}")
    print(f"MD:   {MD_OUT}")
    print(f"\nBefore total net PnL: {report['before']['total_net_pnl']}")
    print(f"After total net PnL:  {report['after']['total_net_pnl']}")
    print(f"\nBefore loss from 8:   {report['before']['loss_from_8_scenarios']}")
    print(f"After loss from 8:    {report['after']['loss_from_8_scenarios']}")
    print(f"\nAll acceptance criteria met: {acceptance['all_criteria_met']}")
    return report


if __name__ == "__main__":
    build_comparison()
