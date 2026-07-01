"""TITAN XAU AI - Sprint 9.9.3.45.3 Managed Local Environment Detection Tests"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestEnvironmentDetection:
    def test_01_no_hardcoded_non_local_blocker(self):
        """The script must not contain the old hard-coded Z AI refusal."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "Z AI / non-local environment - execute-and-monitor must be run locally by operator" not in src

    def test_02_environment_drift_gate_used(self):
        """The script must use EnvironmentDriftGate for real environment verification."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "EnvironmentDriftGate" in src
        assert "DriftVerdict" in src

    def test_03_token_git_mismatch_blocks(self):
        """Token git mismatch must block with LOCAL_TOKEN_GIT_MISMATCH."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "LOCAL_TOKEN_GIT_MISMATCH" in src

    def test_04_confirmation_missing_blocks(self):
        """Missing confirmation flags must block with CONFIRMATION_MISSING."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "CONFIRMATION_MISSING" in src

    def test_05_mt5_not_available_blocks(self):
        """MT5 not available must block with MT5_NOT_AVAILABLE."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "MT5_NOT_AVAILABLE" in src

    def test_06_account_not_demo_blocks(self):
        """Non-DEMO account must block with ACCOUNT_NOT_DEMO."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "ACCOUNT_NOT_DEMO" in src

    def test_07_broker_not_metaquotes_blocks(self):
        """Non-MetaQuotes-Demo broker must block with BROKER_NOT_METAQUOTES_DEMO."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "BROKER_NOT_METAQUOTES_DEMO" in src

    def test_08_sltp_not_executable_blocks(self):
        """Non-executable SL/TP must block with MANAGED_SLTP_NOT_EXECUTABLE."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "MANAGED_SLTP_NOT_EXECUTABLE" in src

    def test_09_force_close_not_ready_blocks(self):
        """Force-close not ready must block with FORCE_CLOSE_NOT_READY."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "FORCE_CLOSE_NOT_READY" in src

    def test_10_env_info_in_report(self):
        """Report should include env_info with current/frozen platform/python."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "env_info" in src
        assert "current_platform" in src
        assert "frozen_platform" in src
        assert "current_python" in src
        assert "frozen_python" in src

    def test_11_order_send_isolated_to_execute_path(self):
        """order_send must only be inside run_execute_and_monitor or
        _build_modify_applier (Sprint 9.9.3.45.6 apply path), not in
        other functions."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        lines = code.splitlines()
        # Sprint 9.9.3.45.6: order_send is now allowed in
        # _build_modify_applier as well as run_execute_and_monitor
        allowed_functions = {"run_execute_and_monitor", "_build_modify_applier"}
        current_fn = None
        for line in lines:
            m = re.match(r"^def (\w+)", line)
            if m:
                current_fn = m.group(1)
            if "mt5.order_send" in line and current_fn not in allowed_functions:
                pytest.fail(
                    f"order_send found outside run_execute_and_monitor / "
                    f"_build_modify_applier (in {current_fn}): {line.strip()}"
                )

    def test_12_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_13_no_raw_mt5_probe(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code)

    def test_14_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "\u2014" not in src

    def test_15_execute_blocks_without_confirm_managed_trailing(self):
        """Missing --confirm-managed-trailing must block."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        class FakeArgs:
            i_understand_demo_risk = True
            confirm_symbol = "XAUUSD"
            confirm_lot = 0.01
            confirm_broker = "MetaQuotes-Demo"
            confirm_one_order_only = True
            confirm_not_live = True
            confirm_environment_locked = True
            confirm_model_parity_pass = True
            confirm_local_operator = True
            confirm_managed_trailing = False
        result = mt.run_execute_and_monitor(FakeArgs())
        assert result["verdict"] == "MANAGED_DEMO_MICRO_BLOCKED"
        assert any("CONFIRMATION_MISSING" in b for b in result["blockers"])

    def test_16_execute_blocks_without_confirm_local_operator(self):
        """Missing --confirm-local-operator must block."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        class FakeArgs:
            i_understand_demo_risk = True
            confirm_symbol = "XAUUSD"
            confirm_lot = 0.01
            confirm_broker = "MetaQuotes-Demo"
            confirm_one_order_only = True
            confirm_not_live = True
            confirm_environment_locked = True
            confirm_model_parity_pass = True
            confirm_local_operator = False
            confirm_managed_trailing = True
        result = mt.run_execute_and_monitor(FakeArgs())
        assert result["verdict"] == "MANAGED_DEMO_MICRO_BLOCKED"
        assert any("CONFIRMATION_MISSING" in b for b in result["blockers"])
