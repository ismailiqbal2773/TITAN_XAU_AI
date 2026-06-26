"""
TITAN XAU AI — Sprint 9.8.1 Demo Micro Readiness Gate Tests
"""
from __future__ import annotations
import json
import pytest
from pathlib import Path
from scripts.audit.demo_micro_readiness_gate import evaluate


def make_report(**overrides) -> dict:
    base = {
        "verdict": "VIRTUAL_LIFECYCLE_READY",
        "order_send_used": False,
        "live_execution_touched": False,
        "combined_metrics": {
            "net_pnl_total": 44.10,
            "profit_factor_net": 1.85,
            "win_rate_net": 52.94,
            "expectancy_net": 2.59,
            "cost_drag_pct": 19.82,
        },
        "normal_metrics": {
            "max_drawdown_pct_of_start_equity": 0.33,
        },
    }
    base.update(overrides)
    return base


class TestDemoMicroGate:
    def test_all_pass_gives_ready(self):
        v, _, checks = evaluate(make_report())
        assert v == "DEMO_MICRO_READY"

    def test_normal_dd_over_5_gives_risk_review(self):
        report = make_report(normal_metrics={"max_drawdown_pct_of_start_equity": 6.0})
        v, _, _ = evaluate(report)
        assert v == "NEEDS_RISK_REVIEW"

    def test_pf_below_1_2_blocks(self):
        report = make_report()
        report["combined_metrics"]["profit_factor_net"] = 1.0
        v, _, _ = evaluate(report)
        assert v == "DEMO_MICRO_BLOCKED"

    def test_expectancy_zero_blocks(self):
        report = make_report()
        report["combined_metrics"]["expectancy_net"] = 0
        v, _, _ = evaluate(report)
        assert v == "DEMO_MICRO_BLOCKED"

    def test_cost_drag_over_35_blocks(self):
        report = make_report()
        report["combined_metrics"]["cost_drag_pct"] = 40
        v, _, _ = evaluate(report)
        assert v == "DEMO_MICRO_BLOCKED"

    def test_order_send_used_blocks(self):
        report = make_report(order_send_used=True)
        v, _, _ = evaluate(report)
        assert v == "DEMO_MICRO_BLOCKED"

    def test_live_touched_blocks(self):
        report = make_report(live_execution_touched=True)
        v, _, _ = evaluate(report)
        assert v == "DEMO_MICRO_BLOCKED"

    def test_net_pnl_negative_blocks(self):
        report = make_report()
        report["combined_metrics"]["net_pnl_total"] = -10
        v, _, _ = evaluate(report)
        assert v == "DEMO_MICRO_BLOCKED"

    def test_win_rate_below_40_blocks(self):
        report = make_report()
        report["combined_metrics"]["win_rate_net"] = 30
        v, _, _ = evaluate(report)
        assert v == "DEMO_MICRO_BLOCKED"

    def test_not_virtual_lifecycle_ready_blocks(self):
        report = make_report(verdict="BLOCKED")
        v, _, _ = evaluate(report)
        assert v == "DEMO_MICRO_BLOCKED"
