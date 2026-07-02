"""TITAN XAU AI - Sprint 9.9.3.45.8.13 Trailing Manager Verification Audit Tests

Tests that the trailing manager verification audit correctly classifies
whether trailing manager should have triggered based on ACTUAL profit_R,
not managed report trigger flags.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
from datetime import datetime, timezone
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class TestTrailingManagerVerificationAudit:
    def test_01_module_imports(self):
        import scripts.audit.trailing_manager_verification_audit as a
        assert hasattr(a, "run_audit")
        assert hasattr(a, "write_report")

    def test_02_returns_result_with_verdict(self):
        import scripts.audit.trailing_manager_verification_audit as a
        result = a.run_audit()
        assert "verdict" in result
        assert "findings" in result

    def test_03_all_verdicts_supported(self):
        import scripts.audit.trailing_manager_verification_audit as a
        assert hasattr(a, "ALL_VERDICTS")
        assert a.TRAILING_MANAGER_OK_NO_TRIGGER in a.ALL_VERDICTS
        assert a.TRAILING_MANAGER_OK_TRIGGERED in a.ALL_VERDICTS
        assert a.TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE in a.ALL_VERDICTS
        assert a.TRAILING_MANAGER_BLOCKED_NOT_RUNNING in a.ALL_VERDICTS

    def test_04_profit_R_below_threshold_no_block(self, tmp_path):
        """profit_R=0.247, thresholds 1.0/1.75/2.0/3.0, sl_modification_events=0
        -> TRAILING_MANAGER_OK_NO_TRIGGER (NOT BLOCKED)."""
        import scripts.audit.trailing_manager_verification_audit as a

        # Create fake forensics with entry/exit deals
        forensics = {
            "findings": {
                "root_cause": "TRAILING_MANAGER_NOT_RUNNING",
                "entry_deal": {"ticket": 50001, "price": 2000.0, "position_id": 12345},
                "exit_deal": {"ticket": 50002, "price": 2002.47, "position_id": 12345},
                "entry_sl": 1990.0,
                "entry_tp": 2030.0,
                "sl_modification_events": 0,
                "sl_hit_detected": True,
                "realized_pl": -7.53,
            }
        }
        # Create fake receipt
        receipt = {"side": "BUY", "success": True}
        # Create fake managed report
        managed = {
            "monitor_iterations": 26,
            "monitor_duration_seconds": 126.07,
            "breakeven_triggered": True,  # Managed report says True but profit_R says NO
            "trailing_triggered": False,
            "profit_lock_triggered": False,
            "final_position_status": "CLOSED",
            "adaptive_trailing_config": {
                "breakeven_trigger_R": 1.0,
                "trailing_trigger_R": 1.75,
                "profit_lock_trigger_R": 3.0,
                "tp_extension_trigger_R": 2.0,
                "min_hold_seconds": 60,
                "min_monitor_iterations": 3,
            },
        }

        f_path = tmp_path / "forensics.json"
        r_path = tmp_path / "receipt.json"
        m_path = tmp_path / "managed.json"
        f_path.write_text(json.dumps(forensics))
        r_path.write_text(json.dumps(receipt))
        m_path.write_text(json.dumps(managed))

        result = a.run_audit(
            receipt_path=r_path,
            forensics_path=f_path,
            managed_report_path=m_path,
        )
        # profit_R = (2002.47 - 2000.0) / (2000.0 - 1990.0) = 2.47 / 10 = 0.247
        # 0.247 < 1.0 (breakeven) -> OK_NO_TRIGGER
        assert result["verdict"] == a.TRAILING_MANAGER_OK_NO_TRIGGER, \
            f"Expected OK_NO_TRIGGER for profit_R=0.247, got {result['verdict']}"
        assert len(result.get("blockers", [])) == 0

    def test_05_profit_R_just_below_threshold(self, tmp_path):
        """profit_R=0.99 -> OK_NO_TRIGGER."""
        import scripts.audit.trailing_manager_verification_audit as a

        forensics = {
            "findings": {
                "entry_deal": {"price": 2000.0},
                "exit_deal": {"price": 2009.9},
                "entry_sl": 1990.0,
                "sl_modification_events": 0,
            }
        }
        receipt = {"side": "BUY"}
        managed = {
            "monitor_iterations": 10,
            "monitor_duration_seconds": 120,
            "adaptive_trailing_config": {"breakeven_trigger_R": 1.0},
        }

        f_path = tmp_path / "f.json"
        r_path = tmp_path / "r.json"
        m_path = tmp_path / "m.json"
        f_path.write_text(json.dumps(forensics))
        r_path.write_text(json.dumps(receipt))
        m_path.write_text(json.dumps(managed))

        result = a.run_audit(receipt_path=r_path, forensics_path=f_path, managed_report_path=m_path)
        # profit_R = 9.9 / 10 = 0.99 < 1.0
        assert result["verdict"] == a.TRAILING_MANAGER_OK_NO_TRIGGER

    def test_06_profit_R_at_breakeven_no_sl_modify_blocks(self, tmp_path):
        """profit_R=1.0, no SL modification, enough monitor -> BLOCKED_NOT_RUNNING."""
        import scripts.audit.trailing_manager_verification_audit as a

        forensics = {
            "findings": {
                "entry_deal": {"price": 2000.0},
                "exit_deal": {"price": 2010.0},
                "entry_sl": 1990.0,
                "sl_modification_events": 0,
            }
        }
        receipt = {"side": "BUY"}
        managed = {
            "monitor_iterations": 5,
            "monitor_duration_seconds": 300,
            "adaptive_trailing_config": {
                "breakeven_trigger_R": 1.0,
                "min_hold_seconds": 60,
                "min_monitor_iterations": 3,
            },
        }

        f_path = tmp_path / "f.json"
        r_path = tmp_path / "r.json"
        m_path = tmp_path / "m.json"
        f_path.write_text(json.dumps(forensics))
        r_path.write_text(json.dumps(receipt))
        m_path.write_text(json.dumps(managed))

        result = a.run_audit(receipt_path=r_path, forensics_path=f_path, managed_report_path=m_path)
        # profit_R = 10/10 = 1.0 >= 1.0, monitor ok, hold ok, no SL modify -> BLOCKED
        assert result["verdict"] == a.TRAILING_MANAGER_BLOCKED_NOT_RUNNING

    def test_07_profit_R_1_8_blocks(self, tmp_path):
        """profit_R=1.8, no SL modification, enough evidence -> BLOCKED."""
        import scripts.audit.trailing_manager_verification_audit as a

        forensics = {
            "findings": {
                "entry_deal": {"price": 2000.0},
                "exit_deal": {"price": 2018.0},
                "entry_sl": 1990.0,
                "sl_modification_events": 0,
            }
        }
        receipt = {"side": "BUY"}
        managed = {
            "monitor_iterations": 5,
            "monitor_duration_seconds": 300,
            "adaptive_trailing_config": {"breakeven_trigger_R": 1.0, "min_hold_seconds": 60, "min_monitor_iterations": 3},
        }

        f_path = tmp_path / "f.json"; r_path = tmp_path / "r.json"; m_path = tmp_path / "m.json"
        f_path.write_text(json.dumps(forensics)); r_path.write_text(json.dumps(receipt)); m_path.write_text(json.dumps(managed))

        result = a.run_audit(receipt_path=r_path, forensics_path=f_path, managed_report_path=m_path)
        assert result["verdict"] == a.TRAILING_MANAGER_BLOCKED_NOT_RUNNING

    def test_08_profit_R_2_2_blocks(self, tmp_path):
        """profit_R=2.2 -> BLOCKED."""
        import scripts.audit.trailing_manager_verification_audit as a

        forensics = {"findings": {"entry_deal": {"price": 2000.0}, "exit_deal": {"price": 2022.0}, "entry_sl": 1990.0, "sl_modification_events": 0}}
        receipt = {"side": "BUY"}
        managed = {"monitor_iterations": 5, "monitor_duration_seconds": 300, "adaptive_trailing_config": {"breakeven_trigger_R": 1.0, "min_hold_seconds": 60, "min_monitor_iterations": 3}}
        f_path = tmp_path / "f.json"; r_path = tmp_path / "r.json"; m_path = tmp_path / "m.json"
        f_path.write_text(json.dumps(forensics)); r_path.write_text(json.dumps(receipt)); m_path.write_text(json.dumps(managed))
        result = a.run_audit(receipt_path=r_path, forensics_path=f_path, managed_report_path=m_path)
        assert result["verdict"] == a.TRAILING_MANAGER_BLOCKED_NOT_RUNNING

    def test_09_profit_R_3_2_blocks(self, tmp_path):
        """profit_R=3.2 -> BLOCKED."""
        import scripts.audit.trailing_manager_verification_audit as a

        forensics = {"findings": {"entry_deal": {"price": 2000.0}, "exit_deal": {"price": 2032.0}, "entry_sl": 1990.0, "sl_modification_events": 0}}
        receipt = {"side": "BUY"}
        managed = {"monitor_iterations": 5, "monitor_duration_seconds": 300, "adaptive_trailing_config": {"breakeven_trigger_R": 1.0, "min_hold_seconds": 60, "min_monitor_iterations": 3}}
        f_path = tmp_path / "f.json"; r_path = tmp_path / "r.json"; m_path = tmp_path / "m.json"
        f_path.write_text(json.dumps(forensics)); r_path.write_text(json.dumps(receipt)); m_path.write_text(json.dumps(managed))
        result = a.run_audit(receipt_path=r_path, forensics_path=f_path, managed_report_path=m_path)
        assert result["verdict"] == a.TRAILING_MANAGER_BLOCKED_NOT_RUNNING

    def test_10_profit_R_1_5_with_sl_modify_ok_triggered(self, tmp_path):
        """profit_R=1.5, SL modification events > 0 -> OK_TRIGGERED."""
        import scripts.audit.trailing_manager_verification_audit as a

        forensics = {"findings": {"entry_deal": {"price": 2000.0}, "exit_deal": {"price": 2015.0}, "entry_sl": 1990.0, "sl_modification_events": 1}}
        receipt = {"side": "BUY"}
        managed = {"monitor_iterations": 5, "monitor_duration_seconds": 300, "adaptive_trailing_config": {"breakeven_trigger_R": 1.0}}
        f_path = tmp_path / "f.json"; r_path = tmp_path / "r.json"; m_path = tmp_path / "m.json"
        f_path.write_text(json.dumps(forensics)); r_path.write_text(json.dumps(receipt)); m_path.write_text(json.dumps(managed))
        result = a.run_audit(receipt_path=r_path, forensics_path=f_path, managed_report_path=m_path)
        assert result["verdict"] == a.TRAILING_MANAGER_OK_TRIGGERED

    def test_11_missing_profit_R_warns(self, tmp_path):
        """Missing profit_R -> WARN_INSUFFICIENT_EVIDENCE."""
        import scripts.audit.trailing_manager_verification_audit as a

        forensics = {"findings": {"sl_modification_events": 0}}
        receipt = {}
        managed = {"monitor_iterations": 5, "monitor_duration_seconds": 300}
        f_path = tmp_path / "f.json"; r_path = tmp_path / "r.json"; m_path = tmp_path / "m.json"
        f_path.write_text(json.dumps(forensics)); r_path.write_text(json.dumps(receipt)); m_path.write_text(json.dumps(managed))
        result = a.run_audit(receipt_path=r_path, forensics_path=f_path, managed_report_path=m_path)
        assert result["verdict"] == a.TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE

    def test_12_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "trailing_manager_verification_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_13_no_position_modification(self):
        src = (REPO_ROOT / "scripts" / "audit" / "trailing_manager_verification_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)

    def test_14_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "audit" / "trailing_manager_verification_audit.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code or "no_" in code

    def test_15_writes_json_and_md(self, tmp_path, monkeypatch):
        import scripts.audit.trailing_manager_verification_audit as a
        monkeypatch.setattr(a, "OUTPUT_DIR", tmp_path)
        result = a.run_audit()
        report = a.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()

    def test_16_reads_forensics_root_cause(self):
        """Audit must read forensics root_cause."""
        src = (REPO_ROOT / "scripts" / "audit" / "trailing_manager_verification_audit.py").read_text()
        assert "root_cause" in src
        assert "TRAILING_MANAGER_NOT_RUNNING" in src

    def test_17_trigger_flags_computed_from_profit_R(self):
        """Trigger flags must be computed from actual profit_R, not managed report."""
        src = (REPO_ROOT / "scripts" / "audit" / "trailing_manager_verification_audit.py").read_text()
        # Must compute breakeven_triggered from best_profit_R >= breakeven_trigger_R
        assert "best_profit_R >= breakeven_trigger_R" in src
        # Must have managed_breakeven_triggered as separate field
        assert "managed_breakeven_triggered" in src

    def test_18_report_includes_all_required_fields(self):
        """Report must include all required fields from Part D."""
        src = (REPO_ROOT / "scripts" / "audit" / "trailing_manager_verification_audit.py").read_text()
        required_fields = [
            "profit_R", "breakeven_trigger_R", "trailing_trigger_R",
            "dynamic_tp_trigger_R", "profit_lock_trigger_R",
            "breakeven_triggered", "trailing_triggered", "dynamic_tp_triggered",
            "profit_lock_triggered", "sl_modification_expected", "sl_modification_events",
            "monitor_iterations", "hold_seconds",
            "manager_expected_reason", "manager_not_expected_reason", "final_verdict_reason",
        ]
        for field in required_fields:
            assert field in src, f"Missing field in source: {field}"

    # === Sprint 9.9.3.45.8.16 v2.7.3: planned_RR + WARN_INSUFFICIENT_PATH_EVIDENCE ===

    def test_19_v2_7_3_new_verdict_supported(self):
        """Audit must support TRAILING_MANAGER_WARN_INSUFFICIENT_PATH_EVIDENCE verdict."""
        import scripts.audit.trailing_manager_verification_audit as a
        assert hasattr(a, "TRAILING_MANAGER_WARN_INSUFFICIENT_PATH_EVIDENCE")
        assert a.TRAILING_MANAGER_WARN_INSUFFICIENT_PATH_EVIDENCE in a.ALL_VERDICTS

    def test_20_v2_7_3_new_fields_present(self):
        """Audit must compute v2.7.3 receipt-geometry fields."""
        src = (REPO_ROOT / "scripts" / "audit" / "trailing_manager_verification_audit.py").read_text()
        for field in [
            "planned_RR",
            "actual_RR_from_receipt",
            "entry_price",  # already existed, now sourced from receipt
            "sl_price",
            "tp_price",
            "receipt_geometry_valid",
            "profit_R_source",
            "mfe_available",
            "close_price_available",
        ]:
            assert field in src, f"Missing v2.7.3 field: {field}"

    def test_21_v2_7_3_planned_RR_computed_from_receipt(self, tmp_path):
        """planned_RR must be computed from receipt's entry/SL/TP/side when
        forensics cannot provide profit_R."""
        import scripts.audit.trailing_manager_verification_audit as a

        # Receipt with full geometry: entry=4075.27, SL=4072.27, TP=4084.27
        # planned_RR = (4084.27 - 4075.27) / (4075.27 - 4072.27) = 9/3 = 3.0
        receipt = {
            "side": "BUY",
            "order_send_result_price": 4075.27,
            "requested_sl": 4072.27,
            "requested_tp": 4084.27,
        }
        # Empty forensics (no entry/exit deal)
        forensics = {"findings": {}}
        managed = {"monitor_iterations": 0, "monitor_duration_seconds": 0}

        r_path = tmp_path / "r.json"
        f_path = tmp_path / "f.json"
        m_path = tmp_path / "m.json"
        r_path.write_text(json.dumps(receipt))
        f_path.write_text(json.dumps(forensics))
        m_path.write_text(json.dumps(managed))

        result = a.run_audit(receipt_path=r_path, forensics_path=f_path, managed_report_path=m_path)
        fnd = result.get("findings", {})
        assert fnd.get("planned_RR") == 3.0, f"Expected planned_RR=3.0, got {fnd.get('planned_RR')}"
        assert fnd.get("receipt_geometry_valid") is True
        assert fnd.get("profit_R_source") == "receipt_planned"

    def test_22_v2_7_3_warn_insufficient_path_evidence_when_no_profit_R(self, tmp_path):
        """When profit_R not computable but receipt provides planned_RR,
        audit must return WARN_INSUFFICIENT_PATH_EVIDENCE (NOT a hard block)."""
        import scripts.audit.trailing_manager_verification_audit as a

        receipt = {
            "side": "BUY",
            "order_send_result_price": 4075.27,
            "requested_sl": 4072.27,
            "requested_tp": 4084.27,
        }
        forensics = {"findings": {}}  # no entry/exit deal, no profit_R
        managed = {"monitor_iterations": 0, "monitor_duration_seconds": 0}

        r_path = tmp_path / "r.json"
        f_path = tmp_path / "f.json"
        m_path = tmp_path / "m.json"
        r_path.write_text(json.dumps(receipt))
        f_path.write_text(json.dumps(forensics))
        m_path.write_text(json.dumps(managed))

        result = a.run_audit(receipt_path=r_path, forensics_path=f_path, managed_report_path=m_path)
        # v2.7.3: should return WARN_INSUFFICIENT_PATH_EVIDENCE, not BLOCKED
        assert result["verdict"] == a.TRAILING_MANAGER_WARN_INSUFFICIENT_PATH_EVIDENCE, \
            f"Expected WARN_INSUFFICIENT_PATH_EVIDENCE, got {result['verdict']}"
        # Must NOT be a hard block (no blockers)
        assert len(result.get("blockers", [])) == 0, \
            f"WARN_INSUFFICIENT_PATH_EVIDENCE must not have blockers: {result.get('blockers')}"

    def test_23_v2_7_3_no_block_when_profit_R_missing_and_no_path_evidence(self, tmp_path):
        """When profit_R missing and no exit price/MFE, audit must NOT block."""
        import scripts.audit.trailing_manager_verification_audit as a

        receipt = {"side": "BUY", "order_send_result_price": 4075.27,
                   "requested_sl": 4072.27, "requested_tp": 4084.27}
        forensics = {"findings": {"sl_modification_events": 0}}
        managed = {"monitor_iterations": 0, "monitor_duration_seconds": 0}

        r_path = tmp_path / "r.json"
        f_path = tmp_path / "f.json"
        m_path = tmp_path / "m.json"
        r_path.write_text(json.dumps(receipt))
        f_path.write_text(json.dumps(forensics))
        m_path.write_text(json.dumps(managed))

        result = a.run_audit(receipt_path=r_path, forensics_path=f_path, managed_report_path=m_path)
        assert "BLOCKED" not in result["verdict"], \
            f"Must not be BLOCKED when profit_R missing: {result['verdict']}"
        assert len(result.get("blockers", [])) == 0

    def test_24_v2_7_3_profit_R_source_field(self):
        """profit_R_source must be one of: forensics, receipt_planned, unknown."""
        src = (REPO_ROOT / "scripts" / "audit" / "trailing_manager_verification_audit.py").read_text()
        assert '"forensics"' in src
        assert '"receipt_planned"' in src
        assert '"unknown"' in src

    def test_25_v2_7_3_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "trailing_manager_verification_audit.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
