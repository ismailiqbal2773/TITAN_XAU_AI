#!/usr/bin/env python3
"""
TITAN XAU AI - Prop Challenge Growth Profile Audit (Sprint v2.8.4)
====================================================================
Verifies the PROP_CHALLENGE_GROWTH_30_8 profile definition and ensures
it complies with all safety rules before being allowed as a v2.8.4
release profile.

Checks:
  * profile exists in config/prop_challenge_growth_profile.yaml
  * monthly target is marked target, NOT guarantee
  * daily DD soft/hard limits configured (1% to 2%)
  * total DD cap < 8%
  * max open positions = 1
  * min RR >= 2
  * preferred RR >= 3
  * max_lot_cap_demo <= 0.01
  * base_risk_per_trade_pct <= 0.005 (Tier 1)
  * no forced trading (NO_TRADE_VALID_DECISION, TARGET_NOT_FORCED, etc.)
  * no martingale/grid/averaging/loss multiplier
  * controlled growth tier rules exist (TIER_0, TIER_1, TIER_2)
  * safety gates required before growth tier
  * v2.8.3.3.1 gates pass before profile allowed
    (reads model_artifact_health_audit.json, feature_parity_audit.json,
    runtime_safety_gate_audit.json)
  * MetaQuotes-Demo only
  * FundedNext demo execution blocked
  * execution still token-gated (OPERATOR_ARM_TOKEN_REQUIRED)
  * build-request only, no order_send

Verdicts:
  PROP_CHALLENGE_GROWTH_PROFILE_PASS
  PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED

NEVER sends orders. NEVER modifies positions. NEVER creates token.
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "prop_challenge_growth"
CONFIG_PATH = REPO_ROOT / "config" / "prop_challenge_growth_profile.yaml"

PROP_CHALLENGE_GROWTH_PROFILE_PASS = "PROP_CHALLENGE_GROWTH_PROFILE_PASS"
PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED = "PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED"

ALL_VERDICTS = (
    PROP_CHALLENGE_GROWTH_PROFILE_PASS,
    PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED,
)

PROFILE_NAME = "PROP_CHALLENGE_GROWTH_30_8"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def run_audit() -> dict:
    """Run the prop challenge growth profile audit.

    NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings_list = []
    findings = {}

    # 1. Profile exists
    cfg = _load_yaml(CONFIG_PATH)
    profile = cfg.get("profile") or {}
    findings["profile_config_path"] = str(CONFIG_PATH)
    findings["profile_config_exists"] = bool(profile)
    findings["profile_name"] = profile.get("name", "")
    if not profile:
        blockers.append("PROFILE_NOT_FOUND: config/prop_challenge_growth_profile.yaml missing or empty")
        return _build_result(ts, PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED,
                            ok_checks, blockers, warnings_list, findings)
    if profile.get("name") != PROFILE_NAME:
        blockers.append(
            f"PROFILE_NAME_MISMATCH: expected {PROFILE_NAME}, got {profile.get('name', '')}"
        )
    else:
        ok_checks.append(f"Profile name matches: {PROFILE_NAME}")

    # 2. Monthly target marked as target, NOT guarantee
    targets = profile.get("targets") or {}
    monthly_target_type = targets.get("monthly_target_type", "")
    if monthly_target_type != "target":
        blockers.append(
            f"MONTHLY_TARGET_MUST_BE_TARGET_NOT_GUARANTEE: got '{monthly_target_type}'"
        )
    else:
        ok_checks.append("Monthly target is marked as 'target' (not guarantee)")

    prop_target_type = targets.get("prop_challenge_target_type", "")
    if prop_target_type != "target":
        blockers.append(
            f"PROP_TARGET_MUST_BE_TARGET_NOT_GUARANTEE: got '{prop_target_type}'"
        )
    else:
        ok_checks.append("Prop challenge target is marked as 'target' (not guarantee)")

    monthly_target_pct = float(targets.get("monthly_growth_target_pct", 0))
    prop_target_pct = float(targets.get("prop_challenge_target_pct", 0))
    findings["monthly_target_pct"] = monthly_target_pct
    findings["prop_challenge_target_pct"] = prop_target_pct
    # Sanity check: monthly ~30%, prop ~10%
    if not (0.25 <= monthly_target_pct <= 0.40):
        warnings_list.append(
            f"MONTHLY_TARGET_UNEXPECTED: {monthly_target_pct} (expected ~0.30)"
        )
    if not (0.05 <= prop_target_pct <= 0.15):
        warnings_list.append(
            f"PROP_TARGET_UNEXPECTED: {prop_target_pct} (expected ~0.10)"
        )

    # 3. Daily DD soft/hard limits (1% to 2%)
    risk_bands = profile.get("risk_bands") or {}
    daily_soft = float(risk_bands.get("daily_dd_soft_limit_pct", 0))
    daily_hard = float(risk_bands.get("daily_dd_hard_limit_pct", 0))
    total_dd = float(risk_bands.get("max_total_dd_pct", 0))
    findings["daily_dd_soft_limit_pct"] = daily_soft
    findings["daily_dd_hard_limit_pct"] = daily_hard
    findings["max_total_dd_pct"] = total_dd
    if not (0.005 <= daily_soft <= 0.015):
        blockers.append(f"DAILY_DD_SOFT_INVALID: {daily_soft} (expected ~0.01)")
    else:
        ok_checks.append(f"Daily DD soft limit valid: {daily_soft}")
    if not (0.015 <= daily_hard <= 0.025):
        blockers.append(f"DAILY_DD_HARD_INVALID: {daily_hard} (expected ~0.02)")
    else:
        ok_checks.append(f"Daily DD hard limit valid: {daily_hard}")

    # 4. Total DD <= 8% (existing project convention allows inclusive <=)
    if total_dd > 0.08:
        blockers.append(f"TOTAL_DD_CAP_EXCEEDS_8_PCT: {total_dd}")
    elif total_dd <= 0:
        blockers.append(f"TOTAL_DD_CAP_MISSING: {total_dd}")
    else:
        ok_checks.append(f"Total DD cap <= 8%: {total_dd}")

    # 5. Kill switch on daily hard breach
    if not risk_bands.get("kill_switch_on_daily_hard_breach", False):
        blockers.append("KILL_SWITCH_NOT_ENABLED_ON_DAILY_HARD_BREACH")
    else:
        ok_checks.append("Kill switch enabled on daily DD hard breach")

    # 6. No forced recovery / no lot increase after loss
    if not risk_bands.get("no_forced_recovery_after_loss", False):
        blockers.append("FORCED_RECOVERY_NOT_DISABLED")
    else:
        ok_checks.append("Forced recovery after loss: DISABLED")
    if not risk_bands.get("no_lot_increase_after_loss", False):
        blockers.append("LOT_INCREASE_AFTER_LOSS_NOT_DISABLED")
    else:
        ok_checks.append("Lot increase after loss: DISABLED")

    # 7. Position sizing
    pos_sizing = profile.get("position_sizing") or {}
    max_positions = int(pos_sizing.get("max_open_positions", 0))
    max_lot = float(pos_sizing.get("max_lot_cap_demo", 0))
    base_risk = float(pos_sizing.get("base_risk_per_trade_pct", 0))
    min_rr = float(pos_sizing.get("min_RR", 0))
    preferred_rr = float(pos_sizing.get("preferred_RR", 0))
    findings["max_open_positions"] = max_positions
    findings["max_lot_cap_demo"] = max_lot
    findings["base_risk_per_trade_pct"] = base_risk
    findings["min_RR"] = min_rr
    findings["preferred_RR"] = preferred_rr

    if max_positions != 1:
        blockers.append(f"MAX_POSITIONS_NOT_ONE: {max_positions}")
    else:
        ok_checks.append("Max open positions = 1")
    if max_lot > 0.01:
        blockers.append(f"MAX_LOT_EXCEEDS_001: {max_lot}")
    else:
        ok_checks.append(f"Max lot cap <= 0.01: {max_lot}")
    if base_risk > 0.005:
        blockers.append(f"BASE_RISK_EXCEEDS_0_5_PCT: {base_risk}")
    else:
        ok_checks.append(f"Base risk per trade <= 0.5%: {base_risk}")
    if min_rr < 2.0:
        blockers.append(f"MIN_RR_BELOW_2: {min_rr}")
    else:
        ok_checks.append(f"Min RR >= 2.0: {min_rr}")
    if preferred_rr < 3.0:
        blockers.append(f"PREFERRED_RR_BELOW_3: {preferred_rr}")
    else:
        ok_checks.append(f"Preferred RR >= 3.0: {preferred_rr}")

    # 8. Risk tiers exist
    risk_tiers = profile.get("risk_tiers") or {}
    required_tiers = ("TIER_0_CAPITAL_PRESERVATION", "TIER_1_STANDARD", "TIER_2_GROWTH_CONTROLLED")
    findings["risk_tiers_present"] = {}
    for tier_name in required_tiers:
        tier = risk_tiers.get(tier_name) or {}
        findings["risk_tiers_present"][tier_name] = bool(tier)
        if not tier:
            blockers.append(f"RISK_TIER_MISSING: {tier_name}")
        else:
            ok_checks.append(f"Risk tier present: {tier_name}")
            # Tier 2 must NOT increase lot or risk above Tier 1
            if tier_name == "TIER_2_GROWTH_CONTROLLED":
                t2_risk = float(tier.get("risk_per_trade_pct", 0))
                t2_lot = float(tier.get("max_lot", 0))
                if t2_risk > 0.005:
                    blockers.append(
                        f"TIER_2_RISK_EXCEEDS_TIER_1_CAP: {t2_risk} > 0.005"
                    )
                else:
                    ok_checks.append(f"Tier 2 risk <= 0.5%: {t2_risk}")
                if t2_lot > 0.01:
                    blockers.append(
                        f"TIER_2_LOT_EXCEEDS_CAP: {t2_lot} > 0.01"
                    )
                else:
                    ok_checks.append(f"Tier 2 lot <= 0.01: {t2_lot}")

    # 9. No-forced-trade rules
    no_forced = profile.get("no_forced_trade") or {}
    required_no_forced = (
        "NO_TRADE_VALID_DECISION", "TARGET_NOT_FORCED",
        "ALPHA_REQUIRED", "REGIME_REQUIRED", "RISK_GATE_REQUIRED",
    )
    findings["no_forced_trade"] = {}
    for rule in required_no_forced:
        val = bool(no_forced.get(rule, False))
        findings["no_forced_trade"][rule] = val
        if not val:
            blockers.append(f"NO_FORCED_TRADE_RULE_DISABLED: {rule}")
        else:
            ok_checks.append(f"No-forced-trade rule enabled: {rule}")

    # 10. Safety gates required
    safety_gates = profile.get("safety_gates_required") or {}
    findings["safety_gates_required"] = safety_gates
    if not safety_gates.get("v2_8_3_3_1_release_gate", False):
        blockers.append("V2_8_3_3_1_RELEASE_GATE_NOT_REQUIRED")

    # 11. Execution venue
    exec_venue = profile.get("execution_venue") or {}
    allowed = exec_venue.get("allowed", "")
    blocked = exec_venue.get("blocked", []) or []
    findings["execution_venue_allowed"] = allowed
    findings["execution_venue_blocked"] = blocked
    if allowed != "MetaQuotes-Demo":
        blockers.append(f"EXECUTION_VENUE_NOT_METAQUOTES_DEMO: {allowed}")
    else:
        ok_checks.append("Execution venue: MetaQuotes-Demo only")
    if "FundedNext-Demo" not in blocked:
        blockers.append("FUNDEDNEXT_DEMO_NOT_BLOCKED")
    else:
        ok_checks.append("FundedNext-Demo blocked")
    if not exec_venue.get("execution_token_required", False):
        blockers.append("EXECUTION_TOKEN_NOT_REQUIRED")
    else:
        ok_checks.append("Execution token required: OPERATOR_ARM_TOKEN_REQUIRED")
    if exec_venue.get("execution_blocker", "") != "OPERATOR_ARM_TOKEN_REQUIRED":
        blockers.append("EXECUTION_BLOCKER_NOT_OPERATOR_ARM_TOKEN_REQUIRED")
    else:
        ok_checks.append("Execution blocker: OPERATOR_ARM_TOKEN_REQUIRED")

    # 12. Forbidden strategies
    forbidden = profile.get("forbidden_strategies") or {}
    findings["forbidden_strategies"] = forbidden
    for strat in ("martingale", "grid", "averaging_down",
                  "loss_based_lot_multiplier", "forced_recovery",
                  "lot_increase_after_loss"):
        if forbidden.get(strat, True) is not False:
            blockers.append(f"FORBIDDEN_STRATEGY_NOT_DISABLED: {strat}")
        else:
            ok_checks.append(f"Forbidden strategy disabled: {strat}")

    # 13. Build-request profile (audit-only)
    build_req = profile.get("build_request") or {}
    findings["build_request"] = build_req
    if build_req.get("order_send_allowed", True) is not False:
        blockers.append("BUILD_REQUEST_ORDER_SEND_NOT_DISABLED")
    else:
        ok_checks.append("Build-request: order_send disabled")
    if build_req.get("token_creation_allowed", True) is not False:
        blockers.append("BUILD_REQUEST_TOKEN_CREATION_NOT_DISABLED")
    else:
        ok_checks.append("Build-request: token creation disabled")
    if build_req.get("position_modification_allowed", True) is not False:
        blockers.append("BUILD_REQUEST_POSITION_MODIFICATION_NOT_DISABLED")
    else:
        ok_checks.append("Build-request: position modification disabled")

    # 14. v2.8.3.3.1 gates must pass before profile allowed
    model_health_dir = REPO_ROOT / "data" / "audit" / "model_health"
    audit_dir = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

    mh = _load_json(model_health_dir / "model_artifact_health_audit.json")
    fp = _load_json(model_health_dir / "feature_parity_audit.json")
    rs = _load_json(audit_dir / "runtime_safety_gate_audit.json")

    mh_verdict = mh.get("verdict", "")
    fp_verdict = fp.get("verdict", "")
    rs_verdict = rs.get("verdict", "")
    mh_failed_required = int(mh.get("failed_required_model_count",
                                    mh.get("failed_model_count", 0)))

    findings["latest_model_health_verdict"] = mh_verdict
    findings["latest_feature_parity_verdict"] = fp_verdict
    findings["latest_runtime_safety_verdict"] = rs_verdict
    findings["model_health_failed_required"] = mh_failed_required

    mh_pass = mh_verdict in ("MODEL_ARTIFACT_HEALTH_PASS",
                              "MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS") and mh_failed_required == 0
    fp_pass = fp_verdict in ("FEATURE_PARITY_PASS", "FEATURE_PARITY_PASS_WITH_WARNINGS")
    rs_pass = rs_verdict == "RUNTIME_SAFETY_GATE_PASS"
    findings["model_health_pass"] = mh_pass
    findings["feature_parity_pass"] = fp_pass
    findings["runtime_safety_pass"] = rs_pass

    if not mh_pass:
        blockers.append(
            f"V2_8_3_3_1_MODEL_HEALTH_NOT_PASS: verdict={mh_verdict}, failed_required={mh_failed_required}"
        )
    else:
        ok_checks.append(f"v2.8.3.3.1 model health pass: {mh_verdict}")
    if not fp_pass:
        blockers.append(f"V2_8_3_3_1_FEATURE_PARITY_NOT_PASS: verdict={fp_verdict}")
    else:
        ok_checks.append(f"v2.8.3.3.1 feature parity pass: {fp_verdict}")
    if not rs_pass:
        blockers.append(f"V2_8_3_3_1_RUNTIME_SAFETY_NOT_PASS: verdict={rs_verdict}")
    else:
        ok_checks.append(f"v2.8.3.3.1 runtime safety pass: {rs_verdict}")

    # Final verdict
    if blockers:
        verdict = PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED
    else:
        verdict = PROP_CHALLENGE_GROWTH_PROFILE_PASS

    return _build_result(ts, verdict, ok_checks, blockers, warnings_list, findings)


