#!/usr/bin/env python3
"""
TITAN XAU AI — Sprint 9.9.3.29 Signal Execution Bridge Report Writer
=====================================================================

Writes signal execution bridge report to JSON + MD.

Output:
  data/audit/signal_bridge/signal_execution_bridge_report.json
  data/audit/signal_bridge/signal_execution_bridge_report.md
"""
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "signal_bridge"
JSON_PATH = OUTPUT_DIR / "signal_execution_bridge_report.json"
MD_PATH = OUTPUT_DIR / "signal_execution_bridge_report.md"

from titan.production.signal_execution_bridge import (
    SignalExecutionBridge, DecisionInput, ExecutionIntent, BridgeDecision,
    MIN_MODEL_CONFIDENCE, MIN_META_CONFIDENCE, MAX_LOT,
)


def write_report() -> dict:
    """Write signal execution bridge report JSON + MD."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()

    bridge = SignalExecutionBridge()

    # Sample approved demo intent
    approved_input = DecisionInput(
        symbol="XAUUSD", model_signal="BUY",
        model_confidence=0.75, meta_confidence=0.70, direction="BUY",
    )
    approved_regime = {"primary_regime": "TREND_UP", "risk_multiplier": 1.0,
                        "allow_new_trade": True, "block_reason": None}
    approved_broker = {"status": "PASS", "server_name": "MetaQuotes-Demo"}
    approved_health = {"status": "HEALTHY"}
    approved_security = {"allowed": True}
    approved_intent = bridge.build_intent(
        approved_input, regime_status=approved_regime,
        broker_info=approved_broker, runtime_health=approved_health,
        security_status=approved_security,
    )

    # Sample blocked intent (low confidence)
    blocked_input = DecisionInput(
        symbol="XAUUSD", model_signal="BUY",
        model_confidence=0.30, meta_confidence=0.40, direction="BUY",
    )
    blocked_intent = bridge.build_intent(blocked_input)

    report = {
        "timestamp_utc": timestamp,
        "bridge_config": {
            "dry_run": bridge.dry_run,
            "demo_only": bridge.demo_only,
            "min_model_confidence": bridge.min_model_confidence,
            "min_meta_confidence": bridge.min_meta_confidence,
            "max_lot": bridge.max_lot,
        },
        "pipeline_gates": [
            {"order": 1, "name": "validate_confidence", "description": "Model + meta confidence thresholds"},
            {"order": 2, "name": "apply_regime_gate", "description": "Regime can block or reduce risk"},
            {"order": 3, "name": "apply_broker_gate", "description": "Broker compatibility check"},
            {"order": 4, "name": "apply_runtime_health_gate", "description": "Runtime health must not be CRITICAL"},
            {"order": 5, "name": "apply_security_gate", "description": "SecurityGate must allow"},
            {"order": 6, "name": "apply_risk_limits", "description": "Lot cap (0.01), risk multiplier cap (1.0)"},
        ],
        "bridge_decisions": [d.value for d in BridgeDecision],
        "fail_closed_rules": [
            "Any gate failure → allowed=False",
            "Any exception → BLOCK_UNKNOWN with allowed=False",
            "risk_multiplier NEVER exceeds 1.0",
            "lot NEVER exceeds 0.01 in current phase",
            "dry_run=True by default",
            "demo_only=True by default",
            "Never calls mt5.order_send",
            "Never calls MT5ExecutionAdapter.send_order",
        ],
        "block_reasons": {
            "BLOCK_LOW_CONFIDENCE": "Model confidence below threshold",
            "BLOCK_META_REJECT": "Meta confidence below threshold",
            "BLOCK_REGIME": "Regime blocks new trades",
            "BLOCK_BROKER": "Broker BLOCKED or REJECT status",
            "BLOCK_RUNTIME_HEALTH": "Runtime health CRITICAL",
            "BLOCK_SECURITY": "SecurityGate release failure",
            "BLOCK_RISK_LIMIT": "Risk limits exceeded",
            "BLOCK_UNKNOWN": "Unknown error / fail-closed",
        },
        "sample_approved_demo_intent": {
            "allowed": approved_intent.allowed,
            "decision": approved_intent.decision,
            "symbol": approved_intent.symbol,
            "side": approved_intent.side,
            "lot": approved_intent.lot,
            "risk_multiplier": approved_intent.risk_multiplier,
            "confidence_final": approved_intent.confidence_final,
            "regime": approved_intent.regime,
            "broker_status": approved_intent.broker_status,
            "dry_run": approved_intent.dry_run,
            "demo_only": approved_intent.demo_only,
            "approval_reasons": approved_intent.approval_reasons,
        },
        "sample_blocked_intent": {
            "allowed": blocked_intent.allowed,
            "decision": blocked_intent.decision,
            "block_reasons": blocked_intent.block_reasons,
        },
        "integration_hooks": {
            "TradeLoop": "TODO Sprint 9.9.4+",
            "InferenceEngine": "TODO Sprint 9.9.4+",
            "DynamicRiskEngine": "TODO Sprint 9.9.4+",
            "RuntimeHealthMonitor": "TODO Sprint 9.9.4+",
            "BrokerCompatibilityMatrix": "TODO Sprint 9.9.4+",
            "SecurityGate": "TODO Sprint 9.9.4+",
            "RegimeDetection": "TODO Sprint 9.9.4+",
            "MT5ExecutionAdapter": "TODO Sprint 9.9.4+",
        },
        "warnings": [
            "No market execution occurs in this sprint — bridge only produces ExecutionIntent.",
            "Bridge does NOT call mt5.order_send or MT5ExecutionAdapter.send_order.",
            "Production trading behavior is NOT changed — bridge is non-blocking foundation.",
        ],
    }

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI — Signal Execution Bridge Report\n\n")
        f.write(f"**Generated:** {timestamp}\n\n")

        f.write("## Bridge Configuration\n\n")
        f.write("| Parameter | Value |\n|---|---|\n")
        for k, v in report["bridge_config"].items():
            f.write(f"| {k} | {v} |\n")

        f.write("\n## Pipeline Gates\n\n")
        f.write("| # | Gate | Description |\n|---|---|---|\n")
        for g in report["pipeline_gates"]:
            f.write(f"| {g['order']} | {g['name']} | {g['description']} |\n")

        f.write("\n## Bridge Decisions\n\n")
        for d in report["bridge_decisions"]:
            f.write(f"- `{d}`\n")

        f.write("\n## Fail-Closed Rules\n\n")
        for r in report["fail_closed_rules"]:
            f.write(f"- {r}\n")

        f.write("\n## Block Reasons\n\n")
        f.write("| Decision | Reason |\n|---|---|\n")
        for k, v in report["block_reasons"].items():
            f.write(f"| `{k}` | {v} |\n")

        f.write("\n## Sample Approved Demo Intent\n\n")
        s = report["sample_approved_demo_intent"]
        f.write(f"| Field | Value |\n|---|---|\n")
        for k, v in s.items():
            f.write(f"| {k} | {v} |\n")

        f.write("\n## Sample Blocked Intent\n\n")
        b = report["sample_blocked_intent"]
        f.write(f"- **Allowed:** {b['allowed']}\n")
        f.write(f"- **Decision:** {b['decision']}\n")
        f.write(f"- **Block Reasons:** {b['block_reasons']}\n")

        f.write("\n## Integration Hook Status\n\n")
        f.write("| Component | Status |\n|---|---|\n")
        for comp, status in report["integration_hooks"].items():
            f.write(f"| {comp} | {status} |\n")

        f.write("\n## ⚠ Warnings\n\n")
        for w in report["warnings"]:
            f.write(f"- **{w}**\n")

    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main():
    print("=" * 70)
    print("  TITAN XAU AI — Signal Execution Bridge Report (Sprint 9.9.3.29)")
    print("=" * 70)
    result = write_report()
    print(f"\n  JSON: {result['json_path']}")
    print(f"  MD:   {result['md_path']}")
    print(f"\n  Gates: 6 (confidence → regime → broker → health → security → risk)")
    print(f"  Decisions: {len(list(BridgeDecision))}")
    print(f"  dry_run=True, demo_only=True, max_lot=0.01")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
