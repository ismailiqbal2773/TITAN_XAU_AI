"""TITAN XAU AI — Sprint 9.9.3.32 Forward Observation Engine Tests"""
from __future__ import annotations
import inspect, json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.forward_observation import (
    ForwardObservationEngine, ForwardObservationEvent,
    ForwardObservationEventType, ForwardObservationSummary,
)


class TestEventNormalization:
    def test_01_signal_normalized(self):
        eng = ForwardObservationEngine()
        raw = {"event": "SIGNAL_CREATED", "symbol": "XAUUSD", "side": "BUY"}
        e = eng.normalize_event(raw)
        assert e.event_type == ForwardObservationEventType.SIGNAL_OBSERVED

    def test_02_execution_intent_normalized(self):
        eng = ForwardObservationEngine()
        raw = {"event": "DEMO_MICRO_ORDER_REQUESTED", "symbol": "XAUUSD"}
        e = eng.normalize_event(raw)
        assert e.event_type == ForwardObservationEventType.EXECUTION_INTENT_OBSERVED

    def test_03_safety_block_normalized(self):
        eng = ForwardObservationEngine()
        raw = {"event": "DEMO_MICRO_ORDER_FAILED", "reason": "reject"}
        e = eng.normalize_event(raw)
        assert e.event_type == ForwardObservationEventType.SAFETY_BLOCK_OBSERVED
        assert e.severity == "CRITICAL"
        assert e.safe is False

    def test_04_heartbeat_normalized(self):
        eng = ForwardObservationEngine()
        raw = {"event": "DEMO_MICRO_FULL_CYCLE_PASS"}
        e = eng.normalize_event(raw)
        assert e.event_type == ForwardObservationEventType.HEARTBEAT_OBSERVED

    def test_05_exit_intent_normalized(self):
        eng = ForwardObservationEngine()
        raw = {"event": "ADAPTER_SLTP_MODIFY_RESULT", "retcode": 10009}
        e = eng.normalize_event(raw)
        assert e.event_type == ForwardObservationEventType.EXIT_INTENT_OBSERVED

    def test_06_broker_health_normalized(self):
        eng = ForwardObservationEngine()
        raw = {"event": "ADAPTER_BROKER_STATE_SNAPSHOT"}
        e = eng.normalize_event(raw)
        assert e.event_type == ForwardObservationEventType.BROKER_HEALTH_OBSERVED

    def test_07_malformed_event_becomes_unknown(self):
        eng = ForwardObservationEngine()
        e = eng.normalize_event({})
        assert e.event_type == ForwardObservationEventType.UNKNOWN

    def test_08_exception_returns_unknown(self):
        eng = ForwardObservationEngine()
        e = eng.normalize_event(None)  # type: ignore
        assert e.event_type == ForwardObservationEventType.UNKNOWN
        assert e.safe is False

    def test_09_inferred_signal_from_name(self):
        eng = ForwardObservationEngine()
        raw = {"event": "CUSTOM_SIGNAL_DETECTED"}
        e = eng.normalize_event(raw)
        assert e.event_type == ForwardObservationEventType.SIGNAL_OBSERVED


