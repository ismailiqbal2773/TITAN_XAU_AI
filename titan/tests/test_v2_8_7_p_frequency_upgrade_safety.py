"""TITAN XAU AI - Sprint v2.8.7-P Frequency Upgrade Safety Tests"""
from __future__ import annotations
import sys, re, json
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestFrequencyUpgradeSafety:
    def test_backtest_script_exists(self):
        assert (REPO_ROOT / "scripts" / "research" / "backtest_opportunity_frequency_upgrade.py").exists()
    def test_backtest_report_exists(self):
        assert (REPO_ROOT / "data" / "reports" / "opportunity_frequency_upgrade" / "frequency_upgrade_backtest.md").exists()
    def test_comparison_csv_exists(self):
        assert (REPO_ROOT / "data" / "reports" / "opportunity_frequency_upgrade" / "h1_vs_mtf_comparison.csv").exists()
    def test_selected_profile_exists(self):
        assert (REPO_ROOT / "data" / "reports" / "opportunity_frequency_upgrade" / "selected_frequency_profile.yaml").exists()
    def test_competition_profile_exists(self):
        path = REPO_ROOT / "config" / "broker_profiles" / "exness_competition_shadow_profile.yaml"
        assert path.exists()
        import yaml
        with open(path) as f: config = yaml.safe_load(f)
        assert config["mode"] == "shadow_only"
        assert config["live_trading"] is False
        assert config["funded_trading"] is False
        assert config["production_ready"] is False
        assert config["no_order_send"] is True
        assert config["risk_percent_C"] == 0
    def test_verdict_is_valid(self):
        path = REPO_ROOT / "data" / "reports" / "opportunity_frequency_upgrade" / "frequency_upgrade_backtest.json"
        data = json.loads(path.read_text())
        assert data["verdict"] in ["FREQUENCY_UPGRADE_PASS","FREQUENCY_UPGRADE_NEAR_PASS","FREQUENCY_UPGRADE_FAIL","SAFETY_FAIL"]
    def test_no_order_send_in_backtest(self):
        src = (REPO_ROOT / "scripts" / "research" / "backtest_opportunity_frequency_upgrade.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        assert "order_send(" not in stripped
    def test_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "research" / "backtest_opportunity_frequency_upgrade.py").read_text()
        assert "martingale" not in src.lower()
    def test_production_ready_false_in_competition_profile(self):
        import yaml
        path = REPO_ROOT / "config" / "broker_profiles" / "exness_competition_shadow_profile.yaml"
        with open(path) as f: config = yaml.safe_load(f)
        assert config["production_ready"] is False
    def test_dd_limits_enforced(self):
        import yaml
        path = REPO_ROOT / "config" / "broker_profiles" / "exness_competition_shadow_profile.yaml"
        with open(path) as f: config = yaml.safe_load(f)
        assert config["daily_DD_limit"] == 0.03
        assert config["total_DD_limit"] == 0.08
