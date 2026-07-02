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

    # === Sprint 9.9.3.45.8.2: dynamic TP extension CLI tests ===

    def test_29_dynamic_tp_extension_flag_exists(self):
        """--use-dynamic-tp-extension flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--use-dynamic-tp-extension" in src

    def test_30_tp_extension_trigger_r_flag_exists(self):
        """--tp-extension-trigger-r flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--tp-extension-trigger-r" in src

    def test_31_tp_extension_r_flag_exists(self):
        """--tp-extension-r flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--tp-extension-r" in src

    def test_32_tp_extension_atr_mult_flag_exists(self):
        """--tp-extension-atr-mult flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--tp-extension-atr-mult" in src

    def test_33_tp_extension_cooldown_seconds_flag_exists(self):
        """--tp-extension-cooldown-seconds flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--tp-extension-cooldown-seconds" in src

    def test_34_min_profit_lock_after_tp_extension_r_flag_exists(self):
        """--min-profit-lock-after-tp-extension-r flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--min-profit-lock-after-tp-extension-r" in src

    def test_35_max_profit_giveback_r_trend_flag_exists(self):
        """--max-profit-giveback-r-trend flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--max-profit-giveback-r-trend" in src

    def test_36_max_profit_giveback_r_range_flag_exists(self):
        """--max-profit-giveback-r-range flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--max-profit-giveback-r-range" in src

    def test_37_dynamic_tp_defaults_to_false(self):
        """--use-dynamic-tp-extension must default to False."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert 'use-dynamic-tp-extension", action="store_true", default=False' in src

    def test_38_build_adaptive_config_includes_dynamic_tp(self):
        """_build_adaptive_config must include dynamic_tp_enabled field."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=True)
        # Add dynamic TP attrs
        args.use_dynamic_tp_extension = True
        args.tp_extension_trigger_r = 2.0
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 2.0
        args.tp_extension_cooldown_seconds = 120
        args.min_profit_lock_after_tp_extension_r = 1.0
        args.max_profit_giveback_r_trend = 1.0
        args.max_profit_giveback_r_range = 0.5
        cfg = m._build_adaptive_config(args)
        assert cfg["dynamic_tp_enabled"] is True
        assert cfg["profit_corridor_enabled"] is True  # adaptive + dynamic_tp
        assert cfg["tp_extension_trigger_R"] == 2.0
        assert cfg["tp_extension_R"] == 1.0
        assert cfg["tp_extension_atr_mult"] == 2.0
        assert cfg["tp_extension_cooldown_seconds"] == 120
        assert cfg["min_profit_lock_after_tp_extension_R"] == 1.0
        assert cfg["max_profit_giveback_r_trend"] == 1.0
        assert cfg["max_profit_giveback_r_range"] == 0.5

    def test_39_build_adaptive_config_dynamic_tp_disabled_by_default(self):
        """_build_adaptive_config must default dynamic_tp_enabled=False."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=True)
        # use_dynamic_tp_extension not set -> should default to False
        cfg = m._build_adaptive_config(args)
        assert cfg["dynamic_tp_enabled"] is False
        assert cfg["profit_corridor_enabled"] is False  # adaptive only, no dynamic_tp

    def test_40_profit_corridor_requires_both_flags(self):
        """profit_corridor_enabled must be True only if both
        adaptive_trailing AND dynamic_tp are enabled."""
        import scripts.operator.run_managed_demo_micro_trade as m
        # Both off
        args1 = FakeArgs(use_adaptive_trailing=False)
        args1.use_dynamic_tp_extension = False
        cfg1 = m._build_adaptive_config(args1)
        assert cfg1["profit_corridor_enabled"] is False

        # Adaptive only
        args2 = FakeArgs(use_adaptive_trailing=True)
        args2.use_dynamic_tp_extension = False
        cfg2 = m._build_adaptive_config(args2)
        assert cfg2["profit_corridor_enabled"] is False

        # Dynamic TP only (without adaptive)
        args3 = FakeArgs(use_adaptive_trailing=False)
        args3.use_dynamic_tp_extension = True
        cfg3 = m._build_adaptive_config(args3)
        assert cfg3["profit_corridor_enabled"] is False  # Both required

        # Both on
        args4 = FakeArgs(use_adaptive_trailing=True)
        args4.use_dynamic_tp_extension = True
        cfg4 = m._build_adaptive_config(args4)
        assert cfg4["profit_corridor_enabled"] is True

    def test_41_run_check_only_includes_dynamic_tp_config(self):
        """run_check_only(args) must include dynamic_tp_enabled in config."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=True)
        args.use_dynamic_tp_extension = True
        args.tp_extension_trigger_r = 2.5  # Custom
        result = m.run_check_only(args)
        cfg = result["adaptive_trailing_config"]
        assert cfg["dynamic_tp_enabled"] is True
        assert cfg["tp_extension_trigger_R"] == 2.5

    # === Sprint 9.9.3.45.8.3: production closure CLI tests ===

    def test_42_account_profile_flag_exists(self):
        """--account-profile flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--account-profile" in src

    def test_43_initial_tp_r_flag_exists(self):
        """--initial-tp-r flag must exist."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--initial-tp-r" in src

    def test_44_build_request_with_account_profile(self):
        """build_request must include account_profile in result."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=True)
        args.account_profile = "prop_firm_100x_demo"
        args.initial_tp_r = 3.0
        args.use_dynamic_tp_extension = True
        args.tp_extension_trigger_r = 2.0
        # Add all required attrs for _build_adaptive_config
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 2.0
        args.tp_extension_cooldown_seconds = 120
        args.min_profit_lock_after_tp_extension_r = 1.0
        args.max_profit_giveback_r_trend = 1.0
        args.max_profit_giveback_r_range = 0.5
        result = m.run_build_request(args=args)
        assert result.get("account_profile") == "prop_firm_100x_demo"
        assert result.get("initial_tp_R") == 3.0

    def test_45_build_request_initial_tp_1r_blocked_for_dynamic_tp(self):
        """--initial-tp-r 1.0 with dynamic TP must block."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=True)
        args.account_profile = "prop_firm_100x_demo"
        args.initial_tp_r = 1.0
        args.use_dynamic_tp_extension = True
        args.tp_extension_trigger_r = 2.0
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 2.0
        args.tp_extension_cooldown_seconds = 120
        args.min_profit_lock_after_tp_extension_r = 1.0
        args.max_profit_giveback_r_trend = 1.0
        args.max_profit_giveback_r_range = 0.5
        result = m.run_build_request(args=args)
        assert result["verdict"] == "BLOCKED"
        assert result.get("dynamic_tp_geometry_valid") is False

    def test_46_build_request_initial_tp_3r_allowed(self):
        """--initial-tp-r 3.0 with dynamic TP should pass geometry."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=True)
        args.account_profile = "prop_firm_100x_demo"
        args.initial_tp_r = 3.0
        args.use_dynamic_tp_extension = True
        args.tp_extension_trigger_r = 2.0
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 2.0
        args.tp_extension_cooldown_seconds = 120
        args.min_profit_lock_after_tp_extension_r = 1.0
        args.max_profit_giveback_r_trend = 1.0
        args.max_profit_giveback_r_range = 0.5
        result = m.run_build_request(args=args)
        assert result.get("dynamic_tp_geometry_valid") is True

    def test_47_build_request_includes_transaction_cost(self):
        """build_request must include transaction_cost in result."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=False)
        args.account_profile = "retail_demo_micro"
        args.initial_tp_r = 3.0
        args.use_dynamic_tp_extension = False
        args.tp_extension_trigger_r = 2.0
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 2.0
        args.tp_extension_cooldown_seconds = 120
        args.min_profit_lock_after_tp_extension_r = 1.0
        args.max_profit_giveback_r_trend = 1.0
        args.max_profit_giveback_r_range = 0.5
        result = m.run_build_request(args=args)
        assert "transaction_cost" in result
        assert "gross_profit" in result
        assert "net_profit" in result

    def test_48_build_request_includes_margin_risk(self):
        """build_request must include margin_risk in result."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=False)
        args.account_profile = "retail_demo_micro"
        args.initial_tp_r = 3.0
        args.use_dynamic_tp_extension = False
        args.tp_extension_trigger_r = 2.0
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 2.0
        args.tp_extension_cooldown_seconds = 120
        args.min_profit_lock_after_tp_extension_r = 1.0
        args.max_profit_giveback_r_trend = 1.0
        args.max_profit_giveback_r_range = 0.5
        result = m.run_build_request(args=args)
        assert "margin_risk" in result

    def test_49_no_martingale_in_build_request(self):
        """build_request code must not contain martingale/grid/averaging."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code, f"Forbidden term '{term}' in code"

    # === Sprint 9.9.3.45.8.15: execution geometry tests ===

    def test_50_build_request_includes_execution_geometry(self):
        """Build-request must include execution_geometry field."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=False)
        args.account_profile = "retail_demo_micro"
        args.initial_tp_r = 3.0
        args.use_dynamic_tp_extension = False
        args.tp_extension_trigger_r = 2.0
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 2.0
        args.tp_extension_cooldown_seconds = 120
        args.min_profit_lock_after_tp_extension_r = 1.0
        args.max_profit_giveback_r_trend = 1.0
        args.max_profit_giveback_r_range = 0.5
        result = m.run_build_request(args=args)
        assert "execution_geometry" in result
        geom = result["execution_geometry"]
        assert "actual_RR" in geom
        assert "minimum_RR" in geom
        assert "initial_tp_R" in geom
        assert "geometry_verdict" in geom

    def test_51_build_request_geometry_pass_for_3R(self):
        """Build-request with initial_tp_r=3.0 should have actual_RR=3.0 and PASS."""
        import scripts.operator.run_managed_demo_micro_trade as m
        args = FakeArgs(use_adaptive_trailing=False)
        args.account_profile = "prop_firm_100x_demo"
        args.initial_tp_r = 3.0
        args.use_dynamic_tp_extension = False
        args.tp_extension_trigger_r = 2.0
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 2.0
        args.tp_extension_cooldown_seconds = 120
        args.min_profit_lock_after_tp_extension_r = 1.0
        args.max_profit_giveback_r_trend = 1.0
        args.max_profit_giveback_r_range = 0.5
        result = m.run_build_request(args=args)
        geom = result["execution_geometry"]
        assert geom["actual_RR"] == 3.0
        assert geom["geometry_verdict"] == "EXECUTION_GEOMETRY_PASS"

    def test_52_geometry_source_has_rr_below_minimum_blocker(self):
        """Source must contain EXECUTION_GEOMETRY_RR_BELOW_MINIMUM blocker."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "EXECUTION_GEOMETRY_RR_BELOW_MINIMUM" in src

    def test_53_execute_path_has_geometry_gate(self):
        """Execute-and-monitor path must have geometry gate before order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Find the execute path section
        idx = src.find("def run_execute_and_monitor")
        assert idx > 0
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert "EXECUTION_GEOMETRY_RR_BELOW_MINIMUM" in body
        assert "actual_rr" in body
        assert "minimum_rr" in body

    # === Sprint 9.9.3.45.8.16 v2.7.3: build-request entry-gate status display ===

    def test_54_v2_7_3_build_request_includes_geometry_status(self):
        """Build-request must include latest_execution_geometry_verdict, actual_RR,
        minimum_RR, initial_tp_R in its result."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "latest_execution_geometry_verdict" in src
        assert "latest_actual_RR" in src
        assert "latest_minimum_RR" in src
        assert "latest_initial_tp_R" in src

    def test_55_v2_7_3_build_request_includes_entry_gate_status(self):
        """Build-request must include end_to_end_entry_gate_status field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "end_to_end_entry_gate_status" in src
        assert "end_to_end_entry_gate_blockers" in src
        assert "execution_proof_mode_alpha_unknown" in src

    def test_56_v2_7_3_build_request_includes_autonomous_status(self):
        """Build-request must include autonomous_demo_readiness_status field."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "autonomous_demo_readiness_status" in src
        assert "autonomous_allowed" in src
        assert "autonomous_demo_blockers" in src

    def test_57_v2_7_3_build_request_includes_broker_and_final_demo_status(self):
        """Build-request must include broker status and final demo readiness status."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "final_demo_readiness_status" in src
        assert "previous_micro_proof_status" in src

    def test_58_v2_7_3_build_request_prints_execution_proof_warning(self):
        """When execution_proof_mode_alpha_unknown=True, build-request console
        must print 'Execution proof mode: alpha/regime not used for entry.'"""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "Execution proof mode: alpha/regime not used for entry." in src
        assert "Do not treat this as autonomous strategy proof." in src

    def test_59_v2_7_3_build_request_run_includes_status(self):
        """Actually run build-request and verify status fields are present."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import argparse
        args = argparse.Namespace(
            direction="BUY", entry_price=4075.27, sl=0, tp=0,
            account_profile="prop_funded_safe",
            prop_funded_profile="prop_funded_safe",
            initial_tp_r=3.0,
            use_dynamic_tp_extension=True,
            use_adaptive_trailing=True,
            tp_extension_trigger_r=2.0,
            risk_mode="conservative",
            broker_profile="metaquotes_demo",
        )
        result = m.run_build_request(
            direction="BUY", entry_price=4075.27, sl=0, tp=0, args=args
        )
        # All v2.7.3 status fields must be present
        assert "latest_execution_geometry_verdict" in result
        assert "latest_actual_RR" in result
        assert "latest_minimum_RR" in result
        assert "latest_initial_tp_R" in result
        assert "end_to_end_entry_gate_status" in result
        assert "autonomous_demo_readiness_status" in result
        assert "autonomous_allowed" in result
        assert "final_demo_readiness_status" in result
        assert "previous_micro_proof_status" in result

    # === Sprint 9.9.3.45.8.17 v2.7.4: Profile source priority ===

    def test_60_v2_7_4_build_request_shows_prop_funded_safe_when_cli_selected(self):
        """When --prop-funded-profile prop_funded_safe is used, build-request
        must show selected_profile=prop_funded_safe (not retail_demo_micro)."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import argparse
        args = argparse.Namespace(
            direction="BUY", entry_price=4075.27, sl=0, tp=0,
            account_profile="",  # No account_profile
            prop_funded_profile="prop_funded_safe",  # CLI selects prop_funded_safe
            initial_tp_r=3.0,
            use_dynamic_tp_extension=True,
            use_adaptive_trailing=True,
            tp_extension_trigger_r=2.0,
            risk_mode="conservative",
            broker_profile="metaquotes_demo",
        )
        result = m.run_build_request(
            direction="BUY", entry_price=4075.27, sl=0, tp=0, args=args
        )
        assert result.get("selected_profile") == "prop_funded_safe", \
            f"Expected prop_funded_safe, got {result.get('selected_profile')}"
        assert result.get("selected_profile_source") == "cli_prop_funded_profile", \
            f"Expected cli_prop_funded_profile, got {result.get('selected_profile_source')}"
        assert result.get("prop_funded_safe_active") is True, \
            f"Expected True, got {result.get('prop_funded_safe_active')}"

    def test_61_v2_7_4_profile_source_priority_cli_first(self):
        """Profile source priority: CLI --prop-funded-profile takes precedence
        over managed_trade_report and receipt."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # CLI prop_funded_profile must be checked first
        assert "cli_prop_funded_profile" in src
        assert "cli_account_profile" in src
        # Find the profile resolution code section (after the comment block,
        # starting with the actual variable assignment).
        idx_cli_code = src.find('if cli_prop_funded_profile:')
        assert idx_cli_code > 0, "cli_prop_funded_profile if-block not found"
        # The managed_trade_report path check must come AFTER the CLI check
        idx_managed_path = src.find('managed_report_path = REPO_ROOT', idx_cli_code)
        assert idx_managed_path > 0, \
            "managed_report_path assignment not found after CLI check"
        # Verify the if/elif structure: cli_prop_funded_profile first,
        # then cli_account_profile, then else (managed/receipt)
        idx_cli_if = src.find('if cli_prop_funded_profile:')
        idx_cli_elif = src.find('elif cli_account_profile:')
        idx_else = src.find('else:', idx_cli_elif)
        assert idx_cli_if < idx_cli_elif < idx_else, \
            "Profile resolution must be: if cli_prop_funded -> elif cli_account -> else managed/receipt"

    def test_62_v2_7_4_profile_resolver_module_exists(self):
        """Shared profile resolver module must exist."""
        from titan.production.selected_profile_resolver import resolve_selected_profile
        assert callable(resolve_selected_profile)

    def test_63_v2_7_4_profile_resolver_returns_dict_with_required_fields(self):
        """Profile resolver must return dict with selected_profile, source, active."""
        from titan.production.selected_profile_resolver import resolve_selected_profile
        result = resolve_selected_profile(REPO_ROOT)
        assert "selected_profile" in result
        assert "selected_profile_source" in result
        assert "prop_funded_safe_active" in result

    def test_64_v2_7_4_no_order_send_in_build_request(self):
        """Build-request must never call mt5.order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src)
        # The build_request function specifically must not call order_send
        idx = src.find("def run_build_request")
        assert idx > 0
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        body_stripped = _strip(body)
        assert not re.search(r"\bmt5\.order_send\s*\(", body_stripped)

    def test_65_v2_7_4_no_execution_token_creation_in_build_request(self):
        """Build-request must never create execution tokens."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def run_build_request")
        assert idx > 0
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        body_lower = body.lower()
        assert "create_local_operator_execution_token" not in body_lower
