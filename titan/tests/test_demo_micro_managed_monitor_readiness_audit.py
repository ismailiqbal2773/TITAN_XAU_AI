"""TITAN XAU AI - Sprint 9.9.3.45.6 Managed Monitor Readiness Audit Tests

Tests for scripts/audit/demo_micro_managed_monitor_readiness_audit.py:
  - readiness audit returns READY only when all gates pass
  - monitor duration > interval
  - monitor loop cannot complete after one HOLD if position open
  - apply path exists
  - apply path is gated
  - HOLD does not modify
  - MODIFY preserves TP
  - MODIFY favorable-only
  - MetaQuotes-Demo only
  - DEMO only
  - no martingale/grid/averaging
  - no order_send in audit (passive source-code audit)
"""
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


class TestManagedMonitorReadinessAudit:
    def test_01_module_imports(self):
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        assert hasattr(a, "run_audit")
        assert hasattr(a, "write_report")

    def test_02_audit_returns_ready(self):
        """Audit must return MANAGED_MONITOR_READY when all gates pass."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        # In the current implementation, all gates should pass
        assert result["verdict"] in ("MANAGED_MONITOR_READY", "MANAGED_MONITOR_BLOCKED")
        # If BLOCKED, print blockers for debugging
        if result["verdict"] == "MANAGED_MONITOR_BLOCKED":
            for b in result.get("blockers", []):
                print(f"  BLOCKER: {b}")
        # We expect READY in the final implementation
        assert result["verdict"] == "MANAGED_MONITOR_READY", \
            f"Expected MANAGED_MONITOR_READY, got {result['verdict']}. Blockers: {result.get('blockers', [])}"

    def test_03_audit_no_order_send(self):
        """Audit must not call mt5.order_send (passive source audit)."""
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_managed_monitor_readiness_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bmt5\.order_modify\s*\(", code)

    def test_04_audit_checks_monitor_duration_gt_interval(self):
        """Audit must verify monitor duration > interval."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("default_duration_greater_than_interval") is True

    def test_05_audit_checks_loop_iterates_max_iterations(self):
        """Audit must verify monitor loop iterates to max_iterations."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("loop_iterates_max_iterations") is True

    def test_06_audit_checks_apply_path_exists(self):
        """Audit must verify apply path exists."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("apply_path_exists") is True

    def test_07_audit_checks_apply_path_gated(self):
        """Audit must verify apply path is gated."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("apply_path_gated") is True

    def test_08_audit_checks_hold_no_modify(self):
        """Audit must verify HOLD does not modify."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("hold_no_modify") is True

    def test_09_audit_checks_modify_preserves_tp(self):
        """Audit must verify MODIFY preserves TP."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("modify_preserves_tp") is True

    def test_10_audit_checks_modify_favorable_only(self):
        """Audit must verify MODIFY is favorable-only."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("modify_favorable_only") is True

    def test_11_audit_checks_metaquotes_demo_only(self):
        """Audit must verify MetaQuotes-Demo broker required."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("metaquotes_demo_only") is True

    def test_12_audit_checks_demo_only(self):
        """Audit must verify DEMO account required."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("demo_only") is True

    def test_13_audit_checks_no_martingale(self):
        """Audit must verify no martingale/grid/averaging."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("no_martingale_grid_averaging") is True

    def test_14_audit_checks_no_widening(self):
        """Audit must verify no SL widening."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("no_widening") is True

    def test_15_audit_checks_apply_integration(self):
        """Audit must verify monitor loop supports apply integration."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert result["findings"].get("apply_integration") is True

    def test_16_audit_writes_json_and_md(self, tmp_path, monkeypatch):
        """Audit must write JSON and MD reports."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        monkeypatch.setattr(a, "OUTPUT_DIR", tmp_path)
        result = a.run_audit()
        report = a.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_17_audit_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_managed_monitor_readiness_audit.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src

    def test_18_audit_safety_fields(self):
        """Audit result must include safety fields."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert "safety" in result
        assert result["safety"]["order_send_called"] is False
        assert result["safety"]["position_modified"] is False

    def test_19_audit_stop_reasons_present(self):
        """Audit must verify all explicit stop reasons present."""
        import scripts.audit.demo_micro_managed_monitor_readiness_audit as a
        result = a.run_audit()
        assert "stop_reasons_present" in result["findings"]

    def test_20_audit_no_martingale_in_audit_script(self):
        """Audit script itself must not IMPLEMENT martingale/grid/averaging.

        References to the terms (in forbidden_terms check list) are
        allowed, but no actual implementation (function calls, class
        definitions, etc.).
        """
        src = (REPO_ROOT / "scripts" / "audit" / "demo_micro_managed_monitor_readiness_audit.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot"]:
            # Allow references in forbidden_terms list (which is a check)
            # but not actual implementation (e.g., function calls)
            # The audit script legitimately checks for these terms in
            # other files, so we just verify no actual implementation
            # pattern like "def martingale" or "martingale()" or "apply_martingale"
            assert f"def {term}" not in code, f"Function definition for '{term}' in audit script"
            assert f"{term}()" not in code, f"Function call to '{term}' in audit script"
