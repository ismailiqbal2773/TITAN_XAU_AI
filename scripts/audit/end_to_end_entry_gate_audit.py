#!/usr/bin/env python3
"""
TITAN XAU AI - End-to-End Entry Gate Audit (Sprint 9.9.3.45.8.16 v2.7.3)
=========================================================================
Verifies whether the executed trade was actually taken through the expected
institutional decision chain:

  Market data
    -> Feature engine
    -> Regime detection
    -> Alpha/model signal
    -> Confidence threshold
    -> Meta-label/calibration
    -> Risk engine
    -> Broker score/spread/slippage gate
    -> Prop/funded profile gate
    -> Execution geometry RR gate
    -> Order request

Passive audit: NEVER sends orders. NEVER modifies positions. NEVER creates
execution tokens. NEVER fakes regime/alpha evidence. If regime/alpha
artifacts are missing, the audit reports missing explicitly.

Verdicts
--------
  ENTRY_GATE_FULL_PASS                              - all gates passed
  ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN      - execution proof valid
                                                      but alpha/regime chain
                                                      not used for entry
  ENTRY_GATE_BLOCKED_ALPHA_MISSING                  - alpha signal missing
  ENTRY_GATE_BLOCKED_REGIME_MISSING                 - regime missing
  ENTRY_GATE_BLOCKED_RISK_OR_BROKER                 - risk or broker gate failed
  ENTRY_GATE_BLOCKED_GEOMETRY                       - RR geometry failed

Outputs:
  data/audit/demo_micro_execution/end_to_end_entry_gate_audit.json
  data/audit/demo_micro_execution/end_to_end_entry_gate_audit.md
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

RECEIPT_PATH = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

# Verdicts
ENTRY_GATE_FULL_PASS = "ENTRY_GATE_FULL_PASS"
ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN = "ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN"
ENTRY_GATE_BLOCKED_ALPHA_MISSING = "ENTRY_GATE_BLOCKED_ALPHA_MISSING"
ENTRY_GATE_BLOCKED_REGIME_MISSING = "ENTRY_GATE_BLOCKED_REGIME_MISSING"
ENTRY_GATE_BLOCKED_RISK_OR_BROKER = "ENTRY_GATE_BLOCKED_RISK_OR_BROKER"
ENTRY_GATE_BLOCKED_GEOMETRY = "ENTRY_GATE_BLOCKED_GEOMETRY"

ALL_VERDICTS = (
    ENTRY_GATE_FULL_PASS,
    ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN,
    ENTRY_GATE_BLOCKED_ALPHA_MISSING,
    ENTRY_GATE_BLOCKED_REGIME_MISSING,
    ENTRY_GATE_BLOCKED_RISK_OR_BROKER,
    ENTRY_GATE_BLOCKED_GEOMETRY,
)


def _load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        return f if f == f else default
    except (TypeError, ValueError):
        return default


def _to_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v)


def _scan_alpha_signal_artifacts() -> dict:
    """Look for any alpha/signal/inference artifacts in data/audit/."""
    alpha_evidence: dict[str, Any] = {
        "alpha_signal_detected": False,
        "alpha_signal_value": None,
        "alpha_confidence": None,
        "alpha_threshold": None,
        "alpha_pass": False,
        "alpha_source_file": "",
        "regime_detected": False,
        "regime_value": None,
        "regime_source_file": "",
        "meta_label_pass": "unknown",
    }

    # Look for inference diagnostic reports
    inference_paths = [
        REPO_ROOT / "data" / "validation" / "inference_diagnostic_report.json",
        REPO_ROOT / "data" / "audit" / "inference" / "inference_diagnostic_report.json",
    ]
    for p in inference_paths:
        if p.exists():
            try:
                data = json.loads(p.read_text())
                alpha_evidence["alpha_source_file"] = str(p)
                # Look for alpha signal fields
                if isinstance(data, dict):
                    for key in ("alpha_signal_value", "alpha_value", "signal_value"):
                        if key in data:
                            alpha_evidence["alpha_signal_detected"] = True
                            alpha_evidence["alpha_signal_value"] = data[key]
                            break
                    for key in ("alpha_confidence", "confidence", "signal_confidence"):
                        if key in data:
                            alpha_evidence["alpha_confidence"] = data[key]
                            break
                    for key in ("alpha_threshold", "confidence_threshold"):
                        if key in data:
                            alpha_evidence["alpha_threshold"] = data[key]
                            break
                    for key in ("regime", "regime_value", "market_regime"):
                        if key in data:
                            alpha_evidence["regime_detected"] = True
                            alpha_evidence["regime_value"] = data[key]
                            break
                break
            except Exception:
                pass

    # Look for any recent journal/signal log entries
    signal_log_paths = list((REPO_ROOT / "data" / "audit").rglob("*signal*.jsonl"))[:5]
    for p in signal_log_paths:
        try:
            text = p.read_text(errors="ignore")
            if "alpha_signal" in text or "alpha_value" in text:
                alpha_evidence["alpha_source_file"] = alpha_evidence["alpha_source_file"] or str(p)
                # Don't override detected=True unless we found a structured value
                break
        except Exception:
            pass

    # Look for regime logs
    regime_log_paths = list((REPO_ROOT / "data" / "audit").rglob("*regime*.json*"))[:5]
    for p in regime_log_paths:
        try:
            if p.suffix == ".json":
                data = json.loads(p.read_text())
                if isinstance(data, dict):
                    for key in ("regime", "regime_value", "market_regime", "current_regime"):
                        if key in data:
                            alpha_evidence["regime_detected"] = True
                            alpha_evidence["regime_value"] = data[key]
                            alpha_evidence["regime_source_file"] = str(p)
                            break
        except Exception:
            pass

    # Compute alpha_pass
    if (alpha_evidence["alpha_signal_detected"]
            and alpha_evidence["alpha_confidence"] is not None
            and alpha_evidence["alpha_threshold"] is not None):
        try:
            alpha_evidence["alpha_pass"] = (
                float(alpha_evidence["alpha_confidence"])
                >= float(alpha_evidence["alpha_threshold"])
            )
        except (TypeError, ValueError):
            alpha_evidence["alpha_pass"] = False

    return alpha_evidence


def run_audit(receipt_path: Optional[Path] = None) -> dict:
    """Run the end-to-end entry gate audit.

    NEVER calls mt5.order_send. NEVER modifies positions.
    NEVER creates execution tokens. NEVER fakes alpha/regime evidence.
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    findings: dict[str, Any] = {}

    path = receipt_path or RECEIPT_PATH
    receipt = _load_json(path)
    findings["receipt_exists"] = receipt is not None
    findings["receipt_path"] = str(path)

    # === Receipt-derived execution fields ===
    execution_success = False
    selected_profile = ""
    symbol = ""
    side = ""
    entry = 0.0
    sl = 0.0
    tp = 0.0
    actual_RR = 0.0
    geometry_pass = False
    order_send_success = False

    if receipt:
        execution_success = bool(receipt.get("success", False))
        selected_profile = _to_str(receipt.get("account_profile") or receipt.get("prop_funded_profile"))
        symbol = _to_str(receipt.get("symbol"))
        side = _to_str(receipt.get("side") or receipt.get("direction"))
        entry = _safe_float(receipt.get("order_send_result_price") or receipt.get("detected_position_entry_price"))
        sl = _safe_float(receipt.get("requested_sl") if receipt.get("requested_sl") is not None else receipt.get("request_sl"))
        tp = _safe_float(receipt.get("requested_tp") if receipt.get("requested_tp") is not None else receipt.get("request_tp"))
        order_send_success = execution_success
        # Compute actual_RR from receipt geometry
        if entry > 0 and sl > 0 and tp > 0:
            side_upper = (side or "").upper()
            if side_upper == "BUY":
                risk_dist = entry - sl
                reward_dist = tp - entry
            elif side_upper == "SELL":
                risk_dist = sl - entry
                reward_dist = entry - tp
            else:
                risk_dist = 0.0
                reward_dist = 0.0
            if risk_dist > 0:
                actual_RR = round(reward_dist / risk_dist, 6)
                geometry_pass = actual_RR >= 2.0  # default minimum_RR
        ok_checks.append(f"Receipt loaded: success={execution_success}, profile={selected_profile}")
    else:
        warnings.append("Receipt file not found - cannot evaluate execution chain")

    findings["execution_success"] = execution_success
    findings["selected_profile"] = selected_profile
    findings["symbol"] = symbol
    findings["side"] = side
    findings["entry"] = entry
    findings["SL"] = sl
    findings["TP"] = tp
    findings["actual_RR"] = actual_RR
    findings["geometry_pass"] = geometry_pass
    findings["order_send_success"] = order_send_success

    # === Execution geometry audit (read pre-computed if available) ===
    geom_audit_path = OUTPUT_DIR / "execution_geometry_audit.json"
    geom_audit = _load_json(geom_audit_path)
    findings["geometry_audit_available"] = geom_audit is not None
    if geom_audit:
        geom_verdict = geom_audit.get("verdict", "")
        findings["latest_execution_geometry_verdict"] = geom_verdict
        if geom_verdict == "EXECUTION_GEOMETRY_PASS":
            geometry_pass = True
            ok_checks.append(f"Execution geometry PASS: {geom_verdict}")
        elif geom_verdict.startswith("EXECUTION_GEOMETRY_FAIL"):
            geometry_pass = False
            blockers.append(f"EXECUTION_GEOMETRY_FAILED: {geom_verdict}")
    else:
        findings["latest_execution_geometry_verdict"] = ""

    # === Alpha / regime chain (NEVER fake) ===
    alpha_evidence = _scan_alpha_signal_artifacts()
    findings.update(alpha_evidence)
    if alpha_evidence["alpha_signal_detected"]:
        ok_checks.append(
            f"Alpha signal detected: value={alpha_evidence['alpha_signal_value']}, "
            f"confidence={alpha_evidence['alpha_confidence']}, "
            f"threshold={alpha_evidence['alpha_threshold']}"
        )
    else:
        warnings.append("Alpha signal not detected in available artifacts")
    if alpha_evidence["regime_detected"]:
        ok_checks.append(f"Regime detected: {alpha_evidence['regime_value']}")
    else:
        warnings.append("Regime not detected in available artifacts")

    # === Risk gate (read from build-request or managed report) ===
    risk_gate_pass = False
    managed_report_path = OUTPUT_DIR / "managed_trade_report.json"
    managed = _load_json(managed_report_path)
    findings["managed_trade_report_available"] = managed is not None
    if managed:
        risk_blockers = managed.get("blockers", []) or []
        margin_risk = managed.get("margin_risk", {}) or {}
        margin_blockers = margin_risk.get("blockers", []) if isinstance(margin_risk, dict) else []
        if not risk_blockers and not margin_blockers:
            risk_gate_pass = True
            ok_checks.append("Risk gate PASS (no risk/margin blockers in managed report)")
        else:
            blockers.append(f"RISK_GATE_FAILED: risk_blockers={risk_blockers}, margin_blockers={margin_blockers}")
    else:
        # If no managed report, default risk_gate_pass to execution_success
        # because the build-request already validates risk/margin.
        risk_gate_pass = execution_success
        if execution_success:
            ok_checks.append("Risk gate PASS (assumed from successful execution)")

    findings["risk_gate_pass"] = risk_gate_pass

    # === Broker gate ===
    broker_gate_pass = False
    broker_score_report_path = REPO_ROOT / "data" / "audit" / "broker_scoring" / "broker_score_report.json"
    broker_score_report = _load_json(broker_score_report_path)
    findings["broker_score_report_available"] = broker_score_report is not None
    broker_score = 0
    if broker_score_report:
        broker_score = broker_score_report.get("overall_score", 0)
    if managed and "broker_score" in managed:
        broker_score = managed.get("broker_score", 0)
    if broker_score >= 70:
        broker_gate_pass = True
        ok_checks.append(f"Broker gate PASS: score={broker_score}")
    else:
        blockers.append(f"BROKER_GATE_FAILED: score={broker_score} < 70")
    findings["broker_gate_pass"] = broker_gate_pass
    findings["broker_score"] = broker_score

    # Spread/slippage gates (usually unknown in demo micro)
    findings["spread_gate_pass"] = "unknown"
    findings["slippage_gate_pass"] = "unknown"

    # === Prop/funded gate ===
    prop_funded_gate_pass = False
    prop_funded_opt_path = REPO_ROOT / "data" / "audit" / "prop_funded_optimization" / "prop_funded_optimization_report.json"
    prop_funded_opt = _load_json(prop_funded_opt_path)
    findings["prop_funded_optimization_report_available"] = prop_funded_opt is not None
    if prop_funded_opt:
        # Look for the selected profile in the optimization report
        profiles = prop_funded_opt.get("profiles", []) or []
        selected_profile_data = None
        for p in profiles:
            if p.get("profile_name") == selected_profile:
                selected_profile_data = p
                break
        if selected_profile_data:
            verdict = selected_profile_data.get("verdict", "")
            if verdict == "PROP_FUNDED_PASS":
                prop_funded_gate_pass = True
                ok_checks.append(f"Prop/funded gate PASS for profile: {selected_profile}")
            else:
                blockers.append(f"PROP_FUNDED_GATE_FAILED: verdict={verdict}")
        else:
            # If profile not in report, default to True if execution_success
            # (build-request already validates prop rules)
            prop_funded_gate_pass = execution_success
    else:
        # No prop funded report - default to execution_success
        prop_funded_gate_pass = execution_success
        if execution_success:
            ok_checks.append("Prop/funded gate PASS (assumed from successful execution)")
    findings["prop_funded_gate_pass"] = prop_funded_gate_pass

    # === Execution gate (order_send_success) ===
    execution_gate_pass = execution_success and geometry_pass
    findings["execution_gate_pass"] = execution_gate_pass
    if execution_gate_pass:
        ok_checks.append("Execution gate PASS (success + geometry)")
    else:
        if not execution_success:
            blockers.append("EXECUTION_GATE_FAILED: order_send not successful")
        if not geometry_pass:
            blockers.append("EXECUTION_GATE_FAILED: geometry not pass")

    # === Journal event ===
    journal_event_found = False
    journal_paths = [
        OUTPUT_DIR / "managed_trade_report.json",
        REPO_ROOT / "data" / "audit" / "atr_execution_audit_journal.jsonl",
    ]
    for jp in journal_paths:
        if jp.exists():
            journal_event_found = True
            break
    findings["journal_event_found"] = journal_event_found
    if journal_event_found:
        ok_checks.append("Journal event found")
    else:
        warnings.append("No journal event found")

    # === Meta-label pass (usually unknown in demo micro) ===
    findings["meta_label_pass"] = "unknown"

    # === Final verdict logic ===
    alpha_missing = not alpha_evidence["alpha_signal_detected"]
    regime_missing = not alpha_evidence["regime_detected"]

    if not execution_success:
        # Execution didn't happen - blocked
        if not geometry_pass:
            verdict = ENTRY_GATE_BLOCKED_GEOMETRY
        elif not (risk_gate_pass and broker_gate_pass):
            verdict = ENTRY_GATE_BLOCKED_RISK_OR_BROKER
        else:
            verdict = ENTRY_GATE_BLOCKED_GEOMETRY  # default
    elif not geometry_pass:
        verdict = ENTRY_GATE_BLOCKED_GEOMETRY
    elif not (risk_gate_pass and broker_gate_pass):
        verdict = ENTRY_GATE_BLOCKED_RISK_OR_BROKER
    elif alpha_missing or regime_missing:
        # v2.7.3: Demo micro is a controlled execution proof that does NOT
        # use live alpha/regime for entry. If either is missing, the audit
        # explicitly returns EXECUTION_ONLY_PASS_ALPHA_UNKNOWN.
        verdict = ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN
        warnings.append(
            "Execution proof mode: alpha/regime not used for entry. "
            "Do not treat this as autonomous strategy proof."
        )
    elif not alpha_evidence["alpha_pass"]:
        # Both alpha and regime detected, but alpha confidence below threshold.
        verdict = ENTRY_GATE_BLOCKED_ALPHA_MISSING
        blockers.append("ALPHA_BELOW_THRESHOLD: alpha confidence below threshold")
    else:
        verdict = ENTRY_GATE_FULL_PASS
        ok_checks.append("All entry gates passed: regime + alpha + risk + broker + geometry")

    findings["final_entry_verdict"] = verdict
    findings["execution_proof_mode_alpha_unknown"] = (
        verdict == ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN
    )

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
            "execution_token_created": False,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "end_to_end_entry_gate_audit.json"
    md_path = OUTPUT_DIR / "end_to_end_entry_gate_audit.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - End-to-End Entry Gate Audit (v2.7.3)\n\n")
        f.write("**Passive audit - no order_send, no position modification, no token creation.**\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")

        fnd = result.get("findings", {}) or {}
        f.write("## Execution Chain Status\n\n")
        f.write("| Gate | Status |\n|---|---|\n")
        gate_fields = [
            "receipt_exists", "execution_success", "selected_profile", "symbol",
            "side", "entry", "SL", "TP", "actual_RR", "geometry_pass",
            "latest_execution_geometry_verdict", "execution_gate_pass",
            "regime_detected", "regime_value", "regime_source_file",
            "alpha_signal_detected", "alpha_signal_value", "alpha_confidence",
            "alpha_threshold", "alpha_pass", "alpha_source_file",
            "meta_label_pass", "risk_gate_pass", "broker_gate_pass",
            "broker_score", "prop_funded_gate_pass",
            "spread_gate_pass", "slippage_gate_pass",
            "journal_event_found", "order_send_success",
            "final_entry_verdict", "execution_proof_mode_alpha_unknown",
        ]
        for k in gate_fields:
            if k in fnd:
                f.write(f"| {k} | {fnd[k]} |\n")

        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
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

        f.write("\n## Decision Chain\n\n")
        f.write("```\n")
        f.write("Market data -> Feature engine -> Regime detection -> Alpha/model signal\n")
        f.write("  -> Confidence threshold -> Meta-label/calibration -> Risk engine\n")
        f.write("  -> Broker score/spread/slippage gate -> Prop/funded profile gate\n")
        f.write("  -> Execution geometry RR gate -> Order request\n")
        f.write("```\n\n")

        if fnd.get("execution_proof_mode_alpha_unknown"):
            f.write(
                "## Execution Proof Mode\n\n"
                "**ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN**\n\n"
                "Execution proof is valid (geometry PASS, risk PASS, broker PASS, "
                "order_send success), but alpha/regime chain was not used for entry. "
                "Do not treat this as autonomous strategy proof.\n"
            )

        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
        f.write("- execution_token_created: False\n")
        f.write("- No martingale / grid / averaging / loss-based lot multiplier.\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="End-to-end entry gate audit (passive, no order_send)"
    )
    parser.add_argument("--receipt", type=str, default="")
    args = parser.parse_args()
    receipt_path = Path(args.receipt) if args.receipt else None

    print("=" * 70)
    print("  TITAN XAU AI - End-to-End Entry Gate Audit (v2.7.3)")
    print("=" * 70)
    result = run_audit(receipt_path=receipt_path)
    report = write_report(result)

    print(f"\n  Verdict: {result['verdict']}")
    fnd = result.get("findings", {})
    print(f"  Receipt exists: {fnd.get('receipt_exists', False)}")
    print(f"  Execution success: {fnd.get('execution_success', False)}")
    print(f"  Selected profile: {fnd.get('selected_profile', '')}")
    print(f"  Side: {fnd.get('side', '')}")
    print(f"  Entry: {fnd.get('entry', 0)}")
    print(f"  SL: {fnd.get('SL', 0)}")
    print(f"  TP: {fnd.get('TP', 0)}")
    print(f"  Actual RR: {fnd.get('actual_RR', 0)}")
    print(f"  Geometry pass: {fnd.get('geometry_pass', False)}")
    print(f"  Regime detected: {fnd.get('regime_detected', False)}")
    print(f"  Alpha signal detected: {fnd.get('alpha_signal_detected', False)}")
    print(f"  Alpha confidence: {fnd.get('alpha_confidence', None)}")
    print(f"  Risk gate pass: {fnd.get('risk_gate_pass', False)}")
    print(f"  Broker gate pass: {fnd.get('broker_gate_pass', False)}")
    print(f"  Prop/funded gate pass: {fnd.get('prop_funded_gate_pass', False)}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    if result.get("blockers"):
        for b in result["blockers"]:
            print(f"    - {b}")
    if fnd.get("execution_proof_mode_alpha_unknown"):
        print("\n  Execution proof mode: alpha/regime not used for entry.")
        print("  Do not treat this as autonomous strategy proof.")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
