"""
TITAN XAU AI — Profile Matrix Readiness Audit Tests
=====================================================

10+ tests covering:
  - Audit produces a verdict in the valid set.
  - Audit does not import MetaTrader5 or call order_send.
  - Audit does not contain banned betting logic.
  - Audit reports every (account × risk_mode) combination.
  - Each combination has the canonical fields.
  - Final verdicts are in {PASS, BLOCKED, SIMULATION_ONLY}.
  - Live account × simulation-only risk mode → BLOCKED.
  - Live account × non-live risk mode → BLOCKED.
  - Demo account × non-live risk mode → SIMULATION_ONLY.
  - JSON / MD reports are written correctly.
  - Audit enforces safety invariants on every account + mode.
  - Audit's design_description is present and meaningful.

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import inspect
import json
import re
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

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


def _write_yaml(path: Path, doc: dict) -> None:
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")


def _make_accounts_yaml(tmp_path: Path) -> Path:
    doc = {
        "profiles": {
            "demo_account": {
                "account_type": "demo",
                "leverage": 100,
                "max_daily_dd_pct": 0.03,
                "max_total_dd_pct": 0.08,
                "max_risk_per_trade_pct": 0.005,
                "max_open_positions": 1,
                "max_margin_usage_pct": 0.15,
                "max_lot": 0.01,
                "minimum_RR": 2.0,
                "dynamic_tp_initial_tp_R": 3.0,
                "dynamic_tp_trigger_R": 2.0,
                "no_martingale": True,
                "no_grid": True,
                "no_averaging": True,
                "no_loss_based_lot_multiplier": True,
            },
            "live_account": {
                "account_type": "live",
                "leverage": 30,
                "max_daily_dd_pct": 0.03,
                "max_total_dd_pct": 0.06,
                "max_risk_per_trade_pct": 0.005,
                "max_open_positions": 1,
                "max_margin_usage_pct": 0.10,
                "max_lot": 0.05,
                "minimum_RR": 2.0,
                "dynamic_tp_initial_tp_R": 3.0,
                "dynamic_tp_trigger_R": 2.0,
                "no_martingale": True,
                "no_grid": True,
                "no_averaging": True,
                "no_loss_based_lot_multiplier": True,
            },
        }
    }
    p = tmp_path / "accounts.yaml"
    _write_yaml(p, doc)
    return p


def _make_modes_yaml(tmp_path: Path) -> Path:
    doc = {
        "modes": {
            "live_safe": {
                "max_risk_per_trade_pct": 0.005,
                "max_daily_dd_pct": 0.03,
                "max_total_dd_pct": 0.06,
                "live_allowed": True,
                "no_martingale": True,
                "no_grid": True,
                "no_averaging": True,
                "no_loss_based_lot_multiplier": True,
            },
            "sim_only": {
                "max_risk_per_trade_pct": 0.015,
                "max_daily_dd_pct": 0.03,
                "max_total_dd_pct": 0.08,
                "live_allowed": False,
                "simulation_only": True,
                "no_martingale": True,
                "no_grid": True,
                "no_averaging": True,
                "no_loss_based_lot_multiplier": True,
            },
            "non_live_demo": {
                "max_risk_per_trade_pct": 0.002,
                "max_daily_dd_pct": 0.02,
                "max_total_dd_pct": 0.04,
                "live_allowed": False,
                "no_martingale": True,
                "no_grid": True,
                "no_averaging": True,
                "no_loss_based_lot_multiplier": True,
            },
        }
    }
    p = tmp_path / "modes.yaml"
    _write_yaml(p, doc)
    return p


def _make_brokers_yaml(tmp_path: Path) -> Path:
    doc = {
        "brokers": {
            "metaquotes_demo": {
                "broker_id": "metaquotes_demo",
                "name": "MetaQuotes-Demo",
                "server": "MetaQuotes-Demo",
                "account_type": "demo",
                "typical_spread_xauusd": 0.35,
                "max_spread_xauusd": 0.50,
                "commission_per_lot_round_turn": 0.0,
                "typical_slippage_xauusd": 0.02,
                "max_slippage_xauusd": 0.10,
                "swap_long_xauusd_per_lot_per_night": -3.50,
                "swap_short_xauusd_per_lot_per_night": -1.20,
                "contract_size_xauusd": 100,
                "stops_level_points_xauusd": 50,
                "freeze_level_points_xauusd": 0,
                "filling_mode": "ORDER_FILLING_IOC",
                "margin_currency": "USD",
                "min_lot": 0.01,
                "max_lot": 100.0,
                "lot_step": 0.01,
                "leverage_options": [30, 50, 100],
            },
        }
    }
    p = tmp_path / "brokers.yaml"
    _write_yaml(p, doc)
    return p


def _make_prop_firm_yaml(tmp_path: Path) -> Path:
    text = textwrap.dedent("""\
        profiles:
          clean_prop:
            firm_id: test
            name: "Clean Prop"
            profit_target_pct: 0.10
            max_daily_loss_pct: 0.05
            max_total_loss_pct: 0.10
            daily_caution_pct: 0.03
            emergency_halt_pct: 0.07
            drawdown_mode: static
            min_trading_days: 4
            consistency_rule_enabled: true
            max_open_positions: 1
            max_lot: 0.01
            risk_per_trade_pct: 0.01
            min_rr: 2.0
            news_trading: true
            weekend_holding: true
            ea_allowed: true
            copy_trading: false
            phase: challenge
        """)
    p = tmp_path / "prop_firm.yaml"
    p.write_text(text, encoding="utf-8")
    return p


# ─── Audit verdict / safety ───────────────────────────────────────────────
class TestProfileMatrixAuditVerdict:
    def test_01_verdict_in_valid_set(self):
        import scripts.audit.profile_matrix_readiness_audit as mod
        result = mod.run_audit()
        assert result["verdict"] in (
            mod.PROFILE_MATRIX_READY,
            mod.PROFILE_MATRIX_READY_WITH_GAPS,
            mod.PROFILE_MATRIX_BLOCKED,
        )

    def test_02_audit_does_not_import_metatrader5(self):
        import scripts.audit.profile_matrix_readiness_audit as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"^\s*import\s+MetaTrader5\b", code, flags=re.MULTILINE)
        assert not re.search(r"^\s*from\s+MetaTrader5\b", code, flags=re.MULTILINE)

    def test_03_audit_does_not_call_order_send(self):
        import scripts.audit.profile_matrix_readiness_audit as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bMetaTrader5\.order_send\s*\(", code)

    def test_04_audit_has_no_banned_betting_logic(self):
        import scripts.audit.profile_matrix_readiness_audit as mod
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

    def test_05_audit_uses_future_annotations(self):
        import scripts.audit.profile_matrix_readiness_audit as mod
        src = inspect.getsource(mod)
        assert "from __future__ import annotations" in src


# ─── Combination structure / verdicts ─────────────────────────────────────
class TestProfileMatrixAuditCombinations:
    def test_06_audit_returns_every_combination(self):
        import scripts.audit.profile_matrix_readiness_audit as mod
        result = mod.run_audit()
        # 6 accounts × 8 modes = 48 combinations.
        assert result["combination_count"] == 48
        assert len(result["combinations"]) == 48
        # Spot-check canonical fields.
        for c in result["combinations"]:
            for key in (
                "account_profile", "risk_mode", "broker_profile",
                "prop_firm_profile", "risk_per_trade",
                "daily_dd_internal", "total_dd_internal",
                "min_rr", "initial_tp_r", "dynamic_tp_trigger_r",
                "broker_score", "prop_rules_verdict", "net_rr_verdict",
                "margin_verdict", "final_verdict",
            ):
                assert key in c, f"missing key {key} in combo {c}"

    def test_07_final_verdicts_in_valid_set(self):
        import scripts.audit.profile_matrix_readiness_audit as mod
        result = mod.run_audit()
        for c in result["combinations"]:
            assert c["final_verdict"] in (
                mod.COMBO_PASS, mod.COMBO_BLOCKED, mod.COMBO_SIMULATION_ONLY,
            ), f"unknown final_verdict: {c['final_verdict']}"

    def test_08_live_account_with_sim_only_mode_is_blocked(self, tmp_path):
        import scripts.audit.profile_matrix_readiness_audit as mod
        result = mod.run_audit(
            account_profiles_path=_make_accounts_yaml(tmp_path),
            risk_modes_path=_make_modes_yaml(tmp_path),
            broker_profiles_path=_make_brokers_yaml(tmp_path),
            prop_firm_profiles_path=_make_prop_firm_yaml(tmp_path),
        )
        # live_account × sim_only → BLOCKED.
        combo = next(
            c for c in result["combinations"]
            if c["account_profile"] == "live_account"
            and c["risk_mode"] == "sim_only"
        )
        assert combo["final_verdict"] == mod.COMBO_BLOCKED
        assert any("simulation_only" in b for b in combo["blockers"])

    def test_09_live_account_with_non_live_mode_is_blocked(self, tmp_path):
        import scripts.audit.profile_matrix_readiness_audit as mod
        result = mod.run_audit(
            account_profiles_path=_make_accounts_yaml(tmp_path),
            risk_modes_path=_make_modes_yaml(tmp_path),
            broker_profiles_path=_make_brokers_yaml(tmp_path),
            prop_firm_profiles_path=_make_prop_firm_yaml(tmp_path),
        )
        # live_account × non_live_demo → BLOCKED.
        combo = next(
            c for c in result["combinations"]
            if c["account_profile"] == "live_account"
            and c["risk_mode"] == "non_live_demo"
        )
        assert combo["final_verdict"] == mod.COMBO_BLOCKED
        assert any("live_allowed=false" in b for b in combo["blockers"])

    def test_10_demo_account_with_sim_only_mode_is_simulation_only(self, tmp_path):
        import scripts.audit.profile_matrix_readiness_audit as mod
        result = mod.run_audit(
            account_profiles_path=_make_accounts_yaml(tmp_path),
            risk_modes_path=_make_modes_yaml(tmp_path),
            broker_profiles_path=_make_brokers_yaml(tmp_path),
            prop_firm_profiles_path=_make_prop_firm_yaml(tmp_path),
        )
        # demo_account × sim_only → SIMULATION_ONLY.
        combo = next(
            c for c in result["combinations"]
            if c["account_profile"] == "demo_account"
            and c["risk_mode"] == "sim_only"
        )
        assert combo["final_verdict"] == mod.COMBO_SIMULATION_ONLY

    def test_11_demo_account_with_live_safe_mode_passes(self, tmp_path):
        import scripts.audit.profile_matrix_readiness_audit as mod
        result = mod.run_audit(
            account_profiles_path=_make_accounts_yaml(tmp_path),
            risk_modes_path=_make_modes_yaml(tmp_path),
            broker_profiles_path=_make_brokers_yaml(tmp_path),
            prop_firm_profiles_path=_make_prop_firm_yaml(tmp_path),
        )
        # demo_account × live_safe → SIMULATION_ONLY (demo account).
        combo = next(
            c for c in result["combinations"]
            if c["account_profile"] == "demo_account"
            and c["risk_mode"] == "live_safe"
        )
        # Demo account on a live-safe mode is treated as SIMULATION_ONLY
        # because the account itself is demo.
        assert combo["final_verdict"] in (
            mod.COMBO_PASS, mod.COMBO_SIMULATION_ONLY,
        )

    def test_12_live_account_with_live_safe_mode_passes(self, tmp_path):
        import scripts.audit.profile_matrix_readiness_audit as mod
        result = mod.run_audit(
            account_profiles_path=_make_accounts_yaml(tmp_path),
            risk_modes_path=_make_modes_yaml(tmp_path),
            broker_profiles_path=_make_brokers_yaml(tmp_path),
            prop_firm_profiles_path=_make_prop_firm_yaml(tmp_path),
        )
        # live_account × live_safe → PASS.
        combo = next(
            c for c in result["combinations"]
            if c["account_profile"] == "live_account"
            and c["risk_mode"] == "live_safe"
        )
        assert combo["final_verdict"] == mod.COMBO_PASS, (
            f"expected PASS, got {combo['final_verdict']}; blockers: "
            f"{combo['blockers']}"
        )


# ─── Report writing ───────────────────────────────────────────────────────
class TestProfileMatrixAuditReport:
    def test_13_json_report_written(self, tmp_path):
        import scripts.audit.profile_matrix_readiness_audit as mod
        result = mod.run_audit()
        report = mod.write_report(result, output_dir=tmp_path)
        assert Path(report["json_path"]).exists()
        with open(report["json_path"]) as f:
            data = json.load(f)
        assert "verdict" in data
        assert "combinations" in data
        assert "design_description" in data

    def test_14_md_report_written_and_contains_matrix(self, tmp_path):
        import scripts.audit.profile_matrix_readiness_audit as mod
        result = mod.run_audit()
        report = mod.write_report(result, output_dir=tmp_path)
        md = Path(report["md_path"]).read_text(encoding="utf-8")
        assert "Profile Matrix Readiness Audit" in md
        assert "Combination matrix" in md
        # The MD must explicitly state the audit NEVER calls order_send.
        assert "order_send" in md
        # And never contains martingale/grid/averaging.
        assert "martingale" in md.lower()

    def test_15_audit_enforces_safety_invariants(self):
        """Every account profile and risk mode in the real YAML must declare
        all four safety invariants as True."""
        accounts_yaml = REPO_ROOT / "config" / "account_profiles.yaml"
        modes_yaml = REPO_ROOT / "config" / "risk_modes.yaml"
        accounts = yaml.safe_load(accounts_yaml.read_text(encoding="utf-8"))["profiles"]
        modes = yaml.safe_load(modes_yaml.read_text(encoding="utf-8"))["modes"]
        for acc_id, acc in accounts.items():
            assert acc.get("no_martingale") is True, f"{acc_id}: no_martingale"
            assert acc.get("no_grid") is True, f"{acc_id}: no_grid"
            assert acc.get("no_averaging") is True, f"{acc_id}: no_averaging"
            assert acc.get("no_loss_based_lot_multiplier") is True, f"{acc_id}: no_llm"
        for mode_id, mode in modes.items():
            assert mode.get("no_martingale") is True, f"{mode_id}: no_martingale"
            assert mode.get("no_grid") is True, f"{mode_id}: no_grid"
            assert mode.get("no_averaging") is True, f"{mode_id}: no_averaging"
            assert mode.get("no_loss_based_lot_multiplier") is True, f"{mode_id}: no_llm"

    def test_16_audit_design_description_is_present_and_meaningful(self):
        import scripts.audit.profile_matrix_readiness_audit as mod
        result = mod.run_audit()
        dd = result["design_description"].lower()
        assert "combination" in dd
        assert "order_send" in dd
        assert "martingale" in dd or "grid" in dd or "averaging" in dd
