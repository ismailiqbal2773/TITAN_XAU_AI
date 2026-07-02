"""TITAN XAU AI - Sprint 9.9.3.45.8.11 Trailing Manager Verification Audit Tests

Tests for scripts/audit/trailing_manager_verification_audit.py:
  - module imports (run_audit, write_report)
  - returns result with verdict
  - all 4 verdicts supported
  - does not block when trigger not reached (sl_modification_events=0 is OK
    if profit_R < breakeven_trigger_R)
  - blocks when trigger reached but manager not running
    (profit_R >= 1.0 AND monitor_iterations >= 3 AND hold_seconds >= 60
    AND sl_modification_events=0)
  - warns when insufficient evidence
  - no order_send in source
  - no martingale/grid/averaging/loss_based_lot_multiplier in source
  - writes json and md
  - reads forensics root_cause
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src: str) -> str:
    """Strip comments, docstrings, and string literals from Python source."""
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


def _write_json(path: Path, data: dict) -> None:
    """Write a JSON file, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


# === Fixture builders ===

def _build_managed_report(
    *,
    monitor_iterations: int = 0,
    monitor_duration_seconds: float = 0.0,
    breakeven_triggered: bool = False,
    trailing_triggered: bool = False,
    profit_lock_triggered: bool = False,
    final_position_status: str = "CLOSED",
    monitor_stop_reason: str = "TIMEOUT",
    breakeven_trigger_R: float = 1.0,
    trailing_trigger_R: float = 1.75,
    profit_lock_trigger_R: float = 3.0,
    tp_extension_trigger_R: float = 2.0,
    min_hold_seconds: int = 60,
    min_monitor_iterations: int = 3,
) -> dict:
    return {
        "verdict": "MANAGED_DEMO_MICRO_COMPLETED",
        "monitor_iterations": monitor_iterations,
        "monitor_duration_seconds": monitor_duration_seconds,
        "monitor_stop_reason": monitor_stop_reason,
        "final_position_status": final_position_status,
        "breakeven_triggered": breakeven_triggered,
        "trailing_triggered": trailing_triggered,
        "profit_lock_triggered": profit_lock_triggered,
        "adaptive_trailing_config": {
            "adaptive_trailing_enabled": False,
            "dynamic_tp_enabled": False,
            "profit_corridor_enabled": False,
            "adaptive_policy_mode": "balanced_conservative",
            "breakeven_trigger_R": breakeven_trigger_R,
            "trailing_trigger_R": trailing_trigger_R,
            "profit_lock_trigger_R": profit_lock_trigger_R,
            "tp_extension_trigger_R": tp_extension_trigger_R,
            "min_hold_seconds": min_hold_seconds,
            "min_monitor_iterations": min_monitor_iterations,
        },
    }


def _build_forensics(
    *,
    root_cause: str = "TRAILING_MANAGER_NOT_RUNNING",
    sl_modification_events: int = 0,
    sl_hit_detected: bool = False,
    realized_pl: float = 0.0,
    entry_sl: float = 1990.0,
    entry_tp: float = 0.0,
    entry_price: float = 2000.0,
    exit_price: float = 0.0,
    mfe: object = None,
) -> dict:
    findings: dict = {
        "root_cause": root_cause,
        "sl_modification_events": sl_modification_events,
        "sl_hit_detected": sl_hit_detected,
        "realized_pl": realized_pl,
        "entry_sl": entry_sl,
        "entry_tp": entry_tp,
        "entry_deal": {
            "ticket": 1,
            "price": entry_price,
            "entry": 0,
        },
        "exit_deal": {
            "ticket": 2,
            "price": exit_price,
            "entry": 1,
        },
        "trailing_active": sl_modification_events > 0,
        "breakeven_active": sl_modification_events > 0,
    }
    if mfe is not None:
        findings["mfe"] = mfe
    return {
        "timestamp_utc": "2026-07-02T03:28:06.307126+00:00",
        "verdict": "DEMO_MICRO_FORENSICS_INCOMPLETE",
        "ok_checks": [],
        "blockers": [],
        "warnings": [],
        "findings": findings,
        "safety": {
            "order_send_called": False,
            "position_modified": False,
        },
    }


