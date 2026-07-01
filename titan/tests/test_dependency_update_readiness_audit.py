"""
TITAN XAU AI — Dependency Update Readiness Audit Tests
========================================================

8+ tests covering:
  - Audit produces a verdict in the valid set
  - Audit does not import MetaTrader5 or call order_send
  - Audit does not run pip install
  - Audit does not contain banned betting logic
  - Audit reports DEPENDENCY_READY (no blockers) on the current repo
  - Audit reads the policy YAML correctly
  - JSON / MD reports are written correctly
  - Lockfile is present, pinned, and has no floating entries
  - Python version meets the minimum requirement

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'r"[^"]*"', '""', src)
    src = re.sub(r"r'[^']*'", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    out = []
    for line in src.splitlines():
        idx = line.find("#")
        if idx >= 0:
            line = line[:idx]
        out.append(line)
    return "\n".join(out)


class TestDependencyAudit:
    def test_01_verdict_in_valid_set(self):
        import scripts.audit.dependency_update_readiness_audit as mod
        result = mod.run_audit()
        assert result["verdict"] in (
            mod.DEPENDENCY_READY,
            mod.DEPENDENCY_NEEDS_UPDATE,
            mod.DEPENDENCY_BLOCKED,
        )

    def test_02_no_metatrader5_import(self):
        import scripts.audit.dependency_update_readiness_audit as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        # No actual `import MetaTrader5` or `from MetaTrader5` statement.
        assert not re.search(r"^\s*import\s+MetaTrader5\b", code, flags=re.MULTILINE)
        assert not re.search(r"^\s*from\s+MetaTrader5\b", code, flags=re.MULTILINE)

    def test_03_no_order_send(self):
        import scripts.audit.dependency_update_readiness_audit as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bMetaTrader5\.order_send\s*\(", code)

    def test_04_no_pip_install_in_audit(self):
        """The audit must NEVER run pip install (it only *detects* pip-install
        patterns in other files)."""
        import scripts.audit.dependency_update_readiness_audit as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        # No actual `subprocess.run([... "pip" ... "install" ... "-U"])` call.
        # The detection *regex literals* are stripped away by _strip(), so any
        # remaining `pip install -U` would be an actual call — which is forbidden.
        assert not re.search(r"subprocess\.run\s*\(\s*\[[^\]]*pip[^\]]*install", code)
        assert not re.search(r"os\.system\s*\(\s*['\"`].*pip\s+install", code)

    def test_05_no_banned_betting_logic_in_audit(self):
        """The audit may *detect* banned patterns via regex string literals,
        but must NOT implement them as actual code logic."""
        import scripts.audit.dependency_update_readiness_audit as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        low = code.lower()
        forbidden_patterns = [
            r"def\s+apply_martingale",
            r"def\s+apply_grid",
            r"def\s+average_down",
            r"\blot\s*\*\s*2\b",
            r"position_size\s*\*=\s*2\b",
            r"(?<!no_)\bloss_based_lot_multiplier\s*=",
            r"(?<!no_)\bmartingale_multiplier\s*=",
        ]
        for pat in forbidden_patterns:
            assert not re.search(pat, low), (
                f"audit implements banned betting pattern: {pat}"
            )

    def test_06_json_writes(self, tmp_path):
        import scripts.audit.dependency_update_readiness_audit as mod
        old_d, old_j, old_m = mod.OUTPUT_DIR, mod.JSON_PATH, mod.MD_PATH
        mod.OUTPUT_DIR = tmp_path
        mod.JSON_PATH = tmp_path / "dep.json"
        mod.MD_PATH = tmp_path / "dep.md"
        try:
            result = mod.run_audit()
            report = mod.write_report(result)
            assert Path(report["json_path"]).exists()
            with open(report["json_path"]) as f:
                data = json.load(f)
            assert "verdict" in data
            assert "python_version" in data
            assert "pinned_count" in data
        finally:
            mod.OUTPUT_DIR, mod.JSON_PATH, mod.MD_PATH = old_d, old_j, old_m

    def test_07_md_writes_and_contains_design_note(self, tmp_path):
        import scripts.audit.dependency_update_readiness_audit as mod
        old_d, old_j, old_m = mod.OUTPUT_DIR, mod.JSON_PATH, mod.MD_PATH
        mod.OUTPUT_DIR = tmp_path
        mod.JSON_PATH = tmp_path / "dep.json"
        mod.MD_PATH = tmp_path / "dep.md"
        try:
            result = mod.run_audit()
            report = mod.write_report(result)
            md = Path(report["md_path"]).read_text()
            assert "Dependency Update Readiness Audit" in md
            assert "pinned" in md.lower()
            # The MD must explicitly state the audit NEVER calls order_send
            # and NEVER runs pip install.
            assert "order_send" in md
            assert "pip install" in md
        finally:
            mod.OUTPUT_DIR, mod.JSON_PATH, mod.MD_PATH = old_d, old_j, old_m

    def test_08_audit_reports_ready_on_current_repo(self):
        """The current repository must pass the dependency audit
        (DEPENDENCY_READY)."""
        import scripts.audit.dependency_update_readiness_audit as mod
        result = mod.run_audit()
        assert result["verdict"] == mod.DEPENDENCY_READY, (
            f"Expected DEPENDENCY_READY, got {result['verdict']}. "
            f"Blockers: {result['blockers']}"
        )

    def test_09_policy_yaml_exists_and_parses(self):
        import yaml  # type: ignore
        policy_path = REPO_ROOT / "config" / "dependency_policy.yaml"
        assert policy_path.exists(), "config/dependency_policy.yaml missing"
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        for key in ("python", "pinning", "metaTrader5", "lockfile",
                    "auto_update", "rollback", "banned", "audit"):
            assert key in policy, f"policy missing section: {key}"
        # min_version must be 3.12.0 or later
        min_v = policy["python"]["min_version"]
        assert tuple(int(x) for x in min_v.split(".")) >= (3, 12, 0)

    def test_10_lockfile_present_pinned_and_no_floating(self):
        import scripts.audit.dependency_update_readiness_audit as mod
        result = mod.run_audit()
        assert result["lockfile_present"] is True
        assert result["pinned_count"] > 0
        assert result["floating_count"] == 0, (
            f"requirements-lock.txt has floating entries: "
            f"{result.get('blockers', [])}"
        )

    def test_11_python_version_meets_minimum(self):
        import scripts.audit.dependency_update_readiness_audit as mod
        result = mod.run_audit()
        actual = tuple(int(x) for x in result["python_version"].split("."))
        minimum = tuple(int(x) for x in result["min_python_version"].split("."))
        assert actual >= minimum, (
            f"Python {result['python_version']} < required {result['min_python_version']}"
        )

    def test_12_audit_design_description_present(self):
        import scripts.audit.dependency_update_readiness_audit as mod
        result = mod.run_audit()
        dd = result["design_description"].lower()
        assert "pinned" in dd
        assert "lockfile" in dd
        assert "rollback" in dd
        assert "auto-update" in dd or "auto update" in dd
