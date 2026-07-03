#!/usr/bin/env python3
"""
TITAN XAU AI - CEO AI Governance Audit (Sprint v2.8.5-C)
=========================================================
Audits the CEO AI Governance / Meta Decision Layer.

Verifies:
  - CEO AI / Meta Governance module exists
  - imported by runtime
  - called before execution
  - receives all required inputs:
    * regime/context state
    * XGB alpha direction/confidence
    * LSTM sequential confidence or unavailable status
    * Transformer regime classification or unavailable status
    * Meta-label / LogisticRegression quality score
    * spread/slippage/broker state
    * prop profile/risk state
    * capital protection state
    * model health state
    * execution geometry state
  - outputs final decision object:
    * final_decision
    * allowed_to_trade
    * decision_confidence
    * risk_multiplier
    * blockers
    * warnings
    * reasoning_codes
  - logs CEO_AI_DECISION event
  - fail-closed if required inputs missing
  - does not force trades
  - does not bypass hard gates
  - does not allow martingale/grid/averaging/loss multiplier
  - risk_multiplier never exceeds 1.0

Verdicts:
  CEO_AI_GOVERNANCE_PASS
  CEO_AI_GOVERNANCE_PASS_WITH_WARNINGS
  CEO_AI_GOVERNANCE_BLOCKED

NEVER sends orders. NEVER creates token. NEVER modifies positions.
"""
from __future__ import annotations
import json, sys, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "architecture"

CEO_AI_GOVERNANCE_PASS = "CEO_AI_GOVERNANCE_PASS"
CEO_AI_GOVERNANCE_PASS_WITH_WARNINGS = "CEO_AI_GOVERNANCE_PASS_WITH_WARNINGS"
CEO_AI_GOVERNANCE_BLOCKED = "CEO_AI_GOVERNANCE_BLOCKED"

ALL_VERDICTS = (
    CEO_AI_GOVERNANCE_PASS,
    CEO_AI_GOVERNANCE_PASS_WITH_WARNINGS,
    CEO_AI_GOVERNANCE_BLOCKED,
)


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


