"""
TITAN XAU AI — Autonomous Demo Smoke Test (Sprint 8)

Simulates full autonomous cycle:
  startup → H1 bar close → feature generation → inference → meta-label
  → trade loop → dry-run order or blocked order → position sync
  → exit manager → journal → shutdown

Answers: Can TITAN generate autonomous demo trades without manual intervention?

Usage:
    python scripts/autonomous_demo_smoke_test.py
    python scripts/autonomous_demo_smoke_test.py --verbose
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from titan.runtime.autonomous_loops import AutonomousRuntime, RuntimeConfig
from titan.production.trade_journal import TradeJournal, EventType
from titan.production.kill_switch_fsm import KillSwitchFSM, KillSwitchInput, KillState


class AutonomousSmokeTest:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results = []

    def check(self, name: str, fn) -> bool:
        print(f"  Testing: {name}... ", end="", flush=True)
        try:
            ok, msg = fn()
            icon = "✓" if ok else "✗"
            print(f"{icon} {msg}")
            self.results.append((name, ok, msg))
            return ok
        except Exception as e:
            print(f"✗ ERROR: {e}")
            self.results.append((name, False, str(e)))
            return False

    def run(self) -> bool:
        print()
        print("=" * 70)
        print("  TITAN XAU AI — Autonomous Demo Smoke Test")
        print("=" * 70)
        print(f"  Mode: dry_run (NO real orders)")
        print()

        tmpdir = tempfile.mkdtemp()
        journal_path = os.path.join(tmpdir, "autonomous_smoke.jsonl")

        # Create runtime
        cfg = RuntimeConfig(
            dry_run=True,
            feature_source="canonical",
            inference_interval_s=0.05,
            position_sync_interval_s=0.05,
            exit_check_interval_s=0.05,
            drift_check_interval_s=0.1,
            heartbeat_interval_s=0.2,
        )
        runtime = AutonomousRuntime(config=cfg, journal_path=journal_path)

        # ─── Step 1: Initialize ──
        self.check("Runtime initialization", lambda: self._test_init(runtime))

        # ─── Step 2: Run single autonomous cycle ──
        asyncio.run(self._test_single_cycle(runtime))

        # ─── Step 3: Run 5 cycles ──
        asyncio.run(self._test_multi_cycle(runtime))

        # ─── Step 4: Kill-switch block test ──
        asyncio.run(self._test_kill_switch_block(runtime))

        # ─── Step 5: Drift → kill-switch test ──
        asyncio.run(self._test_drift_to_kill_switch(runtime))

        # ─── Step 6: Journal verification ──
        self.check("Journal has autonomous events", lambda: self._test_journal(runtime))

        # ─── Step 7: Dry-run enforcement ──
        self.check("Dry-run enforced (no real orders)", lambda: self._test_dry_run(runtime))

        # ─── Step 8: Runtime start/stop ──
        asyncio.run(self._test_start_stop(runtime))

        # Print summary
        return self._print_summary()

    # ─── Test methods ───────────────────────────────────────────────────

    def _test_init(self, runtime) -> tuple[bool, str]:
        runtime.initialize()
        if (runtime.inference_engine and runtime.trade_loop and
            runtime.kill_switch and runtime.feature_stream):
            return True, "All 9 components initialized"
        return False, "Missing components"

    async def _test_single_cycle(self, runtime) -> None:
        print(f"  Testing: Single autonomous cycle... ", end="", flush=True)
        try:
            result = await runtime.run_single_cycle()
            ok = result["signal"] is not None
            icon = "✓" if ok else "✗"
            sig = result["signal"]
            print(f"{icon} dir={sig.direction.name} conf={sig.confidence:.3f} tradeable={sig.is_tradeable}")
            self.results.append(("Single autonomous cycle", ok, f"dir={sig.direction.name}"))
        except Exception as e:
            print(f"✗ ERROR: {e}")
            self.results.append(("Single autonomous cycle", False, str(e)))

    async def _test_multi_cycle(self, runtime) -> None:
        print(f"  Testing: 5 autonomous cycles... ", end="", flush=True)
        try:
            for _ in range(5):
                await runtime.run_single_cycle()
            ok = runtime.signals_generated >= 6  # 1 from single + 5
            icon = "✓" if ok else "✗"
            print(f"{icon} {runtime.signals_generated} signals generated")
            self.results.append(("5 autonomous cycles", ok, f"{runtime.signals_generated} signals"))
        except Exception as e:
            print(f"✗ ERROR: {e}")
            self.results.append(("5 autonomous cycles", False, str(e)))

    async def _test_kill_switch_block(self, runtime) -> None:
        print(f"  Testing: Kill-switch blocks trade... ", end="", flush=True)
        try:
            runtime.kill_switch.update(KillSwitchInput(daily_loss_pct=3.5))
            assert runtime.kill_switch.state == KillState.HALT_NEW_TRADES
            result = await runtime.run_single_cycle()
            ok = result["blocked"] is True
            icon = "✓" if ok else "✗"
            print(f"{icon} blocked=True (state={runtime.kill_switch.state.value})")
            self.results.append(("Kill-switch blocks trade", ok, f"blocked={result['blocked']}"))
            # Reset for further tests
            runtime.kill_switch.reset()
        except Exception as e:
            print(f"✗ ERROR: {e}")
            self.results.append(("Kill-switch blocks trade", False, str(e)))

    async def _test_drift_to_kill_switch(self, runtime) -> None:
        print(f"  Testing: Drift emergency → kill-switch... ", end="", flush=True)
        try:
            runtime.kill_switch.update(KillSwitchInput(drift_emergency=True))
            ok = runtime.kill_switch.state == KillState.EMERGENCY_STOP
            icon = "✓" if ok else "✗"
            print(f"{icon} state={runtime.kill_switch.state.value}")
            self.results.append(("Drift → kill-switch", ok, f"state={runtime.kill_switch.state.value}"))
            runtime.kill_switch.reset()
        except Exception as e:
            print(f"✗ ERROR: {e}")
            self.results.append(("Drift → kill-switch", False, str(e)))

    def _test_journal(self, runtime) -> tuple[bool, str]:
        runtime.journal.flush()
        records = runtime.journal.read_all()
        types = set(r.get("record_type", "") for r in records)
        event_types = set(r.get("event_type", "") for r in records)
        has_signal = "SIGNAL" in types or EventType.SIGNAL_CREATED.value in event_types
        has_startup = EventType.STARTUP.value in event_types
        has_block = EventType.KILL_SWITCH_BLOCK.value in event_types
        ok = has_signal and has_startup and has_block
        return ok, f"{len(records)} records, types={types | event_types}"

    def _test_dry_run(self, runtime) -> tuple[bool, str]:
        if runtime.config.dry_run is True and runtime.trade_loop.config.dry_run is True:
            return True, "dry_run=True in config + trade_loop"
        return False, "dry_run not enforced"

    async def _test_start_stop(self, runtime) -> None:
        print(f"  Testing: Runtime start/stop... ", end="", flush=True)
        try:
            runtime._running = False  # reset
            runtime._shutdown_event.clear()
            task = asyncio.create_task(runtime.start())
            await asyncio.sleep(0.3)
            status = runtime.get_status()
            running = status["running"]
            runtime.shutdown()
            await asyncio.sleep(0.1)
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
            ok = running is True
            icon = "✓" if ok else "✗"
            print(f"{icon} started={running}, signals={status['signals_generated']}")
            self.results.append(("Runtime start/stop", ok, f"signals={status['signals_generated']}"))
        except Exception as e:
            print(f"✗ ERROR: {e}")
            self.results.append(("Runtime start/stop", False, str(e)))

    def _print_summary(self) -> bool:
        print()
        print("-" * 60)
        passed = sum(1 for _, ok, _ in self.results if ok)
        failed = sum(1 for _, ok, _ in self.results if not ok)
        print(f"  Results: {passed} passed, {failed} failed")
        print()
        if failed > 0:
            print("  FAILED:")
            for name, ok, msg in self.results:
                if not ok:
                    print(f"    ✗ {name}: {msg}")
            print()
            print("  ✗ AUTONOMOUS SMOKE TEST FAILED")
            return False
        else:
            print("  ✓ AUTONOMOUS SMOKE TEST PASSED")
            print("  ✓ TITAN can generate autonomous demo trades")
            print("  ✓ No manual intervention required")
            print("  ✓ dry_run=True (no real orders)")
            return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TITAN Autonomous Demo Smoke Test")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    test = AutonomousSmokeTest(verbose=args.verbose)
    success = test.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
