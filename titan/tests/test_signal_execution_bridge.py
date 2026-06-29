"""
TITAN XAU AI — Sprint 9.9.3.29 Signal Execution Bridge Tests
=============================================================
"""
from __future__ import annotations
import inspect
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.signal_execution_bridge import (
    SignalExecutionBridge, DecisionInput, ExecutionIntent, BridgeDecision,
    MIN_MODEL_CONFIDENCE, MIN_META_CONFIDENCE, MAX_LOT,
)


class TestApprovedDemoIntent:
    """Approved demo intent with strong confidence and safe context."""

    def _make_strong_input(self):
        return DecisionInput(
            symbol="XAUUSD", model_signal="BUY",
            model_confidence=0.75, meta_confidence=0.70, direction="BUY",
        )

    def _make_safe_contexts(self):
        return {
            "regime_status": {"primary_regime": "TREND_UP", "risk_multiplier": 1.0,
                               "allow_new_trade": True, "block_reason": None},
            "broker_info": {"status": "PASS", "server_name": "MetaQuotes-Demo"},
            "runtime_health": {"status": "HEALTHY"},
            "security_status": {"allowed": True},
        }

    def test_01_approved_demo_intent(self):
        """Strong confidence + safe context → APPROVE_DEMO_INTENT."""
        bridge = SignalExecutionBridge()
        ctx = self._make_safe_contexts()
        intent = bridge.build_intent(self._make_strong_input(), **ctx)
        assert intent.allowed is True
        assert intent.decision == BridgeDecision.APPROVE_DEMO_INTENT.value
        assert intent.side == "BUY"
        assert intent.lot <= 0.01
        assert intent.risk_multiplier <= 1.0
        assert intent.dry_run is True
        assert intent.demo_only is True

    def test_02_approved_intent_has_approval_reasons(self):
        """Approved intent has non-empty approval_reasons."""
        bridge = SignalExecutionBridge()
        ctx = self._make_safe_contexts()
        intent = bridge.build_intent(self._make_strong_input(), **ctx)
        assert len(intent.approval_reasons) >= 3  # confidence + regime + broker

    def test_03_dry_run_true_by_default(self):
        """dry_run is True by default."""
        bridge = SignalExecutionBridge()
        assert bridge.dry_run is True

    def test_04_demo_only_true_by_default(self):
        """demo_only is True by default."""
        bridge = SignalExecutionBridge()
        assert bridge.demo_only is True


