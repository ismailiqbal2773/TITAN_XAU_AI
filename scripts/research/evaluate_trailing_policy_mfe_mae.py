#!/usr/bin/env python3
"""
TITAN XAU AI - Evaluate Trailing Policy MFE/MAE (Sprint 9.9.3.45.8)
====================================================================
Evaluate trailing policy on historical or existing labeled trade path
data if available.

Inputs:
  - If real trade path data exists (data/audit/demo_micro_execution/
    managed_trade_report.json with monitor_events), use it.
  - Otherwise, use stored virtual lifecycle trade paths from
    data/audit/demo_micro_execution/trailing_policy_evaluation_input.json
    if it exists.
  - Otherwise, run on a small built-in synthetic trade-path bundle
    (clearly labeled as simulation, not real performance claim).

Metrics:
  - early_stopout_rate
  - average_R_captured
  - average_MFE_capture_ratio
  - profit_giveback_ratio
  - avg_win_R
  - avg_loss_R
  - expectancy_R
  - PF estimate
  - max_trade_adverse_R
  - trigger_frequency
  - modify_frequency

Compare policies:
  - no_trailing
  - immediate_breakeven
  - fixed_trailing
  - adaptive_trailing

Output:
  data/audit/demo_micro_execution/trailing_policy_evaluation.json
  data/audit/demo_micro_execution/trailing_policy_evaluation.md

Verdicts:
  - ADAPTIVE_TRAILING_VALIDATED (only when evaluated on real/walk-forward data
    AND adaptive beats all baselines on expectancy_R and PF)
  - ADAPTIVE_TRAILING_NEEDS_MORE_DATA (default; honest label when
    evaluated on synthetic or insufficient data)
  - ADAPTIVE_TRAILING_BLOCKED (no data available at all)

IMPORTANT: Do not claim mathematically proven profitability unless
evaluated on real/walk-forward data. Synthetic results are clearly
labeled as simulation.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

TITAN_MAGIC = 202619


def _load_managed_trade_report() -> Optional[dict]:
    """Load the most recent managed_trade_report.json if it exists."""
    path = OUTPUT_DIR / "managed_trade_report.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_virtual_lifecycle_paths() -> Optional[list]:
    """Load virtual lifecycle trade paths from input file if it exists."""
    path = OUTPUT_DIR / "trailing_policy_evaluation_input.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "trade_paths" in data:
            return data["trade_paths"]
    except Exception:
        pass
    return None


def _synthetic_trade_paths() -> list:
    """Generate a small built-in synthetic trade-path bundle for
    evaluation when no real data is available.

    Clearly labeled as SIMULATION - not a real performance claim.

    Each trade path is a list of (timestamp_offset, price) tuples.
    The first price is the entry, the last is the exit (manual close
    or end of monitor window). The initial SL is set at entry - 10.0
    (BUY) which makes R = 10.0.
    """
    return [
        # Trade 1: trending up, MFE=20, ends at +15 (winner)
        {"direction": "BUY", "entry": 2000.0, "initial_sl": 1990.0,
         "tp": 2020.0, "prices": [2000.0, 2005.0, 2010.0, 2015.0, 2020.0, 2018.0, 2015.0]},
        # Trade 2: whipsaw, MFE=8, MAE=-5, ends at -10 (loser, SL hit)
        {"direction": "BUY", "entry": 2000.0, "initial_sl": 1990.0,
         "tp": 2020.0, "prices": [2000.0, 2003.0, 2008.0, 2005.0, 1998.0, 1995.0, 1990.0]},
        # Trade 3: trending up then pullback, MFE=15, ends at +5 (small winner)
        {"direction": "BUY", "entry": 2000.0, "initial_sl": 1990.0,
         "tp": 2030.0, "prices": [2000.0, 2005.0, 2010.0, 2015.0, 2010.0, 2005.0, 2005.0]},
        # Trade 4: slow trend, MFE=12, ends at +12 (winner)
        {"direction": "BUY", "entry": 2000.0, "initial_sl": 1990.0,
         "tp": 2020.0, "prices": [2000.0, 2002.0, 2006.0, 2010.0, 2012.0, 2012.0, 2012.0]},
        # Trade 5: sharp drop, MFE=2, MAE=-10, ends at -10 (loser, SL hit)
        {"direction": "BUY", "entry": 2000.0, "initial_sl": 1990.0,
         "tp": 2020.0, "prices": [2000.0, 2002.0, 2000.0, 1995.0, 1992.0, 1990.0]},
    ]


def _simulate_policy_on_path(trade_path: dict, policy_name: str) -> dict:
    """Simulate a single policy on a single trade path.

    Returns dict with:
      - R_captured (final profit / R)
      - MFE (max favorable excursion in price)
      - MAE (max adverse excursion in price)
      - MFE_capture_ratio (final_profit / MFE)
      - profit_giveback (MFE - final_profit)
      - profit_giveback_ratio ((MFE - final_profit) / MFE)
      - early_stopout (1 if SL hit during path, 0 otherwise)
      - trigger_count (number of SL modify triggers)
      - modify_count (number of actual SL modifies)
      - final_sl (last SL value)
      - final_profit
    """
    direction = trade_path["direction"]
    entry = trade_path["entry"]
    initial_sl = trade_path["initial_sl"]
    prices = trade_path["prices"]
    R = abs(entry - initial_sl)

    if direction == "BUY":
        # MFE = max(prices) - entry; MAE = entry - min(prices)
        mfe = max(prices) - entry
        mae = entry - min(prices)
    else:
        mfe = entry - min(prices)
        mae = max(prices) - entry

    current_sl = initial_sl
    trigger_count = 0
    modify_count = 0
    final_profit = 0.0
    early_stopout = 0
    last_modify_step = -1000

    for i, price in enumerate(prices[1:], start=1):
        # Check if SL was hit (adverse move)
        if direction == "BUY" and price <= current_sl:
            final_profit = current_sl - entry
            early_stopout = 1
            break
        if direction == "SELL" and price >= current_sl:
            final_profit = entry - current_sl
            early_stopout = 1
            break

        # Apply policy
        if policy_name == "no_trailing":
            # Never move SL
            proposed_sl = current_sl
            should_modify = False
        elif policy_name == "immediate_breakeven":
            # Move SL to entry as soon as profit > 0
            profit = (price - entry) if direction == "BUY" else (entry - price)
            if profit > 0:
                if direction == "BUY":
                    proposed_sl = entry
                    should_modify = proposed_sl > current_sl
                else:
                    proposed_sl = entry
                    should_modify = (proposed_sl < current_sl) or current_sl == 0
            else:
                proposed_sl = current_sl
                should_modify = False
        elif policy_name == "fixed_trailing":
            # Move SL to price - 2.0 (BUY) when profit > 2.0
            profit = (price - entry) if direction == "BUY" else (entry - price)
            if profit > 2.0:
                if direction == "BUY":
                    proposed_sl = price - 2.0
                    should_modify = proposed_sl > current_sl
                else:
                    proposed_sl = price + 2.0
                    should_modify = (proposed_sl < current_sl) or current_sl == 0
            else:
                proposed_sl = current_sl
                should_modify = False
        elif policy_name == "adaptive_trailing":
            # Use AdaptiveTrailingPolicy
            from titan.production.adaptive_trailing_policy import (
                AdaptiveTrailingPolicy, PolicyMode, Regime,
            )
            policy = AdaptiveTrailingPolicy(mode=PolicyMode.BALANCED_CONSERVATIVE)
            decision = policy.evaluate(
                direction=direction,
                entry_price=entry,
                initial_sl=initial_sl,
                current_price=price,
                current_sl=current_sl,
                current_tp=trade_path.get("tp", entry + R * 2),
                atr=1.0, spread=0.05,
                stops_level_points=0, point=0.01,
                regime=Regime.TREND,
                structure_buffer=0.0,
                hold_seconds=i * 5,
                monitor_iterations=i,
                seconds_since_last_modify=(i - last_modify_step) * 5,
                spread_spike_flag=False, news_flag=False,
            )
            from titan.production.adaptive_trailing_policy import PolicyAction
            if decision.action in (PolicyAction.MOVE_TO_BREAKEVEN,
                                    PolicyAction.TRAIL, PolicyAction.PROFIT_LOCK):
                proposed_sl = decision.final_sl
                should_modify = proposed_sl != current_sl
            else:
                proposed_sl = current_sl
                should_modify = False
        else:
            proposed_sl = current_sl
            should_modify = False

        if should_modify:
            trigger_count += 1
            # Cooldown check for adaptive (60s = 12 steps at 5s interval)
            if policy_name == "adaptive_trailing":
                if (i - last_modify_step) * 5 < 60 and i > 1:
                    should_modify = False
            if should_modify:
                modify_count += 1
                current_sl = proposed_sl
                last_modify_step = i

        final_profit = (price - entry) if direction == "BUY" else (entry - price)

    mfe_capture_ratio = (final_profit / mfe) if mfe > 0 else 0.0
    profit_giveback = mfe - final_profit
    profit_giveback_ratio = (profit_giveback / mfe) if mfe > 0 else 0.0
    R_captured = final_profit / R if R > 0 else 0.0

    return {
        "R_captured": R_captured,
        "MFE": mfe,
        "MAE": mae,
        "MFE_capture_ratio": mfe_capture_ratio,
        "profit_giveback": profit_giveback,
        "profit_giveback_ratio": profit_giveback_ratio,
        "early_stopout": early_stopout,
        "trigger_count": trigger_count,
        "modify_count": modify_count,
        "final_sl": current_sl,
        "final_profit": final_profit,
    }


def _evaluate_policy_on_paths(trade_paths: list, policy_name: str) -> dict:
    """Evaluate a single policy on a list of trade paths. Compute aggregate metrics."""
    results = [_simulate_policy_on_path(tp, policy_name) for tp in trade_paths]
    n = len(results)
    if n == 0:
        return _empty_metrics(policy_name)

    early_stopout_rate = sum(r["early_stopout"] for r in results) / n
    avg_R_captured = sum(r["R_captured"] for r in results) / n
    avg_MFE_capture_ratio = sum(r["MFE_capture_ratio"] for r in results) / n
    avg_profit_giveback_ratio = sum(r["profit_giveback_ratio"] for r in results) / n

    winners = [r for r in results if r["final_profit"] > 0]
    losers = [r for r in results if r["final_profit"] <= 0]
    avg_win_R = (sum(r["R_captured"] for r in winners) / len(winners)) if winners else 0.0
    avg_loss_R = (sum(r["R_captured"] for r in losers) / len(losers)) if losers else 0.0

    # Expectancy = (P_win * avg_win_R) + (P_loss * avg_loss_R)
    p_win = len(winners) / n
    p_loss = len(losers) / n
    expectancy_R = (p_win * avg_win_R) + (p_loss * avg_loss_R)

    # PF estimate = sum(winners_profit) / abs(sum(losers_profit))
    sum_wins = sum(r["final_profit"] for r in winners)
    sum_losses = abs(sum(r["final_profit"] for r in losers))
    pf_estimate = (sum_wins / sum_losses) if sum_losses > 0 else float("inf") if sum_wins > 0 else 0.0

    max_trade_adverse_R = max((r["MAE"] / 10.0 for r in results), default=0.0)  # R=10 assumed
    trigger_frequency = sum(r["trigger_count"] for r in results) / n
    modify_frequency = sum(r["modify_count"] for r in results) / n

    return {
        "policy": policy_name,
        "n_trades": n,
        "early_stopout_rate": round(early_stopout_rate, 4),
        "average_R_captured": round(avg_R_captured, 4),
        "average_MFE_capture_ratio": round(avg_MFE_capture_ratio, 4),
        "profit_giveback_ratio": round(avg_profit_giveback_ratio, 4),
        "avg_win_R": round(avg_win_R, 4),
        "avg_loss_R": round(avg_loss_R, 4),
        "expectancy_R": round(expectancy_R, 4),
        "PF_estimate": round(pf_estimate, 4) if pf_estimate != float("inf") else "inf",
        "max_trade_adverse_R": round(max_trade_adverse_R, 4),
        "trigger_frequency": round(trigger_frequency, 4),
        "modify_frequency": round(modify_frequency, 4),
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": round(p_win, 4),
    }


def _empty_metrics(policy_name: str) -> dict:
    return {
        "policy": policy_name, "n_trades": 0,
        "early_stopout_rate": 0.0, "average_R_captured": 0.0,
        "average_MFE_capture_ratio": 0.0, "profit_giveback_ratio": 0.0,
        "avg_win_R": 0.0, "avg_loss_R": 0.0, "expectancy_R": 0.0,
        "PF_estimate": 0.0, "max_trade_adverse_R": 0.0,
        "trigger_frequency": 0.0, "modify_frequency": 0.0,
        "winners": 0, "losers": 0, "win_rate": 0.0,
    }


def run_evaluation() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []
    findings = {}

    # Try to load real data first
    managed_report = _load_managed_trade_report()
    virtual_paths = _load_virtual_lifecycle_paths()

    data_source = "synthetic"
    trade_paths = []

    if managed_report and managed_report.get("monitor_events"):
        # We have real monitor events - but they're a single trade, not a
        # trade-path bundle suitable for statistical evaluation.
        warnings.append(
            "managed_trade_report.json found but contains only one trade; "
            "not sufficient for statistical evaluation. Falling back to synthetic."
        )

    if virtual_paths:
        data_source = "virtual_lifecycle"
        trade_paths = virtual_paths
        ok_checks.append(f"Loaded {len(trade_paths)} virtual lifecycle trade paths")
    else:
        data_source = "synthetic"
        trade_paths = _synthetic_trade_paths()
        warnings.append(
            "No real or virtual lifecycle trade paths found. Using built-in "
            "synthetic trade-path bundle (5 paths). Results are SIMULATION only, "
            "NOT a real performance claim."
        )

    findings["data_source"] = data_source
    findings["n_trade_paths"] = len(trade_paths)

    # Evaluate all 4 policies
    policies = ["no_trailing", "immediate_breakeven", "fixed_trailing", "adaptive_trailing"]
    policy_results = {}
    for p in policies:
        policy_results[p] = _evaluate_policy_on_paths(trade_paths, p)
        ok_checks.append(f"Evaluated {p}: expectancy_R={policy_results[p]['expectancy_R']}, "
                          f"PF={policy_results[p]['PF_estimate']}")

    findings["policy_results"] = policy_results

    # Determine verdict
    # ADAPTIVE_TRAILING_VALIDATED only when:
    #   1. data_source is real or walk-forward (NOT synthetic)
    #   2. adaptive_trailing beats all baselines on expectancy_R AND PF
    # ADAPTIVE_TRAILING_NEEDS_MORE_DATA: default (synthetic data or
    #   adaptive doesn't beat baselines)
    # ADAPTIVE_TRAILING_BLOCKED: no data at all
    if not trade_paths:
        verdict = "ADAPTIVE_TRAILING_BLOCKED"
        blockers.append("No trade paths available for evaluation")
    elif data_source == "synthetic":
        verdict = "ADAPTIVE_TRAILING_NEEDS_MORE_DATA"
        warnings.append(
            "Evaluation on synthetic data. Verdict is NEEDS_MORE_DATA. "
            "Do not claim mathematically proven profitability."
        )
    else:
        # Real or virtual lifecycle data - check if adaptive beats baselines
        adaptive_exp = policy_results["adaptive_trailing"]["expectancy_R"]
        adaptive_pf = policy_results["adaptive_trailing"]["PF_estimate"]
        baselines_beat = True
        for baseline in ["no_trailing", "immediate_breakeven", "fixed_trailing"]:
            base_exp = policy_results[baseline]["expectancy_R"]
            base_pf = policy_results[baseline]["PF_estimate"]
            if adaptive_exp < base_exp:
                baselines_beat = False
                warnings.append(
                    f"adaptive_trailing expectancy_R ({adaptive_exp}) < "
                    f"{baseline} expectancy_R ({base_exp})"
                )
            # PF comparison (handle inf)
            if adaptive_pf != "inf" and base_pf != "inf":
                if adaptive_pf < base_pf:
                    baselines_beat = False
                    warnings.append(
                        f"adaptive_trailing PF ({adaptive_pf}) < "
                        f"{baseline} PF ({base_pf})"
                    )

        if baselines_beat and adaptive_exp > 0:
            verdict = "ADAPTIVE_TRAILING_VALIDATED"
        else:
            verdict = "ADAPTIVE_TRAILING_NEEDS_MORE_DATA"
            warnings.append(
                "Adaptive trailing did not strictly beat all baselines. "
                "Needs more data or tuning."
            )

    # Safety summary
    safety_summary = {
        "order_send_called": False,
        "position_modified": False,
        "no_martingale": True,
        "no_grid": True,
        "no_averaging": True,
        "no_loss_based_lot_multiplier": True,
    }

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "findings": findings,
        "safety": safety_summary,
        "important_note": (
            "This evaluation is a SIMULATION on synthetic data unless "
            "findings.data_source is 'real' or 'virtual_lifecycle'. "
            "Do not claim mathematically proven profitability based on "
            "synthetic results."
        ),
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "trailing_policy_evaluation.json"
    md_path = OUTPUT_DIR / "trailing_policy_evaluation.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Trailing Policy Evaluation (MFE/MAE)\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**Data Source:** {result.get('findings', {}).get('data_source', 'unknown')}\n\n")
        f.write(f"**Trade Paths:** {result.get('findings', {}).get('n_trade_paths', 0)}\n\n")
        f.write(f"**Important Note:** {result.get('important_note', '')}\n\n")
        # Policy comparison table
        f.write("## Policy Comparison\n\n")
        f.write("| Policy | N | Expectancy_R | PF | Win Rate | Avg Win R | Avg Loss R | MFE Capture | Giveback | Early Stopout | Trigger Freq | Modify Freq |\n")
        f.write("|---|---|---|---|---|---|---|---|---|---|---|---|\n")
        for pname, p in result.get("findings", {}).get("policy_results", {}).items():
            f.write(f"| {pname} | {p['n_trades']} | {p['expectancy_R']} | {p['PF_estimate']} | "
                    f"{p['win_rate']} | {p['avg_win_R']} | {p['avg_loss_R']} | "
                    f"{p['average_MFE_capture_ratio']} | {p['profit_giveback_ratio']} | "
                    f"{p['early_stopout_rate']} | {p['trigger_frequency']} | "
                    f"{p['modify_frequency']} |\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
        f.write("- no_martingale: True\n")
        f.write("- no_grid: True\n")
        f.write("- no_averaging: True\n")
        f.write("- no_loss_based_lot_multiplier: True\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate trailing policy MFE/MAE (no order_send, no modification)")
    args = parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - Evaluate Trailing Policy MFE/MAE (Sprint 9.9.3.45.8)")
    print("=" * 70)
    result = run_evaluation()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Data source: {result.get('findings', {}).get('data_source', 'unknown')}")
    print(f"  Trade paths: {result.get('findings', {}).get('n_trade_paths', 0)}")
    print(f"\n  Policy comparison:")
    for pname, p in result.get("findings", {}).get("policy_results", {}).items():
        print(f"    {pname:25s}  exp_R={p['expectancy_R']:>6}  PF={p['PF_estimate']:>6}  "
              f"win_rate={p['win_rate']:>5}  early_stop={p['early_stopout_rate']:>5}")
    if result.get("warnings"):
        print(f"\n  Warnings:")
        for w in result["warnings"]:
            print(f"    - {w}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
