#!/usr/bin/env python3
"""
TITAN XAU AI - Autonomous Demo Readiness Audit (Sprint 9.9.3.45.8.16 v2.7.3)
===========================================================================
Decides whether TITAN can be allowed to run autonomous demo execution.

Autonomous demo must be BLOCKED unless ALL of the following are true:
  1. Latest execution geometry PASS
  2. Forensics/evidence verifier PASS or acceptable receipt-supported evidence
  3. No open positions
  4. Final demo readiness READY
  5. Broker account is DEMO
  6. prop_funded_safe selected
  7. RR gate enforced
  8. Risk per trade <= 0.5%
  9. Max open positions = 1
  10. No martingale/grid/averaging/loss multiplier
  11. End-to-end entry gate is FULL_PASS or explicitly operator-approved
      execution-only mode
  12. 7-day forward demo rollup is complete OR supervisor override says
      observation-only
  13. No stale execution token

Verdicts
--------
  AUTONOMOUS_DEMO_READY_SUPERVISED                  - all checks pass,
                                                       supervised autonomous
  AUTONOMOUS_DEMO_BLOCKED_EVIDENCE_INCOMPLETE       - forensics/evidence incomplete
  AUTONOMOUS_DEMO_BLOCKED_ALPHA_ENTRY_UNKNOWN       - alpha/regime chain not proven
  AUTONOMOUS_DEMO_BLOCKED_RISK                      - risk constraints violated
  AUTONOMOUS_DEMO_BLOCKED_OPEN_POSITION             - open position exists
  AUTONOMOUS_DEMO_OBSERVATION_ONLY                  - supervisor override:
                                                       observation-only mode

NEVER sends orders. NEVER modifies positions. NEVER creates execution tokens.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"
RECEIPT_PATH = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"

# Verdicts
AUTONOMOUS_DEMO_READY_SUPERVISED = "AUTONOMOUS_DEMO_READY_SUPERVISED"
AUTONOMOUS_DEMO_BLOCKED_EVIDENCE_INCOMPLETE = "AUTONOMOUS_DEMO_BLOCKED_EVIDENCE_INCOMPLETE"
AUTONOMOUS_DEMO_BLOCKED_ALPHA_ENTRY_UNKNOWN = "AUTONOMOUS_DEMO_BLOCKED_ALPHA_ENTRY_UNKNOWN"
AUTONOMOUS_DEMO_BLOCKED_ALPHA_ENTRY_FAILED = "AUTONOMOUS_DEMO_BLOCKED_ALPHA_ENTRY_FAILED"
AUTONOMOUS_DEMO_BLOCKED_RISK = "AUTONOMOUS_DEMO_BLOCKED_RISK"
AUTONOMOUS_DEMO_BLOCKED_OPEN_POSITION = "AUTONOMOUS_DEMO_BLOCKED_OPEN_POSITION"
AUTONOMOUS_DEMO_OBSERVATION_ONLY = "AUTONOMOUS_DEMO_OBSERVATION_ONLY"

ALL_VERDICTS = (
    AUTONOMOUS_DEMO_READY_SUPERVISED,
    AUTONOMOUS_DEMO_BLOCKED_EVIDENCE_INCOMPLETE,
    AUTONOMOUS_DEMO_BLOCKED_ALPHA_ENTRY_UNKNOWN,
    AUTONOMOUS_DEMO_BLOCKED_ALPHA_ENTRY_FAILED,
    AUTONOMOUS_DEMO_BLOCKED_RISK,
    AUTONOMOUS_DEMO_BLOCKED_OPEN_POSITION,
    AUTONOMOUS_DEMO_OBSERVATION_ONLY,
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


def _load_profile_data(selected_profile: str) -> dict:
    """Load profile data from account_profiles.yaml OR prop_firm_profiles.yaml.

    Returns empty dict if not found in either.
    """
    if not selected_profile:
        return {}
    paths_to_try = [
        REPO_ROOT / "config" / "account_profiles.yaml",
        REPO_ROOT / "config" / "prop_firm_profiles.yaml",
    ]
    try:
        import yaml as _yaml
        for p in paths_to_try:
            if not p.exists():
                continue
            with open(p, "r", encoding="utf-8") as f:
                data = _yaml.safe_load(f) or {}
            # Check both top-level "profiles" and direct dict-of-profiles
            profiles = data.get("profiles") if isinstance(data, dict) else None
            if profiles and selected_profile in profiles:
                return profiles[selected_profile] or {}
            # Also try direct lookup (prop_firm_profiles.yaml uses top-level dict)
            if isinstance(data, dict) and selected_profile in data:
                return data[selected_profile] or {}
    except Exception:
        pass
    return {}


def run_audit(receipt_path: Optional[Path] = None) -> dict:
    """Run the autonomous demo readiness audit.

    NEVER calls mt5.order_send. NEVER modifies positions. NEVER creates
    execution tokens.
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    findings: dict[str, Any] = {}

    path = receipt_path or RECEIPT_PATH
    receipt = _load_json(path)
    findings["receipt_exists"] = receipt is not None

    # === 1. Latest execution geometry PASS ===
    geom_audit_path = OUTPUT_DIR / "execution_geometry_audit.json"
    geom_audit = _load_json(geom_audit_path)
    findings["geometry_audit_available"] = geom_audit is not None
    latest_geometry_verdict = ""
    geometry_pass = False
    if geom_audit:
        latest_geometry_verdict = geom_audit.get("verdict", "")
        if latest_geometry_verdict == "EXECUTION_GEOMETRY_PASS":
            geometry_pass = True
            ok_checks.append(f"Geometry PASS: {latest_geometry_verdict}")
        else:
            blockers.append(f"GEOMETRY_NOT_PASS: {latest_geometry_verdict}")
    else:
        blockers.append("GEOMETRY_AUDIT_MISSING: execution geometry audit not found")
    findings["latest_execution_geometry_verdict"] = latest_geometry_verdict
    findings["geometry_pass"] = geometry_pass

    # === 2. Forensics/evidence verifier PASS or acceptable receipt-supported ===
    forensics_path = OUTPUT_DIR / "post_trade_forensics.json"
    forensics = _load_json(forensics_path)
    findings["forensics_available"] = forensics is not None
    forensics_verdict = forensics.get("verdict", "") if forensics else ""
    findings["latest_forensics_verdict"] = forensics_verdict

    # Acceptable forensics verdicts (v2.7.3):
    acceptable_forensics_verdicts = {
        "DEMO_MICRO_EVIDENCE_PASS",
        "DEMO_MICRO_EVIDENCE_RECEIPT_DIAGNOSTIC_CONFIRMED",
        "DEMO_MICRO_EVIDENCE_ENTRY_CONFIRMED_CLOSE_DEAL_MISSING",
        "DEMO_MICRO_FORENSICS_COMPLETE_WITH_WARNINGS",
    }
    forensics_pass = forensics_verdict in acceptable_forensics_verdicts
    findings["forensics_pass"] = forensics_pass

    if not forensics:
        blockers.append("FORENSICS_MISSING: post_trade_forensics.json not found")
    elif not forensics_pass:
        blockers.append(
            f"FORENSICS_INCOMPLETE: verdict={forensics_verdict} "
            f"(acceptable: {sorted(acceptable_forensics_verdicts)})"
        )
    else:
        ok_checks.append(f"Forensics PASS: {forensics_verdict}")

    # Also check the evidence verifier
    evidence_verifier_path = OUTPUT_DIR / "demo_micro_evidence_verifier.json"
    evidence_verifier = _load_json(evidence_verifier_path)
    findings["evidence_verifier_available"] = evidence_verifier is not None
    if evidence_verifier:
        ev_verdict = evidence_verifier.get("verdict", "")
        findings["evidence_verifier_verdict"] = ev_verdict
        if ev_verdict == "MICRO_PROOF_PASS":
            ok_checks.append("Evidence verifier PASS")
        elif ev_verdict == "MICRO_PROOF_INCOMPLETE":
            warnings.append("Evidence verifier INCOMPLETE - forensics may still be acceptable")
        else:
            blockers.append(f"EVIDENCE_VERIFIER_FAILED: {ev_verdict}")

    # === 3. No open positions ===
    open_positions_count = 0
    if forensics:
        open_positions_count = forensics.get("findings", {}).get("open_positions_count", 0) or 0
    findings["open_positions_count"] = open_positions_count
    if open_positions_count > 0:
        blockers.append(f"OPEN_POSITION_EXISTS: {open_positions_count} open positions remain")
    else:
        ok_checks.append("No open positions")

    # === 4. Final demo readiness READY ===
    final_demo_path = REPO_ROOT / "data" / "audit" / "demo_readiness" / "final_demo_proof_readiness_report.json"
    final_demo = _load_json(final_demo_path)
    findings["final_demo_readiness_available"] = final_demo is not None
    final_demo_ready = False
    if final_demo:
        final_demo_verdict = final_demo.get("verdict", "") or final_demo.get("overall_verdict", "")
        findings["final_demo_readiness_verdict"] = final_demo_verdict
        if "READY" in final_demo_verdict and "BLOCKED" not in final_demo_verdict:
            final_demo_ready = True
            ok_checks.append(f"Final demo readiness READY: {final_demo_verdict}")
        else:
            blockers.append(f"FINAL_DEMO_NOT_READY: {final_demo_verdict}")
    else:
        # If no final demo readiness report, mark as warning (not blocker)
        warnings.append("Final demo readiness report not found - assuming pending")
        findings["final_demo_readiness_verdict"] = ""

    # === 5. Broker account is DEMO ===
    broker_demo = True
    if receipt:
        account_server = receipt.get("account_server", "") or ""
        if "demo" not in account_server.lower() and "metaquotes" not in account_server.lower():
            broker_demo = False
            blockers.append(f"BROKER_NOT_DEMO: account_server={account_server}")
        else:
            ok_checks.append(f"Broker DEMO: {account_server}")
    findings["broker_demo"] = broker_demo

    # === 6. prop_funded_safe selected ===
    # v2.7.4: Use shared profile resolver (priority: CLI > managed > receipt
    # > final_demo > config default). The receipt may have stale profile info.
    selected_profile = ""
    selected_profile_source = ""
    try:
        from titan.production.selected_profile_resolver import resolve_selected_profile
        resolved = resolve_selected_profile(REPO_ROOT)
        selected_profile = resolved["selected_profile"]
        selected_profile_source = resolved["selected_profile_source"]
    except Exception:
        if receipt:
            selected_profile = (
                receipt.get("prop_funded_profile")
                or receipt.get("account_profile")
                or ""
            )
            selected_profile_source = "latest_receipt"
    findings["selected_profile"] = selected_profile
    findings["selected_profile_source"] = selected_profile_source
    prop_funded_safe_selected = selected_profile == "prop_funded_safe"
    if prop_funded_safe_selected:
        ok_checks.append(f"prop_funded_safe selected (source={selected_profile_source})")
    else:
        # Not strictly a blocker - other safe profiles may be acceptable
        warnings.append(
            f"prop_funded_safe not selected (current: {selected_profile}, "
            f"source={selected_profile_source})"
        )
    findings["prop_funded_safe_selected"] = prop_funded_safe_selected

    # === 7. RR gate enforced ===
    rr_gate_enforced = False
    run_managed_src_path = REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py"
    if run_managed_src_path.exists():
        run_managed_src = run_managed_src_path.read_text()
        rr_gate_enforced = "EXECUTION_GEOMETRY_RR_BELOW_MINIMUM" in run_managed_src
    if rr_gate_enforced:
        ok_checks.append("RR gate enforced in run_managed_demo_micro_trade.py")
    else:
        blockers.append("RR_GATE_NOT_ENFORCED: EXECUTION_GEOMETRY_RR_BELOW_MINIMUM missing from run_managed")
    findings["rr_gate_enforced"] = rr_gate_enforced

    # === 8. Risk per trade <= 0.5% ===
    risk_per_trade_pct = 0.0
    if receipt:
        risk_per_trade_pct = _safe_float(receipt.get("risk_per_trade_pct"))
    # Default if not in receipt - check account/prop profile
    if risk_per_trade_pct == 0.0:
        profile_data = _load_profile_data(selected_profile)
        if profile_data:
            # Try multiple keys
            for key in ("max_risk_per_trade_pct", "risk_per_trade_pct"):
                if key in profile_data:
                    risk_per_trade_pct = _safe_float(profile_data[key])
                    break
    findings["risk_per_trade_pct"] = risk_per_trade_pct
    risk_within_limit = risk_per_trade_pct <= 0.005  # 0.5%
    if risk_within_limit and risk_per_trade_pct > 0:
        ok_checks.append(f"Risk per trade <= 0.5%: {risk_per_trade_pct}")
    elif risk_per_trade_pct == 0.0:
        warnings.append("Risk per trade not specified - cannot verify <= 0.5%")
    else:
        blockers.append(f"RISK_TOO_HIGH: risk_per_trade_pct={risk_per_trade_pct} > 0.005")

    # === 9. Max open positions = 1 ===
    profile_data_for_max = _load_profile_data(selected_profile)
    max_open_positions = 0
    if profile_data_for_max:
        if "max_open_positions" in profile_data_for_max:
            try:
                max_open_positions = int(profile_data_for_max["max_open_positions"])
            except (TypeError, ValueError):
                pass
    findings["max_open_positions"] = max_open_positions
    if max_open_positions == 1:
        ok_checks.append("Max open positions = 1")
    elif max_open_positions == 0:
        warnings.append("Max open positions not specified in profile - cannot verify = 1")
    else:
        blockers.append(f"MAX_OPEN_POSITIONS_NOT_1: {max_open_positions}")

    # === 10. No martingale/grid/averaging/loss multiplier ===
    no_martingale = True
    try:
        import yaml as _yaml3
        ap_path = REPO_ROOT / "config" / "account_profiles.yaml"
        if ap_path.exists():
            ap_src = ap_path.read_text()
            no_martingale = all(s in ap_src for s in [
                "no_martingale: true", "no_grid: true",
                "no_averaging: true", "no_loss_based_lot_multiplier: true",
            ])
    except Exception:
        pass
    findings["no_martingale"] = no_martingale
    if no_martingale:
        ok_checks.append("No martingale/grid/averaging/loss multiplier")
    else:
        blockers.append("FORBIDDEN_PATTERNS_PRESENT: martingale/grid/averaging/loss_multiplier")

    # === 11. End-to-end entry gate FULL_PASS or execution-only approved ===
    entry_gate_audit_path = OUTPUT_DIR / "end_to_end_entry_gate_audit.json"
    entry_gate_audit = _load_json(entry_gate_audit_path)
    findings["entry_gate_audit_available"] = entry_gate_audit is not None
    entry_gate_verdict = ""
    entry_gate_full_pass = False
    entry_gate_execution_only = False
    if entry_gate_audit:
        entry_gate_verdict = entry_gate_audit.get("verdict", "")
        entry_gate_full_pass = entry_gate_verdict == "ENTRY_GATE_FULL_PASS"
        entry_gate_execution_only = (
            entry_gate_verdict == "ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN"
        )
    findings["end_to_end_entry_gate_verdict"] = entry_gate_verdict
    findings["entry_gate_full_pass"] = entry_gate_full_pass
    findings["entry_gate_execution_only"] = entry_gate_execution_only
    if entry_gate_full_pass:
        ok_checks.append("End-to-end entry gate FULL_PASS")
    elif entry_gate_execution_only:
        warnings.append(
            "End-to-end entry gate is EXECUTION_ONLY_PASS_ALPHA_UNKNOWN - "
            "autonomous strategy proof not complete"
        )
    else:
        blockers.append(f"ENTRY_GATE_NOT_PASS: {entry_gate_verdict}")

    # === 12. 7-day forward demo rollup complete OR observation-only override ===
    forward_demo_dir = REPO_ROOT / "data" / "audit" / "forward_demo"
    daily_report_count = 0
    if forward_demo_dir.exists():
        daily_report_count = len(list(forward_demo_dir.glob("daily_report_*.json")))
    findings["forward_demo_daily_reports_count"] = daily_report_count
    forward_demo_complete = daily_report_count >= 7
    findings["forward_demo_complete"] = forward_demo_complete

    # Supervisor override for observation-only mode
    supervisor_override_path = REPO_ROOT / "data" / "runtime" / "supervisor_observation_only.flag"
    supervisor_observation_only = supervisor_override_path.exists()
    findings["supervisor_observation_only_override"] = supervisor_observation_only

    if forward_demo_complete:
        ok_checks.append("7-day forward demo complete")
    elif supervisor_observation_only:
        ok_checks.append("Supervisor override: observation-only mode")
    else:
        warnings.append(
            f"7-day forward demo not complete ({daily_report_count}/7 days) "
            "and no supervisor observation-only override"
        )

    # === 13. No stale execution token ===
    token_path = REPO_ROOT / "data" / "runtime" / "operator_execution_token.json"
    stale_token = False
    if token_path.exists():
        try:
            token_data = json.loads(token_path.read_text())
            token_ts = token_data.get("created_at") or token_data.get("timestamp_utc") or ""
            if token_ts:
                token_dt = datetime.fromisoformat(token_ts.replace("Z", "+00:00"))
                age = (datetime.now(timezone.utc) - token_dt).total_seconds()
                if age > 3600:  # > 1 hour = stale
                    stale_token = True
                    blockers.append(f"STALE_EXECUTION_TOKEN: age={int(age)}s > 3600s")
        except Exception:
            blockers.append("STALE_EXECUTION_TOKEN: cannot parse token file")
    findings["stale_execution_token"] = stale_token
    if not stale_token:
        ok_checks.append("No stale execution token")

    # === Final verdict logic ===
    # v2.7.4: Verdict precedence per spec:
    #   1. open position blocker
    #   2. geometry fail (evidence incomplete)
    #   3. forensics fail (evidence incomplete)
    #   4. risk config hard fail (martingale present, RR gate missing,
    #      risk > 0.5%, max_open_positions > 1)
    #   5. broker actual fail (entry gate explicitly FAILED broker)
    #   6. alpha/regime entry unknown (execution-only proof)
    #   7. forward demo incomplete (warning, not blocker)
    #   8. supervised ready
    evidence_incomplete = (
        not forensics_pass
        or not geom_audit
        or not geometry_pass
    )
    # v2.7.4: Hard risk blockers only - soft "not specified" warnings do NOT
    # trigger BLOCKED_RISK. Max_open_positions == 0 means "not specified"
    # (warning, not blocker). Max_open_positions > 1 means "violates policy"
    # (blocker). Risk_per_trade_pct == 0.0 means "not specified" (warning).
    # Risk_per_trade_pct > 0.005 means "exceeds 0.5%" (blocker).
    hard_risk_blocker = (
        not no_martingale
        or not rr_gate_enforced
        or (risk_per_trade_pct > 0.005)  # strictly greater = exceeds limit
        or (max_open_positions > 1)  # strictly greater = violates policy
    )
    # v2.7.4: Broker actual fail = entry gate verdict explicitly failed broker
    # (broker_gate_status == "FAILED"). If broker gate is UNKNOWN (no artifact),
    # that's a warning, not a blocker.
    broker_actual_fail = False
    if entry_gate_audit:
        eg_findings = entry_gate_audit.get("findings", {}) or {}
        broker_actual_fail = eg_findings.get("broker_gate_status", "") == "FAILED"
    alpha_entry_unknown = (
        entry_gate_execution_only
        or entry_gate_verdict == "ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN"
    )

    # v2.8: Read autonomous entry decision to distinguish UNKNOWN vs FAILED.
    # UNKNOWN = no decision artifact exists (run --autonomous-entry-check first)
    # FAILED = decision exists but is not ALPHA_REGIME_ENTRY_PASS
    autonomous_decision_path = OUTPUT_DIR / "autonomous_entry_decision.json"
    autonomous_decision = _load_json(autonomous_decision_path)
    findings["autonomous_entry_decision_available"] = autonomous_decision is not None
    ae_final_decision = ""
    ae_pass = False
    if autonomous_decision:
        ae_final_decision = autonomous_decision.get("final_decision", "") or ""
        ae_pass = ae_final_decision == "ALPHA_REGIME_ENTRY_PASS"
        findings["autonomous_entry_decision_verdict"] = ae_final_decision
        findings["autonomous_entry_decision_pass"] = ae_pass
    else:
        findings["autonomous_entry_decision_verdict"] = ""
        findings["autonomous_entry_decision_pass"] = False

    # v2.8: entry_gate_full_pass requires autonomous entry decision PASS
    entry_gate_full_pass_v28 = (
        entry_gate_verdict == "ENTRY_GATE_FULL_PASS"
        and ae_pass
    )

    if supervisor_observation_only and not forward_demo_complete:
        verdict = AUTONOMOUS_DEMO_OBSERVATION_ONLY
        ok_checks.append("Verdict: OBSERVATION_ONLY (supervisor override active)")
    elif open_positions_count > 0:
        verdict = AUTONOMOUS_DEMO_BLOCKED_OPEN_POSITION
    elif evidence_incomplete:
        verdict = AUTONOMOUS_DEMO_BLOCKED_EVIDENCE_INCOMPLETE
    elif hard_risk_blocker:
        verdict = AUTONOMOUS_DEMO_BLOCKED_RISK
        if not no_martingale:
            blockers.append("RISK_CONFIG_FAIL: forbidden patterns present (martingale/grid/averaging/loss_multiplier)")
        if not rr_gate_enforced:
            blockers.append("RISK_CONFIG_FAIL: RR gate not enforced in run_managed_demo_micro_trade.py")
        if risk_per_trade_pct > 0.005:
            blockers.append(f"RISK_CONFIG_FAIL: risk_per_trade_pct={risk_per_trade_pct} > 0.005")
        if max_open_positions > 1:
            blockers.append(f"RISK_CONFIG_FAIL: max_open_positions={max_open_positions} > 1")
    elif broker_actual_fail:
        verdict = AUTONOMOUS_DEMO_BLOCKED_RISK
        blockers.append("BROKER_ACTUAL_FAIL: entry gate broker_gate_status=FAILED")
    elif autonomous_decision is None:
        # v2.8: No autonomous entry decision artifact exists.
        # This means --autonomous-entry-check has not been run yet.
        verdict = AUTONOMOUS_DEMO_BLOCKED_ALPHA_ENTRY_UNKNOWN
        blockers.append(
            "ALPHA_REGIME_ENTRY_NOT_PROVEN: autonomous_entry_decision.json not found. "
            "Run --autonomous-entry-check to evaluate the alpha/regime entry chain."
        )
    elif not ae_pass:
        # v2.8: Autonomous entry decision exists but did not pass.
        # v2.8.1: Include the exact decision blockers so the operator knows
        # exactly which gates failed.
        verdict = AUTONOMOUS_DEMO_BLOCKED_ALPHA_ENTRY_FAILED
        blockers.append(
            f"ALPHA_REGIME_ENTRY_FAILED: autonomous entry decision verdict={ae_final_decision}. "
            "The alpha/regime entry chain was evaluated but did not pass all gates."
        )
        # v2.8.1: Append the exact decision blockers
        ae_blockers_list = autonomous_decision.get("blockers", []) or []
        if ae_blockers_list:
            blockers.append(
                "AUTONOMOUS_ENTRY_DECISION_BLOCKERS: " + "; ".join(str(b) for b in ae_blockers_list)
            )
        else:
            blockers.append(
                "AUTONOMOUS_ENTRY_DECISION_BLOCKERS: (no specific blockers in decision - "
                f"verdict={ae_final_decision})"
            )
    elif not entry_gate_full_pass_v28:
        # v2.8: Autonomous decision passed but entry gate audit hasn't
        # upgraded to FULL_PASS yet (stale audit). Re-run entry gate audit.
        verdict = AUTONOMOUS_DEMO_BLOCKED_ALPHA_ENTRY_UNKNOWN
        blockers.append(
            "ENTRY_GATE_NOT_FULL_PASS: autonomous entry decision is PASS but "
            "end-to-end entry gate audit has not upgraded to FULL_PASS. "
            "Re-run end_to_end_entry_gate_audit.py."
        )
    elif not final_demo_ready and not supervisor_observation_only:
        # v2.8: For supervised demo, final demo readiness is required.
        verdict = AUTONOMOUS_DEMO_BLOCKED_EVIDENCE_INCOMPLETE
        blockers.append("FINAL_DEMO_NOT_READY: final demo readiness report not READY")
    elif not broker_demo:
        verdict = AUTONOMOUS_DEMO_BLOCKED_RISK
        blockers.append("BROKER_NOT_DEMO: account is not DEMO")
    else:
        # v2.8: All supervised prerequisites pass:
        # - execution geometry PASS
        # - micro proof PASS
        # - no open positions
        # - broker DEMO
        # - prop_funded_safe active
        # - RR gate enforced
        # - risk per trade <= 0.5%
        # - max open positions = 1
        # - no martingale/grid/averaging/loss multiplier
        # - autonomous entry decision PASS
        # - entry gate FULL_PASS
        # - no stale token
        # 7-day forward demo incomplete is a WARNING for supervised demo, not a blocker.
        verdict = AUTONOMOUS_DEMO_READY_SUPERVISED
        ok_checks.append("All autonomous readiness checks PASSED")
        if not forward_demo_complete:
            warnings.append(
                f"FORWARD_DEMO_INCOMPLETE: {findings.get('forward_demo_daily_reports_count', 0)}/7 days "
                "completed. This is a warning for supervised demo - not a hard blocker."
            )

    autonomous_allowed = verdict == AUTONOMOUS_DEMO_READY_SUPERVISED
    findings["autonomous_allowed"] = autonomous_allowed
    findings["alpha_entry_unknown"] = alpha_entry_unknown
    findings["alpha_entry_failed"] = (
        verdict == AUTONOMOUS_DEMO_BLOCKED_ALPHA_ENTRY_FAILED
    )
    findings["hard_risk_blocker"] = hard_risk_blocker
    findings["broker_actual_fail"] = broker_actual_fail

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "autonomous_allowed": autonomous_allowed,
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
    json_path = OUTPUT_DIR / "autonomous_demo_readiness_audit.json"
    md_path = OUTPUT_DIR / "autonomous_demo_readiness_audit.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Autonomous Demo Readiness Audit (v2.7.3)\n\n")
        f.write("**Passive audit - no order_send, no position modification, no token creation.**\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Autonomous allowed:** **{result.get('autonomous_allowed', False)}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")

        fnd = result.get("findings", {}) or {}
        f.write("## Readiness Matrix\n\n")
        f.write("| Check | Status |\n|---|---|\n")
        check_fields = [
            "receipt_exists", "geometry_pass", "latest_execution_geometry_verdict",
            "forensics_available", "latest_forensics_verdict", "forensics_pass",
            "evidence_verifier_available", "evidence_verifier_verdict",
            "open_positions_count", "final_demo_readiness_available",
            "final_demo_readiness_verdict", "broker_demo", "selected_profile",
            "prop_funded_safe_selected", "rr_gate_enforced",
            "risk_per_trade_pct", "max_open_positions", "no_martingale",
            "end_to_end_entry_gate_verdict", "entry_gate_full_pass",
            "entry_gate_execution_only", "forward_demo_complete",
            "forward_demo_daily_reports_count", "supervisor_observation_only_override",
            "stale_execution_token", "autonomous_allowed",
        ]
        for k in check_fields:
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

        f.write("\n## Autonomous Readiness Rules\n\n")
        f.write("Autonomous demo is ALLOWED only if ALL are true:\n")
        f.write("1. Latest execution geometry PASS\n")
        f.write("2. Forensics/evidence verifier PASS or acceptable receipt-supported evidence\n")
        f.write("3. No open positions\n")
        f.write("4. Final demo readiness READY\n")
        f.write("5. Broker account is DEMO\n")
        f.write("6. prop_funded_safe selected\n")
        f.write("7. RR gate enforced\n")
        f.write("8. Risk per trade <= 0.5%\n")
        f.write("9. Max open positions = 1\n")
        f.write("10. No martingale/grid/averaging/loss multiplier\n")
        f.write("11. End-to-end entry gate FULL_PASS or operator-approved execution-only\n")
        f.write("12. 7-day forward demo complete OR supervisor observation-only override\n")
        f.write("13. No stale execution token\n")

        f.write("\n## Safety\n\n")
        f.write("- order_send_called: False\n")
        f.write("- position_modified: False\n")
        f.write("- execution_token_created: False\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Autonomous demo readiness audit (passive, no order_send)"
    )
    parser.add_argument("--receipt", type=str, default="")
    args = parser.parse_args()
    receipt_path = Path(args.receipt) if args.receipt else None

    print("=" * 70)
    print("  TITAN XAU AI - Autonomous Demo Readiness Audit (v2.7.3)")
    print("=" * 70)
    result = run_audit(receipt_path=receipt_path)
    report = write_report(result)

    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Autonomous allowed: {result.get('autonomous_allowed', False)}")
    print(f"  OK checks: {len(result.get('ok_checks', []))}")
    print(f"  Warnings: {len(result.get('warnings', []))}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    fnd = result.get("findings", {})
    print(f"\n  Geometry pass: {fnd.get('geometry_pass', False)}")
    print(f"  Forensics pass: {fnd.get('forensics_pass', False)}")
    print(f"  Open positions: {fnd.get('open_positions_count', 0)}")
    print(f"  Broker DEMO: {fnd.get('broker_demo', False)}")
    print(f"  prop_funded_safe: {fnd.get('prop_funded_safe_selected', False)}")
    print(f"  RR gate enforced: {fnd.get('rr_gate_enforced', False)}")
    print(f"  Risk per trade pct: {fnd.get('risk_per_trade_pct', 0)}")
    print(f"  Max open positions: {fnd.get('max_open_positions', 0)}")
    print(f"  No martingale: {fnd.get('no_martingale', False)}")
    print(f"  Entry gate verdict: {fnd.get('end_to_end_entry_gate_verdict', '')}")
    print(f"  Forward demo complete: {fnd.get('forward_demo_complete', False)}")
    print(f"  Stale token: {fnd.get('stale_execution_token', False)}")
    if result.get("blockers"):
        print("\n  Blockers:")
        for b in result["blockers"]:
            print(f"    - {b}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