class TestConfidenceGates:
    """Confidence gate tests."""

    def test_05_low_model_confidence_blocks(self):
        """Low model confidence → BLOCK_LOW_CONFIDENCE."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.30,
                             meta_confidence=0.70, direction="BUY")
        intent = bridge.build_intent(inp)
        assert intent.allowed is False
        assert intent.decision == BridgeDecision.BLOCK_LOW_CONFIDENCE.value
        assert any("Model confidence" in r for r in intent.block_reasons)

    def test_06_low_meta_confidence_blocks(self):
        """Low meta confidence → BLOCK_META_REJECT."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.30, direction="BUY")
        intent = bridge.build_intent(inp)
        assert intent.allowed is False
        assert intent.decision == BridgeDecision.BLOCK_META_REJECT.value

    def test_07_no_signal_dry_run_only(self):
        """No model signal → DRY_RUN_ONLY."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="NONE", model_confidence=0.0)
        intent = bridge.build_intent(inp)
        assert intent.allowed is False
        assert intent.decision == BridgeDecision.DRY_RUN_ONLY.value


class TestRegimeGate:
    """Regime gate tests."""

    def test_08_news_shock_blocks(self):
        """NEWS_SHOCK regime blocks."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        regime = {"primary_regime": "NEWS_SHOCK", "risk_multiplier": 0.0,
                   "allow_new_trade": False, "block_reason": "News shock"}
        intent = bridge.build_intent(inp, regime_status=regime)
        assert intent.allowed is False
        assert intent.decision == BridgeDecision.BLOCK_REGIME.value

    def test_09_spread_expansion_blocks(self):
        """SPREAD_EXPANSION regime blocks."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        regime = {"primary_regime": "SPREAD_EXPANSION", "risk_multiplier": 0.3,
                   "allow_new_trade": False, "block_reason": "Spread expansion"}
        intent = bridge.build_intent(inp, regime_status=regime)
        assert intent.allowed is False
        assert intent.decision == BridgeDecision.BLOCK_REGIME.value

    def test_10_unknown_regime_fails_safe(self):
        """UNKNOWN regime reduces risk but doesn't block (allow_new_trade=True)."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        regime = {"primary_regime": "UNKNOWN", "risk_multiplier": 0.5,
                   "allow_new_trade": True, "block_reason": None}
        intent = bridge.build_intent(inp, regime_status=regime,
                                      broker_info={"status": "PASS"},
                                      runtime_health={"status": "HEALTHY"},
                                      security_status={"allowed": True})
        assert intent.allowed is True  # UNKNOWN doesn't block, just reduces
        assert intent.risk_multiplier <= 0.5

    def test_11_regime_reduces_risk_multiplier(self):
        """Regime risk_multiplier is applied and capped at 1.0."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        regime = {"primary_regime": "RANGE", "risk_multiplier": 0.7,
                   "allow_new_trade": True, "block_reason": None}
        intent = bridge.build_intent(inp, regime_status=regime,
                                      broker_info={"status": "PASS"},
                                      runtime_health={"status": "HEALTHY"},
                                      security_status={"allowed": True})
        assert intent.risk_multiplier <= 0.7


class TestBrokerGate:
    """Broker gate tests."""

    def test_12_blocked_broker_blocks(self):
        """BLOCKED broker (FundedNext) blocks."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        broker = {"status": "BLOCKED", "server_name": "FundedNext Free Trial"}
        intent = bridge.build_intent(inp, broker_info=broker)
        assert intent.allowed is False
        assert intent.decision == BridgeDecision.BLOCK_BROKER.value

    def test_13_reject_broker_blocks(self):
        """REJECT broker (FBS) blocks."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        broker = {"status": "REJECT", "server_name": "FBS-Demo"}
        intent = bridge.build_intent(inp, broker_info=broker)
        assert intent.allowed is False
        assert intent.decision == BridgeDecision.BLOCK_BROKER.value

    def test_14_pass_broker_allows(self):
        """PASS broker (MetaQuotes) allows intent."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        broker = {"status": "PASS", "server_name": "MetaQuotes-Demo"}
        intent = bridge.build_intent(inp, broker_info=broker,
                                      runtime_health={"status": "HEALTHY"},
                                      security_status={"allowed": True})
        assert intent.allowed is True
        assert intent.broker_status == "PASS"


class TestRuntimeHealthGate:
    """Runtime health gate tests."""

    def test_15_critical_health_blocks(self):
        """CRITICAL runtime health blocks."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        intent = bridge.build_intent(inp, runtime_health={"status": "CRITICAL"})
        assert intent.allowed is False
        assert intent.decision == BridgeDecision.BLOCK_RUNTIME_HEALTH.value

    def test_16_healthy_health_allows(self):
        """HEALTHY runtime health allows."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        intent = bridge.build_intent(inp, runtime_health={"status": "HEALTHY"},
                                      broker_info={"status": "PASS"},
                                      security_status={"allowed": True})
        assert intent.allowed is True


class TestSecurityGate:
    """Security gate tests."""

    def test_17_security_blocked_blocks(self):
        """Security release failure blocks."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        intent = bridge.build_intent(inp, security_status={"allowed": False,
                                                            "reason": "License invalid"})
        assert intent.allowed is False
        assert intent.decision == BridgeDecision.BLOCK_SECURITY.value

    def test_18_security_allowed_passes(self):
        """Security allowed passes gate."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        intent = bridge.build_intent(inp, security_status={"allowed": True},
                                      broker_info={"status": "PASS"},
                                      runtime_health={"status": "HEALTHY"})
        assert intent.allowed is True


