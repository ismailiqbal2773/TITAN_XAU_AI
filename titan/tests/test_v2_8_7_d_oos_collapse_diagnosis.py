"""TITAN XAU AI - Sprint v2.8.7-D OOS Collapse Diagnosis Tests

Verifies that:
  - OOS diagnosis script exists
  - All required output files are created
  - Direction inversion audit exists
  - Exit geometry audit exists
  - Regime filter audit exists
  - Feature drift audit exists
  - Confidence bucket audit exists
  - MTF mode audit exists
  - recommended_fix_path.md exists
  - No order_send / token / trade in source
  - production_ready remains False
  - No SMA proxy / volatility proxy

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, re, os
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "oos_collapse"
DISCOVERY_DIR = REPO_ROOT / "data" / "reports" / "parameter_discovery"


class TestOOSCollapseDiagnosisScript:
    def test_script_exists(self):
        """OOS collapse diagnosis script must exist."""
        path = REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py"
        assert path.exists(), f"missing {path}"

    def test_script_has_main_function(self):
        """Script must have a main() entry point."""
        src = (REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py").read_text()
        assert "def main():" in src

    def test_script_imports_production_components(self):
        """Script must import real production components (not proxy)."""
        src = (REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py").read_text()
        assert "from scripts.research.run_safe_parameter_discovery import" in src
        assert "from titan.production.feature_stream import" in src
        assert "from titan.production.model_loader import" in src


class TestOOSCollapseOutputFiles:
    """All required output files must exist after diagnosis run."""

    def test_oos_collapse_diagnosis_md_exists(self):
        path = OUTPUT_DIR / "oos_collapse_diagnosis.md"
        assert path.exists(), f"missing {path}"

    def test_oos_collapse_diagnosis_json_exists(self):
        path = OUTPUT_DIR / "oos_collapse_diagnosis.json"
        assert path.exists(), f"missing {path}"

    def test_broker_year_performance_csv_exists(self):
        path = OUTPUT_DIR / "broker_year_performance.csv"
        assert path.exists(), f"missing {path}"

    def test_regime_performance_csv_exists(self):
        path = OUTPUT_DIR / "regime_performance.csv"
        assert path.exists(), f"missing {path}"

    def test_session_performance_csv_exists(self):
        path = OUTPUT_DIR / "session_performance.csv"
        assert path.exists(), f"missing {path}"

    def test_direction_performance_csv_exists(self):
        """Direction inversion audit CSV must exist."""
        path = OUTPUT_DIR / "direction_inversion_audit.csv"
        assert path.exists(), f"missing {path}"

    def test_confidence_bucket_performance_csv_exists(self):
        path = OUTPUT_DIR / "confidence_bucket_performance.csv"
        assert path.exists(), f"missing {path}"

    def test_meta_bucket_performance_in_csv(self):
        """confidence_bucket_performance.csv must contain meta bucket rows."""
        path = OUTPUT_DIR / "confidence_bucket_performance.csv"
        text = path.read_text()
        assert "meta_" in text, "meta bucket rows missing from confidence_bucket_performance.csv"

    def test_mtf_mode_performance_csv_exists(self):
        path = OUTPUT_DIR / "mtf_mode_audit.csv"
        assert path.exists(), f"missing {path}"

    def test_exit_reason_breakdown_csv_exists(self):
        path = OUTPUT_DIR / "exit_reason_breakdown.csv"
        assert path.exists(), f"missing {path}"

    def test_rejection_reason_breakdown_csv_exists(self):
        path = OUTPUT_DIR / "rejection_reason_breakdown.csv"
        assert path.exists(), f"missing {path}"

    def test_recommended_fix_path_md_exists(self):
        path = OUTPUT_DIR / "recommended_fix_path.md"
        assert path.exists(), f"missing {path}"

    def test_direction_inversion_audit_md_exists(self):
        path = OUTPUT_DIR / "direction_inversion_audit.md"
        assert path.exists(), f"missing {path}"

    def test_exit_geometry_audit_md_exists(self):
        path = OUTPUT_DIR / "exit_geometry_audit.md"
        assert path.exists(), f"missing {path}"

    def test_regime_filter_audit_md_exists(self):
        path = OUTPUT_DIR / "regime_filter_audit.md"
        assert path.exists(), f"missing {path}"

    def test_feature_drift_md_exists(self):
        path = OUTPUT_DIR / "feature_drift_2025_2026.md"
        assert path.exists(), f"missing {path}"

    def test_feature_drift_csv_exists(self):
        path = OUTPUT_DIR / "feature_drift_2025_2026.csv"
        assert path.exists(), f"missing {path}"

    def test_confidence_bucket_md_exists(self):
        path = OUTPUT_DIR / "confidence_bucket_performance.md"
        assert path.exists(), f"missing {path}"

    def test_mtf_mode_audit_md_exists(self):
        path = OUTPUT_DIR / "mtf_mode_audit.md"
        assert path.exists(), f"missing {path}"


class TestDiagnosisFlags:
    """Diagnosis flags must be present and correctly typed."""

    def test_diagnosis_json_has_flags(self):
        import json
        path = OUTPUT_DIR / "oos_collapse_diagnosis.json"
        data = json.loads(path.read_text())
        assert "flags" in data
        flags = data["flags"]

        # All required flags must be present
        required_flags = [
            "BUG_FIX_NEEDED",
            "PARAMETER_TUNING_NEEDED",
            "EXIT_GEOMETRY_FIX_NEEDED",
            "REGIME_FILTER_FIX_NEEDED",
            "FEATURE_DRIFT_FIX_NEEDED",
            "DIRECTION_INVERSION_SUSPECT",
            "META_LABEL_RECALIBRATION_NEEDED",
            "MTF_IMPLEMENTATION_GAP",
            "RETRAIN_REQUIRED_LATER",
            "NO_TRADE_ALLOWED",
        ]
        for flag in required_flags:
            assert flag in flags, f"missing flag {flag}"
            assert isinstance(flags[flag], bool), f"flag {flag} must be bool"

    def test_feature_drift_flag_is_true(self):
        """FEATURE_DRIFT_FIX_NEEDED must be True (root cause confirmed)."""
        import json
        path = OUTPUT_DIR / "oos_collapse_diagnosis.json"
        data = json.loads(path.read_text())
        assert data["flags"]["FEATURE_DRIFT_FIX_NEEDED"] is True, \
            "FEATURE_DRIFT_FIX_NEEDED must be True — gold price 2.11x shift causes bb_upper/obv drift"

    def test_no_trade_allowed_flag_is_true(self):
        """NO_TRADE_ALLOWED must be True (no candidate found)."""
        import json
        path = OUTPUT_DIR / "oos_collapse_diagnosis.json"
        data = json.loads(path.read_text())
        assert data["flags"]["NO_TRADE_ALLOWED"] is True

    def test_retrain_required_later_is_true(self):
        """RETRAIN_REQUIRED_LATER must be True (drift requires retrain)."""
        import json
        path = OUTPUT_DIR / "oos_collapse_diagnosis.json"
        data = json.loads(path.read_text())
        assert data["flags"]["RETRAIN_REQUIRED_LATER"] is True

    def test_drift_summary_present(self):
        """Drift summary with gold price IS/OOS means must be present."""
        import json
        path = OUTPUT_DIR / "oos_collapse_diagnosis.json"
        data = json.loads(path.read_text())
        assert "drift_summary" in data
        ds = data["drift_summary"]
        assert "close_is_mean" in ds
        assert "close_oos_mean" in ds
        assert "close_ratio" in ds
        # Gold price must have shifted significantly (>= 1.5x)
        assert ds["close_ratio"] >= 1.5, \
            f"gold price ratio {ds['close_ratio']} too low — expected >= 1.5x drift"

    def test_top_drifted_features_present(self):
        """Top drifted features list must be present and include bb_upper or obv."""
        import json
        path = OUTPUT_DIR / "oos_collapse_diagnosis.json"
        data = json.loads(path.read_text())
        assert "top_drifted_features" in data
        top = data["top_drifted_features"]
        assert len(top) >= 3
        # bb_upper or obv must be in top 5 (absolute-price features)
        assert "bb_upper" in top or "obv" in top, \
            f"expected bb_upper or obv in top drifted features, got {top}"


class TestRecommendedFixPath:
    def test_recommended_fix_path_has_classification(self):
        """recommended_fix_path.md must contain classification flags."""
        path = OUTPUT_DIR / "recommended_fix_path.md"
        text = path.read_text()
        assert "Classification Flags" in text or "## Classification" in text
        assert "FEATURE_DRIFT_FIX_NEEDED" in text
        assert "RETRAIN_REQUIRED_LATER" in text
        assert "NO_TRADE_ALLOWED" in text

    def test_recommended_fix_path_has_root_cause(self):
        """Fix path must explain root cause."""
        path = OUTPUT_DIR / "recommended_fix_path.md"
        text = path.read_text()
        assert "Root Cause" in text or "root cause" in text.lower()

    def test_recommended_fix_path_has_next_sprint(self):
        """Fix path must recommend next sprint."""
        path = OUTPUT_DIR / "recommended_fix_path.md"
        text = path.read_text()
        assert "SPRINT v2.8.7-E" in text or "next sprint" in text.lower()

    def test_recommended_fix_path_does_not_retrain_now(self):
        """Fix path must NOT recommend retraining in current sprint."""
        path = OUTPUT_DIR / "recommended_fix_path.md"
        text = path.read_text()
        assert "Do NOT retrain in this sprint" in text or \
               "RETRAIN_REQUIRED_LATER only" in text


class TestSafety:
    def test_no_order_send_in_diagnosis_script(self):
        """OOS diagnosis script must never call order_send."""
        src = (REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        assert "order_send" not in stripped

    def test_no_token_in_diagnosis_script(self):
        """OOS diagnosis script must never create tokens."""
        src = (REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py").read_text()
        assert "create_local_operator_execution_token" not in src
        assert "execution_token" not in src.lower()

    def test_no_trade_calls_in_diagnosis_script(self):
        """Diagnosis script must not invoke trade execution."""
        src = (REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        for forbidden in ["order_send", "positions_add", "trade_request", "PositionSend"]:
            assert forbidden not in stripped, f"{forbidden} found in diagnosis script"

    def test_no_martingale_in_diagnosis_script(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py").read_text()
        # Strip docstrings and string literals
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        assert "martingale" not in stripped.lower()

    def test_no_sma_proxy_in_diagnosis_script(self):
        """Diagnosis script must NOT use SMA as entry proxy.

        SMA may appear in feature names (sma_20_ratio, sma_200_ratio) but
        must not be used as a standalone entry signal.
        """
        src = (REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py").read_text()
        # Strip docstrings and string literals
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'"[^"]*"', '""', stripped)
        stripped = re.sub(r"'[^']*'", "''", stripped)
        # Look for SMA used as entry decision (not as feature name reference)
        assert "sma_crossover" not in stripped.lower()
        assert "sma_proxy" not in stripped.lower()
        # sma_20_ratio and sma_200_ratio as feature names are OK (they're production features)
        # but using "sma" alone as direction proxy is forbidden
        lines = stripped.split("\n")
        for line in lines:
            line_lower = line.lower()
            # If line mentions sma but not as a feature name, flag it
            if "sma" in line_lower and "sma_" not in line_lower and "sma." not in line_lower:
                if any(kw in line_lower for kw in ["direction", "signal", "entry", "long", "short"]):
                    pytest.fail(f"possible SMA proxy usage: {line.strip()}")

    def test_no_volatility_proxy_in_diagnosis_script(self):
        """Diagnosis script must NOT use volatility as entry proxy.

        ATR and realized_vol may appear as features and regime labels,
        but must not be used as standalone entry signals.
        """
        src = (REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        assert "volatility_proxy" not in stripped.lower()
        assert "vol_proxy" not in stripped.lower()
        # ATR is used for SL/TP geometry (allowed) and as regime label (allowed)
        # but not as entry direction signal

    def test_production_ready_remains_false_in_discovery(self):
        """Parameter discovery must still have production_ready=False."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "production_ready" in src
        assert '"production_ready": False' in src or "'production_ready': False" in src

    def test_demo_go_decision_not_allowed(self):
        """Demo go decision must NOT be DEMO_SHADOW_ALLOWED after v2.8.7-D."""
        path = DISCOVERY_DIR / "demo_go_decision.md"
        assert path.exists()
        text = path.read_text()
        # Must be NO_SAFE_PARAMETER_FOUND (not DEMO_SHADOW_ALLOWED)
        assert "NO_SAFE_PARAMETER_FOUND" in text or "NEEDS_MORE_DATA" in text or \
               "INVALID_IMPLEMENTATION" in text
        assert "DEMO_SHADOW_ALLOWED" not in text, \
            "DEMO_SHADOW_ALLOWED must NOT be set — no candidate found"

    def test_no_bypass_of_meta_label(self):
        """Diagnosis script must not bypass meta-label check."""
        src = (REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py").read_text()
        # The backtest must still check meta_confidence < params.meta_threshold
        assert "meta_confidence < params.meta_threshold" in src or \
               "meta_confidence < self.meta_threshold" in src, \
               "meta-label threshold check must be present (no bypass)"

    def test_no_bypass_of_ceo(self):
        """Diagnosis script must not bypass CEO governance."""
        src = (REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py").read_text()
        assert "evaluate_ceo_decision" in src, \
               "CEO governance must be called (no bypass)"
        assert "ceo_decision.allowed_to_trade" in src or \
               "if not ceo_decision" in src

    def test_uses_real_production_models(self):
        """Diagnosis must use real production XGBoost and meta-label, not proxy."""
        src = (REPO_ROOT / "scripts" / "research" / "run_oos_collapse_diagnosis.py").read_text()
        assert "load_production_models" in src
        # The script imports precompute_model_predictions (which internally uses bundle.xgb
        # and bundle.meta) OR references bundle.xgb directly
        assert "precompute_model_predictions" in src or "bundle.xgb" in src, \
               "must use precompute_model_predictions (which calls bundle.xgb) or bundle.xgb directly"
        assert "bundle.meta" in src or "META_FEATURE_NAMES" in src, \
               "must use bundle.meta or META_FEATURE_NAMES"


class TestDirectionInversionAudit:
    def test_direction_audit_has_improvement_ratio(self):
        """Direction inversion audit must have improvement_ratio column."""
        path = OUTPUT_DIR / "direction_inversion_audit.csv"
        text = path.read_text()
        assert "improvement_ratio" in text
        assert "original_pf" in text
        assert "flipped_pf" in text

    def test_direction_inversion_not_suspect(self):
        """Direction inversion must NOT be suspect (flipping makes it worse)."""
        path = OUTPUT_DIR / "direction_inversion_audit.md"
        text = path.read_text()
        # DIRECTION_INVERSION_SUSPECT should be False
        assert "False" in text


class TestFeatureDriftAudit:
    def test_feature_drift_csv_has_55_features(self):
        """Feature drift CSV must have entries for all 55 production features."""
        import csv
        path = OUTPUT_DIR / "feature_drift_2025_2026.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 55, f"expected 55 feature rows, got {len(rows)}"

    def test_feature_drift_has_drift_score(self):
        """Feature drift CSV must have drift_score column."""
        path = OUTPUT_DIR / "feature_drift_2025_2026.csv"
        text = path.read_text()
        assert "drift_score" in text
        assert "is_mean" in text
        assert "oos_mean" in text

    def test_bb_upper_is_top_drifted(self):
        """bb_upper must be among top drifted features (absolute price feature)."""
        import csv
        path = OUTPUT_DIR / "feature_drift_2025_2026.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        # Sort by drift_score descending
        rows.sort(key=lambda x: float(x["drift_score"]), reverse=True)
        top5 = [r["feature"] for r in rows[:5]]
        assert "bb_upper" in top5, \
            f"bb_upper must be in top 5 drifted features, got {top5}"


class TestMTFModeAudit:
    def test_mtf_modes_all_tested(self):
        """MTF audit must test all 3 modes: h1_only, h1_m15, h1_m15_m5."""
        import csv
        path = OUTPUT_DIR / "mtf_mode_audit.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        modes = {r["mtf_mode"] for r in rows}
        assert "h1_only" in modes
        assert "h1_m15" in modes
        assert "h1_m15_m5" in modes

    def test_mtf_implementation_gap_is_true(self):
        """MTF_IMPLEMENTATION_GAP must be True (backtest doesn't use M15/M5)."""
        path = OUTPUT_DIR / "mtf_mode_audit.md"
        text = path.read_text()
        assert "MTF_IMPLEMENTATION_GAP:** True" in text or \
               "MTF_IMPLEMENTATION_GAP: True" in text


class TestExitGeometryAudit:
    def test_exit_geometry_has_sl_tp_timeout_rates(self):
        """Exit geometry audit must have SL/TP/timeout rates."""
        import csv
        path = OUTPUT_DIR / "exit_geometry_audit.csv"
        with open(path) as f:
            rows = list(csv.DictReader(f))
        assert len(rows) > 0
        first = rows[0]
        assert "sl_hit_rate" in first
        assert "tp_hit_rate" in first
        assert "timeout_rate" in first
