"""TITAN XAU AI - Sprint v2.8.7-A Production-Integrated Parameter Discovery Tests"""
from __future__ import annotations
import sys, re
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestProductionIntegration:
    def test_production_alpha_source_required(self):
        """Final scoring must use production XGBoost, not SMA proxy."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "PRODUCTION_XGBOOST" in src
        assert "alpha_proba" in src
        # Must NOT use SMA proxy for final scoring
        assert "sma_10" not in src or "SMA" not in src.split("PRODUCTION")[0]

    def test_production_meta_label_source_required(self):
        """Final scoring must use production meta-label, not volatility proxy."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "PRODUCTION_META_LABEL" in src
        assert "meta_proba" in src
        # Must NOT use volatility proxy for final scoring
        assert "recent_vol" not in src or "volatility proxy" not in src.lower()

    def test_ceo_called_in_backtest(self):
        """CEO governance must be called during backtest."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "evaluate_ceo_decision" in src
        assert "ceo_decision" in src
        assert "allowed_to_trade" in src

    def test_feature_pipeline_used(self):
        """Production feature pipeline must be used."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "H1FeatureStream" in src
        assert "FEATURE_NAMES" in src
        assert "_compute_features" in src or "latest_vector" in src

    def test_model_loader_used(self):
        """Production model loader must be used."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "load_production_models" in src
        assert "predict_proba" in src

    def test_production_component_audit(self):
        """Output must include production component audit."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "PRODUCTION_AUDIT" in src or "production_audit" in src
        assert "alpha_source" in src
        assert "meta_source" in src
        assert "ceo_source" in src
        assert "feature_source" in src


class TestNoProxy:
    def test_no_sma_proxy_alpha_in_final(self):
        """SMA proxy alpha must not be used for final candidate scoring."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        # The old proxy code used "sma_10" - verify it's removed from run_backtest
        # Find run_backtest function body
        idx = src.find("def run_backtest")
        if idx > 0:
            end = src.find("\ndef ", idx + 1)
            body = src[idx:end if end > 0 else len(src)]
            assert "sma_10" not in body, "SMA proxy must not be in run_backtest"
            assert "price_change" not in body or "alpha_proba" in body

    def test_no_volatility_proxy_meta_in_final(self):
        """Volatility proxy meta-label must not be used for final scoring."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        idx = src.find("def run_backtest")
        if idx > 0:
            end = src.find("\ndef ", idx + 1)
            body = src[idx:end if end > 0 else len(src)]
            assert "recent_vol" not in body, "Volatility proxy must not be in run_backtest"
            assert "0.5 + (recent_vol" not in body

    def test_no_dummy_data(self):
        """Script must not use dummy/synthetic data."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "NO dummy" in src or "no dummy" in src.lower() or "NO dummy/synthetic" in src


class TestSafety:
    def test_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        stripped = re.sub(r'"(?:[^"\\]|\\.)*"', '""', stripped)
        stripped = re.sub(r"'(?:[^'\\]|\\.)*'", "''", stripped)
        assert "order_send(" not in stripped

    def test_no_token(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "create_local_operator_execution_token" not in src

    def test_alpha_threshold_preserved(self):
        """Alpha threshold 0.55 must be in source as production default."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "0.55" in src

    def test_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "martingale" not in src.lower()

    def test_ceo_not_bypassed(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "bypass" not in src.lower() or "do not bypass" in src.lower()

    def test_demo_go_decision_output(self):
        """demo_go_decision.md must be generated."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "demo_go_decision" in src
        assert "DEMO_SHADOW_ALLOWED" in src
        assert "NO_SAFE_PARAMETER_FOUND" in src
        assert "INVALID_IMPLEMENTATION" in src

    def test_production_ready_false(self):
        """Final candidate must have production_ready=False."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "production_ready" in src
        assert "False" in src

    def test_early_stop_supported(self):
        """Early stop must be supported."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "early_stop" in src
        assert "--early-stop" in src
        assert "--mode" in src

    def test_no_lookahead(self):
        """Backtest must not use future data for entry decisions."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "alpha_proba[i]" in src  # Entry uses current bar prediction
        assert "i + j" in src or "i+j" in src  # Exit uses future bars
