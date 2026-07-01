"""
TITAN XAU AI — Broker Score Audit unit tests (Sprint 9.9.3.45.8.5)
=====================================================================

Verifies the ``scripts.audit.broker_score_audit`` module writes both
JSON and Markdown reports, scores multiple brokers, and never invokes
``mt5.order_send``.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit.broker_score_audit import (
    run_audit,
    audit_verdict_for,
    BROKER_SCORING_READY,
    BROKER_SCORING_NEEDS_WORK,
    BROKER_SCORING_BLOCKED,
    ALL_AUDIT_VERDICTS,
)
from titan.production.broker_scoring_engine import (
    BROKER_APPROVED,
    BROKER_CAUTION,
    BROKER_BLOCKED,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────
BROKER_PROFILES_YAML = REPO_ROOT / "config" / "broker_profiles.yaml"
HISTORICAL_CSV = (
    REPO_ROOT
    / "data"
    / "audit"
    / "frozen_balanced_validation"
    / "broker_validation.csv"
)


@pytest.fixture
def audit_output(tmp_path: Path) -> dict:
    """Run the audit against the real config + historical CSV in tmp_path."""
    result = run_audit(
        profiles_path=BROKER_PROFILES_YAML,
        historical_csv=HISTORICAL_CSV if HISTORICAL_CSV.exists() else None,
        output_dir=tmp_path,
    )
    return result


@pytest.fixture
def small_audit_output(tmp_path: Path) -> dict:
    """Run the audit against a tiny in-process YAML for determinism."""
    yaml_doc = {
        "brokers": {
            "alpha_broker": {
                "broker_id": "alpha_broker",
                "name": "Alpha Broker",
                "server": "Alpha-Server",
                "account_type": "live",
                "typical_spread_xauusd": 0.20,
                "max_spread_xauusd": 0.35,
                "commission_per_lot_round_turn": 4.0,
                "typical_slippage_xauusd": 0.015,
                "max_slippage_xauusd": 0.06,
                "swap_long_xauusd_per_lot_per_night": -2.5,
                "swap_short_xauusd_per_lot_per_night": -1.0,
                "contract_size_xauusd": 100,
                "stops_level_points_xauusd": 30,
                "freeze_level_points_xauusd": 0,
                "filling_mode": "ORDER_FILLING_IOC",
                "margin_currency": "USD",
                "min_lot": 0.01,
                "max_lot": 100.0,
                "lot_step": 0.01,
                "leverage_options": [100, 200, 500],
            },
            "omega_broker": {
                "broker_id": "omega_broker",
                "name": "Omega Broker",
                "server": "Omega-Server",
                "account_type": "live",
                "typical_spread_xauusd": 1.2,
                "max_spread_xauusd": 2.0,
                "commission_per_lot_round_turn": 9.0,
                "typical_slippage_xauusd": 0.08,
                "max_slippage_xauusd": 0.15,
                "swap_long_xauusd_per_lot_per_night": -4.5,
                "swap_short_xauusd_per_lot_per_night": -1.8,
                "contract_size_xauusd": 100,
                "stops_level_points_xauusd": 80,
                "freeze_level_points_xauusd": 10,
                "filling_mode": "ORDER_FILLING_RETURN",
                "margin_currency": "USD",
                "min_lot": 0.10,
                "max_lot": 50.0,
                "lot_step": 0.10,
                "leverage_options": [30],
            },
        }
    }
    yaml_path = tmp_path / "broker_profiles.yaml"
    yaml_path.write_text(yaml.safe_dump(yaml_doc), encoding="utf-8")
    return run_audit(
        profiles_path=yaml_path,
        historical_csv=None,
        output_dir=tmp_path,
    )


# ════════════════════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════════════════════
class TestBrokerScoreAudit:
    def test_01_audit_imports(self):
        """run_audit and audit verdicts must import cleanly."""
        assert callable(run_audit)
        assert callable(audit_verdict_for)

    def test_02_audit_returns_result(self, audit_output: dict):
        """run_audit must return a result dict with required keys."""
        assert isinstance(audit_output, dict)
        assert "timestamp_utc" in audit_output
        assert "json_path" in audit_output
        assert "md_path" in audit_output
        assert "brokers" in audit_output
        assert "summary" in audit_output
        assert "audit_verdicts" in audit_output
        assert "table_rows" in audit_output

    def test_03_verdicts_supported(self):
        """All three audit verdicts must be supported."""
        assert set(ALL_AUDIT_VERDICTS) == {
            BROKER_SCORING_READY,
            BROKER_SCORING_NEEDS_WORK,
            BROKER_SCORING_BLOCKED,
        }
        # Engine verdict → audit verdict mapping.
        assert audit_verdict_for(BROKER_APPROVED) == BROKER_SCORING_READY
        assert audit_verdict_for(BROKER_CAUTION) == BROKER_SCORING_NEEDS_WORK
        assert audit_verdict_for(BROKER_BLOCKED) == BROKER_SCORING_BLOCKED

    def test_04_writes_json_and_md(self, audit_output: dict):
        """run_audit must write both JSON and Markdown files."""
        json_path = Path(audit_output["json_path"])
        md_path = Path(audit_output["md_path"])
        assert json_path.exists(), f"JSON not written: {json_path}"
        assert md_path.exists(), f"MD not written: {md_path}"
        # JSON must be parseable.
        with open(json_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        assert "timestamp_utc" in report
        assert "brokers" in report
        assert "table_rows" in report
        assert "summary" in report
        # MD must contain expected sections.
        md_text = md_path.read_text(encoding="utf-8")
        assert "# TITAN XAU AI — Broker Score Report" in md_text
        assert "## Broker Score Table" in md_text
        assert "## Score Components" in md_text

    def test_05_no_mt5_order_send_in_audit_source(self):
        """The audit module source must never call mt5.order_send."""
        import ast
        import scripts.audit.broker_score_audit as mod
        src_path = Path(mod.__file__)
        tree = ast.parse(src_path.read_text(encoding="utf-8"))
        # No MetaTrader5 imports.
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name != "MetaTrader5", (
                        "audit module imports MetaTrader5"
                    )
            elif isinstance(node, ast.ImportFrom):
                assert node.module != "MetaTrader5", (
                    "audit module imports from MetaTrader5"
                )
            elif isinstance(node, ast.Attribute):
                assert node.attr != "order_send", (
                    "audit module calls order_send"
                )

    def test_06_no_martingale_grid_averaging_in_audit_source(self):
        """Audit source must declare safety invariants and never enable
        martingale / grid / averaging strategy primitives."""
        import ast
        import scripts.audit.broker_score_audit as mod
        src = inspect.getsource(mod)
        assert "no_martingale" in src
        assert "no_grid" in src
        assert "no_averaging" in src
        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        forbidden_attrs = {
            "martingale_multiplier",
            "grid_spacing",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_attrs, (
                    f"forbidden attribute {node.attr} found in audit"
                )
            if isinstance(node, ast.FunctionDef):
                assert node.name not in forbidden_attrs, (
                    f"forbidden function {node.name} found in audit"
                )

    def test_07_includes_broker_table(self, audit_output: dict):
        """The audit must produce a table_rows list with broker columns."""
        rows = audit_output["table_rows"]
        assert isinstance(rows, list)
        assert len(rows) >= 4  # 4 YAML brokers + potentially injected
        required_cols = {
            "broker", "broker_id", "score", "verdict", "spread",
            "slippage", "commission", "stop_level", "freeze_level",
            "fill_mode", "net_impact", "prop_compatible", "notes",
        }
        for row in rows:
            assert required_cols.issubset(set(row.keys())), (
                f"row missing columns: {required_cols - set(row.keys())}"
            )

    def test_08_multiple_brokers_scored(self, small_audit_output: dict):
        """Audit must score multiple brokers with distinct verdicts."""
        brokers = small_audit_output["brokers"]
        # At least 2 brokers (alpha_broker + omega_broker from the YAML).
        # With historical_csv=None, no synthetic brokers are injected.
        assert len(brokers) >= 2
        ids = {b["broker_id"] for b in brokers}
        assert "alpha_broker" in ids
        assert "omega_broker" in ids
        # Alpha (perfect) should score higher than Omega (poor).
        alpha = next(b for b in brokers if b["broker_id"] == "alpha_broker")
        omega = next(b for b in brokers if b["broker_id"] == "omega_broker")
        assert alpha["score"] > omega["score"]

    def test_09_audit_includes_exness_from_historical(self, audit_output: dict):
        """If exness is in historical CSV but not YAML, audit must inject it."""
        if not HISTORICAL_CSV.exists():
            pytest.skip("Historical CSV not present")
        ids = {b["broker_id"] for b in audit_output["brokers"]}
        # exness should be either in YAML brokers or injected as synthetic.
        assert "exness" in ids or any(
            "exness" in b.get("broker_name", "").lower() for b in audit_output["brokers"]
        )

    def test_10_audit_summary_counts_match(self, audit_output: dict):
        """Summary counts must add up to total brokers."""
        s = audit_output["summary"]
        total = s["total_brokers"]
        assert s["approved"] + s["needs_work"] + s["blocked"] == total

    def test_11_audit_md_contains_table_header(self, audit_output: dict):
        """The MD file must contain the full table header."""
        md_text = Path(audit_output["md_path"]).read_text(encoding="utf-8")
        # Required columns per spec.
        for col in [
            "Broker", "Score", "Verdict", "Spread", "Slippage",
            "Commission", "StopLevel", "FreezeLevel", "FillMode",
            "NetImpact", "PropCompatible", "Notes",
        ]:
            assert col in md_text, f"MD missing column header: {col}"

    def test_12_audit_safety_invariants_in_json(self, audit_output: dict):
        """The JSON report must include hard invariants flagging no order_send."""
        with open(audit_output["json_path"], "r", encoding="utf-8") as f:
            report = json.load(f)
        assert report["hard_invariants"]["never_calls_mt5_order_send"] is True
        assert report["hard_invariants"]["no_martingale"] is True
        assert report["hard_invariants"]["no_grid"] is True
        assert report["hard_invariants"]["no_averaging"] is True
        assert report["hard_invariants"]["pure_python"] is True
