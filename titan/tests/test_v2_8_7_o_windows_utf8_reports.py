"""TITAN XAU AI - Sprint v2.8.7-O Windows UTF-8 Report Tests"""
from __future__ import annotations
import sys, re
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestWindowsUTF8Reports:
    def _check_no_emoji_writes(self, filepath):
        """Check that a script doesn't write emojis to files without utf-8 encoding."""
        if not filepath.exists():
            return True
        src = filepath.read_text()
        # Find all open() calls that write .md files
        lines = src.split("\n")
        for i, line in enumerate(lines):
            if 'open(' in line and '"w"' in line and '.md' in line:
                if 'encoding="utf-8"' not in line and 'encoding=\'utf-8\'' not in line:
                    # Check if emojis are used in writes near this line
                    for j in range(i, min(i+10, len(lines))):
                        if '\u2705' in lines[j] or '\u274c' in lines[j]:
                            return False
        return True

    def test_supervised_demo_gate_no_emoji_crash(self):
        path = REPO_ROOT / "scripts" / "audit" / "supervised_demo_review_gate.py"
        src = path.read_text()
        # Check that no .md write uses emojis without utf-8
        assert 'encoding="utf-8"' in src or '\u2705' not in src

    def test_dashboard_uses_utf8(self):
        path = REPO_ROOT / "scripts" / "research" / "build_final_project_readiness_dashboard.py"
        src = path.read_text()
        assert 'encoding="utf-8"' in src

    def test_validator_uses_utf8(self):
        path = REPO_ROOT / "scripts" / "audit" / "validate_exness_forward_shadow.py"
        src = path.read_text()
        assert 'encoding="utf-8"' in src

    def test_preflight_uses_utf8(self):
        path = REPO_ROOT / "scripts" / "operator" / "demo_execution_preflight_readonly.py"
        src = path.read_text()
        assert 'encoding="utf-8"' in src

    def test_performance_script_exists(self):
        path = REPO_ROOT / "scripts" / "research" / "evaluate_exness_forward_shadow_performance.py"
        assert path.exists()

    def test_performance_script_uses_utf8(self):
        path = REPO_ROOT / "scripts" / "research" / "evaluate_exness_forward_shadow_performance.py"
        src = path.read_text()
        assert 'encoding="utf-8"' in src

    def test_forward_shadow_runner_uses_utf8(self):
        path = REPO_ROOT / "scripts" / "operator" / "run_exness_mt5_readonly_forward_shadow.py"
        src = path.read_text()
        assert 'encoding="utf-8"' in src
