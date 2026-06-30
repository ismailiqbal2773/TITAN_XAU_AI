"""TITAN XAU AI - Sprint 9.9.3.43.1 Demo Micro Readiness Environment Gate Tests"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestEnvironmentGate:
    def test_01_readiness_includes_environment_drift_check(self):
        import scripts.operator.check_demo_micro_readiness as dm
        result = dm.run_check()
        assert "environment_drift_gate_verdict" in result["checks"]

    def test_02_readiness_includes_parity_check(self):
        import scripts.operator.check_demo_micro_readiness as dm
        result = dm.run_check()
        assert "model_parity_audit_verdict" in result["checks"]

    def test_03_blocks_when_env_lock_blocked(self, monkeypatch):
        import scripts.operator.check_demo_micro_readiness as dm
        # Mock EnvironmentDriftGate to return BLOCKED
        from titan.production.environment_drift_gate import DriftResult, DriftVerdict
        class MockGate:
            def evaluate(self):
                return DriftResult(verdict=DriftVerdict.ENVIRONMENT_LOCK_BLOCKED, blockers=["test block"])
        # Patch the import
        import titan.production.environment_drift_gate as edg
        old_gate = edg.EnvironmentDriftGate
        edg.EnvironmentDriftGate = MockGate
        try:
            result = dm.run_check()
            assert result["verdict"] == "DEMO_MICRO_BLOCKED"
            assert any("Environment drift" in b for b in result["blockers"])
        finally:
            edg.EnvironmentDriftGate = old_gate

    def test_04_blocks_when_parity_fail(self, monkeypatch):
        import scripts.operator.check_demo_micro_readiness as dm
        # Mock parity audit to return FAIL
        import scripts.audit.model_prediction_parity_audit as pa
        old_run = pa.run_parity_audit
        pa.run_parity_audit = lambda: {"verdict": "MODEL_PARITY_FAIL", "blockers": ["test fail"], "warnings": []}
        try:
            result = dm.run_check()
            assert result["verdict"] == "DEMO_MICRO_BLOCKED"
            assert any("parity" in b.lower() for b in result["blockers"])
        finally:
            pa.run_parity_audit = old_run

    def test_05_allows_model_parity_not_available(self):
        """MODEL_PARITY_NOT_AVAILABLE should be approved (not blocked)."""
        import scripts.operator.check_demo_micro_readiness as dm
        assert "MODEL_PARITY_NOT_AVAILABLE" in dm.APPROVED_WARNINGS

    def test_06_no_order_send_in_readiness_script(self):
        src = (REPO_ROOT / "scripts" / "operator" / "check_demo_micro_readiness.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)

    def test_07_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "check_demo_micro_readiness.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_08_no_raw_mt5_probe(self):
        src = (REPO_ROOT / "scripts" / "operator" / "check_demo_micro_readiness.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code)

    def test_09_no_market_execution_adapter(self):
        src = (REPO_ROOT / "scripts" / "operator" / "check_demo_micro_readiness.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert "MT5ExecutionAdapter()" not in code
