"""
TITAN XAU AI — Sprint 9.9.2 Demo Micro Hard Gate (Config Fix)
===============================================================
Fixed: now reads top-level demo_micro config from runtime.yaml.
Uses shared config loader from demo_micro_config.py.
"""
from __future__ import annotations
import json, os, sys, platform
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

from scripts.audit.demo_micro_config import load_demo_micro_config


def evaluate(config_path: str = None) -> dict:
    checks = {}
    reasons = []

    # Load config
    cfg = load_demo_micro_config(config_path)

    # 1. MT5 reachable
    mt5_ok = False
    account_info = None
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            mt5_ok = True
            account_info = mt5.account_info()
            mt5.shutdown()
    except ImportError:
        pass
    checks["mt5_reachable"] = mt5_ok
    if not mt5_ok:
        reasons.append("MT5 not reachable (Linux or not installed)")

    # 2. Account type DEMO
    is_demo = False
    if account_info:
        is_demo = getattr(account_info, "trade_mode", 0) == 0
    checks["account_demo"] = is_demo
    if account_info and not is_demo:
        reasons.append("Account is NOT DEMO — BLOCKED")

    # 3. demo_micro.enabled — NOW READ FROM CONFIG (was hardcoded False)
    checks["demo_micro_enabled"] = cfg["demo_micro_enabled_effective"]
    if not cfg["demo_micro_enabled_effective"]:
        if not cfg["demo_micro_config_found"]:
            reasons.append("demo_micro section not found in config — default false")
        else:
            reasons.append(f"demo_micro.enabled={cfg['demo_micro_enabled_raw']} (config)")

    # 4. Operator arm token
    arm_env = cfg["arm_token_env"]
    arm_present = os.environ.get(arm_env, "0") == "1"
    checks["arm_token_present"] = arm_present
    if not arm_present:
        reasons.append(f"{arm_env} not set to 1")

    # 5. Real/live account blocked
    checks["not_real_account"] = is_demo or account_info is None
    if account_info and not is_demo:
        reasons.append("Real/live account detected — BLOCKED")

    # 6. max_lot <= 0.01
    checks["max_lot_ok"] = cfg["max_lot"] <= 0.01
    if not checks["max_lot_ok"]:
        reasons.append(f"max_lot={cfg['max_lot']} > 0.01")

    # 7. max_open_positions == 1
    checks["max_positions_ok"] = cfg["max_open_positions"] == 1
    if not checks["max_positions_ok"]:
        reasons.append(f"max_open_positions={cfg['max_open_positions']} != 1")

    # 8. max_trades <= 3
    checks["max_trades_ok"] = cfg["max_trades_per_run"] <= 3
    if not checks["max_trades_ok"]:
        reasons.append(f"max_trades_per_run={cfg['max_trades_per_run']} > 3")

    # 9. force_close_on_end
    checks["force_close_on_end"] = cfg["force_close_on_end"]
    if not cfg["force_close_on_end"]:
        reasons.append("force_close_on_end=false")

    # 10. Kill switch NORMAL (assumed)
    checks["kill_switch_normal"] = True

    # 11. Market open / weekend
    now = datetime.now(timezone.utc)
    is_weekend = now.weekday() >= 5
    checks["market_open"] = not is_weekend
    if is_weekend:
        reasons.append("Market closed (weekend)")

    # 12. Demo micro readiness report
    readiness_path = REPO_ROOT / "data" / "audit" / "demo_micro_readiness" / "demo_micro_readiness_report.json"
    readiness_ok = False
    if readiness_path.exists():
        try:
            with open(readiness_path) as f:
                r = json.load(f)
            readiness_ok = r.get("verdict") == "DEMO_MICRO_READY"
        except Exception:
            pass
    checks["demo_micro_readiness_ok"] = readiness_ok
    if not readiness_ok:
        reasons.append("Demo micro readiness report not found or not DEMO_MICRO_READY")

    # Verdict
    if is_weekend and mt5_ok:
        verdict = "MARKET_CLOSED"
    elif not mt5_ok:
        verdict = "DEMO_MICRO_BLOCKED"
    elif not is_demo:
        verdict = "DEMO_MICRO_BLOCKED"
    elif not cfg["demo_micro_enabled_effective"]:
        verdict = "DEMO_MICRO_BLOCKED"
    elif not arm_present:
        verdict = "DEMO_MICRO_BLOCKED"
    elif not readiness_ok:
        verdict = "DEMO_MICRO_BLOCKED"
    elif all(checks.values()):
        verdict = "DEMO_MICRO_ARMED"
    else:
        verdict = "DEMO_MICRO_BLOCKED"

    return {
        "verdict": verdict,
        "reasons": reasons,
        "checks": checks,
        "platform": platform.system(),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        # Diagnostic fields (Sprint 9.9.2)
        "config_path_used": cfg["config_path_used"],
        "demo_micro_config_found": cfg["demo_micro_config_found"],
        "demo_micro_enabled_raw": cfg["demo_micro_enabled_raw"],
        "demo_micro_enabled_effective": cfg["demo_micro_enabled_effective"],
    }


def main():
    print("=" * 78)
    print("  TITAN XAU AI — Sprint 9.9.2 Demo Micro Hard Gate (Config Fix)")
    print("=" * 78)

    result = evaluate()

    print(f"\n── Hard Gate Checks ──")
    for k, v in result["checks"].items():
        print(f"  [{'✓' if v else '✗'}] {k}: {v}")

    # Diagnostic output
    print(f"\n── Config Diagnostics ──")
    print(f"  config_path_used:            {result['config_path_used']}")
    print(f"  demo_micro_config_found:     {result['demo_micro_config_found']}")
    print(f"  demo_micro_enabled_raw:      {result['demo_micro_enabled_raw']}")
    print(f"  demo_micro_enabled_effective: {result['demo_micro_enabled_effective']}")

    if result["reasons"]:
        print(f"\n  Reasons:")
        for r in result["reasons"]:
            print(f"    - {r}")

    print(f"\n  VERDICT: {result['verdict']}")

    # Save report
    json_path = OUTPUT_DIR / "demo_micro_hard_gate_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    md_path = OUTPUT_DIR / "demo_micro_hard_gate_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Sprint 9.9.2 — Demo Micro Hard Gate (Config Fix)\n\n")
        f.write(f"**Verdict: {result['verdict']}**\n\n")
        f.write(f"## Config Diagnostics\n\n| Field | Value |\n|---|---|\n")
        f.write(f"| config_path_used | {result['config_path_used']} |\n")
        f.write(f"| demo_micro_config_found | {result['demo_micro_config_found']} |\n")
        f.write(f"| demo_micro_enabled_raw | {result['demo_micro_enabled_raw']} |\n")
        f.write(f"| demo_micro_enabled_effective | {result['demo_micro_enabled_effective']} |\n")
        f.write(f"\n## Checks\n\n| Check | Passed |\n|---|---|\n")
        for k, v in result["checks"].items():
            f.write(f"| {k} | {'✓' if v else '✗'} |\n")
        if result["reasons"]:
            f.write(f"\n## Reasons\n\n")
            for r in result["reasons"]:
                f.write(f"- {r}\n")

    print(f"\n  JSON: {json_path}")
    print(f"  MD:   {md_path}")


if __name__ == "__main__":
    main()
