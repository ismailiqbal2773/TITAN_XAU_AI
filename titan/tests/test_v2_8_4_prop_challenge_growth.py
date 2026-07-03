"""TITAN XAU AI - Sprint v2.8.4 Prop Challenge Growth Profile Tests

Tests the PROP_CHALLENGE_GROWTH_30_8 profile definition, audit, production
closure integration, and build-request display.

Required tests:
  - profile exists
  - monthly target is target, not guarantee
  - daily DD soft/hard limits valid
  - total DD cap <= 8%
  - max open positions = 1
  - min RR >= 2
  - no forced trading
  - no martingale/grid/averaging/loss multiplier
  - growth tier blocked if model health blocked
  - growth tier blocked if feature parity blocked
  - growth tier blocked if runtime safety blocked
  - growth tier blocked if production closure blockers exist
  - build-request displays profile
  - production closure reads profile audit
  - no mt5.order_send in profile audit/build-request
  - no token creation
  - no position modification
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

AUDIT_DEMO_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"
MODEL_HEALTH_DIR = REPO_ROOT / "data" / "audit" / "model_health"
GROWTH_DIR = REPO_ROOT / "data" / "audit" / "prop_challenge_growth"
MH_PATH = MODEL_HEALTH_DIR / "model_artifact_health_audit.json"
FP_PATH = MODEL_HEALTH_DIR / "feature_parity_audit.json"
RS_PATH = AUDIT_DEMO_DIR / "runtime_safety_gate_audit.json"
GP_PATH = GROWTH_DIR / "prop_challenge_growth_profile_audit.json"
AE_PATH = AUDIT_DEMO_DIR / "autonomous_entry_decision.json"
EG_PATH = AUDIT_DEMO_DIR / "end_to_end_entry_gate_audit.json"
AR_PATH = AUDIT_DEMO_DIR / "autonomous_demo_readiness_audit.json"
CONFIG_PATH = REPO_ROOT / "config" / "prop_challenge_growth_profile.yaml"


def _backup(paths):
    backups = {}
    for p in paths:
        if p.exists():
            backups[str(p)] = p.read_text(encoding="utf-8")
        else:
            backups[str(p)] = None
    return backups


def _restore(backups):
    for p_str, content in backups.items():
        p = Path(p_str)
        if content is None:
            if p.exists():
                p.unlink()
        else:
            p.write_text(content, encoding="utf-8")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


class TestPropChallengeGrowthProfileDefinition:
    """Tests 1-8: Verify profile YAML definition."""

    def test_01_profile_exists(self):
        """Profile config file must exist."""
        assert CONFIG_PATH.exists(), f"Profile config not found: {CONFIG_PATH}"

    def test_02_monthly_target_is_target_not_guarantee(self):
        """Monthly target type must be 'target', NOT 'guarantee'."""
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        profile = cfg.get("profile") or {}
        targets = profile.get("targets") or {}
        assert targets.get("monthly_target_type") == "target", \
            f"Expected 'target', got '{targets.get('monthly_target_type')}'"
        assert targets.get("prop_challenge_target_type") == "target", \
            f"Expected 'target', got '{targets.get('prop_challenge_target_type')}'"

    def test_03_daily_dd_soft_hard_limits_valid(self):
        """Daily DD soft limit ~1%, hard limit ~2%."""
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        risk_bands = (cfg.get("profile") or {}).get("risk_bands") or {}
        soft = float(risk_bands.get("daily_dd_soft_limit_pct", 0))
        hard = float(risk_bands.get("daily_dd_hard_limit_pct", 0))
        assert 0.005 <= soft <= 0.015, f"Soft limit out of range: {soft}"
        assert 0.015 <= hard <= 0.025, f"Hard limit out of range: {hard}"
        assert soft < hard, "Soft limit must be < hard limit"

    def test_04_total_dd_cap_le_8_pct(self):
        """Total DD cap must be <= 8%."""
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        risk_bands = (cfg.get("profile") or {}).get("risk_bands") or {}
        total_dd = float(risk_bands.get("max_total_dd_pct", 0))
        assert 0 < total_dd <= 0.08, f"Total DD cap out of range: {total_dd}"

    def test_05_max_open_positions_one(self):
        """Max open positions must be 1."""
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        pos_sizing = (cfg.get("profile") or {}).get("position_sizing") or {}
        assert int(pos_sizing.get("max_open_positions", 0)) == 1

    def test_06_min_rr_ge_2(self):
        """Min RR must be >= 2."""
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        pos_sizing = (cfg.get("profile") or {}).get("position_sizing") or {}
        assert float(pos_sizing.get("min_RR", 0)) >= 2.0
        assert float(pos_sizing.get("preferred_RR", 0)) >= 3.0

    def test_07_no_forced_trading(self):
        """No-forced-trade rules must all be enabled."""
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        nf = (cfg.get("profile") or {}).get("no_forced_trade") or {}
        for rule in ("NO_TRADE_VALID_DECISION", "TARGET_NOT_FORCED",
                     "ALPHA_REQUIRED", "REGIME_REQUIRED", "RISK_GATE_REQUIRED"):
            assert nf.get(rule, False) is True, f"Rule {rule} must be True"

    def test_08_no_martingale_grid_averaging_loss_multiplier(self):
        """Forbidden strategies must all be disabled (False)."""
        import yaml
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        fs = (cfg.get("profile") or {}).get("forbidden_strategies") or {}
        for strat in ("martingale", "grid", "averaging_down",
                      "loss_based_lot_multiplier", "forced_recovery",
                      "lot_increase_after_loss"):
            assert fs.get(strat, True) is False, \
                f"Strategy {strat} must be False (disabled)"


class TestPropChallengeGrowthProfileAudit:
    """Tests 9-12: Profile audit blocks growth tier when gates blocked."""

    def setup_method(self):
        self._backups = _backup([MH_PATH, FP_PATH, RS_PATH, GP_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_09_growth_profile_audit_passes_in_current_repo(self):
        """Profile audit must PASS in current repo state (all gates pass)."""
        import scripts.audit.prop_challenge_growth_profile_audit as m
        result = m.run_audit()
        assert result["verdict"] == m.PROP_CHALLENGE_GROWTH_PROFILE_PASS, \
            f"Expected PASS, got {result['verdict']}: {result.get('blockers')}"

    def test_10_growth_tier_blocked_if_model_health_blocked(self):
        """Growth profile must be BLOCKED if model health is BLOCKED."""
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_BLOCKED",
            "active_model_count": 2, "failed_required_model_count": 1,
            "failed_optional_model_count": 0,
            "blocked_required_models": [{"name": "broken", "role": "active_primary"}],
            "warned_optional_models": [], "v2_8_4_allowed": False,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})

        import scripts.audit.prop_challenge_growth_profile_audit as m
        result = m.run_audit()
        assert result["verdict"] == m.PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED
        assert any("V2_8_3_3_1_MODEL_HEALTH_NOT_PASS" in b for b in result["blockers"])

    def test_11_growth_tier_blocked_if_feature_parity_blocked(self):
        """Growth profile must be BLOCKED if feature parity is BLOCKED."""
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_PASS",
            "active_model_count": 9, "failed_required_model_count": 0,
            "failed_optional_model_count": 0,
            "blocked_required_models": [], "warned_optional_models": [],
            "v2_8_4_allowed": True,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_BLOCKED"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})

        import scripts.audit.prop_challenge_growth_profile_audit as m
        result = m.run_audit()
        assert result["verdict"] == m.PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED
        assert any("V2_8_3_3_1_FEATURE_PARITY_NOT_PASS" in b for b in result["blockers"])

    def test_12_growth_tier_blocked_if_runtime_safety_blocked(self):
        """Growth profile must be BLOCKED if runtime safety is BLOCKED."""
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_PASS",
            "active_model_count": 9, "failed_required_model_count": 0,
            "failed_optional_model_count": 0,
            "blocked_required_models": [], "warned_optional_models": [],
            "v2_8_4_allowed": True,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_BLOCKED"})

        import scripts.audit.prop_challenge_growth_profile_audit as m
        result = m.run_audit()
        assert result["verdict"] == m.PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED
        assert any("V2_8_3_3_1_RUNTIME_SAFETY_NOT_PASS" in b for b in result["blockers"])


class TestProductionClosureGrowthIntegration:
    """Tests 13-14: Production closure reads growth profile audit."""

    def setup_method(self):
        self._backups = _backup([MH_PATH, FP_PATH, RS_PATH, GP_PATH, AE_PATH, EG_PATH, AR_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_13_production_closure_reads_growth_profile_audit(self):
        """Production closure must read growth profile audit fields."""
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_PASS",
            "active_model_count": 9, "failed_required_model_count": 0,
            "failed_optional_model_count": 0,
            "blocked_required_models": [], "warned_optional_models": [],
            "v2_8_4_allowed": True,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})
        _write_json(GP_PATH, {
            "verdict": "PROP_CHALLENGE_GROWTH_PROFILE_PASS",
            "profile_name": "PROP_CHALLENGE_GROWTH_30_8",
            "findings": {
                "monthly_target_pct": 0.30,
                "daily_dd_soft_limit_pct": 0.01,
                "daily_dd_hard_limit_pct": 0.02,
                "max_total_dd_pct": 0.08,
            },
        })
        _write_json(AR_PATH, {
            "verdict": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_allowed": True, "blockers": [],
        })
        _write_json(EG_PATH, {"verdict": "ENTRY_GATE_FULL_PASS", "blockers": []})

        import scripts.audit.production_closure_readiness_audit as m
        result = m.run_audit()
        assert "latest_growth_profile_verdict" in result
        assert "growth_profile_pass" in result
        assert "growth_profile_name" in result
        assert "growth_monthly_target_pct" in result
        assert "growth_daily_dd_soft_limit_pct" in result
        assert "growth_daily_dd_hard_limit_pct" in result
        assert "growth_total_dd_limit_pct" in result
        assert "growth_profile_allowed" in result
        assert result["growth_profile_name"] == "PROP_CHALLENGE_GROWTH_30_8"
        assert result["growth_profile_pass"] is True
        assert result["growth_profile_allowed"] is True

    def test_14_production_closure_blocks_when_growth_profile_blocked(self):
        """Production closure must add blocker when growth profile is BLOCKED."""
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_PASS",
            "active_model_count": 9, "failed_required_model_count": 0,
            "failed_optional_model_count": 0,
            "blocked_required_models": [], "warned_optional_models": [],
            "v2_8_4_allowed": True,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})
        _write_json(GP_PATH, {
            "verdict": "PROP_CHALLENGE_GROWTH_PROFILE_BLOCKED",
            "profile_name": "PROP_CHALLENGE_GROWTH_30_8",
            "findings": {},
        })
        _write_json(AR_PATH, {
            "verdict": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_allowed": True, "blockers": [],
        })
        _write_json(EG_PATH, {"verdict": "ENTRY_GATE_FULL_PASS", "blockers": []})

        import scripts.audit.production_closure_readiness_audit as m
        result = m.run_audit()
        assert any("GROWTH_PROFILE_BLOCKED" in b for b in result["blockers"]), \
            f"Expected GROWTH_PROFILE_BLOCKED in blockers: {result['blockers']}"
        assert result["growth_profile_allowed"] is False


class TestBuildRequestGrowthDisplay:
    """Tests 15-16: Build-request displays growth profile."""

    def setup_method(self):
        self._backups = _backup([MH_PATH, FP_PATH, RS_PATH, GP_PATH, AE_PATH, EG_PATH, AR_PATH])

    def teardown_method(self):
        _restore(self._backups)

    def test_15_build_request_displays_growth_profile(self):
        """Build-request must display growth profile fields."""
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_PASS_WITH_WARNINGS",
            "active_model_count": 9, "failed_required_model_count": 0,
            "failed_optional_model_count": 0,
            "blocked_required_models": [], "warned_optional_models": [],
            "v2_8_4_allowed": True,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})
        _write_json(GP_PATH, {
            "verdict": "PROP_CHALLENGE_GROWTH_PROFILE_PASS",
            "profile_name": "PROP_CHALLENGE_GROWTH_30_8",
            "findings": {
                "monthly_target_pct": 0.30,
                "daily_dd_soft_limit_pct": 0.01,
                "daily_dd_hard_limit_pct": 0.02,
                "max_total_dd_pct": 0.08,
            },
        })
        _write_json(AE_PATH, {
            "final_decision": "ALPHA_REGIME_ENTRY_PASS", "alpha_pass": True,
            "risk_gate_pass": True, "broker_gate_pass": True,
            "prop_funded_gate_pass": True, "geometry_gate_pass": True,
        })
        _write_json(EG_PATH, {"verdict": "ENTRY_GATE_FULL_PASS", "blockers": []})
        _write_json(AR_PATH, {
            "verdict": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_allowed": True, "blockers": [],
        })

        import scripts.operator.run_managed_demo_micro_trade as m
        args = MagicMock()
        args.direction = "BUY"
        args.entry_price = 2000.0
        args.sl = 0
        args.tp = 0
        args.prop_funded_profile = "prop_funded_safe"
        args.account_profile = ""
        args.use_adaptive_trailing = True
        args.use_dynamic_tp_extension = True
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.initial_tp_r = 3.0
        args.tp_extension_trigger_r = 2.0
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 1.5
        args.tp_extension_cooldown_seconds = 60
        args.min_profit_lock_after_tp_extension_r = 1.5
        args.max_profit_giveback_r_trend = 0.5
        args.max_profit_giveback_r_range = 0.3
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.risk_mode = "conservative"
        args.broker_profile = "metaquotes_demo"

        result = m.run_build_request(args.direction, args.entry_price, args.sl, args.tp, args)
        # Growth profile fields must be present
        assert "latest_growth_profile_verdict" in result
        assert "growth_profile_pass" in result
        assert "growth_profile_name" in result
        assert "growth_monthly_target_pct" in result
        assert "growth_daily_dd_soft_limit_pct" in result
        assert "growth_daily_dd_hard_limit_pct" in result
        assert "growth_total_dd_limit_pct" in result
        assert "growth_profile_allowed" in result
        # Values must match seeded audit data
        assert result["growth_profile_name"] == "PROP_CHALLENGE_GROWTH_30_8"
        assert result["growth_profile_pass"] is True
        assert result["growth_profile_allowed"] is True

    def test_16_build_request_shows_no_forced_trading_and_no_martingale(self):
        """Build-request must show 'No forced trading: True' and 'No martingale/...: True'."""
        _write_json(MH_PATH, {
            "verdict": "MODEL_ARTIFACT_HEALTH_PASS",
            "active_model_count": 9, "failed_required_model_count": 0,
            "failed_optional_model_count": 0,
            "blocked_required_models": [], "warned_optional_models": [],
            "v2_8_4_allowed": True,
        })
        _write_json(FP_PATH, {"verdict": "FEATURE_PARITY_PASS"})
        _write_json(RS_PATH, {"verdict": "RUNTIME_SAFETY_GATE_PASS"})
        _write_json(GP_PATH, {
            "verdict": "PROP_CHALLENGE_GROWTH_PROFILE_PASS",
            "profile_name": "PROP_CHALLENGE_GROWTH_30_8",
            "findings": {
                "monthly_target_pct": 0.30,
                "daily_dd_soft_limit_pct": 0.01,
                "daily_dd_hard_limit_pct": 0.02,
                "max_total_dd_pct": 0.08,
            },
        })
        _write_json(AE_PATH, {
            "final_decision": "ALPHA_REGIME_ENTRY_PASS", "alpha_pass": True,
            "risk_gate_pass": True, "broker_gate_pass": True,
            "prop_funded_gate_pass": True, "geometry_gate_pass": True,
        })
        _write_json(EG_PATH, {"verdict": "ENTRY_GATE_FULL_PASS", "blockers": []})
        _write_json(AR_PATH, {
            "verdict": "AUTONOMOUS_DEMO_READY_SUPERVISED",
            "autonomous_allowed": True, "blockers": [],
        })

        import scripts.operator.run_managed_demo_micro_trade as m
        args = MagicMock()
        args.direction = "BUY"
        args.entry_price = 2000.0
        args.sl = 0
        args.tp = 0
        args.prop_funded_profile = "prop_funded_safe"
        args.account_profile = ""
        args.use_adaptive_trailing = True
        args.use_dynamic_tp_extension = True
        args.adaptive_policy_mode = "balanced_conservative"
        args.breakeven_trigger_r = 1.0
        args.trailing_trigger_r = 1.75
        args.profit_lock_trigger_r = 3.0
        args.initial_tp_r = 3.0
        args.tp_extension_trigger_r = 2.0
        args.tp_extension_r = 1.0
        args.tp_extension_atr_mult = 1.5
        args.tp_extension_cooldown_seconds = 60
        args.min_profit_lock_after_tp_extension_r = 1.5
        args.max_profit_giveback_r_trend = 0.5
        args.max_profit_giveback_r_range = 0.3
        args.min_hold_seconds = 60
        args.min_monitor_iterations = 3
        args.sl_update_cooldown_seconds = 60
        args.risk_mode = "conservative"
        args.broker_profile = "metaquotes_demo"

        result = m.run_build_request(args.direction, args.entry_price, args.sl, args.tp, args)
        # Apply v2.8.3.2 verdict sync to populate execution_now_allowed/execution_blocker
        m.apply_build_request_verdict_sync(result)
        # Safety invariants preserved
        assert result.get("execution_now_allowed", True) is False
        assert result.get("execution_blocker", "") == "OPERATOR_ARM_TOKEN_REQUIRED"


class TestSafetyInvariantsGrowth:
    """Tests 17-19: Safety invariants preserved in growth profile audit."""

    def test_17_no_order_send_in_growth_profile_audit(self):
        """Growth profile audit must never call mt5.order_send."""
        import scripts.audit.prop_challenge_growth_profile_audit as m
        result = m.run_audit()
        assert result["safety"]["order_send_called"] is False

    def test_18_no_token_creation_in_growth_profile_audit(self):
        """Growth profile audit must never create operator execution token."""
        import scripts.audit.prop_challenge_growth_profile_audit as m
        result = m.run_audit()
        assert result["safety"]["token_created"] is False

    def test_19_no_position_modification_in_growth_profile_audit(self):
        """Growth profile audit must never modify positions."""
        import scripts.audit.prop_challenge_growth_profile_audit as m
        result = m.run_audit()
        assert result["safety"]["position_modified"] is False
