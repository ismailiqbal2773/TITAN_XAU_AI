"""
TITAN XAU AI — Sprint 9.9.3.27 Broker Compatibility Matrix Tests
==================================================================
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.broker_compatibility_matrix import (
    KNOWN_BROKERS, get_broker_info, get_all_brokers,
    get_broker_summary, get_priority_ranking,
    BrokerStatus, BrokerRiskLevel, BrokerPriority,
)


class TestKnownBrokers:
    """Verify known broker facts are encoded correctly."""

    def test_01_metaquotes_demo_pass(self):
        """MetaQuotes-Demo is encoded as PASS for single demo micro."""
        b = get_broker_info("MetaQuotes-Demo")
        assert b["status"] == "PASS"
        assert b["titan_micro_status"] == "PASS"
        assert b["raw_probe_status"] == "PASS"
        assert b["preferred_filling_mode"] == "IOC"
        assert b["priority"] == "HIGH"
        assert b["risk_level"] == "LOW"
        assert b["automation_allowed"] is True
        assert b["ea_allowed"] is True

    def test_02_metaquotes_repeatability_pending(self):
        """MetaQuotes-Demo repeatability is PENDING until 3-cycle run."""
        b = get_broker_info("MetaQuotes-Demo")
        assert b["repeatability_status"] == "PENDING"

    def test_03_fbs_demo_reject(self):
        """FBS-Demo is encoded as REJECT with retcode 10006."""
        b = get_broker_info("FBS-Demo")
        assert b["status"] == "REJECT"
        assert b["titan_micro_status"] == "REJECT"
        assert b["priority"] == "LOW"
        assert b["risk_level"] == "HIGH"
        assert "10006" in (b["known_reject_reason"] or "")

    def test_04_fundednext_blocked_do_not_use(self):
        """FundedNext Free Trial is BLOCKED / DO_NOT_USE."""
        b = get_broker_info("FundedNext Free Trial")
        assert b["status"] == "BLOCKED"
        assert b["priority"] == "DO_NOT_USE"
        assert b["risk_level"] == "CRITICAL"
        assert b["automation_allowed"] is False
        assert b["ea_allowed"] is False

    def test_05_exness_pending(self):
        """Exness Demo is PENDING."""
        b = get_broker_info("Exness Demo")
        assert b["status"] == "PENDING"
        assert b["raw_probe_status"] == "PENDING"

    def test_06_icmarkets_pending(self):
        """ICMarkets Demo is PENDING."""
        b = get_broker_info("ICMarkets Demo")
        assert b["status"] == "PENDING"
        assert b["raw_probe_status"] == "PENDING"

    def test_07_unknown_broker_returns_unknown(self):
        """Unknown broker returns UNKNOWN status."""
        b = get_broker_info("RandomBroker-Demo")
        assert b["status"] == "UNKNOWN"
        assert b["priority"] == "MEDIUM"


class TestSummaryAndRanking:
    """Summary and priority ranking tests."""

    def test_08_summary_counts(self):
        """Summary counts match known brokers."""
        s = get_broker_summary()
        assert s["total_brokers"] == 5
        assert s["counts"]["PASS"] == 1     # MetaQuotes-Demo
        assert s["counts"]["REJECT"] == 1   # FBS-Demo
        assert s["counts"]["BLOCKED"] == 1  # FundedNext
        assert s["counts"]["PENDING"] == 2  # Exness + ICMarkets

    def test_09_do_not_use_list(self):
        """DO_NOT_USE list includes FundedNext."""
        s = get_broker_summary()
        assert "FundedNext Free Trial" in s["do_not_use"]

    def test_10_priority_ranking_order(self):
        """Priority ranking is HIGH first, DO_NOT_USE last."""
        ranking = get_priority_ranking()
        assert ranking[0]["priority"] == "HIGH"   # MetaQuotes-Demo
        assert ranking[-1]["priority"] == "DO_NOT_USE"  # FundedNext

    def test_11_next_broker_to_test(self):
        """Next broker to test mentions MetaQuotes-Demo."""
        s = get_broker_summary()
        assert "MetaQuotes-Demo" in s["next_broker_to_test"]


class TestReportWriter:
    """Broker compatibility report writer tests."""

    def test_12_json_report_writes_correctly(self, tmp_path):
        """JSON report writes with all required fields."""
        import scripts.audit.broker_compatibility_report as rep
        old_dir = rep.OUTPUT_DIR
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "broker_compatibility_matrix.json"
        rep.MD_PATH = tmp_path / "broker_compatibility_matrix.md"
        try:
            result = rep.write_report()
            assert Path(result["json_path"]).exists()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert "summary" in data
            assert "priority_ranking" in data
            assert "brokers" in data
            assert "warnings" in data
            assert data["summary"]["total_brokers"] == 5
            assert len(data["warnings"]) >= 2
        finally:
            rep.OUTPUT_DIR = old_dir

    def test_13_md_report_has_summary_table(self, tmp_path):
        """MD report has a summary table."""
        import scripts.audit.broker_compatibility_report as rep
        old_dir = rep.OUTPUT_DIR
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "broker_compatibility_matrix.json"
        rep.MD_PATH = tmp_path / "broker_compatibility_matrix.md"
        try:
            result = rep.write_report()
            md = Path(result["md_path"]).read_text()
            assert "## Summary" in md
            assert "## Priority Ranking" in md
            assert "## Detailed Compatibility Matrix" in md
            assert "MetaQuotes-Demo" in md
            assert "FBS-Demo" in md
            assert "FundedNext Free Trial" in md
            assert "DO NOT USE" in md or "DO_NOT_USE" in md
            assert "repeatability" in md.lower() or "PENDING" in md
        finally:
            rep.OUTPUT_DIR = old_dir

    def test_14_report_includes_fundednext_warning(self, tmp_path):
        """Report includes warning about FundedNext Free Trial."""
        import scripts.audit.broker_compatibility_report as rep
        old_dir = rep.OUTPUT_DIR
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "broker_compatibility_matrix.json"
        rep.MD_PATH = tmp_path / "broker_compatibility_matrix.md"
        try:
            result = rep.write_report()
            md = Path(result["md_path"]).read_text()
            assert "FundedNext" in md
            with open(result["json_path"]) as f:
                data = json.load(f)
            fundednext_warning = [w for w in data["warnings"] if "FundedNext" in w]
            assert len(fundednext_warning) >= 1
        finally:
            rep.OUTPUT_DIR = old_dir
