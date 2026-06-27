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
    def test_01_high_vol_atr_above_95_hard_blocks_trade(self):
        """Sprint 9.9.3.3: ATR percentile > 95 (hard block threshold) blocks trade.

        Note: Sprint 9.9.3.2 used 92 as block threshold, causing over-filtering.
        Sprint 9.9.3.3 moves the hard block to 95+ and uses 90-95 as throttle zone.
        """
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(atr_percentile=96.0)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert dec.decision_label == DecisionLabel.NO_TRADE.value
        assert "HIGH_VOLATILITY" in dec.block_reason
        assert "hard block" in dec.block_reason

    def test_01b_high_vol_90_95_throttles_trade(self):
        """Sprint 9.9.3.3: ATR 90-95 is throttle zone (allow with reduced risk if meta high)."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        # meta >= 0.80 (throttle requirement) → allowed with mult <= 0.25
        inp = _good_input(atr_percentile=92.0, meta_confidence=0.82)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True
        assert dec.risk_multiplier <= 0.25
        assert dec.decision_label == DecisionLabel.REDUCE_RISK.value
        # meta < 0.80 (throttle requirement) → blocked
        inp2 = _good_input(atr_percentile=92.0, meta_confidence=0.78)
        dec2 = engine.evaluate_entry(inp2)
        assert dec2.allow_trade is False
        assert "HIGH_VOLATILITY" in dec2.block_reason

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

    def test_16_poor_broker_quality_throttles_trade(self):
        """Sprint 9.9.3.3: Poor broker quality (50-70 PROP_FIRM) throttles trade.

        Hard block is now at < 50 (PROP_FIRM_STRICT).
        50-70 is throttle zone: allowed with reduced risk.
        """
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        # broker_quality 60 (throttle zone) → allowed with reduced risk
        inp = _good_input(broker_quality=60.0)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True
        assert dec.risk_multiplier <= 0.50
        assert dec.decision_label == DecisionLabel.REDUCE_RISK.value
        # broker_quality 40 (below hard block) → blocked
        inp2 = _good_input(broker_quality=40.0)
        dec2 = engine.evaluate_entry(inp2)
        assert dec2.allow_trade is False
        assert "BASELINE" in dec2.block_reason
        assert "broker_quality" in dec2.block_reason
        assert "hard block" in dec2.block_reason


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


# ─── 13. Sprint 9.9.3.3 — 3-tier calibration tests ───────────────────────────

class TestSprint9933ThreeTier:
    """Tests for the new 3-tier block/throttle/allow logic."""

    def test_9933_atr_95_throttle_zone_allows_with_strong_meta(self):
        """Sprint 9.9.3.3: ATR=95 in PROP_FIRM_STRICT (throttle zone, was hard block before).

        With meta=0.82 (>= 0.80 throttle req), should be ALLOWED with risk_mult <= 0.25.
        """
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(atr_percentile=95.0, meta_confidence=0.82)
        dec = engine.evaluate_entry(inp)
        # Should be allowed (throttle, not hard block)
        assert dec.allow_trade is True
        assert dec.risk_multiplier <= 0.25
        assert dec.decision_label == DecisionLabel.REDUCE_RISK.value

    def test_9933_atr_above_96_hard_blocks(self):
        """Sprint 9.9.3.3: ATR > 95 (PROP_FIRM_STRICT) is hard block."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(atr_percentile=97.0, meta_confidence=0.90)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "HIGH_VOLATILITY" in dec.block_reason
        assert "hard block" in dec.block_reason

    def test_9933_meta_below_block_threshold_blocks(self):
        """Sprint 9.9.3.3: meta < 0.65 (PROP_FIRM_STRICT hard block threshold) blocks."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(meta_confidence=0.60)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "BASELINE" in dec.block_reason
        assert "hard block" in dec.block_reason

    def test_9933_meta_throttle_zone_with_positive_edge_allows(self):
        """Sprint 9.9.3.3: meta in [0.65, 0.70) with strong expected edge allows (throttle).

        This is the KEY overfiltering fix — borderline weak alpha with strong expected
        edge is now allowed with reduced risk, not blocked.
        """
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        # meta=0.68 (between block 0.65 and throttle 0.70) with strong edge
        inp = _good_input(meta_confidence=0.68, expected_edge_usd=1.5)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True
        assert dec.risk_multiplier <= 0.25  # heavily throttled
        assert dec.decision_label == DecisionLabel.REDUCE_RISK.value

    def test_9933_meta_throttle_zone_without_strong_edge_blocks(self):
        """Sprint 9.9.3.3: meta in [0.65, 0.70) without strong edge blocks."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        # meta=0.68 (throttle zone) but no expected edge
        inp = _good_input(meta_confidence=0.68, expected_edge_usd=0.0)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False

    def test_9933_spread_throttle_with_high_edge_allows(self):
        """Sprint 9.9.3.3: spread > normal cap but expected_edge > cost_buffer allows.

        Sprint 9.9.3.2 would have hard-blocked this; 9.9.3.3 throttles it.
        """
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        # spread=0.55 (> 0.50 cap) but expected_edge=2.0 (> 0.50 buffer)
        inp = _good_input(spread_usd=0.55, expected_edge_usd=2.0,
                          meta_confidence=0.75)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True
        assert dec.risk_multiplier <= 0.50  # throttled

    def test_9933_spread_hard_block_above_max(self):
        """Sprint 9.9.3.3: spread > max_spread_usd_block (0.80 PROP_FIRM) hard blocks."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(spread_usd=1.00, expected_edge_usd=10.0)  # even strong edge
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "hard block" in dec.block_reason

    def test_9933_regime_flip_throttle_with_confirmation_allows(self):
        """Sprint 9.9.3.3: regime_flip in [0.60, 0.75] with confirmation + edge allows.

        Sprint 9.9.3.2 would have hard-blocked this; 9.9.3.3 throttles it.
        """
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(regime_flip_probability=0.68,
                          confirmation_present=True,
                          expected_edge_usd=2.0,
                          meta_confidence=0.75)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True
        assert dec.risk_multiplier <= 0.50

    def test_9933_regime_flip_hard_block_above_075(self):
        """Sprint 9.9.3.3: regime_flip > 0.75 (PROP_FIRM) hard blocks."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(regime_flip_probability=0.80,
                          confirmation_present=True,
                          expected_edge_usd=10.0,
                          meta_confidence=0.90)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "REGIME_FLIP" in dec.block_reason
        assert "hard block" in dec.block_reason

    def test_9933_account_health_throttle_with_strong_edge_allows(self):
        """Sprint 9.9.3.3: account_health in throttle zone with strong edge allows."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        # health=55 (between 40 block and 60 throttle) with strong edge
        inp = _good_input(account_health=55.0, expected_edge_usd=1.5,
                          meta_confidence=0.75)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True

    def test_9933_account_health_below_block_threshold_blocks(self):
        """Sprint 9.9.3.3: account_health < min_account_health_block (40 PROP_FIRM) blocks."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(account_health=30.0, expected_edge_usd=10.0)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "hard block" in dec.block_reason


