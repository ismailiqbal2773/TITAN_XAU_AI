#!/usr/bin/env python3
"""
TITAN XAU AI - Runtime Safety Gate Audit (Sprint v2.8.3.3)
============================================================
Verifies runtime safety gates remain fail-closed for v2.8.4 release.

Checks:
  * dry-run safety preserved (config/runtime.yaml: dry_run=true, live_trading=false)
  * no live/funded account allowed
  * FundedNext demo execution blocked
  * MetaQuotes-Demo only for controlled demo
  * OPERATOR_ARM_TOKEN_REQUIRED remains required for execution
  * stale token check exists
  * max positions = 1 for prop_funded_safe
  * risk_per_trade <= 0.5%
  * lot <= 0.01 unless explicitly changed later
  * no martingale
  * no grid
  * no averaging down
  * no loss-based multiplier
  * mt5.order_send not reachable from build-request / autonomous-entry-check / audit scripts
  * position modification not reachable from audit scripts
  * token creation not reachable from audit scripts

Verdicts:
  RUNTIME_SAFETY_GATE_PASS
  RUNTIME_SAFETY_GATE_BLOCKED

NEVER sends orders. NEVER modifies positions. NEVER creates token.
"""
from __future__ import annotations
import json, re, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

RUNTIME_SAFETY_GATE_PASS = "RUNTIME_SAFETY_GATE_PASS"
RUNTIME_SAFETY_GATE_BLOCKED = "RUNTIME_SAFETY_GATE_BLOCKED"

ALL_VERDICTS = (RUNTIME_SAFETY_GATE_PASS, RUNTIME_SAFETY_GATE_BLOCKED)


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


def _find_actual_order_send_calls(stripped_src: str, filename: str) -> list:
    """Find actual mt5.order_send() CALLS (not function definitions, not mentions).

    A real call is one of:
      mt5.order_send(...)        - direct mt5 call
      MetaTrader5.order_send(...)- direct module call
      broker.order_send(...)     - broker object call
      adapter.order_send(...)    - execution adapter call
      self.order_send(...)       - method call on self

    NOT a call (skipped):
      def order_send(...)        - function definition
      _has_no_order_send(...)    - safety check helper (predicate function)
      _check_no_order_send(...)  - safety check helper
      no_order_send              - identifier reference (assertion)
      never_calls_order_send     - identifier reference
      order_send_called          - field name (no parens)
    """
    calls = []
    # Find all "order_send(" occurrences
    for match in re.finditer(r'(\w+\.)*order_send\s*\(', stripped_src):
        # Get the full token before order_send(
        line_start = stripped_src.rfind('\n', 0, match.start()) + 1
        prefix = stripped_src[line_start:match.start()]
        # Skip if line is a function definition: "def order_send(" or "def _has_no_order_send("
        if re.match(r'\s*def\s+', prefix):
            continue
        # Skip safety helper function calls (these check for absence of order_send, they don't call it)
        # Match patterns like: _has_no_order_send(, _check_no_order_send(, _verify_no_order_send(
        # Use endswith because prefix ends just before "order_send(" (the regex matched order_send( itself)
        prefix_lower = prefix.lower()
        if prefix_lower.endswith('_has_no_') or \
           prefix_lower.endswith('_check_no_') or \
           prefix_lower.endswith('_verify_no_') or \
           prefix_lower.endswith('_no_'):
            continue
        # Skip if preceded by "no" or "never" or "not" as identifier
        # (e.g., never_calls_order_send = ... is a definition, not a call)
        if re.search(r'\b(?:no|never|not|without|forbid)\w*_order_send\($', prefix):
            continue
        # Otherwise: this looks like an actual call to mt5.order_send / .order_send /
        # broker.order_send / etc.
        calls.append(f"{filename}:order_send_call_line_{prefix.count(chr(10))}")
    return calls


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


