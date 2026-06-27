"""
TITAN XAU AI — Sprint 9.9.3.2 Stress Loss Governance Engine Tests

20 tests covering all scenario-specific mitigations, profit ladder,
trade acceptance score, account profiles, fail-closed, and safety
(no martingale/grid/averaging/lot escalation).
"""
from __future__ import annotations
import inspect
import pytest
from titan.production.stress_loss_governance import (
    StressLossGovernanceEngine,
    GovernanceInput,
    GovernanceDecision,
    AccountProfile,
    ExitAction,
    DecisionLabel,
    PROFILE_THRESHOLDS,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _good_input(**overrides) -> GovernanceInput:
    """A baseline GOOD input that should be allowed."""
    defaults = dict(
        regime_label="TREND_UP",
        regime_confidence=0.80,
        meta_confidence=0.80,
        atr_percentile=50.0,
        volatility_state="NORMAL",
        spread_usd=0.25,
        slippage_pips=2.0,
        session="LONDON",
        liquidity="GOOD",
        account_health=90.0,
        equity_protection_active=False,
        capital_preservation_active=False,
        broker_quality=85.0,
        daily_dd_pct=0.5,
        daily_dd_threshold_pct=3.0,
        regime_flip_probability=0.20,
        rolling_setup_winrate=0.50,
        account_profile=AccountProfile.PROP_FIRM_STRICT.value,
    )
    defaults.update(overrides)
    return GovernanceInput(**defaults)


# ─── 1. HIGH_VOLATILITY ──────────────────────────────────────────────────────

class TestHighVolatility:
    def test_01_high_vol_atr_above_90_blocks_trade(self):
        """ATR percentile > 90 (PROP_FIRM_STRICT threshold) blocks trade."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(atr_percentile=95.0)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert dec.decision_label == DecisionLabel.NO_TRADE.value
        assert "HIGH_VOLATILITY" in dec.block_reason

    def test_02_high_vol_75_90_requires_meta_075(self):
        """ATR percentile 75-90 requires meta_confidence >= 0.75."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        # meta=0.70 should be blocked in warn zone
        inp = _good_input(atr_percentile=82.0, meta_confidence=0.70)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "HIGH_VOLATILITY" in dec.block_reason
        # meta=0.78 with spread <= 0.40 should be allowed (with reduced risk)
        inp2 = _good_input(atr_percentile=82.0, meta_confidence=0.78, spread_usd=0.30)
        dec2 = engine.evaluate_entry(inp2)
        assert dec2.allow_trade is True
        assert dec2.risk_multiplier <= 0.50

    def test_03_high_vol_lowers_risk_multiplier(self):
        """High volatility warn zone lowers risk multiplier to 0.50."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(atr_percentile=82.0, meta_confidence=0.80, spread_usd=0.30)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True
        assert dec.risk_multiplier <= 0.50
        assert dec.decision_label == DecisionLabel.REDUCE_RISK.value


# ─── 2. AMBIGUOUS_CANDLE ─────────────────────────────────────────────────────

class TestAmbiguousCandle:
    def test_04_ambiguous_candle_blocks_by_default(self):
        """Ambiguous candle blocks by default."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(ambiguous_candle=True, confirmation_present=False)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "AMBIGUOUS_CANDLE" in dec.block_reason

    def test_05_ambiguous_candle_allows_strong_confirmed(self):
        """Ambiguous candle allows only strong confirmed signal."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(
            ambiguous_candle=True,
            confirmation_present=True,
            meta_confidence=0.78,
            regime_confidence=0.72,
            spread_usd=0.25,
            liquidity="GOOD",
        )
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True
        assert dec.decision_label in (DecisionLabel.ALLOW.value,
                                       DecisionLabel.REDUCE_RISK.value)


# ─── 3. BUY_SL / SELL_SL baseline ────────────────────────────────────────────

class TestBaselineEntries:
    def test_06_spread_above_0_30_blocks_baseline(self):
        """Spread > 0.30 (PROP_FIRM_STRICT) blocks baseline entries."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(spread_usd=0.55)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "BASELINE" in dec.block_reason
        assert "spread" in dec.block_reason

    def test_07_weak_meta_below_0_70_blocks(self):
        """Meta < 0.70 blocks SL-prone entries."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(meta_confidence=0.65)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "BASELINE" in dec.block_reason
        assert "meta" in dec.block_reason


# ─── 4. Profit ladder ────────────────────────────────────────────────────────

class TestProfitLadder:
    def test_08_05R_triggers_BE_partial(self):
        """+0.5R triggers MOVE_BE (25% partial + BE)."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(open_trade_side="BUY", current_r_multiple=0.55)
        dec = engine.evaluate_management(inp)
        assert dec.exit_action == ExitAction.MOVE_BE.value
        assert "profit_ladder" in dec.exit_reason
        assert "0.5" in dec.exit_reason or "0.55" in dec.exit_reason

    def test_09_1R_triggers_larger_partial(self):
        """+1R triggers 50% PARTIAL_CLOSE."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(open_trade_side="BUY", current_r_multiple=1.05)
        dec = engine.evaluate_management(inp)
        assert dec.exit_action == ExitAction.PARTIAL_CLOSE.value
        assert "profit_ladder" in dec.exit_reason


# ─── 5. REGIME_FLIP ──────────────────────────────────────────────────────────

class TestRegimeFlip:
    def test_10_regime_flip_prob_above_06_blocks_new_trade(self):
        """Regime flip probability > 0.60 blocks new trade."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(regime_flip_probability=0.75)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "REGIME_FLIP" in dec.block_reason

    def test_11_regime_flip_against_open_trade_closes_reduces(self):
        """Regime flip against open trade triggers close/reduce."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        # Losing trade + flip → REDUCE 50%
        inp_losing = _good_input(
            open_trade_side="BUY",
            current_r_multiple=-0.3,
            regime_flip_probability=0.75,
        )
        dec = engine.evaluate_management(inp_losing)
        assert dec.exit_action == ExitAction.REDUCE.value
        assert "regime_flip" in dec.exit_reason
        # Near-BE trade + flip → CLOSE at BE
        inp_be = _good_input(
            open_trade_side="BUY",
            current_r_multiple=0.1,
            regime_flip_probability=0.75,
        )
        dec_be = engine.evaluate_management(inp_be)
        assert dec_be.exit_action == ExitAction.CLOSE.value
        # Profitable trade + flip → TIGHT_TRAIL
        inp_profit = _good_input(
            open_trade_side="BUY",
            current_r_multiple=0.7,
            regime_flip_probability=0.75,
        )
        dec_profit = engine.evaluate_management(inp_profit)
        assert dec_profit.exit_action == ExitAction.TIGHT_TRAIL.value


# ─── 6. Protection states ────────────────────────────────────────────────────

class TestProtectionStates:
    def test_12_equity_protection_disables_new_trades(self):
        """Equity protection active disables new trades."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(equity_protection_active=True)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "EQUITY_PROTECTION" in dec.block_reason

    def test_13_capital_preservation_disables_new_trades(self):
        """Capital preservation active disables new trades."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(capital_preservation_active=True)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "CAPITAL_PRESERVATION" in dec.block_reason

    def test_14_account_health_low_disables_new_trades(self):
        """Account health < threshold disables new trades."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(account_health=40.0)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "ACCOUNT" in dec.block_reason


# ─── 7. Setup winrate / broker quality ───────────────────────────────────────

class TestSetupBroker:
    def test_15_rolling_setup_winrate_below_35_disables(self):
        """Rolling setup winrate < 35% disables setup."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(rolling_setup_winrate=0.25)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "SETUP" in dec.block_reason

    def test_16_poor_broker_quality_blocks_trade(self):
        """Poor broker quality (< 70 PROP_FIRM) blocks trade."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(broker_quality=60.0)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "BASELINE" in dec.block_reason
        assert "broker_quality" in dec.block_reason


# ─── 8. Protection-zone management ───────────────────────────────────────────

class TestProtectionMgmt:
    def test_17_profitable_trade_in_protection_zone_locks_profit(self):
        """Existing profitable trade in protection zone closes/locks profit."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(
            open_trade_side="BUY",
            current_r_multiple=0.5,
            equity_protection_active=True,
        )
        dec = engine.evaluate_management(inp)
        assert dec.exit_action == ExitAction.PARTIAL_CLOSE.value
        assert "equity_protection" in dec.exit_reason
        assert "lock profit" in dec.exit_reason

    def test_18_near_BE_trade_in_protection_zone_closes_at_BE(self):
        """Near-BE trade in protection zone closes at BE."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(
            open_trade_side="BUY",
            current_r_multiple=0.1,
            equity_protection_active=True,
        )
        dec = engine.evaluate_management(inp)
        assert dec.exit_action == ExitAction.CLOSE.value
        assert "BE" in dec.exit_reason


