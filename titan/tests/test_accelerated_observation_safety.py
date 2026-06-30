"""TITAN XAU AI - Sprint 9.9.3.42.1 Accelerated Observation Safety Tests"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestNoFake7DayProof:
    def test_01_replay_labeled_as_historical(self):
        """Replay mode must be labeled HISTORICAL_REPLAY_VALIDATION."""
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_replay(days=7)
        assert result["mode"] == "HISTORICAL_REPLAY_VALIDATION"

    def test_02_real_short_labeled_correctly(self):
        """Real short mode must be labeled REAL_SHORT_OBSERVATION."""
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_real_short(minutes=60)
        assert result["mode"] == "REAL_SHORT_OBSERVATION"

    def test_03_combined_labeled_as_accelerated(self):
        """Combined mode must be labeled ACCELERATED_TECHNICAL_VALIDATION."""
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_combined(minutes=60, replay_days=7)
        assert result["mode"] == "ACCELERATED_TECHNICAL_VALIDATION"

    def test_04_replay_warning_present(self):
        """Replay must include REPLAY_NOT_REAL_FORWARD_EVIDENCE warning."""
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_replay(days=7)
        assert any("REPLAY_NOT_REAL_FORWARD_EVIDENCE" in w for w in result["warnings"])

    def test_05_real_short_warning_present(self):
        """Real short must include REAL_SHORT_NOT_FULL_7_DAY_EVIDENCE warning."""
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_real_short(minutes=60)
        assert any("REAL_SHORT_NOT_FULL_7_DAY_EVIDENCE" in w for w in result["warnings"])


class TestNoUnsafeExecution:
    def test_06_no_order_send_in_validation_script(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_accelerated_observation_validation.py"
        src = path.read_text(encoding="utf-8")
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r"'''[\s\S]*?'''", "''", code)
        code = re.sub(r'r"[^"]*"', '""', code)
        code = re.sub(r"r'[^']*'", "''", code)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_07_no_demo_micro_execute_in_validation_script(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_accelerated_observation_validation.py"
        src = path.read_text(encoding="utf-8")
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r"'''[\s\S]*?'''", "''", code)
        code = re.sub(r'r"[^"]*"', '""', code)
        code = re.sub(r"r'[^']*'", "''", code)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_08_no_raw_mt5_probe_in_validation_script(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_accelerated_observation_validation.py"
        src = path.read_text(encoding="utf-8")
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r"'''[\s\S]*?'''", "''", code)
        code = re.sub(r'r"[^"]*"', '""', code)
        code = re.sub(r"r'[^']*'", "''", code)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code)

    def test_09_no_metatrader5_import_in_scorecard_script(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_accelerated_observation_scorecard.py"
        src = path.read_text(encoding="utf-8")
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_10_no_market_execution_adapter_use(self):
        """No MT5ExecutionAdapter instantiation in validation scripts."""
        path = REPO_ROOT / "scripts" / "operator" / "run_accelerated_observation_validation.py"
        src = path.read_text(encoding="utf-8")
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r"'''[\s\S]*?'''", "''", code)
        code = re.sub(r'r"[^"]*"', '""', code)
        code = re.sub(r"r'[^']*'", "''", code)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
        assert "MT5ExecutionAdapter()" not in code
        assert not re.search(r"\b(adapter\.send_open_order|adapter\.send_order)\s*\(", code)


class TestApprovedWarningsOnly:
    def test_11_combined_blocks_unapproved_warnings(self):
        """Combined mode must block PASS for unapproved warnings."""
        import scripts.operator.run_accelerated_observation_validation as av
        # Verify APPROVED_WARNINGS set exists
        assert "REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT" in av.APPROVED_WARNINGS
        assert "REPLAY_NOT_REAL_FORWARD_EVIDENCE" in av.APPROVED_WARNINGS
        assert "REAL_SHORT_NOT_FULL_7_DAY_EVIDENCE" in av.APPROVED_WARNINGS

    def test_12_scorecard_separates_metrics(self):
        """Scorecard must not mix replay and real forward evidence."""
        import scripts.operator.run_accelerated_observation_scorecard as sc
        # Verify the scorecard has separate metric sections
        import inspect
        src = inspect.getsource(sc)
        assert "real_short_metrics" in src
        assert "replay_metrics" in src
        assert "true_forward_metrics" in src
