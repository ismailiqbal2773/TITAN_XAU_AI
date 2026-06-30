"""TITAN XAU AI — Sprint 9.9.3.34 Production Assembly Report Tests"""
from __future__ import annotations
import inspect, json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestReportWriter:
    def test_01_json_writes(self, tmp_path):
        import scripts.audit.production_assembly_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            assert Path(result["json_path"]).exists()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert "verdict" in data
            assert "components" in data
            assert "safety_gates" in data
            assert "execution_permissions" in data
            assert "broker_registry" in data
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_02_md_writes(self, tmp_path):
        import scripts.audit.production_assembly_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            md = Path(result["md_path"]).read_text()
            assert "Production Assembly Report" in md
            assert "Component Inventory" in md
            assert "Safety Gates" in md
            assert "Execution Permissions" in md
            assert "Broker Registry" in md
            assert "no market execution" in md.lower()
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md

    def test_03_no_mt5_in_report_writer(self):
        import re
        import scripts.audit.production_assembly_report as rep
        src = inspect.getsource(rep)
        assert "import MetaTrader5" not in src
        # Check for actual calls, not mentions in strings
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_04_verdict_in_report(self, tmp_path):
        import scripts.audit.production_assembly_report as rep
        old_dir, old_json, old_md = rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH
        rep.OUTPUT_DIR = tmp_path
        rep.JSON_PATH = tmp_path / "report.json"
        rep.MD_PATH = tmp_path / "report.md"
        try:
            result = rep.write_report()
            with open(result["json_path"]) as f:
                data = json.load(f)
            assert data["verdict"] in ("RC_READY", "RC_READY_WITH_WARNINGS", "RC_BLOCKED")
        finally:
            rep.OUTPUT_DIR, rep.JSON_PATH, rep.MD_PATH = old_dir, old_json, old_md