class TestSummarize:
    def _events(self, types: list[ForwardObservationEventType]) -> list[ForwardObservationEvent]:
        return [ForwardObservationEvent(event_type=t, timestamp_utc=f"2026-06-29T10:0{i}:00Z")
                for i, t in enumerate(types)]

    def test_10_signal_count(self):
        eng = ForwardObservationEngine()
        s = eng.summarize(self._events([
            ForwardObservationEventType.SIGNAL_OBSERVED,
            ForwardObservationEventType.SIGNAL_OBSERVED,
        ]))
        assert s.signal_count == 2

    def test_11_execution_intent_count(self):
        eng = ForwardObservationEngine()
        s = eng.summarize(self._events([ForwardObservationEventType.EXECUTION_INTENT_OBSERVED]))
        assert s.execution_intent_count == 1

    def test_12_exit_intent_count(self):
        eng = ForwardObservationEngine()
        s = eng.summarize(self._events([ForwardObservationEventType.EXIT_INTENT_OBSERVED]))
        assert s.exit_intent_count == 1

    def test_13_safety_block_count_and_blockers(self):
        eng = ForwardObservationEngine()
        events = [ForwardObservationEvent(
            event_type=ForwardObservationEventType.SAFETY_BLOCK_OBSERVED,
            severity="CRITICAL", safe=False, reason="test block",
            source="test", timestamp_utc="2026-06-29T10:00:00Z",
        )]
        s = eng.summarize(events)
        assert s.safety_block_count == 1
        assert s.safe_to_continue_observation is False
        assert len(s.blockers) == 1

    def test_14_heartbeat_count(self):
        eng = ForwardObservationEngine()
        s = eng.summarize(self._events([ForwardObservationEventType.HEARTBEAT_OBSERVED]))
        assert s.heartbeat_count == 1

    def test_15_no_events_summary(self):
        eng = ForwardObservationEngine()
        s = eng.summarize([])
        assert s.total_events == 0
        assert s.safe_to_continue_observation is True
        assert len(s.warnings) >= 1

    def test_16_safe_summary_no_blockers(self):
        eng = ForwardObservationEngine()
        s = eng.summarize(self._events([
            ForwardObservationEventType.SIGNAL_OBSERVED,
            ForwardObservationEventType.HEARTBEAT_OBSERVED,
        ]))
        assert s.safe_to_continue_observation is True
        assert len(s.blockers) == 0


class TestObservationGaps:
    def test_17_gap_detected(self):
        eng = ForwardObservationEngine()
        events = [
            ForwardObservationEvent(timestamp_utc="2026-06-29T10:00:00Z"),
            ForwardObservationEvent(timestamp_utc="2026-06-29T12:00:00Z"),  # 2h gap
        ]
        gaps = eng.detect_observation_gaps(events, max_gap_seconds=3600)
        assert len(gaps) == 1
        assert gaps[0].event_type == ForwardObservationEventType.OBSERVATION_GAP

    def test_18_no_gap_when_close(self):
        eng = ForwardObservationEngine()
        events = [
            ForwardObservationEvent(timestamp_utc="2026-06-29T10:00:00Z"),
            ForwardObservationEvent(timestamp_utc="2026-06-29T10:30:00Z"),  # 30min
        ]
        gaps = eng.detect_observation_gaps(events, max_gap_seconds=3600)
        assert len(gaps) == 0


class TestLoadFromJsonl:
    def test_19_load_events_from_file(self, tmp_path):
        eng = ForwardObservationEngine()
        jpath = tmp_path / "test.jsonl"
        jpath.write_text(json.dumps({"event": "SIGNAL_CREATED", "symbol": "XAUUSD"}) + "\n"
                          + json.dumps({"event": "DEMO_MICRO_FULL_CYCLE_PASS"}) + "\n")
        events = eng.load_events_from_jsonl([str(jpath)])
        assert len(events) == 2
        assert events[0].event_type == ForwardObservationEventType.SIGNAL_OBSERVED

    def test_20_missing_file_returns_empty(self):
        eng = ForwardObservationEngine()
        events = eng.load_events_from_jsonl(["/nonexistent/path.jsonl"])
        assert len(events) == 0

    def test_21_malformed_lines_skipped(self, tmp_path):
        eng = ForwardObservationEngine()
        jpath = tmp_path / "test.jsonl"
        jpath.write_text('{"event": "SIGNAL_CREATED"}\nNOT_JSON\n{"bad": true}\n')
        events = eng.load_events_from_jsonl([str(jpath)])
        # SIGNAL_CREATED normalizes to SIGNAL_OBSERVED
        # NOT_JSON is skipped (not valid JSON)
        # {"bad": true} has no "event" key → normalizes to UNKNOWN
        assert len(events) == 2  # SIGNAL + UNKNOWN


class TestNoMT5:
    def test_22_no_metatrader5_import(self):
        from titan.production import forward_observation
        src = inspect.getsource(forward_observation)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_23_no_order_send(self):
        from titan.production import forward_observation
        src = inspect.getsource(forward_observation)
        assert "order_send" not in src
        assert "MT5ExecutionAdapter" not in src
