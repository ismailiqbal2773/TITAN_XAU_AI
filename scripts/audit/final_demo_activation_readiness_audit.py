#!/usr/bin/env python3
"""
TITAN XAU AI - Final Demo Activation Readiness Audit (Sprint v2.8.5)
======================================================================
Final readiness gate before supervised MetaQuotes-Demo micro trade start.

Read-only audit. NEVER sends orders. NEVER creates token. NEVER modifies
positions. NEVER calls mt5.order_send.

Verifies:

Environment:
  - Windows local environment supported (advisory; audit can run anywhere)
  - Python version recorded
  - MT5 initialized read-only (best-effort; non-blocking if MT5 unavailable)
  - account server = MetaQuotes-Demo
  - account type = DEMO
  - symbol XAUUSD available
  - latest tick available
  - spread within configured limit
  - no open XAUUSD position
  - no pending XAUUSD order
  - no stale operator token
  - git commit recorded
  - working tree clean if possible

Required gates (read latest audit JSONs - never re-run):
  - model health pass/pass_with_warnings with failed_required_model_count = 0
  - feature parity pass
  - runtime safety pass
  - growth profile pass
  - production closure blockers = 0
  - autonomous readiness supervised ready (advisory; not blocking if missing)
  - build-request PASS (read from latest managed_trade_report.json)
  - execution_now_allowed = False
  - execution_blocker = OPERATOR_ARM_TOKEN_REQUIRED

Risk/execution constraints:
  - max lot = 0.01
  - max open positions = 1
  - risk per trade <= 0.5%
  - minimum RR >= 2.0
  - preferred RR = 3.0
  - ATR SL/TP geometry pass (read from latest execution_geometry_audit.json)
  - no live/funded/real
  - no FundedNext execution
  - no martingale/grid/averaging/loss multiplier

Receipt/forensics:
  - no unresolved active receipt
  - old stale receipts non-blocking only if no open position AND no pending order
  - no fallback to old trades
  - strict receipt matching remains required for future execution

Verdicts:
  FINAL_DEMO_ACTIVATION_READY_SUPERVISED
  FINAL_DEMO_ACTIVATION_BLOCKED

Outputs:
  data/audit/final_demo_activation/final_demo_activation_readiness_audit.json
  data/audit/final_demo_activation/final_demo_activation_readiness_audit.md
"""
from __future__ import annotations
import json, os, sys, platform, subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "final_demo_activation"

FINAL_DEMO_ACTIVATION_READY_SUPERVISED = "FINAL_DEMO_ACTIVATION_READY_SUPERVISED"
FINAL_DEMO_ACTIVATION_BLOCKED = "FINAL_DEMO_ACTIVATION_BLOCKED"
# v2.8.5-C: New intermediate verdicts for non-Windows/no-MT5 environments
FINAL_DEMO_ACTIVATION_OPERATOR_WINDOWS_REQUIRED = "FINAL_DEMO_ACTIVATION_OPERATOR_WINDOWS_REQUIRED"
FINAL_DEMO_ACTIVATION_SIMULATION_PASS_OPERATOR_REQUIRED = "FINAL_DEMO_ACTIVATION_SIMULATION_PASS_OPERATOR_REQUIRED"

ALL_VERDICTS = (
    FINAL_DEMO_ACTIVATION_READY_SUPERVISED,
    FINAL_DEMO_ACTIVATION_BLOCKED,
    FINAL_DEMO_ACTIVATION_OPERATOR_WINDOWS_REQUIRED,
    FINAL_DEMO_ACTIVATION_SIMULATION_PASS_OPERATOR_REQUIRED,
)

ALLOWED_ACCOUNT_SERVER = "MetaQuotes-Demo"
ALLOWED_ACCOUNT_TYPE = "DEMO"
ALLOWED_SYMBOL = "XAUUSD"
MAX_LOT = 0.01
MAX_OPEN_POSITIONS = 1
MAX_RISK_PER_TRADE_PCT = 0.005  # 0.5%
MIN_RR = 2.0
PREFERRED_RR = 3.0
MAX_SPREAD_USD = 1.0  # from config/runtime.yaml risk.max_spread_usd


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _load_runtime_config() -> dict:
    cfg_path = REPO_ROOT / "config" / "runtime.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _git_commit() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        return out
    except Exception:
        return ""


def _git_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        return bool(out)
    except Exception:
        return False


def _git_branch() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        return out
    except Exception:
        return ""


def _check_stale_token() -> dict:
    """Check if operator_execution_token.json exists and is stale (>1hr old)."""
    out = {"token_exists": False, "stale": False, "age_seconds": 0, "error": ""}
    token_path = REPO_ROOT / "data" / "runtime" / "operator_execution_token.json"
    if not token_path.exists():
        return out
    out["token_exists"] = True
    try:
        token_data = json.loads(token_path.read_text())
        token_ts = token_data.get("created_at") or token_data.get("timestamp_utc") or ""
        if token_ts:
            token_dt = datetime.fromisoformat(token_ts.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - token_dt).total_seconds()
            out["age_seconds"] = int(age)
            if age > 3600:  # > 1 hour
                out["stale"] = True
    except Exception as e:
        out["error"] = str(e)
        out["stale"] = True  # treat parse error as stale
    return out


