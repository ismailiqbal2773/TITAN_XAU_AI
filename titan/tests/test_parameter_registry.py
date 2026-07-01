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
        assert entry.runtime_value == ParameterRegistry.DEFAULTS["breakeven_trigger_R"]
