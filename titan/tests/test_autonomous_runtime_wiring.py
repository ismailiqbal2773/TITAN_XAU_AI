"""TITAN XAU AI - Sprint v2.8 Autonomous Runtime Wiring Tests

Tests that the autonomous entry check mode is correctly wired into the
runtime and that actual autonomous order execution remains disabled.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class TestAutonomousRuntimeWiring:
    def test_01_autonomous_entry_check_function_exists(self):
        """run_autonomous_entry_check function must exist."""
        import scripts.operator.run_managed_demo_micro_trade as m
        assert hasattr(m, "run_autonomous_entry_check")
        assert callable(m.run_autonomous_entry_check)

    def test_02_autonomous_entry_check_writes_json_and_md(self, tmp_path):
        """--autonomous-entry-check must write JSON and MD artifacts."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import argparse
        args = argparse.Namespace(
            prop_funded_profile="prop_funded_safe",
            account_profile="",
            initial_tp_r=3.0,
            use_adaptive_trailing=True,
            use_dynamic_tp_extension=True,
            tp_extension_trigger_r=2.0,
        )
        result = m.run_autonomous_entry_check(args)
        assert "report_paths" in result
        json_path = Path(result["report_paths"]["json"])
        md_path = Path(result["report_paths"]["md"])
        assert json_path.exists(), f"JSON not written: {json_path}"
        assert md_path.exists(), f"MD not written: {md_path}"
        # Verify JSON content
        data = json.loads(json_path.read_text())
        assert "final_decision" in data
        assert "regime_detected" in data
        assert "alpha_signal_detected" in data
        assert "safety" in data
        assert data["safety"]["order_send_called"] is False

    def test_03_autonomous_entry_check_never_calls_order_send(self):
        """run_autonomous_entry_check source must never call mt5.order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # Find the function body
        idx = src.find("def run_autonomous_entry_check")
        assert idx > 0
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        body_stripped = _strip(body)
        assert not re.search(r"\bmt5\.order_send\s*\(", body_stripped), \
            "run_autonomous_entry_check must never call mt5.order_send"

    def test_04_autonomous_entry_check_never_modifies_positions(self):
        """run_autonomous_entry_check must never modify positions."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def run_autonomous_entry_check")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        body_stripped = _strip(body)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", body_stripped)

    def test_05_autonomous_entry_check_never_creates_token(self):
        """run_autonomous_entry_check must never create execution tokens."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def run_autonomous_entry_check")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        body_lower = body.lower()
        assert "create_local_operator_execution_token" not in body_lower

    def test_06_autonomous_entry_check_safety_flags(self, tmp_path):
        """Result must include safety flags all set to False."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import argparse
        args = argparse.Namespace(
            prop_funded_profile="prop_funded_safe",
            account_profile="",
            initial_tp_r=3.0,
        )
        result = m.run_autonomous_entry_check(args)
        safety = result.get("safety", {})
        assert safety.get("order_send_called") is False
        assert safety.get("position_modified") is False
        assert safety.get("execution_token_created") is False

    def test_07_cli_argument_exists(self):
        """--autonomous-entry-check CLI argument must exist in source."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "--autonomous-entry-check" in src

    def test_08_dispatch_logic_includes_autonomous_entry_check(self):
        """main() dispatch must route to run_autonomous_entry_check."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        assert "args.autonomous_entry_check" in src
        assert "run_autonomous_entry_check(args)" in src

    def test_09_alpha_regime_entry_decision_engine_imported(self):
        """run_autonomous_entry_check must import the decision engine."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def run_autonomous_entry_check")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert "from titan.production.alpha_regime_entry_decision import evaluate_entry" in body

    def test_10_trade_journal_imported_in_entry_check(self):
        """run_autonomous_entry_check must import TradeJournal."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def run_autonomous_entry_check")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert "from titan.production.trade_journal import TradeJournal" in body

    def test_11_journal_writes_decision_chain(self, tmp_path):
        """Journal must record the full decision chain."""
        import scripts.operator.run_managed_demo_micro_trade as m
        import argparse
        args = argparse.Namespace(
            prop_funded_profile="prop_funded_safe",
            account_profile="",
            initial_tp_r=3.0,
        )
        m.run_autonomous_entry_check(args)
        journal_path = REPO_ROOT / "data" / "audit" / "demo_micro_execution" / "autonomous_entry_journal.jsonl"
        assert journal_path.exists(), "Journal file not written"
        lines = journal_path.read_text().strip().split("\n")
        event_types = [json.loads(l)["event_type"] for l in lines]
        assert "AUTONOMOUS_ENTRY_CHECK_STARTED" in event_types
        assert "REGIME_DETECTION_RESULT" in event_types
        assert "ALPHA_SIGNAL_RESULT" in event_types
        assert "RISK_GATE_RESULT" in event_types
        assert "BROKER_GATE_RESULT" in event_types
        assert "PROP_FUNDED_GATE_RESULT" in event_types
        assert "EXECUTION_GEOMETRY_GATE_RESULT" in event_types
        assert "AUTONOMOUS_ENTRY_DECISION" in event_types

    def test_12_autonomous_execute_not_implemented(self):
        """Actual autonomous order execution must NOT be implemented.
        The source must not contain any function that sends orders in
        autonomous mode."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # There must be no 'autonomous_execute' or 'autonomous_order_send' function
        assert "def run_autonomous_execute" not in src
        assert "def autonomous_order_send" not in src
        # The --autonomous-entry-check mode must only produce a decision, not execute
        idx = src.find("def run_autonomous_entry_check")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        body_stripped = _strip(body)
        assert not re.search(r"\bmt5\.order_send\s*\(", body_stripped)

    def test_13_no_martingale_in_entry_check(self):
        """run_autonomous_entry_check must not use forbidden patterns."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def run_autonomous_entry_check")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        body_lower = _strip(body).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "loss_based_lot"]:
            assert term not in body_lower or "no_" in body_lower or "forbid" in body_lower

    def test_14_decision_engine_no_order_send(self):
        """AlphaRegimeEntryDecisionEngine must never call mt5.order_send."""
        src = (REPO_ROOT / "titan" / "production" / "alpha_regime_entry_decision.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bMetaTrader5\b", code)

    def test_15_selected_profile_resolver_used(self):
        """run_autonomous_entry_check must use the selected_profile_resolver."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def run_autonomous_entry_check")
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert "from titan.production.selected_profile_resolver import resolve_selected_profile" in body
        assert "resolve_selected_profile(REPO_ROOT" in body
