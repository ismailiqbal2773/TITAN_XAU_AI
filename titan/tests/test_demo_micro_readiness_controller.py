"""TITAN XAU AI - Sprint 9.9.3.43 Demo Micro Readiness Controller Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestReadinessController:
    def test_01_check_only_returns_result(self):
        import scripts.operator.check_demo_micro_readiness as dm
        result = dm.run_check()
        assert "verdict" in result and "checks" in result and "blockers" in result

    def test_02_default_is_check_only(self):
        """Default mode is check-only (no execution)."""
        import scripts.operator.check_demo_micro_readiness as dm
        result = dm.run_check()
        assert "verdict" in result  # check-only produces a verdict

    def test_03_refuses_live_trading_true(self, monkeypatch):
        import scripts.operator.check_demo_micro_readiness as dm
        # Patch _read_config_runtime to return live_trading=true
        monkeypatch.setattr(dm, "_read_config_runtime", lambda: {"dry_run": True, "live_trading": True, "max_lot": 0.01, "max_open_positions": 1})
        result = dm.run_check()
        assert result["verdict"] == "DEMO_MICRO_BLOCKED"
        assert any("live_trading" in b for b in result["blockers"])

    def test_04_refuses_dry_run_false(self, monkeypatch):
        import scripts.operator.check_demo_micro_readiness as dm
        monkeypatch.setattr(dm, "_read_config_runtime", lambda: {"dry_run": False, "live_trading": False, "max_lot": 0.01, "max_open_positions": 1})
        result = dm.run_check()
        assert result["verdict"] == "DEMO_MICRO_BLOCKED"
        assert any("dry_run" in b for b in result["blockers"])

    def test_05_refuses_max_lot_above_001(self, monkeypatch):
        import scripts.operator.check_demo_micro_readiness as dm
        monkeypatch.setattr(dm, "_read_config_runtime", lambda: {"dry_run": True, "live_trading": False, "max_lot": 0.10, "max_open_positions": 1})
        result = dm.run_check()
        assert result["verdict"] == "DEMO_MICRO_BLOCKED"
        assert any("max_lot" in b for b in result["blockers"])

    def test_06_refuses_max_positions_above_1(self, monkeypatch):
        import scripts.operator.check_demo_micro_readiness as dm
        monkeypatch.setattr(dm, "_read_config_runtime", lambda: {"dry_run": True, "live_trading": False, "max_lot": 0.01, "max_open_positions": 5})
        result = dm.run_check()
        assert result["verdict"] == "DEMO_MICRO_BLOCKED"
        assert any("max_open_positions" in b for b in result["blockers"])

    def test_07_fundednext_blocked(self):
        from titan.production.broker_observation_gate import BrokerObservationGate, ObservationBrokerVerdict
        gate = BrokerObservationGate()
        assert gate.evaluate(broker_name="FundedNext Free Trial").verdict == ObservationBrokerVerdict.BLOCKED

    def test_08_fbs_blocked(self):
        from titan.production.broker_observation_gate import BrokerObservationGate, ObservationBrokerVerdict
        gate = BrokerObservationGate()
        assert gate.evaluate(broker_name="FBS-Demo").verdict == ObservationBrokerVerdict.BLOCKED

    def test_09_unknown_broker_blocked(self):
        from titan.production.broker_observation_gate import BrokerObservationGate, ObservationBrokerVerdict
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="UnknownBroker")
        assert result.verdict in (ObservationBrokerVerdict.UNKNOWN, ObservationBrokerVerdict.BLOCKED)

    def test_10_metaquotes_allowed(self):
        from titan.production.broker_observation_gate import BrokerObservationGate, ObservationBrokerVerdict
        gate = BrokerObservationGate()
        assert gate.evaluate(broker_name="MetaQuotes-Demo").verdict == ObservationBrokerVerdict.ALLOWED

    def test_11_json_report_writes(self, tmp_path):
        import scripts.operator.check_demo_micro_readiness as dm
        old = dm.OUTPUT_DIR; dm.OUTPUT_DIR = tmp_path
        try:
            result = dm.run_check(); report = dm.write_report(result)
            assert Path(report["json_path"]).exists()
        finally: dm.OUTPUT_DIR = old

    def test_12_md_report_writes(self, tmp_path):
        import scripts.operator.check_demo_micro_readiness as dm
        old = dm.OUTPUT_DIR; dm.OUTPUT_DIR = tmp_path
        try:
            result = dm.run_check(); report = dm.write_report(result)
            assert "Demo Micro Readiness" in Path(report["md_path"]).read_text()
        finally: dm.OUTPUT_DIR = old

    def test_13_no_metatrader5_import(self):
        src = inspect.getsource(__import__("scripts.operator.check_demo_micro_readiness", fromlist=["x"]))
        assert "import MetaTrader5" not in src and "from MetaTrader5" not in src

    def test_14_no_order_send(self):
        import re; src = inspect.getsource(__import__("scripts.operator.check_demo_micro_readiness", fromlist=["x"]))
        code = re.sub(r'"""[\s\S]*?"""','""',src); code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code); code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_15_no_demo_micro_execute(self):
        import re; src = inspect.getsource(__import__("scripts.operator.check_demo_micro_readiness", fromlist=["x"]))
        code = re.sub(r'"""[\s\S]*?"""','""',src); code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code); code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_16_no_raw_mt5_probe(self):
        import re; src = inspect.getsource(__import__("scripts.operator.check_demo_micro_readiness", fromlist=["x"]))
        code = re.sub(r'"""[\s\S]*?"""','""',src); code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code); code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code)

    def test_17_explain_mode(self):
        import scripts.operator.check_demo_micro_readiness as dm
        result = dm.run_check(explain=True)
        assert "explanation" in result

    def test_18_verdict_in_valid_set(self):
        import scripts.operator.check_demo_micro_readiness as dm
        result = dm.run_check()
        assert result["verdict"] in ("DEMO_MICRO_READY","DEMO_MICRO_READY_WITH_WARNINGS","DEMO_MICRO_BLOCKED")
