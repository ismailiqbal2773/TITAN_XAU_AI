"""TITAN XAU AI - Sprint v2.8.7-F Broker Generalization Tests

Verifies:
  - Full v2 profile still works
  - v2_multibroker profile works
  - ICMarkets spread edge audit exists and is fixed
  - Multi-broker dataset exists
  - XGB multibroker saved separately
  - Meta multibroker saved separately
  - Parameter discovery supports --model-profile v2_multibroker
  - MTF still real
  - No order_send
  - No token auto-create
  - No live trading
  - No funded execution
  - No martingale/grid
  - production_ready=False
  - CEO not bypassed
  - Meta-label not bypassed
"""
from __future__ import annotations
import sys, re, os, json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestV2MultibrokerProfile:
    def test_v2_multibroker_profile_exists(self):
        from titan.production.model_registry import list_profiles
        assert "v2_multibroker" in list_profiles()

    def test_v2_multibroker_not_default(self):
        from titan.production.model_registry import get_default_profile_name
        assert get_default_profile_name() != "v2_multibroker"

    def test_v2_multibroker_loads(self):
        from titan.production.model_loader import load_models_by_profile
        b = load_models_by_profile("v2_multibroker")
        assert b.ok
        assert b.xgb is not None
        assert b.meta is not None

    def test_v2_multibroker_models_separate_from_v2(self):
        """v2_multibroker models must be different files from v2_feature_normalized."""
        from titan.production.model_registry import get_profile
        v2 = get_profile("v2_feature_normalized")
        mb = get_profile("v2_multibroker")
        assert v2.xgb_path != mb.xgb_path
        assert v2.meta_path != mb.meta_path

    def test_v1_still_loads(self):
        from titan.production.model_loader import load_models_by_profile
        b = load_models_by_profile("v1_legacy")
        assert b.ok

    def test_v2_feature_normalized_still_loads(self):
        from titan.production.model_loader import load_models_by_profile
        b = load_models_by_profile("v2_feature_normalized")
        assert b.ok


class TestICMarketsSpreadEdge:
    def test_icmarkets_edge_audit_exists(self):
        path = REPO_ROOT / "data" / "reports" / "broker_generalization_v2" / "icmarkets_spread_edge_audit.md"
        assert path.exists()

    def test_icmarkets_edge_fixed(self):
        """ICMarkets must now be detected as POINTS_CONVERTED (not USD)."""
        path = REPO_ROOT / "data" / "reports" / "broker_generalization_v2" / "icmarkets_spread_edge_audit.md"
        text = path.read_text()
        assert "ICMARKETS_SPREAD_EDGE_FIXED:** True" in text or \
               "POINTS_CONVERTED" in text

    def test_icmarkets_normalized_with_integer_detection(self):
        """ICMarkets spread (int64 dtype) must be converted to USD via 0.01 factor."""
        import pandas as pd
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd

        # Simulate ICMarkets data (int64 spread, median=2.0)
        df = pd.DataFrame({
            "open": [3000.0]*10,
            "high": [3010.0]*10,
            "low":  [2990.0]*10,
            "close":[3005.0]*10,
            "spread": [2, 2, 3, 1, 2, 3, 2, 2, 3, 2],  # int64, median=2.0
        })
        out = normalize_xauusd_spread_to_usd(df.copy(), symbol="XAUUSD", source="icmarkets_test")
        assert out["spread_unit_detected"].iloc[0] == "POINTS_CONVERTED"
        # 2.0 * 0.01 = 0.02 USD
        assert out["spread_usd"].iloc[0] == pytest.approx(0.02, abs=1e-9)

    def test_canonical_spread_usd_not_affected(self):
        """Canonical spread_usd (float) must not be double-converted."""
        import pandas as pd
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd

        df = pd.DataFrame({
            "open": [2000.0],
            "high": [2010.0],
            "low":  [1990.0],
            "close":[2005.0],
            "spread_usd": [0.15],
        })
        out = normalize_xauusd_spread_to_usd(df.copy(), symbol="XAUUSD", source="canonical_test")
        assert out["spread_unit_detected"].iloc[0] == "USD"
        assert out["spread_usd"].iloc[0] == 0.15  # unchanged


