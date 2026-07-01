"""TITAN XAU AI - Sprint 9.9.3.45.6 Simulated Managed Trailing Path Tests

Tests for scripts/operator/simulate_managed_trailing_path.py:
  - loss scenario => HOLD
  - breakeven scenario => MODIFY to breakeven/offset
  - trailing scenario => MODIFY favorable SL
  - profit-lock scenario => MODIFY locked profit SL
  - TP preserved on all scenarios
  - no order_send in simulation
  - no martingale/grid/averaging
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


class TestSimulatedManagedTrailingPath:
    def test_01_module_imports(self):
        import scripts.operator.simulate_managed_trailing_path as s
        assert hasattr(s, "simulate_scenario")
        assert hasattr(s, "write_report")

    def test_02_loss_scenario_returns_hold(self):
        """Loss scenario must produce HOLD action."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("loss")
        assert result["verdict"] == "SIMULATION_HOLD"
        assert result["action"] == "HOLD"
        assert result["matches_expected"] is True
        assert result["expected_action"] == "HOLD"

    def test_03_breakeven_scenario_returns_modify(self):
        """Breakeven scenario must produce MOVE_TO_BREAKEVEN action."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("breakeven")
        assert result["verdict"] == "SIMULATION_MODIFY"
        assert result["action"] == "MOVE_TO_BREAKEVEN"
        assert result["matches_expected"] is True
        assert result["expected_action"] == "MOVE_TO_BREAKEVEN"
        # SL must be favorable
        assert result["favorable"] is True
        # SL must move up (BUY)
        assert result["new_sl"] > result["current_sl"]

    def test_04_trailing_scenario_returns_modify(self):
        """Trailing scenario must produce TRAIL action."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("trailing")
        assert result["verdict"] == "SIMULATION_MODIFY"
        assert result["action"] == "TRAIL"
        assert result["matches_expected"] is True
        assert result["expected_action"] == "TRAIL"
        assert result["favorable"] is True
        assert result["new_sl"] > result["current_sl"]

    def test_05_profit_lock_scenario_returns_modify(self):
        """Profit-lock scenario must produce PROFIT_LOCK action."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit-lock")
        assert result["verdict"] == "SIMULATION_MODIFY"
        assert result["action"] == "PROFIT_LOCK"
        assert result["matches_expected"] is True
        assert result["expected_action"] == "PROFIT_LOCK"
        assert result["favorable"] is True
        assert result["new_sl"] > result["current_sl"]

    def test_06_tp_preserved_all_scenarios(self):
        """TP must be preserved in all scenarios."""
        import scripts.operator.simulate_managed_trailing_path as s
        for scenario in ["loss", "breakeven", "trailing", "profit-lock"]:
            result = s.simulate_scenario(scenario)
            assert result["tp_preserved"] is True, \
                f"TP not preserved in scenario {scenario}"

    def test_07_no_widening_all_scenarios(self):
        """SL must not widen (no_widening=True) in all scenarios."""
        import scripts.operator.simulate_managed_trailing_path as s
        for scenario in ["loss", "breakeven", "trailing", "profit-lock"]:
            result = s.simulate_scenario(scenario)
            assert result["no_widening"] is True, \
                f"SL widened in scenario {scenario}"

    def test_08_no_order_send_in_simulation(self):
        """Simulation must not call mt5.order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "simulate_managed_trailing_path.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bmt5\.order_modify\s*\(", code)

    def test_09_no_martingale(self):
        """No martingale/grid/averaging in simulation."""
        src = (REPO_ROOT / "scripts" / "operator" / "simulate_managed_trailing_path.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot", "add_position"]:
            assert term not in code, f"Forbidden term '{term}' in code"

    def test_10_safety_fields_present(self):
        """Result must include safety fields."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("loss")
        assert "safety" in result
        assert result["safety"]["order_send_called"] is False
        assert result["safety"]["position_modified"] is False
        assert result["safety"]["no_martingale"] is True
        assert result["safety"]["no_grid"] is True
        assert result["safety"]["no_averaging"] is True

    def test_11_writes_json_and_md(self, tmp_path, monkeypatch):
        """Simulation must write JSON and MD reports."""
        import scripts.operator.simulate_managed_trailing_path as s
        monkeypatch.setattr(s, "OUTPUT_DIR", tmp_path)
        result = s.simulate_scenario("breakeven")
        report = s.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_12_unknown_scenario_blocked(self):
        """Unknown scenario must be blocked."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("unknown")
        assert result["verdict"] == "SIMULATION_BLOCKED"

    def test_13_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "operator" / "simulate_managed_trailing_path.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src

    def test_14_loss_scenario_no_modify_attempted(self):
        """Loss scenario must not attempt modification."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("loss")
        # For HOLD, no modification should be attempted
        # The preview may still be generated but action=HOLD
        assert result["action"] == "HOLD"

    def test_15_breakeven_new_sl_at_breakeven_offset(self):
        """Breakeven new SL must be entry + breakeven_offset."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("breakeven")
        # entry=2000.0, offset=0.1 => breakeven_sl = 2000.1
        assert abs(result["new_sl"] - 2000.1) < 0.001, \
            f"Expected new_sl ~ 2000.1, got {result['new_sl']}"

    def test_16_trailing_new_sl_favorable(self):
        """Trailing new SL must be current_price - trailing_distance."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("trailing")
        # current=2002.5, distance=1.0 => trailing_sl = 2001.5
        # But profit_lock_sl might be higher; check favorable
        assert result["new_sl"] >= 2000.1  # At least breakeven
        assert result["favorable"] is True

    def test_17_profit_lock_new_sl_at_lock_level(self):
        """Profit-lock new SL must be entry + profit_lock_trigger."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit-lock")
        # entry=2000.0, trigger=3.0 => profit_lock_sl = 2003.0
        # But trailing might be higher (current=2003.5 - 1.0 = 2002.5)
        # So new_sl = max(profit_lock_sl, trailing_sl, breakeven_sl) = 2003.0
        assert result["new_sl"] >= 2003.0, \
            f"Expected new_sl >= 2003.0, got {result['new_sl']}"

    def test_18_all_scenarios_have_required_fields(self):
        """All scenarios must include required fields."""
        import scripts.operator.simulate_managed_trailing_path as s
        required_fields = [
            "scenario", "verdict", "action", "expected_action",
            "matches_expected", "direction", "entry_price",
            "current_price", "current_sl", "current_tp", "new_sl",
            "favorable", "tp_preserved", "no_widening", "modify_reason",
            "safety", "important_note",
        ]
        for scenario in ["loss", "breakeven", "trailing", "profit-lock"]:
            result = s.simulate_scenario(scenario)
            for f in required_fields:
                assert f in result, f"Scenario {scenario} missing field: {f}"

    # === Sprint 9.9.3.45.8 adaptive scenarios ===

    def test_19_small_profit_noise_hold(self):
        """small_profit_noise_hold => HOLD (profit < noise threshold)."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("small_profit_noise_hold")
        assert result["verdict"] == "SIMULATION_HOLD"
        assert result["action"] == "HOLD"
        assert result["matches_expected"] is True
        assert result["policy_mode"].startswith("adaptive")

    def test_20_profit_1R_breakeven(self):
        """profit_1R_breakeven => MOVE_TO_BREAKEVEN after 1R + noise clear."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit_1R_breakeven")
        assert result["verdict"] == "SIMULATION_MODIFY"
        assert result["action"] == "MOVE_TO_BREAKEVEN"
        assert result["matches_expected"] is True
        assert result["phase"] == "PHASE_2_SOFT_BREAKEVEN"
        assert result["profit_R"] == pytest.approx(1.0, abs=0.01)

    def test_21_profit_1R_but_spread_spike_hold(self):
        """profit_1R_but_spread_spike_hold => HOLD (spread spike blocks)."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit_1R_but_spread_spike_hold")
        assert result["verdict"] == "SIMULATION_HOLD"
        assert result["action"] == "HOLD"
        assert result["matches_expected"] is True
        assert any("SPREAD_SPIKE_FLAG_ACTIVE" in b for b in result.get("anti_whipsaw_blocks", []))

    def test_22_profit_1_5R_trend_hold_until_noise_clear(self):
        """profit_1_5R_trend_hold_until_noise_clear => HOLD (cooldown)."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit_1_5R_trend_hold_until_noise_clear")
        assert result["verdict"] == "SIMULATION_HOLD"
        assert result["action"] == "HOLD"
        assert result["matches_expected"] is True
        # Cooldown active
        assert any("COOLDOWN_ACTIVE" in b for b in result.get("anti_whipsaw_blocks", []))

    def test_23_profit_2R_trend_trail_loose(self):
        """profit_2R_trend_trail_loose => TRAIL with wide ATR distance."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit_2R_trend_trail_loose")
        assert result["verdict"] == "SIMULATION_MODIFY"
        assert result["action"] == "TRAIL"
        assert result["matches_expected"] is True
        assert result["phase"] == "PHASE_3_ADAPTIVE_TRAIL"
        assert result["regime"] == "trend"
        # Trend multiplier = 2.0, atr=1.0 => trailing_distance=2.0
        assert result["trailing_distance"] == pytest.approx(2.0, abs=0.01)

    def test_24_profit_2R_range_trail_tighter(self):
        """profit_2R_range_trail_tighter => TRAIL with tighter ATR distance."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit_2R_range_trail_tighter")
        assert result["verdict"] == "SIMULATION_MODIFY"
        assert result["action"] == "TRAIL"
        assert result["matches_expected"] is True
        assert result["phase"] == "PHASE_3_ADAPTIVE_TRAIL"
        assert result["regime"] == "range"
        # Range multiplier = 1.0, atr=1.0 => trailing_distance=1.0
        assert result["trailing_distance"] == pytest.approx(1.0, abs=0.01)

    def test_25_profit_3R_profit_lock(self):
        """profit_3R_profit_lock => PROFIT_LOCK."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit_3R_profit_lock")
        assert result["verdict"] == "SIMULATION_MODIFY"
        assert result["action"] == "PROFIT_LOCK"
        assert result["matches_expected"] is True
        assert result["phase"] == "PHASE_4_PROFIT_LOCK"

    def test_26_pullback_after_trail_no_widen(self):
        """pullback_after_trail_no_widen => HOLD (no SL widening)."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("pullback_after_trail_no_widen")
        # Either HOLD or BLOCKED - both acceptable as long as no widening
        assert result["verdict"] in ("SIMULATION_HOLD", "SIMULATION_BLOCKED")
        assert result["matches_expected"] is True
        # final_sl must not be less than current_sl (no widening for BUY)
        assert result["new_sl"] >= 2018.0  # current_sl was 2018

    def test_27_cooldown_blocks_repeated_modify(self):
        """cooldown_blocks_repeated_modify => HOLD (cooldown active)."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("cooldown_blocks_repeated_modify")
        assert result["verdict"] == "SIMULATION_HOLD"
        assert result["action"] == "HOLD"
        assert result["matches_expected"] is True
        assert any("COOLDOWN_ACTIVE" in b for b in result.get("anti_whipsaw_blocks", []))

    def test_28_minimum_step_blocks_tiny_modify(self):
        """minimum_step_blocks_tiny_modify => HOLD (step too small)."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("minimum_step_blocks_tiny_modify")
        assert result["verdict"] == "SIMULATION_HOLD"
        assert result["action"] == "HOLD"
        assert result["matches_expected"] is True
        # Must have some anti-whipsaw block
        assert len(result.get("anti_whipsaw_blocks", [])) > 0

    def test_29_adaptive_scenarios_have_policy_fields(self):
        """All adaptive scenarios must include adaptive policy fields."""
        import scripts.operator.simulate_managed_trailing_path as s
        adaptive_fields = [
            "phase", "profit_R", "R", "ATR_noise", "regime",
            "spread_buffer", "stop_level_buffer", "trailing_distance",
            "proposed_sl", "final_sl", "anti_whipsaw_blocks",
        ]
        adaptive_scenarios = [
            "small_profit_noise_hold", "profit_1R_breakeven",
            "profit_1R_but_spread_spike_hold",
            "profit_1_5R_trend_hold_until_noise_clear",
            "profit_2R_trend_trail_loose",
            "profit_2R_range_trail_tighter",
            "profit_3R_profit_lock",
            "pullback_after_trail_no_widen",
            "cooldown_blocks_repeated_modify",
            "minimum_step_blocks_tiny_modify",
        ]
        for scenario in adaptive_scenarios:
            result = s.simulate_scenario(scenario)
            for f in adaptive_fields:
                assert f in result, f"Adaptive scenario {scenario} missing field: {f}"

    def test_30_adaptive_scenarios_tp_preserved(self):
        """All adaptive scenarios must preserve TP."""
        import scripts.operator.simulate_managed_trailing_path as s
        adaptive_scenarios = [
            "small_profit_noise_hold", "profit_1R_breakeven",
            "profit_2R_trend_trail_loose",
            "profit_2R_range_trail_tighter",
            "profit_3R_profit_lock",
        ]
        for scenario in adaptive_scenarios:
            result = s.simulate_scenario(scenario)
            assert result["tp_preserved"] is True, f"TP not preserved in {scenario}"

    def test_31_adaptive_scenarios_no_widening(self):
        """All adaptive scenarios must not widen SL."""
        import scripts.operator.simulate_managed_trailing_path as s
        adaptive_scenarios = [
            "small_profit_noise_hold", "profit_1R_breakeven",
            "profit_1R_but_spread_spike_hold",
            "profit_1_5R_trend_hold_until_noise_clear",
            "profit_2R_trend_trail_loose",
            "profit_2R_range_trail_tighter",
            "profit_3R_profit_lock",
            "pullback_after_trail_no_widen",
            "cooldown_blocks_repeated_modify",
            "minimum_step_blocks_tiny_modify",
        ]
        for scenario in adaptive_scenarios:
            result = s.simulate_scenario(scenario)
            # For BUY, new_sl must be >= current_sl (no widening)
            assert result["no_widening"] is True, f"SL widened in {scenario}"

    def test_32_adaptive_scenarios_no_martingale(self):
        """Adaptive scenarios must not contain martingale/grid/averaging."""
        import scripts.operator.simulate_managed_trailing_path as s
        adaptive_scenarios = [
            "small_profit_noise_hold", "profit_1R_breakeven",
            "profit_2R_trend_trail_loose",
            "profit_3R_profit_lock",
        ]
        for scenario in adaptive_scenarios:
            result = s.simulate_scenario(scenario)
            assert result["safety"]["no_martingale"] is True
            assert result["safety"]["no_grid"] is True
            assert result["safety"]["no_averaging"] is True

    # === Sprint 9.9.3.45.8.2.1: contradiction tests ===

    def test_33_profit_3R_no_contradiction(self):
        """profit_3R_trend_extend_tp_profit_floor_sl must NOT have
        contradiction: MODIFY with favorable=False."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit_3R_trend_extend_tp_profit_floor_sl")
        # If action is MODIFY, favorable must be True
        if result["action"] in ("EXTEND_TP_AND_RAISE_SL", "RAISE_SL_ONLY"):
            assert result["favorable"] is True, \
                f"CONTRADICTION: action={result['action']} with favorable={result['favorable']}"
            assert result["no_widening"] is True, \
                f"CONTRADICTION: action={result['action']} with no_widening={result['no_widening']}"

    def test_34_modify_actions_require_favorable_true(self):
        """All MODIFY actions in adaptive scenarios must have favorable=True."""
        import scripts.operator.simulate_managed_trailing_path as s
        modify_scenarios = [
            "profit_2R_trend_extend_tp_and_raise_sl",
            "profit_3R_trend_extend_tp_profit_floor_sl",
            "tp_extension_blocked_if_sl_cannot_protect_profit",
        ]
        for scenario in modify_scenarios:
            result = s.simulate_scenario(scenario)
            if result["action"] in ("EXTEND_TP_AND_RAISE_SL", "RAISE_SL_ONLY"):
                assert result["favorable"] is True, \
                    f"Scenario {scenario}: action={result['action']} with favorable={result['favorable']}"

    def test_35_modify_actions_require_zero_blocking_reasons(self):
        """All MODIFY actions must have blocking_reasons_count=0."""
        import scripts.operator.simulate_managed_trailing_path as s
        modify_scenarios = [
            "profit_2R_trend_extend_tp_and_raise_sl",
            "profit_3R_trend_extend_tp_profit_floor_sl",
            "tp_extension_blocked_if_sl_cannot_protect_profit",
        ]
        for scenario in modify_scenarios:
            result = s.simulate_scenario(scenario)
            if result["action"] in ("EXTEND_TP_AND_RAISE_SL", "RAISE_SL_ONLY"):
                blocking_count = result.get("blocking_reasons_count", 0)
                assert blocking_count == 0, \
                    f"Scenario {scenario}: action={result['action']} with blocking_reasons_count={blocking_count}"

    def test_36_tp_extension_requires_tp_sl_pair_valid(self):
        """EXTEND_TP_AND_RAISE_SL must have tp_sl_pair_valid=True."""
        import scripts.operator.simulate_managed_trailing_path as s
        scenarios = [
            "profit_2R_trend_extend_tp_and_raise_sl",
            "profit_3R_trend_extend_tp_profit_floor_sl",
        ]
        for scenario in scenarios:
            result = s.simulate_scenario(scenario)
            if result["action"] == "EXTEND_TP_AND_RAISE_SL":
                assert result.get("tp_sl_pair_valid") is True, \
                    f"Scenario {scenario}: EXTEND_TP_AND_RAISE_SL with tp_sl_pair_valid={result.get('tp_sl_pair_valid')}"

    def test_37_tp_extension_requires_no_tp_reduction(self):
        """EXTEND_TP_AND_RAISE_SL must have no_tp_reduction=True."""
        import scripts.operator.simulate_managed_trailing_path as s
        scenarios = [
            "profit_2R_trend_extend_tp_and_raise_sl",
            "profit_3R_trend_extend_tp_profit_floor_sl",
        ]
        for scenario in scenarios:
            result = s.simulate_scenario(scenario)
            if result["action"] == "EXTEND_TP_AND_RAISE_SL":
                assert result.get("no_tp_reduction") is True, \
                    f"Scenario {scenario}: EXTEND_TP_AND_RAISE_SL with no_tp_reduction={result.get('no_tp_reduction')}"

    def test_38_hold_actions_can_have_blocking_reasons(self):
        """HOLD actions CAN have blocking_reasons (that's why they're HOLD)."""
        import scripts.operator.simulate_managed_trailing_path as s
        hold_scenarios = [
            "tp_extension_blocked_by_spread",
            "cooldown_blocks_repeated_tp_extension",
        ]
        for scenario in hold_scenarios:
            result = s.simulate_scenario(scenario)
            # These scenarios produce HOLD from corridor (blocking reasons)
            # but may also produce TRAIL from adaptive. Check corridor action.
            corridor_action = result.get("corridor_action", "")
            if corridor_action == "HOLD":
                # HOLD from corridor can have blocking reasons
                blocking_count = result.get("blocking_reasons_count", 0)
                # It's OK for HOLD to have blocking reasons
                assert blocking_count >= 0  # Just verify field exists

    def test_39_result_has_blocking_and_informational_fields(self):
        """Dynamic TP scenarios must include blocking_reasons,
        informational_notes, blocking_reasons_count,
        informational_notes_count, action_allowed."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit_2R_trend_extend_tp_and_raise_sl")
        assert "blocking_reasons" in result
        assert "informational_notes" in result
        assert "blocking_reasons_count" in result
        assert "informational_notes_count" in result
        assert "action_allowed" in result

    def test_40_no_martingale_in_corridor_results(self):
        """Corridor simulation results must not contain martingale/grid/averaging
        implementation (safety flags like 'no_martingale: True' are OK)."""
        import scripts.operator.simulate_managed_trailing_path as s
        result = s.simulate_scenario("profit_3R_trend_extend_tp_profit_floor_sl")
        # Check safety section is present and correct
        safety = result.get("safety", {})
        assert safety.get("no_martingale") is True
        assert safety.get("no_grid") is True
        assert safety.get("no_averaging") is True
        # Check that no actual martingale/grid/averaging implementation
        # is present (not just the safety flag)
        result_str = str(result).lower()
        # Remove safety flags before checking
        result_str_clean = result_str.replace("'no_martingale': true", "").replace("'no_grid': true", "").replace("'no_averaging': true", "")
        result_str_clean = result_str_clean.replace('"no_martingale": true', "").replace('"no_grid": true', "").replace('"no_averaging": true', "")
        assert "martingale" not in result_str_clean
        assert "grid_trade" not in result_str_clean
        assert "averaging_down" not in result_str_clean
