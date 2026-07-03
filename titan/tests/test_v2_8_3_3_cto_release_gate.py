"""TITAN XAU AI - Sprint v2.8.3.3 CTO Consolidated Release Gate Tests

Tests the 3 new audit scripts + production closure integration + build-request display.

Test categories (matching sprint spec Part F):
  1-2.  Model health: all required models pass / missing model blocks
  3.    Model load failure blocks
  4.    Feature count mismatch blocks
  5.    Prediction NaN/inf blocks
  6.    Compatibility warning + valid prediction = PASS_WITH_WARNINGS
  7.    Optional/disabled model failure = PASS_WITH_WARNINGS, not BLOCKED
  8.    Silent fallback blocks
  9.    Runtime safety gate blocks forbidden execution paths
  10.   Audit scripts never call mt5.order_send
  11.   Audit scripts never create token
  12.   Audit scripts never modify positions
  13.   Production closure integrates all 3 gates
  14.   Blocked model health creates production closure blocker
  15.   Passing gates keep production closure blockers 0
  16.   Build-request displays model health, feature parity, runtime safety
  17.   Existing v2.8.3.2 build-request PASS sync remains valid
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
    # v2.8.5-C: Add freshness metadata to all seeded audit JSONs
    from datetime import datetime, timezone
    from titan.production.audit_hygiene import get_git_commit
    if "generated_at_utc" not in data and "verdict" in data:
        data["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
        data["git_commit"] = get_git_commit() or "test_commit"
        data["source_mode"] = "production"
        data["audit_name"] = path.stem
        data["environment_mode"] = "test"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


# ============================================================
# PART F Tests 1-8: Model Artifact Health Audit
# ============================================================

class TestModelArtifactHealthAudit:
    """Tests 1-8: Model health audit verdict logic."""

    def setup_method(self):
        self._backups = _backup([MH_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_01_all_active_required_models_pass(self):
        """Test 1: All active required models pass -> MODEL_ARTIFACT_HEALTH_PASS."""
        import scripts.audit.model_artifact_health_audit as m
        result = m.run_audit()
        # Z AI env: xgboost_v1 + meta_label_v2_context both load successfully
        assert result["verdict"] in (
            m.MODEL_ARTIFACT_HEALTH_PASS,
            m.MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS,
        ), f"Expected PASS or PASS_WITH_WARNINGS, got {result['verdict']}"
        assert result["failed_model_count"] == 0
        # Both active_primary models must be in per_model_results
        active_primary = [r for r in result["per_model_results"] if r["role"] in ("alpha_direction_specialist", "meta_label_quality_filter")]
        assert len(active_primary) >= 2  # xgb + meta
        for r in active_primary:
            assert r["health"] in ("PASS", "PASS_WITH_WARNINGS"), \
                f"Active primary {r['name']} should pass, got {r['health']}"

    def test_02_required_active_model_missing_blocks(self):
        """Test 2: Required active model missing -> BLOCKED."""
        import scripts.audit.model_artifact_health_audit as m
        # Mock _discover_active_models to return a missing path
        with patch.object(m, '_discover_active_models') as mock_disc:
            mock_disc.return_value = [{
                "name": "missing_model",
                "path": "/nonexistent/path/to/missing.pkl",
                "role": "alpha_direction_specialist",
                "config_key": "xgb_path",
            }]
            result = m.run_audit()
        assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_BLOCKED
        assert result["failed_model_count"] >= 1
        assert any("REQUIRED_MODEL_FAILED" in b for b in result["blockers"])

    def test_03_required_active_model_load_failure_blocks(self):
        """Test 3: Required active model load failure -> BLOCKED."""
        import scripts.audit.model_artifact_health_audit as m
        # Create a fake model file with garbage content
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as tmpf:
            tmpf.write(b"NOT_A_VALID_PICKLE_FILE")
            tmpf.flush()
            tmp_path = tmpf.name
        try:
            with patch.object(m, '_discover_active_models') as mock_disc:
                mock_disc.return_value = [{
                    "name": "broken_model",
                    "path": tmp_path,
                    "role": "alpha_direction_specialist",
                    "config_key": "xgb_path",
                }]
                result = m.run_audit()
            assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_BLOCKED
            assert result["failed_model_count"] >= 1
        finally:
            os.unlink(tmp_path)

    def test_04_feature_count_mismatch_blocks(self):
        """Test 4: Feature count mismatch (active_primary with wrong n_features_in_) -> BLOCKED."""
        import scripts.audit.model_artifact_health_audit as m
        # Create a model with wrong feature count - use sklearn dummy
        try:
            from sklearn.linear_model import LogisticRegression
            import numpy as np
            # Train with 10 features but expect 55 for "xgboost_v1"
            X = np.random.randn(20, 10)
            y = np.random.randint(0, 2, 20)
            model = LogisticRegression()
            model.fit(X, y)
            with tempfile.NamedTemporaryFile(suffix="_xgboost_v1.pkl", delete=False) as tmpf:
                pickle.dump(model, tmpf)
                tmpf.flush()
                tmp_path = tmpf.name
            try:
                with patch.object(m, '_discover_active_models') as mock_disc, \
                     patch.object(m, '_expected_feature_count', return_value=55):
                    mock_disc.return_value = [{
                        "name": "xgboost_v1",
                        "path": tmp_path,
                        "role": "alpha_direction_specialist",
                        "config_key": "xgb_path",
                    }]
                    result = m.run_audit()
                # Should be BLOCKED due to feature count mismatch (10 != 55)
                assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_BLOCKED
                failed = [r for r in result["per_model_results"] if r["name"] == "xgboost_v1"]
                assert failed, "xgboost_v1 should be in results"
                assert failed[0]["health"] == "BLOCKED"
                assert any("FEATURE_COUNT_MISMATCH" in e for e in failed[0]["schema"].get("errors", []))
            finally:
                os.unlink(tmp_path)
        except ImportError:
            pytest.skip("sklearn not available")

    def test_05_prediction_nan_inf_blocks(self):
        """Test 5: Prediction output NaN/inf -> BLOCKED."""
        import scripts.audit.model_artifact_health_audit as m
        import numpy as np
        # Create a fake model that returns NaN
        class NaNPredictor:
            n_features_in_ = 55
            classes_ = [0, 1]
            def predict(self, X):
                return np.array([float('nan')])
            def predict_proba(self, X):
                return np.array([[float('nan'), float('nan')]])

        with patch.object(m, '_discover_active_models') as mock_disc, \
             patch.object(m, '_capture_load_warnings', return_value=(NaNPredictor(), [], [])), \
             patch.object(m, '_verify_no_silent_fallback') as mock_nsf:
            mock_disc.return_value = [{
                "name": "xgboost_v1",
                "path": str(REPO_ROOT / "titan" / "data" / "models" / "xgboost_v1.pkl"),
                "role": "alpha_direction_specialist",
                "config_key": "xgb_path",
            }]
            mock_nsf.return_value = {"is_real_model": True, "errors": [], "model_class": "xgboost.sklearn.XGBClassifier"}
            result = m.run_audit()
        assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_BLOCKED

    def test_06_compatibility_warning_with_valid_prediction_passes_with_warnings(self):
        """Test 6: Compatibility warning + valid prediction -> PASS_WITH_WARNINGS."""
        import scripts.audit.model_artifact_health_audit as m

        # Mock the load to capture a fake compatibility warning
        class FakeWarning:
            class _W:
                category = type("InconsistentVersionWarning", (), {"__name__": "InconsistentVersionWarning"})
                message = "Trying to unpickle estimator LogisticRegression from version 1.4.0 when using version 1.5.2."
            def __iter__(self):
                return iter([self._W()])

        # Use the real xgboost_v1.pkl but inject a warning
        real_path = str(REPO_ROOT / "titan" / "data" / "models" / "xgboost_v1.pkl")
        # Load it once to get the real model object
        with open(real_path, "rb") as f:
            real_model = pickle.load(f)

        with patch.object(m, '_discover_active_models') as mock_disc, \
             patch.object(m, '_capture_load_warnings') as mock_load:
            mock_disc.return_value = [{
                "name": "xgboost_v1",
                "path": real_path,
                "role": "alpha_direction_specialist",
                "config_key": "xgb_path",
            }]
            mock_load.return_value = (
                real_model,
                [{
                    "category": "InconsistentVersionWarning",
                    "message": "Trying to unpickle estimator from version 1.4.0 when using version 1.5.2.",
                    "severity": "warning",
                    "is_version_warning": True,
                }],
                [],
            )
            result = m.run_audit()
        assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS
        assert result["failed_model_count"] == 0

    def test_07_optional_disabled_model_failure_passes_with_warnings(self):
        """Test 7: Optional/disabled model failure -> PASS_WITH_WARNINGS (not BLOCKED).

        v2.8.3.3.1 reconciliation: optional role (not ensemble_member) is non-required.
        """
        import scripts.audit.model_artifact_health_audit as m
        # Optional (non-required) model fails to load -> not blocking
        with patch.object(m, '_discover_active_models') as mock_disc:
            # Only an optional (non-required) model that fails
            mock_disc.return_value = [{
                "name": "broken_optional",
                "path": "/nonexistent/optional.pkl",
                "role": "optional",  # v2.8.3.3.1: optional is non-required
                "config_key": "",
                "non_blocking_reason": "Optional challenger - non-blocking",
            }]
            result = m.run_audit()
        # Optional model failing -> PASS_WITH_WARNINGS, not BLOCKED
        assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS
        assert result["failed_required_model_count"] == 0  # required count
        assert result["failed_optional_model_count"] >= 1  # optional count
        assert result["v2_8_4_allowed"] is True  # v2.8.4 still allowed

    def test_08_silent_fallback_blocks(self):
        """Test 8: Silent fallback (dummy model class) -> BLOCKED."""
        import scripts.audit.model_artifact_health_audit as m

        # Create a fake model with unexpected class (silent fallback indicator)
        class DummyModel:
            n_features_in_ = 55
            classes_ = [0, 1]
            def predict(self, X):
                import numpy as np
                return np.array([1])
            def predict_proba(self, X):
                import numpy as np
                return np.array([[0.3, 0.7]])

        real_path = str(REPO_ROOT / "titan" / "data" / "models" / "xgboost_v1.pkl")
        with patch.object(m, '_discover_active_models') as mock_disc, \
             patch.object(m, '_capture_load_warnings', return_value=(DummyModel(), [], [])):
            mock_disc.return_value = [{
                "name": "xgboost_v1",
                "path": real_path,
                "role": "alpha_direction_specialist",
                "config_key": "xgb_path",
            }]
            result = m.run_audit()
        # Dummy model class -> BLOCKED (silent fallback)
        assert result["verdict"] == m.MODEL_ARTIFACT_HEALTH_BLOCKED


# ============================================================
# PART F Tests 9-12: Runtime Safety Gate Audit
# ============================================================

class TestRuntimeSafetyGateAudit:
    """Tests 9-12: Runtime safety gate audit."""

    def setup_method(self):
        self._backups = _backup([RS_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_09_runtime_safety_blocks_forbidden_execution_paths(self):
        """Test 9: Runtime safety gate blocks forbidden execution paths."""
        import scripts.audit.runtime_safety_gate_audit as m
        result = m.run_audit()
        # In current repo state, runtime safety should PASS (no forbidden paths)
        # But if we mock that order_send is reachable, it should BLOCK
        assert "verdict" in result
        assert result["verdict"] in (m.RUNTIME_SAFETY_GATE_PASS, m.RUNTIME_SAFETY_GATE_BLOCKED)

        # Now mock _check_order_send_unreachable_from_safe_paths to return unsafe
        with patch.object(m, '_check_order_send_unreachable_from_safe_paths') as mock_check:
            mock_check.return_value = {
                "build_request_safe": False,
                "autonomous_entry_check_safe": True,
                "audit_scripts_safe": True,
                "errors": ["ORDER_SEND_REACHABLE_FROM_run_build_request: fake call"],
                "scanned_scripts": [],
            }
            result = m.run_audit()
        assert result["verdict"] == m.RUNTIME_SAFETY_GATE_BLOCKED
        assert any("ORDER_SEND_REACHABLE_FROM_BUILD_REQUEST" in b for b in result["blockers"])

    def test_10_audit_scripts_never_call_order_send(self):
        """Test 10: Audit scripts never call mt5.order_send (verified by source scan)."""
        import scripts.audit.runtime_safety_gate_audit as m
        result = m.run_audit()
        findings = result.get("findings", {}).get("order_send_unreachable", {})
        # All read-only audit scripts must be safe
        # (raw_mt5_probe.py and demo_micro_full_cycle.py are execution harnesses, excluded)
        assert findings.get("audit_scripts_safe", False), \
            f"Audit scripts must not call order_send. Errors: {findings.get('errors')}"

    def test_11_audit_scripts_never_create_token(self):
        """Test 11: Audit scripts never create operator execution token."""
        import scripts.audit.runtime_safety_gate_audit as m
        result = m.run_audit()
        findings = result.get("findings", {}).get("token_gating", {})
        assert findings.get("token_creation_not_in_audit_scripts", False), \
            f"Audit scripts must not create tokens. Errors: {findings.get('errors')}"

    def test_12_audit_scripts_never_modify_positions(self):
        """Test 12: Audit scripts never modify positions."""
        import scripts.audit.runtime_safety_gate_audit as m
        result = m.run_audit()
        findings = result.get("findings", {}).get("position_modification_unreachable", {})
        assert findings.get("safe", False), \
            f"Audit scripts must not modify positions. Errors: {findings.get('errors')}"


# ============================================================
# PART F Tests 13-15: Production Closure Integration
# ============================================================

class TestProductionClosureIntegration:
    """Tests 13-15: Production closure reads 3 new gates."""

    def setup_method(self):
        self._backups = _backup([MH_PATH, FP_PATH, RS_PATH, AE_PATH, EG_PATH, AR_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_13_production_closure_integrates_all_gates(self):
        """Test 13: Production closure reads all 3 gates and exposes fields."""
        # Seed all 3 gates as passing
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_PASS",
            "active_model_count": 9, "failed_model_count": 0,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})
        # Seed autonomous_demo_readiness as SUPERVISED to enable autonomous_execution_status
        _write_json(AR_PATH, {
            "verdict": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_allowed": True, "blockers": [],
        })
        _write_json(EG_PATH, {"verdict": "ENTRY_GATE_FULL_PASS", "blockers": []})

        import scripts.audit.production_closure_readiness_audit as m
        result = m.run_audit()
        # All 3 gate fields must be present
        assert "latest_model_health_verdict" in result
        assert "latest_feature_parity_verdict" in result
        assert "latest_runtime_safety_verdict" in result
        assert "model_health_pass" in result
        assert "feature_parity_pass" in result
        assert "runtime_safety_pass" in result
        assert "v2_8_4_allowed" in result
        # All should pass
        assert result["model_health_pass"] is True
        assert result["feature_parity_pass"] is True
        assert result["runtime_safety_pass"] is True
        assert result["v2_8_4_allowed"] is True

    def test_14_blocked_model_health_creates_closure_blocker(self):
        """Test 14: Blocked model health creates production closure blocker + downgrades SUPERVISED_READY."""
        # Seed model health as BLOCKED
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_BLOCKED",
            "active_model_count": 9, "failed_model_count": 2,
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
        # Must have MODEL_HEALTH_BLOCKED blocker
        assert any("MODEL_HEALTH_BLOCKED" in b for b in result["blockers"]), \
            f"Expected MODEL_HEALTH_BLOCKED in blockers: {result['blockers']}"
        # v2.8.4 must NOT be allowed
        assert result["v2_8_4_allowed"] is False
        # autonomous_execution_status must be downgraded from SUPERVISED_READY -> BLOCKED
        assert result["autonomous_execution_status"] == "BLOCKED", \
            f"Expected BLOCKED (downgraded), got {result['autonomous_execution_status']}"

    def test_15_passing_gates_keep_closure_blockers_zero(self):
        """Test 15: All 3 gates passing -> no closure blockers from gates."""
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_PASS",
            "active_model_count": 9, "failed_model_count": 0,
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
        # No gate-related blockers
        gate_blockers = [b for b in result["blockers"]
                        if any(prefix in b for prefix in
                               ("MODEL_HEALTH_BLOCKED", "FEATURE_PARITY_BLOCKED",
                                "RUNTIME_SAFETY_BLOCKED", "V2_8_4_RELEASE_GATE_BLOCKED",
                                "AUTONOMOUS_STATUS_DOWNGRADED"))]
        assert gate_blockers == [], f"Expected no gate blockers, got: {gate_blockers}"
        assert result["v2_8_4_allowed"] is True
        # autonomous_execution_status remains SUPERVISED_READY (not downgraded)
        assert result["autonomous_execution_status"] == "SUPERVISED_READY"


# ============================================================
# PART F Tests 16-17: Build-Request Display
# ============================================================

class TestBuildRequestDisplay:
    """Tests 16-17: Build-request displays new gates + v2.8.3.2 sync still works."""

    def setup_method(self):
        self._backups = _backup([MH_PATH, FP_PATH, RS_PATH, AE_PATH, EG_PATH, AR_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_16_build_request_displays_all_three_gates(self):
        """Test 16: Build-request displays model health, feature parity, runtime safety."""
        # Seed all 3 gates
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS",
            "active_model_count": 9, "failed_model_count": 0,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS_WITH_WARNINGS"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})
        # Seed autonomous entry decision so v2.8.3.2 normalized verdict = PASS
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
        # Apply v2.8.3.2 verdict sync
        m.apply_build_request_verdict_sync(result)

        # Build-request must display all 3 gate fields
        assert "latest_model_health_verdict" in result
        assert "latest_feature_parity_verdict" in result
        assert "latest_runtime_safety_verdict" in result
        assert "active_model_count" in result
        assert "failed_model_count" in result
        assert "v2_8_4_allowed" in result
        # Values must match seeded audit data
        assert result["latest_model_health_verdict"] == "MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS"
        assert result["latest_feature_parity_verdict"] == "FEATURE_PARITY_PASS_WITH_WARNINGS"
        assert result["latest_runtime_safety_verdict"] == "RUNTIME_SAFETY_GATE_PASS"
        assert result["active_model_count"] == 9
        assert result["failed_model_count"] == 0
        assert result["v2_8_4_allowed"] is True

    def test_17_v2832_build_request_pass_sync_remains_valid(self):
        """Test 17: Existing v2.8.3.2 build-request PASS sync still works (regression)."""
        # Seed passing audit files
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
        # Use a minimal result dict like v2.8.3.2 tests
        result = {
            "mode": "build_request", "verdict": "BLOCKED",
            "blockers": ["BROKER_BLOCKED: score=0 < 70"],
            "end_to_end_entry_gate_status": "ENTRY_GATE_FULL_PASS",
            "end_to_end_entry_gate_blockers": [],
            "autonomous_demo_readiness_status": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_demo_blockers": [],
        }
        m.apply_build_request_verdict_sync(result)
        # v2.8.3.2 contract: top-level must be PASS, blockers=0
        assert result["verdict"] == "PASS"
        assert result["blockers"] == []
        assert result["blocker_count"] == 0
        assert result["normalized_verdict"] == "PASS"
        assert result["request_status"] == "READY_FOR_SUPERVISED_OPERATOR_ARM"
        assert result["execution_now_allowed"] is False
        assert result["execution_blocker"] == "OPERATOR_ARM_TOKEN_REQUIRED"


# ============================================================
# PART F Test: Feature Parity Audit (additional)
# ============================================================

class TestFeatureParityAudit:
    """Additional tests for feature parity audit."""

    def setup_method(self):
        self._backups = _backup([FP_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_feature_parity_passes_in_current_repo(self):
        """Feature parity audit must PASS or PASS_WITH_WARNINGS in current repo state."""
        import scripts.audit.feature_parity_audit as m
        result = m.run_audit()
        assert result["verdict"] in (
            m.FEATURE_PARITY_PASS,
            m.FEATURE_PARITY_PASS_WITH_WARNINGS,
        ), f"Expected PASS, got {result['verdict']}: {result.get('blockers')}"