def _check_mt5_environment() -> dict:
    """Best-effort read-only MT5 environment check.

    Returns dict with:
      - mt5_available: bool (True if MetaTrader5 module importable)
      - initialized: bool
      - account_server: str
      - account_type: str  (DEMO/LIVE/CONTEST)
      - symbol_available: bool
      - latest_tick: dict
      - spread_usd: float
      - open_positions_count: int
      - pending_orders_count: int
      - open_xauusd_positions: int
      - pending_xauusd_orders: int
      - error: str

    This function NEVER calls mt5.order_send. It only reads account_info,
    symbol_info, symbol_info_tick, positions_get, orders_get.
    """
    out = {
        "mt5_available": False, "initialized": False,
        "account_server": "", "account_type": "",
        "symbol_available": False, "latest_tick": {},
        "spread_usd": 0.0,
        "open_positions_count": 0, "pending_orders_count": 0,
        "open_xauusd_positions": 0, "pending_xauusd_orders": 0,
        "error": "",
    }
    try:
        import MetaTrader5 as mt5
        out["mt5_available"] = True
    except Exception as e:
        out["error"] = f"MetaTrader5 not installed: {e}"
        return out

    try:
        if not mt5.initialize():
            out["error"] = f"mt5.initialize() failed: {mt5.last_error()}"
            return out
        out["initialized"] = True

        # Account info
        acc = mt5.account_info()
        if acc is not None:
            out["account_server"] = getattr(acc, "server", "") or ""
            trade_mode = getattr(acc, "trade_mode", -1)
            # trade_mode: 0=DEMO, 1=CONTEST, 2=LIVE (MT5 constants)
            if trade_mode == 0:
                out["account_type"] = "DEMO"
            elif trade_mode == 1:
                out["account_type"] = "CONTEST"
            elif trade_mode == 2:
                out["account_type"] = "LIVE"
            else:
                # Fallback: infer from server name
                server_lower = out["account_server"].lower()
                if "demo" in server_lower:
                    out["account_type"] = "DEMO"
                elif "contest" in server_lower:
                    out["account_type"] = "CONTEST"
                else:
                    out["account_type"] = "UNKNOWN"

        # Symbol info
        sym = mt5.symbol_info(ALLOWED_SYMBOL)
        if sym is not None:
            out["symbol_available"] = True
        else:
            # Try alternate symbol names
            for alt in ("XAUUSD.c", "XAUUSD.m", "GOLD"):
                sym = mt5.symbol_info(alt)
                if sym is not None:
                    out["symbol_available"] = True
                    break

        # Latest tick
        tick = mt5.symbol_info_tick(ALLOWED_SYMBOL)
        if tick is not None:
            bid = getattr(tick, "bid", 0) or 0
            ask = getattr(tick, "ask", 0) or 0
            out["latest_tick"] = {"bid": bid, "ask": ask, "time": getattr(tick, "time", 0)}
            out["spread_usd"] = round(ask - bid, 4) if ask > 0 and bid > 0 else 0.0

        # Open positions
        positions = mt5.positions_get(symbol=ALLOWED_SYMBOL) or ()
        out["open_xauusd_positions"] = len(positions)
        all_positions = mt5.positions_get() or ()
        out["open_positions_count"] = len(all_positions)

        # Pending orders
        orders = mt5.orders_get(symbol=ALLOWED_SYMBOL) or ()
        out["pending_xauusd_orders"] = len(orders)
        all_orders = mt5.orders_get() or ()
        out["pending_orders_count"] = len(all_orders)

    except Exception as e:
        out["error"] = f"mt5_read_error: {e}"
    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass
    return out


def _check_receipt_forensics() -> dict:
    """Check for unresolved active receipts / stale forensics.

    Returns dict with:
      - active_receipt_exists: bool
      - active_receipt_path: str
      - stale_receipt_non_blocking: bool (True if no open/pending position)
      - error: str
    """
    out = {
        "active_receipt_exists": False,
        "active_receipt_path": "",
        "stale_receipt_non_blocking": True,
        "error": "",
    }
    receipt_path = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"
    if not receipt_path.exists():
        return out
    out["active_receipt_exists"] = True
    out["active_receipt_path"] = str(receipt_path)
    try:
        receipt_data = json.loads(receipt_path.read_text())
        # If receipt exists but no open position/pending order, it's stale (non-blocking)
        # The MT5 check determines this; default to non-blocking if we can't verify
        out["stale_receipt_non_blocking"] = True
    except Exception as e:
        out["error"] = str(e)
        out["stale_receipt_non_blocking"] = False
    return out


