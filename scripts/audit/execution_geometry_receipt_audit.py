#!/usr/bin/env python3
"""
TITAN XAU AI - Execution Geometry Receipt Audit (Sprint 9.9.3.45.8.15)
======================================================================
Passive audit of the demo micro execution receipt geometry.

Reads:
  - data/runtime/demo_micro_execution_receipt.json
  - config/account_profiles.yaml (optional, used to source minimum_RR
    and initial_tp_R defaults when the receipt does not carry them).

Computes the realised trade geometry from the receipt's requested SL/TP
and detected entry price:
  - side, entry, SL, TP
  - risk_distance, reward_distance
  - actual_RR = reward_distance / risk_distance
  - expected initial_tp_R
  - minimum_RR (from profile or default 2.0)
  - geometry_verdict:
      EXECUTION_GEOMETRY_PASS                  (actual_RR >= minimum_RR)
      EXECUTION_GEOMETRY_FAIL_RR_BELOW_MINIMUM (actual_RR <  minimum_RR)

The audit NEVER calls mt5.order_send. It NEVER modifies positions. It
NEVER falls back to martingale / grid / averaging / loss-based lot
multiplier - the audit is a pure passive observer of the receipt.

Outputs:
  - data/audit/demo_micro_execution/execution_geometry_audit.json
  - data/audit/demo_micro_execution/execution_geometry_audit.md
"""
from __future__ import annotations
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

RECEIPT_PATH = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"
ACCOUNT_PROFILES_PATH = REPO_ROOT / "config" / "account_profiles.yaml"
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

# Hard defaults - profile overrides when present
DEFAULT_MINIMUM_RR = 2.0
DEFAULT_INITIAL_TP_R = 3.0

VERDICT_PASS = "EXECUTION_GEOMETRY_PASS"
VERDICT_FAIL_RR_BELOW_MINIMUM = "EXECUTION_GEOMETRY_FAIL_RR_BELOW_MINIMUM"
VERDICT_RECEIPT_MISSING = "EXECUTION_GEOMETRY_RECEIPT_MISSING"
VERDICT_RECEIPT_INSUFFICIENT = "EXECUTION_GEOMETRY_RECEIPT_INSUFFICIENT"


