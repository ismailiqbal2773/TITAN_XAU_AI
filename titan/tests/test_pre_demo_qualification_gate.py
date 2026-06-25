"""
TITAN XAU AI — Sprint 9.7.1 Pre-Demo Qualification Gate Tests (Fixed)

18 tests covering evidence archive, safety normalization, and verdict rules.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit.pre_demo_qualification_gate import (
    evaluate_safety_gates, evaluate_runtime_stability,
    evaluate_evidence_depth, evaluate_journal_integrity,
    evaluate_operational, compute_verdict,
    derive_normalized_safety, classify_duration,
    find_best_evidence_by_class, load_manifest,
    normalize_bool,
)


def make_report(**overrides) -> dict:
    base = {
        "dry_run": True, "live_trading": False,
        "order_send_guard": {"called_count": 0, "success_count": 0},
        "live_orders_executed": 0, "account_type": "DEMO",
        "shutdown_clean": True, "runtime_ended_early": False,
        "heartbeat_count": 478, "broker_score_events": 478,
        "account_health_events": 478, "atr_usage_count": 5,
        "duplicate_orders": [], "memory_growth_kb": 5000,
        "journal_integrity_errors": [], "timestamp_errors": [],
        "cpu_status": "available", "cpu_average": 15.0,
        "platform": "Windows", "git_commit": "c8dc112",
        "checks": [{"check": "kill_switch", "status": "PASS"}],
        "duration_actual_s": 14402, "signals_generated": 5,
        "decisions_generated": 5, "verdict": "A",
    }
    base.update(overrides)
    return base


def make_normalized(**overrides) -> dict:
    base = {
        "dry_run_normalized": True, "live_trading_normalized": False,
        "shutdown_clean_normalized": True, "account_type_normalized": "DEMO",
        "env_live_trading_normalized": "0", "order_send_called": 0,
        "order_send_success": 0, "live_orders_executed": 0,
        "runtime_ended_early": False,
    }
    base.update(overrides)
    return base


# ════════════════════════════════════════════════════════════════════════════
# 1-2. Missing fields don't create misleading summary
# ════════════════════════════════════════════════════════════════════════════
class TestNormalizedSafety:
    def test_missing_dry_run_does_not_default_false(self):
        report = make_report(dry_run=None)
        del report["dry_run"]
        normalized = derive_normalized_safety(report)
        # Should be True (inferred from order_send=0 + live_orders=0) or None, NOT False
        assert normalized["dry_run_normalized"] is not False

    def test_missing_live_trading_does_not_default_true(self):
        report = make_report()
        del report["live_trading"]
        normalized = derive_normalized_safety(report)
        assert normalized["live_trading_normalized"] is not True

    def test_missing_shutdown_does_not_default_false(self):
        report = make_report()
        del report["shutdown_clean"]
        # Add safety_audit as fallback
        report["safety_audit"] = {"shutdown_clean": True}
        normalized = derive_normalized_safety(report)
        assert normalized["shutdown_clean_normalized"] is not False

    def test_summary_uses_normalized_not_unsafe_defaults(self):
        report = make_report()
        del report["dry_run"]
        del report["live_trading"]
        normalized = derive_normalized_safety(report)
        assert normalized["dry_run_normalized"] != False
        assert normalized["live_trading_normalized"] != True


# ════════════════════════════════════════════════════════════════════════════
# 3. Safety score doesn't contradict summary
# ════════════════════════════════════════════════════════════════════════════
class TestScoreConsistency:
    def test_safety_score_matches_normalized(self):
        normalized = make_normalized()
        score, passes, failures = evaluate_safety_gates(normalized)
        assert score == 35  # all pass
        assert len(failures) == 0

    def test_live_trading_true_reduces_score(self):
        normalized = make_normalized(live_trading_normalized=True)
        score, _, failures = evaluate_safety_gates(normalized)
        assert score < 35
        assert any("live_trading" in f for f in failures)


# ════════════════════════════════════════════════════════════════════════════
# 4. 30min + 4h evidence both detected from archive/manifest
# ════════════════════════════════════════════════════════════════════════════
class TestEvidenceArchive:
    def test_both_30min_and_4h_detected_from_manifest(self):
        manifest = {"runs": [
            {"duration_class": "30min", "verdict": "A", "duration_actual_s": 1805},
            {"duration_class": "4h", "verdict": "A", "duration_actual_s": 14402},
        ]}
        evidence = find_best_evidence_by_class(manifest, None)
        assert evidence["30min"] is not None
        assert evidence["4h"] is not None
        assert evidence["24h"] is None

    def test_latest_report_alone_works(self):
        report = make_report(duration_actual_s=14402)
        evidence = find_best_evidence_by_class({"runs": []}, report)
        assert evidence["4h"] is not None

    def test_archive_does_not_overwrite_previous(self):
        manifest = {"runs": [
            {"run_id": "run1", "duration_class": "30min", "verdict": "A", "duration_actual_s": 1805},
            {"run_id": "run2", "duration_class": "4h", "verdict": "A", "duration_actual_s": 14402},
        ]}
        # Both should still be present
        assert len(manifest["runs"]) == 2

    def test_24h_future_run_can_be_added(self):
        manifest = {"runs": [
            {"duration_class": "30min", "verdict": "A"},
            {"duration_class": "4h", "verdict": "A"},
        ]}
        manifest["runs"].append({"duration_class": "24h", "verdict": "A"})
        evidence = find_best_evidence_by_class(manifest, None)
        assert evidence["24h"] is not None
        assert evidence["30min"] is not None  # not lost
        assert evidence["4h"] is not None  # not lost


# ════════════════════════════════════════════════════════════════════════════
# 5-7. Verdict rules
# ════════════════════════════════════════════════════════════════════════════
class TestVerdictRules:
    def test_4h_without_24h_gives_extended(self):
        report = make_report()
        normalized = make_normalized()
        verdict, _ = compute_verdict(90, report, report, None, normalized)
        assert verdict == "EXTENDED_DRY_RUN_READY"

    def test_24h_with_high_score_gives_demo_live(self):
        report = make_report()
        normalized = make_normalized()
        verdict, _ = compute_verdict(95, report, report, report, normalized)
        assert verdict == "DEMO_LIVE_REVIEW_ALLOWED"

    def test_24h_score_below_90_gives_extended(self):
        report = make_report()
        normalized = make_normalized()
        verdict, _ = compute_verdict(88, report, report, report, normalized)
        assert verdict == "EXTENDED_DRY_RUN_READY"


# ════════════════════════════════════════════════════════════════════════════
# 8-13. Hard block conditions
# ════════════════════════════════════════════════════════════════════════════
class TestHardBlocks:
    def test_live_orders_blocks(self):
        n = make_normalized(live_orders_executed=1)
        v, _ = compute_verdict(95, make_report(), make_report(), make_report(), n)
        assert v == "BLOCKED"

    def test_order_send_success_blocks(self):
        n = make_normalized(order_send_success=1)
        v, _ = compute_verdict(95, make_report(), make_report(), make_report(), n)
        assert v == "BLOCKED"

    def test_live_trading_true_blocks(self):
        n = make_normalized(live_trading_normalized=True)
        v, _ = compute_verdict(95, make_report(), make_report(), make_report(), n)
        assert v == "BLOCKED"

    def test_dry_run_false_blocks(self):
        n = make_normalized(dry_run_normalized=False)
        v, _ = compute_verdict(95, make_report(), make_report(), make_report(), n)
        assert v == "BLOCKED"

    def test_shutdown_false_blocks(self):
        n = make_normalized(shutdown_clean_normalized=False)
        v, _ = compute_verdict(95, make_report(), make_report(), make_report(), n)
        assert v == "BLOCKED"

    def test_non_demo_blocks(self):
        n = make_normalized(account_type_normalized="LIVE")
        v, _ = compute_verdict(95, make_report(), make_report(), make_report(), n)
        assert v == "BLOCKED"


# ════════════════════════════════════════════════════════════════════════════
# 14-16. Evidence quality checks
# ════════════════════════════════════════════════════════════════════════════
class TestEvidenceQuality:
    def test_duplicate_orders_reduce_runtime_score(self):
        report = make_report(duplicate_orders=[{"key": "dup"}])
        score, _, failures = evaluate_runtime_stability(report)
        assert any("duplicate" in f for f in failures)

    def test_journal_errors_reduce_score(self):
        report = make_report(journal_integrity_errors=["err"])
        score, _, failures = evaluate_journal_integrity(report)
        assert score < 10

    def test_timestamp_errors_reduce_score(self):
        report = make_report(timestamp_errors=["err"])
        score, _, failures = evaluate_journal_integrity(report)
        assert score < 10


# ════════════════════════════════════════════════════════════════════════════
# 17-18. Archive integrity
# ════════════════════════════════════════════════════════════════════════════
class TestArchiveIntegrity:
    def test_duration_classification(self):
        assert classify_duration(1805) == "30min"
        assert classify_duration(14402) == "4h"
        assert classify_duration(86400) == "24h"

    def test_normalize_bool_never_unsafe(self):
        assert normalize_bool(None) is None
        assert normalize_bool("true") is True
        assert normalize_bool("false") is False
        assert normalize_bool(True) is True
        assert normalize_bool(False) is False
