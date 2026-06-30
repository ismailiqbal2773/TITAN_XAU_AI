#!/usr/bin/env python3
"""
TITAN XAU AI - Post-Trade Verification (Sprint 9.9.3.44.4)
============================================================
Passive MT5 check only. Never sends orders.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"


def run_verification() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings = []

    # Try passive MT5 check
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return {
                "timestamp_utc": ts,
                "verdict": "DEMO_MICRO_NO_POSITION_FOUND",
                "reason": "MT5 not available or initialize failed",
                "ok_checks": [],
                "blockers": [],
                "warnings": ["MT5 not available - cannot verify position"],
            }

        # Verify account DEMO
        acc = mt5.account_info()
        if acc is not None:
            if hasattr(acc, "trade_mode") and acc.trade_mode != 0:  # 0 = DEMO
                blockers.append("Account is not DEMO mode")
            else:
                ok_checks.append("Account is DEMO mode")

        # Verify XAUUSD positions
        positions = mt5.positions_get(symbol="XAUUSD")
        mt5.shutdown()

        if positions is None or len(positions) == 0:
            return {
                "timestamp_utc": ts,
                "verdict": "DEMO_MICRO_NO_POSITION_FOUND",
                "reason": "No XAUUSD positions found",
                "ok_checks": ok_checks,
                "blockers": blockers,
                "warnings": warnings,
            }

        pos_count = len(positions)
        if pos_count > 1:
            blockers.append(f"Too many positions: {pos_count} (expected 0 or 1)")
        else:
            ok_checks.append(f"Exactly 1 XAUUSD position found")

        # Check position details
        for pos in positions:
            vol = getattr(pos, "volume", 0)
            if vol > 0.01:
                blockers.append(f"Position volume {vol} > 0.01")
            else:
                ok_checks.append(f"Position volume {vol} <= 0.01")

            sl = getattr(pos, "sl", 0)
            tp = getattr(pos, "tp", 0)
            if sl == 0:
                warnings.append("Position has no SL")
            else:
                ok_checks.append(f"Position SL={sl}")
            if tp == 0:
                warnings.append("Position has no TP")
            else:
                ok_checks.append(f"Position TP={tp}")

        if blockers:
            verdict = "DEMO_MICRO_POSITION_BLOCKED"
        elif warnings:
            verdict = "DEMO_MICRO_POSITION_WARNING"
        else:
            verdict = "DEMO_MICRO_POSITION_VERIFIED"

        return {
            "timestamp_utc": ts,
            "verdict": verdict,
            "position_count": pos_count,
            "ok_checks": ok_checks,
            "blockers": blockers,
            "warnings": warnings,
        }

    except ImportError:
        return {
            "timestamp_utc": ts,
            "verdict": "DEMO_MICRO_NO_POSITION_FOUND",
            "reason": "MetaTrader5 not installed",
            "ok_checks": [],
            "blockers": [],
            "warnings": ["MetaTrader5 not available - cannot verify position"],
        }
    except Exception as e:
        return {
            "timestamp_utc": ts,
            "verdict": "DEMO_MICRO_NO_POSITION_FOUND",
            "reason": f"Verification error: {e}",
            "ok_checks": [],
            "blockers": [],
            "warnings": [f"Verification error: {e}"],
        }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "post_trade_verification.json"
    md_path = OUTPUT_DIR / "post_trade_verification.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Post-Trade Verification\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        if result.get("position_count") is not None:
            f.write(f"**Position Count:** {result['position_count']}\n\n")
        if result.get("ok_checks"):
            f.write("## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Post-Trade Verification (Sprint 9.9.3.44.4)")
    print("=" * 70)
    result = run_verification()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
