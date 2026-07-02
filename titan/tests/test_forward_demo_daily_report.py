"""TITAN XAU AI - Forward Demo Daily Report Tests (Sprint 9.9.3.45.10)"""
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


class TestForwardDemoDailyReport:
    def test_01_module_imports(self):
        """Module must import cleanly and expose run_daily_report + main."""
        import scripts.audit.forward_demo_daily_report as mod
        assert hasattr(mod, "run_daily_report")
        assert hasattr(mod, "main")
        assert mod.FORWARD_DAY_PASS == "FORWARD_DAY_PASS"
        assert mod.FORWARD_DAY_WARN == "FORWARD_DAY_WARN"
        assert mod.FORWARD_DAY_BLOCKED == "FORWARD_DAY_BLOCKED"

    def test_02_returns_result(self, tmp_path):
        """run_daily_report() must return a result dict with verdict + paths."""
        import scripts.audit.forward_demo_daily_report as mod
        result = mod.run_daily_report(
            input_data={"trades_today": 1, "closed_trades_today": 1,
                        "net_pnl_today": 2.5},
            output_dir=tmp_path,
            date_str="20260702",
        )
        assert isinstance(result, dict)
        assert "forward_day_verdict" in result
        assert "json_path" in result
        assert "md_path" in result
        assert "safety" in result
        assert "date" in result
        assert result["date"] == "20260702"

    def test_03_verdicts_supported(self):
        """Module source must declare all three verdicts."""
        import scripts.audit.forward_demo_daily_report as mod
        src = inspect.getsource(mod)
        assert "FORWARD_DAY_PASS" in src
        assert "FORWARD_DAY_WARN" in src
        assert "FORWARD_DAY_BLOCKED" in src

    def test_04_blocks_real_account(self, tmp_path):
        """Real account (account_type != demo) must produce FORWARD_DAY_BLOCKED."""
        import scripts.audit.forward_demo_daily_report as mod
        result = mod.run_daily_report(
            input_data={"account_type": "real"},
            output_dir=tmp_path,
            date_str="20260702",
        )
        assert result["forward_day_verdict"] == mod.FORWARD_DAY_BLOCKED
        assert any("REAL_ACCOUNT" in b for b in result["blockers"])

    def test_05_blocks_too_many_titan_positions(self, tmp_path):
        """> 1 open TITAN position must produce FORWARD_DAY_BLOCKED."""
        import scripts.audit.forward_demo_daily_report as mod
        result = mod.run_daily_report(
            input_data={
                "account_type": "demo",
                "titan_magic_positions_count": 2,
                "trades_today": 1,
            },
            output_dir=tmp_path,
            date_str="20260702",
        )
        assert result["forward_day_verdict"] == mod.FORWARD_DAY_BLOCKED
        assert any("TOO_MANY_TITAN_POSITIONS" in b for b in result["blockers"])

    def test_06_warns_no_trades(self, tmp_path):
        """No trades today with clean demo state must produce FORWARD_DAY_WARN."""
        import scripts.audit.forward_demo_daily_report as mod
        result = mod.run_daily_report(
            input_data={
                "account_type": "demo",
                "trades_today": 0,
                "closed_trades_today": 0,
            },
            output_dir=tmp_path,
            date_str="20260702",
        )
        assert result["forward_day_verdict"] == mod.FORWARD_DAY_WARN
        assert any("NO_TRADES_TODAY" in w for w in result["warnings"])
        assert not result["blockers"]

    def test_07_passes_clean_demo_day(self, tmp_path):
        """Clean demo day with 1 closed trade must produce FORWARD_DAY_PASS."""
        import scripts.audit.forward_demo_daily_report as mod
        result = mod.run_daily_report(
            input_data={
                "account_type": "demo",
                "profile": "prop_funded_safe",
                "trades_today": 1,
                "closed_trades_today": 1,
                "net_pnl_today": 5.0,
                "max_daily_dd": 0.005,
                "titan_magic_positions_count": 0,
            },
            output_dir=tmp_path,
            date_str="20260702",
        )
        assert result["forward_day_verdict"] == mod.FORWARD_DAY_PASS
        assert not result["blockers"]
        assert not result["warnings"]
        assert Path(result["json_path"]).exists()
        assert Path(result["md_path"]).exists()

    def test_08_no_order_send(self):
        """Module source must never call mt5.order_send."""
        import scripts.audit.forward_demo_daily_report as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\border_send\s*\(", code)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_09_no_martingale(self):
        """Module source must never reference forbidden recovery patterns."""
        import scripts.audit.forward_demo_daily_report as mod
        src = inspect.getsource(mod)
        code = _strip(src).lower()
        # Strip the legitimate safety-field names first.
        for legit in ("no_martingale", "no_grid", "no_averaging",
                      "no_loss_multiplier"):
            code = code.replace(legit, "")
        for term in ["martingale", "grid_trade", "averaging_down",
                     "loss_based_lot", "loss_multiplier"]:
            assert term not in code, f"forbidden term {term!r} present in module"

    def test_10_blocks_aggressive_profile(self, tmp_path):
        """Aggressive profile must produce FORWARD_DAY_BLOCKED."""
        import scripts.audit.forward_demo_daily_report as mod
        result = mod.run_daily_report(
            input_data={
                "account_type": "demo",
                "profile": "aggressive_high_return",
                "trades_today": 1,
                "closed_trades_today": 1,
            },
            output_dir=tmp_path,
            date_str="20260702",
        )
        assert result["forward_day_verdict"] == mod.FORWARD_DAY_BLOCKED
        assert any("AGGRESSIVE_PROFILE" in b for b in result["blockers"])

    def test_11_blocks_risk_limit_breach(self, tmp_path):
        """max_daily_dd above threshold must produce FORWARD_DAY_BLOCKED."""
        import scripts.audit.forward_demo_daily_report as mod
        result = mod.run_daily_report(
            input_data={
                "account_type": "demo",
                "profile": "prop_funded_safe",
                "trades_today": 1,
                "closed_trades_today": 1,
                "max_daily_dd": 0.05,  # 5% > 3% threshold
            },
            output_dir=tmp_path,
            date_str="20260702",
        )
        assert result["forward_day_verdict"] == mod.FORWARD_DAY_BLOCKED
        assert any("RISK_LIMIT" in b for b in result["blockers"])

    def test_12_blocks_old_fallback_trade(self, tmp_path):
        """old_fallback_trade_used=True must produce FORWARD_DAY_BLOCKED."""
        import scripts.audit.forward_demo_daily_report as mod
        result = mod.run_daily_report(
            input_data={
                "account_type": "demo",
                "profile": "prop_funded_safe",
                "trades_today": 1,
                "closed_trades_today": 1,
                "old_fallback_trade_used": True,
            },
            output_dir=tmp_path,
            date_str="20260702",
        )
        assert result["forward_day_verdict"] == mod.FORWARD_DAY_BLOCKED
        assert any("OLD_FALLBACK_TRADE" in b for b in result["blockers"])

    def test_13_writes_json_and_md(self, tmp_path):
        """Both .json and .md files must be written with expected content."""
        import scripts.audit.forward_demo_daily_report as mod
        result = mod.run_daily_report(
            input_data={
                "account_type": "demo",
                "profile": "prop_funded_safe",
                "trades_today": 1,
                "closed_trades_today": 1,
                "net_pnl_today": 3.0,
            },
            output_dir=tmp_path,
            date_str="20260702",
        )
        json_path = Path(result["json_path"])
        md_path = Path(result["md_path"])
        assert json_path.exists()
        assert md_path.exists()
        assert json_path.name == "daily_report_20260702.json"
        assert md_path.name == "daily_report_20260702.md"
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        assert data["forward_day_verdict"] == mod.FORWARD_DAY_PASS
        assert data["safety"]["order_send_called"] is False
        assert data["no_martingale"] is True
        md = md_path.read_text(encoding="utf-8")
        assert "Forward Demo Daily Report" in md
        assert "FORWARD_DAY_PASS" in md

    def test_14_no_position_modification(self):
        """Module source must never call mt5.order_modify / positions_modify."""
        import scripts.audit.forward_demo_daily_report as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"\bmt5\.(order_modify|positions_modify)\s*\(", code)
