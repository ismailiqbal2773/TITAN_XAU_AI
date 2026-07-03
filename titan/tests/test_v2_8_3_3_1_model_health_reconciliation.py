"""TITAN XAU AI - Sprint v2.8.3.3.1 Model Health Classification Reconciliation Tests

Verifies the fix for the mismatch where lightgbm_v1 (previously misclassified as
ensemble_member) showed BLOCKED per-model but overall verdict was PASS_WITH_WARNINGS.

CTO rule: required_for_runtime = role in (active_primary, ensemble_member).
If a required model fails, overall MUST be BLOCKED and v2.8.4 MUST be blocked.
If an optional/backup/disabled/deprecated model fails, overall may stay
PASS_WITH_WARNINGS and v2.8.4 may stay allowed.

Required tests:
  - active_primary blocked causes overall BLOCKED
  - ensemble_member blocked causes overall BLOCKED
  - backup blocked gives PASS_WITH_WARNINGS
  - optional/disabled/deprecated blocked gives PASS_WITH_WARNINGS
  - failed_required_model_count matches per-model required failures
  - v2.8.4 allowed False if required model blocked
  - production closure blocks when model health blocked
  - build-request displays failed required model list
  - no mt5.order_send
  - no token creation
  - no position modification
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
import pickle
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

AUDIT_DEMO_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"
MODEL_HEALTH_DIR = REPO_ROOT / "data" / "audit" / "model_health"
MH_PATH = MODEL_HEALTH_DIR / "model_artifact_health_audit.json"
FP_PATH = MODEL_HEALTH_DIR / "feature_parity_audit.json"
RS_PATH = AUDIT_DEMO_DIR / "runtime_safety_gate_audit.json"
AE_PATH = AUDIT_DEMO_DIR / "autonomous_entry_decision.json"
EG_PATH = AUDIT_DEMO_DIR / "end_to_end_entry_gate_audit.json"
AR_PATH = AUDIT_DEMO_DIR / "autonomous_demo_readiness_audit.json"


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


class TestModelHealthClassificationReconciliation:
    """Phase 1 tests: Verify model classification reconciliation."""

    def setup_method(self):
        self._backups = _backup([MH_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_01_active_primary_blocked_causes_overall_blocked(self):
        """If an active_primary model fails -> overall verdict MUST be BLOCKED."""
        import scripts.audit.model_artifact_health_audit as m
        with patch.object(m, '_discover_active_models') as mock_disc:
            mock_disc.return_value = [{
                "name": "broken_xgb",
                "path": "/nonexistent/xgb.pkl",
                "role": "active_primary",
                "config_key": "xgb_path",
                "non_blocking_reason": "",
            }]
            result = m.run_audit()
        assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_BLOCKED
        assert result["failed_required_model_count"] == 1
        assert result["v2_8_4_allowed"] is False
        assert len(result["blocked_required_models"]) == 1
        assert result["blocked_required_models"][0]["name"] == "broken_xgb"

    def test_02_ensemble_member_blocked_causes_overall_blocked(self):
        """If an ensemble_member model fails -> overall verdict MUST be BLOCKED.

        v2.8.3.3.1: ensemble_member is REQUIRED for runtime.
        """
        import scripts.audit.model_artifact_health_audit as m
        with patch.object(m, '_discover_active_models') as mock_disc:
            mock_disc.return_value = [{
                "name": "broken_ensemble",
                "path": "/nonexistent/ensemble.pkl",
                "role": "ensemble_member",  # required!
                "config_key": "",
                "non_blocking_reason": "",
            }]
            result = m.run_audit()
        assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_BLOCKED
        assert result["failed_required_model_count"] == 1
        assert result["v2_8_4_allowed"] is False

    def test_03_backup_blocked_gives_pass_with_warnings(self):
        """If a backup model fails -> PASS_WITH_WARNINGS (not BLOCKED)."""
        import scripts.audit.model_artifact_health_audit as m
        with patch.object(m, '_discover_active_models') as mock_disc:
            mock_disc.return_value = [{
                "name": "broken_backup",
                "path": "/nonexistent/backup.pt",
                "role": "backup",  # not required
                "config_key": "",
                "non_blocking_reason": "Backup model - non-blocking",
            }]
            result = m.run_audit()
        assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS
        assert result["failed_required_model_count"] == 0
        assert result["failed_optional_model_count"] >= 1
        assert result["v2_8_4_allowed"] is True

    def test_04_optional_disabled_deprecated_blocked_gives_pass_with_warnings(self):
        """If an optional/disabled/deprecated model fails -> PASS_WITH_WARNINGS."""
        import scripts.audit.model_artifact_health_audit as m
        for role in ("optional", "disabled", "deprecated"):
            with patch.object(m, '_discover_active_models') as mock_disc:
                mock_disc.return_value = [{
                    "name": f"broken_{role}",
                    "path": f"/nonexistent/{role}.pkl",
                    "role": role,
                    "config_key": "",
                    "non_blocking_reason": f"{role} model - non-blocking",
                }]
                result = m.run_audit()
            assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS, \
                f"role={role} should give PASS_WITH_WARNINGS, got {result['verdict']}"
            assert result["failed_required_model_count"] == 0
            assert result["v2_8_4_allowed"] is True

    def test_05_failed_required_count_matches_per_model_required_failures(self):
        """failed_required_model_count must match the count of per-model required_failure=True."""
        import scripts.audit.model_artifact_health_audit as m
        # 2 active_primary models, 1 fails
        with patch.object(m, '_discover_active_models') as mock_disc:
            mock_disc.return_value = [
                {"name": "ok_xgb", "path": str(REPO_ROOT / "titan" / "data" / "models" / "xgboost_v1.pkl"),
                 "role": "active_primary", "config_key": "xgb_path", "non_blocking_reason": ""},
                {"name": "broken_meta", "path": "/nonexistent/meta.pkl",
                 "role": "active_primary", "config_key": "meta_path", "non_blocking_reason": ""},
            ]
            result = m.run_audit()
        per_model_required_failures = sum(
            1 for r in result["per_model_results"]
            if r.get("required_failure", False)
        )
        assert result["failed_required_model_count"] == per_model_required_failures
        assert per_model_required_failures == 1
        assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_BLOCKED

    def test_06_v2_8_4_allowed_false_if_required_model_blocked(self):
        """v2_8_4_allowed MUST be False if any required model is blocked."""
        import scripts.audit.model_artifact_health_audit as m
        with patch.object(m, '_discover_active_models') as mock_disc:
            mock_disc.return_value = [
                {"name": "broken_xgb", "path": "/nonexistent/xgb.pkl",
                 "role": "active_primary", "config_key": "xgb_path", "non_blocking_reason": ""},
                {"name": "optional_challenger", "path": "/nonexistent/optional.pkl",
                 "role": "optional", "config_key": "", "non_blocking_reason": "non-blocking"},
            ]
            result = m.run_audit()
        assert result["v2_8_4_allowed"] is False
        assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_BLOCKED

    def test_07_per_model_includes_reconciliation_fields(self):
        """Each per-model result must include model_name, model_role,
        required_for_runtime, final_status, required_failure,
        blocking_reason, non_blocking_reason."""
        import scripts.audit.model_artifact_health_audit as m
        result = m.run_audit()
        for r in result["per_model_results"]:
            assert "model_name" in r
            assert "model_role" in r
            assert "required_for_runtime" in r
            assert "final_status" in r
            assert "required_failure" in r
            assert "blocking_reason" in r
            assert "non_blocking_reason" in r

    def test_08_lightgbm_v1_classified_as_optional_not_ensemble_member(self):
        """lightgbm_v1 MUST be classified as 'optional' (challenger), not 'ensemble_member'.

        This is the root cause fix for the v2.8.3.3.1 reconciliation.
        Per scripts/titan_audit_report.py: 'Not in F8 inference chain'.
        """
        import scripts.audit.model_artifact_health_audit as m
        result = m.run_audit()
        lgbm = [r for r in result["per_model_results"] if r["name"] == "lightgbm_v1"]
        assert lgbm, "lightgbm_v1 must be discovered"
        assert lgbm[0]["model_role"] == "optional", \
            f"lightgbm_v1 must be 'optional', got '{lgbm[0]['model_role']}'"
        assert lgbm[0]["required_for_runtime"] is False
        assert lgbm[0]["non_blocking_reason"], \
            "lightgbm_v1 must have non_blocking_reason explaining why it's optional"

    def test_09_no_mismatch_between_per_model_and_overall(self):
        """Per-model required failures must match overall failed_required_model_count."""
        import scripts.audit.model_artifact_health_audit as m
        result = m.run_audit()
        per_model_req_failures = sum(
            1 for r in result["per_model_results"] if r.get("required_failure", False)
        )
        assert per_model_req_failures == result["failed_required_model_count"], \
            f"Mismatch: per_model={per_model_req_failures} != overall={result['failed_required_model_count']}"

        # If failed_required == 0, verdict must NOT be BLOCKED
        if result["failed_required_model_count"] == 0:
            assert result["verdict"] != m.MODEL_ARTIFACT_HEALTH_BLOCKED, \
                "verdict=BLOCKED but failed_required_model_count=0 - inconsistency"
        # If failed_required > 0, verdict MUST be BLOCKED
        if result["failed_required_model_count"] > 0:
            assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_BLOCKED, \
                "failed_required_model_count>0 but verdict!=BLOCKED - inconsistency"
            assert result["v2_8_4_allowed"] is False


class TestProductionClosureReconciliation:
    """Phase 1: Production closure must agree with model health."""

    def setup_method(self):
        self._backups = _backup([MH_PATH, FP_PATH, RS_PATH, AE_PATH, EG_PATH, AR_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_10_production_closure_blocks_when_model_health_blocked(self):
        """Production closure must add blocker when model health is BLOCKED."""
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_BLOCKED",
            "active_model_count": 2, "failed_required_model_count": 1,
            "failed_optional_model_count": 0,
            "blocked_required_models": [{"name": "broken", "role": "active_primary"}],
            "warned_optional_models": [], "v2_8_4_allowed": False,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})
        _write_json(AR_PATH, {
            "verdict": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_allowed": True, "blockers": [],
        })
        _write_json(EG_PATH, {"verdict": "ENTRY_GATE_FULL_PASS", "blockers": []})

        import scripts.audit.production_closure_readiness_audit as m
        result = m.run_audit()
        assert any("MODEL_HEALTH_BLOCKED" in b for b in result["blockers"])
        assert result["v2_8_4_allowed"] is False
        assert result["autonomous_execution_status"] == "BLOCKED"  # downgraded

    def test_11_production_closure_passes_when_only_optional_fails(self):
        """Production closure must NOT block when only optional models fail."""
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS",
            "active_model_count": 9, "failed_required_model_count": 0,
            "failed_optional_model_count": 1,
            "blocked_required_models": [],
            "warned_optional_models": [{"name": "lightgbm_v1", "role": "optional"}],
            "v2_8_4_allowed": True,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})
        _write_json(AR_PATH, {
            "verdict": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_allowed": True, "blockers": [],
        })
        _write_json(EG_PATH, {"verdict": "ENTRY_GATE_FULL_PASS", "blockers": []})

        import scripts.audit.production_closure_readiness_audit as m
        result = m.run_audit()
        # No MODEL_HEALTH_BLOCKED blocker
        assert not any("MODEL_HEALTH_BLOCKED" in b for b in result["blockers"])
        assert result["v2_8_4_allowed"] is True
        # SUPERVISED_READY preserved (no downgrade)
        assert result["autonomous_execution_status"] == "SUPERVISED_READY"


class TestBuildRequestReconciliation:
    """Phase 1: Build-request must display failed required/optional model counts."""

    def setup_method(self):
        self._backups = _backup([MH_PATH, FP_PATH, RS_PATH, AE_PATH, EG_PATH, AR_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_12_build_request_displays_failed_required_model_list(self):
        """Build-request must display failed_required_model_count and blocked_required_models."""
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_BLOCKED",
            "active_model_count": 2, "failed_required_model_count": 1,
            "failed_optional_model_count": 0,
            "blocked_required_models": [{"name": "broken_xgb", "role": "active_primary"}],
            "warned_optional_models": [], "v2_8_4_allowed": False,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})
        _write_json(AE_PATH, {
            "final_decision": "ALPHA_REGIME_ENTRY_PASS", "alpha_pass": True,
            "risk_gate_pass": True, "broker_gate_pass": True,
            "prop_funded_gate_pass": True, "geometry_gate_pass": True,
        })
        _write_json(EG_PATH, {"verdict": "ENTRY_GATE_FULL_PASS", "blockers": []})
        _write_json(AR_PATH, {
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
        # Must include new reconciliation fields
        assert "failed_required_model_count" in result
        assert "failed_optional_model_count" in result
        assert "blocked_required_models" in result
        assert "warned_optional_models" in result
        assert result["failed_required_model_count"] == 1
        assert result["failed_optional_model_count"] == 0
        assert len(result["blocked_required_models"]) == 1
        assert result["blocked_required_models"][0]["name"] == "broken_xgb"
        # model_health_pass must be False (1 required failed)
        assert result["model_health_pass"] is False


class TestSafetyInvariantsReconciliation:
    """Phase 1: Safety invariants preserved during reconciliation."""

    def test_13_no_order_send_in_model_health_audit(self):
        """Model health audit must never call mt5.order_send."""
        import scripts.audit.model_artifact_health_audit as m
        result = m.run_audit()
        assert result["safety"]["order_send_called"] is False
        assert result["safety"]["token_created"] is False
        assert result["safety"]["position_modified"] is False

    def test_14_no_token_creation_in_model_health_audit(self):
        """Model health audit must never create operator execution token."""
        import scripts.audit.model_artifact_health_audit as m
        result = m.run_audit()
        assert result["safety"]["token_created"] is False
