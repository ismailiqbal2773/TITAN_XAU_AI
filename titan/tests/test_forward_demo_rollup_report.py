"""TITAN XAU AI - Forward Demo Rollup Report Tests (Sprint 9.9.3.45.11)"""
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
    return src


def _write_daily(dir_path: Path, date_str: str, verdict: str,
                 trades: int = 1, closed: int = 1,
                 net_pnl: float = 1.0,
                 max_daily_dd: float = 0.005,
                 total_dd: float = 0.005,
                 broker_score: float = 7.0,
                 spread_notes: str = "tight spreads",
                 journal_integrity: str = "OK",
                 risk_events: list | None = None) -> Path:
    """Write a daily_report_YYYYMMDD.json file in dir_path."""
    p = dir_path / f"daily_report_{date_str}.json"
    p.write_text(json.dumps({
        "date": date_str,
        "profile": "prop_funded_safe",
        "account_server": "metaquotes-demo",
        "account_type": "demo",
        "broker_score": broker_score,
        "open_positions_count": 0,
        "titan_magic_positions_count": 0,
        "trades_today": trades,
        "closed_trades_today": closed,
        "net_pnl_today": net_pnl,
        "max_daily_dd": max_daily_dd,
        "total_dd": total_dd,
        "spread_slippage_notes": spread_notes,
        "rejected_signals": 0,
        "risk_events": risk_events or [],
        "journal_integrity": journal_integrity,
        "receipt_integrity": "OK",
        "no_martingale": True,
        "no_grid": True,
        "no_averaging": True,
        "no_loss_multiplier": True,
        "forward_day_verdict": verdict,
        "blockers": [],
        "warnings": [],
        "ok_checks": [],
        "safety": {
            "order_send_called": False,
            "position_modified": False,
            "no_martingale": True,
        },
    }), encoding="utf-8")
    return p