# ─── 14. Sprint 9.9.3.3 — Exit management coverage ──────────────────────────

class TestSprint9933ExitManagement:
    """Force coverage of all exit actions: MOVE_BE, PARTIAL_CLOSE, TIGHT_TRAIL,
    EARLY_CLOSE, REDUCE, CLOSE_AT_BE."""

    def test_9933_move_be_at_05R(self):
        """MOVE_BE triggered at +0.5R (profit protection ladder)."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        dec = engine.evaluate_management(_good_input(
            open_trade_side="BUY", current_r_multiple=0.55))
        assert dec.exit_action == ExitAction.MOVE_BE.value
        assert "profit_ladder" in dec.exit_reason

    def test_9933_partial_close_at_1R(self):
        """PARTIAL_CLOSE triggered at +1.0R (50% partial + BE)."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        dec = engine.evaluate_management(_good_input(
            open_trade_side="BUY", current_r_multiple=1.05))
        assert dec.exit_action == ExitAction.PARTIAL_CLOSE.value

    def test_9933_tight_trail_at_15R(self):
        """TIGHT_TRAIL triggered at +1.5R."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        dec = engine.evaluate_management(_good_input(
            open_trade_side="BUY", current_r_multiple=1.6))
        assert dec.exit_action == ExitAction.TIGHT_TRAIL.value

    def test_9933_early_close_baseline_invalidation(self):
        """EARLY_CLOSE triggered by baseline invalidation (-0.3R within 2 candles)."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        dec = engine.evaluate_management(_good_input(
            open_trade_side="BUY", current_r_multiple=-0.35,
            mae=4.0, candles_in_trade=2))
        assert dec.exit_action == ExitAction.CLOSE.value
        assert "invalidation" in dec.exit_reason.lower() or "baseline" in dec.exit_reason.lower()

    def test_9933_reduce_on_equity_protection_losing_trade(self):
        """REDUCE triggered for losing trade in equity protection zone."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        dec = engine.evaluate_management(_good_input(
            open_trade_side="BUY", current_r_multiple=-0.4,
            equity_protection_active=True))
        assert dec.exit_action == ExitAction.REDUCE.value
        assert "equity_protection" in dec.exit_reason

    def test_9933_close_at_be_in_equity_protection_near_be(self):
        """CLOSE_AT_BE triggered for near-BE trade in equity protection zone."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        dec = engine.evaluate_management(_good_input(
            open_trade_side="BUY", current_r_multiple=0.1,
            equity_protection_active=True))
        assert dec.exit_action == ExitAction.CLOSE.value
        assert "BE" in dec.exit_reason or "be" in dec.exit_reason.lower()

    def test_9933_reduce_on_regime_flip_losing(self):
        """REDUCE 50% triggered on losing trade with regime flip against."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        dec = engine.evaluate_management(_good_input(
            open_trade_side="BUY", current_r_multiple=-0.3,
            regime_flip_probability=0.75))
        assert dec.exit_action == ExitAction.REDUCE.value
        assert "regime_flip" in dec.exit_reason

    def test_9933_partial_close_on_equity_protection_profitable(self):
        """PARTIAL_CLOSE triggered to lock profit on +R trade in equity protection."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        dec = engine.evaluate_management(_good_input(
            open_trade_side="BUY", current_r_multiple=0.5,
            equity_protection_active=True))
        assert dec.exit_action == ExitAction.PARTIAL_CLOSE.value
        assert "lock profit" in dec.exit_reason

    def test_9933_close_on_vol_shock_losing(self):
        """CLOSE triggered on vol shock + losing trade."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        dec = engine.evaluate_management(_good_input(
            open_trade_side="BUY", current_r_multiple=-0.2,
            atr_percentile=97.0))
        assert dec.exit_action == ExitAction.CLOSE.value
        assert "high_volatility" in dec.exit_reason

    def test_9933_reduce_on_vol_shock_profitable(self):
        """REDUCE triggered on vol shock + profitable trade."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        dec = engine.evaluate_management(_good_input(
            open_trade_side="BUY", current_r_multiple=0.3,
            atr_percentile=97.0))
        assert dec.exit_action == ExitAction.REDUCE.value
        assert "high_volatility" in dec.exit_reason


