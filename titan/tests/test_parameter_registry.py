"""TITAN XAU AI - Sprint 9.9.3.45.8.3 Parameter Registry Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.parameter_registry import ParameterRegistry, ParameterEntry


class TestParameterRegistry:
    def test_01_registry_imports(self):
        assert ParameterRegistry is not None

    def test_02_registry_has_parameters(self):
        registry = ParameterRegistry()
        assert len(registry.parameters) > 0

    def test_03_default_source_is_safe_default(self):
        """Parameters without backtest artifacts should be SAFE_DEFAULT."""
        registry = ParameterRegistry()
        entry = registry.get_parameter("breakeven_trigger_R")
        assert entry.source in ("SAFE_DEFAULT", "BACKTEST_VALIDATED")

    def test_04_missing_backtest_params_labeled_honestly(self):
        """Missing backtest params must be labeled NEEDS_BACKTEST_BINDING."""
        registry = ParameterRegistry()
        entry = registry.get_parameter("trailing_trigger_R")
        if entry.source == "SAFE_DEFAULT":
            assert entry.validation_status == "NEEDS_BACKTEST_BINDING"

    def test_05_get_all_parameters(self):
        registry = ParameterRegistry()
        params = registry.get_all_parameters()
        assert len(params) > 0
        for p in params:
            assert isinstance(p, ParameterEntry)
            assert p.parameter_name != ""

    def test_06_get_summary(self):
        registry = ParameterRegistry()
        summary = registry.get_summary()
        assert "total_parameters" in summary
        assert "validated" in summary
        assert "safe_default" in summary
        assert "validation_rate" in summary
        assert "parameters" in summary

    def test_07_parameter_has_required_fields(self):
        registry = ParameterRegistry()
        entry = registry.get_parameter("min_hold_seconds")
        required = ["parameter_name", "runtime_value", "source",
                     "artifact_path", "validation_status", "reason"]
        for f in required:
            assert hasattr(entry, f), f"Missing field: {f}"

    def test_08_no_order_send(self):
        import re
        src = (REPO_ROOT / "titan" / "production" / "parameter_registry.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_09_no_martingale(self):
        import re
        src = (REPO_ROOT / "titan" / "production" / "parameter_registry.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', '""', src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in code

    def test_10_runtime_values_match_defaults(self):
        """Runtime values should match DEFAULTS dict."""
        registry = ParameterRegistry()
        entry = registry.get_parameter("breakeven_trigger_R")
        # DEFAULTS now stores (value, description) tuples
        default_value = ParameterRegistry.DEFAULTS["breakeven_trigger_R"]
        if isinstance(default_value, tuple):
            default_value = default_value[0]
        assert entry.runtime_value == default_value

    # === Sprint 9.9.3.45.8.5: backtest binding tests ===

    def test_11_critical_parameters_exist(self):
        """Registry must include critical parameters."""
        registry = ParameterRegistry()
        critical = registry.get_critical_parameters()
        assert len(critical) > 0
        for p in critical:
            assert p.is_critical is True

    def test_12_atr_sl_multiplier_bound(self):
        """ATR SL multiplier must be bound from ATR validation artifact."""
        registry = ParameterRegistry()
        entry = registry.get_parameter("atr_sl_multiplier")
        assert entry.source != "SAFE_DEFAULT", f"atr_sl_multiplier still SAFE_DEFAULT: {entry.reason}"
        assert entry.source_type == "BACKTEST_VALIDATED"
        assert entry.runtime_value == 1.5

    def test_13_tp_multiplier_bound(self):
        """TP multiplier must be bound from ATR validation artifact."""
        registry = ParameterRegistry()
        entry = registry.get_parameter("tp_multiplier_initial_tp_R")
        assert entry.source != "SAFE_DEFAULT"
        assert entry.runtime_value == 3.0

    def test_14_risk_per_trade_bound(self):
        """Risk per trade must be bound from parameter optimization."""
        registry = ParameterRegistry()
        entry = registry.get_parameter("risk_per_trade_pct")
        assert entry.source != "SAFE_DEFAULT"
        assert entry.source_type == "BACKTEST_VALIDATED"

    def test_15_spread_threshold_bound(self):
        """Max spread threshold must be bound from broker execution profile."""
        registry = ParameterRegistry()
        entry = registry.get_parameter("max_spread_threshold")
        assert entry.source != "SAFE_DEFAULT"
        assert entry.source_type == "BROKER_SPLIT_VALIDATED"

    def test_16_no_critical_unbound(self):
        """All critical parameters must be bound (0 unbound)."""
        registry = ParameterRegistry()
        unbound = registry.get_unbound_critical()
        assert len(unbound) == 0, f"Unbound critical: {[p.parameter_name for p in unbound]}"

    def test_17_summary_includes_critical_counts(self):
        """Summary must include critical_total, critical_bound, critical_unbound."""
        registry = ParameterRegistry()
        summary = registry.get_summary()
        assert "critical_total" in summary
        assert "critical_bound" in summary
        assert "critical_unbound" in summary
        assert "artifacts_scanned" in summary

    def test_18_artifacts_scanned_count_positive(self):
        """Artifacts scanned count must be positive."""
        registry = ParameterRegistry()
        summary = registry.get_summary()
        assert summary["artifacts_scanned"] > 0

    def test_19_no_fake_metrics(self):
        """Parameters must not have fabricated metrics - artifact_path must exist if source is not SAFE_DEFAULT."""
        registry = ParameterRegistry()
        from pathlib import Path
        for p in registry.get_all_parameters():
            if p.source != "SAFE_DEFAULT":
                assert p.artifact_path != "", f"Non-safe-default parameter {p.parameter_name} has no artifact_path"
                # Artifact path should be a real file
                assert Path(p.artifact_path).exists(), \
                    f"Artifact path does not exist for {p.parameter_name}: {p.artifact_path}"

    def test_20_confidence_level_set(self):
        """All parameters must have confidence_level set."""
        registry = ParameterRegistry()
        for p in registry.get_all_parameters():
            assert p.confidence_level in ("LOW", "MEDIUM", "HIGH"), \
                f"Invalid confidence_level for {p.parameter_name}: {p.confidence_level}"