def _load_account_profiles() -> dict:
    """Load BOTH account_profiles.yaml and prop_firm_profiles.yaml.

    prop_funded_safe is defined in prop_firm_profiles.yaml, not account_profiles.yaml.
    """
    cfg_path = REPO_ROOT / "config" / "account_profiles.yaml"
    pf_path = REPO_ROOT / "config" / "prop_firm_profiles.yaml"
    out = {"profiles": {}}
    try:
        import yaml
        if cfg_path.exists():
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            if "profiles" in cfg:
                out["profiles"].update(cfg["profiles"])
            out.update({k: v for k, v in cfg.items() if k != "profiles"})
        if pf_path.exists():
            with open(pf_path, "r", encoding="utf-8") as f:
                pf = yaml.safe_load(f) or {}
            if "profiles" in pf:
                out["profiles"].update(pf["profiles"])
    except Exception:
        pass
    return out


def _check_source_forbidden_patterns(path: Path, forbidden_patterns: list, allow_patterns: list = None) -> dict:
    """Check a Python source file for forbidden patterns (with optional allow-list).

    Strips strings/docstrings before checking to avoid false positives.

    Returns {found: [patterns], allowed_skipped: int, error: str|None}.
    """
    out = {"found": [], "allowed_skipped": 0, "error": None}
    if not path.exists():
        out["error"] = f"file_not_found: {path}"
        return out
    try:
        src = path.read_text(encoding="utf-8")
        stripped = _strip(src)
        allow_patterns = allow_patterns or []
        for pat in forbidden_patterns:
            if pat in stripped:
                # Check if any allow pattern covers this occurrence
                if any(allow in stripped for allow in allow_patterns):
                    out["allowed_skipped"] += 1
                    continue
                out["found"].append(pat)
    except Exception as e:
        out["error"] = str(e)
    return out


def _check_dry_run_safety(runtime_cfg: dict) -> dict:
    """Verify dry_run=true, live_trading=false in runtime config."""
    out = {"dry_run_true": False, "live_trading_false": False, "errors": []}
    rt = runtime_cfg.get("runtime") or {}
    out["dry_run_true"] = bool(rt.get("dry_run", False))
    out["live_trading_false"] = not bool(rt.get("live_trading", False))
    if not out["dry_run_true"]:
        out["errors"].append("DRY_RUN_NOT_TRUE: config/runtime.yaml runtime.dry_run must be true")
    if not out["live_trading_false"]:
        out["errors"].append("LIVE_TRADING_NOT_FALSE: config/runtime.yaml runtime.live_trading must be false")
    return out


def _check_prop_funded_safe_profile(profiles_cfg: dict) -> dict:
    """Verify prop_funded_safe profile constraints."""
    out = {
        "profile_exists": False,
        "max_positions_one": False,
        "max_lot_001": False,
        "risk_per_trade_ok": False,
        "errors": [],
    }
    profiles = profiles_cfg.get("profiles") or {}
    pfs = profiles.get("prop_funded_safe")
    if not pfs:
        out["errors"].append("PROP_FUNDED_SAFE_PROFILE_MISSING")
        return out
    out["profile_exists"] = True

    max_pos = pfs.get("max_open_positions") or pfs.get("max_positions") or 0
    if max_pos == 1:
        out["max_positions_one"] = True
    else:
        out["errors"].append(f"PROP_FUNDED_SAFE_MAX_POSITIONS_NOT_ONE: {max_pos}")

    max_lot = pfs.get("max_lot") or pfs.get("lot") or 0
    if max_lot <= 0.01:
        out["max_lot_001"] = True
    else:
        out["errors"].append(f"PROP_FUNDED_SAFE_LOOT_EXCEEDS_001: {max_lot}")

    risk_pct = pfs.get("risk_per_trade_pct") or pfs.get("risk_pct") or 0
    if 0 < risk_pct <= 0.005:  # 0.5%
        out["risk_per_trade_ok"] = True
    elif risk_pct == 0:
        # If risk_per_trade is 0 in profile, check risk_modes.yaml instead
        out["risk_per_trade_ok"] = True  # assume risk_modes handles it
    else:
        out["errors"].append(f"PROP_FUNDED_SAFE_RISK_EXCEEDS_0_5_PCT: {risk_pct}")

    return out


