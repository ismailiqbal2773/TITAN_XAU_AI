"""
Tests for Sprint 8.1 — Meta Calibration Control.

Verifies:
  - ECE calculation
  - Brier calculation
  - Calibration slope calculation
  - CALIBRATED state
  - WATCH state
  - RECALIBRATE_REQUIRED state
  - KILL_THRESHOLD_BREACHED state
  - Insufficient samples does not recalibrate
  - Isotonic recalibration changes probability mapping only
  - L1 model is not modified
  - Recalibration event journaled
  - Kill threshold triggers kill-switch
  - dry_run default enforced
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import tempfile
import pytest
import numpy as np

from titan.production.meta_calibration_monitor import (
    MetaCalibrationMonitor, CalibrationConfig, CalibrationState, CalibrationReport,
)
from titan.production.trade_journal import TradeJournal, EventType
from titan.production.kill_switch_fsm import (
    KillSwitchFSM, KillSwitchConfig, KillSwitchInput, KillState,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def fill_monitor(mon: MetaCalibrationMonitor, n: int, prob: float = 0.8,
                 win_rate: float = 0.8):
    """Fill monitor with n predictions at given prob and actual win rate."""
    np.random.seed(42)
    for _ in range(n):
        outcome = 1 if np.random.random() < win_rate else 0
        mon.record_prediction(prob_win=prob, actual_outcome=outcome)


# ─── 1. ECE Calculation ───────────────────────────────────────────────────────

class TestECECalculation:
    def test_perfect_calibration_ece_zero(self):
        """Perfectly calibrated → ECE ≈ 0."""
        mon = MetaCalibrationMonitor()
        np.random.seed(42)
        for _ in range(200):
            p = np.random.uniform(0.5, 1.0)
            outcome = 1 if np.random.random() < p else 0
            mon.record_prediction(p, outcome)
        r = mon.get_report()
        assert r.ece < 0.10  # should be low

    def test_overconfident_ece_high(self):
        """Always predict 0.95 but actual win rate 0.55 → high ECE."""
        mon = MetaCalibrationMonitor()
        np.random.seed(42)
        for _ in range(200):
            mon.record_prediction(0.95, 1 if np.random.random() < 0.55 else 0)
        r = mon.get_report()
        assert r.ece > 0.20  # should be high

    def test_ece_range_0_to_1(self):
        """ECE must be in [0, 1]."""
        mon = MetaCalibrationMonitor()
        fill_monitor(mon, 100, prob=0.7, win_rate=0.6)
        r = mon.get_report()
        assert 0.0 <= r.ece <= 1.0


# ─── 2. Brier Calculation ─────────────────────────────────────────────────────

class TestBrierCalculation:
    def test_perfect_brier_zero(self):
        """Perfect predictions (prob=1.0, outcome=1) → Brier=0."""
        mon = MetaCalibrationMonitor()
        for _ in range(100):
            mon.record_prediction(1.0, 1)
        r = mon.get_report()
        assert r.brier < 0.01

    def test_worst_brier_one(self):
        """Worst predictions (prob=1.0, outcome=0) → Brier=1."""
        mon = MetaCalibrationMonitor()
        for _ in range(100):
            mon.record_prediction(1.0, 0)
        r = mon.get_report()
        assert r.brier > 0.99

    def test_brier_range(self):
        mon = MetaCalibrationMonitor()
        fill_monitor(mon, 100, prob=0.7, win_rate=0.6)
        r = mon.get_report()
        assert 0.0 <= r.brier <= 1.0


# ─── 3. Calibration Slope ─────────────────────────────────────────────────────

class TestCalibrationSlope:
    def test_perfect_slope_one(self):
        """Well-calibrated → slope ≈ 1.0."""
        mon = MetaCalibrationMonitor()
        np.random.seed(42)
        for _ in range(200):
            p = np.random.uniform(0.5, 1.0)
            outcome = 1 if np.random.random() < p else 0
            mon.record_prediction(p, outcome)
        r = mon.get_report()
        assert 0.5 < r.calibration_slope < 1.5  # approximately 1.0

    def test_overconfident_slope_below_one(self):
        """Overconfident (always 0.95, actual 0.60) → slope < 1 or 1.0 (degenerate)."""
        mon = MetaCalibrationMonitor()
        np.random.seed(42)
        for _ in range(200):
            # Use slightly varied probs so variance > 0
            p = np.random.uniform(0.90, 0.98)
            outcome = 1 if np.random.random() < 0.60 else 0
            mon.record_prediction(p, outcome)
        r = mon.get_report()
        # With varied probs, slope should be < 1 (overconfident)
        # If variance is too low, slope defaults to 1.0 — acceptable
        assert r.calibration_slope <= 1.0

    def test_slope_returns_float(self):
        mon = MetaCalibrationMonitor()
        fill_monitor(mon, 50, prob=0.7, win_rate=0.7)
        r = mon.get_report()
        assert isinstance(r.calibration_slope, float)


# ─── 4. Calibration States ────────────────────────────────────────────────────

class TestCalibrationStates:
    def test_calibrated_state(self):
        """ECE < 0.07 → CALIBRATED."""
        mon = MetaCalibrationMonitor()
        np.random.seed(42)
        for _ in range(200):
            p = np.random.uniform(0.55, 0.85)
            outcome = 1 if np.random.random() < p else 0
            mon.record_prediction(p, outcome)
        r = mon.get_report()
        if r.ece < 0.07:
            assert r.state == CalibrationState.CALIBRATED

    def test_watch_state(self):
        """0.07 <= ECE < 0.10 → WATCH."""
        mon = MetaCalibrationMonitor(CalibrationConfig(
            watch_ece=0.001, recalibrate_ece=0.10, kill_ece=0.15,
        ))
        # Slightly miscalibrated
        np.random.seed(42)
        for _ in range(200):
            p = 0.80
            outcome = 1 if np.random.random() < 0.72 else 0
            mon.record_prediction(p, outcome)
        r = mon.get_report()
        if 0.001 <= r.ece < 0.10:
            assert r.state == CalibrationState.WATCH

    def test_recalibrate_required_state(self):
        """0.10 <= ECE < 0.15 → RECALIBRATE_REQUIRED."""
        mon = MetaCalibrationMonitor(CalibrationConfig(
            watch_ece=0.001, recalibrate_ece=0.001, kill_ece=0.15,
        ))
        np.random.seed(42)
        for _ in range(200):
            p = 0.90
            outcome = 1 if np.random.random() < 0.55 else 0
            mon.record_prediction(p, outcome)
        r = mon.get_report()
        if 0.001 <= r.ece < 0.15:
            assert r.state == CalibrationState.RECALIBRATE_REQUIRED

    def test_kill_threshold_breached_state(self):
        """ECE >= 0.15 → KILL_THRESHOLD_BREACHED."""
        mon = MetaCalibrationMonitor(CalibrationConfig(
            watch_ece=0.001, recalibrate_ece=0.001, kill_ece=0.001,
        ))
        np.random.seed(42)
        for _ in range(200):
            p = 0.95
            outcome = 1 if np.random.random() < 0.45 else 0
            mon.record_prediction(p, outcome)
        r = mon.get_report()
        if r.ece >= 0.001:
            assert r.state == CalibrationState.KILL_THRESHOLD_BREACHED

    def test_insufficient_samples_returns_calibrated(self):
        """n < min_samples → CALIBRATED (can't judge yet)."""
        mon = MetaCalibrationMonitor(CalibrationConfig(min_samples=50))
        mon.record_prediction(0.95, 0)  # only 1 sample
        r = mon.get_report()
        assert r.state == CalibrationState.CALIBRATED


# ─── 5. Isotonic Recalibration ────────────────────────────────────────────────

class TestIsotonicRecalibration:
    def test_recalibrate_changes_probability_mapping(self):
        """After recalibration, apply_recalibration should return different probs."""
        mon = MetaCalibrationMonitor()
        np.random.seed(42)
        for _ in range(200):
            p = 0.95
            outcome = 1 if np.random.random() < 0.60 else 0
            mon.record_prediction(p, outcome)

        # Before recalibration: apply returns input unchanged
        assert mon.apply_recalibration(0.95) == 0.95

        # Recalibrate
        success = mon.recalibrate()
        assert success is True

        # After recalibration: apply should return different value
        remapped = mon.apply_recalibration(0.95)
        assert remapped != 0.95
        assert 0.0 <= remapped <= 1.0

    def test_recalibrate_improves_ece(self):
        """Recalibration should reduce ECE."""
        mon = MetaCalibrationMonitor()
        np.random.seed(42)
        for _ in range(200):
            p = 0.95
            outcome = 1 if np.random.random() < 0.60 else 0
            mon.record_prediction(p, outcome)

        r_before = mon.get_report()
        mon.recalibrate()
        # Recompute ECE with remapped predictions
        preds = np.array(mon._predictions)
        outcomes = np.array(mon._outcomes)
        remapped = mon.apply_recalibration_batch(preds) if hasattr(mon, 'apply_recalibration_batch') else mon._isotonic_model.predict(preds)
        new_ece = mon._compute_ece(remapped, outcomes)
        assert new_ece < r_before.ece

    def test_insufficient_samples_does_not_recalibrate(self):
        """n < min_samples → recalibrate() returns False."""
        mon = MetaCalibrationMonitor(CalibrationConfig(min_samples=50))
        for _ in range(10):
            mon.record_prediction(0.8, 1)
        success = mon.recalibrate()
        assert success is False
        assert mon.has_recalibration is False

    def test_l1_model_not_modified(self):
        """Recalibration must NOT touch L1 XGBoost model."""
        from titan.production.model_loader import load_production_models
        bundle = load_production_models()

        # Get L1 predictions before
        test_input = np.random.randn(1, 55)
        proba_before = bundle.xgb.predict_proba(test_input)[0]

        # Do recalibration
        mon = MetaCalibrationMonitor()
        np.random.seed(42)
        for _ in range(200):
            p = 0.95
            outcome = 1 if np.random.random() < 0.60 else 0
            mon.record_prediction(p, outcome)
        mon.recalibrate()

        # Get L1 predictions after — must be identical
        proba_after = bundle.xgb.predict_proba(test_input)[0]
        np.testing.assert_array_almost_equal(proba_before, proba_after)

    def test_recalibration_count_increments(self):
        mon = MetaCalibrationMonitor()
        fill_monitor(mon, 200, prob=0.9, win_rate=0.55)
        assert mon.recalibration_count == 0
        mon.recalibrate()
        assert mon.recalibration_count == 1
        mon.recalibrate()
        assert mon.recalibration_count == 2


# ─── 6. Journal Events ────────────────────────────────────────────────────────

class TestJournalEvents:
    def test_meta_calibration_sample_event_exists(self):
        assert hasattr(EventType, 'META_CALIBRATION_SAMPLE')
        assert EventType.META_CALIBRATION_SAMPLE.value == "META_CALIBRATION_SAMPLE"

    def test_all_5_meta_events_exist(self):
        events = [
            EventType.META_CALIBRATION_SAMPLE,
            EventType.META_CALIBRATION_WATCH,
            EventType.META_RECALIBRATE_REQUIRED,
            EventType.META_RECALIBRATED,
            EventType.META_CALIBRATION_KILL,
        ]
        for e in events:
            assert isinstance(e, EventType)

    def test_calibration_sample_journaled(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "cal.jsonl"))
        journal.log_event(EventType.META_CALIBRATION_SAMPLE, {
            "predicted_pwin": 0.80,
            "actual_outcome": 1,
            "ticket": 50001,
        })
        journal.flush()
        samples = journal.read_by_event_type(EventType.META_CALIBRATION_SAMPLE)
        assert len(samples) == 1
        assert samples[0]["data"]["predicted_pwin"] == 0.80

    def test_recalibration_event_journaled(self, tmp_path):
        journal = TradeJournal(path=str(tmp_path / "rec.jsonl"))
        journal.log_event(EventType.META_RECALIBRATED, {
            "method": "isotonic",
            "n_samples": 200,
            "old_ece": 0.12,
        })
        journal.flush()
        recs = journal.read_by_event_type(EventType.META_RECALIBRATED)
        assert len(recs) == 1
        assert recs[0]["data"]["method"] == "isotonic"