# ─── 15. Sprint 9.9.3.3 — Anti-overfit synthetic scenarios ──────────────────

class TestSprint9933AntiOverfit:
    """Anti-overfit tests using synthetic unseen scenarios.

    Governance should:
      - ALLOW strong winners (not over-filter)
      - BLOCK clear losers
      - THROTTLE borderline cases based on expected edge
    """

    def test_9933_hv_strong_alpha_allowed(self):
        """High vol + strong alpha should be ALLOWED (throttled, not blocked)."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(
            atr_percentile=92.0, meta_confidence=0.85, regime_confidence=0.85,
            spread_usd=0.30, expected_edge_usd=6.0,
        )
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True
        # Should be throttled due to vol zone
        assert dec.risk_multiplier <= 0.50

    def test_9933_hv_weak_alpha_blocked(self):
        """High vol + weak alpha should be BLOCKED."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(
            atr_percentile=92.0, meta_confidence=0.62, regime_confidence=0.60,
            spread_usd=0.40, expected_edge_usd=-3.0,
        )
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False

    def test_9933_ambiguous_with_confirmation_allowed(self):
        """Ambiguous candle + confirmation + strong meta should be ALLOWED."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(
            ambiguous_candle=True, confirmation_present=True,
            meta_confidence=0.78, regime_confidence=0.75,
            spread_usd=0.25, liquidity="GOOD",
            expected_edge_usd=5.0,
        )
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True

    def test_9933_ambiguous_no_confirmation_blocked(self):
        """Ambiguous candle + no confirmation should be BLOCKED."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(
            ambiguous_candle=True, confirmation_present=False,
            meta_confidence=0.60, regime_confidence=0.55,
            spread_usd=0.30, liquidity="NORMAL",
            expected_edge_usd=-2.0,
        )
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False

    def test_9933_flip_false_alarm_allowed_with_confirmation(self):
        """Regime flip false alarm (high prob but confirmed) should be ALLOWED (throttled)."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(
            regime_flip_probability=0.68, confirmation_present=True,
            meta_confidence=0.78, regime_confidence=0.78,
            expected_edge_usd=4.5,
        )
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True
        assert dec.risk_multiplier <= 0.50

    def test_9933_flip_true_reversal_blocked(self):
        """Regime flip true reversal (> 0.75) should be BLOCKED."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(
            regime_flip_probability=0.80, confirmation_present=False,
            meta_confidence=0.65, regime_confidence=0.50,
            expected_edge_usd=-5.0,
        )
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "hard block" in dec.block_reason

    def test_9933_hi_spread_hi_edge_allowed(self):
        """High spread + high expected edge should be ALLOWED (throttled)."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(
            spread_usd=0.65, expected_edge_usd=8.0,
            meta_confidence=0.80, regime_confidence=0.80,
        )
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True
        assert dec.risk_multiplier <= 0.50

    def test_9933_lo_spread_weak_alpha_blocked(self):
        """Low spread + weak alpha + no edge should be BLOCKED."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(
            spread_usd=0.20, meta_confidence=0.60,
            expected_edge_usd=-1.5,
        )
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False

    def test_9933_broker_poor_throttled_not_blocked(self):
        """Broker quality in throttle zone (50-70) should be ALLOWED with reduced risk."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(broker_quality=55.0,
                          meta_confidence=0.75, expected_edge_usd=2.0)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is True
        assert dec.risk_multiplier <= 0.50

    def test_9933_broker_poor_below_block_blocked(self):
        """Broker quality below hard block (< 50) should be BLOCKED."""
        engine = StressLossGovernanceEngine(AccountProfile.PROP_FIRM_STRICT.value)
        inp = _good_input(broker_quality=40.0,
                          meta_confidence=0.85, expected_edge_usd=5.0)
        dec = engine.evaluate_entry(inp)
        assert dec.allow_trade is False
        assert "hard block" in dec.block_reason