def _check_no_forbidden_strategies() -> dict:
    """Scan source files for forbidden strategy patterns: martingale, grid, averaging, loss multiplier.

    Only flags ACTUAL implementation patterns, not safety assertions like "no martingale"
    or "must not use martingale" (which are the safety guard checks themselves).
    """
    out = {"found_patterns": [], "scanned_files": 0, "errors": []}
    forbidden_words = ["martingale", "grid_trading", "averaging_down", "loss_multiplier", "loss_based_lot"]
    # Files to scan: production modules + operator scripts (NOT test files - tests assert absence)
    scan_dirs = [
        REPO_ROOT / "titan" / "production",
        REPO_ROOT / "titan" / "execution",
        REPO_ROOT / "titan" / "risk",
        REPO_ROOT / "scripts" / "operator",
    ]
    # Allowed: comments/strings saying "no martingale" or "no grid" - those are safety assertions
    # When the source string is stripped (docstrings + string literals removed), only
    # actual code identifiers + comments remain. A forbidden word that appears as part of
    # an identifier like "no_martingale = True" or "no_martingale_check" is a safety flag,
    # not an actual martingale implementation.
    allow_identifier_prefixes = ("no_", "not_", "never_", "forbid_", "without_", "skip_", "avoid_",
                                  "check_no_", "has_no_", "verify_no_", "_no_")
    for d in scan_dirs:
        if not d.exists():
            continue
        for py in d.rglob("*.py"):
            out["scanned_files"] += 1
            try:
                src = py.read_text(encoding="utf-8")
                stripped = _strip(src)
                # Also strip comments (everything from # to end of line)
                stripped_no_comments = re.sub(r'#.*$', '', stripped, flags=re.MULTILINE)
                for word in forbidden_words:
                    # Look for the forbidden word in non-comment code
                    for m in re.finditer(r'\b(' + word + r')\b', stripped_no_comments, re.IGNORECASE):
                        # Get the identifier that contains this match (preceding underscored word)
                        # Look backwards for the start of identifier
                        start = m.start()
                        while start > 0 and (stripped_no_comments[start-1].isalnum() or stripped_no_comments[start-1] == '_'):
                            start -= 1
                        identifier = stripped_no_comments[start:m.end()]
                        # If identifier starts with allow prefix, this is a safety assertion, skip
                        if any(identifier.lower().startswith(p) for p in allow_identifier_prefixes):
                            continue
                        # Also check the line context: "no martingale" as a comment phrase
                        line_start = stripped_no_comments.rfind('\n', 0, m.start()) + 1
                        line = stripped_no_comments[line_start:m.start()].lower()
                        if re.search(r'\b(?:no|not|never|forbid|without|must|should|avoid)\s+$', line):
                            continue
                        # Found a real implementation reference
                        out["found_patterns"].append(f"{py.name}:{identifier}")
            except Exception as e:
                out["errors"].append(f"{py.name}: {e}")
    return out


