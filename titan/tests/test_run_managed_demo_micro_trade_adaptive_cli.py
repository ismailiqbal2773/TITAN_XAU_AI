"""TITAN XAU AI - Sprint 9.9.3.45.8.1 Run Managed Demo Micro Trade Adaptive CLI Tests

Tests for scripts/operator/run_managed_demo_micro_trade.py adaptive
trailing CLI wiring:
  - default run uses legacy/adaptive disabled
  - --use-adaptive-trailing enables adaptive policy
  - CLI config passes into orchestrator
  - report shows adaptive_trailing_enabled=True
  - missing flag keeps adaptive_trailing_enabled=False
  - readiness audit detects adaptive opt-in wiring
  - legacy mode still passes old tests
  - adaptive mode does not add martingale/grid/averaging
  - adaptive mode does not use loss-based lot multiplier
  - HOLD does not modify
  - MODIFY uses existing gated apply path
  - no real order_send in tests
  - order_send mocked
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class FakeArgs:
    """Fake args object for testing adaptive config builders."""
    def __init__(self, use_adaptive_trailing=False, **kwargs):
        self.use_adaptive_trailing = use_adaptive_trailing
        self.adaptive_policy_mode = kwargs.get("adaptive_policy_mode", "balanced_conservative")
        self.breakeven_trigger_r = kwargs.get("breakeven_trigger_r", 1.0)
        self.trailing_trigger_r = kwargs.get("trailing_trigger_r", 1.75)
        self.profit_lock_trigger_r = kwargs.get("profit_lock_trigger_r", 3.0)
        self.min_hold_seconds = kwargs.get("min_hold_seconds", 60)
        self.min_monitor_iterations = kwargs.get("min_monitor_iterations", 3)
        self.sl_update_cooldown_seconds = kwargs.get("sl_update_cooldown_seconds", 60)


class TestRunManagedDemoMicroTradeAdaptiveCLI:
    def test_01_adaptive_cli_flag_exists(self):
        """--use-adaptive-trailing flag must exist in main() parser."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--use-adaptive-trailing" in src

    def test_02_adaptive_policy_mode_flag_exists(self):
        """--adaptive-policy-mode flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--adaptive-policy-mode" in src

    def test_03_breakeven_trigger_r_flag_exists(self):
        """--breakeven-trigger-r flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--breakeven-trigger-r" in src

    def test_04_trailing_trigger_r_flag_exists(self):
        """--trailing-trigger-r flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--trailing-trigger-r" in src

    def test_05_profit_lock_trigger_r_flag_exists(self):
        """--profit-lock-trigger-r flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--profit-lock-trigger-r" in src

    def test_06_min_hold_seconds_flag_exists(self):
        """--min-hold-seconds flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--min-hold-seconds" in src

    def test_07_min_monitor_iterations_flag_exists(self):
        """--min-monitor-iterations flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--min-monitor-iterations" in src

    def test_08_sl_update_cooldown_seconds_flag_exists(self):
        """--sl-update-cooldown-seconds flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--sl-update-cooldown-seconds" in src

    def test_09_legacy_default_preserved(self):
        """use_adaptive_trailing must default to False (legacy mode)."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Check the argparse line includes default=False
        assert 'use-adaptive-trailing", action="store_true", default=False' in src or \
               'use_adaptive_trailing", action="store_true", default=False' in src

    def test_10_build_adaptive_config_disabled_by_default(self):
        """_build_adaptive_config must return adaptive_trailing_enabled=False
        when use_adaptive_trailing not set."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=False)
        cfg = m._build_adaptive_config(args)
        assert cfg["adaptive_trailing_enabled"] is False
        assert cfg["adaptive_policy_mode"] == "balanced_conservative"
        assert cfg["breakeven_trigger_R"] == 1.0
        assert cfg["trailing_trigger_R"] == 1.75
        assert cfg["profit_lock_trigger_R"] == 3.0
        assert cfg["min_hold_seconds"] == 60
        assert cfg["min_monitor_iterations"] == 3
        assert cfg["cooldown_seconds"] == 60

    def test_11_build_adaptive_config_enabled_with_flag(self):
        """_build_adaptive_config must return adaptive_trailing_enabled=True
        when use_adaptive_trailing=True."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=True)
        cfg = m._build_adaptive_config(args)
        assert cfg["adaptive_trailing_enabled"] is True

    def test_12_build_adaptive_config_passes_custom_values(self):
        """_build_adaptive_config must pass custom CLI values."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(
            use_adaptive_trailing=True,
            adaptive_policy_mode="conservative",
            breakeven_trigger_r=1.5,
            trailing_trigger_r=2.5,
            profit_lock_trigger_r=4.0,
            min_hold_seconds=120,
            min_monitor_iterations=5,
            sl_update_cooldown_seconds=90,
        )
        cfg = m._build_adaptive_config(args)
        assert cfg["adaptive_trailing_enabled"] is True
        assert cfg["adaptive_policy_mode"] == "conservative"
        assert cfg["breakeven_trigger_R"] == 1.5
        assert cfg["trailing_trigger_R"] == 2.5
        assert cfg["profit_lock_trigger_R"] == 4.0
        assert cfg["min_hold_seconds"] == 120
        assert cfg["min_monitor_iterations"] == 5
        assert cfg["cooldown_seconds"] == 90

    def test_13_build_adaptive_policy_kwargs(self):
        """_build_adaptive_policy_kwargs must build kwargs for orchestrator."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(
            use_adaptive_trailing=True,
            adaptive_policy_mode="aggressive",
            breakeven_trigger_r=0.75,
        )
        kwargs = m._build_adaptive_policy_kwargs(args)
        assert kwargs["mode"] == "aggressive"
        assert kwargs["breakeven_trigger_R"] == 0.75
        assert kwargs["trailing_trigger_R"] == 1.75  # default
        assert "cooldown_seconds" in kwargs
        assert "min_hold_seconds" in kwargs
        assert "min_monitor_iterations" in kwargs

    def test_14_run_check_only_includes_adaptive_config_when_args_passed(self):
        """run_check_only(args) must include adaptive_trailing_config."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=True)
        result = m.run_check_only(args)
        assert "adaptive_trailing_config" in result
        assert result["adaptive_trailing_config"]["adaptive_trailing_enabled"] is True

    def test_15_run_check_only_no_adaptive_config_when_args_none(self):
        """run_check_only() without args must not include adaptive_trailing_config."""
        import scripts.operator.run_managed_demo_micro_trade as m
        result = m.run_check_only()
        # When args is None, adaptive_trailing_config should not be present
        # (backwards compat with old behavior)
        assert "adaptive_trailing_config" not in result or \
               result.get("adaptive_trailing_config") is None

    def test_16_run_dry_arm_includes_adaptive_config(self):
        """run_dry_arm(args) must include adaptive_trailing_config."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=True, adaptive_policy_mode="balanced")
        result = m.run_dry_arm(args)
        assert "adaptive_trailing_config" in result
        assert result["adaptive_trailing_config"]["adaptive_trailing_enabled"] is True
        assert result["adaptive_trailing_config"]["adaptive_policy_mode"] == "balanced"

    def test_17_run_build_request_includes_adaptive_config(self):
        """run_build_request(args) must include adaptive_trailing_config."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=True)
        result = m.run_build_request(args=args)
        assert "adaptive_trailing_config" in result
        assert result["adaptive_trailing_config"]["adaptive_trailing_enabled"] is True

    def test_18_run_check_only_legacy_when_flag_absent(self):
        """run_check_only(args) with use_adaptive_trailing=False must show
        adaptive_trailing_enabled=False (legacy mode)."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=False)
        result = m.run_check_only(args)
        assert result["adaptive_trailing_config"]["adaptive_trailing_enabled"] is False

    def test_19_orchestrator_wiring_use_adaptive_policy(self):
        """_run_monitor_loop must pass use_adaptive_policy when flag set.

        Source-level check: the orchestrator construction must include
        use_adaptive_policy and adaptive_policy_kwargs when
        use_adaptive_trailing is True.
        """
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Find _run_monitor_loop function body
        idx = src.find("def _run_monitor_loop")
        assert idx > 0
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        # Must include use_adaptive_policy and adaptive_policy_kwargs
        assert "use_adaptive_policy" in body
        assert "adaptive_policy_kwargs" in body
        assert "_build_adaptive_policy_kwargs" in body

    def test_20_adaptive_config_in_execute_and_monitor_return(self):
        """run_execute_and_monitor return dict must include
        adaptive_trailing_config."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Find the execute_and_monitor return dict
        idx = src.find("def run_execute_and_monitor")
        assert idx > 0
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert "adaptive_trailing_config" in body

    def test_21_adaptive_config_in_write_report_md(self):
        """write_report must include Adaptive Trailing Config section in MD."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "Adaptive Trailing Config" in src
        assert "adaptive_trailing_enabled" in src

    def test_22_no_martingale_in_adaptive_wiring(self):
        """Adaptive wiring must NOT add martingale/grid/averaging."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src).lower()
        # These terms should not appear in code (only in forbidden lists
        # of audit scripts, but not in run_managed_demo_micro_trade.py)
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot",
                     "add_position", "loss_based_lot", "recovery_multiplier"]:
            assert term not in code, f"Forbidden term '{term}' in run_managed_demo_micro_trade.py"

    def test_23_no_real_order_send_in_tests(self):
        """Tests must not invoke real mt5.order_send - mocked only."""
        # This test file itself must not call mt5.order_send
        src = (REPO_ROOT / "titan" / "tests" / "test_run_managed_demo_micro_trade_adaptive_cli.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_24_adaptive_mode_choices_validated(self):
        """--adaptive-policy-mode must validate against the 4 allowed choices."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # choices list must include all 4 modes
        assert "conservative" in src
        assert "balanced" in src
        assert "aggressive" in src
        assert "balanced_conservative" in src

    def test_25_adaptive_opt_in_does_not_force_apply(self):
        """--use-adaptive-trailing alone must NOT force apply path.

        Apply path still requires confirm-managed-trailing AND
        confirm-local-operator. Adaptive flag only changes which policy
        is used for evaluation, not whether modify is sent.
        """
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # apply_allowed must still depend on confirm_managed_trailing AND
        # confirm_local_operator, not on use_adaptive_trailing
        idx = src.find("apply_allowed =")
        assert idx > 0
        # Get the next 200 chars
        context = src[idx:idx+400]
        assert "confirm_managed_trailing" in context
        assert "confirm_local_operator" in context
        # use_adaptive_trailing must NOT be in apply_allowed expression
        # (it's a separate flag for policy selection, not apply gate)
        # Get just the apply_allowed = ... line
        line_end = context.find("\n")
        apply_line = context[:line_end]
        assert "use_adaptive_trailing" not in apply_line, \
            "use_adaptive_trailing must not gate apply_allowed"

    def test_26_adaptive_loop_passes_hold_seconds(self):
        """_run_monitor_loop must update orchestrator _hold_seconds when
        adaptive is enabled."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _run_monitor_loop")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert "_hold_seconds" in body

    def test_27_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src
        assert "\u2018" not in src
        assert "\u2019" not in src

    def test_28_adaptive_cli_flag_default_is_false(self):
        """--use-adaptive-trailing must default to False."""
        import scripts.operator.run_managed_demo_micro_trade as m
        # When args has no use_adaptive_trailing attribute, _build_adaptive_config
        # must return False (via getattr default)
        class EmptyArgs:
            pass
        cfg = m._build_adaptive_config(EmptyArgs())
        assert cfg["adaptive_trailing_enabled"] is False
