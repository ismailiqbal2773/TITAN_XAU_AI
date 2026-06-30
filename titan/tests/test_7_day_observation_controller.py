"""TITAN XAU AI - Sprint 9.9.3.42 7-Day Observation Controller Tests"""
from __future__ import annotations
import inspect, json, re, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestCheckOnly:
    def test_01_check_only_returns_results(self):
        import scripts.operator.start_7_day_demo_observation as ctrl
        results = ctrl.run_check_only()
        assert "session_id" in results
        assert "observation_status" in results
        assert "checks" in results
        assert "blockers" in results

    def test_02_check_only_includes_broker_gate(self):
        import scripts.operator.start_7_day_demo_observation as ctrl
        results = ctrl.run_check_only()
        assert "broker_gate_verdict" in results["checks"]
        assert results["checks"]["broker_gate_verdict"] == "ALLOWED"

    def test_03_check_only_includes_rc_verdict(self):
        import scripts.operator.start_7_day_demo_observation as ctrl
        results = ctrl.run_check_only()
        assert "rc_verdict" in results["checks"]

    def test_04_check_only_includes_cto_verdict(self):
        import scripts.operator.start_7_day_demo_observation as ctrl
        results = ctrl.run_check_only()
        assert "cto_verdict" in results["checks"]

    def test_05_check_only_includes_pre_observation_verdict(self):
        import scripts.operator.start_7_day_demo_observation as ctrl
        results = ctrl.run_check_only()
        assert "pre_observation_verdict" in results["checks"]


class TestBrokerGateEnforcement:
    def test_06_fundednext_blocked(self):
        from titan.production.broker_observation_gate import (
            BrokerObservationGate, ObservationBrokerVerdict,
        )
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="FundedNext Free Trial")
        assert result.verdict == ObservationBrokerVerdict.BLOCKED

    def test_07_fbs_blocked(self):
        from titan.production.broker_observation_gate import (
            BrokerObservationGate, ObservationBrokerVerdict,
        )
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="FBS-Demo")
        assert result.verdict == ObservationBrokerVerdict.BLOCKED

    def test_08_unknown_broker_blocked(self):
        from titan.production.broker_observation_gate import (
            BrokerObservationGate, ObservationBrokerVerdict,
        )
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="UnknownBroker123")
        assert result.verdict in (ObservationBrokerVerdict.UNKNOWN, ObservationBrokerVerdict.BLOCKED)

    def test_09_metaquotes_allowed(self):
        from titan.production.broker_observation_gate import (
            BrokerObservationGate, ObservationBrokerVerdict,
        )
        gate = BrokerObservationGate()
        result = gate.evaluate(broker_name="MetaQuotes-Demo")
        assert result.verdict == ObservationBrokerVerdict.ALLOWED


class TestApprovedWarnings:
    def test_10_approved_warnings_filter(self):
        import scripts.operator.start_7_day_demo_observation as ctrl
        approved, unapproved = ctrl._filter_approved_warnings([
            "REGIME_GATE_WIRED_BUT_PLACEHOLDER_CONTEXT: test",
            "Some other warning",
            "git_clean_hint: dirty",
        ])
        assert len(approved) == 2  # regime placeholder + git_clean_hint
        assert len(unapproved) == 1

    def test_11_check_only_accepts_approved_warnings(self):
        import scripts.operator.start_7_day_demo_observation as ctrl
        results = ctrl.run_check_only()
        # The regime placeholder warning should be in approved_warnings
        # not in unapproved_warnings or blockers
        regime_in_approved = any("REGIME" in w for w in results["approved_warnings"])
        regime_in_unapproved = any("REGIME" in w for w in results.get("unapproved_warnings", []))
        # At least one of these should be true (regime warning exists somewhere)
        # The key is that if it exists, it's approved, not unapproved
        if regime_in_approved or regime_in_unapproved:
            assert regime_in_approved or not regime_in_unapproved


class TestSessionStartReport:
    def test_12_json_report_writes(self, tmp_path):
        import scripts.operator.start_7_day_demo_observation as ctrl
        old_dir = ctrl.OUTPUT_DIR
        ctrl.OUTPUT_DIR = tmp_path
        try:
            results = ctrl.run_check_only()
            report = ctrl.write_report(results)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f:
                data = json.load(f)
            assert "session_id" in data
            assert "observation_status" in data
        finally:
            ctrl.OUTPUT_DIR = old_dir

    def test_13_md_report_writes(self, tmp_path):
        import scripts.operator.start_7_day_demo_observation as ctrl
        old_dir = ctrl.OUTPUT_DIR
        ctrl.OUTPUT_DIR = tmp_path
        try:
            results = ctrl.run_check_only()
            report = ctrl.write_report(results)
            md = Path(report["md_path"]).read_text(encoding="utf-8")
            assert "7-Day Observation Session Start" in md
            assert "Observation Status" in md
        finally:
            ctrl.OUTPUT_DIR = old_dir


class TestSafetyInvariants:
    def test_14_no_metatrader5_import(self):
        import scripts.operator.start_7_day_demo_observation as ctrl
        src = inspect.getsource(ctrl)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_15_no_order_send(self):
        import re
        import scripts.operator.start_7_day_demo_observation as ctrl
        src = inspect.getsource(ctrl)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert not re.search(r"\bmt5\.order_send\s*\(", src)

    def test_16_no_demo_micro_execute(self):
        import re
        import scripts.operator.start_7_day_demo_observation as ctrl
        src = inspect.getsource(ctrl)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", src)

    def test_17_no_raw_mt5_probe(self):
        import re
        import scripts.operator.start_7_day_demo_observation as ctrl
        src = inspect.getsource(ctrl)
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'r"[^"]*"', '""', src)
        src = re.sub(r"r'[^']*'", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", src)
