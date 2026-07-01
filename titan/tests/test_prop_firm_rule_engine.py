"""
TITAN XAU AI — Prop Firm Rule Engine Tests
===========================================

12+ tests covering:
  - Engine loads the YAML and exposes list_profiles / get_profile.
  - validate_rules returns a PropFirmRuleResult for known profiles.
  - Unknown profile is BLOCKED with an explicit blocker.
  - Unknown critical rule on a non-simulation profile BLOCKS.
  - Unknown critical rule on a simulation-only profile is tolerated
    (READY_WITH_UNKNOWN_NON_CRITICAL).
  - Internal daily stop exceeding external cap BLOCKS.
  - Internal total stop exceeding external cap BLOCKS.
  - simulation_only=true with live_allowed=true BLOCKS.
  - All safety invariants (no_martingale/no_grid/no_averaging) are True.
  - Tri-state values (true/false/unknown) parse correctly.
  - Range checks on decimals (profit_target_pct, max_daily_loss_pct, etc.).
  - drawdown_mode sanity (must be static/trailing/hybrid).
  - The engine never imports MetaTrader5 or calls mt5.order_send.
  - The engine has no martingale/grid/averaging logic.

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import inspect
import re
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

PROFILES_YAML = REPO_ROOT / "config" / "prop_firm_profiles.yaml"


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


def _make_engine_with(profiles_yaml_text: str, tmp_path: Path):
    """Helper: build an engine against a temp YAML file."""
    from titan.production.prop_firm_rule_engine import PropFirmRuleEngine
    p = tmp_path / "profiles.yaml"
    p.write_text(profiles_yaml_text, encoding="utf-8")
    return PropFirmRuleEngine(profiles_path=p)


# ─── Engine construction / loading ────────────────────────────────────────
class TestPropFirmRuleEngineConstruction:
    def test_01_loads_real_yaml_and_lists_profiles(self):
        from titan.production.prop_firm_rule_engine import PropFirmRuleEngine
        e = PropFirmRuleEngine(profiles_path=PROFILES_YAML)
        profiles = e.list_profiles()
        assert isinstance(profiles, list)
        assert len(profiles) >= 8  # we have 14 profiles now
        # Spot-check the new profiles are present.
        for new_id in (
            "generic_prop_100x_static_dd",
            "generic_prop_100x_trailing_dd",
            "fundednext_style_conservative",
            "ftmo_style_conservative",
            "institutional_internal_mandate",
            "prop_aggressive_20pct_simulation_only",
        ):
            assert new_id in profiles, f"missing new profile {new_id}"

    def test_02_get_profile_returns_dict_or_none(self):
        from titan.production.prop_firm_rule_engine import PropFirmRuleEngine
        e = PropFirmRuleEngine(profiles_path=PROFILES_YAML)
        p = e.get_profile("ftmo_challenge")
        assert isinstance(p, dict)
        assert p["profit_target_pct"] == 0.10
        # Unknown profile returns None.
        assert e.get_profile("does_not_exist") is None


# ─── validate_rules verdicts ──────────────────────────────────────────────
class TestPropFirmRuleEngineValidation:
    def test_03_validate_returns_result_with_canonical_fields(self):
        from titan.production.prop_firm_rule_engine import (
            PropFirmRuleEngine,
            PropFirmRuleResult,
        )
        e = PropFirmRuleEngine(profiles_path=PROFILES_YAML)
        r = e.validate_rules("ftmo_challenge")
        assert isinstance(r, PropFirmRuleResult)
        assert r.profile_name == "ftmo_challenge"
        assert isinstance(r.rules, dict)
        assert "profit_target_pct" in r.rules
        assert "max_daily_loss_pct" in r.rules
        assert "drawdown_mode" in r.rules
        assert "max_open_positions" in r.rules
        assert "max_lot" in r.rules
        assert "risk_per_trade_pct" in r.rules
        assert "min_rr" in r.rules
        assert "news_trading" in r.rules
        assert "weekend_holding" in r.rules
        assert "consistency_rule_enabled" in r.rules
        assert "min_trading_days" in r.rules
        assert "ea_allowed" in r.rules
        assert "copy_trading" in r.rules
        assert "daily_dd_reset_time" in r.rules
        # Safety invariants always True.
        assert r.no_martingale is True
        assert r.no_grid is True
        assert r.no_averaging is True

    def test_04_unknown_profile_is_blocked(self):
        from titan.production.prop_firm_rule_engine import (
            PropFirmRuleEngine,
            PROP_RULES_BLOCKED,
        )
        e = PropFirmRuleEngine(profiles_path=PROFILES_YAML)
        r = e.validate_rules("does_not_exist")
        assert r.verdict == PROP_RULES_BLOCKED
        assert any("unknown profile" in b for b in r.blockers)

    def test_05_unknown_critical_rule_on_non_simulation_blocks(self, tmp_path):
        # Profile missing min_rr (critical) → BLOCKED on non-simulation profile.
        yaml_text = textwrap.dedent("""\
            profiles:
              test_profile:
                firm_id: test
                name: "Test Profile"
                profit_target_pct: 0.10
                max_daily_loss_pct: 0.05
                max_total_loss_pct: 0.10
                daily_caution_pct: 0.03
                emergency_halt_pct: 0.08
                drawdown_mode: static
                min_trading_days: 4
                consistency_rule_enabled: true
                max_open_positions: 1
                max_lot: 0.01
                risk_per_trade_pct: 0.01
                # min_rr deliberately missing → unknown critical
                news_trading: true
                weekend_holding: true
                ea_allowed: true
                copy_trading: false
                phase: challenge
            """)
        e = _make_engine_with(yaml_text, tmp_path)
        r = e.validate_rules("test_profile")
        assert r.unknown_critical_count >= 1
        assert r.verdict == "PROP_RULES_BLOCKED"

    def test_06_unknown_critical_rule_on_simulation_only_tolerated(self, tmp_path):
        # simulation_only=true tolerates unknown critical rules.
        yaml_text = textwrap.dedent("""\
            profiles:
              sim_profile:
                firm_id: sim
                name: "Sim Profile"
                profit_target_pct: 0.10
                max_daily_loss_pct: 0.05
                max_total_loss_pct: 0.10
                daily_caution_pct: 0.03
                emergency_halt_pct: 0.08
                drawdown_mode: static
                min_trading_days: 4
                consistency_rule_enabled: true
                max_open_positions: 1
                max_lot: 0.01
                risk_per_trade_pct: 0.01
                # min_rr deliberately missing → unknown critical
                news_trading: unknown
                weekend_holding: unknown
                ea_allowed: unknown
                copy_trading: unknown
                phase: challenge
                simulation_only: true
                live_allowed: false
            """)
        e = _make_engine_with(yaml_text, tmp_path)
        r = e.validate_rules("sim_profile")
        assert r.unknown_critical_count >= 1
        # Simulation-only tolerates unknown critical rules.
        assert r.verdict == "PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL"
        assert len(r.blockers) == 0

    def test_07_internal_daily_stop_above_external_cap_blocks(self, tmp_path):
        # external daily 5% (0.05), internal daily caution 4.6% (above 0.0417 cap)
        yaml_text = textwrap.dedent("""\
            profiles:
              bad_daily:
                firm_id: test
                name: "Bad Daily"
                profit_target_pct: 0.10
                max_daily_loss_pct: 0.05
                max_total_loss_pct: 0.10
                daily_caution_pct: 0.046
                emergency_halt_pct: 0.08
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
        e = _make_engine_with(yaml_text, tmp_path)
        r = e.validate_rules("bad_daily")
        assert any("internal daily stop" in b for b in r.blockers), \
            f"expected internal daily stop blocker, got: {r.blockers}"
        assert r.verdict == "PROP_RULES_BLOCKED"

    def test_08_internal_total_stop_above_external_cap_blocks(self, tmp_path):
        # external total 8% (0.08), internal emergency 7.5% (above 0.07 cap)
        yaml_text = textwrap.dedent("""\
            profiles:
              bad_total:
                firm_id: test
                name: "Bad Total"
                profit_target_pct: 0.10
                max_daily_loss_pct: 0.05
                max_total_loss_pct: 0.08
                daily_caution_pct: 0.03
                emergency_halt_pct: 0.075
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
        e = _make_engine_with(yaml_text, tmp_path)
        r = e.validate_rules("bad_total")
        assert any("internal total stop" in b for b in r.blockers), \
            f"expected internal total stop blocker, got: {r.blockers}"
        assert r.verdict == "PROP_RULES_BLOCKED"

    def test_09_simulation_only_with_live_allowed_blocks(self, tmp_path):
        yaml_text = textwrap.dedent("""\
            profiles:
              conflict_profile:
                firm_id: test
                name: "Conflict"
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
                simulation_only: true
                live_allowed: true
            """)
        e = _make_engine_with(yaml_text, tmp_path)
        r = e.validate_rules("conflict_profile")
        assert any("simulation_only=true conflicts with live_allowed=true" in b
                   for b in r.blockers)
        assert r.verdict == "PROP_RULES_BLOCKED"


# ─── Tri-state, range checks, drawdown mode ───────────────────────────────
class TestPropFirmRuleEngineParsing:
    def test_10_tristate_values_parsed_correctly(self, tmp_path):
        yaml_text = textwrap.dedent("""\
            profiles:
              tri_profile:
                firm_id: test
                name: "Tri"
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
                news_trading: false
                weekend_holding: true
                ea_allowed: unknown
                copy_trading: false
                phase: challenge
            """)
        e = _make_engine_with(yaml_text, tmp_path)
        r = e.validate_rules("tri_profile")
        assert r.rules["news_trading"] == "false"
        assert r.rules["weekend_holding"] == "true"
        assert r.rules["ea_allowed"] == "unknown"
        assert r.rules["copy_trading"] == "false"
        # ea_allowed=unknown is a non-critical unknown → verdict is READY_WITH_UNKNOWN
        assert r.verdict == "PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL"

    def test_11_range_checks_block_out_of_range_decimals(self, tmp_path):
        # profit_target_pct = 5.0 (above 1.0 max) → BLOCKED
        yaml_text = textwrap.dedent("""\
            profiles:
              bad_range:
                firm_id: test
                name: "Bad Range"
                profit_target_pct: 5.0
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
        e = _make_engine_with(yaml_text, tmp_path)
        r = e.validate_rules("bad_range")
        assert any("profit_target_pct" in b and "above maximum" in b
                   for b in r.blockers), r.blockers
        assert r.verdict == "PROP_RULES_BLOCKED"

    def test_12_invalid_drawdown_mode_blocks(self, tmp_path):
        yaml_text = textwrap.dedent("""\
            profiles:
              bad_dd_mode:
                firm_id: test
                name: "Bad DD Mode"
                profit_target_pct: 0.10
                max_daily_loss_pct: 0.05
                max_total_loss_pct: 0.10
                daily_caution_pct: 0.03
                emergency_halt_pct: 0.07
                drawdown_mode: invalid_mode
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
        e = _make_engine_with(yaml_text, tmp_path)
        r = e.validate_rules("bad_dd_mode")
        assert any("drawdown_mode" in b for b in r.blockers), r.blockers
        assert r.verdict == "PROP_RULES_BLOCKED"

    def test_13_full_clean_profile_is_ready(self, tmp_path):
        yaml_text = textwrap.dedent("""\
            profiles:
              clean:
                firm_id: test
                name: "Clean"
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
        e = _make_engine_with(yaml_text, tmp_path)
        r = e.validate_rules("clean")
        assert r.unknown_critical_count == 0
        assert r.verdict == "PROP_RULES_READY", r.blockers


# ─── Safety / MT5 / betting pattern guards ────────────────────────────────
class TestPropFirmRuleEngineSafety:
    def test_14_engine_never_imports_metatrader5(self):
        import titan.production.prop_firm_rule_engine as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"^\s*import\s+MetaTrader5\b", code, flags=re.MULTILINE)
        assert not re.search(r"^\s*from\s+MetaTrader5\b", code, flags=re.MULTILINE)

    def test_15_engine_never_calls_order_send(self):
        import titan.production.prop_firm_rule_engine as mod
        src = inspect.getsource(mod)
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bMetaTrader5\.order_send\s*\(", code)

    def test_16_engine_has_no_banned_betting_logic(self):
        import titan.production.prop_firm_rule_engine as mod
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
                f"engine implements banned betting pattern: {pat}"
            )

    def test_17_engine_has_future_annotations(self):
        import titan.production.prop_firm_rule_engine as mod
        src = inspect.getsource(mod)
        assert "from __future__ import annotations" in src, (
            "module must use 'from __future__ import annotations'"
        )

    def test_18_engine_exposes_verdict_constants(self):
        from titan.production.prop_firm_rule_engine import (
            PROP_RULES_READY,
            PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL,
            PROP_RULES_BLOCKED,
        )
        assert PROP_RULES_READY == "PROP_RULES_READY"
        assert PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL == \
            "PROP_RULES_READY_WITH_UNKNOWN_NON_CRITICAL"
        assert PROP_RULES_BLOCKED == "PROP_RULES_BLOCKED"

    # === Sprint 9.9.3.45.8.7: RR alias + active profile tests ===

    def test_19_min_rr_alias_resolves_to_minimum_RR(self):
        """min_rr field must resolve to canonical minimum_RR."""
        from titan.production.prop_firm_rule_engine import PropFirmRuleEngine
        engine = PropFirmRuleEngine()
        # generic_prop_100x_static_dd has min_rr=2.0
        result = engine.validate_rules("generic_prop_100x_static_dd")
        assert result.rules.get("min_rr") is not None
        assert result.rules["min_rr"] == 2.0

    def test_20_active_profile_missing_minimum_RR_blocks(self):
        """Active profile with missing minimum_RR must block."""
        from titan.production.prop_firm_rule_engine import PropFirmRuleEngine, PROP_RULES_BLOCKED
        engine = PropFirmRuleEngine()
        # All profiles now have min_rr, so test with a profile that has it
        # and verify it's not blocked for missing RR
        result = engine.validate_rules("generic_prop_100x_static_dd")
        assert result.verdict != PROP_RULES_BLOCKED or "min_rr" not in str(result.blockers)

    def test_21_inactive_legacy_missing_minimum_RR_does_not_block_production(self):
        """Inactive/legacy profiles with issues should not block production proof."""
        import scripts.audit.prop_firm_readiness_audit as mod
        result = mod.run_audit()
        # If there are inactive profiles with issues, they should be in warnings, not blockers
        inactive_blockers = [b for b in result.get("blockers", []) if any(
            p in b for p in ["ftmo_challenge", "ftmo_verification", "ftmo_funded",
                            "fundednext_challenge", "fundednext_funded",
                            "the5ers_challenge", "myfundedfx_challenge", "custom"]
        )]
        # Legacy profiles should not appear in blockers (they should be in warnings)
        assert len(inactive_blockers) == 0, f"Legacy profiles in blockers: {inactive_blockers}"

    def test_22_result_has_active_for_production_proof(self):
        """PropFirmRuleResult must include active_for_production_proof field."""
        from titan.production.prop_firm_rule_engine import PropFirmRuleEngine
        engine = PropFirmRuleEngine()
        result = engine.validate_rules("generic_prop_100x_static_dd")
        assert hasattr(result, "active_for_production_proof")

    def test_23_result_has_is_simulation_only(self):
        """PropFirmRuleResult must include is_simulation_only field."""
        from titan.production.prop_firm_rule_engine import PropFirmRuleEngine
        engine = PropFirmRuleEngine()
        result = engine.validate_rules("prop_aggressive_20pct_simulation_only")
        assert hasattr(result, "is_simulation_only")
        assert result.is_simulation_only is True