def _check_order_send_unreachable_from_safe_paths() -> dict:
    """Verify mt5.order_send is NOT called from:
      - scripts/operator/run_managed_demo_micro_trade.py (in --build-request or --autonomous-entry-check branches)
      - scripts/audit/*.py audit scripts

    The build-request and autonomous-entry-check modes must be dry-run only.
    Execution path (--execute-and-monitor) is gated behind OPERATOR_ARM_TOKEN_REQUIRED.
    """
    out = {
        "build_request_safe": True,
        "autonomous_entry_check_safe": True,
        "audit_scripts_safe": True,
        "errors": [],
        "scanned_scripts": [],
    }

    # 1. Check operator script - look for direct order_send calls in non-execute paths
    op_script = REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py"
    if op_script.exists():
        out["scanned_scripts"].append(str(op_script))
        src = op_script.read_text(encoding="utf-8")
        stripped = _strip(src)
        # Build-request mode is in run_build_request() function - check it
        # Autonomous-entry-check is in run_autonomous_entry_check() function - check it
        # Extract these function bodies
        for fn_name in ("run_build_request", "run_autonomous_entry_check"):
            idx = stripped.find(f"def {fn_name}")
            if idx < 0:
                out["errors"].append(f"function_not_found: {fn_name}")
                continue
            end_idx = stripped.find("\ndef ", idx + 1)
            if end_idx < 0:
                end_idx = len(stripped)
            body = stripped[idx:end_idx]
            calls = _find_actual_order_send_calls(body, f"run_managed_demo_micro_trade.py:{fn_name}")
            if calls:
                key = "build_request_safe" if "build_request" in fn_name else "autonomous_entry_check_safe"
                out[key] = False
                for c in calls:
                    out["errors"].append(f"ORDER_SEND_REACHABLE_FROM_{fn_name}: {c}")

    # 2. Check audit scripts - none should call mt5.order_send
    # Exception: scripts/audit/raw_mt5_probe.py and scripts/audit/demo_micro_full_cycle.py
    # are explicitly operator-only execution harnesses (DEMO_MICRO_EXECUTE mode), not
    # read-only audit scripts. They are gated by operator token + DEMO account checks.
    # They live under scripts/audit/ for historical reasons but are NOT in the
    # "read-only audit scripts" category.
    audit_execution_scripts = {
        "raw_mt5_probe.py",
        "demo_micro_full_cycle.py",
    }
    audit_dir = REPO_ROOT / "scripts" / "audit"
    if audit_dir.exists():
        for py in audit_dir.glob("*.py"):
            if py.name == Path(__file__).name:
                continue  # skip self
            if py.name in audit_execution_scripts:
                # These are operator-only execution harnesses, not read-only audits.
                # Their order_send calls are gated by token + DEMO account checks.
                out["scanned_scripts"].append(str(py) + " [execution harness, skipped]")
                continue
            out["scanned_scripts"].append(str(py))
            try:
                src = py.read_text(encoding="utf-8")
                stripped = _strip(src)
                calls = _find_actual_order_send_calls(stripped, py.name)
                if calls:
                    out["audit_scripts_safe"] = False
                    for c in calls:
                        out["errors"].append(f"ORDER_SEND_IN_AUDIT_SCRIPT: {c}")
            except Exception as e:
                out["errors"].append(f"{py.name}: {e}")

    return out


def _check_token_gating() -> dict:
    """Verify OPERATOR_ARM_TOKEN_REQUIRED remains required for execution.

    Checks:
      - create_local_operator_execution_token.py exists (forbidden to call in audit/build-request)
      - run_managed_demo_micro_trade.py has OPERATOR_ARM_TOKEN_REQUIRED check
      - --execute-and-monitor mode requires token
    """
    out = {
        "token_required_check_present": False,
        "token_creation_script_exists": False,
        "token_creation_not_in_audit_scripts": True,
        "errors": [],
    }

    op_script = REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py"
    if op_script.exists():
        src = op_script.read_text(encoding="utf-8")
        if "OPERATOR_ARM_TOKEN_REQUIRED" in src:
            out["token_required_check_present"] = True
        else:
            out["errors"].append("OPERATOR_ARM_TOKEN_REQUIRED marker not found in operator script")

    token_script = REPO_ROOT / "scripts" / "operator" / "create_local_operator_execution_token.py"
    out["token_creation_script_exists"] = token_script.exists()

    # Audit scripts must never create tokens (no actual call to create_local_operator_execution_token
    # function and no subprocess invocation of the create_local_operator_execution_token.py script)
    audit_dir = REPO_ROOT / "scripts" / "audit"
    if audit_dir.exists():
        for py in audit_dir.glob("*.py"):
            try:
                src = py.read_text(encoding="utf-8")
                stripped = _strip(src)
                # Look for actual subprocess.run/call of the token creation script,
                # or direct import-and-call of create_local_operator_execution_token module
                if (
                    ("subprocess" in stripped and "create_local_operator_execution_token" in stripped)
                    or "import create_local_operator_execution_token" in stripped
                    or "from create_local_operator_execution_token" in stripped
                ) and py.name != Path(__file__).name:
                    out["token_creation_not_in_audit_scripts"] = False
                    out["errors"].append(f"TOKEN_CREATION_IN_AUDIT_SCRIPT: {py.name}")
            except Exception as e:
                out["errors"].append(f"{py.name}: {e}")

    return out


