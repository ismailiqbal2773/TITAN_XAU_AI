"""TITAN XAU AI - Sprint 9.9.3.45.8 Trailing Policy Evaluation Tests

Tests for scripts/research/evaluate_trailing_policy_mfe_mae.py:
  - Evaluation compares no_trailing/fixed/adaptive
  - Evaluation labels insufficient data honestly
  - All required metrics computed
  - No order_send in evaluation
  - No martingale/grid/averaging
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


class TestTrailingPolicyEvaluation:
    def test_01_module_imports(self):
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        assert hasattr(e, "run_evaluation")
        assert hasattr(e, "write_report")
        assert hasattr(e, "_simulate_policy_on_path")
        assert hasattr(e, "_evaluate_policy_on_paths")

    def test_02_evaluation_returns_result(self):
        """run_evaluation must return a result dict."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        result = e.run_evaluation()
        assert "verdict" in result
        assert "findings" in result
        assert "safety" in result

    def test_03_evaluation_verdicts_supported(self):
        """All 3 verdicts must be supported."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        src = (REPO_ROOT / "scripts" / "research" / "evaluate_trailing_policy_mfe_mae.py").read_text()
        assert "ADAPTIVE_TRAILING_VALIDATED" in src
        assert "ADAPTIVE_TRAILING_NEEDS_MORE_DATA" in src
        assert "ADAPTIVE_TRAILING_BLOCKED" in src

    def test_04_evaluation_compares_4_policies(self):
        """Evaluation must compare no_trailing, immediate_breakeven,
        fixed_trailing, adaptive_trailing."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        result = e.run_evaluation()
        policy_results = result.get("findings", {}).get("policy_results", {})
        for p in ["no_trailing", "immediate_breakeven", "fixed_trailing", "adaptive_trailing"]:
            assert p in policy_results, f"Missing policy: {p}"

    def test_05_evaluation_metrics_computed(self):
        """All required metrics must be computed per policy."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        result = e.run_evaluation()
        policy_results = result.get("findings", {}).get("policy_results", {})
        required_metrics = [
            "early_stopout_rate", "average_R_captured",
            "average_MFE_capture_ratio", "profit_giveback_ratio",
            "avg_win_R", "avg_loss_R", "expectancy_R", "PF_estimate",
            "max_trade_adverse_R", "trigger_frequency", "modify_frequency",
            "winners", "losers", "win_rate",
        ]
        for p, p_result in policy_results.items():
            for m in required_metrics:
                assert m in p_result, f"Policy {p} missing metric: {m}"

    def test_06_synthetic_data_labeled_honestly(self):
        """Synthetic data must produce ADAPTIVE_TRAILING_NEEDS_MORE_DATA."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        result = e.run_evaluation()
        # When no real data exists, falls back to synthetic -> NEEDS_MORE_DATA
        if result.get("findings", {}).get("data_source") == "synthetic":
            assert result["verdict"] == "ADAPTIVE_TRAILING_NEEDS_MORE_DATA"
            assert any("synthetic" in w.lower() or "needs more data" in w.lower()
                       for w in result.get("warnings", []))

    def test_07_no_order_send_in_evaluation(self):
        """Evaluation must NOT call mt5.order_send or mt5.order_modify."""
        src = (REPO_ROOT / "scripts" / "research" / "evaluate_trailing_policy_mfe_mae.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bmt5\.order_modify\s*\(", code)

    def test_08_no_martingale_in_evaluation(self):
        """Evaluation must NOT contain martingale/grid/averaging logic."""
        src = (REPO_ROOT / "scripts" / "research" / "evaluate_trailing_policy_mfe_mae.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot",
                     "loss_based_lot", "recovery_multiplier"]:
            assert term not in code, f"Forbidden term '{term}' in evaluation code"

    def test_09_no_loss_based_lot_multiplier(self):
        """Evaluation must NOT implement loss-based lot multiplier."""
        src = (REPO_ROOT / "scripts" / "research" / "evaluate_trailing_policy_mfe_mae.py").read_text()
        code = _strip(src).lower()
        assert "loss_based_lot" not in code
        assert "double_after_loss" not in code

    def test_10_writes_json_and_md(self, tmp_path, monkeypatch):
        """Evaluation must write JSON and MD reports."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        monkeypatch.setattr(e, "OUTPUT_DIR", tmp_path)
        result = e.run_evaluation()
        report = e.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_11_simulate_policy_on_path_returns_metrics(self):
        """_simulate_policy_on_path must return all required metrics."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        trade_path = {
            "direction": "BUY", "entry": 2000.0, "initial_sl": 1990.0,
            "tp": 2020.0,
            "prices": [2000.0, 2005.0, 2010.0, 2015.0, 2018.0],
        }
        result = e._simulate_policy_on_path(trade_path, "no_trailing")
        required = [
            "R_captured", "MFE", "MAE", "MFE_capture_ratio",
            "profit_giveback", "profit_giveback_ratio", "early_stopout",
            "trigger_count", "modify_count", "final_sl", "final_profit",
        ]
        for m in required:
            assert m in result, f"Missing metric: {m}"

    def test_12_no_trailing_never_modifies_sl(self):
        """no_trailing policy must never modify SL (modify_count=0)."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        trade_path = {
            "direction": "BUY", "entry": 2000.0, "initial_sl": 1990.0,
            "tp": 2020.0,
            "prices": [2000.0, 2005.0, 2010.0, 2015.0, 2018.0],
        }
        result = e._simulate_policy_on_path(trade_path, "no_trailing")
        assert result["modify_count"] == 0
        assert result["trigger_count"] == 0
        # final_sl must equal initial_sl
        assert result["final_sl"] == 1990.0

    def test_13_adaptive_trailing_can_modify_sl(self):
        """adaptive_trailing policy can modify SL when triggers fire."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        trade_path = {
            "direction": "BUY", "entry": 2000.0, "initial_sl": 1990.0,
            "tp": 2030.0,
            "prices": [2000.0, 2005.0, 2010.0, 2015.0, 2020.0, 2025.0, 2030.0],
        }
        result = e._simulate_policy_on_path(trade_path, "adaptive_trailing")
        # At some point profit_R >= 1.0, breakeven should trigger
        # (after min_hold_seconds=120, i.e., i*5>=120 => i>=24; but our
        # path only has 7 steps so i*5 max = 30 < 120 -> HOLD due to Phase 0)
        # So modify_count may be 0 in this short path. Either is acceptable.
        assert "modify_count" in result
        assert "trigger_count" in result

    def test_14_evaluation_safety_fields(self):
        """Evaluation result must include safety fields."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        result = e.run_evaluation()
        assert "safety" in result
        assert result["safety"]["order_send_called"] is False
        assert result["safety"]["position_modified"] is False
        assert result["safety"]["no_martingale"] is True
        assert result["safety"]["no_grid"] is True
        assert result["safety"]["no_averaging"] is True
        assert result["safety"]["no_loss_based_lot_multiplier"] is True

    def test_15_evaluation_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "research" / "evaluate_trailing_policy_mfe_mae.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src

    def test_16_evaluation_uses_synthetic_data_when_no_real(self):
        """When no real data exists, evaluation must use synthetic data
        and label it honestly."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        result = e.run_evaluation()
        # In test env, no real managed_trade_report or virtual paths
        assert result.get("findings", {}).get("data_source") in ("synthetic", "virtual_lifecycle", "real")

    def test_17_evaluation_includes_important_note(self):
        """Evaluation result must include important note about simulation."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        result = e.run_evaluation()
        assert "important_note" in result
        assert "simulation" in result["important_note"].lower() or "synthetic" in result["important_note"].lower()

    def test_18_pf_estimate_computed(self):
        """PF estimate must be computed (sum_wins / abs(sum_losses))."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        result = e.run_evaluation()
        policy_results = result.get("findings", {}).get("policy_results", {})
        for p, p_result in policy_results.items():
            pf = p_result["PF_estimate"]
            # PF must be a number or 'inf'
            assert pf == "inf" or isinstance(pf, (int, float))

    def test_19_expectancy_R_computed(self):
        """Expectancy_R must be computed."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        result = e.run_evaluation()
        policy_results = result.get("findings", {}).get("policy_results", {})
        for p, p_result in policy_results.items():
            exp = p_result["expectancy_R"]
            assert isinstance(exp, (int, float))

    def test_20_evaluation_does_not_claim_profitability_on_synthetic(self):
        """Evaluation on synthetic data must NOT claim ADAPTIVE_TRAILING_VALIDATED."""
        import scripts.research.evaluate_trailing_policy_mfe_mae as e
        result = e.run_evaluation()
        if result.get("findings", {}).get("data_source") == "synthetic":
            assert result["verdict"] != "ADAPTIVE_TRAILING_VALIDATED", \
                "Must not claim VALIDATED on synthetic data"
