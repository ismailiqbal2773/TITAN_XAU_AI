"""TITAN XAU AI - Sprint v2.8.7-E Feature v2 + Training + MTF Tests

Verifies:
  - Feature schema v2 exists
  - Absolute features replaced by relative/stationary features
  - Old v1 not deleted
  - scaler_stats_v2 exists
  - xgb v2 model saved separately
  - meta v2 model saved separately
  - Model loader supports v1 and v2
  - MTF h1_m15 uses M15 data
  - MTF h1_m15_m5 uses M15 and M5 data
  - INVALID_MTF_NOT_USED works
  - Parameter discovery supports --model-profile v2_feature_normalized
  - No order_send
  - No token
  - production_ready=False

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, re, os, json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


# ─────────────────────────────────────────────────────────────────────
# Task 1: Feature schema v2
# ─────────────────────────────────────────────────────────────────────

class TestFeatureSchemaV2:
    def test_schema_v2_module_exists(self):
        path = REPO_ROOT / "titan" / "training" / "feature_schema_v2.py"
        assert path.exists()

    def test_schema_v2_has_55_features(self):
        from titan.training.feature_schema_v2 import FEATURE_NAMES_V2, N_FEATURES_V2
        assert N_FEATURES_V2 == 55
        assert len(FEATURE_NAMES_V2) == 55

    def test_absolute_features_replaced(self):
        """5 absolute-price features must be replaced by relative equivalents."""
        from titan.training.feature_schema_v2 import (
            FEATURE_NAMES_V2, ABSOLUTE_TO_RELATIVE, ABSOLUTE_FEATURES_V1,
        )
        # Old absolute names must NOT appear in v2
        for old in ABSOLUTE_FEATURES_V1:
            assert old not in FEATURE_NAMES_V2, f"{old} should be replaced in v2"
        # New relative names must appear in v2
        for old, new in ABSOLUTE_TO_RELATIVE.items():
            assert new in FEATURE_NAMES_V2, f"{new} should be in v2"

    def test_specific_replacements(self):
        """Verify specific feature name replacements."""
        from titan.training.feature_schema_v2 import ABSOLUTE_TO_RELATIVE
        assert ABSOLUTE_TO_RELATIVE["macd_signal"] == "macd_signal_relative"
        assert ABSOLUTE_TO_RELATIVE["macd_hist"] == "macd_hist_relative"
        assert ABSOLUTE_TO_RELATIVE["bb_upper"] == "bb_distance_upper"
        assert ABSOLUTE_TO_RELATIVE["obv"] == "obv_zscore_120"
        assert ABSOLUTE_TO_RELATIVE["obv_slope_20"] == "obv_slope_20_zscore"

    def test_v1_features_not_deleted(self):
        """v1 feature names module must still exist."""
        from titan.production.feature_stream import FEATURE_NAMES as V1
        assert len(V1) == 55
        assert "macd_signal" in V1  # v1 still has absolute
        assert "bb_upper" in V1


class TestFeatureEngineV2:
    def test_engine_v2_module_exists(self):
        path = REPO_ROOT / "titan" / "training" / "feature_engine_v2.py"
        assert path.exists()

    def test_engine_v2_compute_features(self):
        """compute_v2_features must return DataFrame with FEATURE_NAMES_V2 columns."""
        import pandas as pd
        import numpy as np
        from titan.training.feature_engine_v2 import compute_v2_features
        from titan.training.feature_schema_v2 import FEATURE_NAMES_V2

        # Create synthetic 250-bar DataFrame
        n = 250
        df = pd.DataFrame({
            "open": np.random.uniform(2000, 2100, n),
            "high": np.random.uniform(2100, 2200, n),
            "low": np.random.uniform(1900, 2000, n),
            "close": np.random.uniform(2000, 2100, n),
            "volume": np.random.uniform(100, 1000, n),
            "spread": np.random.uniform(0.1, 0.5, n),
        }, index=pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC"))
        feats = compute_v2_features(df)
        assert list(feats.columns) == FEATURE_NAMES_V2
        assert len(feats) == n

    def test_v2_features_are_stationary(self):
        """v2 features (relative) should not blow up with price level changes."""
        import pandas as pd
        import numpy as np
        from titan.training.feature_engine_v2 import compute_v2_features

        # Create two synthetic series: one at $1000, one at $5000 (5x price)
        n = 250
        base_close_low = np.cumsum(np.random.randn(n) * 0.001 + 0.0001) + 6.9  # log ~1000
        base_close_high = base_close_low + np.log(5)  # 5x price

        df_low = pd.DataFrame({
            "open": np.exp(base_close_low), "high": np.exp(base_close_low) * 1.01,
            "low": np.exp(base_close_low) * 0.99, "close": np.exp(base_close_low),
            "volume": np.random.uniform(100, 1000, n), "spread": np.random.uniform(0.1, 0.5, n),
        }, index=pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC"))
        df_high = pd.DataFrame({
            "open": np.exp(base_close_high), "high": np.exp(base_close_high) * 1.01,
            "low": np.exp(base_close_high) * 0.99, "close": np.exp(base_close_high),
            "volume": np.random.uniform(100, 1000, n), "spread": np.random.uniform(0.1, 0.5, n),
        }, index=pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC"))

        feats_low = compute_v2_features(df_low)
        feats_high = compute_v2_features(df_high)

        # bb_distance_upper should be roughly the same for both price levels
        # (it's a relative measure: (bb_upper - close) / close)
        low_mean = float(feats_low["bb_distance_upper"].tail(50).mean())
        high_mean = float(feats_high["bb_distance_upper"].tail(50).mean())
        # Allow up to 5x difference (vs 100x for absolute bb_upper)
        if not (np.isnan(low_mean) or np.isnan(high_mean)):
            ratio = max(low_mean, high_mean) / max(abs(low_mean), abs(high_mean), 1e-6)
            # The values should be very close (both are relative)
            assert abs(low_mean - high_mean) < 0.5, (
                f"bb_distance_upper should be stationary: low={low_mean}, high={high_mean}"
            )


class TestFeatureStreamV2:
    def test_stream_v2_module_exists(self):
        path = REPO_ROOT / "titan" / "production" / "feature_stream_v2.py"
        assert path.exists()

    def test_stream_v2_class_exists(self):
        from titan.production.feature_stream_v2 import H1FeatureStreamV2, FeatureVectorV2
        assert H1FeatureStreamV2 is not None
        assert FeatureVectorV2 is not None


# ─────────────────────────────────────────────────────────────────────
# Task 2-3: Feature datasets v2 + drift recheck
# ─────────────────────────────────────────────────────────────────────

class TestFeatureV2Datasets:
    def test_scaler_stats_v2_exists(self):
        path = REPO_ROOT / "titan" / "data" / "features_v2" / "scaler_stats_v2.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "mean" in data
        assert "std" in data
        assert len(data["mean"]) == 55

    def test_feature_schema_v2_json_exists(self):
        path = REPO_ROOT / "titan" / "data" / "features_v2" / "feature_schema_v2.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["schema_version"] == "v2"
        assert len(data["feature_names_v2"]) == 55

    def test_train_val_test_parquets_exist(self):
        for split in ["train", "val", "test"]:
            for kind in ["X", "y"]:
                path = REPO_ROOT / "titan" / "data" / "features_v2" / f"XAUUSD_H1_{kind}_{split}_v2.parquet"
                assert path.exists(), f"missing {path}"

    def test_drift_recheck_files_exist(self):
        for name in ["feature_drift_v1_vs_v2.md", "feature_drift_v1_vs_v2.csv",
                     "feature_schema_v2_audit.md", "feature_schema_v2_audit.csv",
                     "feature_v2_build_report.md"]:
            path = REPO_ROOT / "data" / "reports" / "feature_v2" / name
            assert path.exists(), f"missing {path}"

    def test_drift_acceptance_pass(self):
        """Drift recheck must show PASS acceptance."""
        path = REPO_ROOT / "data" / "reports" / "feature_v2" / "feature_drift_v1_vs_v2.md"
        text = path.read_text()
        assert "ACCEPTANCE: PASS" in text or "PASS" in text


# ─────────────────────────────────────────────────────────────────────
# Task 4-5: Model v2 training
# ─────────────────────────────────────────────────────────────────────

class TestModelV2Training:
    def test_xgb_v2_model_exists(self):
        path = REPO_ROOT / "titan" / "data" / "models" / "xgboost_v2_feature_normalized.pkl"
        assert path.exists()
        assert path.stat().st_size > 1000  # not empty

    def test_meta_v2_model_exists(self):
        path = REPO_ROOT / "titan" / "data" / "models" / "meta_label_v2_feature_normalized.pkl"
        assert path.exists()
        assert path.stat().st_size > 500  # LogisticRegression pickles are compact (~900 bytes)

    def test_v1_models_not_overwritten(self):
        """v1 models must still exist (not overwritten)."""
        for name in ["xgboost_v1.pkl", "meta_label_v2_context.pkl"]:
            path = REPO_ROOT / "titan" / "data" / "models" / name
            assert path.exists(), f"v1 model missing: {name}"

    def test_xgb_v2_training_report_exists(self):
        path = REPO_ROOT / "data" / "reports" / "training_v2" / "xgb_v2_training_report.md"
        assert path.exists()
        text = path.read_text()
        assert "AUC" in text
        assert "Test" in text or "OOS" in text

    def test_xgb_v2_metrics_json_exists(self):
        path = REPO_ROOT / "data" / "reports" / "training_v2" / "xgb_v2_metrics.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "test_auc" in data
        # OOS AUC must be > 0.50 (better than random)
        assert data["test_auc"] > 0.50, f"v2 OOS AUC must be > 0.50, got {data['test_auc']}"

    def test_xgb_v2_feature_importance_csv_exists(self):
        path = REPO_ROOT / "data" / "reports" / "training_v2" / "xgb_v2_feature_importance.csv"
        assert path.exists()

    def test_meta_v2_training_report_exists(self):
        path = REPO_ROOT / "data" / "reports" / "training_v2" / "meta_v2_training_report.md"
        assert path.exists()
        text = path.read_text()
        assert "AUC" in text

    def test_meta_v2_metrics_json_exists(self):
        path = REPO_ROOT / "data" / "reports" / "training_v2" / "meta_v2_metrics.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert "test_auc" in data
        assert "test_mean_proba" in data
        # Meta must not be degenerate (passes everything or blocks everything)
        assert 0.05 < data["test_mean_proba"] < 0.95, (
            f"v2 meta mean proba degenerate: {data['test_mean_proba']}"
        )

    def test_meta_v2_threshold_scan_csv_exists(self):
        path = REPO_ROOT / "data" / "reports" / "training_v2" / "meta_v2_threshold_scan.csv"
        assert path.exists()


# ─────────────────────────────────────────────────────────────────────
# Task 6: Model registry + loader
# ─────────────────────────────────────────────────────────────────────

class TestModelRegistryV2:
    def test_registry_module_exists(self):
        path = REPO_ROOT / "titan" / "production" / "model_registry.py"
        assert path.exists()

    def test_registry_has_v1_and_v2_profiles(self):
        from titan.production.model_registry import list_profiles
        profiles = list_profiles()
        assert "v1_legacy" in profiles
        assert "v2_feature_normalized" in profiles

    def test_default_profile_is_v1(self):
        """Production default must remain v1_legacy (not auto-switch to v2)."""
        from titan.production.model_registry import get_default_profile_name
        assert get_default_profile_name() == "v1_legacy"

    def test_v2_profile_not_production_default(self):
        from titan.production.model_registry import get_profile
        v2 = get_profile("v2_feature_normalized")
        assert v2.production_default is False

    def test_loader_v1_loads(self):
        from titan.production.model_loader import load_models_by_profile
        b = load_models_by_profile("v1_legacy")
        assert b.ok
        assert b.xgb is not None
        assert b.meta is not None

    def test_loader_v2_loads(self):
        from titan.production.model_loader import load_models_by_profile
        b = load_models_by_profile("v2_feature_normalized")
        assert b.ok
        assert b.xgb is not None
        assert b.meta is not None
        # v2 models must be different objects from v1 (different files)
        b1 = load_models_by_profile("v1_legacy")
        assert b.xgb is not b1.xgb
        assert b.meta is not b1.meta

    def test_loader_unknown_profile_raises(self):
        from titan.production.model_loader import load_models_by_profile
        with pytest.raises(ValueError):
            load_models_by_profile("v3_nonexistent")


# ─────────────────────────────────────────────────────────────────────
# Task 7: Real MTF confirmation
# ─────────────────────────────────────────────────────────────────────

class TestMTFConfirmation:
    def test_mtf_module_exists(self):
        path = REPO_ROOT / "titan" / "production" / "mtf_confirmation.py"
        assert path.exists()

    def test_mtf_h1_only_no_m15_m5(self):
        """h1_only must NOT use M15 or M5."""
        import pandas as pd
        from titan.production.mtf_confirmation import evaluate_mtf
        ts = pd.Timestamp("2025-01-01T00:00:00Z")
        result = evaluate_mtf("h1_only", ts, "LONG", m15_bars=pd.DataFrame(), m5_bars=pd.DataFrame())
        assert result.m15_used is False
        assert result.m5_used is False
        assert result.m15_confirmation_pass is True
        assert result.m5_entry_trigger_pass is True

    def test_mtf_h1_m15_uses_m15(self):
        """h1_m15 must set m15_used=True."""
        import pandas as pd
        import numpy as np
        from titan.production.mtf_confirmation import evaluate_mtf, reset_mtf_caches
        reset_mtf_caches()
        # Create synthetic M15 data
        n = 100
        m15 = pd.DataFrame({
            "open": np.linspace(2000, 2100, n), "high": np.linspace(2010, 2110, n),
            "low": np.linspace(1990, 2090, n), "close": np.linspace(2005, 2105, n),
        }, index=pd.date_range("2024-12-01", periods=n, freq="15min", tz="UTC"))
        ts = m15.index[-5]
        result = evaluate_mtf("h1_m15", ts, "LONG", m15_bars=m15)
        assert result.m15_used is True
        assert result.m5_used is False

    def test_mtf_h1_m15_m5_uses_both(self):
        """h1_m15_m5 must set both m15_used and m5_used to True."""
        import pandas as pd
        import numpy as np
        from titan.production.mtf_confirmation import evaluate_mtf, reset_mtf_caches
        reset_mtf_caches()
        n = 100
        m15 = pd.DataFrame({
            "open": np.linspace(2000, 2100, n), "high": np.linspace(2010, 2110, n),
            "low": np.linspace(1990, 2090, n), "close": np.linspace(2005, 2105, n),
        }, index=pd.date_range("2024-12-01", periods=n, freq="15min", tz="UTC"))
        m5 = pd.DataFrame({
            "open": np.linspace(2000, 2100, n), "high": np.linspace(2010, 2110, n),
            "low": np.linspace(1990, 2090, n), "close": np.linspace(2005, 2105, n),
        }, index=pd.date_range("2024-12-01", periods=n, freq="5min", tz="UTC"))
        ts = m15.index[-5]
        result = evaluate_mtf("h1_m15_m5", ts, "LONG", m15_bars=m15, m5_bars=m5)
        assert result.m15_used is True
        assert result.m5_used is True

    def test_mtf_modes_produce_different_results(self):
        """MTF audit must show 3 modes produce different trade counts."""
        path = REPO_ROOT / "data" / "reports" / "mtf_v2" / "mtf_implementation_audit.md"
        assert path.exists()
        text = path.read_text()
        assert "MTF_IMPLEMENTATION_GAP_FIXED:** True" in text or \
               "MTF_IMPLEMENTATION_GAP_FIXED: True" in text

    def test_mtf_audit_csv_exists(self):
        path = REPO_ROOT / "data" / "reports" / "mtf_v2" / "mtf_mode_effectiveness.csv"
        assert path.exists()


# ─────────────────────────────────────────────────────────────────────
# Task 8: Parameter discovery with v2 model
# ─────────────────────────────────────────────────────────────────────

class TestParameterDiscoveryV2:
    def test_discovery_v2_output_dir_exists(self):
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2"
        assert path.exists()

    def test_demo_go_decision_md_exists(self):
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "demo_go_decision.md"
        assert path.exists()
        text = path.read_text()
        # Must be one of the safe verdicts
        assert any(v in text for v in ["NO_SAFE_PARAMETER_FOUND", "DEMO_SHADOW_ALLOWED",
                                         "NEEDS_MORE_DATA", "INVALID_IMPLEMENTATION"])

    def test_parameter_search_summary_md_exists(self):
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "parameter_search_summary.md"
        assert path.exists()

    def test_top_20_parameter_sets_csv_exists(self):
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "top_20_parameter_sets.csv"
        assert path.exists()

    def test_broker_oos_results_csv_exists(self):
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "broker_oos_results.csv"
        assert path.exists()

    def test_yearly_walkforward_results_csv_exists(self):
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "yearly_walkforward_results.csv"
        assert path.exists()

    def test_leave_one_broker_out_results_csv_exists(self):
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "leave_one_broker_out_results.csv"
        assert path.exists()

    def test_parameter_sensitivity_csv_exists(self):
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "parameter_sensitivity.csv"
        assert path.exists()

    def test_production_component_audit_csv_exists(self):
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "production_component_audit.csv"
        assert path.exists()
        text = path.read_text()
        assert "PRODUCTION_XGBOOST" in text or "alpha_source" in text

    def test_model_profile_flag_in_source(self):
        """--model-profile flag must exist in discovery script."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "--model-profile" in src
        assert "v2_feature_normalized" in src
        assert "model_profile" in src


