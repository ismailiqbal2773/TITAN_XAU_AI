"""TITAN XAU AI - Sprint v2.8.7-G Final Blocker Debug Tests

Verifies:
  - Rejection debug outputs exist
  - REJECT_OVERFIT breakdown analysis exists
  - Near-pass candidate analysis exists
  - Broker calibration scan exists
  - Targeted search outputs exist
  - Final verdict exists
  - No order_send
  - No token
  - production_ready=False
  - CEO not bypassed
  - Meta-label not bypassed
"""
from __future__ import annotations
import sys, re, os, json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

BLOCKER_DIR = REPO_ROOT / "data" / "reports" / "final_blocker_debug"
TARGETED_DIR = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2_targeted"


class TestRejectionDebug:
    def test_rejection_debug_summary_md_exists(self):
        path = BLOCKER_DIR / "rejection_debug_summary.md"
        assert path.exists()

    def test_rejection_debug_summary_json_exists(self):
        path = BLOCKER_DIR / "rejection_debug_summary.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "rejection_breakdown" in data
        assert "total_candidates" in data

    def test_best_failed_candidates_csv_exists(self):
        path = BLOCKER_DIR / "best_failed_candidates.csv"
        assert path.exists()

    def test_broker_failure_matrix_csv_exists(self):
        path = BLOCKER_DIR / "broker_failure_matrix.csv"
        assert path.exists()

    def test_rejection_breakdown_has_reasons(self):
        path = BLOCKER_DIR / "rejection_debug_summary.json"
        data = json.loads(path.read_text())
        rb = data["rejection_breakdown"]
        # Must have at least one rejection reason
        assert len(rb) > 0
        # Reasons must be valid
        valid_reasons = {"REJECT_OVERFIT", "REJECT_BROKER_UNSTABLE", "REJECT_DD",
                         "REJECT_LOW_SAMPLE", "ACCEPT_CANDIDATE"}
        for reason in rb:
            assert reason in valid_reasons, f"unknown reason: {reason}"


class TestNearPassCandidate:
    def test_near_pass_candidate_md_exists(self):
        path = BLOCKER_DIR / "near_pass_candidate.md"
        assert path.exists()

    def test_near_pass_candidate_json_exists(self):
        path = BLOCKER_DIR / "near_pass_candidate.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "near_pass_found" in data

    def test_near_pass_found_is_bool(self):
        path = BLOCKER_DIR / "near_pass_candidate.json"
        data = json.loads(path.read_text())
        assert isinstance(data["near_pass_found"], bool)


class TestBrokerCalibration:
    def test_broker_calibration_scan_csv_exists(self):
        path = BLOCKER_DIR / "broker_calibration_scan.csv"
        assert path.exists()

    def test_broker_calibration_summary_md_exists(self):
        path = BLOCKER_DIR / "broker_calibration_summary.md"
        assert path.exists()

    def test_calibration_scan_has_multiple_brokers(self):
        import csv
        path = BLOCKER_DIR / "broker_calibration_scan.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        brokers = set(r["broker"] for r in rows)
        assert len(brokers) >= 2, f"expected >= 2 brokers, got {brokers}"


class TestTargetedSearch:
    def test_targeted_dir_exists(self):
        assert TARGETED_DIR.exists()

    def test_demo_go_decision_md_exists(self):
        path = TARGETED_DIR / "demo_go_decision.md"
        assert path.exists()
        text = path.read_text()
        assert "DEMO_SHADOW_ALLOWED" in text or "NO_SAFE_PARAMETER_FOUND" in text or \
               "NEEDS_BROKER_SPECIFIC_MODEL" in text

    def test_parameter_search_summary_md_exists(self):
        path = TARGETED_DIR / "parameter_search_summary.md"
        assert path.exists()

    def test_top_20_parameter_sets_csv_exists(self):
        path = TARGETED_DIR / "top_20_parameter_sets.csv"
        assert path.exists()

    def test_broker_oos_results_csv_exists(self):
        path = TARGETED_DIR / "broker_oos_results.csv"
        assert path.exists()


class TestFinalVerdict:
    def test_final_no_go_reason_md_exists(self):
        path = BLOCKER_DIR / "final_no_go_reason.md"
        assert path.exists()

    def test_final_verdict_is_valid(self):
        path = BLOCKER_DIR / "final_no_go_reason.md"
        text = path.read_text()
        valid_verdicts = [
            "NEEDS_BROKER_SPECIFIC_CALIBRATION",
            "NEEDS_BROKER_SPECIFIC_MODEL",
            "NEEDS_MORE_DATA",
            "EXIT_GEOMETRY_REDESIGN_NEEDED",
            "NO_TRADE_ALLOWED",
            "DEMO_SHADOW_ALLOWED",
        ]
        assert any(v in text for v in valid_verdicts), \
            f"no valid verdict found in final_no_go_reason.md"


class TestSafety:
    def _strip(self, src):
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'r"[^"]*"', '""', stripped)
        stripped = re.sub(r"r'[^']*'", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        return stripped

    def test_no_order_send_in_debug_script(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_blocker_debug.py"
        src = self._strip(path.read_text())
        assert "order_send(" not in src

    def test_no_token_in_debug_script(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_blocker_debug.py"
        src = path.read_text()
        assert "create_local_operator_execution_token" not in src

    def test_no_martingale_in_debug_script(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_blocker_debug.py"
        src = self._strip(path.read_text())
        assert "martingale" not in src.lower()

    def test_ceo_not_bypassed(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_blocker_debug.py"
        src = path.read_text()
        assert "evaluate_ceo_decision" in src
        assert "ceo_decision.allowed_to_trade" in src or "if not ceo_decision" in src

    def test_meta_label_not_bypassed(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_blocker_debug.py"
        src = path.read_text()
        # Must check meta threshold
        assert "meta_threshold" in src
        assert "meta_confidence <" in src

    def test_production_ready_false_in_candidate(self):
        """If final_candidate_params.json exists, production_ready must be False."""
        path = TARGETED_DIR / "final_candidate_params.json"
        if path.exists():
            data = json.loads(path.read_text())
            assert data.get("production_ready") is False

    def test_risk_within_safe_range(self):
        """risk_percent must not exceed 0.005 (0.5%)."""
        import csv
        path = BLOCKER_DIR / "best_failed_candidates.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            risk = float(r["risk_percent"])
            assert risk <= 0.005, f"risk_percent {risk} exceeds safe max 0.005"

    def test_no_sma_proxy(self):
        path = REPO_ROOT / "scripts" / "research" / "run_final_blocker_debug.py"
        src = self._strip(path.read_text())
        assert "sma_crossover" not in src.lower()
        assert "sma_proxy" not in src.lower()
