"""TITAN XAU AI - Sprint 9.9.3.45.8.15 Execution Geometry Receipt Audit Tests

Verifies the passive audit script:
  - Module imports cleanly
  - run_audit() returns a dict with required fields
  - All verdicts are supported (PASS, FAIL_RR_BELOW_MINIMUM,
    RECEIPT_MISSING, RECEIPT_INSUFFICIENT)
  - BUY RR=1.0 -> FAIL, BUY RR=3.0 -> PASS
  - Audit never calls mt5.order_send
  - Audit contains no martingale / grid / averaging / loss-based lot
    multiplier logic
  - Audit writes both JSON and Markdown reports
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


AUDIT_PATH = REPO_ROOT / "scripts" / "audit" / "execution_geometry_receipt_audit.py"


def _write_receipt(tmp_path: Path, receipt: dict) -> Path:
    p = tmp_path / "demo_micro_execution_receipt.json"
    p.write_text(json.dumps(receipt), encoding="utf-8")
    return p


class TestExecutionGeometryReceiptAudit:
    def test_01_module_imports(self):
        """Module must import cleanly without side effects."""
        import scripts.audit.execution_geometry_receipt_audit as mod  # noqa: F401
        assert hasattr(mod, "run_audit")
        assert hasattr(mod, "write_report")
        assert hasattr(mod, "main")

    def test_02_run_audit_returns_result_dict(self, tmp_path):
        """run_audit() must return a dict with required top-level fields."""
        import scripts.audit.execution_geometry_receipt_audit as mod
        receipt = {
            "success": True, "side": "BUY",
            "requested_sl": 4053.64, "requested_tp": 4065.64,
            "detected_position_entry_price": 4056.64,
            "order_send_result_price": 4056.64,
        }
        path = _write_receipt(tmp_path, receipt)
        result = mod.run_audit(receipt_path=path)
        assert isinstance(result, dict)
        for k in ("timestamp_utc", "verdict", "ok_checks", "blockers",
                  "warnings", "geometry", "profile", "receipt_path", "safety"):
            assert k in result, f"Missing top-level field: {k}"
        assert result["safety"]["order_send_called"] is False
        assert result["safety"]["position_modified"] is False

    def test_03_verdicts_supported(self):
        """All four verdicts must be defined as module constants."""
        import scripts.audit.execution_geometry_receipt_audit as mod
        assert mod.VERDICT_PASS == "EXECUTION_GEOMETRY_PASS"
        assert mod.VERDICT_FAIL_RR_BELOW_MINIMUM == "EXECUTION_GEOMETRY_FAIL_RR_BELOW_MINIMUM"
        assert mod.VERDICT_RECEIPT_MISSING == "EXECUTION_GEOMETRY_RECEIPT_MISSING"
        assert mod.VERDICT_RECEIPT_INSUFFICIENT == "EXECUTION_GEOMETRY_RECEIPT_INSUFFICIENT"

    def test_04_buy_rr_1_0_fails(self, tmp_path):
        """BUY entry=4056.64 SL=4053.64 TP=4059.64 -> RR=1.0 -> FAIL."""
        import scripts.audit.execution_geometry_receipt_audit as mod
        receipt = {
            "success": True, "side": "BUY",
            "requested_sl": 4053.64, "requested_tp": 4059.64,
            "detected_position_entry_price": 4056.64,
        }
        path = _write_receipt(tmp_path, receipt)
        result = mod.run_audit(receipt_path=path)
        assert result["verdict"] == mod.VERDICT_FAIL_RR_BELOW_MINIMUM
        geo = result["geometry"]
        assert geo["actual_RR"] == pytest.approx(1.0, abs=1e-6)
        assert geo["geometry_verdict"] == mod.VERDICT_FAIL_RR_BELOW_MINIMUM
        assert any("EXECUTION_GEOMETRY_RR_BELOW_MINIMUM" in b
                   for b in result["blockers"])

    def test_05_buy_rr_3_0_passes(self, tmp_path):
        """BUY entry=4056.64 SL=4053.64 TP=4065.64 -> RR=3.0 -> PASS."""
        import scripts.audit.execution_geometry_receipt_audit as mod
        receipt = {
            "success": True, "side": "BUY",
            "requested_sl": 4053.64, "requested_tp": 4065.64,
            "detected_position_entry_price": 4056.64,
        }
        path = _write_receipt(tmp_path, receipt)
        result = mod.run_audit(receipt_path=path)
        assert result["verdict"] == mod.VERDICT_PASS
        geo = result["geometry"]
        assert geo["actual_RR"] == pytest.approx(3.0, abs=1e-6)
        assert geo["geometry_verdict"] == mod.VERDICT_PASS

    def test_06_sell_rr_3_0_passes(self, tmp_path):
        """SELL entry=2000 SL=2010 TP=1970 -> RR=3.0 -> PASS."""
        import scripts.audit.execution_geometry_receipt_audit as mod
        receipt = {
            "success": True, "side": "SELL",
            "requested_sl": 2010.0, "requested_tp": 1970.0,
            "detected_position_entry_price": 2000.0,
        }
        path = _write_receipt(tmp_path, receipt)
        result = mod.run_audit(receipt_path=path)
        assert result["verdict"] == mod.VERDICT_PASS
        geo = result["geometry"]
        assert geo["actual_RR"] == pytest.approx(3.0, abs=1e-6)

    def test_07_no_order_send_in_audit_source(self):
        """The audit script source must not call mt5.order_send."""
        src = AUDIT_PATH.read_text(encoding="utf-8")
        code = _strip(src)
        assert "mt5.order_send" not in code, \
            "audit script must not call mt5.order_send"

    def test_08_no_martingale_in_audit_source(self):
        """The audit script must not contain martingale / grid / averaging /
        loss-based lot multiplier logic."""
        src = AUDIT_PATH.read_text(encoding="utf-8")
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down",
                     "double_lot", "loss_based_lot_multiplier"]:
            assert term not in code, f"Forbidden term '{term}' in audit source"

    def test_09_writes_json_and_md(self, tmp_path):
        """write_report() must write both JSON and Markdown files."""
        import scripts.audit.execution_geometry_receipt_audit as mod
        receipt = {
            "success": True, "side": "BUY",
            "requested_sl": 4053.64, "requested_tp": 4065.64,
            "detected_position_entry_price": 4056.64,
        }
        path = _write_receipt(tmp_path, receipt)
        result = mod.run_audit(receipt_path=path)
        out_dir = tmp_path / "out"
        report = mod.write_report(result, output_dir=out_dir)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()
        # Verify JSON content is valid and contains geometry
        json_data = json.loads(Path(report["json_path"]).read_text(encoding="utf-8"))
        assert "geometry" in json_data
        assert json_data["verdict"] == mod.VERDICT_PASS
        # Verify MD content has expected sections
        md = Path(report["md_path"]).read_text(encoding="utf-8")
        assert "Execution Geometry Receipt Audit" in md
        assert "Geometry" in md
        assert "Safety" in md
        assert "no order_send" in md.lower() or "no `mt5.order_send`" in md.lower()

    def test_10_receipt_missing_returns_correct_verdict(self, tmp_path):
        """When receipt file is missing, verdict must be RECEIPT_MISSING."""
        import scripts.audit.execution_geometry_receipt_audit as mod
        missing = tmp_path / "does_not_exist.json"
        result = mod.run_audit(receipt_path=missing)
        assert result["verdict"] == mod.VERDICT_RECEIPT_MISSING
        assert any("EXECUTION_GEOMETRY_RECEIPT_MISSING" in b
                   for b in result["blockers"])

    def test_11_receipt_with_missing_sl_tp_returns_insufficient(self, tmp_path):
        """When receipt has side but missing SL/TP, verdict must be
        RECEIPT_INSUFFICIENT."""
        import scripts.audit.execution_geometry_receipt_audit as mod
        receipt = {"success": True, "side": "BUY"}
        path = _write_receipt(tmp_path, receipt)
        result = mod.run_audit(receipt_path=path)
        assert result["verdict"] == mod.VERDICT_RECEIPT_INSUFFICIENT
        blockers = result["blockers"]
        assert any("EXECUTION_GEOMETRY_SL_MISSING" in b for b in blockers)
        assert any("EXECUTION_GEOMETRY_TP_MISSING" in b for b in blockers)

    def test_12_entry_derived_from_sl_tp_when_no_detected_price(self, tmp_path):
        """When detected_position_entry_price is missing, entry must be
        derived from requested_sl/tp using initial_tp_R formula."""
        import scripts.audit.execution_geometry_receipt_audit as mod
        # BUY with SL=4053.64, TP=4065.64, initial_tp_R=3.0
        # entry = (TP + initial_tp_R * SL) / (1 + initial_tp_R)
        #       = (4065.64 + 3 * 4053.64) / 4 = 16226.56 / 4 = 4056.64
        receipt = {
            "success": True, "side": "BUY",
            "requested_sl": 4053.64, "requested_tp": 4065.64,
            # no detected_position_entry_price, no order_send_result_price
        }
        path = _write_receipt(tmp_path, receipt)
        result = mod.run_audit(receipt_path=path)
        geo = result["geometry"]
        assert geo["entry"] == pytest.approx(4056.64, abs=1e-4)
        assert geo["entry_source"] == "derived_from_requested_sl_tp"
        assert geo["actual_RR"] == pytest.approx(3.0, abs=1e-4)
        assert result["verdict"] == mod.VERDICT_PASS

    def test_13_request_sl_tp_aliases_supported(self, tmp_path):
        """Receipt may use request_sl/request_tp aliases; audit must
        accept them in addition to requested_sl/requested_tp."""
        import scripts.audit.execution_geometry_receipt_audit as mod
        receipt = {
            "success": True, "side": "SELL",
            "request_sl": 2010.0, "request_tp": 1970.0,
            "detected_position_entry_price": 2000.0,
        }
        path = _write_receipt(tmp_path, receipt)
        result = mod.run_audit(receipt_path=path)
        assert result["verdict"] == mod.VERDICT_PASS
        geo = result["geometry"]
        assert geo["sl"] == 2010.0
        assert geo["tp"] == 1970.0

    def test_14_override_minimum_rr_respected(self, tmp_path):
        """override_minimum_rr must take precedence over profile default."""
        import scripts.audit.execution_geometry_receipt_audit as mod
        # entry=2000 SL=1990 risk=10 TP=2015 reward=15 -> RR=1.5
        # default minimum_RR=2.0 would FAIL; override to 1.0 should PASS
        receipt = {
            "success": True, "side": "BUY",
            "requested_sl": 1990.0, "requested_tp": 2015.0,  # RR=1.5
            "detected_position_entry_price": 2000.0,
        }
        path = _write_receipt(tmp_path, receipt)
        result = mod.run_audit(receipt_path=path, override_minimum_rr=1.0)
        assert result["verdict"] == mod.VERDICT_PASS
        assert result["geometry"]["minimum_RR"] == 1.0
        assert result["geometry"]["actual_RR"] == pytest.approx(1.5, abs=1e-6)

    def test_15_no_martingale_pattern_in_test_file(self):
        """The test file must not implement any lot-doubling or
        loss-based lot-multiplier patterns."""
        src = (REPO_ROOT / "titan" / "tests" / "test_execution_geometry_receipt_audit.py").read_text()
        code = _strip(src)
        forbidden_patterns = [
            r"lot\s*\*=\s*2",
            r"volume\s*\*=\s*2",
            r"lot\s*=\s*lot\s*\*\s*2",
            r"volume\s*=\s*volume\s*\*\s*2",
            r"loss_count\s*\*\s*lot",
            r"loss_count\s*\*\s*volume",
        ]
        for pat in forbidden_patterns:
            assert not re.search(pat, code), \
                f"Forbidden pattern '{pat}' in test file"

    def test_16_no_order_send_in_test_file(self):
        """The test file must not CALL mt5.order_send (i.e., must not have
        any call expression whose function attribute path resolves to
        mt5.order_send). We use AST parsing so textual mentions inside
        regex strings do not produce false positives."""
        import ast
        src_path = REPO_ROOT / "titan" / "tests" / "test_execution_geometry_receipt_audit.py"
        tree = ast.parse(src_path.read_text(encoding="utf-8"))
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # match mt5.order_send(...)
                if (isinstance(func, ast.Attribute)
                        and func.attr == "order_send"
                        and isinstance(func.value, ast.Name)
                        and func.value.id == "mt5"):
                    calls.append(node)
        assert not calls, \
            f"test file must not call mt5.order_send, found {len(calls)} call(s)"
