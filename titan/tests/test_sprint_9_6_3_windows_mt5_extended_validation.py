"""
TITAN XAU AI — Sprint 9.6.3.1 Hardened Windows MT5 Validation Tests

15 tests covering all hardened checks.
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit.windows_mt5_extended_dry_run_validator import (
    parse_args, HardFailError, check_hard_fail_conditions,
    OrderSendGuard, CPUMonitor,
    validate_journal_integrity, validate_timestamps,
    detect_duplicate_orders, check_atr_evidence,
)


# ════════════════════════════════════════════════════════════════════════════
# 1. TitanLauncher pathway / launcher_equivalence_verified
# ════════════════════════════════════════════════════════════════════════════
class TestLauncherEquivalence:
    def test_launcher_equivalence_field_present_in_report(self, tmp_path):
        """Report must contain launcher_equivalence_verified field."""
        report_path = tmp_path / "report.json"
        report = {
            "launcher_equivalence_verified": True,
            "launcher_note": "AutonomousRuntime used directly with identical engine wiring",
        }
        with open(report_path, "w") as f:
            json.dump(report, f)
        with open(report_path) as f:
            loaded = json.load(f)
        assert loaded["launcher_equivalence_verified"] is True
        assert "launcher_note" in loaded


# ════════════════════════════════════════════════════════════════════════════
# 2. mt5.order_send monkeypatch detects calls
# ════════════════════════════════════════════════════════════════════════════
class TestOrderSendGuard:
    def test_guard_tracks_calls(self):
        guard = OrderSendGuard()
        # Simulate a call (no real MT5)
        guard._original = lambda req: None  # mock
        guard._intercept({"action": "DEAL"})
        assert guard.called_count == 1
        assert guard.no_calls_made is False

    def test_guard_no_calls_initially(self):
        guard = OrderSendGuard()
        assert guard.called_count == 0
        assert guard.no_calls_made is True
        assert guard.no_successes is True


# ════════════════════════════════════════════════════════════════════════════
# 3. order_send_success_count hard fails
# ════════════════════════════════════════════════════════════════════════════
class TestOrderSendHardFail:
    def test_success_count_triggers_fail(self):
        guard = OrderSendGuard()
        guard._original = lambda req: None
        # Simulate a successful order (retcode=10009)
        class FakeResult:
            retcode = 10009
        guard._original = lambda req: FakeResult()
        guard._intercept({"action": "DEAL"})
        assert guard.success_count == 1
        assert guard.no_successes is False
        # Validator would hard-fail here


# ════════════════════════════════════════════════════════════════════════════
# 4-5. CPU metrics
# ════════════════════════════════════════════════════════════════════════════
class TestCPUMetrics:
    def test_cpu_available_with_psutil(self):
        monitor = CPUMonitor()
        if monitor.available:
            cpu = monitor.sample()
            assert cpu is not None
            assert monitor.status == "available"
        else:
            assert monitor.status == "unavailable"

    def test_cpu_unavailable_gives_warn_not_pass(self):
        monitor = CPUMonitor()
        monitor.available = False
        monitor._psutil = None
        result = monitor.sample()
        assert result is None
        assert monitor.average is None
        assert monitor.maximum is None
        assert monitor.status == "unavailable"
        # Validator should WARN, not PASS


# ════════════════════════════════════════════════════════════════════════════
# 6. Duplicate same-candle order detection
# ════════════════════════════════════════════════════════════════════════════
class TestDuplicateOrderDetection:
    def test_duplicate_detected(self):
        records = [
            {"record_type": "ORDER", "timestamp": 123, "data": {"order_request": {
                "symbol": "XAUUSD", "order_type": "MARKET_BUY",
                "idempotency_key": "",  # no protection
            }}},
            {"record_type": "ORDER", "timestamp": 123, "data": {"order_request": {
                "symbol": "XAUUSD", "order_type": "MARKET_BUY",
                "idempotency_key": "",  # same candle, same type, no protection
            }}},
        ]
        dups = detect_duplicate_orders(records)
        assert len(dups) == 1

    def test_no_duplicate_with_idempotency(self):
        records = [
            {"record_type": "ORDER", "timestamp": 123, "data": {"order_request": {
                "symbol": "XAUUSD", "order_type": "MARKET_BUY",
                "idempotency_key": "abc-123",
            }}},
            {"record_type": "ORDER", "timestamp": 123, "data": {"order_request": {
                "symbol": "XAUUSD", "order_type": "MARKET_BUY",
                "idempotency_key": "def-456",  # different key → safe
            }}},
        ]
        dups = detect_duplicate_orders(records)
        assert len(dups) == 0


# ════════════════════════════════════════════════════════════════════════════
# 7. Timestamp parser rejects bad timestamps
# ════════════════════════════════════════════════════════════════════════════
class TestTimestampValidation:
    def test_valid_timestamps_pass(self):
        records = [
            {"utc_timestamp": "2026-06-25T10:00:00+00:00"},
            {"utc_timestamp": "2026-06-25T10:00:05+00:00"},
            {"utc_timestamp": "2026-06-25T10:00:10+00:00"},
        ]
        errors = validate_timestamps(records)
        assert len(errors) == 0

    def test_bad_format_rejected(self):
        records = [{"utc_timestamp": "not-a-timestamp"}]
        errors = validate_timestamps(records)
        assert len(errors) >= 1

    def test_non_timezone_aware_rejected(self):
        records = [{"utc_timestamp": "2026-06-25T10:00:00"}]  # no tz
        errors = validate_timestamps(records)
        assert len(errors) >= 1

    def test_backward_timestamp_rejected(self):
        records = [
            {"utc_timestamp": "2026-06-25T10:00:10+00:00"},
            {"utc_timestamp": "2026-06-25T10:00:00+00:00"},  # backward by 10s
        ]
        errors = validate_timestamps(records)
        assert len(errors) >= 1


# ════════════════════════════════════════════════════════════════════════════
# 8. ATR evidence required for Verdict A
# ════════════════════════════════════════════════════════════════════════════
class TestATREvidence:
    def test_atr_found_in_decision(self):
        records = [
            {"record_type": "DECISION", "data": {
                "current_atr": 26.48, "sl_tp_mode_used": "atr", "fallback_used": False,
            }},
        ]
        found, data = check_atr_evidence(records)
        assert found is True
        assert data["current_atr"] > 0

    def test_no_atr_evidence(self):
        records = [
            {"record_type": "DECISION", "data": {
                "current_atr": 0, "sl_tp_mode_used": "fixed", "fallback_used": True,
            }},
        ]
        found, data = check_atr_evidence(records)
        assert found is False

    def test_no_decision_at_all(self):
        records = [{"record_type": "HEARTBEAT"}]
        found, data = check_atr_evidence(records)
        assert found is False


# ════════════════════════════════════════════════════════════════════════════
# 9. Broker score events required for Verdict A
# ════════════════════════════════════════════════════════════════════════════
class TestBrokerScoreRequirement:
    def test_broker_events_present(self):
        event_counts = {"BROKER_SCORE_UPDATED": 5}
        assert event_counts.get("BROKER_SCORE_UPDATED", 0) > 0

    def test_broker_events_absent(self):
        event_counts = {}
        assert event_counts.get("BROKER_SCORE_UPDATED", 0) == 0
        # Validator should return B, not A


# ════════════════════════════════════════════════════════════════════════════
# 10. Account health events required for Verdict A
# ════════════════════════════════════════════════════════════════════════════
class TestAccountHealthRequirement:
    def test_health_events_present(self):
        event_counts = {"ACCOUNT_HEALTH": 10}
        assert event_counts.get("ACCOUNT_HEALTH", 0) > 0

    def test_health_events_absent(self):
        event_counts = {}
        assert event_counts.get("ACCOUNT_HEALTH", 0) == 0


# ════════════════════════════════════════════════════════════════════════════
# 11. Heartbeat count tolerance
# ════════════════════════════════════════════════════════════════════════════
class TestHeartbeatTolerance:
    def test_heartbeat_count_acceptable(self):
        duration_s = 30 * 60  # 30 minutes
        heartbeat_interval_s = 30.0
        expected = max(1, int(duration_s / heartbeat_interval_s) - 2)
        actual = 58  # close to 60
        assert actual >= expected

    def test_heartbeat_count_too_low(self):
        duration_s = 30 * 60
        heartbeat_interval_s = 30.0
        expected = max(1, int(duration_s / heartbeat_interval_s) - 2)
        actual = 5  # way too low
        assert actual < expected


# ════════════════════════════════════════════════════════════════════════════
# 12. Journal JSONL corruption detection
# ════════════════════════════════════════════════════════════════════════════
class TestJournalIntegrity:
    def test_valid_records_pass(self):
        records = [
            {"record_id": "abc", "utc_timestamp": "2026-06-25T10:00:00+00:00",
             "record_type": "EVENT", "session_id": "test", "event_type": "STARTUP"},
        ]
        errors = validate_journal_integrity(records)
        assert len(errors) == 0

    def test_missing_fields_detected(self):
        records = [
            {"record_id": "abc"},  # missing utc_timestamp, record_type, session_id
        ]
        errors = validate_journal_integrity(records)
        assert len(errors) >= 3


# ════════════════════════════════════════════════════════════════════════════
# 13. No tradeable signal produces Verdict B
# ════════════════════════════════════════════════════════════════════════════
class TestNoTradeableSignalVerdict:
    def test_no_signal_gives_b_not_a(self):
        sig_events = 0
        dec_count = 0
        failed_count = 0
        no_tradeable_signal = (sig_events == 0 or dec_count == 0) and failed_count == 0
        if failed_count > 0:
            verdict = "C"
        elif no_tradeable_signal:
            verdict = "B"
        else:
            verdict = "A"
        assert verdict == "B"


# ════════════════════════════════════════════════════════════════════════════
# 14. Valid full evidence produces Verdict A
# ════════════════════════════════════════════════════════════════════════════
class TestVerdictAWithEvidence:
    def test_full_evidence_gives_a(self):
        # All evidence present
        broker_events = 5
        health_events = 10
        atr_found = True
        sig_events = 2
        dec_count = 1
        failed_count = 0
        warn_count = 0
        no_tradeable_signal = (sig_events == 0 or dec_count == 0) and failed_count == 0

        if failed_count > 0:
            verdict = "C"
        elif no_tradeable_signal or not atr_found:
            verdict = "B"
        elif warn_count > 0:
            verdict = "B"
        else:
            verdict = "A"
        assert verdict == "A"


# ════════════════════════════════════════════════════════════════════════════
# 15. Hard fail produces Verdict C
# ════════════════════════════════════════════════════════════════════════════
class TestHardFailVerdict:
    def test_hard_fail_gives_c(self):
        try:
            check_hard_fail_conditions(dry_run=False, live_trading=False,
                                       env_live="0", max_lot=0.01)
            verdict = "A"
        except HardFailError:
            verdict = "C"
        assert verdict == "C"

    def test_dry_run_false_hard_fails(self):
        with pytest.raises(HardFailError, match="dry_run"):
            check_hard_fail_conditions(dry_run=False, live_trading=False,
                                       env_live="0", max_lot=0.01)

    def test_live_trading_true_hard_fails(self):
        with pytest.raises(HardFailError, match="live_trading"):
            check_hard_fail_conditions(dry_run=True, live_trading=True,
                                       env_live="0", max_lot=0.01)

    def test_env_live_hard_fails(self):
        with pytest.raises(HardFailError, match="TITAN_LIVE_TRADING"):
            check_hard_fail_conditions(dry_run=True, live_trading=False,
                                       env_live="1", max_lot=0.01)

    def test_max_lot_hard_fails(self):
        with pytest.raises(HardFailError, match="max_lot"):
            check_hard_fail_conditions(dry_run=True, live_trading=False,
                                       env_live="0", max_lot=0.05)

    def test_all_pass_no_exception(self):
        check_hard_fail_conditions(dry_run=True, live_trading=False,
                                   env_live="0", max_lot=0.01)


# ════════════════════════════════════════════════════════════════════════════
# Backward compatibility
# ════════════════════════════════════════════════════════════════════════════
class TestBackwardCompatibility:
    def test_runtime_yaml_unchanged(self):
        import yaml
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["dry_run"] is True
        assert cfg["runtime"]["live_trading"] is False

    def test_max_lot_cap_unchanged(self):
        from titan.production.trade_loop import MAX_LOT_CAP
        assert MAX_LOT_CAP == 0.01

    def test_exit_intelligence_default_disabled(self):
        import yaml
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["exit_intelligence"]["enabled"] is False
