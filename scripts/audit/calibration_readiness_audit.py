#!/usr/bin/env python3
"""
TITAN XAU AI - Calibration Readiness Audit (Sprint 9.9.3.46)
=============================================================

Static readiness audit for the runtime calibration engine. Verifies the
module exists and defaults to OBSERVE_ONLY.

NEVER imports MetaTrader5. NEVER sends orders. Pure static / source audit.

Verdicts:
    - CALIBRATION_READY       : all checks pass
    - CALIBRATION_NEEDS_WORK  : warnings only
    - CALIBRATION_BLOCKED     : one or more blockers

Writes report to:
    data/audit/demo_micro_execution/calibration_readiness_audit.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    findings: dict = {}

    # ──────────────────────────────────────────────────────────────────
    # 1. Module exists
    # ──────────────────────────────────────────────────────────────────
    try:
        from titan.production.runtime_calibration_engine import (
            RuntimeCalibrationEngine,
            CalibrationMode,
            CalibrationSuggestion,
            CalibrationEngineResult,
        )
        ok_checks.append("RuntimeCalibrationEngine module imports cleanly")
        findings["engine_imports"] = True
    except Exception as e:  # pragma: no cover - audit-time only
        blockers.append(f"RuntimeCalibrationEngine import failed: {e}")
        findings["engine_imports"] = False
        # Bail out: cannot proceed without the module
        return {
            "timestamp_utc": ts,
            "verdict": "CALIBRATION_BLOCKED",
            "ok_checks": ok_checks,
            "blockers": blockers,
            "warnings": warnings,
            "findings": findings,
            "safety": {
                "order_send_called": False,
                "position_modified": False,
                "auto_promote_to_live": False,
                "no_martingale": True,
                "no_grid": True,
                "no_averaging": True,
            },
        }

    # ──────────────────────────────────────────────────────────────────
    # 2. Modes present
    # ──────────────────────────────────────────────────────────────────
    required_modes = [
        "OBSERVE_ONLY",
        "SUGGEST",
        "SHADOW_APPLY",
        "APPLY_DEMO_WITH_APPROVAL",
        "LIVE",
    ]
    modes = [m.value for m in CalibrationMode]
    missing_modes = [m for m in required_modes if m not in modes]
    if not missing_modes:
        ok_checks.append("All required calibration modes present")
        findings["modes_present"] = True
    else:
        blockers.append(f"Missing calibration modes: {missing_modes}")
        findings["modes_present"] = False

    # ──────────────────────────────────────────────────────────────────
    # 3. Default mode is OBSERVE_ONLY
    # ──────────────────────────────────────────────────────────────────
    engine_path = REPO_ROOT / "titan" / "production" / "runtime_calibration_engine.py"
    if engine_path.exists():
        eng_src = engine_path.read_text(encoding="utf-8")
        if "DEFAULT_MODE = CalibrationMode.OBSERVE_ONLY" in eng_src:
            ok_checks.append("DEFAULT_MODE = CalibrationMode.OBSERVE_ONLY present in source")
            findings["default_mode_constant"] = True
        else:
            blockers.append("DEFAULT_MODE constant for OBSERVE_ONLY missing")
            findings["default_mode_constant"] = False
    else:
        blockers.append(f"RuntimeCalibrationEngine source not found: {engine_path}")

    # Functional default mode check
    try:
        eng = RuntimeCalibrationEngine()
        if eng.mode == CalibrationMode.OBSERVE_ONLY:
            ok_checks.append("RuntimeCalibrationEngine defaults to OBSERVE_ONLY")
            findings["default_mode_functional"] = True
        else:
            blockers.append(
                f"RuntimeCalibrationEngine defaults to {eng.mode.value} - CRITICAL"
            )
            findings["default_mode_functional"] = False
    except Exception as e:
        blockers.append(f"RuntimeCalibrationEngine default mode check failed: {e}")
        findings["default_mode_functional"] = False

    # ──────────────────────────────────────────────────────────────────
    # 4. Initial non-default mode must be downgraded
    # ──────────────────────────────────────────────────────────────────
    try:
        eng2 = RuntimeCalibrationEngine(mode=CalibrationMode.LIVE)
        if eng2.mode == CalibrationMode.OBSERVE_ONLY:
            ok_checks.append(
                "RuntimeCalibrationEngine(initial_mode=LIVE) downgraded to OBSERVE_ONLY"
            )
            findings["initial_mode_downgrade"] = True
        else:
            blockers.append(
                f"RuntimeCalibrationEngine(initial_mode=LIVE) NOT downgraded - "
                f"got {eng2.mode.value} - CRITICAL"
            )
            findings["initial_mode_downgrade"] = False
    except Exception as e:
        blockers.append(f"RuntimeCalibrationEngine initial mode downgrade check failed: {e}")
        findings["initial_mode_downgrade"] = False

    # ──────────────────────────────────────────────────────────────────
    # 5. Safety invariants in source
    # ──────────────────────────────────────────────────────────────────
    if engine_path.exists():
        # No MetaTrader5 import
        if "import MetaTrader5" not in eng_src and "from MetaTrader5" not in eng_src:
            ok_checks.append("RuntimeCalibrationEngine: no MetaTrader5 import")
            findings["engine_no_mt5"] = True
        else:
            blockers.append("RuntimeCalibrationEngine: MetaTrader5 import found")
            findings["engine_no_mt5"] = False
        # No order_send - check stripped code (ignore docstring/string mentions)
        eng_code_stripped = _strip(eng_src)
        order_send_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        order_send_matches = re.findall(order_send_pattern, eng_code_stripped)
        if not order_send_matches:
            ok_checks.append("RuntimeCalibrationEngine: no order_send calls")
            findings["engine_no_order_send"] = True
        else:
            blockers.append(
                f"RuntimeCalibrationEngine: order_send call found: {order_send_matches}"
            )
            findings["engine_no_order_send"] = False
        # Safety invariant fields present
        safety_required = [
            "no_martingale",
            "no_grid",
            "no_averaging",
            "auto_promote_to_live",
            "silent_live_threshold_change",
        ]
        missing_safety = [s for s in safety_required if s not in eng_src]
        if not missing_safety:
            ok_checks.append("RuntimeCalibrationEngine: safety invariant fields present")
            findings["engine_safety_fields"] = True
        else:
            blockers.append(
                f"RuntimeCalibrationEngine: missing safety fields: {missing_safety}"
            )
            findings["engine_safety_fields"] = False
        # No martingale/grid/averaging/loss_based_lot_multiplier in stripped code
        eng_code = _strip(eng_src).lower()
        eng_check = eng_code.replace("no_martingale", "").replace("no_grid", "")
        eng_check = eng_check.replace("no_averaging", "").replace(
            "no_loss_based_lot_multiplier", ""
        )
        forbidden = [
            "martingale",
            "grid_trade",
            "averaging_down",
            "double_lot",
            "add_position",
            "loss_based_lot_multiplier",
            "recovery_multiplier",
        ]
        found_forbidden = [t for t in forbidden if t in eng_check]
        if not found_forbidden:
            ok_checks.append(
                "RuntimeCalibrationEngine: no martingale/grid/averaging/loss_based_lot"
            )
            findings["engine_no_forbidden_patterns"] = True
        else:
            blockers.append(
                f"RuntimeCalibrationEngine: forbidden patterns: {found_forbidden}"
            )
            findings["engine_no_forbidden_patterns"] = False
        # LIVE mode requires explicit approval
        if (
            "ceo_approval=True" in eng_src
            and "LIVE mode requires explicit ceo_approval=True" in eng_src
        ):
            ok_checks.append("RuntimeCalibrationEngine: LIVE requires ceo_approval=True")
            findings["engine_live_requires_ceo"] = True
        else:
            blockers.append(
                "RuntimeCalibrationEngine: LIVE mode ceo_approval requirement missing"
            )
            findings["engine_live_requires_ceo"] = False

    # ──────────────────────────────────────────────────────────────────
    # 6. Functional smoke: LIVE without ceo_approval blocked
    # ──────────────────────────────────────────────────────────────────
    try:
        eng3 = RuntimeCalibrationEngine()
        ok, blockers_3 = eng3.set_mode(CalibrationMode.LIVE, approved_by="someone")
        if not ok and any("ceo_approval" in b for b in blockers_3):
            ok_checks.append("RuntimeCalibrationEngine: LIVE without ceo_approval blocked")
            findings["engine_live_blocks_without_ceo"] = True
        else:
            blockers.append(
                "RuntimeCalibrationEngine: LIVE allowed without ceo_approval - CRITICAL"
            )
            findings["engine_live_blocks_without_ceo"] = False
    except Exception as e:
        blockers.append(f"RuntimeCalibrationEngine LIVE block check failed: {e}")
        findings["engine_live_blocks_without_ceo"] = False

    # ──────────────────────────────────────────────────────────────────
    # 7. Functional smoke: LIVE with ceo_approval approved
    # ──────────────────────────────────────────────────────────────────
    try:
        eng4 = RuntimeCalibrationEngine()
        ok, blockers_4 = eng4.set_mode(
            CalibrationMode.LIVE,
            approved_by="ceo@example.com",
            ceo_approval=True,
        )
        if ok and eng4.mode == CalibrationMode.LIVE:
            ok_checks.append("RuntimeCalibrationEngine: LIVE with ceo_approval approved")
            findings["engine_live_approves_with_ceo"] = True
        else:
            blockers.append(
                f"RuntimeCalibrationEngine: LIVE with ceo_approval rejected: {blockers_4}"
            )
            findings["engine_live_approves_with_ceo"] = False
    except Exception as e:
        blockers.append(f"RuntimeCalibrationEngine LIVE approval check failed: {e}")
        findings["engine_live_approves_with_ceo"] = False

    # ──────────────────────────────────────────────────────────────────
    # 8. OBSERVE_ONLY run_cycle emits no suggestions
    # ──────────────────────────────────────────────────────────────────
    try:
        eng5 = RuntimeCalibrationEngine()
        eng5.suggest("entry_threshold", 0.5, 0.55, reason="test")
        result = eng5.run_cycle({"sample_count": 1000})
        if (
            result.mode == CalibrationMode.OBSERVE_ONLY
            and result.applied is False
            and len(result.suggestions) == 0
        ):
            ok_checks.append(
                "RuntimeCalibrationEngine: OBSERVE_ONLY emits no suggestions"
            )
            findings["engine_observe_only_no_emit"] = True
        else:
            blockers.append(
                "RuntimeCalibrationEngine: OBSERVE_ONLY emitted suggestions - CRITICAL"
            )
            findings["engine_observe_only_no_emit"] = False
    except Exception as e:
        blockers.append(f"RuntimeCalibrationEngine OBSERVE_ONLY check failed: {e}")
        findings["engine_observe_only_no_emit"] = False

    # ──────────────────────────────────────────────────────────────────
    # 9. CalibrationSuggestion dataclass fields
    # ──────────────────────────────────────────────────────────────────
    try:
        s = CalibrationSuggestion(
            parameter_name="entry_threshold",
            current_value=0.5,
            suggested_value=0.55,
            mode=CalibrationMode.SUGGEST,
        )
        required_fields = [
            "parameter_name",
            "current_value",
            "suggested_value",
            "mode",
            "approved",
        ]
        missing_fields = [f for f in required_fields if not hasattr(s, f)]
        if missing_fields:
            blockers.append(
                f"CalibrationSuggestion missing fields: {missing_fields}"
            )
            findings["suggestion_fields"] = False
        elif s.approved is not False:
            blockers.append(
                "CalibrationSuggestion.approved is not False by default - CRITICAL"
            )
            findings["suggestion_fields"] = False
        else:
            ok_checks.append("CalibrationSuggestion has required fields and approved=False default")
            findings["suggestion_fields"] = True
    except Exception as e:
        blockers.append(f"CalibrationSuggestion check failed: {e}")
        findings["suggestion_fields"] = False

    # ──────────────────────────────────────────────────────────────────
    # Verdict
    # ──────────────────────────────────────────────────────────────────
    if blockers:
        verdict = "CALIBRATION_BLOCKED"
    elif warnings:
        verdict = "CALIBRATION_NEEDS_WORK"
    else:
        verdict = "CALIBRATION_READY"

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "findings": findings,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "auto_promote_to_live": False,
            "silent_live_threshold_change": False,
            "no_martingale": True,
            "no_grid": True,
            "no_averaging": True,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "calibration_readiness_audit.json"
    md_path = OUTPUT_DIR / "calibration_readiness_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Calibration Readiness Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write("## Findings\n\n")
        f.write("| Check | Status |\n|---|---|\n")
        for k, v in result.get("findings", {}).items():
            if isinstance(v, bool):
                status = "PASS" if v else "FAIL"
                f.write(f"| {k} | {status} |\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
        f.write("- auto_promote_to_live: False\n")
        f.write("- silent_live_threshold_change: False\n")
        f.write("- no_martingale: True\n")
        f.write("- no_grid: True\n")
        f.write("- no_averaging: True\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Calibration readiness audit (no MT5, no order_send)"
    )
    parser.parse_args()
    print("=" * 70)
    print("  TITAN XAU AI - Calibration Readiness Audit (Sprint 9.9.3.46)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  OK checks: {len(result.get('ok_checks', []))}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    if result.get("blockers"):
        print("\n  Blockers:")
        for b in result["blockers"]:
            print(f"    - {b}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0 if result["verdict"] == "CALIBRATION_READY" else 1


if __name__ == "__main__":
    sys.exit(main())