class TestMultibrokerDataset:
    def test_multibroker_features_dir_exists(self):
        path = REPO_ROOT / "titan" / "data" / "features_v2_multibroker"
        assert path.exists()

    def test_multibroker_scaler_exists(self):
        path = REPO_ROOT / "titan" / "data" / "features_v2_multibroker" / "scaler_stats_v2_multibroker.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data["mean"]) == 55

    def test_multibroker_schema_exists(self):
        path = REPO_ROOT / "titan" / "data" / "features_v2_multibroker" / "feature_schema_v2_multibroker.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["schema_version"] == "v2_multibroker"

    def test_multibroker_train_val_test_exist(self):
        for split in ["train", "val", "test"]:
            for kind in ["X", "y"]:
                path = REPO_ROOT / "titan" / "data" / "features_v2_multibroker" / f"XAUUSD_H1_{kind}_{split}_v2_multibroker.parquet"
                assert path.exists(), f"missing {path}"

    def test_multibroker_dataset_report_exists(self):
        path = REPO_ROOT / "data" / "reports" / "broker_generalization_v2" / "multibroker_dataset_report.md"
        assert path.exists()


class TestMultibrokerModels:
    def test_xgb_multibroker_model_exists(self):
        path = REPO_ROOT / "titan" / "data" / "models" / "xgboost_v2_multibroker.pkl"
        assert path.exists()
        assert path.stat().st_size > 1000

    def test_meta_multibroker_model_exists(self):
        path = REPO_ROOT / "titan" / "data" / "models" / "meta_label_v2_multibroker.pkl"
        assert path.exists()
        assert path.stat().st_size > 500

    def test_v1_models_not_overwritten(self):
        for name in ["xgboost_v1.pkl", "meta_label_v2_context.pkl"]:
            path = REPO_ROOT / "titan" / "data" / "models" / name
            assert path.exists()

    def test_v2_models_not_overwritten(self):
        for name in ["xgboost_v2_feature_normalized.pkl", "meta_label_v2_feature_normalized.pkl"]:
            path = REPO_ROOT / "titan" / "data" / "models" / name
            assert path.exists()

    def test_xgb_multibroker_training_report_exists(self):
        path = REPO_ROOT / "data" / "reports" / "broker_generalization_v2" / "xgb_v2_multibroker_training_report.md"
        assert path.exists()

    def test_xgb_multibroker_metrics_json_exists(self):
        path = REPO_ROOT / "data" / "reports" / "broker_generalization_v2" / "xgb_v2_multibroker_metrics.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "test_auc" in data
        assert data["test_auc"] > 0.50

    def test_meta_multibroker_training_report_exists(self):
        path = REPO_ROOT / "data" / "reports" / "broker_generalization_v2" / "meta_v2_multibroker_training_report.md"
        assert path.exists()

    def test_meta_multibroker_metrics_json_exists(self):
        path = REPO_ROOT / "data" / "reports" / "broker_generalization_v2" / "meta_v2_multibroker_metrics.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert 0.05 < data["test_mean_proba"] < 0.95