class TestForwardDemoRollupReport:
    def test_01_module_imports(self):
        """Module must import cleanly and expose run_rollup + main."""
        import scripts.audit.forward_demo_rollup_report as mod
        assert hasattr(mod, "run_rollup")
        assert hasattr(mod, "main")
        assert mod.CONTINUE_30_DAY_DEMO == "CONTINUE_30_DAY_DEMO"
        assert mod.EXTEND_7_DAY_OBSERVATION == "EXTEND_7_DAY_OBSERVATION"
        assert mod.FIX_BLOCKERS_BEFORE_CONTINUE == "FIX_BLOCKERS_BEFORE_CONTINUE"

    def test_02_returns_result(self, tmp_path):
        """run_rollup() must return a result dict with all expected fields."""
        import scripts.audit.forward_demo_rollup_report as mod
        result = mod.run_rollup(input_dir=tmp_path, output_dir=tmp_path)
        assert isinstance(result, dict)
        for field in ["days_observed", "pass_days", "warn_days", "blocked_days",
                      "total_trades", "net_pnl", "win_rate", "pf",
                      "max_daily_dd", "max_total_dd", "avg_spread_slippage",
                      "risk_events_count", "journal_integrity_status",
                      "broker_stability_status", "recommendation",
                      "completed", "days_remaining", "safety"]:
            assert field in result, f"missing field {field!r}"
        assert "json_path" in result
        assert "md_path" in result

    def test_03_verdicts_supported(self):
        """Module source must declare all three recommendations."""
        import scripts.audit.forward_demo_rollup_report as mod
        src = inspect.getsource(mod)
        assert "CONTINUE_30_DAY_DEMO" in src
        assert "EXTEND_7_DAY_OBSERVATION" in src
        assert "FIX_BLOCKERS_BEFORE_CONTINUE" in src

    def test_04_does_not_complete_before_7_days(self, tmp_path):
        """With < 7 daily reports, completed must be False and recommendation
        must be EXTEND_7_DAY_OBSERVATION (when no blockers)."""
        import scripts.audit.forward_demo_rollup_report as mod
        # Write 5 PASS days
        for i in range(1, 6):
            _write_daily(tmp_path, f"2026070{i}", "FORWARD_DAY_PASS")
        result = mod.run_rollup(input_dir=tmp_path, output_dir=tmp_path)
        assert result["days_observed"] == 5
        assert result["completed"] is False
        assert result["days_remaining"] == 2
        assert result["recommendation"] == mod.EXTEND_7_DAY_OBSERVATION

    def test_05_recommends_continue_only_if_no_blocked_days(self, tmp_path):
        """With 7+ days AND 0 blocked days AND integrity OK, recommendation
        must be CONTINUE_30_DAY_DEMO. Any blocked day must force
        FIX_BLOCKERS_BEFORE_CONTINUE."""
        import scripts.audit.forward_demo_rollup_report as mod
        # 7 PASS days -> CONTINUE_30_DAY_DEMO
        for i in range(1, 8):
            _write_daily(tmp_path, f"2026070{i}", "FORWARD_DAY_PASS")
        result = mod.run_rollup(input_dir=tmp_path, output_dir=tmp_path)
        assert result["days_observed"] == 7
        assert result["completed"] is True
        assert result["blocked_days"] == 0
        assert result["recommendation"] == mod.CONTINUE_30_DAY_DEMO

        # Now add a blocked day -> FIX_BLOCKERS_BEFORE_CONTINUE
        _write_daily(tmp_path, "20260708", "FORWARD_DAY_BLOCKED")
        result2 = mod.run_rollup(input_dir=tmp_path, output_dir=tmp_path)
        assert result2["blocked_days"] == 1
        assert result2["recommendation"] == mod.FIX_BLOCKERS_BEFORE_CONTINUE

    def test_06_no_order_send(self):
        """Module source must never call mt5.order_send."""
        import scripts.audit.forward_demo_rollup_report as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\border_send\s*\(", code)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_07_no_martingale(self):
        """Module source must never reference forbidden recovery patterns."""
        import scripts.audit.forward_demo_rollup_report as mod
        src = inspect.getsource(mod)
        code = _strip(src).lower()
        for legit in ("no_martingale", "no_grid", "no_averaging",
                      "no_loss_multiplier"):
            code = code.replace(legit, "")
        for term in ["martingale", "grid_trade", "averaging_down",
                     "loss_based_lot", "loss_multiplier"]:
            assert term not in code, f"forbidden term {term!r} present in module"

    def test_08_writes_json_and_md(self, tmp_path):
        """Both JSON and MD files must be written with expected content."""
        import scripts.audit.forward_demo_rollup_report as mod
        for i in range(1, 8):
            _write_daily(tmp_path, f"2026070{i}", "FORWARD_DAY_PASS")
        result = mod.run_rollup(input_dir=tmp_path, output_dir=tmp_path)
        json_path = Path(result["json_path"])
        md_path = Path(result["md_path"])
        assert json_path.exists()
        assert md_path.exists()
        assert json_path.name == "forward_demo_rollup_report.json"
        assert md_path.name == "forward_demo_rollup_report.md"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["recommendation"] == mod.CONTINUE_30_DAY_DEMO
        assert data["safety"]["order_send_called"] is False
        assert data["no_martingale"] is True
        md = md_path.read_text(encoding="utf-8")
        assert "Forward Demo Rollup Report" in md
        assert "CONTINUE_30_DAY_DEMO" in md

    def test_09_no_position_modification(self):
        """Module source must never call mt5.order_modify / positions_modify."""
        import scripts.audit.forward_demo_rollup_report as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)

    def test_10_aggregates_metrics_correctly(self, tmp_path):
        """Rollup must aggregate trades, net_pnl, win_rate, pf correctly."""
        import scripts.audit.forward_demo_rollup_report as mod
        # 3 winning days, 1 losing day
        _write_daily(tmp_path, "20260701", "FORWARD_DAY_PASS",
                     trades=2, closed=2, net_pnl=10.0)
        _write_daily(tmp_path, "20260702", "FORWARD_DAY_PASS",
                     trades=1, closed=1, net_pnl=5.0)
        _write_daily(tmp_path, "20260703", "FORWARD_DAY_PASS",
                     trades=1, closed=1, net_pnl=3.0)
        _write_daily(tmp_path, "20260704", "FORWARD_DAY_WARN",
                     trades=1, closed=1, net_pnl=-4.0)
        result = mod.run_rollup(input_dir=tmp_path, output_dir=tmp_path)
        assert result["days_observed"] == 4
        assert result["total_trades"] == 5
        assert result["closed_trades"] == 5
        assert result["net_pnl"] == round(10.0 + 5.0 + 3.0 - 4.0, 4)
        assert result["win_rate"] == round(3 / 4, 4)
        # gross_profit = 18, gross_loss = -4, pf = 4.5
        assert result["gross_profit"] == 18.0
        assert result["gross_loss"] == -4.0
        assert result["pf"] == round(18.0 / 4.0, 4)
        # 4 days observed < 7 -> not completed -> EXTEND
        assert result["recommendation"] == mod.EXTEND_7_DAY_OBSERVATION

    def test_11_fix_blockers_when_journal_degraded(self, tmp_path):
        """DEGRADED journal integrity must force FIX_BLOCKERS_BEFORE_CONTINUE."""
        import scripts.audit.forward_demo_rollup_report as mod
        for i in range(1, 8):
            _write_daily(tmp_path, f"2026070{i}", "FORWARD_DAY_PASS",
                         journal_integrity="DEGRADED")
        result = mod.run_rollup(input_dir=tmp_path, output_dir=tmp_path)
        assert result["journal_integrity_status"] == "DEGRADED"
        assert result["recommendation"] == mod.FIX_BLOCKERS_BEFORE_CONTINUE

    def test_12_empty_dir_extends_observation(self, tmp_path):
        """An empty daily report dir must produce EXTEND_7_DAY_OBSERVATION."""
        import scripts.audit.forward_demo_rollup_report as mod
        result = mod.run_rollup(input_dir=tmp_path, output_dir=tmp_path)
        assert result["days_observed"] == 0
        assert result["completed"] is False
        assert result["days_remaining"] == 7
        # 0 days observed -> no blockers, not completed -> EXTEND
        assert result["recommendation"] == mod.EXTEND_7_DAY_OBSERVATION

    def test_13_safety_fingerprint_always_present(self, tmp_path):
        """The safety fingerprint must always be present on the result."""
        import scripts.audit.forward_demo_rollup_report as mod
        result = mod.run_rollup(input_dir=tmp_path, output_dir=tmp_path)
        assert result["safety"]["order_send_called"] is False
        assert result["safety"]["position_modified"] is False
        assert result["safety"]["no_martingale"] is True
