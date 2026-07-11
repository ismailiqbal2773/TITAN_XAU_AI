"""TITAN XAU AI - Sprint v2.8.7-P MTF Data Bridge Tests"""
from __future__ import annotations
import sys, re
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestMTFDataBridge:
    def test_audit_script_exists(self):
        assert (REPO_ROOT / "scripts" / "audit" / "mtf_data_bridge_audit.py").exists()
    def test_no_order_send(self):
        src = (REPO_ROOT / "scripts" / "audit" / "mtf_data_bridge_audit.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        assert "order_send(" not in stripped
    def test_no_token(self):
        src = (REPO_ROOT / "scripts" / "audit" / "mtf_data_bridge_audit.py").read_text()
        assert "create_local_operator_execution_token" not in src