# ─── 9. Safety: no martingale/grid/averaging/lot escalation ──────────────────

class TestSafetyInvariants:
    def test_19_no_martingale_grid_averaging_lot_escalation(self):
        """No martingale/grid/averaging/lot escalation introduced."""
        import titan.production.stress_loss_governance as mod
        src = inspect.getsource(mod)
        # Forbidden patterns
        assert "def _martingale" not in src
        assert "def _grid" not in src
        assert "def _averaging" not in src
        assert "lot *= 2" not in src
        assert "next_lot" not in src
        assert "add_to_position" not in src
        # Risk multiplier must never exceed 1.0 (only DECREASE risk)
        # Verify in code: every assignment to mult uses min()
        assert "mult = min(mult" in src
        # No "mult = 1.5" or "mult = 2.0" anywhere
        assert "mult = 1.5" not in src
        assert "mult = 2.0" not in src
        # Verify risk_multiplier in PROFILE_THRESHOLDS never exceeds 1.0
        for profile_name, th in PROFILE_THRESHOLDS.items():
            assert th["risk_multiplier_in_warn_vol"] <= 1.0, \
                f"{profile_name}: risk_multiplier_in_warn_vol > 1.0"


# ─── 10. Fail-closed ─────────────────────────────────────────────────────────

class TestFailClosed:
    def test_20_fail_closed_on_invalid_inputs(self):
        """Fail-closed on missing/invalid governance inputs."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)

        # Invalid meta_confidence
        inp = _good_input(meta_confidence=-0.5)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "fail-closed" in dec.block_reason
        assert dec.governance_score == 0.0

        # Invalid atr_percentile (out of range)
        inp2 = _good_input(atr_percentile=150.0)
        dec2 = engine.evaluate_entry(inp2)
        assert dec2.allow_trade is False
        assert "fail-closed" in dec2.block_reason

        # Invalid account_health (out of range)
        inp3 = _good_input(account_health=200.0)
        dec3 = engine.evaluate_entry(inp3)
        assert dec3.allow_trade is False
        assert "fail-closed" in dec3.block_reason

        # Invalid regime_flip_probability (out of range)
        inp4 = _good_input(regime_flip_probability=1.5)
        dec4 = engine.evaluate_entry(inp4)
        assert dec4.allow_trade is False
        assert "fail-closed" in dec4.block_reason

        # Fail-closed in management → EXIT for safety
        inp5 = _good_input(open_trade_side="BUY", current_r_multiple=0.5,
                           meta_confidence=-0.1)
        dec5 = engine.evaluate_management(inp5)
        assert dec5.exit_action == ExitAction.CLOSE.value
        assert "fail-closed" in dec5.exit_reason


# ─── 11. Account profile tests (institutional strictest) ─────────────────────

class TestAccountProfiles:
    def test_institutional_is_strictest(self):
        """INSTITUTIONAL profile has strictest thresholds."""
        retail = PROFILE_THRESHOLDS[AccountProfile.RETAIL_SAFE.value]
        prop = PROFILE_THRESHOLDS[AccountProfile.PROP_FIRM_STRICT.value]
        inst = PROFILE_THRESHOLDS[AccountProfile.INSTITUTIONAL_CAPITAL_PROTECTION.value]

        # min_meta_confidence: inst >= prop >= retail
        assert inst["min_meta_confidence"] >= prop["min_meta_confidence"]
        assert prop["min_meta_confidence"] >= retail["min_meta_confidence"]

        # max_spread_usd: inst <= prop <= retail
        assert inst["max_spread_usd"] <= prop["max_spread_usd"]
        assert prop["max_spread_usd"] <= retail["max_spread_usd"]

        # max_atr_percentile_block: inst <= prop <= retail
        assert inst["max_atr_percentile_block"] <= prop["max_atr_percentile_block"]
        assert prop["max_atr_percentile_block"] <= retail["max_atr_percentile_block"]

        # min_account_health: inst >= prop >= retail
        assert inst["min_account_health"] >= prop["min_account_health"]
        assert prop["min_account_health"] >= retail["min_account_health"]

    def test_institutional_blocks_what_retail_allows(self):
        """INSTITUTIONAL blocks trades that RETAIL_SAFE allows."""
        # meta=0.70, regime_conf=0.65 — RETAIL allows, INSTITUTIONAL blocks
        inp_retail = _good_input(
            meta_confidence=0.70,
            regime_confidence=0.65,
            account_profile=AccountProfile.RETAIL_SAFE.value,
        )
        engine_retail = StressLossGovernanceEngine(AccountProfile.RETAIL_SAFE.value)
        dec_retail = engine_retail.evaluate_entry(inp_retail)
        assert dec_retail.allow_trade is True

        inp_inst = _good_input(
            meta_confidence=0.70,
            regime_confidence=0.65,
            account_profile=AccountProfile.INSTITUTIONAL_CAPITAL_PROTECTION.value,
        )
        engine_inst = StressLossGovernanceEngine(
            AccountProfile.INSTITUTIONAL_CAPITAL_PROTECTION.value)
        dec_inst = engine_inst.evaluate_entry(inp_inst)
        assert dec_inst.allow_trade is False

    def test_institutional_approval_requires_high_score(self):
        """institutional_approval=True only when score >= 70 and meta >= 0.75."""
        engine = StressLossGovernanceEngine(
            AccountProfile.INSTITUTIONAL_CAPITAL_PROTECTION.value)
        # Weak input — should not get institutional approval
        inp_weak = _good_input(
            meta_confidence=0.76,
            regime_confidence=0.71,
            atr_percentile=70,
            account_profile=AccountProfile.INSTITUTIONAL_CAPITAL_PROTECTION.value,
        )
        dec_weak = engine.evaluate_entry(inp_weak)
        # Strong input — should get institutional approval
        inp_strong = _good_input(
            meta_confidence=0.85,
            regime_confidence=0.85,
            atr_percentile=40,
            spread_usd=0.20,
            account_health=95,
            broker_quality=90,
            account_profile=AccountProfile.INSTITUTIONAL_CAPITAL_PROTECTION.value,
        )
        dec_strong = engine.evaluate_entry(inp_strong)
        # At least one of them must have institutional_approval=True for the strong
        assert dec_strong.allow_trade is True
        assert dec_strong.institutional_approval is True
        assert dec_strong.governance_score >= 70.0


# ─── 12. Explainability ──────────────────────────────────────────────────────

class TestExplainability:
    def test_every_decision_has_audit_trail(self):
        """Every decision returns audit dict with checks list."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        # Allowed trade
        dec_allow = engine.evaluate_entry(_good_input())
        assert "checks" in dec_allow.audit
        assert len(dec_allow.audit["checks"]) >= 6
        # Blocked trade
        dec_block = engine.evaluate_entry(_good_input(meta_confidence=0.50))
        assert dec_block.block_reason != ""
        assert "checks" in dec_block.audit
        # Management decision
        dec_mgmt = engine.evaluate_management(
            _good_input(open_trade_side="BUY", current_r_multiple=1.0))
        assert dec_mgmt.audit.get("phase") == "management"

    def test_blocked_trade_includes_clear_reason(self):
        """Every blocked trade includes a clear reason."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(spread_usd=0.80, atr_percentile=95.0,
                          equity_protection_active=True)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        # Multiple block reasons should be in block_reason
        assert "HIGH_VOLATILITY" in dec.block_reason
        assert "BASELINE" in dec.block_reason
        assert "EQUITY_PROTECTION" in dec.block_reason

    def test_exit_action_includes_reason(self):
        """Every non-HOLD exit action includes a reason."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        # MOVE_BE
        dec = engine.evaluate_management(
            _good_input(open_trade_side="BUY", current_r_multiple=0.5))
        assert dec.exit_action == ExitAction.MOVE_BE.value
        assert dec.exit_reason != ""
        # PARTIAL_CLOSE
        dec2 = engine.evaluate_management(
            _good_input(open_trade_side="BUY", current_r_multiple=1.0))
        assert dec2.exit_action == ExitAction.PARTIAL_CLOSE.value
        assert dec2.exit_reason != ""
        # TIGHT_TRAIL
        dec3 = engine.evaluate_management(
            _good_input(open_trade_side="BUY", current_r_multiple=1.6))
        assert dec3.exit_action == ExitAction.TIGHT_TRAIL.value
        assert dec3.exit_reason != ""
