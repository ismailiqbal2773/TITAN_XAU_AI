"""TITAN XAU AI - Sprint 9.9.3.43 Demo Micro Readiness Safety Tests"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestNoUnsafeExposure:
    def _strip(self, src):
        src = re.sub(r'"""[\s\S]*?"""','""',src); src = re.sub(r"'''[\s\S]*?'''","''",src)
        src = re.sub(r'r"[^"]*"','""',src); src = re.sub(r"r'[^']*'","''",src)
        src = re.sub(r'"(?:[^"\\]|\\.)*"','""',src); src = re.sub(r"'(?:[^'\\]|\\.)*'","''",src)
        lines = []
        for line in src.splitlines():
            idx = line.find("#")
            if idx >= 0: line = line[:idx]
            lines.append(line)
        return "\n".join(lines)

    def test_01_no_order_send_in_readiness_script(self):
        src = (REPO_ROOT / "scripts" / "operator" / "check_demo_micro_readiness.py").read_text()
        code = self._strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_02_no_demo_micro_execute_in_readiness_script(self):
        src = (REPO_ROOT / "scripts" / "operator" / "check_demo_micro_readiness.py").read_text()
        code = self._strip(src)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_03_no_raw_mt5_probe_in_readiness_script(self):
        src = (REPO_ROOT / "scripts" / "operator" / "check_demo_micro_readiness.py").read_text()
        code = self._strip(src)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code)

    def test_04_no_market_execution_adapter_in_readiness_script(self):
        src = (REPO_ROOT / "scripts" / "operator" / "check_demo_micro_readiness.py").read_text()
        code = self._strip(src)
        assert "MT5ExecutionAdapter()" not in code

    def test_05_no_order_execution_command_in_operator_console(self):
        """Operator console must not expose any order execution command."""
        src = (REPO_ROOT / "titan" / "production" / "operator_control_console.py").read_text()
        code = self._strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_06_no_auto_pip_install_in_any_audit_script(self):
        scripts = [
            "scripts/audit/dependency_compatibility_audit.py",
            "scripts/audit/generate_environment_lock_report.py",
            "scripts/audit/model_artifact_compatibility_audit.py",
            "scripts/audit/runtime_self_healing_audit.py",
        ]
        for rel in scripts:
            src = (REPO_ROOT / rel).read_text()
            # Strip docstrings
            code = re.sub(r'"""[\s\S]*?"""', '""', src)
            # Check actual code (not docstrings) for pip install
            assert "subprocess.run" not in code or "pip" not in code.lower(), \
                f"{rel} contains pip install in code"

    def test_07_safety_design_doc_exists(self):
        assert (REPO_ROOT / "docs" / "operator" / "demo_micro_execution_safety_design.md").exists()

    def test_08_safety_design_doc_no_crash_impossible_claim(self):
        src = (REPO_ROOT / "docs" / "operator" / "demo_micro_execution_safety_design.md").read_text()
        # The doc may mention "crash impossible" only in negation context
        lower = src.lower()
        if "crash impossible" in lower:
            idx = lower.find("crash impossible")
            context = lower[max(0, idx-30):idx]
            assert "not" in context, "Safety design doc claims crash impossible without negation"
        if "never crashes" in lower:
            idx = lower.find("never crashes")
            context = lower[max(0, idx-30):idx]
            assert "not" in context, "Safety design doc claims never crashes without negation"

    def test_09_safety_design_doc_has_rules(self):
        src = (REPO_ROOT / "docs" / "operator" / "demo_micro_execution_safety_design.md").read_text()
        assert "max lot 0.01" in src.lower() or "max_lot" in src.lower()
        assert "no martingale" in src.lower()
        assert "no grid" in src.lower()
        assert "no averaging" in src.lower()
        assert "MetaQuotes-Demo only" in src
