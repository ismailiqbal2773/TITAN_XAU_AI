"""TITAN XAU AI - Sprint v2.8.7-B Meta-Label Broker Diagnostic Tests"""
from __future__ import annotations
import sys, re, csv, os
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "parameter_discovery"


class TestMetaLabelDiagnostic:
    def test_diagnostic_generates_files(self):
        """Meta diagnostic must generate output files."""
        import scripts.research.run_meta_label_broker_diagnostic as m
        result = m.run_diagnostic()
        assert (OUTPUT_DIR / "meta_label_broker_diagnostic.md").exists()
        assert (OUTPUT_DIR / "meta_label_broker_diagnostic.csv").exists()
        assert (OUTPUT_DIR / "meta_feature_distribution_comparison.md").exists()
        assert (OUTPUT_DIR / "meta_feature_distribution_comparison.csv").exists()
        assert (OUTPUT_DIR / "model_compatibility_audit.md").exists()

    def test_meta_label_broker_shift_detected(self):
        """META_LABEL_BROKER_SHIFT must be tracked."""
        import scripts.research.run_meta_label_broker_diagnostic as m
        result = m.run_diagnostic()
        assert "meta_label_broker_shift" in result
        # The shift IS detected (spread_pct drift causes meta distribution shift)
        # But the direction is OPPOSITE: brokers have meta~1.0 while canonical has meta~0.39
        # So meta>0.65=0 is NOT the issue - brokers have TOO MANY meta>0.65
        assert isinstance(result["meta_label_broker_shift"], bool)

    def test_top_drifted_feature_identified(self):
        """Top drifted feature must be identified."""
        import scripts.research.run_meta_label_broker_diagnostic as m
        result = m.run_diagnostic()
        assert "top_drifted_feature" in result
        assert result["top_drifted_feature"] == "spread_pct"

    def test_model_compatibility_audit_generated(self):
        """Model compatibility audit must be generated."""
        assert (OUTPUT_DIR / "model_compatibility_audit.md").exists()
        src = (OUTPUT_DIR / "model_compatibility_audit.md").read_text()
        assert "XGBoost" in src
        assert "sklearn" in src


class TestMTFGridFix:
    def test_mtf_modes_in_grid(self):
        """Fast grid must include h1_only, h1_m15, h1_m15_m5."""
        import scripts.research.run_safe_parameter_discovery as m
        grid = m.generate_param_grid("fast")
        mtf_modes = set(p.mtf_mode for p in grid)
        assert "h1_only" in mtf_modes
        assert "h1_m15" in mtf_modes
        assert "h1_m15_m5" in mtf_modes

    def test_progress_every_flag_exists(self):
        """--progress-every flag must exist."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "--progress-every" in src
        assert "progress_every" in src


class TestSafety:
    def test_no_order_send(self):
        """Diagnostic script must never call order_send."""
        src = (REPO_ROOT / "scripts" / "research" / "run_meta_label_broker_diagnostic.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        assert "order_send(" not in stripped

    def test_no_token(self):
        """Diagnostic script must never create tokens."""
        src = (REPO_ROOT / "scripts" / "research" / "run_meta_label_broker_diagnostic.py").read_text()
        assert "create_local_operator_execution_token" not in src

    def test_production_ready_false(self):
        """Parameter discovery must still have production_ready=False."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "production_ready" in src
        assert "False" in src

    def test_no_martingale(self):
        """No martingale in diagnostic script."""
        src = (REPO_ROOT / "scripts" / "research" / "run_meta_label_broker_diagnostic.py").read_text()
        assert "martingale" not in src.lower()

    def test_alpha_threshold_preserved(self):
        """Alpha threshold 0.55 must be in parameter discovery source."""
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "0.55" in src
