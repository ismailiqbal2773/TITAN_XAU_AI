#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.28 Regime Detection Report Writer
===============================================================

Writes regime detection report to JSON + MD.

Output:
  data/audit/regime/regime_detection_report.json
  data/audit/regime/regime_detection_report.md
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "regime"
JSON_PATH = OUTPUT_DIR / "regime_detection_report.json"
MD_PATH = OUTPUT_DIR / "regime_detection_report.md"

from titan.production.regime_detection import (
    RegimeType, detect_regime, get_all_regime_decisions,
    get_regime_decision,
)


def write_report() -> dict:
    """Write regime detection report JSON + MD."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    decisions = get_all_regime_decisions()

    # Get current regime (safe default)
    current = detect_regime()

    report = {
        "timestamp_utc": timestamp,
        "current_regime": {
            "primary_regime": current.primary_regime.value,
            "secondary_regimes": [r.value for r in current.secondary_regimes],
            "confidence": current.confidence,
            "risk_multiplier": current.risk_multiplier,
            "allow_new_trade": current.allow_new_trade,
            "block_reason": current.block_reason,
            "session": current.session.value if current.session else None,
        },
        "supported_regimes": [r.value for r in RegimeType],
        "regime_decisions": decisions,
        "risk_multiplier_rules": {
            "max_risk_multiplier": 1.0,
            "rule": "Regime can ONLY reduce risk (multiplier <= 1.0), never increase.",
            "block_regimes": [r for r, d in decisions.items()
                              if not d.get("allow_new_trade", True)],
            "reduce_regimes": [r for r, d in decisions.items()
                               if d.get("risk_multiplier", 1.0) < 1.0
                               and d.get("allow_new_trade", True)],
        },
        "integration_hooks": {
            "ContextEngine": "TODO Sprint 9.9.4+",
            "TradeLoop": "TODO Sprint 9.9.4+",
            "DynamicRiskEngine": "TODO Sprint 9.9.4+",
            "MetaCalibration": "TODO Sprint 9.9.4+",
            "AIExitIntelligence": "TODO Sprint 9.9.4+",
            "BrokerCompatibilityMatrix": "TODO Sprint 9.9.4+",
            "Dashboard": "TODO Sprint 9.9.4+",
        },
        "warnings": [
            "Production trading behavior is NOT changed yet — regime detection is non-blocking foundation.",
            "Regime can only reduce risk or block unsafe trades — risk_multiplier never exceeds 1.0.",
            "Failed detection defaults to UNKNOWN with safe risk reduction (0.5 multiplier).",
        ],
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI — Regime Detection Report\n\n")
        f.write(f"**Generated:** {timestamp}\n\n")

        # Current regime
        f.write("## Current Regime (Safe Default)\n\n")
        f.write(f"| Field | Value |\n|---|---|\n")
        f.write(f"| Primary | {current.primary_regime.value} |\n")
        f.write(f"| Secondary | {', '.join(r.value for r in current.secondary_regimes) or 'None'} |\n")
        f.write(f"| Risk Multiplier | {current.risk_multiplier} |\n")
        f.write(f"| Allow New Trade | {current.allow_new_trade} |\n")
        f.write(f"| Block Reason | {current.block_reason or 'None'} |\n")
        f.write(f"| Session | {current.session.value if current.session else 'None'} |\n\n")

        # Supported regimes
        f.write("## Supported Regimes\n\n")
        f.write("| Regime | Risk Mult | Allow Trade | Block Reason | Note |\n")
        f.write("|---|---|---|---|---|\n")
        for r in RegimeType:
            d = decisions.get(r.value, {})
            f.write(f"| {r.value} | {d.get('risk_multiplier', 'N/A')} | "
                    f"{'✓' if d.get('allow_new_trade') else '✗'} | "
                    f"{d.get('block_reason') or 'None'} | {d.get('note', '')} |\n")

        # Risk rules
        f.write("\n## Risk Multiplier Rules\n\n")
        f.write("- **Maximum risk_multiplier: 1.0** (regime can only reduce, never increase)\n")
        f.write(f"- **Block regimes**: {', '.join(report['risk_multiplier_rules']['block_regimes'])}\n")
        f.write(f"- **Reduce regimes**: {', '.join(report['risk_multiplier_rules']['reduce_regimes'])}\n")

        # Integration hooks
        f.write("\n## Integration Hook Status\n\n")
        f.write("| Component | Status |\n|---|---|\n")
        for comp, status in report["integration_hooks"].items():
            f.write(f"| {comp} | {status} |\n")

        # Warnings
        f.write("\n## ⚠ Warnings\n\n")
        for w in report["warnings"]:
            f.write(f"- **{w}**\n")

    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main():
    print("=" * 70)
    print("  TITAN XAU AI — Regime Detection Report (Sprint 9.9.3.28)")
    print("=" * 70)
    result = write_report()
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")

    current = detect_regime()
    print(f"\n  Current regime: {current.primary_regime.value}")
    print(f"  Risk multiplier: {current.risk_multiplier}")
    print(f"  Allow new trade: {current.allow_new_trade}")
    print(f"\n  Supported regimes: {len(list(RegimeType))}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
