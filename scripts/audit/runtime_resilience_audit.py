#!/usr/bin/env python3
"""
TITAN XAU AI - Runtime Resilience Audit
=========================================
Verifies that the runtime resilience subsystem (RuntimeHealthGuard,
FailClosedRuntimeGuard, WatchdogRestarter) is present and exhibits the
required fail-closed safety properties.

NEVER imports MetaTrader5. NEVER sends orders. Pure-Python source audit.

Verdicts:
  - RESILIENCE_READY        : all critical checks pass.
  - RESILIENCE_NEEDS_WORK   : non-blocking issues found.
  - RESILIENCE_BLOCKED      : a fail-closed safety property is missing.
"""
from __future__ import annotations

import inspect
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "runtime_resilience"
JSON_PATH = OUTPUT_DIR / "runtime_resilience_audit.json"
MD_PATH = OUTPUT_DIR / "runtime_resilience_audit.md"

REQUIRED_MODULES: dict[str, tuple[str, ...]] = {
    "titan/production/runtime_health_guard.py": (
        "RuntimeHealthGuard", "heartbeat", "check_component",
        "enter_recovery_mode", "is_healthy",
    ),
    "titan/production/fail_closed_runtime_guard.py": (
        "FailClosedRuntimeGuard", "emergency_stop", "block_new_trades",
        "allow_new_trades", "is_blocked",
    ),
    "titan/production/watchdog_restarter.py": (
        "WatchdogRestarter", "check_orphan_positions",
        "safe_restart", "generate_crash_report",
    ),
}

RESILIENCE_READY = "RESILIENCE_READY"
RESILIENCE_NEEDS_WORK = "RESILIENCE_NEEDS_WORK"
RESILIENCE_BLOCKED = "RESILIENCE_BLOCKED"