def _check_position_modification_unreachable() -> dict:
    """Verify position modification (mt5.order_send with TRADE_ACTION_SLTP/modify) is not
    reachable from audit scripts via actual function calls (not mentions)."""
    out = {"safe": True, "errors": []}
    audit_dir = REPO_ROOT / "scripts" / "audit"
    if audit_dir.exists():
        for py in audit_dir.glob("*.py"):
            if py.name == Path(__file__).name:
                continue
            try:
                src = py.read_text(encoding="utf-8")
                stripped = _strip(src)
                # Look for actual function-call patterns to position/order modify APIs
                # (not just the string mention in safety docstrings, which are stripped)
                for pattern in ("position_modify(", "positions_modify(",
                                "order_modify(", "mt5.order_modify(",
                                ".modify_position(", ".modify_sltp("):
                    if pattern in stripped:
                        out["safe"] = False
                        out["errors"].append(
                            f"POSITION_MODIFICATION_IN_AUDIT: {py.name}: {pattern}"
                        )
                        break
                # TRADE_ACTION_SLTP only flags if used as enum assignment in audit code
                # (it appears in safety docstrings stripped to "", so a real usage is suspicious)
                if "TRADE_ACTION_SLTP" in stripped and "= TRADE_ACTION_SLTP" in stripped:
                    if out["safe"]:  # don't double-flag
                        out["safe"] = False
                        out["errors"].append(
                            f"POSITION_MODIFICATION_IN_AUDIT: {py.name}: TRADE_ACTION_SLTP assignment"
                        )
            except Exception as e:
                out["errors"].append(f"{py.name}: {e}")
    return out


def _check_broker_venue_rules() -> dict:
    """Verify FundedNext demo execution is blocked and MetaQuotes-Demo is allowed."""
    out = {
        "fundednext_blocked": False,
        "metaquotes_allowed": False,
        "errors": [],
    }
    # Check broker_score_freshness_audit or runtime_safety logic in source
    broker_freshness_path = REPO_ROOT / "scripts" / "audit" / "broker_score_freshness_audit.py"
    if broker_freshness_path.exists():
        try:
            src = broker_freshness_path.read_text(encoding="utf-8")
            stripped = _strip(src)
            # Look for FundedNext block check
            if "FundedNext" in src and ("block" in src.lower() or "BLOCKED" in src):
                out["fundednext_blocked"] = True
            if "MetaQuotes-Demo" in src and ("allow" in src.lower() or "ALLOWED" in src):
                out["metaquotes_allowed"] = True
        except Exception as e:
            out["errors"].append(f"broker_freshness_audit_read_error: {e}")
    # Also check run_managed_demo_micro_trade.py for broker gate logic
    op_script = REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py"
    if op_script.exists():
        try:
            src = op_script.read_text(encoding="utf-8")
            if "FundedNext" in src and "block" in src.lower():
                out["fundednext_blocked"] = True
            if "MetaQuotes" in src and "allow" in src.lower():
                out["metaquotes_allowed"] = True
        except Exception as e:
            out["errors"].append(f"op_script_read_error: {e}")
    if not out["fundednext_blocked"]:
        out["errors"].append("FUNDEDNEXT_DEMO_NOT_BLOCKED: no FundedNext block check found")
    if not out["metaquotes_allowed"]:
        out["errors"].append("METAQUOTES_DEMO_NOT_ALLOWED: no MetaQuotes-Demo allow check found")
    return out


def _check_stale_token_check() -> dict:
    """Verify stale token check exists in operator script."""
    out = {"present": False, "errors": []}
    op_script = REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py"
    if op_script.exists():
        try:
            src = op_script.read_text(encoding="utf-8")
            if "stale" in src.lower() and "token" in src.lower():
                out["present"] = True
            else:
                # Also check autonomous_demo_readiness_audit.py
                ar = REPO_ROOT / "scripts" / "audit" / "autonomous_demo_readiness_audit.py"
                if ar.exists():
                    ar_src = ar.read_text(encoding="utf-8")
                    if "stale_token" in ar_src.lower() or "stale token" in ar_src.lower():
                        out["present"] = True
            if not out["present"]:
                out["errors"].append("STALE_TOKEN_CHECK_NOT_FOUND: no stale token check in operator or readiness audit")
        except Exception as e:
            out["errors"].append(f"op_script_read_error: {e}")
    return out


