"""TITAN XAU AI - Sprint 9.9.3.42.1 Accelerated Observation Validation Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestCheckOnly:
    def test_01_default_mode_is_check_only(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_check_only()
        assert result["mode"] == "CHECK_ONLY"

    def test_02_check_only_returns_verdict(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_check_only()
        assert result["verdict"] in ("CHECK_ONLY_PASS", "CHECK_ONLY_BLOCKED")

    def test_03_check_only_verifies_dry_run(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_check_only()
        assert "dry_run" in result
        assert result["dry_run"] is True

    def test_04_check_only_verifies_live_trading_false(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_check_only()
        assert "live_trading" in result
        assert result["live_trading"] is False

    def test_05_check_only_verifies_broker_gate(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_check_only()
        assert "broker_gate_verdict" in result
        assert result["broker_gate_verdict"] == "ALLOWED"


class TestReplayMode:
    def test_06_replay_returns_result(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_replay(days=7)
        assert "mode" in result
        assert result["mode"] == "HISTORICAL_REPLAY_VALIDATION"

    def test_07_replay_labeled_as_historical(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_replay(days=7)
        assert result["mode"] == "HISTORICAL_REPLAY_VALIDATION"

    def test_08_replay_includes_not_real_forward_warning(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_replay(days=7)
        has_warning = any("REPLAY_NOT_REAL_FORWARD_EVIDENCE" in w for w in result.get("warnings", []))
        assert has_warning, "Replay must include REPLAY_NOT_REAL_FORWARD_EVIDENCE warning"

    def test_09_replay_order_send_count_is_zero(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_replay(days=7)
        assert result.get("order_send_count", 0) == 0

    def test_10_replay_live_trading_false(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_replay(days=7)
        assert result.get("live_trading_detected") is False

    def test_11_replay_writes_json(self, tmp_path):
        import scripts.operator.run_accelerated_observation_validation as av
        old_dir = av.OUTPUT_DIR
        av.OUTPUT_DIR = tmp_path
        try:
            result = av.run_replay(days=7)
            report = av.write_replay_report(result)
            assert Path(report["json_path"]).exists()
        finally:
            av.OUTPUT_DIR = old_dir

    def test_12_replay_writes_md(self, tmp_path):
        import scripts.operator.run_accelerated_observation_validation as av
        old_dir = av.OUTPUT_DIR
        av.OUTPUT_DIR = tmp_path
        try:
            result = av.run_replay(days=7)
            report = av.write_replay_report(result)
            md = Path(report["md_path"]).read_text(encoding="utf-8")
            assert "HISTORICAL_REPLAY_VALIDATION" in md
        finally:
            av.OUTPUT_DIR = old_dir


class TestRealShortMode:
    def test_13_real_short_refuses_below_30_minutes(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_real_short(minutes=15)
        assert result["verdict"] == "REAL_SHORT_FAIL"

    def test_14_real_short_returns_result(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_real_short(minutes=60)
        assert "mode" in result
        assert result["mode"] == "REAL_SHORT_OBSERVATION"

    def test_15_real_short_order_send_zero(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_real_short(minutes=60)
        assert result.get("order_send_count", 0) == 0

    def test_16_real_short_includes_not_full_7day_warning(self):
        import scripts.operator.run_accelerated_observation_validation as av
        result = av.run_real_short(minutes=60)
        has_warning = any("REAL_SHORT_NOT_FULL_7_DAY_EVIDENCE" in w for w in result.get("warnings", []))
        assert has_warning


class TestCombinedMode:
    def test_17_combined_produces_final_report(self, tmp_path):
        import scripts.operator.run_accelerated_observation_validation as av
        old_dir = av.OUTPUT_DIR
        av.OUTPUT_DIR = tmp_path
        try:
            result = av.run_combined(minutes=60, replay_days=7)
            assert "verdict" in result
            assert result["mode"] == "ACCELERATED_TECHNICAL_VALIDATION"
            report = av.write_combined_report(result)
            assert Path(report["json_path"]).exists()
        finally:
            av.OUTPUT_DIR = old_dir

    def test_18_combined_verdict_in_valid_set(self, tmp_path):
        import scripts.operator.run_accelerated_observation_validation as av
        old_dir = av.OUTPUT_DIR
        av.OUTPUT_DIR = tmp_path
        try:
            result = av.run_combined(minutes=60, replay_days=7)
            assert result["verdict"] in (
                "ACCELERATED_VALIDATION_PASS",
                "ACCELERATED_VALIDATION_PASS_WITH_WARNINGS",
                "ACCELERATED_VALIDATION_FAIL",
                "ACCELERATED_VALIDATION_INSUFFICIENT_DATA",
            )
        finally:
            av.OUTPUT_DIR = old_dir


class TestSafetyInvariants:
    def test_19_no_metatrader5_import(self):
        import scripts.operator.run_accelerated_observation_validation as av
        src = inspect.getsource(av)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_20_no_order_send(self):
        import re
        import scripts.operator.run_accelerated_observation_validation as av
        src = inspect.getsource(av)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert not re.search(r"\bmt5\.order_send\s*\(", src)

    def test_21_no_demo_micro_execute(self):
        import re
        import scripts.operator.run_accelerated_observation_validation as av
        src = inspect.getsource(av)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", src)

    def test_22_no_raw_mt5_probe(self):
        import re
        import scripts.operator.run_accelerated_observation_validation as av
        src = inspect.getsource(av)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", src)