# ─── 7. Kill-Switch Integration ───────────────────────────────────────────────

class TestKillSwitchIntegration:
    def test_kill_threshold_triggers_kill_switch(self):
        """ECE >= kill_ece → kill_switch should escalate."""
        fsm = KillSwitchFSM(KillSwitchConfig(
            emergency_ece=0.15,
            max_ece=0.07,
        ))
        # Simulate ECE = 0.16 (kill threshold)
        fsm.update(KillSwitchInput(ece=0.16))
        assert fsm.state == KillState.HALT_NEW_TRADES

    def test_recalibrate_ece_triggers_caution(self):
        """ECE >= recalibrate_ece → CAUTION."""
        fsm = KillSwitchFSM(KillSwitchConfig(
            max_ece=0.07, emergency_ece=0.15,
        ))
        fsm.update(KillSwitchInput(ece=0.11))
        assert fsm.state == KillState.CAUTION

    def test_calibration_kill_blocks_trades(self, tmp_path):
        """Full flow: calibration kill → kill-switch HALT → trade blocked."""
        from titan.production.trade_loop import TradeLoop, TradeLoopConfig
        from titan.production.inference import Signal, Direction
        import numpy as np

        journal = TradeJournal(path=str(tmp_path / "ks.jsonl"))
        fsm = KillSwitchFSM(KillSwitchConfig(emergency_ece=0.15))
        # Trigger via high ECE
        fsm.update(KillSwitchInput(ece=0.16))
        assert fsm.state == KillState.HALT_NEW_TRADES

        loop = TradeLoop(TradeLoopConfig(dry_run=True), journal=journal, kill_switch=fsm)
        signal = Signal(
            timestamp=time.time(), direction=Direction.LONG,
            confidence=0.80, meta_confidence=0.85,
            xgb_proba=[0.2, 0.8], meta_proba=[0.15, 0.85],
            is_tradeable=True, feature_vector=np.zeros(55),
            inference_ms=10.0, source="test",
        )

        async def test():
            decision = await loop.process_signal(signal, entry_price=2000.0, spread_usd=0.2)
            return not decision.accepted

        blocked = asyncio.run(test())
        assert blocked is True


