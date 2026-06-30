"""TITAN XAU AI - Sprint 9.9.3.45 Manage Demo Micro Position Operator Tests"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestManageOperator:
    def test_01_check_only_returns_result(self):
        import scripts.operator.manage_demo_micro_position as mp
        result = mp.run_check_only()
        assert "verdict" in result and result["mode"] == "check_only"

    def test_02_preview_trailing_returns_result(self):
        import scripts.operator.manage_demo_micro_position as mp
        result = mp.run_preview_trailing()
        assert "verdict" in result and result["mode"] == "preview_trailing"

    def test_03_apply_once_blocks_without_confirm(self):
        import scripts.operator.manage_demo_micro_position as mp
        class FakeArgs:
            confirm_local_operator = False
        result = mp.run_apply_once(FakeArgs())
        assert result["verdict"] == "MANAGE_REFUSED"
        assert any("local-operator" in b.lower() for b in result["blockers"])

    def test_04_apply_once_blocks_in_z_ai(self):
        import scripts.operator.manage_demo_micro_position as mp
        class FakeArgs:
            confirm_local_operator = True
        result = mp.run_apply_once(FakeArgs())
        assert result["verdict"] == "MANAGE_REFUSED"

    def test_05_no_order_send_in_preview(self):
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        # order_send may only be in apply-once gated path, not in preview
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        # Check that order_send is not in run_preview_trailing or run_check_only
        # It's OK in run_apply_once (which is gated)
        lines = code.splitlines()
        in_apply = False
        for line in lines:
            if "def run_apply_once" in line:
                in_apply = True
            elif line and not line[0].isspace() and "def " in line:
                in_apply = False
            if "mt5.order_send" in line and not in_apply:
                pytest.fail(f"order_send found outside apply_once: {line.strip()}")

    def test_06_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_07_no_raw_mt5_probe(self):
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code)
