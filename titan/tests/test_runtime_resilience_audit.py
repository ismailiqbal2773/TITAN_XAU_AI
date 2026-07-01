"""
TITAN XAU AI — Runtime Resilience Audit Tests
==============================================

10+ tests covering:
  - Audit produces a verdict in the valid set
  - Audit does not import MetaTrader5 or call order_send
  - Audit does not contain banned betting patterns
  - Audit reports no blockers (i.e. RESILIENCE_READY)
  - WatchdogRestarter new methods are wired and behave correctly
  - RuntimeHealthGuard heartbeat / recovery
  - FailClosedRuntimeGuard sticky emergency stop
  - JSON / MD reports are written correctly
  - Crash reports never claim "crash impossible"

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


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


class TestResilienceAudit:
    def test_01_verdict_in_valid_set(self):
        import scripts.audit.runtime_resilience_audit as mod
        result = mod.run_audit()
        assert result["verdict"] in (
            mod.RESILIENCE_READY,
            mod.RESILIENCE_NEEDS_WORK,
            mod.RESILIENCE_BLOCKED,
        )

    def test_02_no_metatrader5_import(self):
        import scripts.audit.runtime_resilience_audit as mod
        src = inspect.getsource(mod)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_03_no_order_send(self):
        import scripts.audit.runtime_resilience_audit as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bMetaTrader5\.order_send\s*\(", code)

    def test_04_no_martingale_grid_averaging(self):
        """The audit script may *mention* banned patterns (it must detect
        them), but must NOT implement them as actual betting logic —
        e.g., no `def apply_martingale`, no lot-doubling on loss.
        """
        import scripts.audit.runtime_resilience_audit as mod
        src = inspect.getsource(mod)
        # Strip strings/comments so banned words mentioned as detection
        # string literals are removed before scanning.
        code = _strip(src)
        low = code.lower()
        # Forbidden: function definitions / calls that implement the banned
        # patterns as actual logic.
        forbidden_patterns = [
            r"def\s+apply_martingale",
            r"def\s+apply_grid",
            r"def\s+average_down",
            r"lot\s*\*\s*2\b",                # lot doubling
            r"position_size\s*\*=\s*2\b",
            r"loss_based_lot_multiplier\s*=",
        ]
        for pat in forbidden_patterns:
            assert not re.search(pat, low), (
                f"audit script implements banned betting pattern: {pat}"
            )

    def test_05_json_writes(self, tmp_path):
        import scripts.audit.runtime_resilience_audit as mod
        old_d, old_j, old_m = mod.OUTPUT_DIR, mod.JSON_PATH, mod.MD_PATH
        mod.OUTPUT_DIR = tmp_path
        mod.JSON_PATH = tmp_path / "rr.json"
        mod.MD_PATH = tmp_path / "rr.md"
        try:
            result = mod.run_audit()
            report = mod.write_report(result)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f:
                data = json.load(f)
            assert "verdict" in data
            assert "ok_checks" in data and "blockers" in data
        finally:
            mod.OUTPUT_DIR, mod.JSON_PATH, mod.MD_PATH = old_d, old_j, old_m

    def test_06_md_writes_and_contains_safety_claims(self, tmp_path):
        import scripts.audit.runtime_resilience_audit as mod
        old_d, old_j, old_m = mod.OUTPUT_DIR, mod.JSON_PATH, mod.MD_PATH
        mod.OUTPUT_DIR = tmp_path
        mod.JSON_PATH = tmp_path / "rr.json"
        mod.MD_PATH = tmp_path / "rr.md"
        try:
            result = mod.run_audit()
            report = mod.write_report(result)
            md = Path(report["md_path"]).read_text()
            assert "Runtime Resilience Audit" in md
            assert "fail-closed" in md.lower()
            assert "recoverable" in md.lower()
            assert "auditable" in md.lower()
            # MD must NOT positively claim "crash impossible" / "never crashes"
            # without negation context.
            for line in md.splitlines():
                stripped = line.strip().lower()
                if "crash impossible" in stripped or "never crashes" in stripped:
                    assert (
                        "not" in stripped
                        or "negation" in stripped
                        or "doesn't" in stripped
                        or "don't" in stripped
                    ), f"MD falsely claims: {stripped}"
        finally:
            mod.OUTPUT_DIR, mod.JSON_PATH, mod.MD_PATH = old_d, old_j, old_m

    def test_07_audit_reports_ready_or_work(self):
        """The resilience subsystem must be READY (no blockers)."""
        import scripts.audit.runtime_resilience_audit as mod
        result = mod.run_audit()
        assert result["verdict"] == mod.RESILIENCE_READY, (
            f"Expected RESILIENCE_READY, got {result['verdict']}. "
            f"Blockers: {result['blockers']}"
        )

    def test_08_audit_design_description_present(self):
        import scripts.audit.runtime_resilience_audit as mod
        result = mod.run_audit()
        assert "design_description" in result
        dd = result["design_description"].lower()
        assert "fail-closed" in dd
        assert "recoverable" in dd
        assert "auditable" in dd


class TestRuntimeHealthGuard:
    def test_09_heartbeat_then_check_component_marks_healthy(self):
        from titan.production.runtime_health_guard import RuntimeHealthGuard
        t0 = time.time()
        fake_now = [t0]
        rhg = RuntimeHealthGuard(clock=lambda: fake_now[0], recovery_threshold=2)
        rhg.register_component("loop_a", expected_interval_s=1.0)
        rhg.heartbeat("loop_a", status="ok")
        assert rhg.check_component("loop_a") is True
        assert rhg.is_healthy() is True

    def test_10_stale_heartbeat_triggers_recovery(self):
        from titan.production.runtime_health_guard import RuntimeHealthGuard
        t0 = time.time()
        fake_now = [t0]
        rhg = RuntimeHealthGuard(clock=lambda: fake_now[0], recovery_threshold=2)
        rhg.register_component("loop_a", expected_interval_s=1.0)
        rhg.heartbeat("loop_a")
        # Advance time well past threshold
        fake_now[0] = t0 + 10.0
        rhg.check_component("loop_a")  # first failure
        rhg.check_component("loop_a")  # second failure → recovery
        assert rhg.in_recovery is True
        assert rhg.is_healthy() is False
        # Once we heartbeat again and re-check, recovery should clear.
        rhg.heartbeat("loop_a")
        rhg.check_component("loop_a")
        # exit_recovery_mode requires all components healthy; check again:
        assert rhg.is_healthy() is True
        assert rhg.in_recovery is False


class TestFailClosedRuntimeGuard:
    def test_11_emergency_stop_is_sticky(self):
        from titan.production.fail_closed_runtime_guard import FailClosedRuntimeGuard
        t0 = time.time()
        guard = FailClosedRuntimeGuard(clock=lambda: t0)
        # Healthy state initially
        assert guard.is_blocked() is False
        guard.emergency_stop(reason="test")
        assert guard.is_blocked() is True
        assert guard.emergency_stop_active is True
        # Cannot reset without clearing manual block + recovery (currently none set,
        # so this should succeed).
        assert guard.reset_emergency_stop(reason="audit") is True
        assert guard.is_blocked() is False

    def test_12_recovery_mode_blocks_new_trades(self):
        from titan.production.fail_closed_runtime_guard import FailClosedRuntimeGuard
        t0 = time.time()
        guard = FailClosedRuntimeGuard(clock=lambda: t0)
        guard.set_recovery_mode(True, reason="runtime unhealthy")
        assert guard.is_blocked() is True
        # allow_new_trades must be refused while in recovery.
        assert guard.allow_new_trades() is False
        # Clear recovery, then allow.
        guard.set_recovery_mode(False)
        assert guard.allow_new_trades() is True
        assert guard.is_blocked() is False


class TestWatchdogRestarterResilience:
    def test_13_orphan_detection_no_orphans(self):
        from titan.production.watchdog_restarter import WatchdogRestarter
        wr = WatchdogRestarter(
            dry_run=True, positions_provider=lambda: [],
        )
        rep = wr.check_orphan_positions()
        assert rep.has_orphans is False
        assert rep.orphan_count == 0

    def test_14_orphan_detection_with_orphans_sets_fail_closed(self):
        from titan.production.watchdog_restarter import WatchdogRestarter
        from titan.production.fail_closed_runtime_guard import FailClosedRuntimeGuard
        positions = [{"ticket": 1, "magic": 4242, "volume": 0.1}]
        fcrg = FailClosedRuntimeGuard()
        wr = WatchdogRestarter(
            dry_run=True,
            positions_provider=lambda: positions,
            fail_closed_guard=fcrg,
        )
        rep = wr.check_orphan_positions(magic_filter=4242)
        assert rep.has_orphans is True
        assert rep.orphan_count == 1
        # FailClosedRuntimeGuard should now be blocked (recovery mode mirrored).
        assert fcrg.is_blocked() is True

    def test_15_safe_restart_aborts_with_orphans(self):
        from titan.production.watchdog_restarter import WatchdogRestarter
        positions = [{"ticket": 1, "magic": 4242, "volume": 0.1}]
        wr = WatchdogRestarter(
            dry_run=True, positions_provider=lambda: positions,
        )
        cr = asyncio.run(wr.safe_restart(reason="audit test"))
        assert "ABORTED" in cr.reason
        assert cr.fail_closed is True

    def test_16_safe_restart_dry_run_completes_with_no_orphans(self):
        from titan.production.watchdog_restarter import WatchdogRestarter
        wr = WatchdogRestarter(
            dry_run=True, positions_provider=lambda: [],
        )
        cr = asyncio.run(wr.safe_restart(reason="audit test"))
        assert "DRY_RUN" in cr.reason
        assert cr.fail_closed is True

    def test_17_generate_crash_report_never_claims_never_crash(self, tmp_path):
        from titan.production.watchdog_restarter import WatchdogRestarter
        wr = WatchdogRestarter(
            dry_run=True,
            positions_provider=lambda: [],
            crash_report_dir=tmp_path,
        )
        cr = wr.generate_crash_report(reason="audit test")
        assert cr.fail_closed is True
        assert cr.never_claims_never_crash is True
        assert "fail-closed" in cr.design_note
        assert "recoverable" in cr.design_note
        assert "auditable" in cr.design_note
        # Crash report files should have been written to tmp_path.
        files = list(tmp_path.glob("crash_report_*.json"))
        assert len(files) == 1
        with open(files[0]) as f:
            data = json.load(f)
        assert data["never_claims_never_crash"] is True
        md_files = list(tmp_path.glob("crash_report_*.md"))
        assert len(md_files) == 1
        md = md_files[0].read_text()
        # MD must not contain a positive claim that crashes are impossible.
        # Allowed: "does not claim 'never crash'", "never_claims_never_crash",
        # "never claims 'never crash': true" — i.e., the phrase is being
        # explicitly negated by the surrounding wording.
        forbidden_positive_patterns = [
            r"\bwill never crash\b",
            r"\bnever crashes\b(?!\s*[:\-])",      # but allow "never crashes:" as a key
            r"\bcrash(?:es)? is impossible\b",
            r"\bcrash impossible\b(?!\s+to)",       # but allow "crash impossible to fail"
        ]
        for pat in forbidden_positive_patterns:
            assert not re.search(pat, md, flags=re.IGNORECASE), (
                f"crash report MD makes a false safety claim: {pat}"
            )
        # The MD must explicitly include the fail-closed / recoverable / auditable
        # design note.
        assert "fail-closed" in md.lower()
        assert "recoverable" in md.lower()
        assert "auditable" in md.lower()