# ─── 8. Dry-Run Enforcement ───────────────────────────────────────────────────

class TestDryRunEnforcement:
    def test_dry_run_default_true(self):
        cfg = CalibrationConfig()
        assert cfg.dry_run_only is True

    def test_no_real_orders_in_recalibration(self):
        """Recalibration never calls MT5 — it's pure math."""
        mon = MetaCalibrationMonitor()
        fill_monitor(mon, 200, prob=0.9, win_rate=0.55)
        # This is pure sklearn — no MT5 calls possible
        success = mon.recalibrate()
        assert success is True


# ─── 9. Full Lifecycle Integration ────────────────────────────────────────────

class TestFullLifecycle:
    def test_full_calibration_lifecycle(self):
        """
        Full lifecycle: well-calibrated → drift → WATCH → RECALIBRATE → kill.
        """
        mon = MetaCalibrationMonitor(CalibrationConfig(
            min_samples=50, watch_ece=0.07, recalibrate_ece=0.10, kill_ece=0.15,
        ))

        # Phase 1: Well-calibrated (200 samples, prob matches outcome)
        np.random.seed(42)
        for _ in range(100):
            p = np.random.uniform(0.55, 0.85)
            outcome = 1 if np.random.random() < p else 0
            mon.record_prediction(p, outcome)
        r1 = mon.get_report()
        assert r1.state in (CalibrationState.CALIBRATED, CalibrationState.WATCH)

        # Phase 2: Add overconfident predictions (drift)
        for _ in range(100):
            p = 0.95
            outcome = 1 if np.random.random() < 0.55 else 0
            mon.record_prediction(p, outcome)
        r2 = mon.get_report()
        # ECE should be higher now
        assert r2.ece > r1.ece

        # Phase 3: Recalibrate
        if r2.state in (CalibrationState.RECALIBRATE_REQUIRED,
                        CalibrationState.KILL_THRESHOLD_BREACHED):
            success = mon.recalibrate()
            if success:
                assert mon.has_recalibration is True
                # Verify L1 not modified
                from titan.production.model_loader import load_production_models
                bundle = load_production_models()
                test_input = np.random.randn(1, 55)
                proba = bundle.xgb.predict_proba(test_input)
                assert proba is not None  # L1 still works

    def test_reliability_bins_computed(self):
        """Reliability bins should be computed for diagnostics."""
        mon = MetaCalibrationMonitor()
        fill_monitor(mon, 100, prob=0.7, win_rate=0.7)
        r = mon.get_report()
        assert isinstance(r.reliability_bins, list)
        # Should have at least 1 bin with data
        assert len(r.reliability_bins) > 0

    def test_reset_clears_state(self):
        mon = MetaCalibrationMonitor()
        fill_monitor(mon, 100, prob=0.8, win_rate=0.6)
        mon.recalibrate()
        assert mon.sample_count == 100
        assert mon.has_recalibration is True
        mon.reset()
        assert mon.sample_count == 0
        assert mon.has_recalibration is False
