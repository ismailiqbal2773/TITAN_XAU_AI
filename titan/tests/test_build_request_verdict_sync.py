"""TITAN XAU AI - Sprint v2.8.3.2 Build-Request Verdict Sync Tests

Tests the sync between top-level build-request verdict and the
v2.8.3.1 normalized verdict. After v2.8.3.2, the top-level
``verdict``/``blockers``/``blocker_count`` fields MUST match the
normalized verdict when all upstream gates pass.

Required tests:
  A. build-request normalized PASS syncs top-level
  B. build-request BLOCKED remains blocked (fail-closed)
  C. OPERATOR_ARM_TOKEN_REQUIRED is not a build-request blocker
  D. Safety regression: no order_send in --build-request or --autonomous-entry-check
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


AUDIT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"
AE_PATH = AUDIT_DIR / "autonomous_entry_decision.json"
ENTRY_GATE_PATH = AUDIT_DIR / "end_to_end_entry_gate_audit.json"
AUTONOMOUS_READINESS_PATH = AUDIT_DIR / "autonomous_demo_readiness_audit.json"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _backup_audit_files():
    backups = {}
    for p in (AE_PATH, ENTRY_GATE_PATH, AUTONOMOUS_READINESS_PATH):
        if p.exists():
            backups[str(p)] = p.read_text(encoding="utf-8")
        else:
            backups[str(p)] = None
    return backups


def _restore_audit_files(backups):
    for p_str, content in backups.items():
        p = Path(p_str)
        if content is None:
            if p.exists():
                p.unlink()
        else:
            p.write_text(content, encoding="utf-8")


def _seed_passing_audit_files():
    _write_json(AE_PATH, {
        "final_decision": "ALPHA_REGIME_ENTRY_PASS",
        "regime_detected": True, "regime_value": "SPREAD_EXPANSION",
        "alpha_signal_detected": True, "alpha_direction": "LONG",
        "alpha_confidence": 0.5989, "alpha_threshold": 0.55, "alpha_pass": True,
        "risk_gate_pass": True, "broker_gate_pass": True,
        "prop_funded_gate_pass": True, "geometry_gate_pass": True,
    })
    _write_json(ENTRY_GATE_PATH, {"verdict": "ENTRY_GATE_FULL_PASS", "blockers": []})
    _write_json(AUTONOMOUS_READINESS_PATH, {
        "verdict": "AUTONOMOUS_DEMO_READY_SUPERVISED", "blockers": [], "autonomous_allowed": True,
    })


def _seed_blocking_audit_files():
    _write_json(AE_PATH, {"final_decision": "ALPHA_REGIME_ENTRY_BLOCKED_RISK_GATE"})
    _write_json(ENTRY_GATE_PATH, {"verdict": "ENTRY_GATE_BLOCKED", "blockers": ["risk_gate_blocked"]})
    _write_json(AUTONOMOUS_READINESS_PATH, {
        "verdict": "AUTONOMOUS_DEMO_BLOCKED", "blockers": ["autonomous_blocked"],
    })


class TestBuildRequestVerdictSync:
    def setup_method(self):
        self._backups = _backup_audit_files()

    def teardown_method(self):
        _restore_audit_files(self._backups)

    def test_a_build_request_normalized_pass_syncs_top_level(self):
        _seed_passing_audit_files()
        import scripts.operator.run_managed_demo_micro_trade as m

        result = {
            "mode": "build_request", "verdict": "BLOCKED",
            "blockers": ["BROKER_BLOCKED: score=0 < 70"],
            "end_to_end_entry_gate_status": "ENTRY_GATE_FULL_PASS",
            "end_to_end_entry_gate_blockers": [],
            "autonomous_demo_readiness_status": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_demo_blockers": [],
            "ceo_governance_imported": True,
            "ceo_governance_called": True,
            "ceo_final_decision": "PASS",
            "ceo_allowed_to_trade": True,
            "ceo_blockers": [],
        }
        m.apply_build_request_verdict_sync(result)

        assert result["verdict"] == "PASS"
        assert result["blockers"] == []
        assert result["blocker_count"] == 0
        assert result["normalized_verdict"] == "PASS"
        assert result["normalized_blockers"] == []
        assert result["normalized_blocker_count"] == 0
        assert result["request_status"] == "READY_FOR_SUPERVISED_OPERATOR_ARM"
        assert result["autonomous_entry_decision_pass"] is True
        assert result["entry_gate_pass"] is True
        assert result["autonomous_readiness_pass"] is True
        assert result["supervised_only"] is True
        assert result["execution_now_allowed"] is False
        assert result["execution_blocker"] == "OPERATOR_ARM_TOKEN_REQUIRED"

    def test_b_build_request_blocked_remains_blocked(self):
        _seed_blocking_audit_files()
        import scripts.operator.run_managed_demo_micro_trade as m

        result = {
            "mode": "build_request", "verdict": "BLOCKED",
            "blockers": ["risk_gate_blocked", "autonomous_blocked"],
            "end_to_end_entry_gate_status": "ENTRY_GATE_BLOCKED",
            "end_to_end_entry_gate_blockers": ["risk_gate_blocked"],
            "autonomous_demo_readiness_status": "AUTONOMOUS_DEMO_BLOCKED",
            "autonomous_demo_blockers": ["autonomous_blocked"],
            # v2.8.5-D: CEO governance fields (CEO passes, but gates blocked)
            "ceo_governance_imported": True,
            "ceo_governance_called": True,
            "ceo_final_decision": "BLOCKED",
            "ceo_allowed_to_trade": False,
            "ceo_blockers": ["CEO_REGIME_NOT_DETECTED"],
        }
        m.apply_build_request_verdict_sync(result)

        assert result["verdict"] == "BLOCKED"
        # v2.8.5-D: CEO blockers add to the count
        assert result["blocker_count"] >= 2
        assert result["normalized_verdict"] == "BLOCKED"
        assert result["normalized_blocker_count"] > 0
        assert result["request_status"] == "BLOCKED"
        assert result["execution_now_allowed"] is False
        assert result["execution_blocker"] == "OPERATOR_ARM_TOKEN_REQUIRED"

    def test_c_operator_arm_token_required_not_a_build_request_blocker(self):
        _seed_passing_audit_files()
        import scripts.operator.run_managed_demo_micro_trade as m

        result = {
            "mode": "build_request", "verdict": "BLOCKED",
            "blockers": ["BROKER_BLOCKED: score=0 < 70"],
            "end_to_end_entry_gate_status": "ENTRY_GATE_FULL_PASS",
            "end_to_end_entry_gate_blockers": [],
            "autonomous_demo_readiness_status": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_demo_blockers": [],
            "ceo_governance_imported": True,
            "ceo_governance_called": True,
            "ceo_final_decision": "PASS",
            "ceo_allowed_to_trade": True,
            "ceo_blockers": [],
        }
        m.apply_build_request_verdict_sync(result)

        assert result["verdict"] == "PASS"
        assert result["blocker_count"] == 0
        assert result["blockers"] == []
        assert result["execution_now_allowed"] is False
        assert result["execution_blocker"] == "OPERATOR_ARM_TOKEN_REQUIRED"

        all_blockers = (result.get("blockers", []) or []) + (result.get("normalized_blockers", []) or [])
        assert not any("OPERATOR_ARM_TOKEN_REQUIRED" in str(b) for b in all_blockers), \
            f"OPERATOR_ARM_TOKEN_REQUIRED must NOT be a build-request blocker, found in: {all_blockers}"

    def test_d_no_order_send_in_build_request_or_autonomous_entry_check(self):
        _seed_passing_audit_files()
        import scripts.operator.run_managed_demo_micro_trade as m

        fake_mt5 = MagicMock()
        fake_mt5.initialize.return_value = True
        fake_mt5.shutdown.return_value = None
        fake_mt5.account_info.return_value = MagicMock(
            server="MetaQuotes-Demo", login=12345, balance=10000.0,
            currency="USD", leverage=100, trade_allowed=True,
        )
        fake_mt5.symbol_info.return_value = MagicMock(
            visible=True, trade_mode=0, bid=2000.0, ask=2000.5, digits=2, point=0.01,
        )
        fake_mt5.positions_get.return_value = ()
        fake_mt5.order_send.return_value = MagicMock(retcode=0, comment="")

        with patch.dict(sys.modules, {"MetaTrader5": fake_mt5}):
            argv_br = [
                "run_managed_demo_micro_trade.py", "--build-request",
                "--prop-funded-profile", "prop_funded_safe",
                "--use-adaptive-trailing", "--use-dynamic-tp-extension",
            ]
            with patch.object(sys, "argv", argv_br):
                try:
                    m.main()
                except SystemExit:
                    pass
            assert fake_mt5.order_send.call_count == 0, \
                f"order_send must NOT be called in --build-request, got {fake_mt5.order_send.call_count} calls"

            argv_ae = [
                "run_managed_demo_micro_trade.py", "--autonomous-entry-check",
                "--prop-funded-profile", "prop_funded_safe",
                "--use-adaptive-trailing", "--use-dynamic-tp-extension",
            ]
            with patch.object(sys, "argv", argv_ae):
                try:
                    m.main()
                except SystemExit:
                    pass
            assert fake_mt5.order_send.call_count == 0, \
                f"order_send must NOT be called in --autonomous-entry-check, got {fake_mt5.order_send.call_count} calls"

    def test_e_write_report_emits_normalized_fields(self):
        _seed_passing_audit_files()
        import scripts.operator.run_managed_demo_micro_trade as m

        result = {
            "mode": "build_request", "verdict": "PASS", "blockers": [], "blocker_count": 0,
            "normalized_verdict": "PASS", "normalized_blockers": [], "normalized_blocker_count": 0,
            "request_status": "READY_FOR_SUPERVISED_OPERATOR_ARM",
            "autonomous_entry_decision_pass": True, "entry_gate_pass": True,
            "autonomous_readiness_pass": True, "supervised_only": True,
            "execution_now_allowed": False, "execution_blocker": "OPERATOR_ARM_TOKEN_REQUIRED",
            "timestamp_utc": "2026-07-02T00:00:00Z",
        }

        report = m.write_report(result)
        json_path = Path(report["json_path"])
        md_path = Path(report["md_path"])

        with open(json_path, "r", encoding="utf-8") as f:
            j = json.load(f)
        assert j["mode"] == "build_request"
        assert j["verdict"] == "PASS"
        assert j["blockers"] == []
        assert j["blocker_count"] == 0
        assert j["normalized_verdict"] == "PASS"
        assert j["normalized_blockers"] == []
        assert j["normalized_blocker_count"] == 0
        assert j["request_status"] == "READY_FOR_SUPERVISED_OPERATOR_ARM"
        assert j["execution_now_allowed"] is False
        assert j["execution_blocker"] == "OPERATOR_ARM_TOKEN_REQUIRED"

        md = md_path.read_text(encoding="utf-8")
        assert "**Mode:** build_request" in md
        assert "**Verdict:** **PASS**" in md
        assert "**Blockers:** 0" in md
        assert "Build-Request Verdict Normalization" in md
        assert "READY_FOR_SUPERVISED_OPERATOR_ARM" in md
        assert "OPERATOR_ARM_TOKEN_REQUIRED" in md
        assert "execution_now_allowed" in md
        assert "execution_blocker" in md

    def test_f_apply_sync_ignored_for_non_build_request(self):
        import scripts.operator.run_managed_demo_micro_trade as m
        original = {
            "mode": "autonomous_entry_check", "verdict": "ALPHA_REGIME_ENTRY_PASS", "blockers": [],
        }
        result = dict(original)
        m.apply_build_request_verdict_sync(result)
        assert result["verdict"] == "ALPHA_REGIME_ENTRY_PASS"
        assert result["blockers"] == []
        assert "normalized_verdict" not in result
        assert "request_status" not in result

    def test_g_missing_audit_inputs_keeps_fail_closed(self):
        for p in (AE_PATH, ENTRY_GATE_PATH, AUTONOMOUS_READINESS_PATH):
            if p.exists():
                p.unlink()
        import scripts.operator.run_managed_demo_micro_trade as m

        result = {
            "mode": "build_request", "verdict": "BLOCKED",
            "blockers": ["BROKER_BLOCKED: score=0 < 70"],
            "end_to_end_entry_gate_status": "",
            "end_to_end_entry_gate_blockers": [],
            "autonomous_demo_readiness_status": "",
            "autonomous_demo_blockers": [],
            "ceo_governance_imported": True,
            "ceo_governance_called": True,
            "ceo_final_decision": "PASS",
            "ceo_allowed_to_trade": True,
            "ceo_blockers": [],
        }
        m.apply_build_request_verdict_sync(result)

        assert result["verdict"] == "BLOCKED"
        assert result["blocker_count"] >= 1
        assert result["normalized_verdict"] == "BLOCKED"
        assert result["request_status"] == "BLOCKED"
        assert result["execution_now_allowed"] is False
        assert result["execution_blocker"] == "OPERATOR_ARM_TOKEN_REQUIRED"
