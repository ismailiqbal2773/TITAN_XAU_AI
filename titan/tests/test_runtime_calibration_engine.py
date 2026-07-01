"""TITAN XAU AI - Sprint 9.9.3.46 Runtime Calibration Engine Tests"""
from __future__ import annotations

import inspect
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.runtime_calibration_engine import (
    CalibrationEngineResult,
    CalibrationMode,
    CalibrationSuggestion,
    RuntimeCalibrationEngine,
    SAFETY_INVARIANTS,
)


class TestModes:
    def test_01_all_modes_present(self):
        modes = [m.value for m in CalibrationMode]
        for m in [
            "OBSERVE_ONLY",
            "SUGGEST",
            "SHADOW_APPLY",
            "APPLY_DEMO_WITH_APPROVAL",
            "LIVE",
        ]:
            assert m in modes, f"Missing mode: {m}"


class TestDefaultMode:
    def test_02_default_mode_is_observe_only(self):
        eng = RuntimeCalibrationEngine()
        assert eng.mode == CalibrationMode.OBSERVE_ONLY

    def test_03_initial_non_default_mode_downgraded(self):
        """Even if caller requests LIVE, engine must default to OBSERVE_ONLY."""
        eng = RuntimeCalibrationEngine(mode=CalibrationMode.LIVE)
        assert eng.mode == CalibrationMode.OBSERVE_ONLY

    def test_04_observe_only_emits_no_suggestions(self):
        eng = RuntimeCalibrationEngine()
        eng.suggest("entry_threshold", 0.5, 0.55, reason="test")
        result = eng.run_cycle({"sample_count": 1000})
        assert result.mode == CalibrationMode.OBSERVE_ONLY
        assert result.applied is False
        assert len(result.suggestions) == 0


class TestModeEscalation:
    def test_05_escalate_to_suggest_allowed(self):
        eng = RuntimeCalibrationEngine()
        ok, blockers = eng.set_mode(CalibrationMode.SUGGEST)
        assert ok is True
        assert eng.mode == CalibrationMode.SUGGEST

    def test_06_escalate_to_live_without_ceo_blocked(self):
        eng = RuntimeCalibrationEngine()
        ok, blockers = eng.set_mode(
            CalibrationMode.LIVE, approved_by="someone"
        )
        assert ok is False
        assert any("ceo_approval" in b for b in blockers)
        assert eng.mode != CalibrationMode.LIVE

    def test_07_escalate_to_live_with_ceo_approved(self):
        eng = RuntimeCalibrationEngine()
        ok, blockers = eng.set_mode(
            CalibrationMode.LIVE,
            approved_by="ceo@example.com",
            ceo_approval=True,
        )
        assert ok is True
        assert eng.mode == CalibrationMode.LIVE

    def test_08_escalate_to_apply_demo_requires_approver(self):
        eng = RuntimeCalibrationEngine()
        ok, blockers = eng.set_mode(CalibrationMode.APPLY_DEMO_WITH_APPROVAL)
        assert ok is False
        assert any("approved_by" in b for b in blockers)
        # With approver
        ok2, _ = eng.set_mode(
            CalibrationMode.APPLY_DEMO_WITH_APPROVAL, approved_by="op@example.com"
        )
        assert ok2 is True
        assert eng.mode == CalibrationMode.APPLY_DEMO_WITH_APPROVAL


class TestSuggestions:
    def test_09_suggestion_has_required_fields(self):
        s = CalibrationSuggestion(
            parameter_name="entry_threshold",
            current_value=0.5,
            suggested_value=0.55,
            mode=CalibrationMode.SUGGEST,
        )
        for f in [
            "parameter_name",
            "current_value",
            "suggested_value",
            "mode",
            "approved",
            "approver",
            "reason",
            "delta",
            "timestamp_utc",
        ]:
            assert hasattr(s, f), f"Missing field: {f}"
        assert s.approved is False  # always False at construction
        assert s.delta == pytest.approx(0.05)

    def test_10_suggestion_delta_clamped_to_max_threshold_delta(self):
        eng = RuntimeCalibrationEngine()
        # Try a 50% delta - should be clamped to ±5%
        s = eng.suggest("entry_threshold", 0.5, 1.0, reason="too big")
        assert abs(s.delta) <= 0.06  # MAX_THRESHOLD_DELTA=0.05 + float tolerance
        assert "clamped" in s.reason


