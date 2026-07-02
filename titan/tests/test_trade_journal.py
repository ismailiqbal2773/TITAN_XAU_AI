"""TITAN XAU AI - Sprint v2.8 Trade Journal Autonomous Entry Check Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestTradeJournalAutonomousEvents:
    def test_01_autonomous_event_types_exist(self):
        """All v2.8 autonomous entry check event types must exist."""
        from titan.production.trade_journal import EventType
        assert EventType.AUTONOMOUS_ENTRY_CHECK_STARTED.value == "AUTONOMOUS_ENTRY_CHECK_STARTED"
        assert EventType.REGIME_DETECTION_RESULT.value == "REGIME_DETECTION_RESULT"
        assert EventType.ALPHA_SIGNAL_RESULT.value == "ALPHA_SIGNAL_RESULT"
        assert EventType.META_LABEL_GATE_RESULT.value == "META_LABEL_GATE_RESULT"
        assert EventType.RISK_GATE_RESULT.value == "RISK_GATE_RESULT"
        assert EventType.BROKER_GATE_RESULT.value == "BROKER_GATE_RESULT"
        assert EventType.PROP_FUNDED_GATE_RESULT.value == "PROP_FUNDED_GATE_RESULT"
        assert EventType.EXECUTION_GEOMETRY_GATE_RESULT.value == "EXECUTION_GEOMETRY_GATE_RESULT"
        assert EventType.AUTONOMOUS_ENTRY_DECISION.value == "AUTONOMOUS_ENTRY_DECISION"
        assert EventType.AUTONOMOUS_DEMO_NOT_READY.value == "AUTONOMOUS_DEMO_NOT_READY"

    def test_02_log_autonomous_entry_decision(self, tmp_path):
        """log_autonomous_entry_decision must write to journal."""
        from titan.production.trade_journal import TradeJournal
        journal_path = tmp_path / "journal.jsonl"
        journal = TradeJournal(path=str(journal_path))
        event_id = journal.log_autonomous_entry_decision({
            "final_decision": "ALPHA_REGIME_ENTRY_PASS",
            "blockers": [],
            "warnings": [],
            "confidence": 0.7,
            "threshold": 0.55,
            "profile": "prop_funded_safe",
            "actual_RR": 3.0,
        })
        assert event_id
        assert journal_path.exists()
        lines = journal_path.read_text().strip().split("\n")
        assert len(lines) >= 1
        record = json.loads(lines[-1])
        assert record["event_type"] == "AUTONOMOUS_ENTRY_DECISION"
        assert record["data"]["final_decision"] == "ALPHA_REGIME_ENTRY_PASS"

    def test_03_log_autonomous_entry_check_started(self, tmp_path):
        """log_autonomous_entry_check_started must write to journal."""
        from titan.production.trade_journal import TradeJournal
        journal_path = tmp_path / "journal.jsonl"
        journal = TradeJournal(path=str(journal_path))
        journal.log_autonomous_entry_check_started({
            "profile": "prop_funded_safe",
            "symbol": "XAUUSD",
        })
        lines = journal_path.read_text().strip().split("\n")
        record = json.loads(lines[-1])
        assert record["event_type"] == "AUTONOMOUS_ENTRY_CHECK_STARTED"

    def test_04_log_regime_detection_result(self, tmp_path):
        """log_regime_detection_result must write to journal."""
        from titan.production.trade_journal import TradeJournal
        journal_path = tmp_path / "journal.jsonl"
        journal = TradeJournal(path=str(journal_path))
        journal.log_regime_detection_result({
            "regime_detected": True,
            "regime_value": "TREND_UP",
        })
        lines = journal_path.read_text().strip().split("\n")
        record = json.loads(lines[-1])
        assert record["event_type"] == "REGIME_DETECTION_RESULT"

    def test_05_log_alpha_signal_result(self, tmp_path):
        """log_alpha_signal_result must write to journal."""
        from titan.production.trade_journal import TradeJournal
        journal_path = tmp_path / "journal.jsonl"
        journal = TradeJournal(path=str(journal_path))
        journal.log_alpha_signal_result({
            "alpha_signal_detected": True,
            "alpha_direction": "LONG",
        })
        lines = journal_path.read_text().strip().split("\n")
        record = json.loads(lines[-1])
        assert record["event_type"] == "ALPHA_SIGNAL_RESULT"

    def test_06_log_autonomous_demo_not_ready(self, tmp_path):
        """log_autonomous_demo_not_ready must write to journal."""
        from titan.production.trade_journal import TradeJournal
        journal_path = tmp_path / "journal.jsonl"
        journal = TradeJournal(path=str(journal_path))
        journal.log_autonomous_demo_not_ready({
            "blockers": ["ALPHA_REGIME_ENTRY_NOT_PROVEN"],
        })
        lines = journal_path.read_text().strip().split("\n")
        record = json.loads(lines[-1])
        assert record["event_type"] == "AUTONOMOUS_DEMO_NOT_READY"

    def test_07_all_gate_helper_methods_exist(self):
        """All v2.8 gate helper methods must exist on TradeJournal."""
        from titan.production.trade_journal import TradeJournal
        assert hasattr(TradeJournal, "log_autonomous_entry_check_started")
        assert hasattr(TradeJournal, "log_regime_detection_result")
        assert hasattr(TradeJournal, "log_alpha_signal_result")
        assert hasattr(TradeJournal, "log_meta_label_gate_result")
        assert hasattr(TradeJournal, "log_risk_gate_result")
        assert hasattr(TradeJournal, "log_broker_gate_result")
        assert hasattr(TradeJournal, "log_prop_funded_gate_result")
        assert hasattr(TradeJournal, "log_execution_geometry_gate_result")
        assert hasattr(TradeJournal, "log_autonomous_entry_decision")
        assert hasattr(TradeJournal, "log_autonomous_demo_not_ready")

    def test_08_journal_includes_decision_chain(self, tmp_path):
        """Journal must record the full decision chain in order."""
        from titan.production.trade_journal import TradeJournal
        journal_path = tmp_path / "journal.jsonl"
        journal = TradeJournal(path=str(journal_path))
        # Log the full chain
        journal.log_autonomous_entry_check_started({"profile": "prop_funded_safe"})
        journal.log_regime_detection_result({"regime_detected": True})
        journal.log_alpha_signal_result({"alpha_direction": "LONG"})
        journal.log_meta_label_gate_result({"pass": True})
        journal.log_risk_gate_result({"pass": True})
        journal.log_broker_gate_result({"pass": True})
        journal.log_prop_funded_gate_result({"pass": True})
        journal.log_execution_geometry_gate_result({"pass": True, "actual_RR": 3.0})
        journal.log_autonomous_entry_decision({
            "final_decision": "ALPHA_REGIME_ENTRY_PASS",
            "blockers": [],
            "warnings": [],
        })
        lines = journal_path.read_text().strip().split("\n")
        event_types = [json.loads(l)["event_type"] for l in lines]
        # Must contain all 9 event types in order
        assert "AUTONOMOUS_ENTRY_CHECK_STARTED" in event_types
        assert "REGIME_DETECTION_RESULT" in event_types
        assert "ALPHA_SIGNAL_RESULT" in event_types
        assert "META_LABEL_GATE_RESULT" in event_types
        assert "RISK_GATE_RESULT" in event_types
        assert "BROKER_GATE_RESULT" in event_types
        assert "PROP_FUNDED_GATE_RESULT" in event_types
        assert "EXECUTION_GEOMETRY_GATE_RESULT" in event_types
        assert "AUTONOMOUS_ENTRY_DECISION" in event_types
        # The decision must be last
        assert event_types[-1] == "AUTONOMOUS_ENTRY_DECISION"
