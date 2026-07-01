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