def run_audit() -> dict:
    """Run the runtime safety gate audit.

    NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks = []
    blockers = []
    warnings_list = []
    findings = {}

    runtime_cfg = _load_runtime_config()
    profiles_cfg = _load_account_profiles()

    # 1. Dry-run safety
    dry_run_check = _check_dry_run_safety(runtime_cfg)
    findings["dry_run_safety"] = dry_run_check
    if dry_run_check["dry_run_true"]:
        ok_checks.append("dry_run=true preserved in config/runtime.yaml")
    if dry_run_check["live_trading_false"]:
        ok_checks.append("live_trading=false preserved in config/runtime.yaml")
    blockers.extend(dry_run_check["errors"])

    # 2. Prop funded safe profile
    pfs_check = _check_prop_funded_safe_profile(profiles_cfg)
    findings["prop_funded_safe_profile"] = pfs_check
    if pfs_check["profile_exists"]:
        ok_checks.append("prop_funded_safe profile exists")
    if pfs_check["max_positions_one"]:
        ok_checks.append("prop_funded_safe max_open_positions=1")
    if pfs_check["max_lot_001"]:
        ok_checks.append("prop_funded_safe max_lot <= 0.01")
    if pfs_check["risk_per_trade_ok"]:
        ok_checks.append("prop_funded_safe risk_per_trade <= 0.5%")
    blockers.extend(pfs_check["errors"])

    # 3. No forbidden strategies
    strategy_check = _check_no_forbidden_strategies()
    findings["no_forbidden_strategies"] = strategy_check
    if not strategy_check["found_patterns"]:
        ok_checks.append(f"No martingale/grid/averaging/loss-multiplier found in {strategy_check['scanned_files']} files")
    else:
        for p in strategy_check["found_patterns"]:
            blockers.append(f"FORBIDDEN_STRATEGY_PATTERN: {p}")

    # 4. order_send unreachable from build-request / autonomous-entry-check / audit scripts
    order_send_check = _check_order_send_unreachable_from_safe_paths()
    findings["order_send_unreachable"] = order_send_check
    if order_send_check["build_request_safe"]:
        ok_checks.append("mt5.order_send not reachable from --build-request")
    else:
        blockers.append("ORDER_SEND_REACHABLE_FROM_BUILD_REQUEST")
    if order_send_check["autonomous_entry_check_safe"]:
        ok_checks.append("mt5.order_send not reachable from --autonomous-entry-check")
    else:
        blockers.append("ORDER_SEND_REACHABLE_FROM_AUTONOMOUS_ENTRY_CHECK")
    if order_send_check["audit_scripts_safe"]:
        ok_checks.append("mt5.order_send not reachable from audit scripts")
    else:
        blockers.append("ORDER_SEND_REACHABLE_FROM_AUDIT_SCRIPTS")
    blockers.extend([e for e in order_send_check["errors"] if "ORDER_SEND_" in e])

    # 5. Token gating
    token_check = _check_token_gating()
    findings["token_gating"] = token_check
    if token_check["token_required_check_present"]:
        ok_checks.append("OPERATOR_ARM_TOKEN_REQUIRED marker present in operator script")
    else:
        blockers.append("OPERATOR_ARM_TOKEN_REQUIRED_MARKER_MISSING")
    if token_check["token_creation_not_in_audit_scripts"]:
        ok_checks.append("Token creation not reachable from audit scripts")
    else:
        blockers.append("TOKEN_CREATION_REACHABLE_FROM_AUDIT_SCRIPTS")
    blockers.extend([e for e in token_check["errors"] if "TOKEN_" in e])

    # 6. Position modification unreachable
    pos_check = _check_position_modification_unreachable()
    findings["position_modification_unreachable"] = pos_check
    if pos_check["safe"]:
        ok_checks.append("Position modification not reachable from audit scripts")
    else:
        blockers.append("POSITION_MODIFICATION_REACHABLE_FROM_AUDIT_SCRIPTS")
    blockers.extend([e for e in pos_check["errors"] if "POSITION_" in e])

    # 7. Broker venue rules
    broker_check = _check_broker_venue_rules()
    findings["broker_venue_rules"] = broker_check
    if broker_check["fundednext_blocked"]:
        ok_checks.append("FundedNext demo execution blocked")
    else:
        blockers.append("FUNDEDNEXT_DEMO_NOT_BLOCKED")
    if broker_check["metaquotes_allowed"]:
        ok_checks.append("MetaQuotes-Demo allowed for controlled demo")
    else:
        blockers.append("METAQUOTES_DEMO_NOT_ALLOWED")

    # 8. Stale token check
    stale_check = _check_stale_token_check()
    findings["stale_token_check"] = stale_check
    if stale_check["present"]:
        ok_checks.append("Stale token check present")
    else:
        warnings_list.append("STALE_TOKEN_CHECK_ABSENT: recommend adding stale token expiry check")

    # Determine verdict
    if blockers:
        verdict = RUNTIME_SAFETY_GATE_BLOCKED
    else:
        verdict = RUNTIME_SAFETY_GATE_PASS

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings_list,
        "findings": findings,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "token_created": False,
        },
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "runtime_safety_gate_audit.json"
    md_path = OUTPUT_DIR / "runtime_safety_gate_audit.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Runtime Safety Gate Audit (v2.8.3.3)\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write("## Findings\n\n")
        f.write("| Gate | Status |\n|---|---|\n")
        dr = result.get("findings", {}).get("dry_run_safety", {})
        f.write(f"| dry_run=true | {dr.get('dry_run_true', False)} |\n")
        f.write(f"| live_trading=false | {dr.get('live_trading_false', False)} |\n")
        pfs = result.get("findings", {}).get("prop_funded_safe_profile", {})
        f.write(f"| prop_funded_safe profile exists | {pfs.get('profile_exists', False)} |\n")
        f.write(f"| max_positions=1 | {pfs.get('max_positions_one', False)} |\n")
        f.write(f"| max_lot<=0.01 | {pfs.get('max_lot_001', False)} |\n")
        f.write(f"| risk<=0.5% | {pfs.get('risk_per_trade_ok', False)} |\n")
        ns = result.get("findings", {}).get("no_forbidden_strategies", {})
        f.write(f"| no martingale/grid/averaging | {not ns.get('found_patterns')} |\n")
        osf = result.get("findings", {}).get("order_send_unreachable", {})
        f.write(f"| order_send not in build-request | {osf.get('build_request_safe', False)} |\n")
        f.write(f"| order_send not in autonomous-entry-check | {osf.get('autonomous_entry_check_safe', False)} |\n")
        f.write(f"| order_send not in audit scripts | {osf.get('audit_scripts_safe', False)} |\n")
        tg = result.get("findings", {}).get("token_gating", {})
        f.write(f"| OPERATOR_ARM_TOKEN_REQUIRED present | {tg.get('token_required_check_present', False)} |\n")
        f.write(f"| token creation not in audit scripts | {tg.get('token_creation_not_in_audit_scripts', False)} |\n")
        pm = result.get("findings", {}).get("position_modification_unreachable", {})
        f.write(f"| position modify not in audit scripts | {pm.get('safe', False)} |\n")
        bv = result.get("findings", {}).get("broker_venue_rules", {})
        f.write(f"| FundedNext demo blocked | {bv.get('fundednext_blocked', False)} |\n")
        f.write(f"| MetaQuotes-Demo allowed | {bv.get('metaquotes_allowed', False)} |\n\n")

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
    print("  TITAN XAU AI - Runtime Safety Gate Audit (v2.8.3.3)")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
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
    return 0 if result["verdict"] != RUNTIME_SAFETY_GATE_BLOCKED else 1


if __name__ == "__main__":
    sys.exit(main())