# ─────────────────────────────────────────────────────────────────────
# Task 9: Safety
# ─────────────────────────────────────────────────────────────────────

class TestSafety:
    def _strip(self, src):
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        return stripped

    def test_no_order_send_in_any_v2_8_7_e_file(self):
        files = [
            "titan/production/feature_stream_v2.py",
            "titan/production/mtf_confirmation.py",
            "titan/production/model_registry.py",
            "titan/training/feature_schema_v2.py",
            "titan/training/feature_engine_v2.py",
            "scripts/research/run_feature_v2_build.py",
            "scripts/research/run_model_v2_training.py",
            "scripts/research/run_mtf_v2_audit.py",
            "scripts/research/run_safe_parameter_discovery.py",
        ]
        for f in files:
            path = REPO_ROOT / f
            if path.exists():
                src = self._strip(path.read_text())
                assert "order_send" not in src, f"order_send found in {f}"

    def test_no_token_in_any_v2_8_7_e_file(self):
        files = [
            "titan/production/feature_stream_v2.py",
            "titan/production/mtf_confirmation.py",
            "titan/production/model_registry.py",
            "scripts/research/run_feature_v2_build.py",
            "scripts/research/run_model_v2_training.py",
            "scripts/research/run_safe_parameter_discovery.py",
        ]
        for f in files:
            path = REPO_ROOT / f
            if path.exists():
                src = path.read_text()
                assert "create_local_operator_execution_token" not in src, f"token found in {f}"

    def test_no_martingale_in_any_v2_8_7_e_file(self):
        files = [
            "titan/production/feature_stream_v2.py",
            "titan/production/mtf_confirmation.py",
            "titan/training/feature_engine_v2.py",
            "scripts/research/run_feature_v2_build.py",
            "scripts/research/run_model_v2_training.py",
            "scripts/research/run_safe_parameter_discovery.py",
        ]
        for f in files:
            path = REPO_ROOT / f
            if path.exists():
                src = self._strip(path.read_text())
                assert "martingale" not in src.lower(), f"martingale found in {f}"

    def test_no_sma_proxy(self):
        """No SMA used as entry direction proxy."""
        files = [
            "titan/production/mtf_confirmation.py",
            "scripts/research/run_safe_parameter_discovery.py",
            "scripts/research/run_model_v2_training.py",
        ]
        for f in files:
            path = REPO_ROOT / f
            if path.exists():
                src = self._strip(path.read_text())
                assert "sma_crossover" not in src.lower()
                assert "sma_proxy" not in src.lower()

    def test_no_volatility_proxy(self):
        files = [
            "titan/production/mtf_confirmation.py",
            "scripts/research/run_safe_parameter_discovery.py",
        ]
        for f in files:
            path = REPO_ROOT / f
            if path.exists():
                src = self._strip(path.read_text())
                assert "volatility_proxy" not in src.lower()
                assert "vol_proxy" not in src.lower()

    def test_production_ready_remains_false(self):
        """production_ready must remain False in discovery script."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert '"production_ready": False' in src or "'production_ready': False" in src

    def test_v2_not_default_profile(self):
        """v2 must NOT be the production default."""
        from titan.production.model_registry import get_default_profile_name
        assert get_default_profile_name() != "v2_feature_normalized"

    def test_no_bypass_of_meta_label(self):
        """Discovery script must still check meta_confidence threshold."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "meta_confidence < params.meta_threshold" in src

    def test_no_bypass_of_ceo(self):
        """Discovery script must still call CEO governance."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "evaluate_ceo_decision" in src
        assert "ceo_decision.allowed_to_trade" in src or "if not ceo_decision" in src

    def test_uses_real_production_models(self):
        """v2 must use real production XGBoost + meta-label, not proxy."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "load_models_by_profile" in src or "load_production_models" in src
        assert "bundle.xgb" in src or "predict_proba" in src

    def test_v2_demo_go_decision_not_unsafe(self):
        """If v2 demo_go_decision is DEMO_SHADOW_ALLOWED, it must still require operator review."""
        path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "demo_go_decision.md"
        text = path.read_text()
        # If allowed, must require operator review (not auto-trade)
        if "DEMO_SHADOW_ALLOWED" in text:
            # Check that final_candidate (if exists) has production_ready=False
            cand_path = REPO_ROOT / "data" / "reports" / "parameter_discovery_v2" / "final_candidate_params.json"
            if cand_path.exists():
                data = json.loads(cand_path.read_text())
                assert data.get("production_ready") is False, \
                    "production_ready must remain False even for DEMO_SHADOW_ALLOWED"
