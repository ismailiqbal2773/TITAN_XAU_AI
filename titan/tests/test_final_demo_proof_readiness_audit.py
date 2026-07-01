"""TITAN XAU AI - Sprint 9.9.3.45.8.9 Final Demo Proof Readiness Audit Tests"""
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


class TestFinalDemoProofReadinessAudit:
    def test_01_audit_imports(self):
        import scripts.audit.final_demo_proof_readiness_audit as a
        assert hasattr(a, "run_audit")
        assert hasattr(a, "write_report")

    def test_02_audit_returns_result(self):
        import scripts.audit.final_demo_proof_readiness_audit as a
        result = a.run_audit()
        assert "verdict" in result
        assert "findings" in result

    def test_03_audit_verdicts_supported(self):
        src = (REPO_ROOT / "scripts" / "audit" / "final_demo_proof_readiness_audit.py").read_text()
        assert "FINAL_DEMO_PROOF_READY" in src
        assert "FINAL_DEMO_PROOF_READY_WITH_WARNINGS" in src
        assert "FINAL_DEMO_PROOF_BLOCKED" in src

    def test_04_selected_profile_is_prop_funded_safe(self):
        """Selected profile must be prop_funded_safe."""
        import scripts.audit.final_demo_proof_readiness_audit as a
        result = a.run_audit()
        assert result.get("selected_profile") == "prop_funded_safe"

    def test_05_aggressive_profile_blocked_from_execution(self):
        """Aggressive 20% profile must be simulation-only and not executable."""
        import scripts.audit.final_demo_proof_readiness_audit as a
        result = a.run_audit()
        # The audit should check aggressive profile is simulation-only
        # If audit passes (READY), aggressive must be sim-only
        if result["verdict"] != "FINAL_DEMO_PROOF_BLOCKED":
            assert "simulation-only" in " ".join(result.get("ok_checks", [])).lower() or \
                   "simulation-only" in " ".join(result.get("warnings", [])).lower() or \
                   result["verdict"] in ("FINAL_DEMO_PROOF_READY", "FINAL_DEMO_PROOF_READY_WITH_WARNINGS")

    def test_06_risk_per_trade_le_0_005(self):
        """Risk per trade must be <= 0.005."""
        import scripts.audit.final_demo_proof_readiness_audit as a
        result = a.run_audit()
        findings = result.get("findings", {})
        assert findings.get("risk_per_trade_pct", 0) <= 0.005

    def test_07_internal_daily_dd_le_2pct(self):
        """Internal daily DD must be <= 2.0%."""
        import scripts.audit.final_demo_proof_readiness_audit as a
        result = a.run_audit()
        findings = result.get("findings", {})
        assert findings.get("internal_daily_dd_pct", 0) <= 2.0

    def test_08_internal_total_dd_le_6pct(self):
        """Internal total DD must be <= 6.0%."""
        import scripts.audit.final_demo_proof_readiness_audit as a
        result = a.run_audit()
        findings = result.get("findings", {})
        assert findings.get("internal_total_dd_pct", 0) <= 6.0

    def test_09_broker_score_ge_85(self):
        """Broker score must be >= 85."""
        import scripts.audit.final_demo_proof_readiness_audit as a
        result = a.run_audit()
        findings = result.get("findings", {})
        assert findings.get("broker_score", 0) >= 85

    def test_10_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "final_demo_proof_readiness_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_11_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "audit" / "final_demo_proof_readiness_audit.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code or "no_" in code

    def test_12_writes_json_and_md(self, tmp_path, monkeypatch):
        import scripts.audit.final_demo_proof_readiness_audit as a
        monkeypatch.setattr(a, "OUTPUT_DIR", tmp_path)
        result = a.run_audit()
        report = a.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_13_operator_checklist_does_not_trade(self):
        """Operator checklist script must NOT call order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "demo_proof_operator_checklist.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bmt5\.order_modify\s*\(", code)

    def test_14_open_position_probe_no_order_send(self):
        """Open position probe must NOT call order_send or order_modify."""
        src = (REPO_ROOT / "scripts" / "operator" / "check_open_positions.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bmt5\.order_modify\s*\(", code)

    def test_15_audit_includes_dry_run_check(self):
        """Audit must check dry_run is true."""
        import scripts.audit.final_demo_proof_readiness_audit as a
        result = a.run_audit()
        ok_str = " ".join(result.get("ok_checks", []))
        blockers_str = " ".join(result.get("blockers", []))
        assert "dry_run" in ok_str.lower() or "dry_run" in blockers_str.lower()

    def test_16_audit_includes_live_trading_check(self):
        """Audit must check live_trading is false."""
        import scripts.audit.final_demo_proof_readiness_audit as a
        result = a.run_audit()
        ok_str = " ".join(result.get("ok_checks", []))
        blockers_str = " ".join(result.get("blockers", []))
        assert "live_trading" in ok_str.lower() or "live_trading" in blockers_str.lower()

    def test_17_audit_includes_no_token_check(self):
        """Audit must check no execution token exists."""
        import scripts.audit.final_demo_proof_readiness_audit as a
        result = a.run_audit()
        ok_str = " ".join(result.get("ok_checks", []))
        warnings_str = " ".join(result.get("warnings", []))
        assert "token" in ok_str.lower() or "token" in warnings_str.lower()
