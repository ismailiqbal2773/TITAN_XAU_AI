"""
TITAN XAU AI — Sprint 9.8 Virtual Lifecycle Validator (Fixed DD)
==================================================================

Fixed Sprint 9.8.1: DD now calculated from configurable starting equity
(6000.00), not from 0. Normal vs stress scenarios separated.

Sprint 9.9.3.2: Added optional --governance flag to apply the
StressLossGovernanceEngine decision layer. When --governance is NOT
passed (default), behavior is unchanged — full backward compatibility.

Output:
  data/audit/virtual_lifecycle/virtual_lifecycle_report.json
  data/audit/virtual_lifecycle/virtual_lifecycle_report.md
  data/audit/virtual_lifecycle/virtual_lifecycle_journal.jsonl
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.virtual_position_ledger import VirtualPositionLedger
from titan.production.net_profit_engine import NetProfitEngine
from titan.production.trade_journal import TradeJournal

DEFAULT_START_EQUITY = 6000.00

# Scenario classification
NORMAL_SCENARIOS = {
    "BUY_TP", "BUY_SL", "SELL_TP", "SELL_SL",
    "BUY_AI_EXIT", "SELL_AI_EXIT",
    "PROFIT_LOCK", "MAX_HOLDING", "STALE_EXIT",
}
STRESS_SCENARIOS = {
    "REGIME_FLIP_BUY", "REGIME_FLIP_SELL", "ALPHA_DECAY",
    "AMBIGUOUS_CANDLE", "SPREAD_SPIKE_TP", "HIGH_VOLATILITY",
    "EQUITY_PROTECTION", "CAPITAL_PRESERVATION",
}


def run_scenarios(journal, governance_engine=None):
    ledger = VirtualPositionLedger(journal=journal)
    engine = NetProfitEngine()

    scenarios = [
        ("BUY_TP", "BUY", 2000, 1990, 2020, 2021, 2005, 2020, "TP_HIT", 0.30, 0.30),
        ("BUY_SL", "BUY", 2000, 1990, 2020, 2005, 1989, 1990, "SL_HIT", 0.30, 0.30),
        ("SELL_TP", "SELL", 2000, 2010, 1980, 2005, 1979, 1980, "TP_HIT", 0.30, 0.30),
        ("SELL_SL", "SELL", 2000, 2010, 1980, 2011, 1995, 2010, "SL_HIT", 0.30, 0.30),
        ("BUY_AI_EXIT", "BUY", 2000, 1990, 2020, 2012, 2008, 2010, "AI_EXIT_CLOSE", 0.30, 0.30),
        ("SELL_AI_EXIT", "SELL", 2000, 2010, 1980, 2005, 1988, 1990, "AI_EXIT_CLOSE", 0.30, 0.30),
        ("REGIME_FLIP_BUY", "BUY", 2000, 1990, 2020, 2008, 2002, 2000, "REGIME_RISK_EXIT", 0.30, 0.30),
        ("REGIME_FLIP_SELL", "SELL", 2000, 2010, 1980, 1998, 1992, 2000, "REGIME_RISK_EXIT", 0.30, 0.30),
        ("ALPHA_DECAY", "BUY", 2000, 1990, 2020, 2008, 2002, 2001, "ALPHA_DECAY_EXIT", 0.30, 0.30),
        ("AMBIGUOUS_CANDLE", "BUY", 2000, 1990, 2020, 2025, 1985, 2005, "SL_HIT", 0.30, 0.30),
        ("SPREAD_SPIKE_TP", "BUY", 2000, 1990, 2020, 2020, 2015, 2020, "TP_HIT", 0.80, 0.30),
        ("HIGH_VOLATILITY", "BUY", 2000, 1990, 2020, 2030, 1980, 2005, "SL_HIT", 0.50, 0.30),
        ("MAX_HOLDING", "BUY", 2000, 1990, 2020, 2008, 2002, 2005, "MAX_HOLDING_EXIT", 0.30, 0.30),
        ("PROFIT_LOCK", "BUY", 2000, 1990, 2020, 2018, 2010, 2015, "PROFIT_LOCK_EXIT", 0.30, 0.30),
        ("STALE_EXIT", "BUY", 2000, 1990, 2020, 2003, 1998, 2001, "STALE_POSITION_EXIT", 0.30, 0.30),
        ("EQUITY_PROTECTION", "BUY", 2000, 1990, 2020, 2005, 1995, 1995, "EQUITY_PROTECTION_EXIT", 0.30, 0.30),
        ("CAPITAL_PRESERVATION", "BUY", 2000, 1990, 2020, 2005, 1995, 1998, "CAPITAL_PRESERVATION_EXIT", 0.30, 0.30),
    ]

    results = []
    governance_decisions = []
    for name, direction, entry, sl, tp, high, low, close, reason, spread, comm in scenarios:
        # Sprint 9.9.3.2: If governance engine provided, evaluate entry first.
        # If blocked, skip this scenario entirely (no position opened).
        governance_decision = None
        if governance_engine is not None:
            from titan.production.stress_loss_governance import GovernanceInput
            # Build a representative GovernanceInput for this scenario.
            # We use the same logic as in stress_loss_mitigation_comparison.py
            # to keep behavior consistent.
            inp = _scenario_to_governance_input(name, governance_engine.account_profile)
            governance_decision = governance_engine.evaluate_entry(inp)
            if not governance_decision.allow_trade:
                # Skip scenario — record as blocked, no position opened
                is_stress = name in STRESS_SCENARIOS
                results.append({
                    "scenario": name,
                    "category": "STRESS" if is_stress else "NORMAL",
                    "direction": direction,
                    "entry": entry,
                    "close": entry,  # no trade
                    "reason": "GOVERNANCE_BLOCKED",
                    "gross_pnl": 0.0,
                    "net_pnl": 0.0,
                    "r_multiple": 0.0,
                    "mfe": 0.0,
                    "mae": 0.0,
                    "costs": {
                        "spread_cost": 0, "commission_cost": 0,
                        "slippage_cost": 0, "swap_cost": 0,
                        "total_cost": 0, "is_estimate": False, "estimate_reason": "",
                    },
                    "is_profitable_net": False,
                    "governance_blocked": True,
                    "governance_block_reason": governance_decision.block_reason,
                })
                governance_decisions.append({
                    "scenario": name,
                    "allow_trade": False,
                    "block_reason": governance_decision.block_reason,
                    "governance_score": governance_decision.governance_score,
                })
                continue

        pos = ledger.open_position(
            "XAUUSD", direction, entry, 0.01, sl, tp,
            spread_cost=spread, commission_cost=comm,
            signal_id=f"sig-{name}", decision_id=f"dec-{name}",
        )
        if reason in ("TP_HIT", "SL_HIT"):
            ledger.update_positions(current_price=close, high=high, low=low)
        else:
            ledger.close_position(pos.position_id, close, reason)

        net_result = engine.calculate(
            direction=direction, entry_price=entry, close_price=pos.close_price or close,
            lot=0.01, sl=sl, spread_usd=spread, slippage_pips=2.0, swap_cost=0,
        )

        is_stress = name in STRESS_SCENARIOS
        results.append({
            "scenario": name,
            "category": "STRESS" if is_stress else "NORMAL",
            "direction": direction,
            "entry": entry,
            "close": pos.close_price or close,
            "reason": pos.close_reason,
            "gross_pnl": pos.gross_pnl,
            "net_pnl": pos.net_pnl,
            "r_multiple": pos.r_multiple,
            "mfe": pos.mfe,
            "mae": pos.mae,
            "costs": net_result.costs.to_dict(),
            "is_profitable_net": pos.net_pnl > 0,
            "governance_blocked": False,
            "governance_block_reason": "",
        })
        if governance_decision is not None:
            governance_decisions.append({
                "scenario": name,
                "allow_trade": True,
                "risk_multiplier": governance_decision.risk_multiplier,
                "governance_score": governance_decision.governance_score,
                "institutional_approval": governance_decision.institutional_approval,
            })

    return ledger, results, governance_decisions


def _scenario_to_governance_input(name, profile):
    """Map a scenario to a GovernanceInput (mirrors comparison script logic)."""
    from titan.production.stress_loss_governance import GovernanceInput
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
    )
    if name == "BUY_TP":
        base.update(dict(meta_confidence=0.78, regime_confidence=0.80))
    elif name == "BUY_SL":
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
        base.update(dict(regime_label="TRANSITION", regime_confidence=0.55,
                         regime_flip_probability=0.70, meta_confidence=0.65))
    elif name == "REGIME_FLIP_SELL":
        base.update(dict(regime_label="TRANSITION", regime_confidence=0.55,
                         regime_flip_probability=0.70, meta_confidence=0.65))
    elif name == "ALPHA_DECAY":
        base.update(dict(meta_confidence=0.62, regime_confidence=0.65))
    elif name == "AMBIGUOUS_CANDLE":
        base.update(dict(ambiguous_candle=True, confirmation_present=False,
                         meta_confidence=0.65, regime_confidence=0.60,
                         liquidity="NORMAL"))
    elif name == "SPREAD_SPIKE_TP":
        base.update(dict(spread_usd=0.80, meta_confidence=0.80, regime_confidence=0.80))
    elif name == "HIGH_VOLATILITY":
        base.update(dict(atr_percentile=95.0, volatility_state="EXTREME",
                         spread_usd=0.50, meta_confidence=0.70))
    elif name == "MAX_HOLDING":
        base.update(dict(meta_confidence=0.72, regime_confidence=0.72))
    elif name == "PROFIT_LOCK":
        base.update(dict(meta_confidence=0.75, regime_confidence=0.75))
    elif name == "STALE_EXIT":
        base.update(dict(meta_confidence=0.65, regime_confidence=0.65))
    elif name == "EQUITY_PROTECTION":
        base.update(dict(equity_protection_active=True, account_health=55.0,
                         daily_dd_pct=2.5, daily_dd_threshold_pct=3.0))
    elif name == "CAPITAL_PRESERVATION":
        base.update(dict(capital_preservation_active=True, account_health=20.0,
                         daily_dd_pct=2.9, daily_dd_threshold_pct=3.0))
    return GovernanceInput(**base)


def compute_metrics(closed_positions, start_equity=DEFAULT_START_EQUITY):
    """Compute metrics with proper equity-based DD calculation."""
    if not closed_positions:
        return _empty_metrics()

    gross_pnl_total = sum(p.gross_pnl for p in closed_positions)
    net_pnl_total = sum(p.net_pnl for p in closed_positions)
    wins = [p for p in closed_positions if p.net_pnl > 0]
    losses = [p for p in closed_positions if p.net_pnl < 0]
    win_rate = len(wins) / len(closed_positions) * 100
    gross_wins = sum(p.net_pnl for p in wins) if wins else 0
    gross_losses = abs(sum(p.net_pnl for p in losses)) if losses else 0
    profit_factor = gross_wins / gross_losses if gross_losses > 0 else float('inf')
    avg_r = sum(p.r_multiple for p in closed_positions) / len(closed_positions)
    expectancy = net_pnl_total / len(closed_positions)
    avg_holding = sum(p.holding_seconds for p in closed_positions) / len(closed_positions)
    mfe_avg = sum(p.mfe for p in closed_positions) / len(closed_positions)
    mae_avg = sum(p.mae for p in closed_positions) / len(closed_positions)
    cost_drag_total = sum(p.spread_cost + p.commission_cost + p.slippage_cost + p.swap_cost for p in closed_positions)
    cost_drag_pct = (cost_drag_total / abs(gross_pnl_total) * 100) if gross_pnl_total != 0 else 0

    # DD calculation with realistic starting equity
    equity = start_equity
    peak = start_equity
    max_dd_usd = 0.0
    max_dd_pct_peak = 0.0
    for p in closed_positions:
        equity += p.net_pnl
        if equity > peak:
            peak = equity
        dd_usd = peak - equity
        dd_pct = (dd_usd / peak * 100) if peak > 0 else 0
        if dd_usd > max_dd_usd:
            max_dd_usd = dd_usd
        if dd_pct > max_dd_pct_peak:
            max_dd_pct_peak = dd_pct

    max_dd_pct_start = (max_dd_usd / start_equity * 100) if start_equity > 0 else 0

    return {
        "closed_positions": len(closed_positions),
        "gross_pnl_total": round(gross_pnl_total, 4),
        "net_pnl_total": round(net_pnl_total, 4),
        "win_rate_net": round(win_rate, 2),
        "profit_factor_net": round(profit_factor, 2),
        "max_drawdown_usd": round(max_dd_usd, 4),
        "max_drawdown_pct_of_start_equity": round(max_dd_pct_start, 4),
        "max_drawdown_pct_of_peak_equity": round(max_dd_pct_peak, 4),
        "avg_r": round(avg_r, 4),
        "expectancy_net": round(expectancy, 4),
        "avg_holding_time": round(avg_holding, 2),
        "mfe_avg": round(mfe_avg, 4),
        "mae_avg": round(mae_avg, 4),
        "cost_drag_total": round(cost_drag_total, 4),
        "cost_drag_pct": round(cost_drag_pct, 2),
        "start_equity": start_equity,
    }


def _empty_metrics():
    return {
        "closed_positions": 0, "gross_pnl_total": 0, "net_pnl_total": 0,
        "win_rate_net": 0, "profit_factor_net": 0,
        "max_drawdown_usd": 0, "max_drawdown_pct_of_start_equity": 0,
        "max_drawdown_pct_of_peak_equity": 0,
        "avg_r": 0, "expectancy_net": 0, "avg_holding_time": 0,
        "mfe_avg": 0, "mae_avg": 0, "cost_drag_total": 0, "cost_drag_pct": 0,
        "start_equity": DEFAULT_START_EQUITY,
    }


def main():
    parser = argparse.ArgumentParser(
        description="TITAN XAU AI Sprint 9.8.1 Virtual Lifecycle Validator")
    parser.add_argument("--governance", action="store_true",
                        help="Apply StressLossGovernanceEngine decision layer "
                             "(Sprint 9.9.3.2). Default: off (backward compatible).")
    parser.add_argument("--profile",
                        choices=["RETAIL_SAFE", "PROP_FIRM_STRICT",
                                 "INSTITUTIONAL_CAPITAL_PROTECTION"],
                        default="PROP_FIRM_STRICT",
                        help="Account profile for governance (default: PROP_FIRM_STRICT)")
    args = parser.parse_args()

    print("=" * 78)
    print("  TITAN XAU AI — Sprint 9.8.1 Virtual Lifecycle Validator (Fixed DD)")
    if args.governance:
        print(f"  + Sprint 9.9.3.2 Governance: ENABLED (profile={args.profile})")
    print("=" * 78)

    governance_engine = None
    if args.governance:
        from titan.production.stress_loss_governance import (
            StressLossGovernanceEngine, AccountProfile,
        )
        governance_engine = StressLossGovernanceEngine(args.profile)

    out_dir = REPO_ROOT / "data" / "audit" / "virtual_lifecycle"
    out_dir.mkdir(parents=True, exist_ok=True)
    journal_path = out_dir / "virtual_lifecycle_journal.jsonl"
    if journal_path.exists():
        journal_path.unlink()

    journal = TradeJournal(path=str(journal_path), session_id="vlc_9_8_1")

    print("\n── Running 17 virtual lifecycle scenarios ──")
    ledger, results, governance_decisions = run_scenarios(journal, governance_engine)
    journal.flush()

    all_closed = ledger.get_closed_positions()
    # When governance is enabled, some scenarios are blocked (no position opened).
    # We must align all_closed with results carefully: results includes both
    # blocked entries (governance_blocked=True, no position) and ran entries.
    # Only the ran entries have a corresponding closed position in the ledger.
    ran_results = [r for r in results if not r.get("governance_blocked", False)]
    normal_closed = [p for p, r in zip(all_closed, ran_results) if r["category"] == "NORMAL"]
    stress_closed = [p for p, r in zip(all_closed, ran_results) if r["category"] == "STRESS"]

    if governance_engine is not None:
        blocked_count = sum(1 for r in results if r.get("governance_blocked", False))
        print(f"\n  Governance: blocked {blocked_count} / {len(results)} scenarios")

    print(f"\n  Normal scenarios: {len(normal_closed)}")
    print(f"  Stress scenarios: {len(stress_closed)}")

    print("\n── Computing metrics (equity-based DD) ──")
    combined_metrics = compute_metrics(all_closed, DEFAULT_START_EQUITY)
    normal_metrics = compute_metrics(normal_closed, DEFAULT_START_EQUITY) if normal_closed else _empty_metrics()
    stress_metrics = compute_metrics(stress_closed, DEFAULT_START_EQUITY) if stress_closed else _empty_metrics()

    # Print
    print(f"\n  ── COMBINED ──")
    _print_metrics(combined_metrics)
    print(f"\n  ── NORMAL ──")
    _print_metrics(normal_metrics)
    print(f"\n  ── STRESS ──")
    _print_metrics(stress_metrics)

    # Verify no order_send
    import titan.production.virtual_position_ledger as vpl
    import inspect
    src = inspect.getsource(vpl)
    order_send_safe = "import MetaTrader5" not in src and "mt5.order_send" not in src

    # Verdict
    if not order_send_safe:
        verdict = "BLOCKED"
    else:
        verdict = "VIRTUAL_LIFECYCLE_READY"

    # Demo gate
    demo_gate = _demo_gate(combined_metrics, normal_metrics, order_send_safe)

    print(f"\n  {'=' * 50}")
    print(f"  VERDICT:     {verdict}")
    print(f"  DEMO_GATE:   {demo_gate}")
    print(f"  order_send:  {'NO' if order_send_safe else 'YES'}")
    print(f"  {'=' * 50}")

    # Save reports
    report = {
        "audit": "sprint_9_8_1_virtual_lifecycle_fixed",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "demo_gate": demo_gate,
        "order_send_used": not order_send_safe,
        "live_execution_touched": False,
        "combined_metrics": combined_metrics,
        "normal_metrics": normal_metrics,
        "stress_metrics": stress_metrics,
        "scenarios": results,
    }
    if governance_engine is not None:
        report["governance_enabled"] = True
        report["governance_profile"] = governance_engine.account_profile
        report["governance_decisions"] = governance_decisions
        report["governance_blocked_count"] = sum(
            1 for r in results if r.get("governance_blocked", False))
    else:
        report["governance_enabled"] = False
    json_path = out_dir / "virtual_lifecycle_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    md_path = out_dir / "virtual_lifecycle_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Sprint 9.8.1 — Virtual Lifecycle Report (Fixed DD)\n\n")
        f.write(f"**Verdict: {verdict}**\n\n")
        f.write(f"**Demo Gate: {demo_gate}**\n\n")
        f.write(f"**Order_send used: {not order_send_safe}**\n\n")
        f.write(f"## Normal Metrics\n\n| Metric | Value |\n|---|---|\n")
        for k, v in normal_metrics.items():
            f.write(f"| {k} | {v} |\n")
        f.write(f"\n## Stress Metrics\n\n| Metric | Value |\n|---|---|\n")
        for k, v in stress_metrics.items():
            f.write(f"| {k} | {v} |\n")
        f.write(f"\n## Combined Metrics\n\n| Metric | Value |\n|---|---|\n")
        for k, v in combined_metrics.items():
            f.write(f"| {k} | {v} |\n")

    print(f"\n  JSON: {json_path}")
    print(f"  MD:   {md_path}")
    print(f"  Journal: {journal_path}")


def _print_metrics(m):
    print(f"    Net PnL:          ${m['net_pnl_total']:.2f}")
    print(f"    Win rate:          {m['win_rate_net']}%")
    print(f"    Profit factor:     {m['profit_factor_net']}")
    print(f"    Max DD (USD):      ${m['max_drawdown_usd']:.2f}")
    print(f"    Max DD (% equity): {m['max_drawdown_pct_of_start_equity']}%")
    print(f"    Max DD (% peak):   {m['max_drawdown_pct_of_peak_equity']}%")
    print(f"    Expectancy:        ${m['expectancy_net']:.4f}")
    print(f"    Cost drag:         {m['cost_drag_pct']}%")


def _demo_gate(combined, normal, order_send_safe):
    """Evaluate demo micro readiness."""
    if not order_send_safe:
        return "DEMO_MICRO_BLOCKED"
    if combined["net_pnl_total"] <= 0:
        return "DEMO_MICRO_BLOCKED"
    if combined["profit_factor_net"] < 1.2:
        return "DEMO_MICRO_BLOCKED"
    if combined["win_rate_net"] < 40:
        return "DEMO_MICRO_BLOCKED"
    if combined["expectancy_net"] <= 0:
        return "DEMO_MICRO_BLOCKED"
    if combined["cost_drag_pct"] > 35:
        return "DEMO_MICRO_BLOCKED"
    if normal["max_drawdown_pct_of_start_equity"] > 5.0:
        return "NEEDS_RISK_REVIEW"
    return "DEMO_MICRO_READY"


if __name__ == "__main__":
    main()
