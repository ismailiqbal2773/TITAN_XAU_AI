"""TITAN XAU AI - Sprint v2.8.5 Final Demo Activation Readiness Tests

Tests the final demo activation readiness audit, production closure integration,
build-request integration, and operator runbook.

Required tests (per sprint spec):
  1.  final demo activation passes when all gates pass
  2.  blocks when model health has required failure
  3.  blocks when feature parity blocked
  4.  blocks when runtime safety blocked
  5.  blocks when growth profile blocked
  6.  blocks when production closure has blockers
  7.  blocks when account is not MetaQuotes-Demo
  8.  blocks when account is live/funded/real
  9.  blocks when XAUUSD open position exists
  10. blocks when XAUUSD pending order exists
  11. blocks when stale operator token exists
  12. old stale receipt non-blocking only when no open/pending position
  13. final demo activation audit never calls mt5.order_send
  14. final demo activation audit never creates token
  15. final demo activation audit never modifies positions
  16. production closure reads final activation verdict
  17. build-request displays final activation verdict
  18. build-request remains read-only
  19. runbook contains exact operator commands
  20. FundedNext execution remains blocked
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

AUDIT_DEMO_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"
MODEL_HEALTH_DIR = REPO_ROOT / "data" / "audit" / "model_health"
GROWTH_DIR = REPO_ROOT / "data" / "audit" / "prop_challenge_growth"
FINAL_ACTIVATION_DIR = REPO_ROOT / "data" / "audit" / "final_demo_activation"
MH_PATH = MODEL_HEALTH_DIR / "model_artifact_health_audit.json"
FP_PATH = MODEL_HEALTH_DIR / "feature_parity_audit.json"
RS_PATH = AUDIT_DEMO_DIR / "runtime_safety_gate_audit.json"
GP_PATH = GROWTH_DIR / "prop_challenge_growth_profile_audit.json"
PC_PATH = AUDIT_DEMO_DIR / "production_closure_readiness_audit.json"
FA_PATH = FINAL_ACTIVATION_DIR / "final_demo_activation_readiness_audit.json"
BR_PATH = AUDIT_DEMO_DIR / "managed_trade_report.json"
TOKEN_PATH = REPO_ROOT / "data" / "runtime" / "operator_execution_token.json"
RECEIPT_PATH = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"
RUNBOOK_PATH = REPO_ROOT / "docs" / "FINAL_METAQUOTES_DEMO_START_RUNBOOK.md"


def _backup(paths):
    backups = {}
    for p in paths:
        if p.exists():
            backups[str(p)] = p.read_text(encoding="utf-8")
        else:
            backups[str(p)] = None
    return backups


def _restore(backups):
    for p_str, content in backups.items():
        p = Path(p_str)
        if content is None:
            if p.exists():
                p.unlink()
        else:
            p.write_text(content, encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _seed_all_passing():
    """Seed all required audit JSONs as PASS."""
    _write_json(MH_PATH, {
        "verdict": "MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS",
        "active_model_count": 9, "failed_required_model_count": 0,
        "failed_optional_model_count": 0,
        "blocked_required_models": [], "warned_optional_models": [],
        "v2_8_4_allowed": True,
    })
    _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS"})
    _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})
    _write_json(GP_PATH, {
        "verdict": "PROP_CHALLENGE_GROWTH_PROFILE_PASS",
        "profile_name": "PROP_CHALLENGE_GROWTH_30_8",
        "findings": {},
    })
    _write_json(PC_PATH, {
        "verdict": "PRODUCTION_CLOSURE_READY_WITH_SAFE_DEFAULTS",
        "blockers": [],
    })
    _write_json(BR_PATH, {
        "mode": "build_request", "verdict": "PASS",
        "normalized_verdict": "PASS",
        "request_status": "READY_FOR_SUPERVISED_OPERATOR_ARM",
        "execution_now_allowed": False,
        "execution_blocker": "OPERATOR_ARM_TOKEN_REQUIRED",
    })


def _mock_mt5_env(server="MetaQuotes-Demo", account_type="DEMO",
                  symbol_available=True, open_positions=0, pending_orders=0,
                  spread=0.5, mt5_available=True, initialized=True):
    """Build a mock MT5 environment dict for _check_mt5_environment."""
    return {
        "mt5_available": mt5_available, "initialized": initialized,
        "account_server": server, "account_type": account_type,
        "symbol_available": symbol_available,
        "latest_tick": {"bid": 2000.0, "ask": 2000.5, "time": 0} if symbol_available else {},
        "spread_usd": spread,
        "open_positions_count": open_positions, "pending_orders_count": pending_orders,
        "open_xauusd_positions": open_positions, "pending_xauusd_orders": pending_orders,
        "error": "",
    }


# ============================================================
# Tests 1-6: Final demo activation verdict logic
# ============================================================

class TestFinalDemoActivationVerdict:
    """Tests 1-6: Final demo activation audit verdict logic."""

    def setup_method(self):
        self._backups = _backup([MH_PATH, FP_PATH, RS_PATH, GP_PATH, PC_PATH, BR_PATH,
                                  FA_PATH, TOKEN_PATH, RECEIPT_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_01_passes_when_all_gates_pass(self):
        """Test 1: FINAL_DEMO_ACTIVATION_READY_SUPERVISED when all gates pass."""
        _seed_all_passing()
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment', return_value=_mock_mt5_env()):
            result = m.run_audit()
        assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_READY_SUPERVISED
        assert result["final_demo_activation_allowed"] is True
        assert len(result["blockers"]) == 0

    def test_02_blocks_when_model_health_required_failure(self):
        """Test 2: BLOCKED when model health has required failure."""
        _seed_all_passing()
        # Override model health to BLOCKED
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_BLOCKED",
            "active_model_count": 2, "failed_required_model_count": 1,
            "failed_optional_model_count": 0,
            "blocked_required_models": [{"name": "broken", "role": "active_primary"}],
            "warned_optional_models": [], "v2_8_4_allowed": False,
        })
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment', return_value=_mock_mt5_env()):
            result = m.run_audit()
        assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_BLOCKED
        assert any("MODEL_HEALTH_NOT_PASS" in b for b in result["blockers"])

    def test_03_blocks_when_feature_parity_blocked(self):
        """Test 3: BLOCKED when feature parity blocked."""
        _seed_all_passing()
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_BLOCKED"})
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment', return_value=_mock_mt5_env()):
            result = m.run_audit()
        assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_BLOCKED
        assert any("FEATURE_PARITY_NOT_PASS" in b for b in result["blockers"])

    def test_04_blocks_when_runtime_safety_blocked(self):
        """Test 4: BLOCKED when runtime safety blocked."""
        _seed_all_passing()
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_BLOCKED"})
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment', return_value=_mock_mt5_env()):
            result = m.run_audit()
        assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_BLOCKED
        assert any("RUNTIME_SAFETY_NOT_PASS" in b for b in result["blockers"])

    def test_05_blocks_when_growth_profile_blocked(self):
        """Test 5: BLOCKED when growth profile blocked."""
        _seed_all_passing()
        _write_json(GP_PATH, {
            "verdict": "PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED",
            "profile_name": "PROP_CHALLENGE_GROWTH_30_8", "findings": {},
        })
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment', return_value=_mock_mt5_env()):
            result = m.run_audit()
        assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_BLOCKED
        assert any("GROWTH_PROFILE_NOT_PASS" in b for b in result["blockers"])

    def test_06_blocks_when_production_closure_has_blockers(self):
        """Test 6: BLOCKED when production closure has blockers."""
        _seed_all_passing()
        _write_json(PC_PATH, {
            "verdict": "PRODUCTION_CLOSURE_BLOCKED",
            "blockers": ["some_blocker"],
        })
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment', return_value=_mock_mt5_env()):
            result = m.run_audit()
        assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_BLOCKED
        assert any("PRODUCTION_CLOSURE_NOT_READY" in b for b in result["blockers"])


# ============================================================
# Tests 7-12: MT5 environment + receipt checks
# ============================================================

class TestFinalDemoActivationMT5Env:
    """Tests 7-12: MT5 environment and receipt checks."""

    def setup_method(self):
        self._backups = _backup([MH_PATH, FP_PATH, RS_PATH, GP_PATH, PC_PATH, BR_PATH,
                                  FA_PATH, TOKEN_PATH, RECEIPT_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_07_blocks_when_account_not_metaquotes_demo(self):
        """Test 7: BLOCKED when account server is not MetaQuotes-Demo."""
        _seed_all_passing()
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment',
                          return_value=_mock_mt5_env(server="FundedNext-Demo")):
            result = m.run_audit()
        assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_BLOCKED
        assert any("ACCOUNT_SERVER_NOT_METAQUOTES_DEMO" in b for b in result["blockers"])

    def test_08_blocks_when_account_live_funded_real(self):
        """Test 8: BLOCKED when account type is LIVE/CONTEST."""
        _seed_all_passing()
        import scripts.audit.final_demo_activation_readiness_audit as m
        for bad_type in ("LIVE", "CONTEST"):
            with patch.object(m, '_check_mt5_environment',
                              return_value=_mock_mt5_env(account_type=bad_type)):
                result = m.run_audit()
            assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_BLOCKED, \
                f"account_type={bad_type} should block"
            assert any("ACCOUNT_TYPE_NOT_DEMO" in b for b in result["blockers"]), \
                f"account_type={bad_type} should add ACCOUNT_TYPE_NOT_DEMO blocker"

    def test_09_blocks_when_xauusd_open_position_exists(self):
        """Test 9: BLOCKED when XAUUSD open position exists."""
        _seed_all_passing()
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment',
                          return_value=_mock_mt5_env(open_positions=1)):
            result = m.run_audit()
        assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_BLOCKED
        assert any("OPEN_XAUUSD_POSITION_EXISTS" in b for b in result["blockers"])

    def test_10_blocks_when_xauusd_pending_order_exists(self):
        """Test 10: BLOCKED when XAUUSD pending order exists."""
        _seed_all_passing()
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment',
                          return_value=_mock_mt5_env(pending_orders=1)):
            result = m.run_audit()
        assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_BLOCKED
        assert any("PENDING_XAUUSD_ORDER_EXISTS" in b for b in result["blockers"])

    def test_11_blocks_when_stale_operator_token_exists(self):
        """Test 11: BLOCKED when stale operator token exists."""
        _seed_all_passing()
        # Create a stale token file (>1hr old)
        from datetime import datetime, timezone, timedelta
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        _write_json(TOKEN_PATH, {"created_at": old_ts, "symbol": "XAUUSD"})
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment', return_value=_mock_mt5_env()):
            result = m.run_audit()
        assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_BLOCKED
        assert any("STALE_OPERATOR_TOKEN" in b for b in result["blockers"])

    def test_12_old_stale_receipt_non_blocking_when_no_open_pending(self):
        """Test 12: Old stale receipt is non-blocking when no open/pending position."""
        _seed_all_passing()
        # Create a stale receipt file
        RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _write_json(RECEIPT_PATH, {
            "timestamp_utc": "2026-01-01T00:00:00Z",
            "success": True,
            "order_ticket": 12345,
        })
        import scripts.audit.final_demo_activation_readiness_audit as m
        # No open/pending position -> stale receipt is non-blocking
        with patch.object(m, '_check_mt5_environment',
                          return_value=_mock_mt5_env(open_positions=0, pending_orders=0)):
            result = m.run_audit()
        # Stale receipt non-blocking -> verdict can still be READY_SUPERVISED
        assert "UNRESOLVED_ACTIVE_RECEIPT" not in " ".join(result["blockers"])
        assert any("STALE_RECEIPT_NON_BLOCKING" in w for w in result["warnings"])


# ============================================================
# Tests 13-15: Safety invariants
# ============================================================

class TestFinalDemoActivationSafety:
    """Tests 13-15: Final demo activation audit never violates safety."""

    def setup_method(self):
        self._backups = _backup([MH_PATH, FP_PATH, RS_PATH, GP_PATH, PC_PATH, BR_PATH,
                                  FA_PATH, TOKEN_PATH, RECEIPT_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_13_never_calls_mt5_order_send(self):
        """Test 13: Final demo activation audit never calls mt5.order_send."""
        _seed_all_passing()
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment', return_value=_mock_mt5_env()):
            result = m.run_audit()
        assert result["safety"]["order_send_called"] is False

    def test_14_never_creates_token(self):
        """Test 14: Final demo activation audit never creates operator token."""
        _seed_all_passing()
        import scripts.audit.final_demo_activation_readiness_audit as m
        # Ensure no token exists before audit
        if TOKEN_PATH.exists():
            TOKEN_PATH.unlink()
        with patch.object(m, '_check_mt5_environment', return_value=_mock_mt5_env()):
            result = m.run_audit()
        assert result["safety"]["token_created"] is False
        # Token file should NOT have been created
        assert not TOKEN_PATH.exists(), "Audit must not create token file"

    def test_15_never_modifies_positions(self):
        """Test 15: Final demo activation audit never modifies positions."""
        _seed_all_passing()
        import scripts.audit.final_demo_activation_readiness_audit as m
        with patch.object(m, '_check_mt5_environment', return_value=_mock_mt5_env()):
            result = m.run_audit()
        assert result["safety"]["position_modified"] is False


# ============================================================
# Tests 16-18: Production closure + build-request integration
# ============================================================

class TestFinalActivationIntegration:
    """Tests 16-18: Production closure and build-request read final activation."""

    def setup_method(self):
        self._backups = _backup([MH_PATH, FP_PATH, RS_PATH, GP_PATH, PC_PATH, BR_PATH,
                                  FA_PATH, TOKEN_PATH, RECEIPT_PATH,
                                  AUDIT_DEMO_DIR / "autonomous_entry_decision.json",
                                  AUDIT_DEMO_DIR / "end_to_end_entry_gate_audit.json",
                                  AUDIT_DEMO_DIR / "autonomous_demo_readiness_audit.json"])

    def teardown_method(self):
        _restore(self._backups)

    def test_16_production_closure_reads_final_activation_verdict(self):
        """Test 16: Production closure reads latest_final_demo_activation_verdict."""
        _seed_all_passing()
        # Seed final activation audit
        _write_json(FA_PATH, {
            "verdict": "FINAL_DEMO_ACTIVATION_READY_SUPERVISED",
            "final_demo_activation_allowed": True,
            "findings": {
                "mt5_environment": {
                    "account_server": "MetaQuotes-Demo",
                    "account_type": "DEMO",
                    "open_xauusd_positions": 0,
                    "pending_xauusd_orders": 0,
                },
                "operator_token": {"stale": False},
                "build_request_execution_blocker": "OPERATOR_ARM_TOKEN_REQUIRED",
            },
        })
        # Seed autonomous readiness as SUPERVISED
        _write_json(AUDIT_DEMO_DIR / "autonomous_demo_readiness_audit.json", {
            "verdict": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_allowed": True, "blockers": [],
        })
        _write_json(AUDIT_DEMO_DIR / "end_to_end_entry_gate_audit.json", {
            "verdict": "ENTRY_GATE_FULL_PASS", "blockers": [],
        })
        import scripts.audit.production_closure_readiness_audit as m
        result = m.run_audit()
        assert "latest_final_demo_activation_verdict" in result
        assert "final_demo_activation_pass" in result
        assert "final_demo_activation_allowed" in result
        assert "metaquotes_demo_verified" in result
        assert "open_positions_count" in result
        assert "pending_orders_count" in result
        assert "stale_token_detected" in result
        assert result["latest_final_demo_activation_verdict"] == "FINAL_DEMO_ACTIVATION_READY_SUPERVISED"
        assert result["final_demo_activation_pass"] is True
        assert result["final_demo_activation_allowed"] is True
        assert result["metaquotes_demo_verified"] is True

    def test_17_build_request_displays_final_activation_verdict(self):
        """Test 17: Build-request displays final activation verdict fields."""
        _seed_all_passing()
        _write_json(FA_PATH, {
            "verdict": "FINAL_DEMO_ACTIVATION_READY_SUPERVISED",
            "final_demo_activation_allowed": True,
            "findings": {
                "mt5_environment": {
                    "account_server": "MetaQuotes-Demo",
                    "account_type": "DEMO",
                    "open_xauusd_positions": 0,
                    "pending_xauusd_orders": 0,
                },
                "operator_token": {"stale": False},
            },
        })
        # Seed autonomous entry decision so v2.8.3.2 normalized verdict = PASS
        _write_json(AUDIT_DEMO_DIR / "autonomous_entry_decision.json", {
            "final_decision": "ALPHA_REGIME_ENTRY_PASS", "alpha_pass": True,
            "risk_gate_pass": True, "broker_gate_pass": True,
            "prop_funded_gate_pass": True, "geometry_gate_pass": True,
        })
        _write_json(AUDIT_DEMO_DIR / "end_to_end_entry_gate_audit.json", {
            "verdict": "ENTRY_GATE_FULL_PASS", "blockers": [],
        })
        _write_json(AUDIT_DEMO_DIR / "autonomous_demo_readiness_audit.json", {
            "verdict": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_allowed": True, "blockers": [],
        })
        import scripts.operator.run_managed_demo_micro_trade as m
        args = MagicMock()
        args.direction = "BUY"
        args.entry_price = 2000.0
        args.sl = 0
        args.tp = 0
        args.prop_funded_profile = "prop_funded_safe"
        args.account_profile = ""
        args.use_adaptive_trailing = True
        args.use_dynamic_tp_extension = True
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.initial_tp_r = 3.0
        args.tp_extension_trigger_r = 2.0
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 1.5
        args.tp_extension_cooldown_seconds = 60
        args.min_profit_lock_after_tp_extension_r = 1.5
        args.max_profit_giveback_r_trend = 0.5
        args.max_profit_giveback_r_range = 0.3
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.risk_mode = "conservative"
        args.broker_profile = "metaquotes_demo"

        result = m.run_build_request(args.direction, args.entry_price, args.sl, args.tp, args)
        # Final activation fields must be present
        assert "latest_final_demo_activation_verdict" in result
        assert "final_demo_activation_pass" in result
        assert "final_demo_activation_allowed" in result
        assert "metaquotes_demo_verified" in result
        assert "open_positions_count" in result
        assert "pending_orders_count" in result
        assert "stale_token_detected" in result
        # Values must match seeded data
        assert result["latest_final_demo_activation_verdict"] == "FINAL_DEMO_ACTIVATION_READY_SUPERVISED"
        assert result["final_demo_activation_allowed"] is True
        assert result["metaquotes_demo_verified"] is True

    def test_18_build_request_remains_read_only(self):
        """Test 18: Build-request remains read-only (no token, no order_send, no modify)."""
        _seed_all_passing()
        _write_json(FA_PATH, {
            "verdict": "FINAL_DEMO_ACTIVATION_READY_SUPERVISED",
            "final_demo_activation_allowed": True,
            "findings": {
                "mt5_environment": {
                    "account_server": "MetaQuotes-Demo", "account_type": "DEMO",
                    "open_xauusd_positions": 0, "pending_xauusd_orders": 0,
                },
                "operator_token": {"stale": False},
            },
        })
        _write_json(AUDIT_DEMO_DIR / "autonomous_entry_decision.json", {
            "final_decision": "ALPHA_REGIME_ENTRY_PASS", "alpha_pass": True,
            "risk_gate_pass": True, "broker_gate_pass": True,
            "prop_funded_gate_pass": True, "geometry_gate_pass": True,
        })
        _write_json(AUDIT_DEMO_DIR / "end_to_end_entry_gate_audit.json", {
            "verdict": "ENTRY_GATE_FULL_PASS", "blockers": [],
        })
        _write_json(AUDIT_DEMO_DIR / "autonomous_demo_readiness_audit.json", {
            "verdict": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_allowed": True, "blockers": [],
        })
        import scripts.operator.run_managed_demo_micro_trade as m
        args = MagicMock()
        args.direction = "BUY"
        args.entry_price = 2000.0
        args.sl = 0
        args.tp = 0
        args.prop_funded_profile = "prop_funded_safe"
        args.account_profile = ""
        args.use_adaptive_trailing = True
        args.use_dynamic_tp_extension = True
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.initial_tp_r = 3.0
        args.tp_extension_trigger_r = 2.0
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 1.5
        args.tp_extension_cooldown_seconds = 60
        args.min_profit_lock_after_tp_extension_r = 1.5
        args.max_profit_giveback_r_trend = 0.5
        args.max_profit_giveback_r_range = 0.3
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.risk_mode = "conservative"
        args.broker_profile = "metaquotes_demo"

        result = m.run_build_request(args.direction, args.entry_price, args.sl, args.tp, args)
        m.apply_build_request_verdict_sync(result)
        # Safety invariants preserved
        assert result.get("execution_now_allowed", True) is False
        assert result.get("execution_blocker", "") == "OPERATOR_ARM_TOKEN_REQUIRED"
        # Build-request never creates token
        assert not TOKEN_PATH.exists() or json.loads(TOKEN_PATH.read_text()).get("created_at", "") == ""


# ============================================================
# Tests 19-20: Runbook + FundedNext blocking
# ============================================================

class TestRunbookAndFundedNext:
    """Tests 19-20: Runbook contains exact commands, FundedNext remains blocked."""

    def test_19_runbook_contains_exact_operator_commands(self):
        """Test 19: Runbook must contain exact Windows commands for Steps 1-5."""
        assert RUNBOOK_PATH.exists(), f"Runbook not found: {RUNBOOK_PATH}"
        content = RUNBOOK_PATH.read_text(encoding="utf-8")
        # Step 1 commands
        assert "git pull origin main" in content
        assert "myenv\\Scripts\\activate" in content
        assert "git status" in content
        # Step 2 audit commands
        assert "python scripts/audit/model_artifact_health_audit.py" in content
        assert "python scripts/audit/feature_parity_audit.py" in content
        assert "python scripts/audit/runtime_safety_gate_audit.py" in content
        assert "python scripts/audit/prop_challenge_growth_profile_audit.py" in content
        assert "python scripts/audit/final_demo_activation_readiness_audit.py" in content
        assert "python scripts/audit/production_closure_readiness_audit.py" in content
        # Step 3 build-request
        assert "python scripts/operator/run_managed_demo_micro_trade.py --build-request" in content
        assert "--prop-funded-profile prop_funded_safe" in content
        assert "--use-adaptive-trailing" in content
        assert "--use-dynamic-tp-extension" in content
        # Step 4 token creation
        assert "python scripts/operator/create_local_operator_execution_token.py" in content
        assert "--symbol XAUUSD" in content
        assert "--lot 0.01" in content
        assert "--broker MetaQuotes-Demo" in content
        assert "--expiry-minutes 10" in content
        # Step 5 execute-and-monitor
        assert "python scripts/operator/run_managed_demo_micro_trade.py --execute-and-monitor" in content
        assert "--i-understand-demo-risk" in content
        assert "--confirm-symbol XAUUSD" in content
        assert "--confirm-lot 0.01" in content
        assert "--confirm-broker MetaQuotes-Demo" in content
        assert "--confirm-one-order-only" in content
        assert "--confirm-not-live" in content
        assert "--confirm-environment-locked" in content
        assert "--confirm-model-parity-pass" in content
        assert "--confirm-local-operator" in content
        assert "--confirm-managed-trailing" in content
        assert "--monitor-duration-minutes 30" in content
        assert "--monitor-interval-seconds 5" in content

    def test_20_fundednext_execution_remains_blocked(self):
        """Test 20: FundedNext execution remains blocked."""
        _seed_all_passing()
        import scripts.audit.final_demo_activation_readiness_audit as m
        # FundedNext-Demo server must block
        with patch.object(m, '_check_mt5_environment',
                          return_value=_mock_mt5_env(server="FundedNext-Demo",
                                                     account_type="DEMO")):
            result = m.run_audit()
        assert result["verdict"] == m.FINAL_DEMO_ACTIVATION_BLOCKED
        assert any("ACCOUNT_SERVER_NOT_METAQUOTES_DEMO" in b for b in result["blockers"])
        # Verify runbook explicitly mentions FundedNext blocking
        runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
        assert "FundedNext" in runbook
        assert "Do NOT run on FundedNext" in runbook or "NO FundedNext execution" in runbook
