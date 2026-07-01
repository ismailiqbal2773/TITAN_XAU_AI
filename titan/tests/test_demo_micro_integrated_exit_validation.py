"""TITAN XAU AI - Sprint 9.9.3.45.8.2 Integrated Exit Validation Tests

Tests for scripts/audit/demo_micro_integrated_exit_validation.py:
  - adaptive iteration propagation correct
  - min iteration/hold clears
  - TP preserve default
  - dynamic TP opt-in exists
  - TP extension paired with SL improvement
  - SL profit floor enforced
  - no TP reduction
  - no SL widening
  - no tick chasing
  - cooldown/hysteresis
  - spread/news freeze blocks
  - monitor lifecycle
  - receipt/forensics strict matching
  - no martingale/grid/averaging
  - no loss-based lot multiplier
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


class TestIntegratedExitValidation:
    def test_01_module_imports(self):
        import scripts.audit.demo_micro_integrated_exit_validation as v
        assert hasattr(v, "run_validation")
        assert hasattr(v, "write_report")

    def test_02_validation_returns_result(self):
        """run_validation must return a result dict."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert "verdict" in result
        assert "findings" in result
        assert "safety" in result

    def test_03_validation_verdicts_supported(self):
        """All 3 verdicts must be supported."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_integrated_exit_validation.py").read_text()
        assert "INTEGRATED_EXIT_VALIDATION_READY" in src
        assert "INTEGRATED_EXIT_VALIDATION_READY_DYNAMIC_TP_OPT_IN" in src
        assert "INTEGRATED_EXIT_VALIDATION_BLOCKED" in src

    def test_04_validation_iteration_propagation(self):
        """Validation must check iteration propagation."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("iteration_propagation") is True

    def test_05_validation_min_iteration_hold_clears(self):
        """Validation must check min iteration/hold clears."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("min_iteration_hold_clears") is True

    def test_06_validation_tp_preserve_default(self):
        """Validation must check TP preserve default."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("tp_preserve_default") is True

    def test_07_validation_dynamic_tp_opt_in(self):
        """Validation must check dynamic TP opt-in exists."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("dynamic_tp_opt_in") is True

    def test_08_validation_tp_sl_paired(self):
        """Validation must check TP extension paired with SL improvement."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("tp_sl_paired") is True

    def test_09_validation_sl_profit_floor(self):
        """Validation must check SL profit floor enforced."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("sl_profit_floor") is True

    def test_10_validation_no_tp_reduction(self):
        """Validation must check no TP reduction."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("no_tp_reduction") is True

    def test_11_validation_no_sl_widening(self):
        """Validation must check no SL widening."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("no_sl_widening") is True

    def test_12_validation_no_tick_chasing(self):
        """Validation must check no tick chasing."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("no_tick_chasing") is True

    def test_13_validation_cooldown_hysteresis(self):
        """Validation must check cooldown/hysteresis."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("cooldown_hysteresis") is True

    def test_14_validation_spread_news_blocks(self):
        """Validation must check spread/news freeze blocks."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("spread_news_blocks") is True

    def test_15_validation_monitor_lifecycle(self):
        """Validation must check monitor lifecycle."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("monitor_lifecycle") is True

    def test_16_validation_receipt_forensics_strict(self):
        """Validation must check receipt/forensics strict matching."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("receipt_forensics_strict") is True

    def test_17_validation_no_martingale(self):
        """Validation must check no martingale/grid/averaging."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("no_martingale_grid_averaging") is True

    def test_18_validation_no_loss_based_lot_multiplier(self):
        """Validation must check no loss-based lot multiplier."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("no_loss_based_lot_multiplier") is True

    def test_19_validation_corridor_module_exists(self):
        """Validation must check corridor module exists."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("corridor_module_exists") is True

    def test_20_validation_paired_builder_exists(self):
        """Validation must check paired builder module exists."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("paired_builder_exists") is True

    def test_21_validation_corridor_scenarios(self):
        """Validation must check corridor scenarios exist."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["findings"].get("corridor_scenarios") is True

    def test_22_validation_returns_dynamic_tp_opt_in_verdict(self):
        """Validation must return DYNAMIC_TP_OPT_IN when all wiring complete."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["verdict"] == "INTEGRATED_EXIT_VALIDATION_READY_DYNAMIC_TP_OPT_IN", \
            f"Expected DYNAMIC_TP_OPT_IN, got {result['verdict']}"

    def test_23_validation_no_order_send(self):
        """Validation script must NOT call mt5.order_send."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_integrated_exit_validation.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bmt5\.order_modify\s*\(", code)

    def test_24_validation_safety_fields(self):
        """Validation result must include safety fields."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        result = v.run_validation()
        assert result["safety"]["order_send_called"] is False
        assert result["safety"]["position_modified"] is False

    def test_25_validation_writes_json_and_md(self, tmp_path, monkeypatch):
        """Validation must write JSON and MD reports."""
        import scripts.audit.demo_micro_integrated_exit_validation as v
        monkeypatch.setattr(v, "OUTPUT_DIR", tmp_path)
        result = v.run_validation()
        report = v.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_26_validation_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_integrated_exit_validation.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src

    # === Sprint 9.9.3.45.8.2.1: contradiction detection tests ===

    def test_27_validation_detects_modify_with_favorable_false(self):
        """Integrated validation must catch MODIFY with favorable=False
        contradiction in simulation results."""
        # Run the profit_3R scenario and verify no contradiction
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit_3R_trend_extend_tp_profit_floor_sl")
        # If action is MODIFY, favorable must be True
        if result["action"] in ("EXTEND_TP_AND_RAISE_SL", "RAISE_SL_ONLY"):
            assert result["favorable"] is True, \
                f"CONTRADICTION: MODIFY action with favorable=False"
        # If action is MODIFY, blocking_reasons_count must be 0
        if result["action"] in ("EXTEND_TP_AND_RAISE_SL", "RAISE_SL_ONLY"):
            assert result.get("blocking_reasons_count", 0) == 0, \
                f"CONTRADICTION: MODIFY action with blocking_reasons_count>0"

    def test_28_validation_detects_modify_with_blocking_reasons(self):
        """Integrated validation must catch MODIFY with blocking reasons."""
        import scripts.operator.simulate_managed_trailing_path as s
        # Test all dynamic TP scenarios
        dynamic_tp_scenarios = [
            "tp_extension_disabled_preserve",
            "profit_2R_trend_extend_tp_and_raise_sl",
            "profit_2R_range_no_tp_extension",
            "profit_3R_trend_extend_tp_profit_floor_sl",
            "tp_extension_blocked_by_spread",
            "tp_extension_blocked_if_sl_cannot_protect_profit",
            "cooldown_blocks_repeated_tp_extension",
            "no_tp_reduction",
            "no_sl_widening",
            "no_tick_chasing",
        ]
        for scenario in dynamic_tp_scenarios:
            result = s.simulate_scenario(scenario)
            if result["action"] in ("EXTEND_TP_AND_RAISE_SL", "RAISE_SL_ONLY"):
                # MODIFY must have favorable=True
                assert result["favorable"] is True, \
                    f"Scenario {scenario}: MODIFY with favorable={result['favorable']}"
                # MODIFY must have blocking_reasons_count=0
                assert result.get("blocking_reasons_count", 0) == 0, \
                    f"Scenario {scenario}: MODIFY with blocking_reasons_count={result.get('blocking_reasons_count')}"

    def test_29_validation_profit_2R_no_contradiction(self):
        """profit_2R_trend_extend_tp_and_raise_sl must not have contradiction."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit_2R_trend_extend_tp_and_raise_sl")
        assert result["action"] == "EXTEND_TP_AND_RAISE_SL"
        assert result["favorable"] is True
        assert result.get("blocking_reasons_count", 0) == 0
        assert result.get("tp_sl_pair_valid") is True
        assert result.get("no_tp_reduction") is True

    def test_30_validation_raise_sl_only_no_contradiction(self):
        """tp_extension_blocked_if_sl_cannot_protect_profit (RAISE_SL_ONLY)
        must not have contradiction."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("tp_extension_blocked_if_sl_cannot_protect_profit")
        assert result["action"] == "RAISE_SL_ONLY"
        assert result["favorable"] is True
        assert result.get("blocking_reasons_count", 0) == 0