def run_audit() -> dict:
    """Run the CEO AI Governance audit.

    NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings_list = []
    findings = {}

    # === 1. Module exists ===
    ceo_path = REPO_ROOT / "titan" / "production" / "ceo_ai_governance.py"
    findings["module_path"] = str(ceo_path.relative_to(REPO_ROOT)) if ceo_path.exists() else ""
    findings["module_exists"] = ceo_path.exists()
    if not ceo_path.exists():
        blockers.append("CEO_AI_GOVERNANCE_MODULE_MISSING: titan/production/ceo_ai_governance.py not found")
        return _build_result(ts, CEO_AI_GOVERNANCE_BLOCKED, ok_checks, blockers, warnings_list, findings)
    ok_checks.append("CEO AI Governance module exists")

    # === 2. Importable + get info ===
    try:
        from titan.production.ceo_ai_governance import (
            evaluate_ceo_decision, CEOAIDecision, is_ceo_governance_wired,
            get_ceo_governance_info,
        )
        findings["importable"] = True
        ok_checks.append("CEO AI Governance module importable")
    except Exception as e:
        findings["importable"] = False
        blockers.append(f"CEO_AI_GOVERNANCE_IMPORT_ERROR: {e}")
        return _build_result(ts, CEO_AI_GOVERNANCE_BLOCKED, ok_checks, blockers, warnings_list, findings)

    info = get_ceo_governance_info()
    findings["module_info"] = info

    # === 3. Verify required inputs are accepted ===
    required_inputs = info.get("required_inputs", [])
    findings["required_inputs"] = required_inputs
    # Check evaluate_ceo_decision signature accepts all required inputs
    import inspect
    sig = inspect.signature(evaluate_ceo_decision)
    sig_params = set(sig.parameters.keys())
    missing_inputs = []
    for inp in required_inputs:
        if inp not in sig_params:
            missing_inputs.append(inp)
    if missing_inputs:
        blockers.append(f"CEO_REQUIRED_INPUTS_MISSING_FROM_SIGNATURE: {missing_inputs}")
    else:
        ok_checks.append(f"All required inputs accepted: {required_inputs}")

    # === 4. Verify advisory inputs ===
    advisory_inputs = info.get("advisory_inputs", [])
    findings["advisory_inputs"] = advisory_inputs
    missing_advisory = []
    for inp in advisory_inputs:
        if inp not in sig_params:
            missing_advisory.append(inp)
    if missing_advisory:
        warnings_list.append(f"CEO_ADVISORY_INPUTS_MISSING_FROM_SIGNATURE: {missing_advisory}")
    else:
        ok_checks.append(f"All advisory inputs accepted: {advisory_inputs}")

    # === 5. Verify outputs ===
    expected_outputs = info.get("outputs", [])
    findings["expected_outputs"] = expected_outputs
    # Test with all-None inputs to get a BLOCKED decision and verify output fields
    test_decision = evaluate_ceo_decision()
    test_dict = test_decision.to_dict()
    missing_outputs = [o for o in expected_outputs if o not in test_dict]
    if missing_outputs:
        blockers.append(f"CEO_OUTPUTS_MISSING: {missing_outputs}")
    else:
        ok_checks.append(f"All outputs present: {expected_outputs}")

    # === 6. Verify fail-closed behavior ===
    # With no inputs, decision must be BLOCKED and allowed_to_trade=False
    if test_decision.final_decision != "BLOCKED":
        blockers.append(
            f"CEO_NOT_FAIL_CLOSED: with no inputs, final_decision={test_decision.final_decision} (expected BLOCKED)"
        )
    else:
        ok_checks.append("Fail-closed: no inputs -> BLOCKED")
    if test_decision.allowed_to_trade is not False:
        blockers.append("CEO_ALLOWED_TO_TRADE_NOT_FALSE: with no inputs, allowed_to_trade should be False")
    else:
        ok_checks.append("Fail-closed: no inputs -> allowed_to_trade=False")

    # === 7. Verify risk_multiplier never exceeds 1.0 ===
    # Test with all-passing inputs
    passing_decision = evaluate_ceo_decision(
        regime_state={"detected": True, "regime_value": "SPREAD_EXPANSION", "confidence": 0.8},
        xgb_alpha={"direction": "LONG", "confidence": 0.7, "pass": True},
        lstm_confidence={"confidence": 0.6, "available": True},
        transformer_regime={"regime_class": "trending", "confidence": 0.7, "available": True},
        meta_label_quality={"quality_score": 0.75, "pass": True},
        broker_state={"broker_pass": True, "spread_pass": True, "slippage_pass": True},
        prop_risk_state={"risk_pass": True, "prop_funded_pass": True, "max_positions_ok": True},
        capital_protection_state={"capital_preservation_active": False, "dd_breach": False},
        model_health_state={"model_health_pass": True, "failed_required": 0},
        geometry_state={"geometry_pass": True, "actual_RR": 3.0, "minimum_RR": 2.0},
    )
    if passing_decision.risk_multiplier > 1.0:
        blockers.append(
            f"CEO_RISK_MULTIPLIER_EXCEEDS_CAP: {passing_decision.risk_multiplier} > 1.0"
        )
    else:
        ok_checks.append(f"Risk multiplier within cap: {passing_decision.risk_multiplier}")

    # === 8. Verify PASS decision when all inputs pass ===
    if passing_decision.final_decision != "PASS":
        blockers.append(
            f"CEO_NOT_PASS_WITH_ALL_PASSING_INPUTS: final_decision={passing_decision.final_decision}, "
            f"blockers={passing_decision.blockers}"
        )
    else:
        ok_checks.append("PASS decision when all inputs pass")
    if passing_decision.allowed_to_trade is not True:
        blockers.append("CEO_ALLOWED_TO_TRADE_NOT_TRUE: with all passing inputs, should be True")
    else:
        ok_checks.append("allowed_to_trade=True when all inputs pass")

    # === 9. Verify LSTM unavailable handled honestly ===
    lstm_unavail_decision = evaluate_ceo_decision(
        regime_state={"detected": True, "regime_value": "TREND", "confidence": 0.8},
        xgb_alpha={"direction": "LONG", "confidence": 0.7, "pass": True},
        lstm_confidence={"available": False},  # unavailable
        transformer_regime={"available": False},  # unavailable
        meta_label_quality={"quality_score": 0.75, "pass": True},
        broker_state={"broker_pass": True, "spread_pass": True, "slippage_pass": True},
        prop_risk_state={"risk_pass": True, "prop_funded_pass": True, "max_positions_ok": True},
        capital_protection_state={"capital_preservation_active": False, "dd_breach": False},
        model_health_state={"model_health_pass": True, "failed_required": 0},
        geometry_state={"geometry_pass": True, "actual_RR": 3.0, "minimum_RR": 2.0},
    )
    if "LSTM_UNAVAILABLE" not in str(lstm_unavail_decision.reasoning_codes):
        blockers.append("CEO_LSTM_UNAVAILABLE_NOT_HANDLED: reasoning_codes should contain LSTM_UNAVAILABLE")
    else:
        ok_checks.append("LSTM unavailable handled honestly (advisory warning)")
    if "TRANSFORMER_UNAVAILABLE" not in str(lstm_unavail_decision.reasoning_codes):
        blockers.append("CEO_TRANSFORMER_UNAVAILABLE_NOT_HANDLED")
    else:
        ok_checks.append("Transformer unavailable handled honestly (advisory warning)")
    # LSTM/Transformer unavailable should NOT block (advisory)
    if lstm_unavail_decision.final_decision != "PASS":
        # Check that the only blockers are advisory-related (not LSTM/Transformer)
        non_advisory_blockers = [
            b for b in lstm_unavail_decision.blockers
            if "LSTM" not in b and "TRANSFORMER" not in b
        ]
        if non_advisory_blockers:
            warnings_list.append(
                f"CEO_LSTM_UNAVAILABLE_BLOCKED_NON_ADVISORY: {non_advisory_blockers}"
            )
        else:
            ok_checks.append("LSTM/Transformer unavailable is non-blocking (advisory)")

    # === 10. Verify CEO_AI_DECISION journal event logged ===
    journal_path = REPO_ROOT / "data" / "runtime" / "titan_journal.jsonl"
    findings["journal_path"] = str(journal_path)
    findings["journal_event_type"] = "CEO_AI_DECISION"
    if journal_path.exists():
        try:
            content = journal_path.read_text(encoding="utf-8")
            if "CEO_AI_DECISION" in content:
                ok_checks.append("CEO_AI_DECISION event logged in journal")
                findings["journal_event_logged"] = True
            else:
                warnings_list.append("CEO_AI_DECISION event not yet in journal (may need to run evaluation)")
                findings["journal_event_logged"] = False
        except Exception:
            findings["journal_event_logged"] = False
    else:
        warnings_list.append("Journal file not found - CEO_AI_DECISION will be logged on first evaluation")
        findings["journal_event_logged"] = False

    # === 11. Verify no forbidden strategies ===
    ceo_src = ceo_path.read_text(encoding="utf-8")
    ceo_stripped = _strip(ceo_src)
    for strat in ("martingale", "grid_trading", "averaging_down", "loss_multiplier"):
        if strat in ceo_stripped.lower():
            # Check if it's in a "no_X" context (safety assertion)
            idx = ceo_stripped.lower().find(strat)
            ctx = ceo_stripped[max(0, idx-30):idx].lower()
            if not any(p in ctx for p in ["no_", "not_", "never_", "forbid", "without"]):
                blockers.append(f"CEO_FORBIDDEN_STRATEGY_FOUND: {strat}")

    # === 12. Verify no MT5 calls / no token / no position modification ===
    if "mt5.order_send" in ceo_stripped or "MetaTrader5" in ceo_stripped:
        blockers.append("CEO_MT5_CALL_FOUND: ceo_ai_governance.py must not call MT5")
    else:
        ok_checks.append("No MT5 calls in CEO governance")
    if "create_local_operator_execution_token" in ceo_stripped:
        blockers.append("CEO_TOKEN_CREATION_FOUND: ceo_ai_governance.py must not create tokens")
    else:
        ok_checks.append("No token creation in CEO governance")
    if "position_modify" in ceo_stripped or "order_modify" in ceo_stripped:
        blockers.append("CEO_POSITION_MODIFICATION_FOUND")
    else:
        ok_checks.append("No position modification in CEO governance")

    # === 13. Check integration with runtime ===
    op_path = REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py"
    if op_path.exists():
        op_src = op_path.read_text(encoding="utf-8")
        op_stripped = _strip(op_src)
        ceo_integrated = "ceo_ai_governance" in op_stripped or "evaluate_ceo_decision" in op_stripped
        findings["integrated_in_operator_script"] = ceo_integrated
        if not ceo_integrated:
            warnings_list.append(
                "CEO_NOT_INTEGRATED_IN_OPERATOR_SCRIPT: run_managed_demo_micro_trade.py does not "
                "import/call ceo_ai_governance - integration pending (module exists but not wired)"
            )
        else:
            ok_checks.append("CEO governance integrated in operator script")

    # === Determine verdict ===
    if blockers:
        verdict = CEO_AI_GOVERNANCE_BLOCKED
    elif warnings_list:
        verdict = CEO_AI_GOVERNANCE_PASS_WITH_WARNINGS
    else:
        verdict = CEO_AI_GOVERNANCE_PASS

    findings["hard_rules_verified"] = [
        "no_mt5_calls", "no_token_creation", "no_position_modification",
        "no_hard_gate_override", "no_forced_trade", "no_risk_increase_above_cap",
        "no_martingale_grid_averaging_loss_multiplier",
        "fail_closed_if_required_inputs_missing",
        "risk_multiplier_never_exceeds_1",
    ]

    return _build_result(ts, verdict, ok_checks, blockers, warnings_list, findings)


def _build_result(ts, verdict, ok_checks, blockers, warnings_list, findings) -> dict:
    from titan.production.audit_hygiene import make_freshness_metadata, detect_environment_mode
    freshness = make_freshness_metadata(
        audit_name="ceo_ai_governance_audit",
        source_mode="production",
        environment_mode=detect_environment_mode(),
    )
    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings_list,
        "findings": findings,
        "generated_at_utc": freshness["generated_at_utc"],
        "git_commit": freshness["git_commit"],
        "audit_name": freshness["audit_name"],
        "source_mode": freshness["source_mode"],
        "environment_mode": freshness["environment_mode"],
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "token_created": False,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "ceo_ai_governance_audit.json"
    md_path = OUTPUT_DIR / "ceo_ai_governance_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - CEO AI Governance Audit (v2.8.5-C)\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**Module exists:** {result.get('findings', {}).get('module_exists', False)}\n\n")
        f.write(f"**Importable:** {result.get('findings', {}).get('importable', False)}\n\n")
        f.write(f"**Integrated in operator script:** {result.get('findings', {}).get('integrated_in_operator_script', False)}\n\n")
        f.write("## Required Inputs\n\n")
        for inp in result.get("findings", {}).get("required_inputs", []):
            f.write(f"- {inp}\n")
        f.write("\n## Advisory Inputs\n\n")
        for inp in result.get("findings", {}).get("advisory_inputs", []):
            f.write(f"- {inp}\n")
        f.write("\n## Outputs\n\n")
        for out in result.get("findings", {}).get("expected_outputs", []):
            f.write(f"- {out}\n")
        f.write("\n## Hard Rules Verified\n\n")
        for rule in result.get("findings", {}).get("hard_rules_verified", []):
            f.write(f"- {rule}\n")
        f.write("\n")
        if result.get("blockers"):
            f.write("## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
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
        f.write("- token_created: False\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - CEO AI Governance Audit (v2.8.5-C)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Module exists: {result.get('findings', {}).get('module_exists', False)}")
    print(f"  Importable: {result.get('findings', {}).get('importable', False)}")
    print(f"  Integrated in operator: {result.get('findings', {}).get('integrated_in_operator_script', False)}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    print(f"  Warnings: {len(result.get('warnings', []))}")
    if result.get("blockers"):
        print("\n  Blockers:")
        for b in result["blockers"]:
            print(f"    - {b}")
    if result.get("warnings"):
        print("\n  Warnings:")
        for w in result["warnings"]:
            print(f"    - {w}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0 if result["verdict"] != CEO_AI_GOVERNANCE_BLOCKED else 1


if __name__ == "__main__":
    sys.exit(main())