def _git_head_short() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10,
        )
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'r"[^"]*"', '""', src)
    src = re.sub(r"r'[^']*'", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    out = []
    for line in src.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


def _has_no_order_send(code: str) -> bool:
    return not re.search(r"\bmt5\.order_send\s*\(", code) and \
           not re.search(r"\bMetaTrader5\.order_send\s*\(", code)


def _has_no_martingale(code: str) -> bool:
    bad = ("martingale", "grid_doubling", "averaging_down", "loss_based_lot_multiplier")
    low = code.lower()
    return not any(b in low for b in bad)


def run_audit() -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    head = _git_head_short()

    ok_checks: list[str] = []
    warnings_list: list[str] = []
    blockers: list[str] = []

    # 1. Each required module exists with required symbols
    for rel, symbols in REQUIRED_MODULES.items():
        path = REPO_ROOT / rel
        if not path.exists():
            blockers.append(f"missing required module: {rel}")
            continue
        src = path.read_text(encoding="utf-8")
        for sym in symbols:
            if sym not in src:
                blockers.append(f"{rel}: missing required symbol '{sym}'")
            else:
                ok_checks.append(f"{rel}: defines '{sym}'")

    # 2. Each module declares `from __future__ import annotations`
    for rel in REQUIRED_MODULES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        if "from __future__ import annotations" in src:
            ok_checks.append(f"{rel}: future annotations declared")
        else:
            blockers.append(f"{rel}: missing 'from __future__ import annotations'")

    # 3. Safety: no order_send, no martingale/grid/averaging in any module
    for rel in REQUIRED_MODULES:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        src = path.read_text(encoding="utf-8")
        code = _strip(src)
        if _has_no_order_send(code):
            ok_checks.append(f"{rel}: never calls mt5.order_send")
        else:
            blockers.append(f"{rel}: calls mt5.order_send")
        if _has_no_martingale(code):
            ok_checks.append(f"{rel}: no martingale/grid/averaging")
        else:
            blockers.append(f"{rel}: contains banned betting pattern")

    # 4. FailClosedRuntimeGuard is fail-closed (is_blocked reflects all 3 sources)
    fcrg_path = REPO_ROOT / "titan/production/fail_closed_runtime_guard.py"
    if fcrg_path.exists():
        fcrg_src = fcrg_path.read_text(encoding="utf-8")
        if "emergency_stop" in fcrg_src and "recovery_mode" in fcrg_src and "manual_block" in fcrg_src:
            ok_checks.append("FailClosedRuntimeGuard: tracks emergency/recovery/manual states")
        else:
            blockers.append("FailClosedRuntimeGuard: missing one of emergency/recovery/manual states")
        if "is_blocked" in fcrg_src:
            ok_checks.append("FailClosedRuntimeGuard: exposes is_blocked()")
        else:
            blockers.append("FailClosedRuntimeGuard: missing is_blocked()")

    # 5. RuntimeHealthGuard exposes heartbeat/check_component/enter_recovery_mode/is_healthy
    rhg_path = REPO_ROOT / "titan/production/runtime_health_guard.py"
    if rhg_path.exists():
        rhg_src = rhg_path.read_text(encoding="utf-8")
        for m in ("def heartbeat", "def check_component", "def enter_recovery_mode", "def is_healthy"):
            if m in rhg_src:
                ok_checks.append(f"RuntimeHealthGuard: defines {m}")
            else:
                blockers.append(f"RuntimeHealthGuard: missing {m}")

    # 6. WatchdogRestarter exposes new methods + does NOT claim "never crash"
    wr_path = REPO_ROOT / "titan/production/watchdog_restarter.py"
    if wr_path.exists():
        wr_src = wr_path.read_text(encoding="utf-8")
        for m in ("def check_orphan_positions", "async def safe_restart", "def generate_crash_report"):
            if m in wr_src:
                ok_checks.append(f"WatchdogRestarter: defines {m}")
            else:
                blockers.append(f"WatchdogRestarter: missing {m}")

        # Never claim "crash impossible" or "never crashes"
        wr_lower = wr_src.lower()
        bad_claims = []
        for phrase in ("crash impossible", "never crashes", "never crash", "crashes impossible"):
            # Allow phrase inside negation context only.
            if phrase in wr_lower:
                idx = wr_lower.find(phrase)
                ctx_before = wr_lower[max(0, idx - 40):idx]
                if "not" in ctx_before or "does not" in ctx_before or "don't" in ctx_before:
                    ok_checks.append(f"WatchdogRestarter: phrase '{phrase}' used only in negation")
                else:
                    bad_claims.append(phrase)
        if bad_claims:
            blockers.append(
                f"WatchdogRestarter: falsely claims {bad_claims} — must be fail-closed, recoverable, auditable"
            )
        else:
            ok_checks.append("WatchdogRestarter: does not falsely claim crash impossible")

        # Must explicitly state "fail-closed, recoverable, auditable" (or similar)
        if "fail-closed" in wr_lower and "recoverable" in wr_lower and "auditable" in wr_lower:
            ok_checks.append("WatchdogRestarter: claims fail-closed, recoverable, auditable")
        else:
            blockers.append(
                "WatchdogRestarter: missing fail-closed/recoverable/auditable safety claim"
            )

    # 7. Runtime self-test: build guards, simulate failure, verify fail-closed
    try:
        from titan.production.runtime_health_guard import RuntimeHealthGuard
        from titan.production.fail_closed_runtime_guard import FailClosedRuntimeGuard
        import time as _t

        # Simulate a clock so we can move time forward deterministically.
        t0 = _t.time()
        fake_now = [t0]

        def clock() -> float:
            return fake_now[0]

        rhg = RuntimeHealthGuard(clock=clock, recovery_threshold=2)
        fcrg = FailClosedRuntimeGuard(clock=clock)
        fcrg.set_recovery_mode(False)  # initially healthy

        rhg.register_component("inference_loop", expected_interval_s=1.0)
        # No heartbeat yet → check_component returns False
        healthy = rhg.check_component("inference_loop")
        if healthy:
            blockers.append("RuntimeHealthGuard: did NOT detect missing heartbeat")
        else:
            ok_checks.append("RuntimeHealthGuard: detects missing heartbeat")
        # First failure: not yet in recovery (threshold=2)
        if rhg.in_recovery:
            blockers.append("RuntimeHealthGuard: entered recovery too early (threshold=2)")
        else:
            ok_checks.append("RuntimeHealthGuard: respects recovery threshold")
        # Advance time + check again → should enter recovery
        fake_now[0] = t0 + 10.0
        rhg.check_component("inference_loop")
        if not rhg.in_recovery:
            blockers.append("RuntimeHealthGuard: did NOT enter recovery after threshold")
        else:
            ok_checks.append("RuntimeHealthGuard: enters recovery after threshold")

        # Mirror recovery into FailClosedRuntimeGuard
        fcrg.set_recovery_mode(True, reason="runtime_unhealthy")
        if not fcrg.is_blocked():
            blockers.append("FailClosedRuntimeGuard: not blocked when in recovery mode")
        else:
            ok_checks.append("FailClosedRuntimeGuard: blocks when in recovery mode")

        # Try to allow new trades while in recovery — must fail.
        if fcrg.allow_new_trades(reason="attempt"):
            blockers.append("FailClosedRuntimeGuard: allowed new trades while in recovery mode")
        else:
            ok_checks.append("FailClosedRuntimeGuard: refuses to allow trades in recovery mode")

        # Trigger emergency stop — must be sticky.
        fcrg.set_recovery_mode(False)
        fcrg.emergency_stop(reason="test")
        if not fcrg.emergency_stop_active:
            blockers.append("FailClosedRuntimeGuard: emergency stop not active")
        else:
            ok_checks.append("FailClosedRuntimeGuard: emergency stop is active")
        # Cannot reset emergency stop if manual block set
        fcrg.block_new_trades()
        if fcrg.reset_emergency_stop():
            blockers.append("FailClosedRuntimeGuard: reset emergency stop with manual block active")
        else:
            ok_checks.append("FailClosedRuntimeGuard: refuses to reset emergency stop with manual block")

    except Exception as e:
        blockers.append(f"Resilience runtime self-test error: {e}")

    # 8. WatchdogRestarter runtime self-test: orphan detection + safe_restart
    try:
        import asyncio
        from titan.production.watchdog_restarter import (
            WatchdogRestarter, OrphanPositionReport, CrashReport,
        )
        # Provider returns two orphan positions
        positions = [
            {"ticket": 1, "magic": 4242, "symbol": "XAUUSD", "volume": 0.1},
            {"ticket": 2, "magic": 4242, "symbol": "XAUUSD", "volume": 0.2},
        ]
        wr = WatchdogRestarter(
            dry_run=True,
            positions_provider=lambda: positions,
        )
        rep = wr.check_orphan_positions(magic_filter=4242)
        if not rep.has_orphans or rep.orphan_count != 2:
            blockers.append(
                f"WatchdogRestarter: orphan detection failed (count={rep.orphan_count})"
            )
        else:
            ok_checks.append("WatchdogRestarter: orphan detection works")

        # safe_restart with orphans present → must abort (fail-closed)
        async def _sr():
            return await wr.safe_restart(reason="audit test")
        cr = asyncio.get_event_loop().run_until_complete(_sr()) \
            if False else asyncio.run(_sr())
        if "ABORTED" in cr.reason:
            ok_checks.append("WatchdogRestarter: safe_restart aborts when orphans present")
        else:
            blockers.append(
                f"WatchdogRestarter: safe_restart did NOT abort with orphans ({cr.reason})"
            )

        # generate_crash_report — must include fail-closed design note
        wr2 = WatchdogRestarter(dry_run=True, positions_provider=lambda: [])
        cr2 = wr2.generate_crash_report(reason="audit test")
        if cr2.fail_closed and cr2.never_claims_never_crash:
            ok_checks.append("WatchdogRestarter: crash report is fail-closed + auditable")
        else:
            blockers.append("WatchdogRestarter: crash report missing fail-closed/auditable fields")
    except Exception as e:
        blockers.append(f"WatchdogRestarter runtime self-test error: {e}")

    # ── Verdict ─────────────────────────────────────────────────────────
    if blockers:
        verdict = RESILIENCE_BLOCKED
    elif warnings_list:
        verdict = RESILIENCE_NEEDS_WORK
    else:
        verdict = RESILIENCE_READY

    return {
        "timestamp_utc": ts,
        "head_short": head,
        "verdict": verdict,
        "ok_checks": ok_checks,
        "warnings": warnings_list,
        "blockers": blockers,
        "design_description": (
            "Fail-closed runtime resilience with heartbeat health guard, "
            "sticky emergency stop, orphan-position detection on restart, "
            "and auditable crash reports. The system is crash-tolerant, "
            "recoverable, and auditable — it does NOT claim 'never crash'."
        ),
    }


def write_report(result: dict) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str, ensure_ascii=False)
    with open(MD_PATH, "w", encoding="utf-8") as f:
        f.write("# TITAN XAU AI - Runtime Resilience Audit\n\n")
        f.write(f"**Verdict:** **{result['verdict']}**\n\n")
        f.write(f"**Design:** {result['design_description']}\n\n")
        f.write(f"**Timestamp:** {result['timestamp_utc']}\n\n")
        if result.get("ok_checks"):
            f.write("## OK Checks\n\n")
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
        f.write("\n**The system does NOT claim 'crash impossible'.**\n")
        f.write("**The system IS fail-closed, recoverable, and auditable.**\n")
    return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}


def main() -> int:
    print("=" * 70)
    print("  TITAN XAU AI - Runtime Resilience Audit")
    print("=" * 70)
    result = run_audit()
    report = write_report(result)
    print(f"\n  Verdict: {result['verdict']}")
    print(f"  Blockers: {len(result['blockers'])}")
    print(f"  Warnings: {len(result['warnings'])}")
    print(f"\n  JSON: {report['json_path']}")
    print(f"  MD:   {report['md_path']}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
