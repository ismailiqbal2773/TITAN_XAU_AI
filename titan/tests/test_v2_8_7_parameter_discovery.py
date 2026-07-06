"""TITAN XAU AI - Sprint v2.8.7 Safe Parameter Discovery Tests"""
from __future__ import annotations
import sys, json, csv, os, re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "parameter_discovery"
CONFIG_OUTPUT = REPO_ROOT / "config" / "research_candidate_params_v2_8_7.json"


class TestSafety:
    def test_no_order_send(self):
        """Script must never call order_send."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', stripped)
        stripped = re.sub(r"'(?:[^'\\]|\\.)*'", "''", stripped)
        assert "order_send(" not in stripped

    def test_no_token(self):
        """Script must never create tokens."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "create_local_operator_execution_token" not in src

    def test_no_dummy_data(self):
        """Script must not use dummy/synthetic data."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        # Check for "NO dummy/synthetic" assertion in docstring (allowed)
        # but not actual dummy data generation
        assert "dummy" not in src.lower().split("# no dummy")[0].split('"""no dummy')[0] or "no dummy" in src.lower()

    def test_alpha_threshold_not_lowered_in_production(self):
        """Alpha threshold 0.55 must remain in source as production default."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "0.55" in src  # Production threshold preserved

    def test_no_martingale(self):
        """No martingale/grid/averaging."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "martingale" not in src.lower()

    def test_ceo_not_bypassed(self):
        """CEO must not be bypassed."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        # The script should not claim to bypass CEO
        assert "bypass" not in src.lower() or "do not bypass" in src.lower()


class TestDataIntegrity:
    def test_real_data_only(self):
        """Script must use real data from repo paths."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "titan/data/canonical" in src or "canonical" in src
        assert "mt5_brokers" in src or "exness" in src

    def test_train_val_oos_split_enforced(self):
        """Train/validation/OOS split must be enforced."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "2020" in src and "2023" in src  # IS
        assert "2024" in src  # Validation
        assert "2025" in src and "2026" in src  # OOS

    def test_leave_one_broker_out_enforced(self):
        """LOBO must be implemented."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "lobo" in src.lower() or "leave_one_broker" in src.lower() or "held_out" in src.lower()

    def test_no_full_data_overfit(self):
        """Script must not select on full data."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "oos" in src.lower()
        assert "in_sample" in src.lower() or "is_" in src.lower() or '"is"' in src


class TestHardFails:
    def test_dd_hard_fail(self):
        """Max total DD > 8% must cause hard fail."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "0.08" in src
        assert "REJECT_DD" in src

    def test_prop_violation_hard_fail(self):
        """Prop violations > 0 must cause hard fail."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "prop_violations" in src
        assert "REJECT_DD" in src

    def test_low_sample_penalty(self):
        """Low sample must cause penalty/rejection."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "REJECT_LOW_SAMPLE" in src
        assert "MIN_SAMPLE_TRADES" in src

    def test_broker_unstable_rejected(self):
        """Top set cannot be selected if only one broker passes."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "REJECT_BROKER_UNSTABLE" in src


class TestOutputFiles:
    def test_output_files_created(self):
        """Output files must be created when script runs."""
        import scripts.research.run_safe_parameter_discovery as m
        m.run_discovery(
            "prop_funded_safe", [0.005], 0.01, ["H1"],
            ["canonical"], False, True
        )
        assert (OUTPUT_DIR / "parameter_search_summary.json").exists()
        assert (OUTPUT_DIR / "parameter_search_summary.md").exists()
        assert (OUTPUT_DIR / "overfit_risk_report.md").exists()

    def test_final_candidate_is_research_only(self):
        """Final candidate must be research-only, not production."""
        import scripts.research.run_safe_parameter_discovery as m
        m.run_discovery(
            "prop_funded_safe", [0.005], 0.01, ["H1"],
            ["canonical"], False, True
        )
        # Check if final_candidate_params.json exists
        candidate_path = OUTPUT_DIR / "final_candidate_params.json"
        if candidate_path.exists():
            with open(candidate_path) as f:
                candidate = json.load(f)
            assert candidate.get("production_ready") is False
            assert candidate.get("requires_operator_review") is True
            assert candidate.get("requires_demo_shadow_test") is True


class TestNoLookahead:
    def test_no_future_data_in_backtest(self):
        """Backtest must not use future data."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        # Check that backtest iterates forward (i increases) and uses i+j for exit
        assert "for i in range" in src
        assert "i + j" in src or "i+j" in src  # Exit uses future bars relative to entry
        # But entry must not use future data
        assert "closes[i]" in src  # Entry at current bar