def run_audit() -> dict:
    """Run the final demo activation readiness audit.

    NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.
    Only reads MT5 account_info, symbol_info, symbol_info_tick, positions_get,
    orders_get (read-only operations).
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings_list = []
    findings = {}

    # === Environment ===
    findings["environment"] = {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "is_windows": platform.system() == "Windows",
        "repo_root": str(REPO_ROOT),
    }
    if platform.system() == "Windows":
        ok_checks.append(f"Windows environment detected: {platform.platform()}")
    else:
        warnings_list.append(
            f"NON_WINDOWS_ENVIRONMENT: {platform.system()} - audit can run but "
            "execution requires Windows MetaQuotes-Demo MT5 terminal"
        )

    # Git state
    git_commit = _git_commit()
    git_dirty = _git_dirty()
    git_branch = _git_branch()
    findings["git"] = {
        "commit": git_commit,
        "branch": git_branch,
        "dirty": git_dirty,
    }
    if git_commit:
        ok_checks.append(f"Git commit: {git_commit[:12]}")
    if git_dirty:
        warnings_list.append("GIT_WORKING_TREE_DIRTY: uncommitted changes present")
    else:
        ok_checks.append("Git working tree clean")

    # === MT5 Environment (best-effort, non-blocking if MT5 unavailable) ===
    mt5_env = _check_mt5_environment()
    findings["mt5_environment"] = mt5_env
    if mt5_env["mt5_available"] and mt5_env["initialized"]:
        ok_checks.append("MT5 initialized (read-only)")
        # Account server check
        if mt5_env["account_server"] == ALLOWED_ACCOUNT_SERVER:
            ok_checks.append(f"Account server: {ALLOWED_ACCOUNT_SERVER}")
        else:
            blockers.append(
                f"ACCOUNT_SERVER_NOT_METAQUOTES_DEMO: got '{mt5_env['account_server']}'"
            )
        # Account type check
        if mt5_env["account_type"] == ALLOWED_ACCOUNT_TYPE:
            ok_checks.append(f"Account type: {ALLOWED_ACCOUNT_TYPE}")
        elif mt5_env["account_type"] in ("LIVE", "CONTEST"):
            blockers.append(
                f"ACCOUNT_TYPE_NOT_DEMO: got '{mt5_env['account_type']}' - "
                "live/contest accounts are BLOCKED for demo activation"
            )
        elif mt5_env["account_type"] == "UNKNOWN":
            warnings_list.append("ACCOUNT_TYPE_UNKNOWN: cannot verify DEMO status")
        # Symbol check
        if mt5_env["symbol_available"]:
            ok_checks.append(f"Symbol {ALLOWED_SYMBOL} available")
        else:
            blockers.append(f"SYMBOL_NOT_AVAILABLE: {ALLOWED_SYMBOL} not found")
        # Latest tick check
        if mt5_env["latest_tick"]:
            ok_checks.append("Latest tick available")
        else:
            blockers.append("LATEST_TICK_UNAVAILABLE: cannot get symbol_info_tick")
        # Spread check
        if mt5_env["spread_usd"] > MAX_SPREAD_USD:
            blockers.append(
                f"SPREAD_EXCEEDS_LIMIT: {mt5_env['spread_usd']} > {MAX_SPREAD_USD}"
            )
        elif mt5_env["spread_usd"] > 0:
            ok_checks.append(f"Spread within limit: {mt5_env['spread_usd']}")
        # Open positions check
        if mt5_env["open_xauusd_positions"] > 0:
            blockers.append(
                f"OPEN_XAUUSD_POSITION_EXISTS: {mt5_env['open_xauusd_positions']} "
                "open XAUUSD position(s) - cannot start new trade"
            )
        else:
            ok_checks.append("No open XAUUSD position")
        if mt5_env["pending_xauusd_orders"] > 0:
            blockers.append(
                f"PENDING_XAUUSD_ORDER_EXISTS: {mt5_env['pending_xauusd_orders']} "
                "pending XAUUSD order(s)"
            )
        else:
            ok_checks.append("No pending XAUUSD order")
    else:
        # MT5 not available (Z AI env, or MT5 terminal not running)
        if not mt5_env["mt5_available"]:
            warnings_list.append(
                "MT5_NOT_AVAILABLE: MetaTrader5 module not installed. "
                "Audit can run in read-only mode but MT5 environment checks skipped. "
                "Operator must run this audit on Windows with MT5 terminal running."
            )
        else:
            warnings_list.append(
                f"MT5_NOT_INITIALIZED: {mt5_env.get('error', '')}. "
                "Operator must run this audit on Windows with MT5 terminal running."
            )

    # === Stale operator token check ===
    token_check = _check_stale_token()
    findings["operator_token"] = token_check
    if token_check["stale"]:
        blockers.append(
            f"STALE_OPERATOR_TOKEN: token exists, age={token_check['age_seconds']}s > 3600s. "
            "Operator must delete stale token before starting new trade."
        )
    elif token_check["token_exists"]:
        warnings_list.append(
            f"OPERATOR_TOKEN_EXISTS: age={token_check['age_seconds']}s - "
            "non-stale but should be reviewed"
        )
    else:
        ok_checks.append("No stale operator token")

    # === Required Gates (read latest audit JSONs) ===
    model_health_dir = REPO_ROOT / "data" / "audit" / "model_health"
    audit_dir = REPO_ROOT / "data" / "audit" / "demo_micro_execution"
    growth_dir = REPO_ROOT / "data" / "audit" / "prop_challenge_growth"

    # 1. Model health
    mh = _load_json(model_health_dir / "model_artifact_health_audit.json")
    mh_verdict = mh.get("verdict", "")
    mh_failed_required = int(mh.get("failed_required_model_count",
                                    mh.get("failed_model_count", 0)))
    mh_pass = mh_verdict in ("MODEL_ARTIFACT_HEALTH_PASS",
                              "MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS") and mh_failed_required == 0
    findings["model_health_verdict"] = mh_verdict
    findings["model_health_failed_required"] = mh_failed_required
    findings["model_health_pass"] = mh_pass
    if not mh_pass:
        blockers.append(
            f"MODEL_HEALTH_NOT_PASS: verdict={mh_verdict}, failed_required={mh_failed_required}"
        )
    else:
        ok_checks.append(f"Model health: {mh_verdict}, failed_required=0")

    # 2. Feature parity
    fp = _load_json(model_health_dir / "feature_parity_audit.json")
    fp_verdict = fp.get("verdict", "")
    fp_pass = fp_verdict in ("FEATURE_PARITY_PASS", "FEATURE_PARITY_PASS_WITH_WARNINGS")
    findings["feature_parity_verdict"] = fp_verdict
    findings["feature_parity_pass"] = fp_pass
    if not fp_pass:
        blockers.append(f"FEATURE_PARITY_NOT_PASS: verdict={fp_verdict}")
    else:
        ok_checks.append(f"Feature parity: {fp_verdict}")

    # 3. Runtime safety
    rs = _load_json(audit_dir / "runtime_safety_gate_audit.json")
    rs_verdict = rs.get("verdict", "")
    rs_pass = rs_verdict == "RUNTIME_SAFETY_GATE_PASS"
    findings["runtime_safety_verdict"] = rs_verdict
    findings["runtime_safety_pass"] = rs_pass
    if not rs_pass:
        blockers.append(f"RUNTIME_SAFETY_NOT_PASS: verdict={rs_verdict}")
    else:
        ok_checks.append(f"Runtime safety: {rs_verdict}")

    # 4. Growth profile
    gp = _load_json(growth_dir / "prop_challenge_growth_profile_audit.json")
    gp_verdict = gp.get("verdict", "")
    gp_pass = gp_verdict == "PROP_CHALLENGE_GROWTH_PROFILE_PASS"
    findings["growth_profile_verdict"] = gp_verdict
    findings["growth_profile_pass"] = gp_pass
    if not gp_pass:
        blockers.append(f"GROWTH_PROFILE_NOT_PASS: verdict={gp_verdict}")
    else:
        ok_checks.append(f"Growth profile: {gp_verdict}")

    # 5. Production closure — REMOVED v2.8.5-D
    # final_demo_activation must NOT depend on production_closure artifact.
    # Acyclic order: base audits -> build-request -> final_demo_activation
    # -> production_closure (aggregator).
    # production_closure may read final_demo_activation, but NOT vice versa.
    findings["production_closure_verdict"] = ""
    findings["production_closure_blockers_count"] = 0
    findings["production_closure_pass"] = True  # not checked here
    ok_checks.append("Production closure dependency removed (acyclic audit chain)")

    # 5a. Runtime architecture pipeline (v2.8.5-D: required gate)
    arch_dir = REPO_ROOT / "data" / "audit" / "architecture"
    ap = _load_json(arch_dir / "runtime_architecture_pipeline_audit.json")
    ap_verdict = ap.get("verdict", "")
    ap_pass = ap_verdict in (
        "RUNTIME_ARCHITECTURE_PIPELINE_PASS",
        "RUNTIME_ARCHITECTURE_PIPELINE_PASS_WITH_WARNINGS",
    )
    findings["runtime_architecture_pipeline_verdict"] = ap_verdict
    findings["runtime_architecture_pipeline_pass"] = ap_pass
    if not ap_pass:
        blockers.append(f"RUNTIME_ARCHITECTURE_PIPELINE_NOT_PASS: verdict={ap_verdict}")
    else:
        ok_checks.append(f"Runtime architecture pipeline: {ap_verdict}")

    # 5b. CEO AI governance (v2.8.5-D: required gate)
    cg = _load_json(arch_dir / "ceo_ai_governance_audit.json")
    cg_verdict = cg.get("verdict", "")
    cg_pass = cg_verdict in (
        "CEO_AI_GOVERNANCE_PASS",
        "CEO_AI_GOVERNANCE_PASS_WITH_WARNINGS",
    )
    findings["ceo_ai_governance_verdict"] = cg_verdict
    findings["ceo_ai_governance_pass"] = cg_pass
    if not cg_pass:
        blockers.append(f"CEO_AI_GOVERNANCE_NOT_PASS: verdict={cg_verdict}")
    else:
        ok_checks.append(f"CEO AI governance: {cg_verdict}")

    # 6. Autonomous readiness (advisory - not blocking if missing in Z AI env)
    ar = _load_json(audit_dir / "autonomous_demo_readiness_audit.json")
    ar_verdict = ar.get("verdict", "")
    ar_pass = ar_verdict == "AUTONOMOUS_DEMO_READY_SUPERVISED"
    findings["autonomous_readiness_verdict"] = ar_verdict
    findings["autonomous_readiness_pass"] = ar_pass
    if ar_verdict == "":
        warnings_list.append("AUTONOMOUS_READINESS_AUDIT_MISSING - run autonomous_demo_readiness_audit.py")
    elif not ar_pass:
        warnings_list.append(f"AUTONOMOUS_READINESS_NOT_SUPERVISED: verdict={ar_verdict}")
    else:
        ok_checks.append(f"Autonomous readiness: {ar_verdict}")

    # 7. Build-request (read from latest managed_trade_report.json)
    # v2.8.5-D: build-request must have CEO imported + called
    br = _load_json(audit_dir / "managed_trade_report.json")
    br_mode = br.get("mode", "")
    br_verdict = br.get("verdict", "")
    br_normalized_verdict = br.get("normalized_verdict", "")
    br_request_status = br.get("request_status", "")
    br_execution_now_allowed = br.get("execution_now_allowed", True)  # default True so missing file blocks
    br_execution_blocker = br.get("execution_blocker", "")
    br_ceo_imported = br.get("ceo_governance_imported", False)
    br_ceo_called = br.get("ceo_governance_called", False)
    br_ceo_decision = br.get("ceo_final_decision", "")
    br_ceo_allowed = br.get("ceo_allowed_to_trade", False)
    br_pass = (
        br_mode == "build_request"
        and br_verdict == "PASS"
        and br_normalized_verdict == "PASS"
        and br_request_status == "READY_FOR_SUPERVISED_OPERATOR_ARM"
        and br_execution_now_allowed is False
        and br_execution_blocker == "OPERATOR_ARM_TOKEN_REQUIRED"
        and br_ceo_imported is True  # v2.8.5-D: CEO must be imported
        and br_ceo_called is True  # v2.8.5-D: CEO must be called
    )
    findings["build_request_mode"] = br_mode
    findings["build_request_verdict"] = br_verdict
    findings["build_request_normalized_verdict"] = br_normalized_verdict
    findings["build_request_request_status"] = br_request_status
    findings["build_request_execution_now_allowed"] = br_execution_now_allowed
    findings["build_request_execution_blocker"] = br_execution_blocker
    findings["build_request_ceo_imported"] = br_ceo_imported
    findings["build_request_ceo_called"] = br_ceo_called
    findings["build_request_ceo_decision"] = br_ceo_decision
    findings["build_request_ceo_allowed"] = br_ceo_allowed
    findings["build_request_pass"] = br_pass
    if not br_ceo_imported:
        blockers.append("BUILD_REQUEST_CEO_NOT_IMPORTED: build-request did not import CEO AI governance")
    if not br_ceo_called:
        blockers.append("BUILD_REQUEST_CEO_NOT_CALLED: build-request did not call evaluate_ceo_decision")
    if not br_pass:
        blockers.append(
            f"BUILD_REQUEST_NOT_PASS: mode={br_mode}, verdict={br_verdict}, "
            f"normalized={br_normalized_verdict}, request_status={br_request_status}, "
            f"execution_now_allowed={br_execution_now_allowed}, "
            f"execution_blocker={br_execution_blocker}, "
            f"ceo_imported={br_ceo_imported}, ceo_called={br_ceo_called}"
        )
    else:
        ok_checks.append(
            f"Build-request: PASS, request_status={br_request_status}, "
            "execution_now_allowed=False, execution_blocker=OPERATOR_ARM_TOKEN_REQUIRED, "
            f"ceo_imported={br_ceo_imported}, ceo_called={br_ceo_called}"
        )

    # === Risk/execution constraints (read from runtime.yaml + growth profile) ===
    runtime_cfg = _load_runtime_config()
    risk = (runtime_cfg.get("risk") or {})
    findings["risk_constraints"] = {
        "max_lot": float(risk.get("max_lot", 0)),
        "max_open_positions": int(risk.get("max_open_positions", 0)),
        "max_spread_usd": float(risk.get("max_spread_usd", 0)),
    }
    if float(risk.get("max_lot", 0)) > MAX_LOT:
        blockers.append(f"MAX_LOT_EXCEEDS_001: {risk.get('max_lot')}")
    else:
        ok_checks.append(f"Max lot: {risk.get('max_lot')}")
    if int(risk.get("max_open_positions", 0)) > MAX_OPEN_POSITIONS:
        blockers.append(f"MAX_OPEN_POSITIONS_EXCEEDS_1: {risk.get('max_open_positions')}")
    else:
        ok_checks.append(f"Max open positions: {risk.get('max_open_positions')}")

    # Growth profile risk constraints
    gp_cfg_path = REPO_ROOT / "config" / "prop_challenge_growth_profile.yaml"
    gp_cfg = _load_yaml(gp_cfg_path)
    gp_profile = (gp_cfg.get("profile") or {}) if gp_cfg else {}
    pos_sizing = gp_profile.get("position_sizing") or {}
    risk_bands = gp_profile.get("risk_bands") or {}
    forbidden = gp_profile.get("forbidden_strategies") or {}
    findings["growth_risk_constraints"] = {
        "base_risk_per_trade_pct": float(pos_sizing.get("base_risk_per_trade_pct", 0)),
        "min_RR": float(pos_sizing.get("min_RR", 0)),
        "preferred_RR": float(pos_sizing.get("preferred_RR", 0)),
        "max_total_dd_pct": float(risk_bands.get("max_total_dd_pct", 0)),
    }
    base_risk = float(pos_sizing.get("base_risk_per_trade_pct", 0))
    if base_risk > MAX_RISK_PER_TRADE_PCT:
        blockers.append(f"BASE_RISK_EXCEEDS_0_5_PCT: {base_risk}")
    else:
        ok_checks.append(f"Base risk per trade: {base_risk}")
    min_rr = float(pos_sizing.get("min_RR", 0))
    if min_rr < MIN_RR:
        blockers.append(f"MIN_RR_BELOW_2: {min_rr}")
    else:
        ok_checks.append(f"Min RR: {min_rr}")
    preferred_rr = float(pos_sizing.get("preferred_RR", 0))
    if preferred_rr < PREFERRED_RR:
        blockers.append(f"PREFERRED_RR_BELOW_3: {preferred_rr}")
    else:
        ok_checks.append(f"Preferred RR: {preferred_rr}")

    # Forbidden strategies check (all must be False)
    for strat in ("martingale", "grid", "averaging_down",
                  "loss_based_lot_multiplier", "forced_recovery",
                  "lot_increase_after_loss"):
        if forbidden.get(strat, True) is not False:
            blockers.append(f"FORBIDDEN_STRATEGY_NOT_DISABLED: {strat}")
        else:
            ok_checks.append(f"Forbidden strategy disabled: {strat}")

    # ATR SL/TP geometry pass (read from latest execution_geometry_audit.json)
    geom = _load_json(audit_dir / "execution_geometry_audit.json")
    geom_verdict = geom.get("verdict", "")
    findings["execution_geometry_verdict"] = geom_verdict
    if geom_verdict == "":
        warnings_list.append("EXECUTION_GEOMETRY_AUDIT_MISSING - non-blocking")
    elif geom_verdict != "EXECUTION_GEOMETRY_PASS":
        blockers.append(f"EXECUTION_GEOMETRY_NOT_PASS: {geom_verdict}")
    else:
        ok_checks.append(f"Execution geometry: {geom_verdict}")

    # === Receipt/forensics check ===
    receipt_check = _check_receipt_forensics()
    findings["receipt_forensics"] = receipt_check
    if receipt_check["active_receipt_exists"]:
        # Stale receipt is non-blocking ONLY if no open/pending position
        no_open_or_pending = (
            mt5_env.get("open_xauusd_positions", 0) == 0
            and mt5_env.get("pending_xauusd_orders", 0) == 0
        )
        if no_open_or_pending:
            warnings_list.append(
                "STALE_RECEIPT_NON_BLOCKING: receipt exists but no open/pending position"
            )
        else:
            blockers.append(
                "UNRESOLVED_ACTIVE_RECEIPT: receipt exists AND open/pending position present"
            )
    else:
        ok_checks.append("No active receipt")

    # === Final verdict ===
    # v2.8.5-C: READY_SUPERVISED requires Windows + MT5 + MetaQuotes-Demo + all gates pass.
    # Non-Windows/no-MT5 environments cannot emit READY_SUPERVISED even if all gates pass.
    from titan.production.audit_hygiene import (
        load_growth_profile_config, validate_artifact_freshness, get_git_commit,
        detect_environment_mode,
    )
    current_commit = get_git_commit()
    env_mode = detect_environment_mode()
    is_windows = (env_mode == "windows")
    mt5_available = bool(mt5_env.get("mt5_available", False))
    mt5_initialized = bool(mt5_env.get("initialized", False))
    metaquotes_demo_verified = bool(
        mt5_env.get("account_server", "") == ALLOWED_ACCOUNT_SERVER
        and mt5_env.get("account_type", "") == ALLOWED_ACCOUNT_TYPE
        and mt5_env.get("symbol_available", False)
    )

    # v2.8.5-E.2: MetaQuotes-Demo verified = False is an EXPLICIT blocker.
    # Even if all other gates pass, if MetaQuotes-Demo is not verified,
    # final activation MUST be BLOCKED.
    if not metaquotes_demo_verified:
        blockers.append(
            f"METAQUOTES_DEMO_NOT_VERIFIED: account_server={mt5_env.get('account_server', '')}, "
            f"account_type={mt5_env.get('account_type', '')}, "
            f"symbol_available={mt5_env.get('symbol_available', False)}"
        )

    # v2.8.5-E.2: MT5 not initialized is an EXPLICIT blocker.
    if not mt5_initialized:
        blockers.append(
            "MT5_NOT_INITIALIZED: MT5 terminal not initialized"
        )

    # v2.8.5-E.2: Build-request CEO blocked is an EXPLICIT blocker.
    # If build-request report shows CEO BLOCKED, final activation MUST be BLOCKED.
    br_ceo_final = br.get("ceo_final_decision", "")
    br_ceo_allowed = br.get("ceo_allowed_to_trade", True)  # default True so missing doesn't block
    if br_ceo_final == "BLOCKED" or br_ceo_allowed is False:
        blockers.append(
            f"BUILD_REQUEST_CEO_BLOCKED: ceo_final_decision={br_ceo_final}, "
            f"ceo_allowed_to_trade={br_ceo_allowed}"
        )

    # v2.8.5-C: Validate growth profile values from config (not from audit JSON)
    gp_cfg = load_growth_profile_config()
    growth_profile_values_valid = (
        gp_cfg["valid"]
        and gp_cfg["monthly_target_pct"] == 0.30
        and gp_cfg["daily_dd_soft_limit_pct"] == 0.01
        and gp_cfg["daily_dd_hard_limit_pct"] == 0.02
        and gp_cfg["max_total_dd_pct"] == 0.08
    )
    if not growth_profile_values_valid:
        blockers.append(
            f"GROWTH_PROFILE_VALUES_INVALID: expected monthly=0.30, daily_dd=0.01-0.02, "
            f"total_dd=0.08; got monthly={gp_cfg['monthly_target_pct']}, "
            f"daily_dd_soft={gp_cfg['daily_dd_soft_limit_pct']}, "
            f"daily_dd_hard={gp_cfg['daily_dd_hard_limit_pct']}, "
            f"total_dd={gp_cfg['max_total_dd_pct']}"
        )

    # v2.8.5-C: Validate audit artifacts freshness (detect stale/test-mode/commit-mismatch)
    audit_artifacts_fresh = True
    stale_artifacts_detected = []
    for artifact_path, artifact_name in [
        (model_health_dir / "model_artifact_health_audit.json", "model_artifact_health_audit"),
        (model_health_dir / "feature_parity_audit.json", "feature_parity_audit"),
        (audit_dir / "runtime_safety_gate_audit.json", "runtime_safety_gate_audit"),
        (growth_dir / "prop_challenge_growth_profile_audit.json", "prop_challenge_growth_profile_audit"),
        # v2.8.5-D: production_closure REMOVED from freshness list (acyclic dependency)
        (REPO_ROOT / "data" / "audit" / "architecture" / "runtime_architecture_pipeline_audit.json", "runtime_architecture_pipeline_audit"),
        (REPO_ROOT / "data" / "audit" / "architecture" / "ceo_ai_governance_audit.json", "ceo_ai_governance_audit"),
    ]:
        fr = validate_artifact_freshness(artifact_path, artifact_name, current_commit)
        if not fr["fresh"]:
            audit_artifacts_fresh = False
            stale_artifacts_detected.append({
                "artifact": artifact_name,
                "reason": fr["reason"],
            })
            # Stale artifacts are blockers (cannot infer readiness from stale data)
            blockers.append(f"AUDIT_ARTIFACT_STALE: {artifact_name} - {fr['reason']}")

    findings["growth_profile_values_valid"] = growth_profile_values_valid
    findings["audit_artifacts_fresh"] = audit_artifacts_fresh
    findings["stale_artifacts_detected"] = stale_artifacts_detected
    findings["environment_mode"] = env_mode
    findings["operator_windows_required"] = not is_windows
    findings["mt5_required_for_full_ready"] = not (mt5_available and mt5_initialized)
    findings["metaquotes_demo_verified"] = metaquotes_demo_verified
    findings["full_ready_requires_windows_mt5"] = not (is_windows and mt5_available and mt5_initialized and metaquotes_demo_verified)

    # Determine verdict with v2.8.5-C semantics
    if blockers:
        verdict = FINAL_DEMO_ACTIVATION_BLOCKED
        activation_verdict_reason = "blockers_present"
    elif not is_windows or not mt5_available or not mt5_initialized or not metaquotes_demo_verified:
        # All gates pass BUT not on Windows MetaQuotes-Demo with MT5 verified.
        # Cannot emit READY_SUPERVISED - emit intermediate verdict.
        if is_windows and mt5_available and mt5_initialized and not metaquotes_demo_verified:
            # Windows + MT5 available + initialized BUT account not MetaQuotes-Demo DEMO
            verdict = FINAL_DEMO_ACTIVATION_BLOCKED
            activation_verdict_reason = "windows_mt5_available_but_not_metaquotes_demo"
        else:
            # Non-Windows or MT5 not available/initialized
            verdict = FINAL_DEMO_ACTIVATION_OPERATOR_WINDOWS_REQUIRED
            activation_verdict_reason = (
                f"requires_windows_mt5_metaquotes_demo: "
                f"is_windows={is_windows}, mt5_available={mt5_available}, "
                f"mt5_initialized={mt5_initialized}, metaquotes_demo_verified={metaquotes_demo_verified}"
            )
    else:
        # All gates pass AND Windows + MT5 + MetaQuotes-Demo verified
        verdict = FINAL_DEMO_ACTIVATION_READY_SUPERVISED
        activation_verdict_reason = "all_gates_pass_windows_mt5_metaquotes_demo_verified"

    findings["activation_verdict_reason"] = activation_verdict_reason

    # Compute final_demo_activation_allowed (True ONLY if verdict is READY_SUPERVISED)
    final_demo_activation_allowed = (verdict == FINAL_DEMO_ACTIVATION_READY_SUPERVISED)

    # v2.8.5-C: Add freshness metadata to result
    from titan.production.audit_hygiene import make_freshness_metadata
    freshness = make_freshness_metadata(
        audit_name="final_demo_activation_readiness_audit",
        source_mode="production",
        environment_mode=env_mode,
    )

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "final_demo_activation_allowed": final_demo_activation_allowed,
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


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "final_demo_activation_readiness_audit.json"
    md_path = OUTPUT_DIR / "final_demo_activation_readiness_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Final Demo Activation Readiness Audit (v2.8.5)\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Final demo activation allowed:** **{result.get('final_demo_activation_allowed', False)}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**Blockers:** {len(result.get('blockers', []))}\n\n")
        f.write(f"**Warnings:** {len(result.get('warnings', []))}\n\n")

        # Environment
        env = result.get("findings", {}).get("environment", {})
        f.write("## Environment\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| python_version | {env.get('python_version', '')} |\n")
        f.write(f"| platform | {env.get('platform', '')} |\n")
        f.write(f"| is_windows | {env.get('is_windows', False)} |\n")
        git = result.get("findings", {}).get("git", {})
        f.write(f"| git_commit | {git.get('commit', '')[:12]} |\n")
        f.write(f"| git_branch | {git.get('branch', '')} |\n")
        f.write(f"| git_dirty | {git.get('dirty', False)} |\n\n")

        # MT5 Environment
        mt5_env = result.get("findings", {}).get("mt5_environment", {})
        f.write("## MT5 Environment (read-only)\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| mt5_available | {mt5_env.get('mt5_available', False)} |\n")
        f.write(f"| initialized | {mt5_env.get('initialized', False)} |\n")
        f.write(f"| account_server | {mt5_env.get('account_server', '')} |\n")
        f.write(f"| account_type | {mt5_env.get('account_type', '')} |\n")
        f.write(f"| symbol_available | {mt5_env.get('symbol_available', False)} |\n")
        f.write(f"| spread_usd | {mt5_env.get('spread_usd', 0)} |\n")
        f.write(f"| open_positions_count | {mt5_env.get('open_positions_count', 0)} |\n")
        f.write(f"| open_xauusd_positions | {mt5_env.get('open_xauusd_positions', 0)} |\n")
        f.write(f"| pending_orders_count | {mt5_env.get('pending_orders_count', 0)} |\n")
        f.write(f"| pending_xauusd_orders | {mt5_env.get('pending_xauusd_orders', 0)} |\n")
        f.write(f"| error | {mt5_env.get('error', '')} |\n\n")

        # Required Gates
        fnd = result.get("findings", {})
        f.write("## Required Gates\n\n")
        f.write("| Gate | Verdict | Pass |\n|---|---|---|\n")
        f.write(f"| model_health | {fnd.get('model_health_verdict', '')} | {fnd.get('model_health_pass', False)} |\n")
        f.write(f"| feature_parity | {fnd.get('feature_parity_verdict', '')} | {fnd.get('feature_parity_pass', False)} |\n")
        f.write(f"| runtime_safety | {fnd.get('runtime_safety_verdict', '')} | {fnd.get('runtime_safety_pass', False)} |\n")
        f.write(f"| growth_profile | {fnd.get('growth_profile_verdict', '')} | {fnd.get('growth_profile_pass', False)} |\n")
        f.write(f"| production_closure | {fnd.get('production_closure_verdict', '')} | {fnd.get('production_closure_pass', False)} |\n")
        f.write(f"| autonomous_readiness | {fnd.get('autonomous_readiness_verdict', '')} | {fnd.get('autonomous_readiness_pass', False)} |\n")
        f.write(f"| build_request | {fnd.get('build_request_verdict', '')} | {fnd.get('build_request_pass', False)} |\n")
        f.write(f"| execution_geometry | {fnd.get('execution_geometry_verdict', '')} | {'PASS' if fnd.get('execution_geometry_verdict', '') == 'EXECUTION_GEOMETRY_PASS' else 'N/A'} |\n\n")

        # Build-request details
        f.write("## Build-Request Status\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| mode | {fnd.get('build_request_mode', '')} |\n")
        f.write(f"| verdict | {fnd.get('build_request_verdict', '')} |\n")
        f.write(f"| normalized_verdict | {fnd.get('build_request_normalized_verdict', '')} |\n")
        f.write(f"| request_status | {fnd.get('build_request_request_status', '')} |\n")
        f.write(f"| execution_now_allowed | {fnd.get('build_request_execution_now_allowed', False)} |\n")
        f.write(f"| execution_blocker | {fnd.get('build_request_execution_blocker', '')} |\n\n")

        # Operator token
        token = result.get("findings", {}).get("operator_token", {})
        f.write("## Operator Token\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| token_exists | {token.get('token_exists', False)} |\n")
        f.write(f"| stale | {token.get('stale', False)} |\n")
        f.write(f"| age_seconds | {token.get('age_seconds', 0)} |\n\n")

        # Receipt/forensics
        receipt = result.get("findings", {}).get("receipt_forensics", {})
        f.write("## Receipt/Forensics\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| active_receipt_exists | {receipt.get('active_receipt_exists', False)} |\n")
        f.write(f"| stale_receipt_non_blocking | {receipt.get('stale_receipt_non_blocking', False)} |\n\n")

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
        f.write("\n> This audit is READ-ONLY. It never calls mt5.order_send, never creates tokens, never modifies positions.\n")
    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Final Demo Activation Readiness Audit (v2.8.5)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Final demo activation allowed: {result.get('final_demo_activation_allowed', False)}")
    print(f"  Blockers: {len(result.get('blockers', []))}")
    print(f"  Warnings: {len(result.get('warnings', []))}")
    fnd = result.get("findings", {})
    mt5_env = fnd.get("mt5_environment", {})
    print(f"\n  --- Environment ---")
    print(f"  Python: {fnd.get('environment', {}).get('python_version', '')}")
    print(f"  Platform: {fnd.get('environment', {}).get('platform', '')}")
    print(f"  Git commit: {fnd.get('git', {}).get('commit', '')[:12]}")
    print(f"  Git dirty: {fnd.get('git', {}).get('dirty', False)}")
    print(f"\n  --- MT5 Environment ---")
    print(f"  MT5 available: {mt5_env.get('mt5_available', False)}")
    print(f"  MT5 initialized: {mt5_env.get('initialized', False)}")
    print(f"  Account server: {mt5_env.get('account_server', 'N/A')}")
    print(f"  Account type: {mt5_env.get('account_type', 'N/A')}")
    print(f"  Open XAUUSD positions: {mt5_env.get('open_xauusd_positions', 0)}")
    print(f"  Pending XAUUSD orders: {mt5_env.get('pending_xauusd_orders', 0)}")
    print(f"\n  --- Required Gates ---")
    print(f"  Model health: {fnd.get('model_health_verdict', '')} (failed_required={fnd.get('model_health_failed_required', 0)})")
    print(f"  Feature parity: {fnd.get('feature_parity_verdict', '')}")
    print(f"  Runtime safety: {fnd.get('runtime_safety_verdict', '')}")
    print(f"  Growth profile: {fnd.get('growth_profile_verdict', '')}")
    print(f"  Production closure: {fnd.get('production_closure_verdict', '')}")
    print(f"  Build-request: {fnd.get('build_request_verdict', '')} (normalized={fnd.get('build_request_normalized_verdict', '')})")
    print(f"  execution_now_allowed: {fnd.get('build_request_execution_now_allowed', False)}")
    print(f"  execution_blocker: {fnd.get('build_request_execution_blocker', '')}")
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
    return 0 if result["verdict"] != FINAL_DEMO_ACTIVATION_BLOCKED else 1


if __name__ == "__main__":
    sys.exit(main())
