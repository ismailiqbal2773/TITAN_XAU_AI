"""TITAN XAU AI - Sprint v2.8.3.1 Verdict Normalizer Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestVerdictNormalizer:
    def test_01_module_imports(self):
        from titan.production.verdict_normalizer import (
            is_alpha_entry_pass, is_entry_gate_pass,
            is_autonomous_readiness_pass, is_production_autonomous_pass,
        )
        assert callable(is_alpha_entry_pass)
        assert callable(is_entry_gate_pass)
        assert callable(is_autonomous_readiness_pass)
        assert callable(is_production_autonomous_pass)

    def test_02_alpha_entry_pass_recognized(self):
        from titan.production.verdict_normalizer import is_alpha_entry_pass
        assert is_alpha_entry_pass("ALPHA_REGIME_ENTRY_PASS") is True
        assert is_alpha_entry_pass("PASS") is True
        assert is_alpha_entry_pass("ALPHA_REGIME_ENTRY_BLOCKED_NO_REGIME") is False
        assert is_alpha_entry_pass("") is False
        assert is_alpha_entry_pass(None) is False

    def test_03_entry_gate_pass_recognized(self):
        from titan.production.verdict_normalizer import is_entry_gate_pass
        assert is_entry_gate_pass("ENTRY_GATE_FULL_PASS") is True
        assert is_entry_gate_pass("PASS") is True
        assert is_entry_gate_pass("ENTRY_GATE_BLOCKED_GEOMETRY") is False
        assert is_entry_gate_pass("") is False

    def test_04_autonomous_readiness_pass_recognized(self):
        from titan.production.verdict_normalizer import is_autonomous_readiness_pass
        assert is_autonomous_readiness_pass("AUTONOMOUS_DEMO_READY_SUPERVISED") is True
        assert is_autonomous_readiness_pass("PASS") is True
        assert is_autonomous_readiness_pass("SUPERVISED_READY") is True
        assert is_autonomous_readiness_pass("AUTONOMOUS_DEMO_BLOCKED_RISK") is False
        assert is_autonomous_readiness_pass("") is False

    def test_05_production_autonomous_pass_recognized(self):
        from titan.production.verdict_normalizer import is_production_autonomous_pass
        assert is_production_autonomous_pass("SUPERVISED_READY") is True
        assert is_production_autonomous_pass("AUTONOMOUS_DEMO_READY_SUPERVISED") is True
        assert is_production_autonomous_pass("PASS") is True
        assert is_production_autonomous_pass("BLOCKED") is False
        assert is_production_autonomous_pass("") is False

    def test_06_case_insensitive(self):
        from titan.production.verdict_normalizer import is_alpha_entry_pass
        assert is_alpha_entry_pass("alpha_regime_entry_pass") is True
        assert is_alpha_entry_pass("pass") is True

    def test_07_no_order_send_in_source(self):
        import re
        src = (REPO_ROOT / "titan" / "production" / "verdict_normalizer.py").read_text()
        assert not re.search(r"\bmt5\.order_send\s*\(", src)
