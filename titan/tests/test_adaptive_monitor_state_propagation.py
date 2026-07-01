"""TITAN XAU AI - Sprint 9.9.3.45.8.2 Adaptive Monitor State Propagation Tests

Tests that the orchestrator correctly propagates actual monitor_iterations
to the adaptive policy (fixes stale monitor_iterations=1 bug).

Bug context:
  Before this sprint, _run_monitor_loop constructed a fresh
  ManagedTradeOrchestrator per iteration, causing self._monitor_iterations
  to reset to 0 each time and get incremented to 1 inside
  evaluate_single_step. The adaptive policy then saw monitor_iterations=1
  on every iteration, so Phase 0 (min_monitor_iterations=3) never cleared.

Fix:
  evaluate_single_step and monitor_position now accept explicit
  monitor_iterations, hold_seconds, seconds_since_last_modify parameters
  that override the internal tracker state.
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.demo_micro_managed_trade_orchestrator import ManagedTradeOrchestrator
from titan.production.adaptive_trailing_policy import Regime, PolicyAction


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class TestAdaptiveMonitorStatePropagation:
    def test_01_orchestrator_accepts_explicit_monitor_iterations(self):
        """evaluate_single_step must accept monitor_iterations parameter."""
        orch = ManagedTradeOrchestrator(use_adaptive_policy=True)
        # Pass monitor_iterations=5 explicitly
        rec, event = orch.evaluate_single_step(
            position_ticket=12345, direction="BUY",
            entry_price=2000.0, current_sl=1990.0, current_tp=2020.0,
            current_price=2010.0, is_open=True,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
        )
        # event should record actual_monitor_iteration=5
        assert event.actual_monitor_iteration == 5
        assert event.policy_monitor_iteration == 5

    def test_02_orchestrator_accepts_explicit_hold_seconds(self):
        """evaluate_single_step must accept hold_seconds parameter."""
        orch = ManagedTradeOrchestrator(use_adaptive_policy=True)
        rec, event = orch.evaluate_single_step(
            position_ticket=12345, direction="BUY",
            entry_price=2000.0, current_sl=1990.0, current_tp=2020.0,
            current_price=2010.0, is_open=True,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
        )
        assert event.hold_seconds == 120

    def test_03_iteration_sequence_1_to_5(self):
        """5 iterations must show policy iteration sequence 1,2,3,4,5,
        not always 1."""
        orch = ManagedTradeOrchestrator(use_adaptive_policy=True)
        iterations = []
        for i in range(1, 6):
            rec, event = orch.evaluate_single_step(
                position_ticket=12345, direction="BUY",
                entry_price=2000.0, current_sl=1990.0, current_tp=2020.0,
                current_price=2001.0,  # profit_R=0.1, HOLD territory
                is_open=True,
                atr=1.0, spread=0.05, regime=Regime.TREND,
                hold_seconds=i * 10, monitor_iterations=i,
                seconds_since_last_modify=999,
            )
            iterations.append(event.actual_monitor_iteration)
        assert iterations == [1, 2, 3, 4, 5], \
            f"Expected [1, 2, 3, 4, 5], got {iterations}"

    def test_04_phase_0_clears_after_min_iterations(self):
        """Phase 0 must clear after monitor_iterations >= min (3)."""
        orch = ManagedTradeOrchestrator(use_adaptive_policy=True)
        # Iteration 2: still Phase 0
        rec2, event2 = orch.evaluate_single_step(
            position_ticket=12345, direction="BUY",
            entry_price=2000.0, current_sl=1990.0, current_tp=2020.0,
            current_price=2010.0,  # profit_R=1.0
            is_open=True,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            hold_seconds=120, monitor_iterations=2,  # Below min=3
            seconds_since_last_modify=999,
        )
        assert event2.phase == "PHASE_0_INITIAL_PROTECTION"

        # Iteration 3: Phase 0 clears, moves to Phase 2 (breakeven)
        rec3, event3 = orch.evaluate_single_step(
            position_ticket=12345, direction="BUY",
            entry_price=2000.0, current_sl=1990.0, current_tp=2020.0,
            current_price=2010.0,  # profit_R=1.0
            is_open=True,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            hold_seconds=120, monitor_iterations=3,  # Meets min=3
            seconds_since_last_modify=999,
        )
        assert event3.phase != "PHASE_0_INITIAL_PROTECTION", \
            f"Phase 0 should clear at iteration 3, got {event3.phase}"

    def test_05_phase_0_clears_after_min_hold_seconds(self):
        """Phase 0 must clear after hold_seconds >= min (60)."""
        orch = ManagedTradeOrchestrator(use_adaptive_policy=True)
        # hold_seconds=30: still Phase 0
        rec30, event30 = orch.evaluate_single_step(
            position_ticket=12345, direction="BUY",
            entry_price=2000.0, current_sl=1990.0, current_tp=2020.0,
            current_price=2010.0,  # profit_R=1.0
            is_open=True,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            hold_seconds=30,  # Below min=60
            monitor_iterations=5,
            seconds_since_last_modify=999,
        )
        assert event30.phase == "PHASE_0_INITIAL_PROTECTION"

        # hold_seconds=60: Phase 0 clears
        rec60, event60 = orch.evaluate_single_step(
            position_ticket=12345, direction="BUY",
            entry_price=2000.0, current_sl=1990.0, current_tp=2020.0,
            current_price=2010.0,  # profit_R=1.0
            is_open=True,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            hold_seconds=60,  # Meets min=60
            monitor_iterations=5,
            seconds_since_last_modify=999,
        )
        assert event60.phase != "PHASE_0_INITIAL_PROTECTION", \
            f"Phase 0 should clear at hold_seconds=60, got {event60.phase}"

    def test_06_stale_iteration_bug_cannot_recur(self):
        """Stale monitor_iterations=1 bug must not recur.

        Construct fresh orchestrators per call (simulating _run_monitor_loop
        behavior) and verify explicit monitor_iterations param overrides
        internal state.
        """
        for i in range(1, 6):
            # Fresh orchestrator each iteration (like _run_monitor_loop does)
            orch = ManagedTradeOrchestrator(use_adaptive_policy=True)
            rec, event = orch.evaluate_single_step(
                position_ticket=12345, direction="BUY",
                entry_price=2000.0, current_sl=1990.0, current_tp=2020.0,
                current_price=2010.0,  # profit_R=1.0
                is_open=True,
                atr=1.0, spread=0.05, regime=Regime.TREND,
                hold_seconds=120, monitor_iterations=i,  # Explicit
                seconds_since_last_modify=999,
            )
            assert event.actual_monitor_iteration == i, \
                f"Expected iteration {i}, got {event.actual_monitor_iteration} (stale bug?)"

    def test_07_monitor_position_accepts_explicit_iterations(self):
        """monitor_position must accept monitor_iterations parameter."""
        orch = ManagedTradeOrchestrator(use_adaptive_policy=True)
        result = orch.monitor_position(
            position_ticket=12345, direction="BUY",
            entry_price=2000.0, current_sl=1990.0, current_tp=2020.0,
            current_price=2010.0, is_open=True,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
        )
        # Verify event recorded correct iteration
        if result.monitor_events:
            last_event = result.monitor_events[-1]
            assert last_event.get("actual_monitor_iteration") == 5 or \
                   last_event.get("policy_monitor_iteration") == 5

    def test_08_monitor_position_hold_seconds_passed(self):
        """monitor_position must pass hold_seconds to policy."""
        orch = ManagedTradeOrchestrator(use_adaptive_policy=True)
        result = orch.monitor_position(
            position_ticket=12345, direction="BUY",
            entry_price=2000.0, current_sl=1990.0, current_tp=2020.0,
            current_price=2010.0, is_open=True,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            hold_seconds=120, monitor_iterations=5,
            seconds_since_last_modify=999,
        )
        if result.monitor_events:
            last_event = result.monitor_events[-1]
            assert last_event.get("hold_seconds") == 120

    def test_09_event_includes_adaptive_state_fields(self):
        """MonitorEvent must include adaptive state fields."""
        from titan.production.demo_micro_managed_trade_orchestrator import MonitorEvent
        # Check dataclass fields
        import dataclasses
        fields = {f.name for f in dataclasses.fields(MonitorEvent)}
        assert "actual_monitor_iteration" in fields
        assert "policy_monitor_iteration" in fields
        assert "hold_seconds" in fields
        assert "phase" in fields
        assert "profit_R" in fields

    def test_10_run_managed_passes_actual_iterations_to_orchestrator(self):
        """_run_monitor_loop must pass actual monitor_iterations to
        orchestrator.monitor_position()."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Find _run_monitor_loop body
        idx = src.find("def _run_monitor_loop")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        # Must pass monitor_iterations=monitor_iterations to monitor_position
        assert "monitor_iterations=monitor_iterations" in body
        assert "hold_seconds=actual_hold_seconds" in body

    def test_11_no_stale_phase_0_on_iteration_5(self):
        """On iteration 5 with hold_seconds=100, Phase 0 must NOT trigger."""
        orch = ManagedTradeOrchestrator(use_adaptive_policy=True)
        rec, event = orch.evaluate_single_step(
            position_ticket=12345, direction="BUY",
            entry_price=2000.0, current_sl=1990.0, current_tp=2020.0,
            current_price=2001.0,  # profit_R=0.1, below breakeven
            is_open=True,
            atr=1.0, spread=0.05, regime=Regime.TREND,
            hold_seconds=100, monitor_iterations=5,
            seconds_since_last_modify=999,
        )
        # Should be Phase 1 (noise filter), NOT Phase 0
        assert event.phase != "PHASE_0_INITIAL_PROTECTION", \
            f"Phase 0 should not trigger at iteration 5, got {event.phase}"
        assert event.phase == "PHASE_1_NOISE_FILTER"

    def test_12_no_martingale_in_state_propagation(self):
        """State propagation must NOT add martingale/grid/averaging."""
        src = (REPO_ROOT / "titan" / "production" / "demo_micro_managed_trade_orchestrator.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot"]:
            assert term not in code, f"Forbidden term '{term}' in orchestrator"

    def test_13_no_loss_based_lot_multiplier(self):
        """State propagation must NOT use loss-based lot multiplier."""
        src = (REPO_ROOT / "titan" / "production" / "demo_micro_managed_trade_orchestrator.py").read_text()
        code = _strip(src).lower()
        assert "loss_based_lot" not in code
        assert "double_after_loss" not in code
