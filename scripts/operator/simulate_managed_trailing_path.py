#!/usr/bin/env python3
"""
TITAN XAU AI - Simulate Managed Trailing Path (Sprint 9.9.3.45.8)
==================================================================
Test decision logic without real MT5 order or modification.

Sprint 9.9.3.45.8: Adds adaptive trailing policy scenarios with
R-multiple, ATR/noise buffer, regime, spread/stop-level buffers, and
hysteresis/cooldown.

Legacy scenarios (Sprint 9.9.3.45.6, kept for backwards compat):
  --scenario loss        -> HOLD (price moved against position)
  --scenario breakeven   -> MODIFY to breakeven/offset
  --scenario trailing    -> MODIFY favorable SL
  --scenario profit-lock -> MODIFY locked profit SL

Adaptive scenarios (Sprint 9.9.3.45.8):
  --scenario small_profit_noise_hold            -> HOLD (profit < noise threshold)
  --scenario profit_1R_breakeven                -> MODIFY (MOVE_TO_BREAKEVEN after 1R + noise clear)
  --scenario profit_1R_but_spread_spike_hold    -> HOLD (spread spike blocks breakeven)
  --scenario profit_1_5R_trend_hold_until_noise_clear -> HOLD (cooldown or noise)
  --scenario profit_2R_trend_trail_loose        -> MODIFY (TRAIL with wide ATR distance)
  --scenario profit_2R_range_trail_tighter      -> MODIFY (TRAIL with tighter ATR distance)
  --scenario profit_3R_profit_lock              -> MODIFY (PROFIT_LOCK)
  --scenario pullback_after_trail_no_widen      -> HOLD/BLOCKED (no SL widening on pullback)
  --scenario cooldown_blocks_repeated_modify    -> HOLD (cooldown active)
  --scenario minimum_step_blocks_tiny_modify    -> HOLD (step distance too small)

Output:
  data/audit/demo_micro_execution/simulated_trailing_path.json
  data/audit/demo_micro_execution/simulated_trailing_path.md

NO order_send. NO modification. Pure decision simulation.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

TITAN_MAGIC = 202619
TITAN_COMMENT = "TITAN_DEMO_MICRO"
TITAN_SYMBOL = "XAUUSD"


# === Legacy scenario definitions (Sprint 9.9.3.45.6) ===
# BUY position: entry 2000.0, SL 1990.0, TP 2010.0
LEGACY_SCENARIOS = {
    "loss": {
        "description": "Price moved against position (below entry). HOLD expected.",
        "direction": "BUY",
        "entry_price": 2000.0,
        "current_price": 1995.0,
        "current_sl": 1990.0,
        "current_tp": 2010.0,
        "expected_action": "HOLD",
    },
    "breakeven": {
        "description": "Price moved +1.5 above entry (past breakeven_trigger=1.0).",
        "direction": "BUY",
        "entry_price": 2000.0,
        "current_price": 2001.5,
        "current_sl": 1990.0,
        "current_tp": 2010.0,
        "expected_action": "MOVE_TO_BREAKEVEN",
    },
    "trailing": {
        "description": "Price moved +2.5 above entry (past trailing_trigger=2.0).",
        "direction": "BUY",
        "entry_price": 2000.0,
        "current_price": 2002.5,
        "current_sl": 1990.0,
        "current_tp": 2010.0,
        "expected_action": "TRAIL",
    },
    "profit-lock": {
        "description": "Price moved +3.5 above entry (past profit_lock_trigger=3.0).",
        "direction": "BUY",
        "entry_price": 2000.0,
        "current_price": 2003.5,
        "current_sl": 1990.0,
        "current_tp": 2010.0,
        "expected_action": "PROFIT_LOCK",
    },
}


# === Adaptive scenario definitions (Sprint 9.9.3.45.8) ===
# Common baseline: BUY, entry=2000.0, initial_sl=1990.0, R=10.0, TP=2010.0
# Adaptive scenarios use the AdaptiveTrailingPolicy (legacy_mode=False)
ADAPTIVE_SCENARIOS = {
    "small_profit_noise_hold": {
        "description": "Small profit (+0.3) below ATR noise threshold. HOLD expected.",
        "direction": "BUY", "entry_price": 2000.0, "initial_sl": 1990.0,
        "current_price": 2000.3, "current_sl": 1990.0, "current_tp": 2010.0,
        "atr": 1.0, "spread": 0.05, "stops_level_points": 0, "point": 0.01,
        "regime": "trend", "structure_buffer": 0.0,
        "hold_seconds": 120, "monitor_iterations": 5,
        "seconds_since_last_modify": 999, "spread_spike_flag": False, "news_flag": False,
        "expected_action": "HOLD",
    },
    "profit_1R_breakeven": {
        "description": "Profit = 1R (10.0) reached, noise clear, no spread spike. MOVE_TO_BREAKEVEN.",
        "direction": "BUY", "entry_price": 2000.0, "initial_sl": 1990.0,
        "current_price": 2010.0, "current_sl": 1990.0, "current_tp": 2020.0,
        "atr": 1.0, "spread": 0.05, "stops_level_points": 0, "point": 0.01,
        "regime": "trend", "structure_buffer": 0.0,
        "hold_seconds": 120, "monitor_iterations": 5,
        "seconds_since_last_modify": 999, "spread_spike_flag": False, "news_flag": False,
        "expected_action": "MOVE_TO_BREAKEVEN",
    },
    "profit_1R_but_spread_spike_hold": {
        "description": "Profit = 1R reached but spread spike flag active. HOLD.",
        "direction": "BUY", "entry_price": 2000.0, "initial_sl": 1990.0,
        "current_price": 2010.0, "current_sl": 1990.0, "current_tp": 2020.0,
        "atr": 1.0, "spread": 0.05, "stops_level_points": 0, "point": 0.01,
        "regime": "trend", "structure_buffer": 0.0,
        "hold_seconds": 120, "monitor_iterations": 5,
        "seconds_since_last_modify": 999, "spread_spike_flag": True, "news_flag": False,
        "expected_action": "HOLD",
    },
    "profit_1_5R_trend_hold_until_noise_clear": {
        "description": "Profit = 1.5R but cooldown active (recent modify). HOLD.",
        "direction": "BUY", "entry_price": 2000.0, "initial_sl": 1990.0,
        "current_price": 2015.0, "current_sl": 1990.0, "current_tp": 2030.0,
        "atr": 1.0, "spread": 0.05, "stops_level_points": 0, "point": 0.01,
        "regime": "trend", "structure_buffer": 0.0,
        "hold_seconds": 120, "monitor_iterations": 5,
        "seconds_since_last_modify": 10,  # Cooldown active
        "spread_spike_flag": False, "news_flag": False,
        "expected_action": "HOLD",
    },
    "profit_2R_trend_trail_loose": {
        "description": "Profit = 2R in trend regime. TRAIL with wide ATR distance.",
        "direction": "BUY", "entry_price": 2000.0, "initial_sl": 1990.0,
        "current_price": 2020.0, "current_sl": 1990.0, "current_tp": 2040.0,
        "atr": 1.0, "spread": 0.05, "stops_level_points": 0, "point": 0.01,
        "regime": "trend", "structure_buffer": 0.0,
        "hold_seconds": 120, "monitor_iterations": 5,
        "seconds_since_last_modify": 999, "spread_spike_flag": False, "news_flag": False,
        "expected_action": "TRAIL",
    },
    "profit_2R_range_trail_tighter": {
        "description": "Profit = 2R in range regime. TRAIL with tighter ATR distance.",
        "direction": "BUY", "entry_price": 2000.0, "initial_sl": 1990.0,
        "current_price": 2020.0, "current_sl": 1990.0, "current_tp": 2040.0,
        "atr": 1.0, "spread": 0.05, "stops_level_points": 0, "point": 0.01,
        "regime": "range", "structure_buffer": 0.0,
        "hold_seconds": 120, "monitor_iterations": 5,
        "seconds_since_last_modify": 999, "spread_spike_flag": False, "news_flag": False,
        "expected_action": "TRAIL",
    },
    "profit_3R_profit_lock": {
        "description": "Profit = 3R reached. PROFIT_LOCK.",
        "direction": "BUY", "entry_price": 2000.0, "initial_sl": 1990.0,
        "current_price": 2030.0, "current_sl": 2010.0, "current_tp": 2050.0,
        "atr": 1.0, "spread": 0.05, "stops_level_points": 0, "point": 0.01,
        "regime": "trend", "structure_buffer": 0.0,
        "hold_seconds": 120, "monitor_iterations": 5,
        "seconds_since_last_modify": 999, "spread_spike_flag": False, "news_flag": False,
        "expected_action": "PROFIT_LOCK",
    },
    "pullback_after_trail_no_widen": {
        "description": "Price pulled back after SL was trailed. New proposed SL would widen. HOLD/BLOCKED.",
        "direction": "BUY", "entry_price": 2000.0, "initial_sl": 1990.0,
        "current_price": 2015.0, "current_sl": 2018.0,  # SL already trailed up
        "current_tp": 2040.0,
        "atr": 1.0, "spread": 0.05, "stops_level_points": 0, "point": 0.01,
        "regime": "trend", "structure_buffer": 0.0,
        "hold_seconds": 120, "monitor_iterations": 5,
        "seconds_since_last_modify": 999, "spread_spike_flag": False, "news_flag": False,
        "expected_action": "HOLD",  # HOLD because proposed SL would widen
    },
    "cooldown_blocks_repeated_modify": {
        "description": "Recent modify (10s ago), cooldown=60s. HOLD.",
        "direction": "BUY", "entry_price": 2000.0, "initial_sl": 1990.0,
        "current_price": 2018.0, "current_sl": 1990.0, "current_tp": 2030.0,
        "atr": 1.0, "spread": 0.05, "stops_level_points": 0, "point": 0.01,
        "regime": "trend", "structure_buffer": 0.0,
        "hold_seconds": 120, "monitor_iterations": 5,
        "seconds_since_last_modify": 10,  # Within 60s cooldown
        "spread_spike_flag": False, "news_flag": False,
        "expected_action": "HOLD",
    },
    "minimum_step_blocks_tiny_modify": {
        "description": "Proposed SL improvement is below minimum_sl_step_distance. HOLD.",
        "direction": "BUY", "entry_price": 2000.0, "initial_sl": 1990.0,
        "current_price": 2010.05,  # Just slightly above 1R breakeven trigger
        "current_sl": 2001.0,  # SL already at breakeven+0.1; tiny step proposed
        "current_tp": 2020.0,
        "atr": 1.0, "spread": 0.05, "stops_level_points": 0, "point": 0.01,
        "regime": "trend", "structure_buffer": 0.0,
        "hold_seconds": 120, "monitor_iterations": 5,
        "seconds_since_last_modify": 999, "spread_spike_flag": False, "news_flag": False,
        "expected_action": "HOLD",
    },
}


def simulate_scenario(scenario: str) -> dict:
    """Run a synthetic decision simulation. No MT5, no order_send."""
    ts = datetime.now(timezone.utc).isoformat()

    # Try legacy scenarios first
    if scenario in LEGACY_SCENARIOS:
        return _simulate_legacy(scenario, ts)

    # Try adaptive scenarios
    if scenario in ADAPTIVE_SCENARIOS:
        return _simulate_adaptive(scenario, ts)

    return {
        "timestamp_utc": ts,
        "scenario": scenario,
        "verdict": "SIMULATION_BLOCKED",
        "blockers": [f"Unknown scenario: {scenario}"],
        "available_scenarios": list(LEGACY_SCENARIOS.keys()) + list(ADAPTIVE_SCENARIOS.keys()),
    }


def _simulate_legacy(scenario: str, ts: str) -> dict:
    """Run a legacy scenario using DemoMicroPositionManager (legacy_mode=True)."""
    cfg = LEGACY_SCENARIOS[scenario]
    from titan.production.demo_micro_position_manager import (
        DemoMicroPositionManager, SLAction,
    )
    from titan.production.demo_micro_sl_modify_builder import DemoMicroSLModifyBuilder

    mgr = DemoMicroPositionManager()  # legacy_mode=True by default
    builder = DemoMicroSLModifyBuilder()

    rec = mgr.evaluate(
        direction=cfg["direction"],
        entry_price=cfg["entry_price"],
        current_price=cfg["current_price"],
        current_sl=cfg["current_sl"],
        current_tp=cfg["current_tp"],
    )

    preview = builder.build_preview(
        ticket=999999,
        new_sl=rec.new_sl, tp=cfg["current_tp"],
        favorable=rec.favorable, reason=rec.reason,
        blockers=rec.blockers,
    )

    tp_preserved = rec.tp == cfg["current_tp"]
    favorable = rec.favorable
    if cfg["direction"] == "BUY":
        no_widening = rec.new_sl >= cfg["current_sl"]
    else:
        no_widening = rec.new_sl <= cfg["current_sl"] or cfg["current_sl"] == 0

    if rec.action == SLAction.HOLD:
        verdict = "SIMULATION_HOLD"
        action_label = "HOLD"
    elif rec.action == SLAction.BLOCKED:
        verdict = "SIMULATION_BLOCKED"
        action_label = "MODIFY_BLOCKED"
    else:
        if not tp_preserved:
            verdict = "SIMULATION_BLOCKED"
            action_label = "MODIFY_BLOCKED_TP_NOT_PRESERVED"
        elif not favorable:
            verdict = "SIMULATION_BLOCKED"
            action_label = "MODIFY_BLOCKED_UNFAVORABLE"
        elif not no_widening:
            verdict = "SIMULATION_BLOCKED"
            action_label = "MODIFY_BLOCKED_WIDENING"
        else:
            verdict = "SIMULATION_MODIFY"
            action_label = rec.action.value

    expected = cfg["expected_action"]
    matches_expected = rec.action.value == expected

    return {
        "timestamp_utc": ts,
        "scenario": scenario,
        "scenario_description": cfg["description"],
        "policy_mode": "legacy",
        "verdict": verdict,
        "action": action_label,
        "expected_action": expected,
        "matches_expected": matches_expected,
        "direction": cfg["direction"],
        "entry_price": cfg["entry_price"],
        "current_price": cfg["current_price"],
        "current_sl": cfg["current_sl"],
        "current_tp": cfg["current_tp"],
        "new_sl": rec.new_sl,
        "favorable": favorable,
        "tp_preserved": tp_preserved,
        "no_widening": no_widening,
        "modify_reason": rec.reason,
        "preview": preview,
        "blockers": rec.blockers,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "no_martingale": True,
            "no_grid": True,
            "no_averaging": True,
        },
        "important_note": "This is a SIMULATION only. No mt5.order_send was called. No position was modified.",
    }


def _simulate_adaptive(scenario: str, ts: str) -> dict:
    """Run an adaptive scenario using AdaptiveTrailingPolicy via
    DemoMicroPositionManager(legacy_mode=False)."""
    cfg = ADAPTIVE_SCENARIOS[scenario]
    from titan.production.demo_micro_position_manager import (
        DemoMicroPositionManager, SLAction,
    )
    from titan.production.adaptive_trailing_policy import Regime
    from titan.production.demo_micro_sl_modify_builder import DemoMicroSLModifyBuilder

    # Build adaptive manager with balanced_conservative mode (default for proof)
    mgr = DemoMicroPositionManager(legacy_mode=False)
    builder = DemoMicroSLModifyBuilder()

    # Map regime string to Regime enum
    regime_str = cfg.get("regime", "unknown")
    try:
        regime = Regime(regime_str)
    except ValueError:
        regime = Regime.UNKNOWN

    rec = mgr.evaluate(
        direction=cfg["direction"],
        entry_price=cfg["entry_price"],
        current_price=cfg["current_price"],
        current_sl=cfg["current_sl"],
        current_tp=cfg["current_tp"],
        stops_level_points=cfg.get("stops_level_points", 0),
        point=cfg.get("point", 0.01),
        initial_sl=cfg["initial_sl"],
        atr=cfg.get("atr", 0.0),
        spread=cfg.get("spread", 0.0),
        regime=regime,
        structure_buffer=cfg.get("structure_buffer", 0.0),
        hold_seconds=cfg.get("hold_seconds", 0),
        monitor_iterations=cfg.get("monitor_iterations", 0),
        seconds_since_last_modify=cfg.get("seconds_since_last_modify", 0),
        spread_spike_flag=cfg.get("spread_spike_flag", False),
        news_flag=cfg.get("news_flag", False),
    )

    preview = builder.build_preview(
        ticket=999999,
        new_sl=rec.new_sl, tp=cfg["current_tp"],
        favorable=rec.favorable, reason=rec.reason,
        blockers=rec.blockers,
    )

    tp_preserved = rec.tp == cfg["current_tp"]
    favorable = rec.favorable
    if cfg["direction"] == "BUY":
        no_widening = rec.new_sl >= cfg["current_sl"]
    else:
        no_widening = rec.new_sl <= cfg["current_sl"] or cfg["current_sl"] == 0

    if rec.action == SLAction.HOLD:
        verdict = "SIMULATION_HOLD"
        action_label = "HOLD"
    elif rec.action == SLAction.BLOCKED:
        verdict = "SIMULATION_BLOCKED"
        action_label = "MODIFY_BLOCKED"
    else:
        if not tp_preserved:
            verdict = "SIMULATION_BLOCKED"
            action_label = "MODIFY_BLOCKED_TP_NOT_PRESERVED"
        elif not favorable:
            verdict = "SIMULATION_BLOCKED"
            action_label = "MODIFY_BLOCKED_UNFAVORABLE"
        elif not no_widening:
            verdict = "SIMULATION_BLOCKED"
            action_label = "MODIFY_BLOCKED_WIDENING"
        else:
            verdict = "SIMULATION_MODIFY"
            action_label = rec.action.value

    expected = cfg["expected_action"]
    matches_expected = rec.action.value == expected

    return {
        "timestamp_utc": ts,
        "scenario": scenario,
        "scenario_description": cfg["description"],
        "policy_mode": "adaptive_balanced_conservative",
        "verdict": verdict,
        "action": action_label,
        "expected_action": expected,
        "matches_expected": matches_expected,
        "direction": cfg["direction"],
        "entry_price": cfg["entry_price"],
        "current_price": cfg["current_price"],
        "current_sl": cfg["current_sl"],
        "current_tp": cfg["current_tp"],
        "initial_sl": cfg["initial_sl"],
        "new_sl": rec.new_sl,
        "favorable": favorable,
        "tp_preserved": tp_preserved,
        "no_widening": no_widening,
        "modify_reason": rec.reason,
        "phase": rec.phase,
        "profit_R": rec.profit_R,
        "R": rec.R,
        "ATR_noise": rec.ATR_noise,
        "regime": rec.regime,
        "spread_buffer": rec.spread_buffer,
        "stop_level_buffer": rec.stop_level_buffer,
        "structure_buffer": rec.structure_buffer,
        "trailing_distance": rec.trailing_distance,
        "proposed_sl": rec.proposed_sl,
        "final_sl": rec.final_sl,
        "anti_whipsaw_blocks": rec.anti_whipsaw_blocks,
        "preview": preview,
        "blockers": rec.blockers,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "no_martingale": True,
            "no_grid": True,
            "no_averaging": True,
        },
        "important_note": "This is a SIMULATION only. No mt5.order_send was called. No position was modified.",
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "simulated_trailing_path.json"
    md_path = OUTPUT_DIR / "simulated_trailing_path.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Simulated Managed Trailing Path\n\n")
        f.write(f"**Scenario:** {result.get('scenario', 'unknown')}\n\n")
        f.write(f"**Policy Mode:** {result.get('policy_mode', 'unknown')}\n\n")
        f.write(f"**Verdict:** **{result.get('verdict', 'UNKNOWN')}**\n\n")
        f.write(f"**Action:** {result.get('action', 'N/A')}\n\n")
        f.write(f"**Expected:** {result.get('expected_action', 'N/A')}\n\n")
        f.write(f"**Matches Expected:** {result.get('matches_expected', False)}\n\n")
        f.write(f"**Timestamp:** {result.get('timestamp_utc', '')}\n\n")
        f.write(f"**Description:** {result.get('scenario_description', '')}\n\n")
        f.write("## Synthetic Position\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| direction | {result.get('direction', 'N/A')} |\n")
        f.write(f"| entry_price | {result.get('entry_price', 'N/A')} |\n")
        f.write(f"| current_price | {result.get('current_price', 'N/A')} |\n")
        f.write(f"| current_sl | {result.get('current_sl', 'N/A')} |\n")
        f.write(f"| current_tp | {result.get('current_tp', 'N/A')} |\n")
        if result.get("initial_sl") is not None:
            f.write(f"| initial_sl | {result.get('initial_sl', 'N/A')} |\n")
        f.write("\n## Decision\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| new_sl | {result.get('new_sl', 'N/A')} |\n")
        f.write(f"| favorable | {result.get('favorable', 'N/A')} |\n")
        f.write(f"| tp_preserved | {result.get('tp_preserved', 'N/A')} |\n")
        f.write(f"| no_widening | {result.get('no_widening', 'N/A')} |\n")
        f.write(f"| modify_reason | {result.get('modify_reason', 'N/A')} |\n")
        # Adaptive fields
        if result.get("policy_mode", "").startswith("adaptive"):
            f.write("\n## Adaptive Policy Fields\n\n")
            f.write("| Field | Value |\n|---|---|\n")
            f.write(f"| phase | {result.get('phase', 'N/A')} |\n")
            f.write(f"| profit_R | {result.get('profit_R', 'N/A')} |\n")
            f.write(f"| R | {result.get('R', 'N/A')} |\n")
            f.write(f"| ATR_noise | {result.get('ATR_noise', 'N/A')} |\n")
            f.write(f"| regime | {result.get('regime', 'N/A')} |\n")
            f.write(f"| spread_buffer | {result.get('spread_buffer', 'N/A')} |\n")
            f.write(f"| stop_level_buffer | {result.get('stop_level_buffer', 'N/A')} |\n")
            f.write(f"| structure_buffer | {result.get('structure_buffer', 'N/A')} |\n")
            f.write(f"| trailing_distance | {result.get('trailing_distance', 'N/A')} |\n")
            f.write(f"| proposed_sl | {result.get('proposed_sl', 'N/A')} |\n")
            f.write(f"| final_sl | {result.get('final_sl', 'N/A')} |\n")
            if result.get("anti_whipsaw_blocks"):
                f.write("\n## Anti-Whipsaw Blocks\n\n")
                for b in result["anti_whipsaw_blocks"]:
                    f.write(f"- {b}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- {b}\n")
        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
        f.write("- no_martingale: True\n")
        f.write("- no_grid: True\n")
        f.write("- no_averaging: True\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    all_scenarios = list(LEGACY_SCENARIOS.keys()) + list(ADAPTIVE_SCENARIOS.keys())
    parser = argparse.ArgumentParser(description="Simulate managed trailing path (no MT5, no order_send)")
    parser.add_argument("--scenario", required=True,
                        choices=all_scenarios,
                        help="Scenario to simulate")
    args = parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - Simulate Managed Trailing Path (Sprint 9.9.3.45.8)")
    print("=" * 70)
    result = simulate_scenario(args.scenario)
    report = write_report(result)
    print(f"\n  Scenario: {result.get('scenario', 'unknown')}")
    print(f"  Policy mode: {result.get('policy_mode', 'unknown')}")
    print(f"  Verdict: {result.get('verdict', 'UNKNOWN')}")
    print(f"  Action: {result.get('action', 'N/A')}")
    print(f"  Expected: {result.get('expected_action', 'N/A')}")
    print(f"  Matches expected: {result.get('matches_expected', False)}")
    print(f"  New SL: {result.get('new_sl', 'N/A')}")
    print(f"  TP preserved: {result.get('tp_preserved', 'N/A')}")
    print(f"  Favorable: {result.get('favorable', 'N/A')}")
    if result.get("policy_mode", "").startswith("adaptive"):
        print(f"  Phase: {result.get('phase', 'N/A')}")
        print(f"  profit_R: {result.get('profit_R', 'N/A')}")
        print(f"  Regime: {result.get('regime', 'N/A')}")
        if result.get("anti_whipsaw_blocks"):
            print(f"  Anti-whipsaw blocks: {len(result['anti_whipsaw_blocks'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
