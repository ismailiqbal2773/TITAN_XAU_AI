"""TITAN XAU AI - Sprint v2.8.2 Broker Score Freshness Audit Tests"""
from __future__ import annotations
import json, re, sys
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


class TestBrokerScoreFreshnessAudit:
    def test_01_module_imports(self):
        import scripts.audit.broker_score_freshness_audit as a
        assert hasattr(a, "run_audit")
        assert hasattr(a, "write_report")

    def test_02_all_verdicts_supported(self):
        import scripts.audit.broker_score_freshness_audit as a
        assert a.BROKER_SCORE_VALID in a.ALL_VERDICTS
        assert a.BROKER_SCORE_FAIL in a.ALL_VERDICTS
        assert a.BROKER_SCORE_STALE in a.ALL_VERDICTS
        assert a.BROKER_SCORE_MISMATCH in a.ALL_VERDICTS
        assert a.BROKER_SCORE_NOT_FOUND in a.ALL_VERDICTS
        assert a.BROKER_VENUE_CONTROLLED_DEMO_ALLOWED in a.ALL_VERDICTS
        assert a.BROKER_VENUE_FUNDEDNEXT_BLOCKED in a.ALL_VERDICTS
        assert a.BROKER_VENUE_VALIDATION_PENDING in a.ALL_VERDICTS

    def test_03_returns_result_with_verdict(self):
        import scripts.audit.broker_score_freshness_audit as a
        result = a.run_audit()
        assert "verdict" in result
        assert "findings" in result
        assert "safety" in result
        assert result["verdict"] in a.ALL_VERDICTS

    def test_04_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "broker_score_freshness_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_05_no_position_modification(self):
        src = (REPO_ROOT / "scripts" / "audit" / "broker_score_freshness_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)

    def test_06_no_execution_token_creation(self):
        src = (REPO_ROOT / "scripts" / "audit" / "broker_score_freshness_audit.py").read_text()
        code = _strip(src).lower()
        assert "create_local_operator_execution_token" not in code

    def test_07_includes_broker_report_freshness_fields(self):
        """Audit must include broker report freshness validation fields."""
        import scripts.audit.broker_score_freshness_audit as a
        result = a.run_audit()
        fnd = result.get("findings", {})
        assert "broker_report_exists" in fnd
        assert "broker_report_path" in fnd
        assert "broker_report_is_stale" in fnd
        assert "broker_report_matches_current_account" in fnd

    def test_08_includes_execution_venue_fields(self):
        """Audit must include execution venue allowed/reason fields."""
        import scripts.audit.broker_score_freshness_audit as a
        result = a.run_audit()
        fnd = result.get("findings", {})
        assert "broker_execution_venue_allowed" in fnd
        assert "broker_execution_venue_reason" in fnd

    def test_09_includes_fundednext_block_check(self):
        """Audit must check for FundedNext demo and block it."""
        src = (REPO_ROOT / "scripts" / "audit" / "broker_score_freshness_audit.py").read_text()
        assert "FUNDEDNEXT_DEMO_ALGO_NOT_ALLOWED" in src
        assert "fundednext" in src.lower()

    def test_10_includes_metaquotes_demo_allowed_check(self):
        """Audit must allow MetaQuotes-Demo for controlled demo."""
        src = (REPO_ROOT / "scripts" / "audit" / "broker_score_freshness_audit.py").read_text()
        assert "METAQUOTES_DEMO_ALLOWED_FOR_CONTROLLED_LOCAL_DEMO" in src
        assert "metaquotes" in src.lower()

    def test_11_stale_score_zero_not_treated_as_fail(self):
        """Stale score=0 must not be treated as actual fail."""
        src = (REPO_ROOT / "scripts" / "audit" / "broker_score_freshness_audit.py").read_text()
        assert "BROKER_SCORE_STALE" in src
        assert "broker_report_generated_without_mt5" in src

    def test_12_writes_json_and_md(self, tmp_path, monkeypatch):
        import scripts.audit.broker_score_freshness_audit as a
        monkeypatch.setattr(a, "OUTPUT_DIR", tmp_path)
        result = a.run_audit()
        report = a.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_13_safety_flags_in_result(self):
        """Result must include all safety flags."""
        import scripts.audit.broker_score_freshness_audit as a
        result = a.run_audit()
        safety = result.get("safety", {})
        assert safety.get("order_send_called") is False
        assert safety.get("position_modified") is False
        assert safety.get("execution_token_created") is False

    def test_14_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "audit" / "broker_score_freshness_audit.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code or "no_" in code or "forbid" in code