class TestApproveSuggestion:
    def test_11_approve_suggestion_requires_demo_or_live_mode(self):
        eng = RuntimeCalibrationEngine()
        eng.suggest("entry_threshold", 0.5, 0.55, reason="test")
        # OBSERVE_ONLY mode - cannot approve
        ok, blockers = eng.approve_suggestion("entry_threshold", approver="op")
        assert ok is False
        assert any("APPLY_DEMO_WITH_APPROVAL" in b or "LIVE" in b for b in blockers)

    def test_12_approve_suggestion_in_demo_mode(self):
        eng = RuntimeCalibrationEngine()
        eng.set_mode(CalibrationMode.SUGGEST)
        eng.suggest("entry_threshold", 0.5, 0.55, reason="test")
        eng.set_mode(
            CalibrationMode.APPLY_DEMO_WITH_APPROVAL, approved_by="op@example.com"
        )
        ok, _ = eng.approve_suggestion("entry_threshold", approver="op")
        assert ok is True


class TestRunCycle:
    def test_13_suggest_mode_emits_suggestions_without_applying(self):
        eng = RuntimeCalibrationEngine()
        eng.set_mode(CalibrationMode.SUGGEST)
        eng.suggest("entry_threshold", 0.5, 0.55, reason="test")
        result = eng.run_cycle({"sample_count": 1000})
        assert result.mode == CalibrationMode.SUGGEST
        assert len(result.suggestions) == 1
        assert result.applied is False
        assert result.applied_to == "none"

    def test_14_shadow_apply_applies_to_shadow(self):
        eng = RuntimeCalibrationEngine()
        eng.set_mode(CalibrationMode.SUGGEST)
        eng.suggest("entry_threshold", 0.5, 0.55, reason="test")
        eng.set_mode(CalibrationMode.SHADOW_APPLY)
        result = eng.run_cycle({"sample_count": 1000})
        assert result.mode == CalibrationMode.SHADOW_APPLY
        assert result.applied is True
        assert result.applied_to == "shadow"

    def test_15_insufficient_samples_blocks_cycle(self):
        eng = RuntimeCalibrationEngine()
        eng.set_mode(CalibrationMode.SUGGEST)
        result = eng.run_cycle({"sample_count": 100})  # < 500 minimum
        assert result.applied is False
        assert any("Insufficient" in b for b in result.blockers)


class TestSafetyInvariants:
    def test_16_no_metatrader5_import(self):
        from titan.production import runtime_calibration_engine
        src = inspect.getsource(runtime_calibration_engine)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_17_no_order_send_calls(self):
        from titan.production import runtime_calibration_engine
        src = inspect.getsource(runtime_calibration_engine)
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_18_no_forbidden_patterns(self):
        from titan.production import runtime_calibration_engine
        src_raw = inspect.getsource(runtime_calibration_engine)
        src = re.sub(r'"""[\s\S]*?"""', '""', src_raw)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        low = src.lower()
        low = low.replace("no_martingale", "").replace("no_grid", "")
        low = low.replace("no_averaging", "").replace("no_loss_based_lot_multiplier", "")
        forbidden = [
            "martingale",
            "grid_trade",
            "averaging_down",
            "double_lot",
            "add_position",
            "loss_based_lot_multiplier",
            "recovery_multiplier",
        ]
        found = [t for t in forbidden if t in low]
        assert found == [], f"Forbidden patterns found: {found}"

    def test_19_safety_invariants_constant(self):
        assert SAFETY_INVARIANTS["no_martingale"] is True
        assert SAFETY_INVARIANTS["no_grid"] is True
        assert SAFETY_INVARIANTS["no_averaging"] is True
        assert SAFETY_INVARIANTS["auto_promote_to_live"] is False
        assert SAFETY_INVARIANTS["silent_live_threshold_change"] is False

    def test_20_result_has_safety_fields(self):
        eng = RuntimeCalibrationEngine()
        result = eng.run_cycle({"sample_count": 1000})
        assert result.no_martingale is True
        assert result.no_grid is True
        assert result.no_averaging is True
        assert result.auto_promote_to_live is False
        assert result.silent_live_threshold_change is False
        assert result.human_approval_required is True

    def test_21_enforce_no_silent_live_threshold_change(self):
        eng = RuntimeCalibrationEngine()
        assert eng.enforce_no_silent_live_threshold_change() is False

    def test_22_enforce_no_auto_promotion_to_live(self):
        eng = RuntimeCalibrationEngine()
        assert eng.enforce_no_auto_promotion_to_live() is False

    def test_23_summary_returns_dict(self):
        eng = RuntimeCalibrationEngine()
        s = eng.summary()
        assert s["mode"] == "OBSERVE_ONLY"
        assert s["default_mode"] == "OBSERVE_ONLY"
        assert s["auto_promote_to_live"] is False
        assert s["silent_live_threshold_change"] is False
        assert s["no_martingale"] is True
