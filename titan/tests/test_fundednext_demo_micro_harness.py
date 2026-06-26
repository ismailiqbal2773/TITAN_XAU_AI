"""
TITAN XAU AI — Sprint 9.9 FundedNext Demo Micro Harness Tests
"""
from __future__ import annotations
import asyncio, json, os, pytest
from pathlib import Path
from scripts.audit.fundednext_demo_micro_full_cycle import run, parse_args


class TestDryArmCheck:
    def test_dry_check_sends_no_order(self):
        import sys
        old = sys.argv
        sys.argv = ["harness", "--mode", "DRY_ARM_CHECK_ONLY"]
        from scripts.audit.fundednext_demo_micro_full_cycle import parse_args
        args = parse_args()
        sys.argv = old
        asyncio.run(run(args))
        # Read report
        report_path = Path("data/audit/demo_micro/demo_micro_report.json")
        assert report_path.exists()
        with open(report_path) as f:
            r = json.load(f)
        assert r["order_send_called"] is False
        assert r["mode"] == "DRY_ARM_CHECK_ONLY"

    def test_dry_check_does_not_require_arm(self):
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)
        import sys
        old = sys.argv
        sys.argv = ["harness", "--mode", "DRY_ARM_CHECK_ONLY"]
        from scripts.audit.fundednext_demo_micro_full_cycle import parse_args
        args = parse_args()
        sys.argv = old
        asyncio.run(run(args))  # should not crash

    def test_execute_requires_arm(self):
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)
        import sys
        old = sys.argv
        sys.argv = ["harness", "--mode", "DEMO_MICRO_EXECUTE"]
        from scripts.audit.fundednext_demo_micro_full_cycle import parse_args
        args = parse_args()
        sys.argv = old
        asyncio.run(run(args))
        report_path = Path("data/audit/demo_micro/demo_micro_report.json")
        with open(report_path) as f:
            r = json.load(f)
        assert r["final_verdict"] == "DEMO_MICRO_BLOCKED"
        assert "Arm token" in r.get("reason", "")

    def test_execute_blocked_without_demo(self):
        os.environ["TITAN_DEMO_MICRO_ARMED"] = "1"
        import sys
        old = sys.argv
        sys.argv = ["harness", "--mode", "DEMO_MICRO_EXECUTE"]
        from scripts.audit.fundednext_demo_micro_full_cycle import parse_args
        args = parse_args()
        sys.argv = old
        asyncio.run(run(args))
        report_path = Path("data/audit/demo_micro/demo_micro_report.json")
        with open(report_path) as f:
            r = json.load(f)
        # On Linux without MT5, should be blocked
        assert r["final_verdict"] in ("DEMO_MICRO_BLOCKED", "DEMO_MANUAL_REVIEW_REQUIRED")
        os.environ.pop("TITAN_DEMO_MICRO_ARMED", None)

    def test_no_real_live_execution_possible(self):
        import titan.production.virtual_position_ledger as vpl
        import inspect
        src = inspect.getsource(vpl)
        assert "mt5.order_send" not in src

    def test_demo_micro_config_disabled_by_default(self):
        import yaml
        from pathlib import Path
        REPO_ROOT = Path(__file__).resolve().parents[2]
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["demo_micro"]["enabled"] is False

    def test_dry_run_unchanged_by_default(self):
        import yaml
        from pathlib import Path
        REPO_ROOT = Path(__file__).resolve().parents[2]
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["dry_run"] is True
        assert cfg["runtime"]["live_trading"] is False

    def test_max_lot_config_0_01(self):
        import yaml
        from pathlib import Path
        REPO_ROOT = Path(__file__).resolve().parents[2]
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["demo_micro"]["max_lot"] <= 0.01

    def test_max_open_positions_1(self):
        import yaml
        from pathlib import Path
        REPO_ROOT = Path(__file__).resolve().parents[2]
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["demo_micro"]["max_open_positions"] == 1

    def test_force_close_on_end_true(self):
        import yaml
        from pathlib import Path
        REPO_ROOT = Path(__file__).resolve().parents[2]
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["demo_micro"]["force_close_on_end"] is True

    def test_report_json_generated(self):
        import sys
        old = sys.argv
        sys.argv = ["harness", "--mode", "DRY_ARM_CHECK_ONLY"]
        from scripts.audit.fundednext_demo_micro_full_cycle import parse_args
        args = parse_args()
        sys.argv = old
        asyncio.run(run(args))
        assert Path("data/audit/demo_micro/demo_micro_report.json").exists()

    def test_report_md_generated(self):
        assert Path("data/audit/demo_micro/demo_micro_report.md").exists()

    def test_no_production_live_path_changed(self):
        import yaml
        from pathlib import Path
        REPO_ROOT = Path(__file__).resolve().parents[2]
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["live_trading"] is False
