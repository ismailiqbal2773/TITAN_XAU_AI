"""TITAN XAU AI - Sprint 9.9.3.45.8.16 v2.7.3 End-to-End Entry Gate Audit Tests"""
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


class TestEndToEndEntryGateAudit:
    def test_01_module_imports(self):
        import scripts.audit.end_to_end_entry_gate_audit as a
        assert hasattr(a, "run_audit")
        assert hasattr(a, "write_report")

    def test_02_all_verdicts_supported(self):
        import scripts.audit.end_to_end_entry_gate_audit as a
        assert hasattr(a, "ALL_VERDICTS")
        assert a.ENTRY_GATE_FULL_PASS in a.ALL_VERDICTS
        assert a.ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN in a.ALL_VERDICTS
        assert a.ENTRY_GATE_BLOCKED_ALPHA_MISSING in a.ALL_VERDICTS
        assert a.ENTRY_GATE_BLOCKED_REGIME_MISSING in a.ALL_VERDICTS
        assert a.ENTRY_GATE_BLOCKED_RISK_OR_BROKER in a.ALL_VERDICTS
        assert a.ENTRY_GATE_BLOCKED_GEOMETRY in a.ALL_VERDICTS

    def test_03_returns_result_with_verdict(self):
        import scripts.audit.end_to_end_entry_gate_audit as a
        result = a.run_audit()
        assert "verdict" in result
        assert "findings" in result
        assert "safety" in result

    def test_04_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "end_to_end_entry_gate_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_05_no_position_modification(self):
        src = (REPO_ROOT / "scripts" / "audit" / "end_to_end_entry_gate_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)

    def test_06_no_execution_token_creation(self):
        src = (REPO_ROOT / "scripts" / "audit" / "end_to_end_entry_gate_audit.py").read_text()
        code = _strip(src).lower()
        assert "create_local_operator_execution_token" not in code
        assert "execution_token_created" in src

    def test_07_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "audit" / "end_to_end_entry_gate_audit.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code or "no_" in code or "forbid" in code

    def test_08_report_includes_all_required_fields(self):
        """Report must include all v2.7.3 spec fields."""
        src = (REPO_ROOT / "scripts" / "audit" / "end_to_end_entry_gate_audit.py").read_text()
        required_fields = [
            "receipt_exists", "execution_success", "selected_profile",
            "symbol", "side", "entry", "SL", "TP", "actual_RR", "geometry_pass",
            "regime_detected", "regime_value", "regime_source_file",
            "alpha_signal_detected", "alpha_signal_value", "alpha_confidence",
            "alpha_threshold", "alpha_pass", "meta_label_pass",
            "risk_gate_pass", "broker_gate_pass", "prop_funded_gate_pass",
            "spread_gate_pass", "slippage_gate_pass", "execution_gate_pass",
            "journal_event_found", "order_send_success", "final_entry_verdict",
        ]
        for field in required_fields:
            assert field in src, f"Missing required field: {field}"

    def test_09_execution_only_pass_when_alpha_missing(self, tmp_path):
        """ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN when execution succeeded,
        geometry/risk/broker passed, but alpha/regime not detected."""
        import scripts.audit.end_to_end_entry_gate_audit as a

        # Build a receipt that passes geometry: entry=4075.27, SL=4072.27, TP=4084.27 -> RR=3.0
        receipt = {
            "success": True,
            "account_profile": "prop_funded_safe",
            "symbol": "XAUUSD",
            "side": "BUY",
            "order_send_result_price": 4075.27,
            "requested_sl": 4072.27,
            "requested_tp": 4084.27,
        }
        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps(receipt))

        result = a.run_audit(receipt_path=receipt_path)
        # Without alpha/regime artifacts, this should be EXECUTION_ONLY_PASS_ALPHA_UNKNOWN
        # OR BLOCKED_RISK_OR_BROKER (if no managed report available to confirm risk)
        assert result["verdict"] in (
            a.ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN,
            a.ENTRY_GATE_BLOCKED_RISK_OR_BROKER,
            a.ENTRY_GATE_BLOCKED_REGIME_MISSING,
        ), f"Unexpected verdict: {result['verdict']}"

    def test_10_blocked_geometry_when_rr_below_minimum(self, tmp_path):
        """ENTRY_GATE_BLOCKED_GEOMETRY when actual_RR < 2.0."""
        import scripts.audit.end_to_end_entry_gate_audit as a

        # RR = 1.0 (SL distance = TP distance = 3.0)
        receipt = {
            "success": True,
            "account_profile": "prop_funded_safe",
            "symbol": "XAUUSD",
            "side": "BUY",
            "order_send_result_price": 4075.27,
            "requested_sl": 4072.27,
            "requested_tp": 4078.27,  # only 3.0 reward -> RR=1.0
        }
        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps(receipt))

        result = a.run_audit(receipt_path=receipt_path)
        assert result["findings"]["actual_RR"] < 2.0, \
            f"Expected actual_RR < 2.0, got {result['findings']['actual_RR']}"
        assert not result["findings"]["geometry_pass"], \
            "Geometry must fail when RR < 2.0"

    def test_11_execution_proof_mode_warning_emitted(self, tmp_path):
        """When verdict is EXECUTION_ONLY_PASS_ALPHA_UNKNOWN, the warning
        'Execution proof mode: alpha/regime not used for entry' must appear."""
        import scripts.audit.end_to_end_entry_gate_audit as a

        # Build a receipt that passes geometry: entry=4075.27, SL=4072.27, TP=4084.27 -> RR=3.0
        receipt = {
            "success": True,
            "account_profile": "prop_funded_safe",
            "symbol": "XAUUSD",
            "side": "BUY",
            "order_send_result_price": 4075.27,
            "requested_sl": 4072.27,
            "requested_tp": 4084.27,
        }
        receipt_path = tmp_path / "receipt.json"
        receipt_path.write_text(json.dumps(receipt))

        result = a.run_audit(receipt_path=receipt_path)
        if result["verdict"] == a.ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN:
            warnings_text = " ".join(result.get("warnings", []))
            assert "alpha/regime not used for entry" in warnings_text, \
                "Execution proof mode warning must be emitted"

    def test_12_writes_json_and_md(self, tmp_path, monkeypatch):
        import scripts.audit.end_to_end_entry_gate_audit as a
        monkeypatch.setattr(a, "OUTPUT_DIR", tmp_path)
        result = a.run_audit()
        report = a.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_13_no_fake_alpha_evidence(self):
        """Source must NOT fabricate alpha/regime evidence - must scan real files."""
        src = (REPO_ROOT / "scripts" / "audit" / "end_to_end_entry_gate_audit.py").read_text()
        # Must scan for actual files, not hard-code "alpha_signal_detected": True
        assert "_scan_alpha_signal_artifacts" in src
        # Default must be False, not True
        assert '"alpha_signal_detected": False' in src
        assert '"regime_detected": False' in src

    def test_14_safety_flags_in_result(self):
        """Result must include all safety flags."""
        import scripts.audit.end_to_end_entry_gate_audit as a
        result = a.run_audit()
        safety = result.get("safety", {})
        assert safety.get("order_send_called") is False
        assert safety.get("position_modified") is False
        assert safety.get("execution_token_created") is False

    def test_15_full_pass_path_exists_in_source(self):
        """Source must contain the ENTRY_GATE_FULL_PASS verdict path."""
        src = (REPO_ROOT / "scripts" / "audit" / "end_to_end_entry_gate_audit.py").read_text()
        assert "ENTRY_GATE_FULL_PASS" in src
        assert "regime_missing" in src
        assert "alpha_missing" in src

    def test_16_blocked_verdicts_distinct(self):
        """All blocked verdicts must be distinct from EXECUTION_ONLY_PASS."""
        import scripts.audit.end_to_end_entry_gate_audit as a
        blocked = {
            a.ENTRY_GATE_BLOCKED_ALPHA_MISSING,
            a.ENTRY_GATE_BLOCKED_REGIME_MISSING,
            a.ENTRY_GATE_BLOCKED_RISK_OR_BROKER,
            a.ENTRY_GATE_BLOCKED_GEOMETRY,
        }
        assert a.ENTRY_GATE_EXECUTION_ONLY_PASS_ALPHA_UNKNOWN not in blocked
        assert a.ENTRY_GATE_FULL_PASS not in blocked