class TestRiskLimits:
    """Risk limit tests."""

    def test_19_risk_multiplier_never_above_1(self):
        """risk_multiplier is never above 1.0."""
        intent = ExecutionIntent(risk_multiplier=2.0)
        assert intent.risk_multiplier == 1.0

    def test_20_lot_never_above_001(self):
        """lot is never above 0.01."""
        intent = ExecutionIntent(lot=0.05)
        assert intent.lot == 0.01

    def test_21_bridge_lot_cap(self):
        """Bridge caps lot at max_lot."""
        bridge = SignalExecutionBridge(max_lot=0.01)
        inp = DecisionInput(model_signal="BUY", model_confidence=0.75,
                             meta_confidence=0.70, direction="BUY")
        intent = bridge.build_intent(inp, broker_info={"status": "PASS"},
                                      runtime_health={"status": "HEALTHY"},
                                      security_status={"allowed": True})
        assert intent.lot <= 0.01


class TestFailClosed:
    """Fail-closed behavior tests."""

    def test_22_exception_returns_fail_closed(self):
        """Exception during build_intent returns fail-closed intent."""
        bridge = SignalExecutionBridge()
        # Pass invalid input to trigger exception
        inp = DecisionInput(model_signal="BUY", model_confidence="invalid",  # type: ignore
                             meta_confidence=0.70, direction="BUY")
        intent = bridge.build_intent(inp)
        assert intent.allowed is False
        assert intent.decision == BridgeDecision.BLOCK_UNKNOWN.value

    def test_23_fail_closed_intent_fields(self):
        """Fail-closed intent has correct fields."""
        bridge = SignalExecutionBridge()
        inp = DecisionInput(model_signal="BUY", model_confidence=0.30,
                             meta_confidence=0.70, direction="BUY")
        intent = bridge.build_intent(inp)
        assert intent.allowed is False
        assert len(intent.block_reasons) >= 1
        assert intent.dry_run is True
        assert intent.demo_only is True


class TestNoMT5Execution:
    """Verify bridge never calls MT5 execution."""

    def test_24_no_order_send_calls_in_source(self):
        """Bridge source does not contain actual order_send CALLS (not just mentions)."""
        import re
        from titan.production import signal_execution_bridge
        src = inspect.getsource(signal_execution_bridge)
        # Check for actual function calls (not just mentions in docstrings/comments)
        # Pattern: mt5.order_send( or adapter.send_open_order( or adapter.send_order(
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls in source: {matches}"

    def test_25_no_mt5_import(self):
        """Bridge does not import MetaTrader5."""
        from titan.production import signal_execution_bridge
        src = inspect.getsource(signal_execution_bridge)
        assert "import MetaTrader5" not in src


class TestReportWriter:
    """Report writer tests."""

    def test_26_json_report_writes(self, tmp_path):
        """JSON report writes with all required fields."""
        import scripts.audit.signal_execution_bridge_report as rep
        old_dir = rep.OUTPUT_DIR
        old_json = rep.JSON_PATH
        old_md = rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            assert Path(result["json_path"]).exists()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert "pipeline_gates" in data
            assert "bridge_decisions" in data
            assert "fail_closed_rules" in data
            assert "sample_approved_demo_intent" in data
            assert "sample_blocked_intent" in data
            assert "warnings" in data
        finally:
            rep.OUTPUT_DIR = old_dir
            rep.JSON_PATH = old_json
            rep.MD_PATH = old_md

    def test_27_md_report_writes(self, tmp_path):
        """MD report writes with summary."""
        import scripts.audit.signal_execution_bridge_report as rep
        old_dir = rep.OUTPUT_DIR
        old_json = rep.JSON_PATH
        old_md = rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            md = Path(result["md_path"]).read_text()
            assert "Signal Execution Bridge Report" in md
            assert "Pipeline Gates" in md
            assert "Fail-Closed Rules" in md
            assert "Sample Approved" in md
            assert "Warnings" in md
            assert "no market execution" in md.lower() or "No market" in md
        finally:
            rep.OUTPUT_DIR = old_dir
            rep.JSON_PATH = old_json
            rep.MD_PATH = old_md
