#!/usr/bin/env python3
"""
TITAN XAU AI - Managed Demo Micro Trade Operator (Sprint 9.9.3.45.5)
=====================================================================
Orchestrates: gate check -> build request -> execute once -> monitor.

Sprint 9.9.3.45.5 changes:
  - Capture full safe order_send result fields (retcode, comment, order,
    deal, volume, price, bid, ask, request_id, retcode_external).
  - Receipt uses correct field names: order_send_result_order,
    order_send_result_deal, order_send_result_retcode,
    order_send_result_comment, requested_sl, requested_tp,
    detected_position_ticket, detected_position_identifier,
    resolved_history_position_id.
  - Never label a position ticket as order_ticket unless it is actually
    result.order. Never label a deal ticket unless it is actually
    result.deal. Zero/missing values stored as null with warning.
  - After retcode 10009: poll positions_get AND history_deals_get /
    history_orders_get around execution timestamp. Resolve actual
    position ticket, position identifier, order ticket, deal ticket,
    history position_id. Mark position_open_verified / history_verified
    / pending_history accordingly.
  - Monitor lifecycle: loop with iterations until position closed,
    timeout reached, gate blocked, or unrecoverable error. Adds
    monitor_iterations, monitor_duration_seconds, monitor_stop_reason,
    final_position_status, final_position_source,
    final_positions_get_count, final_history_match_found,
    close_deal_ticket, close_comment, realized_pl.
  - Never report final_position_status=OPEN unless final positions_get
    confirms it. If position disappears without history, return
    COMPLETED_WITH_WARNINGS or FAILED with stop_reason
    POSITION_DISAPPEARED_WITHOUT_HISTORY. Must not be STARTED.

Z AI must NOT run --execute-and-monitor.
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"
RECEIPT_PATH = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"

# Constants
TITAN_MAGIC = 202619
TITAN_COMMENT = "TITAN_DEMO_MICRO"


def _build_adaptive_config(args) -> dict:
    """Sprint 9.9.3.45.8.1: Build adaptive trailing config dict from CLI args.
    Sprint 9.9.3.45.8.2: Added dynamic TP extension config fields.

    Returns dict with:
      - adaptive_trailing_enabled (bool)
      - dynamic_tp_enabled (bool)
      - profit_corridor_enabled (bool) [True only if adaptive AND dynamic_tp both enabled]
      - adaptive_policy_mode (str)
      - breakeven_trigger_R (float)
      - trailing_trigger_R (float)
      - profit_lock_trigger_R (float)
      - min_hold_seconds (int)
      - min_monitor_iterations (int)
      - cooldown_seconds (int)
      - tp_extension_trigger_R (float)
      - tp_extension_R (float)
      - tp_extension_atr_mult (float)
      - tp_extension_cooldown_seconds (int)
      - min_profit_lock_after_tp_extension_R (float)
      - max_profit_giveback_r_trend (float)
      - max_profit_giveback_r_range (float)
    """
    adaptive_enabled = bool(getattr(args, "use_adaptive_trailing", False))
    dynamic_tp_enabled = bool(getattr(args, "use_dynamic_tp_extension", False))
    return {
        "adaptive_trailing_enabled": adaptive_enabled,
        "dynamic_tp_enabled": dynamic_tp_enabled,
        "profit_corridor_enabled": adaptive_enabled and dynamic_tp_enabled,
        "adaptive_policy_mode": getattr(args, "adaptive_policy_mode", "balanced_conservative"),
        "breakeven_trigger_R": float(getattr(args, "breakeven_trigger_r", 1.0)),
        "trailing_trigger_R": float(getattr(args, "trailing_trigger_r", 1.75)),
        "profit_lock_trigger_R": float(getattr(args, "profit_lock_trigger_r", 3.0)),
        "min_hold_seconds": int(getattr(args, "min_hold_seconds", 60)),
        "min_monitor_iterations": int(getattr(args, "min_monitor_iterations", 3)),
        "cooldown_seconds": int(getattr(args, "sl_update_cooldown_seconds", 60)),
        # Sprint 9.9.3.45.8.2: dynamic TP extension config
        "tp_extension_trigger_R": float(getattr(args, "tp_extension_trigger_r", 2.0)),
        "tp_extension_R": float(getattr(args, "tp_extension_r", 1.0)),
        "tp_extension_atr_mult": float(getattr(args, "tp_extension_atr_mult", 2.0)),
        "tp_extension_cooldown_seconds": int(getattr(args, "tp_extension_cooldown_seconds", 120)),
        "min_profit_lock_after_tp_extension_R": float(getattr(args, "min_profit_lock_after_tp_extension_r", 1.0)),
        "max_profit_giveback_r_trend": float(getattr(args, "max_profit_giveback_r_trend", 1.0)),
        "max_profit_giveback_r_range": float(getattr(args, "max_profit_giveback_r_range", 0.5)),
    }


def _build_adaptive_policy_kwargs(args) -> dict:
    """Sprint 9.9.3.45.8.1: Build adaptive_policy_kwargs for orchestrator.

    Only called when use_adaptive_trailing=True.
    """
    return {
        "mode": getattr(args, "adaptive_policy_mode", "balanced_conservative"),
        "breakeven_trigger_R": float(getattr(args, "breakeven_trigger_r", 1.0)),
        "trailing_trigger_R": float(getattr(args, "trailing_trigger_r", 1.75)),
        "profit_lock_trigger_R": float(getattr(args, "profit_lock_trigger_r", 3.0)),
        "min_hold_seconds": int(getattr(args, "min_hold_seconds", 60)),
        "min_monitor_iterations": int(getattr(args, "min_monitor_iterations", 3)),
        "cooldown_seconds": int(getattr(args, "sl_update_cooldown_seconds", 60)),
    }


def run_check_only(args=None) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    from titan.production.demo_micro_execution_gate import DemoMicroExecutionGate
    gate = DemoMicroExecutionGate()
    gate_result = gate.evaluate()
    result = {
        "timestamp_utc": ts,
        "mode": "check_only",
        "verdict": "MANAGED_DEMO_MICRO_READY" if "PASS" in gate_result.verdict.value else "MANAGED_DEMO_MICRO_BLOCKED",
        "gate_verdict": gate_result.verdict.value,
        "gate_blockers": gate_result.blockers,
        "next_action": "Run --dry-arm to arm managed trade",
    }
    # Sprint 9.9.3.45.8.1: include adaptive trailing config in report
    if args is not None:
        result["adaptive_trailing_config"] = _build_adaptive_config(args)
    return result


def run_dry_arm(args=None) -> dict:
    result = run_check_only(args)
    result["mode"] = "dry_arm"
    result["armed"] = "PASS" in result.get("gate_verdict", "")
    result["next_action"] = "Run --build-request to generate executable order preview"
    return result


def run_build_request(direction: str = "BUY", entry_price: float = 2000.0,
                       sl: float = 0.0, tp: float = 0.0, args=None) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    from titan.production.demo_micro_order_builder import DemoMicroOrderBuilder
    builder = DemoMicroOrderBuilder()

    # Sprint 9.9.3.45.8.3: profile-driven geometry
    account_profile_name = getattr(args, "account_profile", "retail_demo_micro") if args else "retail_demo_micro"
    initial_tp_r = getattr(args, "initial_tp_r", 3.0) if args else 3.0
    use_dynamic_tp = bool(getattr(args, "use_dynamic_tp_extension", False)) if args else False
    use_adaptive = bool(getattr(args, "use_adaptive_trailing", False)) if args else False

    # Load account profile
    import yaml as _yaml
    account_profiles_path = REPO_ROOT / "config" / "account_profiles.yaml"
    account_profile = {}
    if account_profiles_path.exists():
        try:
            with open(account_profiles_path, "r", encoding="utf-8") as f:
                ap_data = _yaml.safe_load(f) or {}
            account_profile = ap_data.get("profiles", {}).get(account_profile_name, {})
        except Exception:
            pass

    # If initial_tp_r provided, compute TP from entry and SL
    computed_tp = tp
    computed_sl = sl
    if initial_tp_r > 0 and sl == 0:
        # Default SL = entry - 10.0 (10 USD for XAUUSD at 2000)
        computed_sl = entry_price - 10.0 if direction == "BUY" else entry_price + 10.0
    if initial_tp_r > 0:
        R = abs(entry_price - computed_sl) if computed_sl > 0 else 10.0
        if direction == "BUY":
            computed_tp = entry_price + (initial_tp_r * R)
        else:
            computed_tp = entry_price - (initial_tp_r * R)

    build_result = builder.build_preview(
        direction=direction, entry_price=entry_price, sl=computed_sl, tp=computed_tp,
        safe_fallback=False,
    )
    result = {
        "timestamp_utc": ts,
        "mode": "build_request",
        "verdict": build_result["verdict"],
        "executable_status": build_result.get("executable_status"),
        "preview": build_result.get("preview"),
        "next_action": "If EXECUTABLE_WITH_PROTECTIVE_SL_TP, run --execute-and-monitor locally",
    }
    # Sprint 9.9.3.45.8.1: include adaptive trailing config in report
    if args is not None:
        result["adaptive_trailing_config"] = _build_adaptive_config(args)

    # Sprint 9.9.3.45.8.14: Build-request geometry proof
    if computed_sl > 0 and computed_tp > 0:
        if direction == "BUY":
            req_risk_distance = entry_price - computed_sl
            req_reward_distance = computed_tp - entry_price
        else:
            req_risk_distance = computed_sl - entry_price
            req_reward_distance = entry_price - computed_tp
        req_actual_rr = req_reward_distance / req_risk_distance if req_risk_distance > 0 else 0.0
        req_minimum_rr = 2.0
        if account_profile_name and ("prop" in account_profile_name or "funded" in account_profile_name):
            req_minimum_rr = 2.0
        result["execution_geometry"] = {
            "side": direction,
            "estimated_entry": entry_price,
            "estimated_sl": computed_sl,
            "estimated_tp": computed_tp,
            "sl_distance": req_risk_distance,
            "tp_distance": req_reward_distance,
            "actual_RR": round(req_actual_rr, 4),
            "minimum_RR": req_minimum_rr,
            "initial_tp_R": initial_tp_r,
            "geometry_verdict": "EXECUTION_GEOMETRY_PASS" if req_actual_rr >= req_minimum_rr else "EXECUTION_GEOMETRY_RR_BELOW_MINIMUM",
            "geometry_blockers": [] if req_actual_rr >= req_minimum_rr else [
                f"EXECUTION_GEOMETRY_RR_BELOW_MINIMUM: actual_RR={req_actual_rr:.4f} < minimum_RR={req_minimum_rr}"
            ],
        }
        if req_actual_rr < req_minimum_rr:
            result["verdict"] = "BLOCKED"
            if "blockers" not in result:
                result["blockers"] = []
            result["blockers"].append(
                f"EXECUTION_GEOMETRY_RR_BELOW_MINIMUM: actual_RR={req_actual_rr:.4f} < minimum_RR={req_minimum_rr}"
            )

    # Sprint 9.9.3.45.8.3: profile-driven geometry and cost/RR validation
    result["account_profile"] = account_profile_name
    result["initial_tp_R"] = initial_tp_r
    result["dynamic_tp_enabled"] = use_dynamic_tp

    # Dynamic TP geometry validation
    dynamic_tp_trigger_r = float(getattr(args, "tp_extension_trigger_r", 2.0)) if args else 2.0
    geometry_blockers = []
    if use_dynamic_tp:
        if initial_tp_r <= dynamic_tp_trigger_r:
            geometry_blockers.append(
                f"DYNAMIC_TP_TRIGGER_BEYOND_STATIC_TP: initial_tp_R={initial_tp_r} <= dynamic_tp_trigger_R={dynamic_tp_trigger_r}"
            )
            result["verdict"] = "BLOCKED"
        if initial_tp_r < 3.0:
            geometry_blockers.append(
                f"INITIAL_TP_TOO_CLOSE_FOR_DYNAMIC_TP: initial_tp_R={initial_tp_r} < 3.0"
            )
            result["verdict"] = "BLOCKED"
        # RR 1:1 blocked for prop/funded/institutional
        is_prop_or_funded = (
            "prop_firm" in account_profile_name
            or "funded" in account_profile_name
            or "institutional" in account_profile_name
        )
        if is_prop_or_funded and initial_tp_r < 2.0:
            geometry_blockers.append(
                f"RR_1_1_BLOCKED_FOR_PROP_DYNAMIC_TP: initial_tp_R={initial_tp_r} < 2.0 for {account_profile_name}"
            )
            result["verdict"] = "BLOCKED"

    result["dynamic_tp_geometry_valid"] = len(geometry_blockers) == 0
    if geometry_blockers:
        result["geometry_blockers"] = geometry_blockers

    # Transaction cost and net profit validation (if we have valid SL/TP)
    if computed_sl > 0 and computed_tp > 0:
        try:
            from titan.production.transaction_cost_engine import TransactionCostEngine
            from titan.production.net_profit_target_validator import NetProfitTargetValidator

            cost_profile = account_profile.get("commission_model", "zero_spread_demo")
            validator = NetProfitTargetValidator(
                account_profile_name=account_profile_name,
                cost_profile_name=cost_profile,
            )
            validation = validator.validate(
                direction=direction,
                entry_price=entry_price,
                sl_price=computed_sl,
                tp_price=computed_tp,
                lot=0.01,
                initial_tp_R=initial_tp_r,
                dynamic_tp_trigger_R=dynamic_tp_trigger_r,
                dynamic_tp_enabled=use_dynamic_tp,
            )
            result["transaction_cost"] = validation.cost_result
            result["net_profit_validation"] = validation.to_dict()
            result["gross_RR"] = validation.target_net_RR  # Will be overridden below
            # Actually get gross_RR from cost result
            result["gross_RR"] = validation.cost_result.get("gross_RR", 0.0)
            result["net_RR"] = validation.cost_result.get("net_RR", 0.0)
            result["gross_profit"] = validation.target_gross_profit
            result["net_profit"] = validation.expected_net_profit
            result["total_transaction_cost"] = validation.expected_total_transaction_cost
            result["net_profit_target_reached"] = validation.net_profit_target_reached
            if validation.blockers:
                result["verdict"] = "BLOCKED"
                if "blockers" not in result:
                    result["blockers"] = []
                result["blockers"].extend(validation.blockers)
        except Exception as e:
            result["cost_validation_error"] = str(e)

    # Margin/leverage guard
    try:
        from titan.production.margin_leverage_guard import MarginLeverageGuard
        broker_profile_name = "metaquotes_demo"
        guard = MarginLeverageGuard(
            account_profile_name=account_profile_name,
            broker_profile_name=broker_profile_name,
        )
        margin_result = guard.calculate(
            price=entry_price, sl_price=computed_sl, lot=0.01,
        )
        result["margin_risk"] = margin_result.to_dict()
        result["prop_firm_safe"] = margin_result.prop_firm_safe
        result["retail_safe"] = margin_result.retail_safe
        result["institutional_safe"] = margin_result.institutional_safe
        if margin_result.blockers:
            if result["verdict"] != "BLOCKED":
                result["verdict"] = "BLOCKED"
            if "blockers" not in result:
                result["blockers"] = []
            result["blockers"].extend(margin_result.blockers)
    except Exception as e:
        result["margin_guard_error"] = str(e)

    # Sprint 9.9.3.45.8.6: broker scoring integration
    try:
        from titan.production.broker_scoring_engine import BrokerScoringEngine
        broker_profile_name = getattr(args, "broker_profile", "metaquotes_demo") if args else "metaquotes_demo"
        scorer = BrokerScoringEngine()
        if scorer.has_broker(broker_profile_name):
            broker_score_result = scorer.score_broker(broker_profile_name)
            result["broker_score"] = broker_score_result.overall_score
            result["broker_verdict"] = broker_score_result.verdict
            result["broker_score_details"] = broker_score_result.to_dict()
            result["prop_funded_compatible"] = broker_score_result.prop_funded_compatible
            # Block build-request if broker score < 70
            if broker_score_result.overall_score < 70:
                if result["verdict"] != "BLOCKED":
                    result["verdict"] = "BLOCKED"
                if "blockers" not in result:
                    result["blockers"] = []
                result["blockers"].append(f"BROKER_BLOCKED: score={broker_score_result.overall_score} < 70")
                result["broker_block_reason"] = broker_score_result.verdict
            # Caution: allow only conservative/proof mode
            elif 70 <= broker_score_result.overall_score < 85:
                result["broker_caution"] = True
                risk_mode = getattr(args, "risk_mode", "conservative") if args else "conservative"
                if "aggressive" in risk_mode:
                    if result["verdict"] != "BLOCKED":
                        result["verdict"] = "BLOCKED"
                    if "blockers" not in result:
                        result["blockers"] = []
                    result["blockers"].append(f"BROKER_CAUTION: score={broker_score_result.overall_score}, aggressive mode blocked")
        else:
            result["broker_score"] = 0
            result["broker_verdict"] = "BROKER_SCORE_INCOMPLETE"
            result["broker_block_reason"] = "BROKER_SCORE_INCOMPLETE: broker profile not found"
    except Exception as e:
        result["broker_score_error"] = str(e)

    # Sprint 9.9.3.45.8.6: risk mode integration
    risk_mode = getattr(args, "risk_mode", "conservative") if args else "conservative"
    result["risk_mode"] = risk_mode
    risk_modes_path = REPO_ROOT / "config" / "risk_modes.yaml"
    if risk_modes_path.exists():
        try:
            import yaml as _yaml2
            with open(risk_modes_path, "r", encoding="utf-8") as f:
                rm_data = _yaml2.safe_load(f) or {}
            modes = rm_data.get("modes", {})
            mode_config = modes.get(risk_mode, {})
            result["risk_mode_config"] = mode_config
            # Check if aggressive simulation-only mode
            if mode_config.get("simulation_only", False):
                result["simulation_only"] = True
                result["executable_request"] = False
            if not mode_config.get("live_allowed", True):
                result["live_allowed"] = False
        except Exception:
            pass

    # Sprint 9.9.3.45.8.7: prop firm profile validation
    prop_firm_profile = getattr(args, "prop_firm_profile", "") if args else ""
    if prop_firm_profile:
        result["prop_firm_profile"] = prop_firm_profile
        try:
            from titan.production.prop_firm_rule_engine import PropFirmRuleEngine
            pf_engine = PropFirmRuleEngine()
            pf_result = pf_engine.validate_rules(prop_firm_profile)
            result["prop_rules_verdict"] = pf_result.verdict
            result["prop_rules_active"] = pf_result.active_for_production_proof
            result["prop_rules_simulation_only"] = pf_result.is_simulation_only
            # If active profile is blocked, block build-request
            if pf_result.verdict == "PROP_RULES_BLOCKED" and pf_result.active_for_production_proof:
                if result["verdict"] != "BLOCKED":
                    result["verdict"] = "BLOCKED"
                if "blockers" not in result:
                    result["blockers"] = []
                result["blockers"].extend(pf_result.blockers)
            # If simulation-only, mark as not executable
            if pf_result.is_simulation_only:
                result["simulation_only"] = True
                result["executable_request"] = False
        except Exception as e:
            result["prop_rules_error"] = str(e)

    # Sprint 9.9.3.45.8.7: set executable_request default
    if "executable_request" not in result:
        result["executable_request"] = result.get("verdict") == "PASS" and not result.get("simulation_only", False)

    # Sprint 9.9.3.45.8.8: prop funded optimizer integration
    prop_funded_profile = getattr(args, "prop_funded_profile", "") if args else ""
    if prop_funded_profile:
        result["prop_funded_profile"] = prop_funded_profile
        try:
            from titan.production.prop_funded_optimizer import PropFundedOptimizer
            optimizer = PropFundedOptimizer()
            opt_result = optimizer.optimize()
            # Find the selected profile
            selected = None
            for p in opt_result.profiles:
                if p.profile_name == prop_funded_profile:
                    selected = p
                    break
            if selected:
                result["optimizer_verdict"] = selected.verdict
                result["optimizer_score"] = selected.optimizer_score
                result["optimizer_monthly_return"] = selected.monthly_return_estimate
                result["optimizer_pf"] = selected.pf
                result["optimizer_sharpe"] = selected.sharpe
                result["optimizer_sortino"] = selected.sortino
                result["optimizer_wfe"] = selected.wfe
                result["optimizer_monte_carlo_survival"] = selected.monte_carlo_survival
                result["optimizer_max_dd"] = selected.max_dd
                result["optimizer_daily_dd_internal"] = selected.internal_daily_dd_pct
                result["optimizer_total_dd_internal"] = selected.internal_total_dd_pct
                result["optimizer_broker_score"] = selected.broker_score
                # If simulation-only, mark as not executable
                if selected.simulation_only:
                    result["simulation_only"] = True
                    result["executable_request"] = False
                # If blocked, block build-request
                if selected.verdict == "PROP_FUNDED_BLOCKED":
                    if result["verdict"] != "BLOCKED":
                        result["verdict"] = "BLOCKED"
                    if "blockers" not in result:
                        result["blockers"] = []
                    result["blockers"].append(f"OPTIMIZER_BLOCKED: {prop_funded_profile} verdict={selected.verdict}")
            else:
                result["optimizer_error"] = f"Profile {prop_funded_profile} not found in optimizer"
        except Exception as e:
            result["optimizer_error"] = str(e)

    return result


def _capture_order_send_result_safe(order_result) -> dict:
    """Sprint 9.9.3.45.5: Capture full safe order_send result fields.

    Returns dict with retcode, comment, order, deal, volume, price, bid,
    ask, request_id, retcode_external. Zero/missing values stored as
    None so receipt never mislabels missing data as a real ticket.
    """
    def _safe_int(v):
        try:
            iv = int(v) if v is not None else 0
            return iv if iv > 0 else None
        except Exception:
            return None

    def _safe_float(v):
        try:
            fv = float(v) if v is not None else 0.0
            return fv if fv != 0.0 else None
        except Exception:
            return None

    if order_result is None:
        return {
            "retcode": 0,
            "comment": "RESULT_NONE",
            "order": None,
            "deal": None,
            "volume": None,
            "price": None,
            "bid": None,
            "ask": None,
            "request_id": None,
            "retcode_external": None,
        }

    return {
        "retcode": int(getattr(order_result, "retcode", 0) or 0),
        "comment": str(getattr(order_result, "comment", "") or ""),
        "order": _safe_int(getattr(order_result, "order", 0)),
        "deal": _safe_int(getattr(order_result, "deal", 0)),
        "volume": _safe_float(getattr(order_result, "volume", 0)),
        "price": _safe_float(getattr(order_result, "price", 0)),
        "bid": _safe_float(getattr(order_result, "bid", 0)),
        "ask": _safe_float(getattr(order_result, "ask", 0)),
        "request_id": _safe_int(getattr(order_result, "request_id", 0)),
        "retcode_external": _safe_int(getattr(order_result, "retcode_external", 0)),
    }


def _build_receipt(*, ts: str, current_head: str, env_info: dict, acc,
                   volume: float, direction: str, sl: float, tp: float,
                   raw_result: dict, execution_success: bool) -> dict:
    """Sprint 9.9.3.45.5: Build receipt with correct field names.

    Legacy fields ``order_ticket`` / ``deal_ticket`` are only populated
    when raw result.order / result.deal are non-zero. ``position_id`` is
    NOT populated from result.position_id (that was the 9.9.3.45.4 bug
    that mislabeled position_id=0). Detection-based fields are filled
    later by _update_receipt_with_detection().
    """
    import hashlib as _hashlib
    warnings = []
    if execution_success and (raw_result["order"] is None or raw_result["deal"] is None):
        warnings.append(
            "ORDER_SEND_RESULT_INCOMPLETE: retcode=10009 but "
            f"order={raw_result['order']} deal={raw_result['deal']} "
            "position_id=0 - broker did not return full ticket information"
        )

    return {
        "timestamp_utc": ts,
        "git_commit": current_head,
        "execution_mode": "execute_and_monitor",
        "success": execution_success,
        "account_server": env_info.get("account_server", "unknown"),
        "account_login_hash": _hashlib.sha256(
            str(getattr(acc, "login", 0)).encode()
        ).hexdigest()[:16] if acc else "unknown",
        "symbol": "XAUUSD",
        "volume": volume,
        "side": direction,
        "request_magic": TITAN_MAGIC,
        "request_comment": TITAN_COMMENT,
        "requested_sl": float(sl) if sl else None,
        "requested_tp": float(tp) if tp else None,
        # Raw order_send result fields (Sprint 9.9.3.45.5)
        "order_send_result_retcode": raw_result["retcode"],
        "order_send_result_comment": raw_result["comment"],
        "order_send_result_order": raw_result["order"],
        "order_send_result_deal": raw_result["deal"],
        "order_send_result_volume": raw_result["volume"],
        "order_send_result_price": raw_result["price"],
        "order_send_result_bid": raw_result["bid"],
        "order_send_result_ask": raw_result["ask"],
        "order_send_result_request_id": raw_result["request_id"],
        "order_send_result_retcode_external": raw_result["retcode_external"],
        # Legacy compat: only populated when raw result has non-zero values
        "order_ticket": raw_result["order"],
        "deal_ticket": raw_result["deal"],
        # NOT populated from result.position_id (was the 45.4 bug)
        "position_id": None,
        # Detection-based fields - populated by _update_receipt_with_detection
        "detected_position_ticket": None,
        "detected_position_identifier": None,
        "resolved_history_position_id": None,
        "position_detected": False,
        "position_detection_method": "",
        "position_open_verified": False,
        "history_verified": False,
        "pending_history": False,
        "warnings": warnings,
        "error_reason": "" if execution_success else f"retcode={raw_result['retcode']}",
    }


def _write_receipt(receipt: dict) -> bool:
    """Write receipt atomically. Returns True on success."""
    try:
        RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(RECEIPT_PATH, "w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2, ensure_ascii=False)
        return True
    except Exception:
        return False


def _detect_position_via_positions_and_history(*, mt5, execution_ts: str,
                                                expected_order, expected_deal,
                                                detection_timeout: int = 10,
                                                detection_interval: int = 1) -> dict:
    """Sprint 9.9.3.45.5: Position detection via positions_get + history.

    Polls positions_get for TITAN_DEMO_MICRO magic/comment, and queries
    history_deals_get / history_orders_get around execution timestamp.
    Returns dict with:
      detected_position_ticket, detected_position_identifier,
      detected_position_direction, detected_position_entry_price,
      detected_position_sl, detected_position_tp,
      detected_position_current_price, detection_method,
      position_open_verified, history_verified, pending_history,
      resolved_history_position_id, history_order_ticket,
      history_deal_ticket, warnings
    """
    import time as _time

    result = {
        "detected_position_ticket": None,
        "detected_position_identifier": None,
        "detected_position_direction": "BUY",
        "detected_position_entry_price": 0.0,
        "detected_position_sl": 0.0,
        "detected_position_tp": 0.0,
        "detected_position_current_price": 0.0,
        "detection_method": "",
        "position_open_verified": False,
        "history_verified": False,
        "pending_history": False,
        "resolved_history_position_id": None,
        "history_order_ticket": None,
        "history_deal_ticket": None,
        "warnings": [],
    }

    # Parse execution timestamp
    try:
        exec_dt = datetime.fromisoformat(execution_ts.replace("Z", "+00:00"))
    except Exception:
        exec_dt = datetime.now(timezone.utc)

    from_dt = exec_dt - timedelta(minutes=5)
    to_dt = exec_dt + timedelta(minutes=5)
    now_dt = datetime.now(timezone.utc)
    if to_dt < now_dt:
        to_dt = now_dt + timedelta(minutes=1)

    # Poll positions_get for up to detection_timeout seconds
    detected_position = None
    detection_method = ""
    for attempt in range(max(1, detection_timeout)):
        positions = mt5.positions_get(symbol="XAUUSD")
        if positions:
            for p in positions:
                magic = getattr(p, "magic", 0)
                comment = getattr(p, "comment", "") or ""
                if magic == TITAN_MAGIC or TITAN_COMMENT in comment:
                    detected_position = p
                    detection_method = "positions_get_magic_comment"
                    break
        if detected_position:
            break
        _time.sleep(detection_interval)

    # Query history (deals + orders) around execution timestamp
    history_deals = []
    history_orders = []
    try:
        hd = mt5.history_deals_get(from_dt, to_dt)
        if hd:
            history_deals = list(hd)
    except Exception:
        pass
    try:
        ho = mt5.history_orders_get(from_dt, to_dt)
        if ho:
            history_orders = list(ho)
    except Exception:
        pass

    # Match history by expected_order, expected_deal, magic, or comment
    matching_history_deal = None
    matching_history_order = None
    history_position_id = None

    # Try explicit deal ticket
    if expected_deal:
        for d in history_deals:
            if getattr(d, "ticket", 0) == expected_deal:
                matching_history_deal = d
                history_position_id = getattr(d, "position_id", 0) or None
                break
    # Try explicit order ticket
    if not matching_history_deal and expected_order:
        for o in history_orders:
            if getattr(o, "ticket", 0) == expected_order:
                matching_history_order = o
                history_position_id = getattr(o, "position_id", 0) or None
                break
        for d in history_deals:
            if getattr(d, "order", 0) == expected_order:
                matching_history_deal = d
                history_position_id = getattr(d, "position_id", 0) or None
                break
    # Try magic + comment
    if not matching_history_deal and not matching_history_order:
        titan_deals = [d for d in history_deals
                       if getattr(d, "magic", 0) == TITAN_MAGIC
                       and TITAN_COMMENT in (getattr(d, "comment", "") or "")]
        if titan_deals:
            # Pick the deal whose time is closest to execution_ts
            titan_deals.sort(key=lambda d: abs(getattr(d, "time", 0) - exec_dt.timestamp()))
            matching_history_deal = titan_deals[0]
            history_position_id = getattr(matching_history_deal, "position_id", 0) or None

    # Resolve position identifier from history
    if history_position_id and not matching_history_order:
        for o in history_orders:
            if getattr(o, "position_id", 0) == history_position_id:
                matching_history_order = o
                break

    # Populate result
    if detected_position is not None:
        result["detected_position_ticket"] = getattr(detected_position, "ticket", 0) or None
        result["detected_position_identifier"] = getattr(detected_position, "identifier", None) or result["detected_position_ticket"]
        result["detected_position_direction"] = "BUY" if getattr(detected_position, "type", 1) == 0 else "SELL"
        result["detected_position_entry_price"] = float(getattr(detected_position, "price_open", 0) or 0)
        result["detected_position_sl"] = float(getattr(detected_position, "sl", 0) or 0)
        result["detected_position_tp"] = float(getattr(detected_position, "tp", 0) or 0)
        result["detected_position_current_price"] = float(getattr(detected_position, "price_current", 0) or 0)
        result["detection_method"] = detection_method
        result["position_open_verified"] = True

    if matching_history_deal is not None or matching_history_order is not None:
        result["history_verified"] = True
        result["resolved_history_position_id"] = history_position_id
        if matching_history_deal is not None:
            result["history_deal_ticket"] = getattr(matching_history_deal, "ticket", 0) or None
        if matching_history_order is not None:
            result["history_order_ticket"] = getattr(matching_history_order, "ticket", 0) or None
    elif detected_position is not None:
        # Position detected but history not yet visible - pending
        result["pending_history"] = True
        result["warnings"].append(
            "POSITION_OPEN_BUT_HISTORY_PENDING: positions_get detected position "
            "but history_deals_get/history_orders_get did not yet show the trade"
        )

    return result


def _update_receipt_with_detection(receipt: dict, detection: dict) -> dict:
    """Sprint 9.9.3.45.5: Update receipt with detection results."""
    receipt["detected_position_ticket"] = detection["detected_position_ticket"]
    receipt["detected_position_identifier"] = detection["detected_position_identifier"]
    receipt["resolved_history_position_id"] = detection["resolved_history_position_id"]
    receipt["position_detected"] = detection["detected_position_ticket"] is not None or detection["history_verified"]
    receipt["position_detection_method"] = detection["detection_method"] or ("history_verified" if detection["history_verified"] else "")
    receipt["position_open_verified"] = detection["position_open_verified"]
    receipt["history_verified"] = detection["history_verified"]
    receipt["pending_history"] = detection["pending_history"]
    if detection["warnings"]:
        receipt.setdefault("warnings", []).extend(detection["warnings"])
    return receipt


def _build_modify_applier(*, mt5, args, ok_checks) -> Optional[object]:
    """Sprint 9.9.3.45.6: Build a modify applier callable for the monitor
    loop.

    Returns None (no applier = preview-only mode) unless ALL of:
      - args.confirm_managed_trailing is True
      - args.confirm_local_operator is True
      - Local operator token is valid

    Z AI environment drift gate already blocks execute-and-monitor
    entirely, so this function is only reached on the local operator
    Windows machine. Still, we double-check the confirmations here so
    the apply path is never silently enabled.

    The applier sends TRADE_ACTION_SLTP via mt5.order_send EXACTLY ONCE
    per call. Tests mock mt5.order_send / mt5.order_modify.
    """
    if not getattr(args, "confirm_managed_trailing", False):
        return None
    if not getattr(args, "confirm_local_operator", False):
        return None

    def _applier(position_ticket: int, new_sl: float, tp: float) -> dict:
        """Send TRADE_ACTION_SLTP modify request exactly once.

        Returns {retcode, success, reason}.
        """
        try:
            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": "XAUUSD",
                "position": int(position_ticket),
                "sl": float(new_sl),
                "tp": float(tp),
            }
            # Sprint 9.9.3.45.6: prefer mt5.order_modify if available,
            # else fall back to mt5.order_send with TRADE_ACTION_SLTP.
            if hasattr(mt5, "order_modify"):
                result = mt5.order_modify(request)
            else:
                result = mt5.order_send(request)
            retcode = int(getattr(result, "retcode", 0) or 0)
            success = retcode == 10009
            reason = "TRADE_RETCODE_DONE" if success else f"retcode={retcode}"
            return {"retcode": retcode, "success": success, "reason": reason}
        except Exception as e:
            return {"retcode": 0, "success": False, "reason": f"APPLIER_ERROR: {e}"}

    ok_checks.append("SL modify applier enabled (local operator, confirm-managed-trailing)")
    return _applier


def _run_monitor_loop(*, mt5, detected_position, args, ok_checks,
                       modify_applier=None) -> dict:
    """Sprint 9.9.3.45.6: Continuous monitor lifecycle loop.

    Iterates until one of:
      - position closed (verified by history_deals_get) -> POSITION_CLOSED
      - configured timeout reached -> TIMEOUT
      - kill switch / gate blocked -> KILL_SWITCH_BLOCKED / GATE_BLOCKED
      - unrecoverable error -> ERROR
      - position disappeared without history -> POSITION_DISAPPEARED_WITHOUT_HISTORY

    The loop must NOT exit after one HOLD evaluation while position is
    still open. monitor_iterations > 1 when position remains open beyond
    one interval.

    Sprint 9.9.3.45.6 additions:
      - CLI overrides via args.monitor_duration_minutes /
        args.monitor_interval_seconds (fall back to duration_minutes /
        interval_seconds for backwards compat).
      - modify_applier integration: when set and apply conditions met,
        sends TRADE_ACTION_SLTP exactly once per MODIFY decision step.
      - Explicit stop reasons: POSITION_CLOSED, TIMEOUT,
        KILL_SWITCH_BLOCKED, GATE_BLOCKED, ERROR (plus
        POSITION_DISAPPEARED_WITHOUT_HISTORY from 45.5).
      - sl_modify_attempts list with old_sl, new_sl, tp_preserved,
        modify_reason, modify_success, modify_retcode.
      - Journal events: HOLD, BREAKEVEN_MODIFY, TRAILING_MODIFY,
        PROFIT_LOCK_MODIFY, MODIFY_BLOCKED, MODIFY_SUCCESS, MODIFY_FAILED.
    """
    import time as _time
    from titan.production.demo_micro_managed_trade_orchestrator import (
        ManagedTradeOrchestrator, SLAction,
        STOP_REASON_POSITION_CLOSED, STOP_REASON_TIMEOUT,
        STOP_REASON_KILL_SWITCH_BLOCKED, STOP_REASON_GATE_BLOCKED,
        STOP_REASON_ERROR,
    )

    # Sprint 9.9.3.45.6: CLI overrides (fall back to old attribute names
    # for backwards compat with tests written against 45.5).
    duration_minutes = (
        getattr(args, "monitor_duration_minutes", None)
        if getattr(args, "monitor_duration_minutes", None) is not None
        else getattr(args, "duration_minutes", 30)
    )
    interval_seconds = (
        getattr(args, "monitor_interval_seconds", None)
        if getattr(args, "monitor_interval_seconds", None) is not None
        else getattr(args, "interval_seconds", 5)
    )

    # Compute max iterations. For tests, allow very small durations.
    max_iterations = max(1, (duration_minutes * 60) // max(1, interval_seconds))
    # Safety cap so unit tests with duration_minutes=0 don't loop forever.
    if max_iterations > 10000:
        max_iterations = 10000

    position_ticket = detected_position["detected_position_ticket"]
    direction = detected_position["detected_position_direction"]
    entry_price = detected_position["detected_position_entry_price"]
    sl = detected_position["detected_position_sl"]
    tp = detected_position["detected_position_tp"]

    monitor_iterations = 0
    monitor_start = _time.time()
    monitor_events = []
    sl_modify_previews = []
    sl_modify_attempts = []
    breakeven_triggered = False
    trailing_triggered = False
    profit_lock_triggered = False
    final_position_status = "UNKNOWN"
    final_position_source = ""
    final_positions_get_count = 0
    final_history_match_found = False
    close_deal_ticket = None
    close_comment = ""
    realized_pl = 0.0
    monitor_stop_reason = ""
    warnings = []
    apply_mode = modify_applier is not None

    # Determine if apply path is allowed (only when applier is set AND
    # all managed confirmations are present).
    apply_allowed = (
        apply_mode
        and getattr(args, "confirm_managed_trailing", False)
        and getattr(args, "confirm_local_operator", False)
    )

    try:
        for iteration in range(1, max_iterations + 1):
            monitor_iterations = iteration

            # Sprint 9.9.3.45.6: kill switch check (delegated gate can
            # toggle this via args.kill_switch).
            if getattr(args, "kill_switch", False):
                monitor_stop_reason = STOP_REASON_KILL_SWITCH_BLOCKED
                final_position_status = "UNKNOWN"
                final_position_source = "kill_switch_active"
                warnings.append("KILL_SWITCH_BLOCKED: kill switch active, monitor stopped")
                monitor_events.append({
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "event_type": "MONITOR_KILL_SWITCH",
                    "description": "Kill switch active - monitor stopped",
                    "sl_action": "HOLD",
                    "new_sl": 0.0,
                    "current_sl": sl,
                    "favorable": False,
                    "modify_attempted": False,
                    "modify_retcode": 0,
                    "modify_success": False,
                    "modify_reason": "KILL_SWITCH_BLOCKED",
                })
                break

            # Poll positions_get
            try:
                positions = mt5.positions_get(symbol="XAUUSD") or []
            except Exception as e:
                monitor_stop_reason = STOP_REASON_ERROR
                final_position_status = "UNKNOWN"
                final_position_source = f"positions_get_error: {e}"
                warnings.append(f"ERROR: positions_get raised {e}")
                monitor_events.append({
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "event_type": "MONITOR_ERROR",
                    "description": f"positions_get error: {e}",
                    "sl_action": "HOLD",
                    "new_sl": 0.0,
                    "current_sl": sl,
                    "favorable": False,
                    "modify_attempted": False,
                    "modify_retcode": 0,
                    "modify_success": False,
                    "modify_reason": "POSITIONS_GET_ERROR",
                })
                break

            titan_positions = [p for p in positions if getattr(p, "magic", 0) == TITAN_MAGIC]
            final_positions_get_count = len(titan_positions)

            current_position = None
            for p in titan_positions:
                if getattr(p, "ticket", 0) == position_ticket:
                    current_position = p
                    break

            if current_position is None:
                # Position disappeared - check history
                try:
                    from_dt = datetime.now(timezone.utc) - timedelta(minutes=30)
                    deals = mt5.history_deals_get(from_dt, datetime.now(timezone.utc)) or []
                except Exception:
                    deals = []
                matching_deals = [d for d in deals
                                  if getattr(d, "position_id", 0) == position_ticket
                                  or getattr(d, "order", 0) == position_ticket]
                if matching_deals:
                    final_history_match_found = True
                    final_position_status = "CLOSED"
                    final_position_source = "history_deals_get"
                    close_deal = matching_deals[-1]
                    close_deal_ticket = getattr(close_deal, "ticket", 0) or None
                    close_comment = getattr(close_deal, "comment", "") or ""
                    realized_pl = float(sum(getattr(d, "profit", 0) or 0 for d in matching_deals))
                    monitor_stop_reason = STOP_REASON_POSITION_CLOSED
                    monitor_events.append({
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "event_type": "MONITOR_POSITION_CLOSED",
                        "description": f"Position {position_ticket} closed. Close deal={close_deal_ticket}, profit={realized_pl}",
                        "sl_action": "HOLD",
                        "new_sl": 0.0,
                        "current_sl": sl,
                        "favorable": realized_pl >= 0,
                        "modify_attempted": False,
                        "modify_retcode": 0,
                        "modify_success": False,
                        "modify_reason": "POSITION_CLOSED",
                    })
                else:
                    # Position disappeared without history - unsafe state
                    final_position_status = "UNKNOWN"
                    final_position_source = "positions_get_empty_history_empty"
                    monitor_stop_reason = "POSITION_DISAPPEARED_WITHOUT_HISTORY"
                    warnings.append(
                        f"POSITION_DISAPPEARED_WITHOUT_HISTORY: position {position_ticket} "
                        "no longer in positions_get and not found in history_deals_get"
                    )
                    monitor_events.append({
                        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                        "event_type": "MONITOR_POSITION_DISAPPEARED",
                        "description": f"Position {position_ticket} disappeared without history",
                        "sl_action": "HOLD",
                        "new_sl": 0.0,
                        "current_sl": sl,
                        "favorable": False,
                        "modify_attempted": False,
                        "modify_retcode": 0,
                        "modify_success": False,
                        "modify_reason": "POSITION_DISAPPEARED_WITHOUT_HISTORY",
                    })
                break

            # Position still open - evaluate
            current_price = float(getattr(current_position, "price_current", 0) or 0)
            current_sl = float(getattr(current_position, "sl", 0) or sl)
            current_tp = float(getattr(current_position, "tp", 0) or tp)

            # Sprint 9.9.3.45.6: build orchestrator with optional applier
            # Sprint 9.9.3.45.8.1: wire adaptive trailing policy when
            # --use-adaptive-trailing flag is set. Legacy default
            # preserved when flag absent.
            # Sprint 9.9.3.45.8.2: pass actual monitor_iterations and
            # hold_seconds to orchestrator.monitor_position() so the
            # adaptive policy receives the correct iteration count
            # (fixes stale monitor_iterations=1 bug).
            use_adaptive = bool(getattr(args, "use_adaptive_trailing", False))
            orch_kwargs = dict(
                duration_minutes=duration_minutes,
                interval_seconds=interval_seconds,
                apply_modifications=apply_allowed,
                modify_applier=modify_applier if apply_allowed else None,
            )
            if use_adaptive:
                orch_kwargs["use_adaptive_policy"] = True
                orch_kwargs["adaptive_policy_kwargs"] = _build_adaptive_policy_kwargs(args)
            orch = ManagedTradeOrchestrator(**orch_kwargs)
            # Sprint 9.9.3.45.8.2: compute actual hold_seconds for this
            # iteration = monitor_iterations * interval_seconds
            actual_hold_seconds = monitor_iterations * interval_seconds
            actual_seconds_since_last_modify = 999  # TODO: track last modify time
            rec_result = orch.monitor_position(
                position_ticket=position_ticket,
                direction=direction,
                entry_price=entry_price,
                current_sl=current_sl,
                current_tp=current_tp,
                current_price=current_price,
                is_open=True,
                monitor_iterations=monitor_iterations,
                hold_seconds=actual_hold_seconds,
                seconds_since_last_modify=actual_seconds_since_last_modify,
            )
            if rec_result.monitor_events:
                monitor_events.extend(rec_result.monitor_events)
            if rec_result.sl_modify_previews:
                sl_modify_previews.extend(rec_result.sl_modify_previews)
            if rec_result.sl_modify_attempts:
                sl_modify_attempts.extend(rec_result.sl_modify_attempts)
            if rec_result.breakeven_triggered:
                breakeven_triggered = True
            if rec_result.trailing_triggered:
                trailing_triggered = True
            if rec_result.profit_lock_triggered:
                profit_lock_triggered = True

            # Sprint 9.9.3.45.6: journal decision events
            # The orchestrator already appended MONITOR_EVALUATION; we
            # additionally journal the decision type for clarity.
            last_event = rec_result.monitor_events[-1] if rec_result.monitor_events else None
            if last_event:
                sl_action = last_event.get("sl_action", "HOLD")
                if sl_action == "HOLD":
                    journal_type = "HOLD"
                elif sl_action == "MOVE_TO_BREAKEVEN":
                    journal_type = "BREAKEVEN_MODIFY"
                elif sl_action == "TRAIL":
                    journal_type = "TRAILING_MODIFY"
                elif sl_action == "PROFIT_LOCK":
                    journal_type = "PROFIT_LOCK_MODIFY"
                elif sl_action == "BLOCKED":
                    journal_type = "MODIFY_BLOCKED"
                else:
                    journal_type = sl_action
                # Append MODIFY_SUCCESS / MODIFY_FAILED if apply was attempted
                if last_event.get("modify_attempted"):
                    if last_event.get("modify_success"):
                        journal_type = "MODIFY_SUCCESS"
                    else:
                        journal_type = "MODIFY_FAILED"

            # Sleep until next iteration (skip on last)
            if iteration < max_iterations:
                _time.sleep(max(0, interval_seconds))
        else:
            # Loop completed without break - timeout reached.
            # Verify with one final positions_get that position is still open.
            try:
                final_positions = mt5.positions_get(symbol="XAUUSD") or []
            except Exception:
                final_positions = []
            final_titan = [p for p in final_positions if getattr(p, "magic", 0) == TITAN_MAGIC]
            final_positions_get_count = len(final_titan)
            still_open = any(getattr(p, "ticket", 0) == position_ticket for p in final_titan)
            if still_open:
                final_position_status = "OPEN"
                final_position_source = "positions_get"
                monitor_stop_reason = STOP_REASON_TIMEOUT
            else:
                # Position disappeared at the very end without history
                try:
                    from_dt = datetime.now(timezone.utc) - timedelta(minutes=30)
                    deals = mt5.history_deals_get(from_dt, datetime.now(timezone.utc)) or []
                except Exception:
                    deals = []
                matching_deals = [d for d in deals
                                  if getattr(d, "position_id", 0) == position_ticket]
                if matching_deals:
                    final_history_match_found = True
                    final_position_status = "CLOSED"
                    final_position_source = "history_deals_get"
                    close_deal = matching_deals[-1]
                    close_deal_ticket = getattr(close_deal, "ticket", 0) or None
                    close_comment = getattr(close_deal, "comment", "") or ""
                    realized_pl = float(sum(getattr(d, "profit", 0) or 0 for d in matching_deals))
                    monitor_stop_reason = STOP_REASON_POSITION_CLOSED
                else:
                    final_position_status = "UNKNOWN"
                    final_position_source = "positions_get_empty_history_empty"
                    monitor_stop_reason = "POSITION_DISAPPEARED_WITHOUT_HISTORY"
                    warnings.append(
                        f"POSITION_DISAPPEARED_WITHOUT_HISTORY: position {position_ticket} "
                        "disappeared at timeout without history"
                    )
    except Exception as e:
        # Unrecoverable error
        monitor_stop_reason = STOP_REASON_ERROR
        final_position_status = "UNKNOWN"
        final_position_source = f"unrecoverable_error: {e}"
        warnings.append(f"ERROR: monitor loop unrecoverable: {e}")
        monitor_events.append({
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event_type": "MONITOR_ERROR",
            "description": f"Unrecoverable error: {e}",
            "sl_action": "HOLD",
            "new_sl": 0.0,
            "current_sl": sl,
            "favorable": False,
            "modify_attempted": False,
            "modify_retcode": 0,
            "modify_success": False,
            "modify_reason": "UNRECOVERABLE_ERROR",
        })

    monitor_duration_seconds = round(_time.time() - monitor_start, 2)

    # Determine verdict based on final position status
    if final_position_status == "OPEN":
        verdict = "MANAGED_DEMO_MICRO_STARTED"
    elif final_position_status == "CLOSED":
        verdict = "MANAGED_DEMO_MICRO_COMPLETED"
    else:  # UNKNOWN
        verdict = "MANAGED_DEMO_MICRO_COMPLETED_WITH_WARNINGS"

    return {
        "verdict": verdict,
        "monitor_iterations": monitor_iterations,
        "monitor_duration_seconds": monitor_duration_seconds,
        "monitor_stop_reason": monitor_stop_reason,
        "final_position_status": final_position_status,
        "final_position_source": final_position_source,
        "final_positions_get_count": final_positions_get_count,
        "final_history_match_found": final_history_match_found,
        "close_deal_ticket": close_deal_ticket,
        "close_comment": close_comment,
        "realized_pl": realized_pl,
        "monitor_events": monitor_events,
        "sl_modify_previews": sl_modify_previews,
        "sl_modify_attempts": sl_modify_attempts,
        "breakeven_triggered": breakeven_triggered,
        "trailing_triggered": trailing_triggered,
        "profit_lock_triggered": profit_lock_triggered,
        "apply_mode": apply_mode,
        "apply_allowed": apply_allowed,
        "warnings": warnings,
    }


def run_execute_and_monitor(args) -> dict:
    """Execute and monitor. Z AI must NOT run this.

    Sprint 9.9.3.45.3: Replaced hard-coded non-local refusal with real
    environment gate. Execution is allowed only when ALL evidence-based
    checks pass. Z AI/non-Windows is blocked by environment drift gate,
    not by a hard-coded string.

    Sprint 9.9.3.45.5: Receipt truth + MT5 result mapping + monitor
    lifecycle. See module docstring.
    """
    import platform as _platform
    import sys as _sys

    ts = datetime.now(timezone.utc).isoformat()
    blockers = []
    ok_checks = []
    env_info = {}

    # 1. Check all confirmation flags
    required_flags = {
        "i_understand_demo_risk": getattr(args, "i_understand_demo_risk", False),
        "confirm_symbol": getattr(args, "confirm_symbol", ""),
        "confirm_lot": getattr(args, "confirm_lot", 0.0),
        "confirm_broker": getattr(args, "confirm_broker", ""),
        "confirm_one_order_only": getattr(args, "confirm_one_order_only", False),
        "confirm_not_live": getattr(args, "confirm_not_live", False),
        "confirm_environment_locked": getattr(args, "confirm_environment_locked", False),
        "confirm_model_parity_pass": getattr(args, "confirm_model_parity_pass", False),
        "confirm_local_operator": getattr(args, "confirm_local_operator", False),
        "confirm_managed_trailing": getattr(args, "confirm_managed_trailing", False),
    }
    missing_flags = [k for k, v in required_flags.items() if not v]
    if missing_flags:
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"CONFIRMATION_MISSING: {', '.join(missing_flags)}"],
            "important_note": "No order was sent. No mt5.order_send was called.",
            "timestamp_utc": ts,
        }
    ok_checks.append("All confirmation flags present")

    # 2. Local operator token check
    from scripts.operator.create_local_operator_execution_token import load_and_validate_token, consume_token
    token_result = load_and_validate_token()
    if not token_result["valid"]:
        reason = token_result["reason"]
        if "expired" in reason.lower():
            blocker = "LOCAL_TOKEN_EXPIRED"
        elif "not found" in reason.lower():
            blocker = "LOCAL_TOKEN_MISSING"
        elif "consumed" in reason.lower():
            blocker = "LOCAL_TOKEN_MISSING"
        else:
            blocker = f"LOCAL_TOKEN_INVALID: {reason}"
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [blocker],
            "important_note": "No order was sent. No mt5.order_send was called.",
            "timestamp_utc": ts,
        }
    token = token_result["token"]
    ok_checks.append(f"Local operator token valid (expires: {token.get('expires_utc', 'N/A')})")

    # 3. Environment drift gate
    from titan.production.environment_drift_gate import EnvironmentDriftGate, DriftVerdict
    env_gate = EnvironmentDriftGate()
    drift_result = env_gate.evaluate()
    env_info["current_platform"] = _platform.platform()
    env_info["current_python"] = f"{_sys.version_info.major}.{_sys.version_info.minor}.{_sys.version_info.micro}"
    env_info["frozen_platform"] = ""
    env_info["frozen_python"] = ""
    env_info["environment_drift_verdict"] = drift_result.verdict.value

    import json as _json
    sig_path = REPO_ROOT / "config" / "environment" / "environment_signature.json"
    if sig_path.exists():
        try:
            with open(sig_path, "r", encoding="utf-8") as f:
                sig = _json.load(f)
            env_info["frozen_platform"] = sig.get("platform", "")
            env_info["frozen_python"] = sig.get("python_version", "")
        except Exception:
            pass

    if drift_result.verdict == DriftVerdict.ENVIRONMENT_LOCK_BLOCKED:
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"ENVIRONMENT_DRIFT_BLOCKED: {drift_result.blockers}"],
            "important_note": "No order was sent. No mt5.order_send was called.",
            "timestamp_utc": ts,
            "env_info": env_info,
        }
    ok_checks.append(f"Environment drift: {drift_result.verdict.value}")

    # 4. Token git commit check
    import subprocess as _sp
    try:
        head_r = _sp.run(["git", "rev-parse", "--short", "HEAD"],
                         cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10)
        current_head = head_r.stdout.strip() if head_r.returncode == 0 else "unknown"
    except Exception:
        current_head = "unknown"
    token_git = token.get("git_commit", "")
    if token_git and token_git != current_head and token_git != "unknown":
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"LOCAL_TOKEN_GIT_MISMATCH: token={token_git} current={current_head}"],
            "important_note": "No order was sent. Recreate token after pulling new commit.",
            "timestamp_utc": ts,
            "env_info": env_info,
        }
    ok_checks.append(f"Git commit: {current_head}")

    # 5. Gate check
    gate_result = run_check_only(args)
    if "BLOCKED" in gate_result.get("gate_verdict", ""):
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": gate_result.get("gate_blockers", []),
            "important_note": "No order was sent.",
            "timestamp_utc": ts,
            "env_info": env_info,
        }
    ok_checks.append("Demo micro gate passed")

    # 6. Build executable SL/TP request
    from titan.production.demo_micro_order_builder import DemoMicroOrderBuilder
    builder = DemoMicroOrderBuilder()
    build_result = builder.build_preview(
        direction=getattr(args, "direction", "BUY"),
        entry_price=getattr(args, "entry_price", 2000.0),
        sl=getattr(args, "sl", 0.0),
        tp=getattr(args, "tp", 0.0),
        safe_fallback=False,
    )
    executable_status = build_result.get("executable_status", "PREVIEW_ONLY_NOT_EXECUTABLE")
    env_info["sltp_executable_status"] = executable_status
    if executable_status != "EXECUTABLE_WITH_PROTECTIVE_SL_TP":
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"MANAGED_SLTP_NOT_EXECUTABLE: {executable_status}"],
            "important_note": "No order was sent. SL/TP not executable.",
            "timestamp_utc": ts,
            "env_info": env_info,
        }
    ok_checks.append("SL/TP executable with protective values")

    # 7. Force-close readiness
    from scripts.operator.check_demo_micro_force_close_readiness import run_check as fc_check
    fc_result = fc_check()
    env_info["force_close_verdict"] = fc_result.get("verdict", "UNKNOWN")
    if "READY" not in fc_result.get("verdict", ""):
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"FORCE_CLOSE_NOT_READY: {fc_result.get('verdict', 'UNKNOWN')}"],
            "important_note": "No order was sent.",
            "timestamp_utc": ts,
            "env_info": env_info,
        }
    ok_checks.append("Force-close readiness: READY")

    # 8. Consume token (regardless of MT5 outcome)
    consume_token()

    # 9. Attempt gated execution via MT5
    try:
        import MetaTrader5 as mt5
    except ImportError:
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": ["MT5_NOT_AVAILABLE: MetaTrader5 not installed"],
            "important_note": "No order was sent.",
            "timestamp_utc": ts,
            "env_info": env_info,
            "ok_checks": ok_checks,
            "execution_attempted": False,
            "order_send_called": False,
            "receipt_written": False,
        }

    try:
        if not mt5.initialize():
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
                "blockers": ["MT5_NOT_AVAILABLE: initialize failed"],
                "important_note": "No order was sent.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
                "execution_attempted": False,
                "order_send_called": False,
                "receipt_written": False,
            }

        # Verify account DEMO
        acc = mt5.account_info()
        if acc is not None:
            env_info["account_server"] = getattr(acc, "server", "unknown")
            env_info["account_trade_mode"] = getattr(acc, "trade_mode", -1)
            if getattr(acc, "trade_mode", -1) != 0:  # 0 = DEMO
                mt5.shutdown()
                return {
                    "mode": "execute_and_monitor",
                    "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
                    "blockers": ["ACCOUNT_NOT_DEMO: trade_mode is not DEMO"],
                    "important_note": "No order was sent.",
                    "timestamp_utc": ts,
                    "env_info": env_info,
                    "ok_checks": ok_checks,
                    "execution_attempted": False,
                    "order_send_called": False,
                    "receipt_written": False,
                }
            if "MetaQuotes-Demo" not in getattr(acc, "server", ""):
                mt5.shutdown()
                return {
                    "mode": "execute_and_monitor",
                    "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
                    "blockers": ["BROKER_NOT_METAQUOTES_DEMO"],
                    "important_note": "No order was sent.",
                    "timestamp_utc": ts,
                    "env_info": env_info,
                    "ok_checks": ok_checks,
                    "execution_attempted": False,
                    "order_send_called": False,
                    "receipt_written": False,
                }
        ok_checks.append(f"Account: {env_info.get('account_server', 'unknown')} DEMO mode")

        # Verify open positions = 0
        positions = mt5.positions_get(symbol="XAUUSD")
        if positions is not None and len(positions) > 0:
            mt5.shutdown()
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
                "blockers": [f"OPEN_POSITIONS_NOT_ZERO: {len(positions)} positions found"],
                "important_note": "No order was sent.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
                "execution_attempted": False,
                "order_send_called": False,
                "receipt_written": False,
            }
        ok_checks.append("Open positions: 0")

        # Sprint 9.9.3.45.8.14: RR Geometry enforcement before order_send
        # If prop_funded_profile is selected, enforce minimum_RR >= 2.0
        # and recompute TP from initial_tp_R if needed.
        prop_funded_profile = getattr(args, "prop_funded_profile", "") if args else ""
        initial_tp_r = getattr(args, "initial_tp_r", 3.0) if args else 3.0

        # Build and send order (exactly once, no retry)
        preview = build_result["preview"]
        direction = preview["order_type"]
        volume = preview["volume"]
        sl = float(preview["sl"])
        tp = float(preview["tp"])

        # Sprint 9.9.3.45.8.14: If prop_funded_profile is set, enforce TP = entry + initial_tp_R * risk
        if prop_funded_profile and initial_tp_r > 0 and sl > 0:
            tick_for_geom = mt5.symbol_info_tick("XAUUSD")
            entry_for_geom = tick_for_geom.ask if direction == "BUY" else tick_for_geom.bid
            risk_distance = abs(entry_for_geom - sl)
            if risk_distance > 0:
                if direction == "BUY":
                    tp = entry_for_geom + (initial_tp_r * risk_distance)
                else:
                    tp = entry_for_geom - (initial_tp_r * risk_distance)
                ok_checks.append(
                    f"RR geometry: prop_funded_profile={prop_funded_profile}, "
                    f"initial_tp_R={initial_tp_r}, risk={risk_distance:.4f}, "
                    f"tp_distance={initial_tp_r * risk_distance:.4f}, TP={tp:.4f}"
                )

        # Sprint 9.9.3.45.8.14: RR Geometry gate - block if RR < minimum_RR
        tick_for_rr = mt5.symbol_info_tick("XAUUSD")
        entry_for_rr = tick_for_rr.ask if direction == "BUY" else tick_for_rr.bid
        if direction == "BUY":
            risk_distance = entry_for_rr - sl
            reward_distance = tp - entry_for_rr
        else:
            risk_distance = sl - entry_for_rr
            reward_distance = entry_for_rr - tp

        actual_rr = reward_distance / risk_distance if risk_distance > 0 else 0.0
        minimum_rr = 2.0  # Hard minimum for all execution
        if prop_funded_profile:
            minimum_rr = 2.0  # prop_funded_safe requires minimum_RR >= 2.0

        if actual_rr < minimum_rr:
            mt5.shutdown()
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
                "blockers": [
                    f"EXECUTION_GEOMETRY_RR_BELOW_MINIMUM: actual_RR={actual_rr:.4f} < minimum_RR={minimum_rr} "
                    f"(entry={entry_for_rr}, SL={sl}, TP={tp}, risk={risk_distance}, reward={reward_distance})"
                ],
                "important_note": "No order was sent. RR geometry below minimum. "
                                  "TP must be at least initial_tp_R * risk_distance from entry.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
                "execution_attempted": False,
                "order_send_called": False,
                "receipt_written": False,
                "execution_geometry": {
                    "side": direction,
                    "entry": entry_for_rr,
                    "sl": sl,
                    "tp": tp,
                    "risk_distance": risk_distance,
                    "reward_distance": reward_distance,
                    "actual_rr": actual_rr,
                    "minimum_rr": minimum_rr,
                    "initial_tp_r": initial_tp_r,
                    "geometry_verdict": "EXECUTION_GEOMETRY_RR_BELOW_MINIMUM",
                },
            }
        ok_checks.append(
            f"RR geometry PASS: actual_RR={actual_rr:.4f} >= minimum_RR={minimum_rr}"
        )

        tick = mt5.symbol_info_tick("XAUUSD")
        price = tick.ask if direction == "BUY" else tick.bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": "XAUUSD",
            "volume": float(volume),
            "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "magic": TITAN_MAGIC,
            "comment": TITAN_COMMENT,
            "deviation": 20,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Sprint 9.9.3.45.5: Capture full safe order_send result fields
        order_result = mt5.order_send(request)
        raw_result = _capture_order_send_result_safe(order_result)
        order_send_retcode = raw_result["retcode"]
        execution_success = order_send_retcode == 10009

        # Build receipt with correct field names
        receipt = _build_receipt(
            ts=ts, current_head=current_head, env_info=env_info, acc=acc,
            volume=volume, direction=direction, sl=sl, tp=tp,
            raw_result=raw_result, execution_success=execution_success,
        )

        # Persist receipt IMMEDIATELY (mandatory before any STARTED claim)
        receipt_written = _write_receipt(receipt)
        if not receipt_written:
            try:
                mt5.shutdown()
            except Exception:
                pass
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_FAILED",
                "blockers": ["RECEIPT_WRITE_FAILED: receipt could not be persisted"],
                "order_send_called": True,
                "order_send_retcode": order_send_retcode,
                "order_send_comment": raw_result["comment"],
                "receipt_written": False,
                "important_note": "order_send was called but receipt could not be written. Verdict FAILED.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
                "execution_attempted": True,
            }
        ok_checks.append("Execution receipt written (truthful field mapping)")

        # If order_send failed, return FAILED
        if order_result is None or not execution_success:
            try:
                mt5.shutdown()
            except Exception:
                pass
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_FAILED",
                "blockers": [f"ORDER_SEND_FAILED: retcode={order_send_retcode}"],
                "order_send_called": True,
                "order_send_retcode": order_send_retcode,
                "order_send_comment": raw_result["comment"],
                "receipt_written": receipt_written,
                "receipt_path": str(RECEIPT_PATH),
                "important_note": "order_send was called once and failed. No retry. Receipt written.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
                "execution_attempted": True,
                "position_detected": False,
                "monitor_started": False,
            }

        ok_checks.append(f"order_send succeeded: retcode={order_send_retcode}")

        # Sprint 9.9.3.45.5: Position detection via positions_get + history
        detection = _detect_position_via_positions_and_history(
            mt5=mt5, execution_ts=ts,
            expected_order=raw_result["order"],
            expected_deal=raw_result["deal"],
            detection_timeout=10, detection_interval=1,
        )
        receipt = _update_receipt_with_detection(receipt, detection)
        # Re-write receipt with detection results
        _write_receipt(receipt)

        # If neither positions_get nor history can verify the trade, FAILED
        if not detection["position_open_verified"] and not detection["history_verified"]:
            try:
                mt5.shutdown()
            except Exception:
                pass
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_FAILED",
                "blockers": ["POSITION_NOT_VERIFIED_AFTER_EXECUTION: order_send retcode=10009 but no open position and no history match"],
                "order_send_called": True,
                "order_send_retcode": order_send_retcode,
                "order_send_comment": raw_result["comment"],
                "receipt_written": receipt_written,
                "receipt_path": str(RECEIPT_PATH),
                "position_detected": False,
                "position_detection_method": "",
                "position_open_verified": False,
                "history_verified": False,
                "pending_history": False,
                "monitor_started": False,
                "important_note": "order_send retcode=10009 but trade not found in positions_get or history. Verdict FAILED, not STARTED.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
                "execution_attempted": True,
                "warnings": receipt.get("warnings", []),
            }

        ok_checks.append(
            f"Position verified: open={detection['position_open_verified']} "
            f"history={detection['history_verified']} pending={detection['pending_history']}"
        )

        # If only history verified (quick close), COMPLETED_WITH_WARNINGS
        if not detection["position_open_verified"] and detection["history_verified"]:
            try:
                mt5.shutdown()
            except Exception:
                pass
            return {
                "mode": "execute_and_monitor",
                "verdict": "MANAGED_DEMO_MICRO_COMPLETED_WITH_WARNINGS",
                "blockers": [],
                "warnings": ["POSITION_CLOSED_BEFORE_MONITOR: position opened and closed within detection window"],
                "order_send_called": True,
                "order_send_retcode": order_send_retcode,
                "order_send_comment": raw_result["comment"],
                "receipt_written": receipt_written,
                "receipt_path": str(RECEIPT_PATH),
                "position_detected": True,
                "position_detection_method": "history_verified",
                "detected_position_ticket": detection["detected_position_ticket"],
                "detected_position_identifier": detection["detected_position_identifier"],
                "resolved_history_position_id": detection["resolved_history_position_id"],
                "position_open_verified": False,
                "history_verified": True,
                "pending_history": False,
                "monitor_started": False,
                "important_note": "Position opened and closed quickly. Monitor not started. No false STARTED.",
                "timestamp_utc": ts,
                "env_info": env_info,
                "ok_checks": ok_checks,
                "execution_attempted": True,
                "final_position_status": "CLOSED",
                "final_position_source": "history_verified",
                "monitor_iterations": 0,
                "monitor_duration_seconds": 0,
                "monitor_stop_reason": "POSITION_CLOSED_BEFORE_MONITOR",
                "final_positions_get_count": 0,
                "final_history_match_found": True,
                "close_deal_ticket": detection["history_deal_ticket"],
                "close_comment": "",
                "realized_pl": 0.0,
            }

        # Position is open - start managed monitor lifecycle loop
        # Sprint 9.9.3.45.6: build modify applier when local operator
        # has confirmed managed trailing. Applier is None in Z AI / dry
        # run / preview-only mode.
        modify_applier = _build_modify_applier(
            mt5=mt5, args=args, ok_checks=ok_checks,
        )
        monitor_result = _run_monitor_loop(
            mt5=mt5, detected_position=detection, args=args, ok_checks=ok_checks,
            modify_applier=modify_applier,
        )
        try:
            mt5.shutdown()
        except Exception:
            pass

        # Update receipt with final state
        receipt["position_detected"] = True
        receipt["detected_position_ticket"] = detection["detected_position_ticket"]
        receipt["detected_position_identifier"] = detection["detected_position_identifier"]
        receipt["resolved_history_position_id"] = monitor_result.get("resolved_history_position_id") or detection["resolved_history_position_id"]
        _write_receipt(receipt)

        return {
            "mode": "execute_and_monitor",
            "verdict": monitor_result["verdict"],
            "order_send_called": True,
            "order_send_retcode": order_send_retcode,
            "order_send_comment": raw_result["comment"],
            "receipt_written": receipt_written,
            "receipt_path": str(RECEIPT_PATH),
            "position_detected": True,
            "position_detection_method": detection["detection_method"],
            "detected_position_ticket": detection["detected_position_ticket"],
            "detected_position_identifier": detection["detected_position_identifier"],
            "resolved_history_position_id": detection["resolved_history_position_id"],
            "position_open_verified": detection["position_open_verified"],
            "history_verified": detection["history_verified"],
            "pending_history": detection["pending_history"],
            "position_id": detection["detected_position_ticket"],
            "entry_price": detection["detected_position_entry_price"],
            "sl": detection["detected_position_sl"],
            "tp": detection["detected_position_tp"],
            "monitor_started": True,
            "monitor_result": monitor_result,
            "monitor_iterations": monitor_result["monitor_iterations"],
            "monitor_duration_seconds": monitor_result["monitor_duration_seconds"],
            "monitor_stop_reason": monitor_result["monitor_stop_reason"],
            "final_position_status": monitor_result["final_position_status"],
            "final_position_source": monitor_result["final_position_source"],
            "final_positions_get_count": monitor_result["final_positions_get_count"],
            "final_history_match_found": monitor_result["final_history_match_found"],
            "close_deal_ticket": monitor_result["close_deal_ticket"],
            "close_comment": monitor_result["close_comment"],
            "realized_pl": monitor_result["realized_pl"],
            "monitor_events": monitor_result["monitor_events"],
            "breakeven_triggered": monitor_result["breakeven_triggered"],
            "trailing_triggered": monitor_result["trailing_triggered"],
            "profit_lock_triggered": monitor_result["profit_lock_triggered"],
            # Sprint 9.9.3.45.8.1: adaptive trailing config in report
            "adaptive_trailing_config": _build_adaptive_config(args),
            "important_note": "Order sent once and succeeded. Position verified. Monitor lifecycle complete.",
            "timestamp_utc": ts,
            "env_info": env_info,
            "ok_checks": ok_checks,
            "execution_attempted": True,
            "warnings": monitor_result.get("warnings", []),
            "next_action": (
                "Position closed. Forensics available." if monitor_result["final_position_status"] == "CLOSED"
                else "Monitor reached timeout with position still open." if monitor_result["final_position_status"] == "OPEN"
                else "Position disappeared without history. Investigate receipt vs MT5 state."
            ),
        }

    except Exception as e:
        try:
            mt5.shutdown()
        except Exception:
            pass
        return {
            "mode": "execute_and_monitor",
            "verdict": "MANAGED_DEMO_MICRO_BLOCKED",
            "blockers": [f"EXECUTION_ERROR: {e}"],
            "important_note": "No order was sent. Error before order_send.",
            "timestamp_utc": ts,
            "env_info": env_info,
            "ok_checks": ok_checks,
        }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "managed_trade_report.json"
    md_path = OUTPUT_DIR / "managed_trade_report.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Managed Demo Micro Trade Report\n\n")
        f.write(f"**Mode:** {result.get('mode', 'unknown')}\n\n")
        f.write(f"**Verdict:** **{result.get('verdict', 'UNKNOWN')}**\n\n")
        f.write(f"**Timestamp:** {result.get('timestamp_utc', '')}\n\n")
        env_info = result.get("env_info", {})
        if env_info:
            f.write("## Environment Info\n\n")
            f.write("| Field | Value |\n|---|---|\n")
            for k, v in env_info.items():
                f.write(f"| {k} | {v} |\n")
        # Sprint 9.9.3.45.8.1: adaptive trailing config section
        adaptive_cfg = result.get("adaptive_trailing_config")
        if adaptive_cfg:
            f.write("\n## Adaptive Trailing Config\n\n")
            f.write("| Field | Value |\n|---|---|\n")
            f.write(f"| adaptive_trailing_enabled | {adaptive_cfg.get('adaptive_trailing_enabled', False)} |\n")
            f.write(f"| dynamic_tp_enabled | {adaptive_cfg.get('dynamic_tp_enabled', False)} |\n")
            f.write(f"| profit_corridor_enabled | {adaptive_cfg.get('profit_corridor_enabled', False)} |\n")
            f.write(f"| adaptive_policy_mode | {adaptive_cfg.get('adaptive_policy_mode', 'N/A')} |\n")
            f.write(f"| breakeven_trigger_R | {adaptive_cfg.get('breakeven_trigger_R', 'N/A')} |\n")
            f.write(f"| trailing_trigger_R | {adaptive_cfg.get('trailing_trigger_R', 'N/A')} |\n")
            f.write(f"| profit_lock_trigger_R | {adaptive_cfg.get('profit_lock_trigger_R', 'N/A')} |\n")
            f.write(f"| min_hold_seconds | {adaptive_cfg.get('min_hold_seconds', 'N/A')} |\n")
            f.write(f"| min_monitor_iterations | {adaptive_cfg.get('min_monitor_iterations', 'N/A')} |\n")
            f.write(f"| cooldown_seconds | {adaptive_cfg.get('cooldown_seconds', 'N/A')} |\n")
            # Sprint 9.9.3.45.8.2: dynamic TP extension config
            f.write(f"| tp_extension_trigger_R | {adaptive_cfg.get('tp_extension_trigger_R', 'N/A')} |\n")
            f.write(f"| tp_extension_R | {adaptive_cfg.get('tp_extension_R', 'N/A')} |\n")
            f.write(f"| tp_extension_atr_mult | {adaptive_cfg.get('tp_extension_atr_mult', 'N/A')} |\n")
            f.write(f"| tp_extension_cooldown_seconds | {adaptive_cfg.get('tp_extension_cooldown_seconds', 'N/A')} |\n")
            f.write(f"| min_profit_lock_after_tp_extension_R | {adaptive_cfg.get('min_profit_lock_after_tp_extension_R', 'N/A')} |\n")
            f.write(f"| max_profit_giveback_r_trend | {adaptive_cfg.get('max_profit_giveback_r_trend', 'N/A')} |\n")
            f.write(f"| max_profit_giveback_r_range | {adaptive_cfg.get('max_profit_giveback_r_range', 'N/A')} |\n")
        # Execution truthfulness fields (Sprint 9.9.3.45.5)
        truth_fields = [
            ("order_send_called", "Order send called"),
            ("order_send_retcode", "Order send retcode"),
            ("order_send_comment", "Order send comment"),
            ("receipt_written", "Receipt written"),
            ("receipt_path", "Receipt path"),
            ("position_detected", "Position detected"),
            ("position_detection_method", "Position detection method"),
            ("detected_position_ticket", "Detected position ticket"),
            ("detected_position_identifier", "Detected position identifier"),
            ("resolved_history_position_id", "Resolved history position id"),
            ("position_open_verified", "Position open verified"),
            ("history_verified", "History verified"),
            ("pending_history", "Pending history"),
            ("monitor_started", "Monitor started"),
            ("monitor_iterations", "Monitor iterations"),
            ("monitor_duration_seconds", "Monitor duration seconds"),
            ("monitor_stop_reason", "Monitor stop reason"),
            ("final_position_status", "Final position status"),
            ("final_position_source", "Final position source"),
            ("final_positions_get_count", "Final positions get count"),
            ("final_history_match_found", "Final history match found"),
            ("close_deal_ticket", "Close deal ticket"),
            ("close_comment", "Close comment"),
            ("realized_pl", "Realized PL"),
        ]
        f.write("\n## Execution Truthfulness\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, label in truth_fields:
            if k in result:
                f.write(f"| {label} | {result[k]} |\n")
        if result.get("ok_checks"):
            f.write("\n## OK Checks\n\n")
            for c in result["ok_checks"]:
                f.write(f"- {c}\n")
        if result.get("blockers"):
            f.write("\n## Blockers\n\n")
            for b in result["blockers"]:
                f.write(f"- **{b}**\n")
        if result.get("warnings"):
            f.write("\n## Warnings\n\n")
            for w in result["warnings"]:
                f.write(f"- {w}\n")
        if result.get("next_action"):
            f.write(f"\n## Next Action\n\n{result['next_action']}\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Managed demo micro trade operator")
    parser.add_argument("--check-only", action="store_true", default=True)
    parser.add_argument("--dry-arm", action="store_true", default=False)
    parser.add_argument("--build-request", action="store_true", default=False)
    parser.add_argument("--execute-and-monitor", action="store_true", default=False)
    parser.add_argument("--direction", default="BUY")
    parser.add_argument("--entry-price", type=float, default=2000.0)
    parser.add_argument("--sl", type=float, default=0.0)
    parser.add_argument("--tp", type=float, default=0.0)
    parser.add_argument("--i-understand-demo-risk", action="store_true", default=False)
    parser.add_argument("--confirm-symbol", default="")
    parser.add_argument("--confirm-lot", type=float, default=0.0)
    parser.add_argument("--confirm-broker", default="")
    parser.add_argument("--confirm-one-order-only", action="store_true", default=False)
    parser.add_argument("--confirm-not-live", action="store_true", default=False)
    parser.add_argument("--confirm-environment-locked", action="store_true", default=False)
    parser.add_argument("--confirm-model-parity-pass", action="store_true", default=False)
    parser.add_argument("--confirm-local-operator", action="store_true", default=False)
    parser.add_argument("--confirm-managed-trailing", action="store_true", default=False)
    parser.add_argument("--duration-minutes", type=int, default=30)
    parser.add_argument("--interval-seconds", type=int, default=5)
    # Sprint 9.9.3.45.6: explicit monitor duration/interval CLI overrides
    parser.add_argument("--monitor-duration-minutes", type=int, default=30,
                        help="Monitor loop duration in minutes (default 30)")
    parser.add_argument("--monitor-interval-seconds", type=int, default=5,
                        help="Monitor loop interval in seconds (default 5)")
    # Sprint 9.9.3.45.8.1: adaptive trailing opt-in CLI flags
    parser.add_argument("--use-adaptive-trailing", action="store_true", default=False,
                        help="Enable adaptive anti-whipsaw trailing policy (default: legacy mode)")
    parser.add_argument("--adaptive-policy-mode", default="balanced_conservative",
                        choices=["conservative", "balanced", "aggressive", "balanced_conservative"],
                        help="Adaptive policy mode (default: balanced_conservative)")
    parser.add_argument("--breakeven-trigger-r", type=float, default=1.0,
                        help="Breakeven trigger in R-multiple (default: 1.0)")
    parser.add_argument("--trailing-trigger-r", type=float, default=1.75,
                        help="Trailing trigger in R-multiple (default: 1.75)")
    parser.add_argument("--profit-lock-trigger-r", type=float, default=3.0,
                        help="Profit lock trigger in R-multiple (default: 3.0)")
    parser.add_argument("--min-hold-seconds", type=int, default=60,
                        help="Minimum hold seconds before any SL move (default: 60)")
    parser.add_argument("--min-monitor-iterations", type=int, default=3,
                        help="Minimum monitor iterations before any SL move (default: 3)")
    parser.add_argument("--sl-update-cooldown-seconds", type=int, default=60,
                        help="SL update cooldown in seconds (default: 60)")
    # Sprint 9.9.3.45.8.2: dynamic TP extension opt-in CLI flags
    parser.add_argument("--use-dynamic-tp-extension", action="store_true", default=False,
                        help="Enable dynamic TP extension (profit corridor). Default: OFF. Requires --use-adaptive-trailing.")
    parser.add_argument("--tp-extension-trigger-r", type=float, default=2.0,
                        help="TP extension trigger in R-multiple (default: 2.0)")
    parser.add_argument("--tp-extension-r", type=float, default=1.0,
                        help="TP extension distance in R-multiple (default: 1.0)")
    parser.add_argument("--tp-extension-atr-mult", type=float, default=2.0,
                        help="TP extension ATR multiplier (default: 2.0)")
    parser.add_argument("--tp-extension-cooldown-seconds", type=int, default=120,
                        help="TP extension cooldown in seconds (default: 120)")
    parser.add_argument("--min-profit-lock-after-tp-extension-r", type=float, default=1.0,
                        help="Minimum profit lock R after TP extension (default: 1.0)")
    parser.add_argument("--max-profit-giveback-r-trend", type=float, default=1.0,
                        help="Max profit giveback R in trend regime (default: 1.0)")
    parser.add_argument("--max-profit-giveback-r-range", type=float, default=0.5,
                        help="Max profit giveback R in range regime (default: 0.5)")
    # Sprint 9.9.3.45.8.3: production closure profile-driven geometry
    parser.add_argument("--account-profile", default="retail_demo_micro",
                        help="Account profile name (default: retail_demo_micro)")
    parser.add_argument("--initial-tp-r", type=float, default=3.0,
                        help="Initial TP in R-multiple (default: 3.0)")
    # Sprint 9.9.3.45.8.6: risk mode selection
    parser.add_argument("--risk-mode", default="conservative",
                        help="Risk mode (default: conservative)")
    parser.add_argument("--broker-profile", default="metaquotes_demo",
                        help="Broker profile name (default: metaquotes_demo)")
    # Sprint 9.9.3.45.8.7: prop firm profile selection
    parser.add_argument("--prop-firm-profile", default="",
                        help="Prop firm profile name (default: none)")
    # Sprint 9.9.3.45.8.8: prop funded optimizer profile
    parser.add_argument("--prop-funded-profile", default="",
                        help="Prop funded optimizer profile (prop_funded_safe, prop_funded_growth, prop_funded_aggressive_20pct_simulation)")
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI - Managed Demo Micro Trade (Sprint 9.9.3.45.8.6)")
    print("=" * 70)
    if getattr(args, "use_adaptive_trailing", False):
        print(f"  Adaptive trailing: ENABLED (mode={args.adaptive_policy_mode})")
    else:
        print("  Adaptive trailing: disabled (legacy mode)")
    if getattr(args, "use_dynamic_tp_extension", False):
        if getattr(args, "use_adaptive_trailing", False):
            print(f"  Dynamic TP extension: ENABLED (profit corridor active, trigger_R={args.tp_extension_trigger_r})")
        else:
            print("  Dynamic TP extension: ENABLED but BLOCKED (requires --use-adaptive-trailing)")
    else:
        print("  Dynamic TP extension: disabled (TP preserved at original value)")

    if args.execute_and_monitor:
        result = run_execute_and_monitor(args)
    elif args.dry_arm:
        result = run_dry_arm(args)
    elif args.build_request:
        result = run_build_request(args.direction, args.entry_price, args.sl, args.tp, args)
    else:
        result = run_check_only(args)

    report = write_report(result)
    print(f"\n  Mode: {result.get('mode', 'check_only')}")
    print(f"  Verdict: {result.get('verdict', 'UNKNOWN')}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    # Sprint 9.9.3.45.8.1: print adaptive trailing config in console
    adaptive_cfg = result.get("adaptive_trailing_config")
    if adaptive_cfg:
        print(f"  Adaptive trailing enabled: {adaptive_cfg.get('adaptive_trailing_enabled', False)}")
        if adaptive_cfg.get("adaptive_trailing_enabled"):
            print(f"  Adaptive policy mode: {adaptive_cfg.get('adaptive_policy_mode')}")
        # Sprint 9.9.3.45.8.2: print dynamic TP extension status
        print(f"  Dynamic TP extension enabled: {adaptive_cfg.get('dynamic_tp_enabled', False)}")
        if adaptive_cfg.get('profit_corridor_enabled'):
            print(f"  Profit corridor active: True (adaptive + dynamic_tp)")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