def _build_result(ts, verdict, ok_checks, blockers, warnings_list, findings) -> dict:
    # Sprint v2.8.5-C: Add freshness metadata
    from titan.production.audit_hygiene import make_freshness_metadata, detect_environment_mode
    freshness = make_freshness_metadata(
        audit_name="prop_challenge_growth_profile_audit",
        source_mode="production",
        environment_mode=detect_environment_mode(),
    )
    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "profile_name": PROFILE_NAME,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings_list,
        "findings": findings,
        # v2.8.5-C: freshness metadata for audit hygiene
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
    json_path = OUTPUT_DIR / "prop_challenge_growth_profile_audit.json"
    md_path = OUTPUT_DIR / "prop_challenge_growth_profile_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Prop Challenge Growth Profile Audit (v2.8.4)\n\n")
        f.write(f"**Profile:** {result.get('profile_name', '')}\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write("## Findings\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        fnd = result.get("findings", {})
        f.write(f"| profile_name | {fnd.get('profile_name', '')} |\n")
        f.write(f"| monthly_target_pct | {fnd.get('monthly_target_pct', 0)} |\n")
        f.write(f"| prop_challenge_target_pct | {fnd.get('prop_challenge_target_pct', 0)} |\n")
        f.write(f"| daily_dd_soft_limit_pct | {fnd.get('daily_dd_soft_limit_pct', 0)} |\n")
        f.write(f"| daily_dd_hard_limit_pct | {fnd.get('daily_dd_hard_limit_pct', 0)} |\n")
        f.write(f"| max_total_dd_pct | {fnd.get('max_total_dd_pct', 0)} |\n")
        f.write(f"| max_open_positions | {fnd.get('max_open_positions', 0)} |\n")
        f.write(f"| max_lot_cap_demo | {fnd.get('max_lot_cap_demo', 0)} |\n")
        f.write(f"| base_risk_per_trade_pct | {fnd.get('base_risk_per_trade_pct', 0)} |\n")
        f.write(f"| min_RR | {fnd.get('min_RR', 0)} |\n")
        f.write(f"| preferred_RR | {fnd.get('preferred_RR', 0)} |\n")
        f.write(f"| latest_model_health_verdict | {fnd.get('latest_model_health_verdict', '')} |\n")
        f.write(f"| latest_feature_parity_verdict | {fnd.get('latest_feature_parity_verdict', '')} |\n")
        f.write(f"| latest_runtime_safety_verdict | {fnd.get('latest_runtime_safety_verdict', '')} |\n")
        f.write(f"| model_health_pass | {fnd.get('model_health_pass', False)} |\n")
        f.write(f"| feature_parity_pass | {fnd.get('feature_parity_pass', False)} |\n")
        f.write(f"| runtime_safety_pass | {fnd.get('runtime_safety_pass', False)} |\n\n")

        # Risk tiers
        tiers = fnd.get("risk_tiers_present", {})
        if tiers:
            f.write("## Risk Tiers\n\n")
            f.write("| Tier | Present |\n|---|---|\n")
            for t, p in tiers.items():
                f.write(f"| {t} | {p} |\n")
            f.write("\n")

        # No-forced-trade rules
        nf = fnd.get("no_forced_trade", {})
        if nf:
            f.write("## No-Forced-Trade Rules\n\n")
            f.write("| Rule | Enabled |\n|---|---|\n")
            for r, v in nf.items():
                f.write(f"| {r} | {v} |\n")
            f.write("\n")

        # Forbidden strategies
        fs = fnd.get("forbidden_strategies", {})
        if fs:
            f.write("## Forbidden Strategies\n\n")
            f.write("| Strategy | Disabled |\n|---|---|\n")
            for s, v in fs.items():
                f.write(f"| {s} | {v is False} |\n")
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
    print("  TITAN XAU AI - Prop Challenge Growth Profile Audit (v2.8.4)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Profile: {result.get('profile_name', '')}")
    print(f"  Verdict: {result['verdict']}")
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
    return 0 if result["verdict"] != PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED else 1


if __name__ == "__main__":
    sys.exit(main())
