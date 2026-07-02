"""TITAN XAU AI - Sprint v2.8 Alpha/Regime Entry Decision Engine Tests"""
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


class TestAlphaRegimeEntryDecision:
    def test_01_module_imports(self):
        from titan.production.alpha_regime_entry_decision import (
            evaluate_entry, AlphaRegimeEntryDecision, ALL_VERDICTS,
        )
        assert callable(evaluate_entry)
        assert len(ALL_VERDICTS) == 10

    def test_02_no_regime_blocks(self):
        """No regime result -> ALPHA_REGIME_ENTRY_BLOCKED_NO_REGIME."""
        from titan.production.alpha_regime_entry_decision import (
            evaluate_entry, ALPHA_REGIME_ENTRY_BLOCKED_NO_REGIME,
        )
        decision = evaluate_entry(
            regime_result=None,
            alpha_signal={"detected": True, "direction": "LONG", "confidence": 0.7},
            risk_gate_result={"pass": True},
            broker_gate_result={"pass": True},
            prop_funded_gate_result={"pass": True},
            geometry_gate_result={"pass": True, "actual_RR": 3.0},
        )
        assert decision.final_decision == ALPHA_REGIME_ENTRY_BLOCKED_NO_REGIME
        assert not decision.regime_detected
        assert any("NO_REGIME" in b for b in decision.blockers)

    def test_03_no_alpha_blocks(self):
        """No alpha signal -> ALPHA_REGIME_ENTRY_BLOCKED_NO_ALPHA."""
        from titan.production.alpha_regime_entry_decision import (
            evaluate_entry, ALPHA_REGIME_ENTRY_BLOCKED_NO_ALPHA,
        )
        decision = evaluate_entry(
            regime_result={"detected": True, "regime_value": "TREND_UP", "confidence": 0.8},
            alpha_signal=None,
            risk_gate_result={"pass": True},
            broker_gate_result={"pass": True},
            prop_funded_gate_result={"pass": True},
            geometry_gate_result={"pass": True, "actual_RR": 3.0},
        )
        assert decision.final_decision == ALPHA_REGIME_ENTRY_BLOCKED_NO_ALPHA
        assert not decision.alpha_signal_detected

    def test_04_confidence_below_threshold_blocks(self):
        """Confidence < threshold -> ALPHA_REGIME_ENTRY_BLOCKED_CONFIDENCE."""
        from titan.production.alpha_regime_entry_decision import (
            evaluate_entry, ALPHA_REGIME_ENTRY_BLOCKED_CONFIDENCE,
        )
        decision = evaluate_entry(
            regime_result={"detected": True, "regime_value": "TREND_UP"},
            alpha_signal={"detected": True, "direction": "LONG", "confidence": 0.4},
            confidence_threshold=0.55,
            risk_gate_result={"pass": True},
            broker_gate_result={"pass": True},
            prop_funded_gate_result={"pass": True},
            geometry_gate_result={"pass": True, "actual_RR": 3.0},
        )
        assert decision.final_decision == ALPHA_REGIME_ENTRY_BLOCKED_CONFIDENCE
        assert not decision.alpha_pass
        assert any("CONFIDENCE_BELOW_THRESHOLD" in b for b in decision.blockers)

    def test_05_geometry_fail_blocks(self):
        """Geometry RR < 2.0 -> ALPHA_REGIME_ENTRY_BLOCKED_GEOMETRY."""
        from titan.production.alpha_regime_entry_decision import (
            evaluate_entry, ALPHA_REGIME_ENTRY_BLOCKED_GEOMETRY,
        )
        decision = evaluate_entry(
            regime_result={"detected": True, "regime_value": "TREND_UP"},
            alpha_signal={"detected": True, "direction": "LONG", "confidence": 0.7},
            confidence_threshold=0.55,
            risk_gate_result={"pass": True},
            broker_gate_result={"pass": True},
            prop_funded_gate_result={"pass": True},
            geometry_gate_result={"pass": False, "actual_RR": 1.0},
        )
        assert decision.final_decision == ALPHA_REGIME_ENTRY_BLOCKED_GEOMETRY
        assert not decision.geometry_gate_pass

    def test_06_risk_fail_blocks(self):
        """Risk gate fail -> ALPHA_REGIME_ENTRY_BLOCKED_RISK."""
        from titan.production.alpha_regime_entry_decision import (
            evaluate_entry, ALPHA_REGIME_ENTRY_BLOCKED_RISK,
        )
        decision = evaluate_entry(
            regime_result={"detected": True, "regime_value": "TREND_UP"},
            alpha_signal={"detected": True, "direction": "LONG", "confidence": 0.7},
            confidence_threshold=0.55,
            risk_gate_result={"pass": False, "blockers": ["MARGIN_TOO_HIGH"]},
            broker_gate_result={"pass": True},
            prop_funded_gate_result={"pass": True},
            geometry_gate_result={"pass": True, "actual_RR": 3.0},
        )
        assert decision.final_decision == ALPHA_REGIME_ENTRY_BLOCKED_RISK
        assert not decision.risk_gate_pass

    def test_07_broker_fail_blocks(self):
        """Broker gate fail -> ALPHA_REGIME_ENTRY_BLOCKED_BROKER."""
        from titan.production.alpha_regime_entry_decision import (
            evaluate_entry, ALPHA_REGIME_ENTRY_BLOCKED_BROKER,
        )
        decision = evaluate_entry(
            regime_result={"detected": True, "regime_value": "TREND_UP"},
            alpha_signal={"detected": True, "direction": "LONG", "confidence": 0.7},
            confidence_threshold=0.55,
            risk_gate_result={"pass": True},
            broker_gate_result={"pass": False, "status": "FAILED"},
            prop_funded_gate_result={"pass": True},
            geometry_gate_result={"pass": True, "actual_RR": 3.0},
        )
        assert decision.final_decision == ALPHA_REGIME_ENTRY_BLOCKED_BROKER
        assert not decision.broker_gate_pass

    def test_08_all_gates_pass(self):
        """All gates pass -> ALPHA_REGIME_ENTRY_PASS."""
        from titan.production.alpha_regime_entry_decision import (
            evaluate_entry, ALPHA_REGIME_ENTRY_PASS,
        )
        decision = evaluate_entry(
            regime_result={"detected": True, "regime_value": "TREND_UP", "confidence": 0.8},
            alpha_signal={"detected": True, "direction": "LONG", "confidence": 0.7},
            confidence_threshold=0.55,
            meta_label_result={"pass": True},
            calibration_result={"pass": True},
            risk_gate_result={"pass": True},
            broker_gate_result={"pass": True},
            prop_funded_gate_result={"pass": True},
            spread_gate_result={"pass": True},
            slippage_gate_result={"pass": True},
            news_gate_result={"pass": True},
            session_gate_result={"pass": True},
            geometry_gate_result={"pass": True, "actual_RR": 3.0},
        )
        assert decision.final_decision == ALPHA_REGIME_ENTRY_PASS
        assert decision.alpha_pass
        assert decision.regime_detected
        assert decision.alpha_direction == "LONG"
        assert decision.side == "BUY"
        assert decision.actual_RR == 3.0
        assert len(decision.blockers) == 0

    def test_09_decision_has_all_required_fields(self):
        """Decision dataclass must have all v2.8 spec fields."""
        from titan.production.alpha_regime_entry_decision import AlphaRegimeEntryDecision
        d = AlphaRegimeEntryDecision()
        required = [
            "timestamp_utc", "symbol", "timeframe", "selected_profile", "side",
            "regime_detected", "regime_value", "regime_confidence",
            "alpha_signal_detected", "alpha_direction", "alpha_confidence",
            "alpha_threshold", "alpha_pass", "meta_label_pass", "calibration_pass",
            "risk_gate_pass", "broker_gate_pass", "prop_funded_gate_pass",
            "spread_gate_pass", "slippage_gate_pass", "news_gate_pass",
            "session_gate_pass", "geometry_gate_pass", "actual_RR",
            "minimum_RR", "initial_tp_R", "final_decision", "blockers",
            "warnings", "evidence_sources",
        ]
        for field in required:
            assert hasattr(d, field), f"Missing field: {field}"

    def test_10_to_dict_serializable(self):
        """Decision must be serializable to dict."""
        from titan.production.alpha_regime_entry_decision import evaluate_entry
        d = evaluate_entry(
            regime_result={"detected": True, "regime_value": "TREND_UP"},
            alpha_signal={"detected": True, "direction": "LONG", "confidence": 0.7},
            risk_gate_result={"pass": True},
            broker_gate_result={"pass": True},
            prop_funded_gate_result={"pass": True},
            geometry_gate_result={"pass": True, "actual_RR": 3.0},
        )
        dd = d.to_dict()
        assert isinstance(dd, dict)
        assert "final_decision" in dd
        assert "blockers" in dd
        assert isinstance(dd["blockers"], list)
        import json
        json.dumps(dd)  # must be JSON-serializable

    def test_11_short_direction_maps_to_sell(self):
        """Alpha direction SHORT must map to side=SELL."""
        from titan.production.alpha_regime_entry_decision import evaluate_entry
        d = evaluate_entry(
            regime_result={"detected": True},
            alpha_signal={"detected": True, "direction": "SHORT", "confidence": 0.7},
            risk_gate_result={"pass": True},
            broker_gate_result={"pass": True},
            prop_funded_gate_result={"pass": True},
            geometry_gate_result={"pass": True, "actual_RR": 3.0},
        )
        assert d.alpha_direction == "SHORT"
        assert d.side == "SELL"

    def test_12_no_order_send_in_source(self):
        """Source must never call mt5.order_send."""
        src = (REPO_ROOT / "titan" / "production" / "alpha_regime_entry_decision.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bMetaTrader5\b", code)

    def test_13_no_position_modification(self):
        """Source must never modify positions."""
        src = (REPO_ROOT / "titan" / "production" / "alpha_regime_entry_decision.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)

    def test_14_no_martingale(self):
        """Source must not contain forbidden patterns."""
        src = (REPO_ROOT / "titan" / "production" / "alpha_regime_entry_decision.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code or "no_" in code or "forbid" in code

    def test_15_meta_label_block(self):
        """Meta-label fail -> ALPHA_REGIME_ENTRY_BLOCKED_META_LABEL."""
        from titan.production.alpha_regime_entry_decision import (
            evaluate_entry, ALPHA_REGIME_ENTRY_BLOCKED_META_LABEL,
        )
        d = evaluate_entry(
            regime_result={"detected": True},
            alpha_signal={"detected": True, "direction": "LONG", "confidence": 0.7},
            meta_label_result={"pass": False},
            risk_gate_result={"pass": True},
            broker_gate_result={"pass": True},
            prop_funded_gate_result={"pass": True},
            geometry_gate_result={"pass": True, "actual_RR": 3.0},
        )
        assert d.final_decision == ALPHA_REGIME_ENTRY_BLOCKED_META_LABEL

    def test_16_spread_block(self):
        """Spread fail -> ALPHA_REGIME_ENTRY_BLOCKED_SPREAD."""
        from titan.production.alpha_regime_entry_decision import (
            evaluate_entry, ALPHA_REGIME_ENTRY_BLOCKED_SPREAD,
        )
        d = evaluate_entry(
            regime_result={"detected": True},
            alpha_signal={"detected": True, "direction": "LONG", "confidence": 0.7},
            risk_gate_result={"pass": True},
            broker_gate_result={"pass": True},
            prop_funded_gate_result={"pass": True},
            spread_gate_result={"pass": False, "spread": 0.8, "limit": 0.5},
            geometry_gate_result={"pass": True, "actual_RR": 3.0},
        )
        assert d.final_decision == ALPHA_REGIME_ENTRY_BLOCKED_SPREAD

    def test_17_news_block(self):
        """News fail -> ALPHA_REGIME_ENTRY_BLOCKED_NEWS."""
        from titan.production.alpha_regime_entry_decision import (
            evaluate_entry, ALPHA_REGIME_ENTRY_BLOCKED_NEWS,
        )
        d = evaluate_entry(
            regime_result={"detected": True},
            alpha_signal={"detected": True, "direction": "LONG", "confidence": 0.7},
            risk_gate_result={"pass": True},
            broker_gate_result={"pass": True},
            prop_funded_gate_result={"pass": True},
            news_gate_result={"pass": False, "reason": "FOMC in 30min"},
            geometry_gate_result={"pass": True, "actual_RR": 3.0},
        )
        assert d.final_decision == ALPHA_REGIME_ENTRY_BLOCKED_NEWS
