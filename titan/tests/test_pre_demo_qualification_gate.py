"""
TITAN XAU AI — Sprint 9.7 Pre-Demo Qualification Gate Tests
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
    report_has_live_orders, report_has_order_send_success,
    load_evidence_run,
)


def make_report(**overrides) -> dict:
    """Build a synthetic evidence report for testing."""
    base = {
        "dry_run": True,
        "live_trading": False,
        "env_live_trading": "0",
        "order_send_guard": {"called_count": 0, "success_count": 0},
        "live_orders_executed": 0,
        "account_type": "DEMO",
        "shutdown_clean": True,
        "runtime_ended_early": False,
        "heartbeat_count": 478,
        "broker_score_events": 478,
        "account_health_events": 478,
        "dynamic_risk_active": True,
        "atr_usage_count": 5,
        "duplicate_orders": [],
        "memory_growth_kb": 5000,
        "journal_integrity_errors": [],
        "timestamp_errors": [],
        "cpu_status": "available",
        "cpu_average": 15.0,
        "platform": "Windows",
        "git_commit": "c8dc112",
        "checks": [{"check": "kill_switch", "status": "PASS"}],
        "duration_actual_s": 14402,
        "signals_generated": 5,
        "decisions_generated": 5,
    }
    base.update(overrides)
    return base


# ════════════════════════════════════════════════════════════════════════════
# 1. 4h A evidence without 24h = EXTENDED_DRY_RUN_READY
# ════════════════════════════════════════════════════════════════════════════
class TestExtendedDryRunReady:
    def test_4h_without_24h_gives_extended(self):
        report = make_report()
        score = 90  # high score
        verdict, reason = compute_verdict(score, report, report, None, [])
        assert verdict == "EXTENDED_DRY_RUN_READY"
        assert "4h" in reason

    def test_4h_with_24h_gives_demo_live(self):
        report = make_report()
        score = 95
        verdict, reason = compute_verdict(score, report, report, report, [])
        assert verdict == "DEMO_LIVE_REVIEW_ALLOWED"


# ════════════════════════════════════════════════════════════════════════════
# 2. 24h A evidence present = DEMO_LIVE_REVIEW_ALLOWED
# ════════════════════════════════════════════════════════════════════════════
class TestDemoLiveReview:
    def test_24h_with_high_score_gives_demo_live(self):
        report = make_report()
        score = 92
        verdict, reason = compute_verdict(score, report, report, report, [])
        assert verdict == "DEMO_LIVE_REVIEW_ALLOWED"
        assert "24h" in reason

    def test_24h_but_low_score_gives_continue(self):
        report = make_report()
        score = 78
        verdict, reason = compute_verdict(score, report, report, report, [])
        assert verdict == "CONTINUE_DRY_RUN"


# ════════════════════════════════════════════════════════════════════════════
# 3. Any live_orders_executed > 0 = BLOCKED
# ════════════════════════════════════════════════════════════════════════════
class TestLiveOrdersBlocked:
    def test_live_orders_blocks(self):
        report = make_report(live_orders_executed=1)
        assert report_has_live_orders(report) is True
        verdict, reason = compute_verdict(95, report, report, report, [])
        assert verdict == "BLOCKED"

    def test_zero_live_orders_ok(self):
        report = make_report(live_orders_executed=0)
        assert report_has_live_orders(report) is False


# ════════════════════════════════════════════════════════════════════════════
# 4. order_send success > 0 = BLOCKED
# ════════════════════════════════════════════════════════════════════════════
class TestOrderSendBlocked:
    def test_order_send_success_blocks(self):
        report = make_report(order_send_guard={"called_count": 1, "success_count": 1})
        assert report_has_order_send_success(report) is True
        verdict, reason = compute_verdict(95, report, report, report, [])
        assert verdict == "BLOCKED"

    def test_zero_success_ok(self):
        report = make_report(order_send_guard={"called_count": 0, "success_count": 0})
        assert report_has_order_send_success(report) is False


# ════════════════════════════════════════════════════════════════════════════
# 5. live_trading true = BLOCKED
# ════════════════════════════════════════════════════════════════════════════
class TestLiveTradingBlocked:
    def test_live_trading_true_blocks(self):
        report = make_report(live_trading=True)
        score, passes, failures = evaluate_safety_gates(report)
        verdict, reason = compute_verdict(95, report, report, report, failures)
        assert verdict == "BLOCKED"


# ════════════════════════════════════════════════════════════════════════════
# 6. shutdown_clean false = BLOCKED
# ════════════════════════════════════════════════════════════════════════════
class TestShutdownBlocked:
    def test_shutdown_not_clean_blocks(self):
        report = make_report(shutdown_clean=False)
        score, passes, failures = evaluate_safety_gates(report)
        verdict, reason = compute_verdict(95, report, report, report, failures)
        assert verdict == "BLOCKED"


# ════════════════════════════════════════════════════════════════════════════
# 7. Missing evidence = CONTINUE_DRY_RUN or BLOCKED
# ════════════════════════════════════════════════════════════════════════════
class TestMissingEvidence:
    def test_no_evidence_at_all_blocks(self):
        score, passes, failures = evaluate_safety_gates(None)
        assert score == 0
        assert "no_evidence_report" in failures

    def test_only_30min_gives_continue(self):
        report = make_report()
        score = 80
        verdict, reason = compute_verdict(score, report, None, None, [])
        # No 4h or 24h → can't be EXTENDED or DEMO_LIVE
        assert verdict in ("CONTINUE_DRY_RUN", "BLOCKED")


# ════════════════════════════════════════════════════════════════════════════
# 8. Scoring boundaries
# ════════════════════════════════════════════════════════════════════════════
class TestScoringBoundaries:
    def test_perfect_report_scores_high(self):
        report = make_report()
        safety, _, _ = evaluate_safety_gates(report)
        runtime, _, _ = evaluate_runtime_stability(report)
        journal, _, _ = evaluate_journal_integrity(report)
        ops, _, _ = evaluate_operational(report)
        evidence, _, _ = evaluate_evidence_depth(report, report, report)
        total = safety + runtime + evidence + journal + ops
        assert total >= 85  # should be high with perfect report

    def test_safety_max_35(self):
        report = make_report()
        safety, _, _ = evaluate_safety_gates(report)
        assert safety <= 35

    def test_runtime_max_25(self):
        report = make_report()
        runtime, _, _ = evaluate_runtime_stability(report)
        assert runtime <= 25

    def test_evidence_max_20(self):
        evidence, _, _ = evaluate_evidence_depth(
            make_report(), make_report(), make_report())
        assert evidence <= 20

    def test_journal_max_10(self):
        report = make_report()
        journal, _, _ = evaluate_journal_integrity(report)
        assert journal <= 10

    def test_ops_max_10(self):
        report = make_report()
        ops, _, _ = evaluate_operational(report)
        assert ops <= 10

    def test_score_89_without_24h_gives_extended(self):
        report = make_report()
        verdict, _ = compute_verdict(89, report, report, None, [])
        assert verdict == "EXTENDED_DRY_RUN_READY"

    def test_score_84_gives_continue(self):
        report = make_report()
        verdict, _ = compute_verdict(84, report, report, None, [])
        assert verdict == "CONTINUE_DRY_RUN"

    def test_score_90_with_24h_gives_demo_live(self):
        report = make_report()
        verdict, _ = compute_verdict(90, report, report, report, [])
        assert verdict == "DEMO_LIVE_REVIEW_ALLOWED"

    def test_score_89_with_24h_gives_extended(self):
        report = make_report()
        verdict, _ = compute_verdict(89, report, report, report, [])
        # Score < 90 → not demo-live even with 24h, but ≥85 with 4h → EXTENDED
        assert verdict == "EXTENDED_DRY_RUN_READY"


# ════════════════════════════════════════════════════════════════════════════
# 9. Safety evaluation details
# ════════════════════════════════════════════════════════════════════════════
class TestSafetyEvaluation:
    def test_dry_run_false_loses_points(self):
        report = make_report(dry_run=False)
        score, _, failures = evaluate_safety_gates(report)
        assert score < 35
        assert any("dry_run" in f for f in failures)

    def test_non_demo_loses_points(self):
        report = make_report(account_type="LIVE")
        score, _, failures = evaluate_safety_gates(report)
        assert any("account_demo" in f for f in failures)

    def test_runtime_ended_early_loses_points(self):
        report = make_report(runtime_ended_early=True)
        score, _, failures = evaluate_safety_gates(report)
        assert any("runtime_not_ended_early" in f for f in failures)


# ════════════════════════════════════════════════════════════════════════════
# 10. Journal integrity
# ════════════════════════════════════════════════════════════════════════════
class TestJournalIntegrity:
    def test_clean_journal_passes(self):
        report = make_report(journal_integrity_errors=[], timestamp_errors=[])
        score, passes, failures = evaluate_journal_integrity(report)
        assert score == 10
        assert len(failures) == 0

    def test_corrupt_journal_loses_points(self):
        report = make_report(journal_integrity_errors=["error1"], timestamp_errors=[])
        score, _, failures = evaluate_journal_integrity(report)
        assert score < 10
        assert any("journal_integrity" in f for f in failures)

    def test_bad_timestamps_lose_points(self):
        report = make_report(journal_integrity_errors=[], timestamp_errors=["error1"])
        score, _, failures = evaluate_journal_integrity(report)
        assert score < 10
        assert any("timestamps_utc" in f for f in failures)