def _build_receipt(*, side: str = "BUY", success: bool = True) -> dict:
    return {
        "timestamp_utc": "2026-07-02T03:25:00.000000+00:00",
        "execution_mode": "execute_and_monitor",
        "success": success,
        "symbol": "XAUUSD",
        "volume": 0.01,
        "side": side,
        "request_magic": 202619,
        "request_comment": "TITAN_DEMO_MICRO",
        "position_detected": True,
    }


class TestTrailingManagerVerificationAudit:
    """Tests for trailing_manager_verification_audit.run_audit / write_report."""

    # --- Test 1: module imports ---
    def test_01_module_imports(self):
        import scripts.audit.trailing_manager_verification_audit as a
        assert hasattr(a, "run_audit")
        assert hasattr(a, "write_report")
        assert callable(a.run_audit)
        assert callable(a.write_report)

    # --- Test 2: returns result with verdict ---
    def test_02_returns_result_with_verdict(self):
        import scripts.audit.trailing_manager_verification_audit as a
        result = a.run_audit()
        assert isinstance(result, dict)
        assert "verdict" in result
        assert "timestamp_utc" in result
        assert "ok_checks" in result
        assert "blockers" in result
        assert "warnings" in result
        assert "findings" in result
        assert "safety" in result
        assert isinstance(result["verdict"], str)
        assert isinstance(result["findings"], dict)
        assert isinstance(result["safety"], dict)

    # --- Test 3: all 4 verdicts supported ---
    def test_03_all_four_verdicts_supported(self):
        src = (
            REPO_ROOT
            / "scripts"
            / "audit"
            / "trailing_manager_verification_audit.py"
        ).read_text()
        assert "TRAILING_MANAGER_OK_NO_TRIGGER" in src
        assert "TRAILING_MANAGER_OK_TRIGGERED" in src
        assert "TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE" in src
        assert "TRAILING_MANAGER_BLOCKED_NOT_RUNNING" in src
        # Also verify the ALL_VERDICTS constant contains all 4
        import scripts.audit.trailing_manager_verification_audit as a
        assert len(a.ALL_VERDICTS) == 4
        for v in a.ALL_VERDICTS:
            assert v in (
                "TRAILING_MANAGER_OK_NO_TRIGGER",
                "TRAILING_MANAGER_OK_TRIGGERED",
                "TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE",
                "TRAILING_MANAGER_BLOCKED_NOT_RUNNING",
            )

    # --- Test 4: does NOT block when trigger not reached
    #     (sl_modification_events=0 is OK if profit_R < breakeven_trigger_R) ---
    def test_04_does_not_block_when_trigger_not_reached(self, tmp_path):
        import scripts.audit.trailing_manager_verification_audit as a

        receipt_path = tmp_path / "receipt.json"
        forensics_path = tmp_path / "forensics.json"
        report_path = tmp_path / "managed_trade_report.json"

        # profit_R = (2005 - 2000) / (2000 - 1990) = 5/10 = 0.5
        # 0.5 < breakeven_trigger_R=1.0 -> trigger NOT reached
        _write_json(receipt_path, _build_receipt(side="BUY"))
        _write_json(
            forensics_path,
            _build_forensics(
                root_cause="TRAILING_MANAGER_NOT_RUNNING",
                sl_modification_events=0,
                sl_hit_detected=False,
                realized_pl=5.0,
                entry_sl=1990.0,
                entry_price=2000.0,
                exit_price=2005.0,
            ),
        )
        _write_json(
            report_path,
            _build_managed_report(
                monitor_iterations=5,
                monitor_duration_seconds=300.0,
                breakeven_triggered=False,
                trailing_triggered=False,
                profit_lock_triggered=False,
                final_position_status="CLOSED",
            ),
        )

        result = a.run_audit(
            receipt_path=receipt_path,
            forensics_path=forensics_path,
            managed_report_path=report_path,
        )
        assert result["verdict"] == "TRAILING_MANAGER_OK_NO_TRIGGER", (
            f"Expected OK_NO_TRIGGER, got {result['verdict']}. "
            f"Blockers: {result.get('blockers', [])}"
        )
        assert result["blockers"] == []
        assert result["findings"]["sl_modification_events"] == 0
        assert result["findings"]["profit_R"] is not None
        assert result["findings"]["profit_R"] < 1.0
        assert result["findings"]["no_trailing_event_acceptable"] is True
        assert result["findings"]["sl_modification_expected"] is False

    # --- Test 5: BLOCKS when trigger reached but manager not running
    #     (profit_R >= 1.0 AND monitor_iterations >= 3 AND
    #      hold_seconds >= 60 AND sl_modification_events=0) ---
    def test_05_blocks_when_trigger_reached_but_not_running(self, tmp_path):
        import scripts.audit.trailing_manager_verification_audit as a

        receipt_path = tmp_path / "receipt.json"
        forensics_path = tmp_path / "forensics.json"
        report_path = tmp_path / "managed_trade_report.json"

        # profit_R = (2015 - 2000) / (2000 - 1990) = 15/10 = 1.5 >= 1.0
        # monitor_iterations=5 >= 3, hold_seconds=300 >= 60,
        # sl_modification_events=0, no trigger flags fired
        _write_json(receipt_path, _build_receipt(side="BUY"))
        _write_json(
            forensics_path,
            _build_forensics(
                root_cause="TRAILING_MANAGER_NOT_RUNNING",
                sl_modification_events=0,
                sl_hit_detected=False,
                realized_pl=15.0,
                entry_sl=1990.0,
                entry_price=2000.0,
                exit_price=2015.0,
            ),
        )
        _write_json(
            report_path,
            _build_managed_report(
                monitor_iterations=5,
                monitor_duration_seconds=300.0,
                breakeven_triggered=False,
                trailing_triggered=False,
                profit_lock_triggered=False,
                final_position_status="CLOSED",
            ),
        )

        result = a.run_audit(
            receipt_path=receipt_path,
            forensics_path=forensics_path,
            managed_report_path=report_path,
        )
        assert result["verdict"] == "TRAILING_MANAGER_BLOCKED_NOT_RUNNING", (
            f"Expected BLOCKED_NOT_RUNNING, got {result['verdict']}. "
            f"Blockers: {result.get('blockers', [])}"
        )
        assert len(result["blockers"]) >= 1
        assert result["findings"]["profit_R"] is not None
        assert result["findings"]["profit_R"] >= 1.0
        assert result["findings"]["monitor_iterations"] >= 3
        assert result["findings"]["hold_seconds"] >= 60
        assert result["findings"]["sl_modification_events"] == 0
        assert result["findings"]["sl_modification_expected"] is True
        assert result["findings"]["sl_modification_occurred"] is False

    # --- Test 6: WARNS when insufficient evidence ---
    def test_06_warns_when_insufficient_evidence(self, tmp_path):
        import scripts.audit.trailing_manager_verification_audit as a

        # No files at all - cannot determine anything
        result = a.run_audit(
            receipt_path=tmp_path / "missing_receipt.json",
            forensics_path=tmp_path / "missing_forensics.json",
            managed_report_path=tmp_path / "missing_report.json",
        )
        assert result["verdict"] == "TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE"
        assert result["findings"]["receipt_available"] is False
        assert result["findings"]["forensics_available"] is False
        assert result["findings"]["managed_trade_report_available"] is False
        assert result["findings"]["profit_R_computable"] is False

    # --- Test 7: no order_send in source ---
    def test_07_no_order_send_in_source(self):
        src = (
            REPO_ROOT
            / "scripts"
            / "audit"
            / "trailing_manager_verification_audit.py"
        ).read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bmt5\.order_modify\s*\(", code)
        assert not re.search(r"\border_send\s*\(", code)
        # Safety fields must explicitly record order_send_called=False
        assert '"order_send_called": False' in src or \
               "'order_send_called': False" in src or \
               '"order_send_called": False' in src

    # --- Test 8: no martingale / grid / averaging / loss-based lot ---
    def test_08_no_martingale_in_source(self):
        src = (
            REPO_ROOT
            / "scripts"
            / "audit"
            / "trailing_manager_verification_audit.py"
        ).read_text()
        code = _strip(src).lower()
        forbidden_terms = [
            "martingale",
            "grid_trade",
            "averaging_down",
            "double_lot",
            "add_position",
            "loss_based_lot",
            "recovery_multiplier",
            "double_after_loss",
            "loss_multiplier",
        ]
        for term in forbidden_terms:
            # The audit script may legitimately reference these as
            # safety flags in the safety dict (e.g., no_martingale=True)
            # but must not IMPLEMENT any of them.
            assert f"def {term}" not in code, \
                f"Function definition for '{term}' found in audit script"
            assert f"{term}()" not in code, \
                f"Function call to '{term}' found in audit script"
        # Safety fields must explicitly record no_martingale / no_grid /
        # no_averaging = True
        assert '"no_martingale": True' in src or \
               "'no_martingale': True" in src
        assert '"no_grid": True' in src or \
               "'no_grid': True" in src
        assert '"no_averaging": True' in src or \
               "'no_averaging': True" in src

    # --- Test 9: writes json and md ---
    def test_09_writes_json_and_md(self, tmp_path, monkeypatch):
        import scripts.audit.trailing_manager_verification_audit as a
        monkeypatch.setattr(a, "OUTPUT_DIR", tmp_path)
        result = a.run_audit(
            receipt_path=tmp_path / "missing_receipt.json",
            forensics_path=tmp_path / "missing_forensics.json",
            managed_report_path=tmp_path / "missing_report.json",
        )
        report = a.write_report(result)
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()
        # Verify JSON is parseable and contains verdict
        with open(report["json_path"], "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert "verdict" in loaded
        assert loaded["verdict"] == result["verdict"]
        # Verify MD contains the verdict
        md_text = Path(report["md_path"]).read_text(encoding="utf-8")
        assert result["verdict"] in md_text
        assert "Trailing Manager Verification Audit" in md_text

    # --- Test 10: reads forensics root_cause ---
    def test_10_reads_forensics_root_cause(self, tmp_path):
        import scripts.audit.trailing_manager_verification_audit as a

        receipt_path = tmp_path / "receipt.json"
        forensics_path = tmp_path / "forensics.json"
        report_path = tmp_path / "managed_trade_report.json"

        _write_json(receipt_path, _build_receipt(side="BUY"))
        _write_json(
            forensics_path,
            _build_forensics(
                root_cause="TRAILING_MANAGER_NOT_RUNNING",
                sl_modification_events=0,
                entry_price=2000.0,
                exit_price=2005.0,  # profit_R = 0.5 (no trigger)
            ),
        )
        _write_json(
            report_path,
            _build_managed_report(
                monitor_iterations=5,
                monitor_duration_seconds=300.0,
                final_position_status="CLOSED",
            ),
        )

        result = a.run_audit(
            receipt_path=receipt_path,
            forensics_path=forensics_path,
            managed_report_path=report_path,
        )
        # Forensics root_cause must be captured in findings
        assert (
            result["findings"]["forensics_root_cause"]
            == "TRAILING_MANAGER_NOT_RUNNING"
        )
        assert (
            result["findings"]["forensics_root_cause_is_trailing_not_running"]
            is True
        )

    # --- Test 11: OK_TRIGGERED when trigger fired and SL modified ---
    def test_11_ok_triggered_when_trigger_fired_and_sl_modified(self, tmp_path):
        import scripts.audit.trailing_manager_verification_audit as a

        receipt_path = tmp_path / "receipt.json"
        forensics_path = tmp_path / "forensics.json"
        report_path = tmp_path / "managed_trade_report.json"

        _write_json(receipt_path, _build_receipt(side="BUY"))
        _write_json(
            forensics_path,
            _build_forensics(
                root_cause="TRAILING_MANAGER_RUNNING",
                sl_modification_events=2,
                sl_hit_detected=False,
                realized_pl=20.0,
                entry_sl=1990.0,
                entry_price=2000.0,
                exit_price=2020.0,  # profit_R = 2.0
            ),
        )
        _write_json(
            report_path,
            _build_managed_report(
                monitor_iterations=10,
                monitor_duration_seconds=600.0,
                breakeven_triggered=True,
                trailing_triggered=True,
                profit_lock_triggered=False,
                final_position_status="CLOSED",
            ),
        )

        result = a.run_audit(
            receipt_path=receipt_path,
            forensics_path=forensics_path,
            managed_report_path=report_path,
        )
        assert result["verdict"] == "TRAILING_MANAGER_OK_TRIGGERED", (
            f"Expected OK_TRIGGERED, got {result['verdict']}. "
            f"Blockers: {result.get('blockers', [])}"
        )
        assert result["findings"]["trigger_fired"] is True
        assert result["findings"]["sl_modification_occurred"] is True

    # --- Test 12: SELL-side profit_R computation ---
    def test_12_sell_side_profit_R_computation(self, tmp_path):
        import scripts.audit.trailing_manager_verification_audit as a

        receipt_path = tmp_path / "receipt.json"
        forensics_path = tmp_path / "forensics.json"
        report_path = tmp_path / "managed_trade_report.json"

        # SELL: entry=2000, sl=2010 (risk=10), exit=1985 -> profit_R=1.5
        _write_json(receipt_path, _build_receipt(side="SELL"))
        _write_json(
            forensics_path,
            _build_forensics(
                root_cause="TRAILING_MANAGER_NOT_RUNNING",
                sl_modification_events=0,
                entry_sl=2010.0,
                entry_price=2000.0,
                exit_price=1985.0,
            ),
        )
        _write_json(
            report_path,
            _build_managed_report(
                monitor_iterations=5,
                monitor_duration_seconds=300.0,
                final_position_status="CLOSED",
            ),
        )

        result = a.run_audit(
            receipt_path=receipt_path,
            forensics_path=forensics_path,
            managed_report_path=report_path,
        )
        # profit_R should be 1.5 >= 1.0 -> BLOCKED_NOT_RUNNING
        assert result["findings"]["profit_R"] is not None
        assert abs(result["findings"]["profit_R"] - 1.5) < 1e-6
        assert result["verdict"] == "TRAILING_MANAGER_BLOCKED_NOT_RUNNING"

    # --- Test 13: MFE-based trigger detection ---
    def test_13_mfe_triggers_block_when_manager_silent(self, tmp_path):
        import scripts.audit.trailing_manager_verification_audit as a

        receipt_path = tmp_path / "receipt.json"
        forensics_path = tmp_path / "forensics.json"
        report_path = tmp_path / "managed_trade_report.json"

        # exit_price gives profit_R < 1.0 (position closed at small profit)
        # but MFE=2.5R shows the position was deep in profit during monitor
        _write_json(receipt_path, _build_receipt(side="BUY"))
        _write_json(
            forensics_path,
            _build_forensics(
                root_cause="TRAILING_MANAGER_NOT_RUNNING",
                sl_modification_events=0,
                entry_sl=1990.0,
                entry_price=2000.0,
                exit_price=2005.0,  # profit_R = 0.5
                mfe=2.5,  # MFE in R-multiples
            ),
        )
        _write_json(
            report_path,
            _build_managed_report(
                monitor_iterations=5,
                monitor_duration_seconds=300.0,
                final_position_status="CLOSED",
            ),
        )

        result = a.run_audit(
            receipt_path=receipt_path,
            forensics_path=forensics_path,
            managed_report_path=report_path,
        )
        # MFE 2.5R >= breakeven_trigger_R=1.0, monitor + hold met, no SL mod
        assert result["findings"]["mfe_available"] is True
        assert result["findings"]["mfe_profit_R"] == 2.5
        assert result["verdict"] == "TRAILING_MANAGER_BLOCKED_NOT_RUNNING"

    # --- Test 14: trigger fired but no SL modification AND monitor/hold
    #     conditions not met -> WARN (not BLOCKED) ---
    def test_14_trigger_fired_no_sl_mod_insufficient_monitor_warns(
        self, tmp_path
    ):
        import scripts.audit.trailing_manager_verification_audit as a

        receipt_path = tmp_path / "receipt.json"
        forensics_path = tmp_path / "forensics.json"
        report_path = tmp_path / "managed_trade_report.json"

        _write_json(receipt_path, _build_receipt(side="BUY"))
        _write_json(
            forensics_path,
            _build_forensics(
                root_cause="TRAILING_MANAGER_NOT_RUNNING",
                sl_modification_events=0,
                entry_price=2000.0,
                exit_price=2010.0,  # profit_R = 1.0
            ),
        )
        # monitor_iterations=1 (< 3 min) and hold=10 (< 60 min) - insufficient
        _write_json(
            report_path,
            _build_managed_report(
                monitor_iterations=1,
                monitor_duration_seconds=10.0,
                breakeven_triggered=True,  # trigger fired
                trailing_triggered=False,
                profit_lock_triggered=False,
                final_position_status="CLOSED",
            ),
        )

        result = a.run_audit(
            receipt_path=receipt_path,
            forensics_path=forensics_path,
            managed_report_path=report_path,
        )
        # Trigger fired but monitor/hold conditions not met -> WARN
        assert result["verdict"] == (
            "TRAILING_MANAGER_WARN_INSUFFICIENT_EVIDENCE"
        )
        assert result["findings"]["trigger_fired"] is True
        assert result["findings"]["monitor_iterations_sufficient"] is False
        assert result["findings"]["hold_seconds_sufficient"] is False

    # --- Test 15: no mt5 import in audit script ---
    def test_15_no_mt5_import_in_audit(self):
        src = (
            REPO_ROOT
            / "scripts"
            / "audit"
            / "trailing_manager_verification_audit.py"
        ).read_text()
        code = _strip(src)
        # Must not import MetaTrader5 or mt5
        assert not re.search(r"\bimport\s+MetaTrader5\b", code)
        assert not re.search(r"\bfrom\s+MetaTrader5\b", code)
        assert not re.search(r"\bimport\s+mt5\b", code)

    # --- Test 16: profit_R below threshold with high monitor_iterations
    #     does not block ---
    def test_16_zero_sl_modifications_with_zero_profit_R_is_ok(self, tmp_path):
        """Regression: sl_modification_events=0 alone must NOT cause
        BLOCKED - only when profit_R >= breakeven_trigger_R AND
        monitor_iterations >= min AND hold_seconds >= min."""
        import scripts.audit.trailing_manager_verification_audit as a

        receipt_path = tmp_path / "receipt.json"
        forensics_path = tmp_path / "forensics.json"
        report_path = tmp_path / "managed_trade_report.json"

        # profit_R = (2000 - 2000) / 10 = 0.0 < 1.0 -> NO TRIGGER
        _write_json(receipt_path, _build_receipt(side="BUY"))
        _write_json(
            forensics_path,
            _build_forensics(
                root_cause="TRAILING_MANAGER_NOT_RUNNING",
                sl_modification_events=0,
                entry_sl=1990.0,
                entry_price=2000.0,
                exit_price=2000.0,  # profit_R = 0.0
            ),
        )
        _write_json(
            report_path,
            _build_managed_report(
                monitor_iterations=10,
                monitor_duration_seconds=600.0,
                final_position_status="CLOSED",
            ),
        )

        result = a.run_audit(
            receipt_path=receipt_path,
            forensics_path=forensics_path,
            managed_report_path=report_path,
        )
        # Even with high monitor_iterations and hold_seconds, since
        # profit_R < breakeven_trigger_R, sl_modification_events=0 is OK.
        assert result["verdict"] == "TRAILING_MANAGER_OK_NO_TRIGGER"
        assert result["blockers"] == []
        assert result["findings"]["sl_modification_events"] == 0
        assert result["findings"]["no_trailing_event_acceptable"] is True

    # --- Test 17: position closed cleanly without SL hit and no trigger
    #     flags -> OK_NO_TRIGGER even when profit_R not computable ---
    def test_17_closed_no_sl_hit_no_trigger_ok_no_trigger(self, tmp_path):
        import scripts.audit.trailing_manager_verification_audit as a

        receipt_path = tmp_path / "receipt.json"
        forensics_path = tmp_path / "forensics.json"
        report_path = tmp_path / "managed_trade_report.json"

        # No entry_sl / entry_price -> profit_R not computable
        _write_json(receipt_path, _build_receipt(side="BUY"))
        _write_json(
            forensics_path,
            _build_forensics(
                root_cause="NO_OPEN_POSITION_TO_MANAGE",
                sl_modification_events=0,
                sl_hit_detected=False,
                entry_sl=0.0,
                entry_price=0.0,
                exit_price=0.0,
            ),
        )
        _write_json(
            report_path,
            _build_managed_report(
                monitor_iterations=3,
                monitor_duration_seconds=120.0,
                breakeven_triggered=False,
                trailing_triggered=False,
                profit_lock_triggered=False,
                final_position_status="CLOSED",
            ),
        )

        result = a.run_audit(
            receipt_path=receipt_path,
            forensics_path=forensics_path,
            managed_report_path=report_path,
        )
        assert result["verdict"] == "TRAILING_MANAGER_OK_NO_TRIGGER"
        assert result["findings"]["profit_R_computable"] is False

    # --- Test 18: safety fields present and correct ---
    def test_18_safety_fields(self, tmp_path):
        import scripts.audit.trailing_manager_verification_audit as a
        result = a.run_audit(
            receipt_path=tmp_path / "missing.json",
            forensics_path=tmp_path / "missing.json",
            managed_report_path=tmp_path / "missing.json",
        )
        assert result["safety"]["order_send_called"] is False
        assert result["safety"]["position_modified"] is False
        assert result["safety"]["no_martingale"] is True
        assert result["safety"]["no_grid"] is True
        assert result["safety"]["no_averaging"] is True

    # --- Test 19: from __future__ import annotations at top ---
    def test_19_future_annotations_import(self):
        src = (
            REPO_ROOT
            / "scripts"
            / "audit"
            / "trailing_manager_verification_audit.py"
        ).read_text()
        # Must have the future import in the first 50 lines
        head = "\n".join(src.splitlines()[:50])
        assert "from __future__ import annotations" in head

    # --- Test 20: write_report creates parent directory if missing ---
    def test_20_write_report_creates_parent_dir(self, tmp_path, monkeypatch):
        import scripts.audit.trailing_manager_verification_audit as a
        nested = tmp_path / "nested" / "deep" / "out"
        monkeypatch.setattr(a, "OUTPUT_DIR", nested)
        result = a.run_audit(
            receipt_path=tmp_path / "missing.json",
            forensics_path=tmp_path / "missing.json",
            managed_report_path=tmp_path / "missing.json",
        )
        report = a.write_report(result)
        assert nested.exists()
        assert Path(report["json_path"]).exists()
        assert Path(report["md_path"]).exists()