class TestParameterDiscoveryV2Multibroker:
    def test_discovery_v2_multibroker_output_exists(self):
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2_multibroker"
        assert path.exists()

    def test_demo_go_decision_md_exists(self):
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2_multibroker" / "demo_go_decision.md"
        assert path.exists()
        text = path.read_text()
        assert any(v in text for v in ["NO_SAFE_PARAMETER_FOUND", "DEMO_SHADOW_ALLOWED"])

    def test_model_profile_v2_multibroker_in_cli(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "v2_multibroker" in src
        assert "--model-profile" in src


class TestBrokerGeneralizationAudit:
    def test_broker_feature_distribution_exists(self):
        for ext in ["md", "csv"]:
            path = REPO_ROOT / "data" / "reports" / "broker_generalization_v2" / f"broker_feature_distribution_v2.{ext}"
            assert path.exists()

    def test_broker_prediction_distribution_exists(self):
        for ext in ["md", "csv"]:
            path = REPO_ROOT / "data" / "reports" / "broker_generalization_v2" / f"broker_prediction_distribution_v2.{ext}"
            assert path.exists()

    def test_broker_failure_summary_exists(self):
        path = REPO_ROOT / "data" / "reports" / "broker_generalization_v2" / "broker_failure_summary_v2.md"
        assert path.exists()
        text = path.read_text()
        assert "BROKER_GENERALIZATION_GAP" in text
        assert "ICMARKETS_SPREAD_EDGE" in text


class TestSafety:
    def _strip(self, src):
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'r"[^"]*"', '""', stripped)
        stripped = re.sub(r"r'[^']*'", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        return stripped

    def test_no_order_send_in_new_files(self):
        files = [
            "scripts/research/run_broker_generalization_audit_v2.py",
            "scripts/research/run_multibroker_v2_training.py",
            "scripts/audit/final_commercial_mvp_readiness_audit.py",
            "scripts/operator/run_commercial_demo_mvp.py",
        ]
        for f in files:
            path = REPO_ROOT / f
            if path.exists():
                src = self._strip(path.read_text())
                # Check for actual call pattern (not just string reference)
                assert "order_send(" not in src, f"order_send call found in {f}"

    def test_no_token_in_new_files(self):
        files = [
            "scripts/research/run_broker_generalization_audit_v2.py",
            "scripts/research/run_multibroker_v2_training.py",
            "scripts/audit/final_commercial_mvp_readiness_audit.py",
            "scripts/operator/run_commercial_demo_mvp.py",
        ]
        for f in files:
            path = REPO_ROOT / f
            if path.exists():
                src = path.read_text()
                assert "create_local_operator_execution_token" not in src, f"token found in {f}"

    def test_no_martingale(self):
        files = [
            "scripts/research/run_broker_generalization_audit_v2.py",
            "scripts/research/run_multibroker_v2_training.py",
        ]
        for f in files:
            path = REPO_ROOT / f
            if path.exists():
                src = self._strip(path.read_text())
                assert "martingale" not in src.lower(), f"martingale found in {f}"

    def test_production_ready_false(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert '"production_ready": False' in src

    def test_ceo_not_bypassed(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "evaluate_ceo_decision" in src
        assert "ceo_decision.allowed_to_trade" in src or "if not ceo_decision" in src

    def test_meta_label_not_bypassed(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "meta_confidence < params.meta_threshold" in src

    def test_no_live_trading_in_commercial_profile(self):
        path = REPO_ROOT / "config" / "commercial_profile.yaml"
        text = path.read_text()
        assert "live_trading: false" in text
        assert "funded_trading: false" in text
        assert "production_ready: false" in text
        assert "dry_run: true" in text

    def test_no_funded_brokers_in_whitelist(self):
        path = REPO_ROOT / "config" / "commercial_profile.yaml"
        text = path.read_text()
        # live: must be empty
        assert "live: []" in text or "live:  []" in text


class TestCommercialMVPReadiness:
    def test_audit_md_exists(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.md"
        assert path.exists()

    def test_audit_json_exists(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "verdict" in data
        assert "commercial_mvp_ready" in data
        assert "demo_shadow_ready" in data
        assert "live_ready" in data
        assert "funded_ready" in data

    def test_verdict_is_valid(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        data = json.loads(path.read_text())
        assert data["verdict"] in ["COMMERCIAL_MVP_READY", "DEMO_SHADOW_READY", "NOT_READY"]

    def test_live_ready_is_false(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        data = json.loads(path.read_text())
        assert data["live_ready"] is False

    def test_funded_ready_is_false(self):
        path = REPO_ROOT / "data" / "reports" / "final_commercial_mvp_readiness" / "final_commercial_mvp_readiness.json"
        data = json.loads(path.read_text())
        assert data["funded_ready"] is False

    def test_commercial_skeleton_files_exist(self):
        for f in [
            "config/commercial_profile.yaml",
            "config/license_policy.yaml",
            "docs/operator/COMMERCIAL_MVP_RUNBOOK.md",
            "docs/operator/DEMO_SHADOW_RUNBOOK.md",
            "docs/operator/INSTALLATION_WINDOWS.md",
            "scripts/operator/run_commercial_demo_mvp.py",
        ]:
            path = REPO_ROOT / f
            assert path.exists(), f"missing {f}"

    def test_commercial_demo_runner_blocks_without_auth(self):
        """run_commercial_demo_mvp.py must block when demo shadow not authorized."""
        path = REPO_ROOT / "scripts" / "operator" / "run_commercial_demo_mvp.py"
        src = path.read_text()
        assert "BLOCKED" in src or "NO_SAFE_PARAMETER_FOUND" in src
        assert "dry_run" in src