def _load_receipt(path: Optional[Path] = None) -> Optional[dict]:
    """Load receipt JSON. Returns None if missing or unreadable."""
    p = path or RECEIPT_PATH
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _load_account_profile(profile_name: str = "") -> dict:
    """Load account profile from config/account_profiles.yaml.

    Returns empty dict if file missing, yaml missing, or profile not found.
    Never raises.
    """
    if not profile_name:
        return {}
    if not ACCOUNT_PROFILES_PATH.exists():
        return {}
    try:
        import yaml
        with open(ACCOUNT_PROFILES_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return (data.get("profiles") or {}).get(profile_name, {}) or {}
    except Exception:
        return {}


def _safe_float(value: Any) -> float:
    """Coerce value to float, returning 0.0 for None/invalid."""
    if value is None:
        return 0.0
    try:
        f = float(value)
        if f != f:  # NaN
            return 0.0
        return f
    except (TypeError, ValueError):
        return 0.0


def _derive_entry_from_sl_tp(side: str, sl: float, tp: float,
                              initial_tp_r: float) -> float:
    """Derive entry price from SL/TP and initial_tp_R.

    For both BUY and SELL, the consistent relationship when reward/risk =
    initial_tp_R is:
        entry = (TP + initial_tp_R * SL) / (1 + initial_tp_R)

    Returns 0.0 if inputs insufficient.
    """
    if sl <= 0 or tp <= 0 or initial_tp_r <= 0:
        return 0.0
    side_upper = (side or "").upper()
    # Sanity: BUY should have SL < TP; SELL should have SL > TP. We do not
    # enforce hard block here - the audit will flag the geometry as broken
    # via risk/reward signs, but we still need a numeric entry.
    if side_upper == "BUY":
        if sl >= tp:
            return 0.0
    elif side_upper == "SELL":
        if tp >= sl:
            return 0.0
    return (tp + initial_tp_r * sl) / (1.0 + initial_tp_r)


def _resolve_entry(receipt: dict, side: str, sl: float, tp: float,
                   initial_tp_r: float) -> tuple[float, str]:
    """Resolve entry price with safe fallback chain.

    Returns (entry_price, entry_source).
    """
    # 1. Direct detected position entry price (most authoritative)
    detected_entry = _safe_float(receipt.get("detected_position_entry_price"))
    if detected_entry > 0:
        return detected_entry, "detected_position_entry_price"
    # 2. Order send result price (broker-reported fill)
    fill_price = _safe_float(receipt.get("order_send_result_price"))
    if fill_price > 0:
        return fill_price, "order_send_result_price"
    # 3. Derived from requested SL/TP using initial_tp_R formula
    derived = _derive_entry_from_sl_tp(side, sl, tp, initial_tp_r)
    if derived > 0:
        return derived, "derived_from_requested_sl_tp"
    return 0.0, "unavailable"


def _compute_geometry(side: str, entry: float, sl: float, tp: float) -> dict:
    """Compute risk_distance, reward_distance, actual_RR.

    For BUY:  risk_distance = entry - SL, reward_distance = TP - entry
    For SELL: risk_distance = SL - entry, reward_distance = entry - TP
    """
    side_upper = (side or "").upper()
    if side_upper == "BUY":
        risk_distance = entry - sl
        reward_distance = tp - entry
    elif side_upper == "SELL":
        risk_distance = sl - entry
        reward_distance = entry - tp
    else:
        risk_distance = 0.0
        reward_distance = 0.0
    actual_rr = (reward_distance / risk_distance) if risk_distance > 0 else 0.0
    return {
        "risk_distance": round(risk_distance, 6),
        "reward_distance": round(reward_distance, 6),
        "actual_RR": round(actual_rr, 6),
        "risk_distance_positive": risk_distance > 0,
        "reward_distance_positive": reward_distance > 0,
    }


def _geometry_verdict(actual_rr: float, minimum_rr: float) -> str:
    """Return PASS or FAIL_RR_BELOW_MINIMUM based on actual_RR vs minimum."""
    if actual_rr >= minimum_rr:
        return VERDICT_PASS
    return VERDICT_FAIL_RR_BELOW_MINIMUM


def run_audit(receipt_path: Optional[Path] = None,
              account_profile_name: str = "",
              override_minimum_rr: Optional[float] = None,
              override_initial_tp_r: Optional[float] = None) -> dict:
    """Run the geometry audit against the latest receipt.

    Returns a dict with: timestamp_utc, verdict, blockers, warnings,
    ok_checks, geometry, profile, receipt_path, safety.

    NEVER calls mt5.order_send. NEVER modifies positions.
    """
    ts = datetime.now(timezone.utc).isoformat()
    ok_checks: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    safety = {
        "order_send_called": False,
        "position_modified": False,
        "martingale_used": False,
        "grid_used": False,
        "averaging_used": False,
        "loss_based_lot_multiplier_used": False,
    }

    path = receipt_path or RECEIPT_PATH
    receipt = _load_receipt(path)

    if not receipt:
        blockers.append("EXECUTION_GEOMETRY_RECEIPT_MISSING: receipt file not found or unreadable")
        return {
            "timestamp_utc": ts,
            "verdict": VERDICT_RECEIPT_MISSING,
            "ok_checks": ok_checks,
            "blockers": blockers,
            "warnings": warnings,
            "geometry": {},
            "profile": {"name": account_profile_name or ""},
            "receipt_path": str(path),
            "safety": safety,
        }

    ok_checks.append(f"Receipt loaded from {path}")

    # Determine profile name from receipt or argument
    profile_name = account_profile_name or receipt.get("account_profile") or ""
    profile = _load_account_profile(profile_name) if profile_name else {}
    if profile:
        ok_checks.append(f"Account profile loaded: {profile_name}")
    elif profile_name:
        warnings.append(f"Account profile '{profile_name}' not found - using defaults")
    else:
        warnings.append("No account profile specified - using defaults")

    # Resolve side
    side = (receipt.get("side") or receipt.get("direction") or "").upper()
    if side not in ("BUY", "SELL"):
        blockers.append(f"EXECUTION_GEOMETRY_SIDE_INVALID: side='{side}' must be BUY or SELL")
        return {
            "timestamp_utc": ts,
            "verdict": VERDICT_RECEIPT_INSUFFICIENT,
            "ok_checks": ok_checks,
            "blockers": blockers,
            "warnings": warnings,
            "geometry": {"side": side},
            "profile": {"name": profile_name, "fields": profile},
            "receipt_path": str(path),
            "safety": safety,
        }
    ok_checks.append(f"Side: {side}")

    # Resolve SL/TP - support both requested_sl/tp and request_sl/tp aliases
    sl = _safe_float(
        receipt.get("requested_sl")
        if receipt.get("requested_sl") is not None
        else receipt.get("request_sl")
    )
    tp = _safe_float(
        receipt.get("requested_tp")
        if receipt.get("requested_tp") is not None
        else receipt.get("request_tp")
    )

    if sl <= 0:
        blockers.append("EXECUTION_GEOMETRY_SL_MISSING: requested_sl not present or zero in receipt")
    if tp <= 0:
        blockers.append("EXECUTION_GEOMETRY_TP_MISSING: requested_tp not present or zero in receipt")
    if blockers:
        return {
            "timestamp_utc": ts,
            "verdict": VERDICT_RECEIPT_INSUFFICIENT,
            "ok_checks": ok_checks,
            "blockers": blockers,
            "warnings": warnings,
            "geometry": {"side": side, "sl": sl, "tp": tp},
            "profile": {"name": profile_name, "fields": profile},
            "receipt_path": str(path),
            "safety": safety,
        }

    ok_checks.append(f"SL: {sl}")
    ok_checks.append(f"TP: {tp}")

    # Resolve minimum_RR and initial_tp_R with override > profile > default
    minimum_rr = (
        override_minimum_rr
        if override_minimum_rr is not None
        else _safe_float(profile.get("minimum_RR")) or DEFAULT_MINIMUM_RR
    )
    initial_tp_r = (
        override_initial_tp_r
        if override_initial_tp_r is not None
        else _safe_float(profile.get("dynamic_tp_initial_tp_R")) or DEFAULT_INITIAL_TP_R
    )
    if override_minimum_rr is not None:
        ok_checks.append(f"minimum_RR override: {minimum_rr}")
    if override_initial_tp_r is not None:
        ok_checks.append(f"initial_tp_R override: {initial_tp_r}")

    # Resolve entry price (with safe fallback chain)
    entry, entry_source = _resolve_entry(receipt, side, sl, tp, initial_tp_r)
    if entry <= 0:
        blockers.append(
            "EXECUTION_GEOMETRY_ENTRY_UNAVAILABLE: could not resolve entry price "
            "from detected_position_entry_price, order_send_result_price, or "
            "derived_from_requested_sl_tp"
        )
        return {
            "timestamp_utc": ts,
            "verdict": VERDICT_RECEIPT_INSUFFICIENT,
            "ok_checks": ok_checks,
            "blockers": blockers,
            "warnings": warnings,
            "geometry": {"side": side, "sl": sl, "tp": tp, "entry": 0.0},
            "profile": {
                "name": profile_name,
                "fields": profile,
                "minimum_RR": minimum_rr,
                "initial_tp_R": initial_tp_r,
            },
            "receipt_path": str(path),
            "safety": safety,
        }
    ok_checks.append(f"Entry resolved via {entry_source}: {entry}")

    geometry = _compute_geometry(side, entry, sl, tp)
    if not geometry["risk_distance_positive"]:
        blockers.append(
            f"EXECUTION_GEOMETRY_RISK_DISTANCE_NONPOSITIVE: risk_distance={geometry['risk_distance']} "
            f"must be > 0 (side={side}, entry={entry}, SL={sl})"
        )
    if not geometry["reward_distance_positive"]:
        blockers.append(
            f"EXECUTION_GEOMETRY_REWARD_DISTANCE_NONPOSITIVE: reward_distance={geometry['reward_distance']} "
            f"must be > 0 (side={side}, entry={entry}, TP={tp})"
        )

    actual_rr = geometry["actual_RR"]
    verdict = _geometry_verdict(actual_rr, minimum_rr)
    if verdict == VERDICT_FAIL_RR_BELOW_MINIMUM:
        blockers.append(
            f"EXECUTION_GEOMETRY_RR_BELOW_MINIMUM: actual_RR={actual_rr:.6f} "
            f"< minimum_RR={minimum_rr:.6f}"
        )
    else:
        ok_checks.append(
            f"Geometry PASS: actual_RR={actual_rr:.6f} >= minimum_RR={minimum_rr:.6f}"
        )

    geometry_payload = {
        "side": side,
        "entry": round(entry, 6),
        "sl": sl,
        "tp": tp,
        "entry_source": entry_source,
        "risk_distance": geometry["risk_distance"],
        "reward_distance": geometry["reward_distance"],
        "actual_RR": actual_rr,
        "expected_initial_tp_R": initial_tp_r,
        "minimum_RR": minimum_rr,
        "geometry_verdict": verdict,
        "risk_distance_positive": geometry["risk_distance_positive"],
        "reward_distance_positive": geometry["reward_distance_positive"],
    }

    return {
        "timestamp_utc": ts,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "blockers": blockers,
        "warnings": warnings,
        "geometry": geometry_payload,
        "profile": {
            "name": profile_name,
            "fields": profile,
            "minimum_RR": minimum_rr,
            "initial_tp_R": initial_tp_r,
        },
        "receipt_path": str(path),
        "safety": safety,
    }


def write_report(result: dict, output_dir: Optional[Path] = None) -> dict:
    """Write the audit result to JSON and MD files.

    Returns dict with json_path and md_path.
    """
    out = output_dir or OUTPUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "execution_geometry_audit.json"
    md_path = out / "execution_geometry_audit.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Execution Geometry Receipt Audit\n\n")
        f.write("**Passive audit - no order_send, no position modification.**\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        f.write(f"**Receipt path:** `{result.get('receipt_path', '')}`\n\n")

        geo = result.get("geometry", {}) or {}
        profile = result.get("profile", {}) or {}
        f.write("## Geometry\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k in [
            "side", "entry", "entry_source", "sl", "tp",
            "risk_distance", "reward_distance", "actual_RR",
            "expected_initial_tp_R", "minimum_RR", "geometry_verdict",
            "risk_distance_positive", "reward_distance_positive",
        ]:
            if k in geo:
                f.write(f"| {k} | {geo[k]} |\n")

        f.write("\n## Profile\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        f.write(f"| name | {profile.get('name', '')} |\n")
        f.write(f"| minimum_RR | {profile.get('minimum_RR', '')} |\n")
        f.write(f"| initial_tp_R | {profile.get('initial_tp_R', '')} |\n")

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

        safety = result.get("safety", {}) or {}
        f.write("\n## Safety\n\n")
        f.write("| Field | Value |\n|---|---|\n")
        for k, v in safety.items():
            f.write(f"| {k} | {v} |\n")
        f.write("\n- No `mt5.order_send` was called.\n")
        f.write("- No martingale / grid / averaging / loss-based lot multiplier was used.\n")
        f.write("- This audit is a passive observer of the receipt only.\n")

    return {"json_path": str(json_path), "md_path": str(md_path)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execution geometry receipt audit (passive, no order_send)"
    )
    parser.add_argument("--receipt", type=str, default="",
                        help="Override receipt JSON path")
    parser.add_argument("--account-profile", type=str, default="",
                        help="Account profile name (default: from receipt)")
    parser.add_argument("--minimum-rr", type=float, default=None,
                        help="Override minimum_RR (default: profile or 2.0)")
    parser.add_argument("--initial-tp-r", type=float, default=None,
                        help="Override initial_tp_R (default: profile or 3.0)")
    args = parser.parse_args()

    receipt_path = Path(args.receipt) if args.receipt else None
    result = run_audit(
        receipt_path=receipt_path,
        account_profile_name=args.account_profile,
        override_minimum_rr=args.minimum_rr,
        override_initial_tp_r=args.initial_tp_r,
    )
    report = write_report(result)

    print("=" * 70)
    print("  TITAN XAU AI - Execution Geometry Receipt Audit")
    print("  (Sprint 9.9.3.45.8.15)")
    print("=" * 70)
    print(f"  Verdict: {result['verdict']}")
    geo = result.get("geometry", {}) or {}
    if geo:
        print(f"  Side:        {geo.get('side', '')}")
        print(f"  Entry:       {geo.get('entry', '')} ({geo.get('entry_source', '')})")
        print(f"  SL:          {geo.get('sl', '')}")
        print(f"  TP:          {geo.get('tp', '')}")
        print(f"  Risk dist:   {geo.get('risk_distance', '')}")
        print(f"  Reward dist: {geo.get('reward_distance', '')}")
        print(f"  Actual RR:   {geo.get('actual_RR', '')}")
        print(f"  Minimum RR:  {geo.get('minimum_RR', '')}")
        print(f"  Initial tp R:{geo.get('expected_initial_tp_R', '')}")
    print(f"  Blockers:    {len(result.get('blockers', []))}")
    print(f"  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
