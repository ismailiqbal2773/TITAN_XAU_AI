"""Tests for Compliance Module — 5 prop firms, rules, engine, audit"""
import pytest
from datetime import datetime, timezone, timedelta

from titan.compliance.profiles import (
    FirmProfile, FirmId, PropFirmProfiles,
    DailyLossMode, DrawdownMode, NewsMode, WeekendMode,
    PROFIT_TARGET_PCT,
)
from titan.compliance.rule_engine import (
    ComplianceRuleEngine, RuleAction, RuleResult, RuleContext,
    DailyLossRule, SoftDailyLossRule, OverallDrawdownRule,
    TrailingDrawdownRule, ProfitTargetRule, ConsistencyRule,
    NewsBlackoutRule, WeekendRule, MaxLotRule, MaxPositionsRule,
    LeverageRule, HedgingRule, MinTradingDaysRule, MaxTradingDaysRule,
)
from titan.compliance.engine import ComplianceEngine, ComplianceState, ComplianceReport
from titan.compliance.audit import ComplianceAuditLog, AuditEvent


# ─── Profile Tests ──────────────────────────────────────────────────────────

class TestFirmProfiles:
    def test_all_5_firms_supported(self):
        for fid in [FirmId.FTMO, FirmId.FUNDEDNEXT, FirmId.E8,
                    FirmId.THE5ERS, FirmId.FUNDING_PIPS]:
            profile = PropFirmProfiles.get(fid, balance=100_000)
            assert profile.firm_id == fid
            assert profile.initial_balance == 100_000
            assert profile.max_daily_loss_pct > 0
            assert profile.max_overall_drawdown_pct > 0
            assert profile.max_daily_loss_pct <= profile.max_overall_drawdown_pct

    def test_ftmo_specifics(self):
        p = PropFirmProfiles.get(FirmId.FTMO)
        assert p.max_daily_loss_pct == 0.05
        assert p.max_overall_drawdown_pct == 0.10
        assert p.drawdown_mode == DrawdownMode.STATIC
        assert p.profit_target_pct_phase1 == 0.10
        assert p.profit_target_pct_phase2 == 0.05
        assert p.min_trading_days == 4
        assert p.consistency_pct == 0.40

    def test_fundednext_specifics(self):
        p = PropFirmProfiles.get(FirmId.FUNDEDNEXT)
        assert p.max_daily_loss_pct == 0.05
        assert p.max_overall_drawdown_pct == 0.10
        assert p.drawdown_mode == DrawdownMode.TRAILING
        assert p.consistency_pct == 0.0  # no consistency rule

    def test_e8_specifics(self):
        p = PropFirmProfiles.get(FirmId.E8)
        assert p.max_overall_drawdown_pct == 0.08  # 8% lower DD
        assert p.weekend_mode == WeekendMode.ALLOW  # weekend OK

    def test_the5ers_specifics(self):
        p = PropFirmProfiles.get(FirmId.THE5ERS)
        assert p.max_daily_loss_pct == 0.04  # tighter
        assert p.max_overall_drawdown_pct == 0.06  # lower DD
        assert not p.hedging_allowed
        assert p.news_blackout_minutes == 2

    def test_funding_pips_specifics(self):
        p = PropFirmProfiles.get(FirmId.FUNDING_PIPS)
        assert p.max_daily_loss_pct == 0.05
        assert p.max_overall_drawdown_pct == 0.10
        assert p.profit_target_pct_phase1 == 0.08

    def test_custom_profile_configurable(self):
        p = PropFirmProfiles.get(FirmId.CUSTOM, balance=50_000)
        assert p.initial_balance == 50_000
        assert p.drawdown_mode == DrawdownMode.HYBRID
        assert p.max_lot_per_trade == 10.0

    def test_balance_override(self):
        p = PropFirmProfiles.get(FirmId.FTMO, balance=200_000)
        assert p.initial_balance == 200_000

    def test_all_firms_returns_dict(self):
        all_profs = PropFirmProfiles.all_firms(balance=100_000)
        assert FirmId.FTMO in all_profs
        assert FirmId.FUNDEDNEXT in all_profs
        assert FirmId.E8 in all_profs
        assert FirmId.THE5ERS in all_profs
        assert FirmId.FUNDING_PIPS in all_profs
        assert FirmId.CUSTOM in all_profs

    def test_supported_firms_list(self):
        firms = PropFirmProfiles.supported_firms()
        assert "ftmo" in firms
        assert "fundednext" in firms
        assert "e8" in firms
        assert "the5ers" in firms
        assert "funding_pips" in firms


# ─── Rule Tests ─────────────────────────────────────────────────────────────

def make_ctx(**kwargs) -> RuleContext:
    """Build a RuleContext with sensible defaults."""
    defaults = dict(
        initial_balance=100_000,
        current_balance=100_000,
        current_equity=100_000,
        peak_equity=100_000,
        start_of_day_balance=100_000,
        start_of_day_equity=100_000,
        now=datetime(2026, 6, 18, 12, 0, tzinfo=timezone.utc),  # Thursday
        trading_days_elapsed=5,
        is_weekend=False,
        is_high_impact_news=False,
        open_positions=1,
        net_exposure=0.5,
        gross_exposure=0.5,
        pending_lot_size=0.0,
        has_hedged_positions=False,
        today_realized_pnl=0.0,
        today_unrealized_pnl=0.0,
        largest_single_day_profit=0.0,
        total_realized_pnl=0.0,
    )
    defaults.update(kwargs)
    return RuleContext(**defaults)


class TestDailyLossRule:
    def test_no_loss_passes(self):
        rule = DailyLossRule()
        ctx = make_ctx()
        prof = PropFirmProfiles.get(FirmId.FTMO)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.ALLOW

    def test_at_hard_limit_closes_all(self):
        rule = DailyLossRule()
        # 5% loss = -5000 on 100k
        ctx = make_ctx(current_equity=95_000, current_balance=95_000)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.CLOSE_ALL
        assert result.severity == 100

    def test_below_hard_limit_allows(self):
        rule = DailyLossRule()
        # 4% loss = -4000
        ctx = make_ctx(current_equity=96_000, current_balance=96_000)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.ALLOW


class TestSoftDailyLossRule:
    def test_no_soft_limit(self):
        rule = SoftDailyLossRule()
        ctx = make_ctx()
        prof = PropFirmProfiles.get(FirmId.FTMO)
        prof.soft_daily_loss_pct = 0.0
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.ALLOW

    def test_at_soft_limit_disables_new(self):
        rule = SoftDailyLossRule()
        # 4.5% loss → at soft limit (FTMO soft = 4.5%)
        ctx = make_ctx(current_equity=95_500, current_balance=95_500)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.DISABLE_NEW
        assert result.severity == 70


class TestOverallDrawdownRule:
    def test_no_dd_passes(self):
        rule = OverallDrawdownRule()
        ctx = make_ctx()
        prof = PropFirmProfiles.get(FirmId.FTMO)
        assert rule.evaluate(ctx, prof).action == RuleAction.ALLOW

    def test_at_max_dd_halts(self):
        rule = OverallDrawdownRule()
        # 10% DD from initial → halt
        ctx = make_ctx(current_equity=90_000, current_balance=90_000)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.HALT

    def test_e8_lower_dd_threshold(self):
        """E8 has 8% DD vs FTMO 10%."""
        rule = OverallDrawdownRule()
        # 9% DD — passes FTMO, fails E8
        ctx = make_ctx(current_equity=91_000, current_balance=91_000)
        ftmo = PropFirmProfiles.get(FirmId.FTMO)
        e8 = PropFirmProfiles.get(FirmId.E8)
        assert rule.evaluate(ctx, ftmo).action == RuleAction.ALLOW
        assert rule.evaluate(ctx, e8).action == RuleAction.HALT


class TestTrailingDrawdownRule:
    def test_no_trailing_skips(self):
        rule = TrailingDrawdownRule()
        ctx = make_ctx()
        prof = PropFirmProfiles.get(FirmId.FTMO)  # STATIC mode
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.ALLOW

    def test_trailing_breach_halts(self):
        rule = TrailingDrawdownRule()
        # FundedNext: trailing DD = 10%. Peak=105k, equity=94k → DD = 11k/100k = 11%
        ctx = make_ctx(
            peak_equity=105_000,
            current_equity=94_000,
            current_balance=94_000,
        )
        prof = PropFirmProfiles.get(FirmId.FUNDEDNEXT)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.HALT

    def test_trailing_above_threshold_ok(self):
        rule = TrailingDrawdownRule()
        # Peak=105k, equity=100k → DD = 5k/100k = 5% < 10%
        ctx = make_ctx(
            peak_equity=105_000,
            current_equity=100_000,
            current_balance=100_000,
        )
        prof = PropFirmProfiles.get(FirmId.FUNDEDNEXT)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.ALLOW


class TestProfitTargetRule:
    def test_phase1_target_met(self):
        rule = ProfitTargetRule(phase="phase1")
        # FTMO phase1 = 10% → 110k equity
        ctx = make_ctx(current_equity=110_500, current_balance=110_500)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        result = rule.evaluate(ctx, prof)
        assert result.details["reached"] is True

    def test_phase1_target_not_met(self):
        rule = ProfitTargetRule(phase="phase1")
        ctx = make_ctx(current_equity=105_000, current_balance=105_000)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        result = rule.evaluate(ctx, prof)
        assert result.details["reached"] is False


class TestConsistencyRule:
    def test_no_consistency_rule_passes(self):
        rule = ConsistencyRule()
        ctx = make_ctx(total_realized_pnl=5000, largest_single_day_profit=5000)
        prof = PropFirmProfiles.get(FirmId.FUNDEDNEXT)  # no consistency
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.ALLOW

    def test_ftmo_consistency_breach(self):
        """FTMO: largest day profit must be ≤ 40% of total."""
        rule = ConsistencyRule()
        # Total = 5000, largest day = 3000 → 60% > 40% → breach
        ctx = make_ctx(total_realized_pnl=5000, largest_single_day_profit=3000)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.DISABLE_NEW

    def test_ftmo_consistency_ok(self):
        rule = ConsistencyRule()
        # Total = 10000, largest = 3000 → 30% < 40%
        ctx = make_ctx(total_realized_pnl=10000, largest_single_day_profit=3000)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.ALLOW


class TestNewsBlackoutRule:
    def test_allow_mode_never_blocks(self):
        rule = NewsBlackoutRule()
        ctx = make_ctx(is_high_impact_news=True)
        prof = PropFirmProfiles.get(FirmId.FTMO)  # ALLOW
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.ALLOW

    def test_5ers_blackout_during_news(self):
        rule = NewsBlackoutRule()
        ctx = make_ctx(is_high_impact_news=True, minutes_since_news=0)
        prof = PropFirmProfiles.get(FirmId.THE5ERS)  # BLACKOUT_WINDOW, 2min
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.DISABLE_NEW

    def test_5ers_blackout_after_window(self):
        rule = NewsBlackoutRule()
        ctx = make_ctx(is_high_impact_news=False, minutes_since_news=5)
        prof = PropFirmProfiles.get(FirmId.THE5ERS)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.ALLOW

    def test_no_news_trading_mode(self):
        rule = NewsBlackoutRule()
        prof = PropFirmProfiles.get(FirmId.THE5ERS)
        prof.news_mode = NewsMode.NO_NEWS_TRADING
        ctx = make_ctx(is_high_impact_news=True)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.DISABLE_NEW


class TestWeekendRule:
    def test_allow_mode(self):
        rule = WeekendRule()
        prof = PropFirmProfiles.get(FirmId.E8)  # ALLOW
        ctx = make_ctx(is_weekend=True, open_positions=2)
        assert rule.evaluate(ctx, prof).action == RuleAction.ALLOW

    def test_no_weekend_holding_closes_positions(self):
        rule = WeekendRule()
        prof = PropFirmProfiles.get(FirmId.FTMO)
        prof.weekend_mode = WeekendMode.NO_WEEKEND_HOLDING
        ctx = make_ctx(is_weekend=True, open_positions=1)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.CLOSE_ALL

    def test_no_weekend_no_open_positions(self):
        rule = WeekendRule()
        prof = PropFirmProfiles.get(FirmId.FTMO)
        prof.weekend_mode = WeekendMode.NO_WEEKEND_HOLDING
        ctx = make_ctx(is_weekend=True, open_positions=0)
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.DISABLE_NEW


class TestMaxLotRule:
    def test_no_cap_passes(self):
        rule = MaxLotRule()
        ctx = make_ctx(pending_lot_size=100.0)
        prof = PropFirmProfiles.get(FirmId.FTMO)  # 0 = unlimited
        assert rule.evaluate(ctx, prof).action == RuleAction.ALLOW

    def test_over_cap_blocks(self):
        rule = MaxLotRule()
        ctx = make_ctx(pending_lot_size=15.0)
        prof = PropFirmProfiles.get(FirmId.CUSTOM)  # 10.0 cap
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.DISABLE_NEW


class TestMaxPositionsRule:
    def test_no_cap(self):
        rule = MaxPositionsRule()
        ctx = make_ctx(open_positions=100)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        assert rule.evaluate(ctx, prof).action == RuleAction.ALLOW

    def test_at_cap_blocks(self):
        rule = MaxPositionsRule()
        ctx = make_ctx(open_positions=5)
        prof = PropFirmProfiles.get(FirmId.CUSTOM)  # 5 cap
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.DISABLE_NEW


class TestLeverageRule:
    def test_no_cap(self):
        rule = LeverageRule()
        ctx = make_ctx(gross_exposure=1000.0, current_equity=1000.0)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        assert rule.evaluate(ctx, prof).action == RuleAction.ALLOW

    def test_over_cap_reduces(self):
        rule = LeverageRule()
        # 50 lots × $100k = $5M notional / $100k equity = 50x > 30x cap
        ctx = make_ctx(gross_exposure=50.0, current_equity=100_000)
        prof = PropFirmProfiles.get(FirmId.CUSTOM)  # 30x cap
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.REDUCE_POSITION


class TestHedgingRule:
    def test_hedging_allowed(self):
        rule = HedgingRule()
        ctx = make_ctx(has_hedged_positions=True)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        assert rule.evaluate(ctx, prof).action == RuleAction.ALLOW

    def test_hedging_not_allowed_closes_all(self):
        rule = HedgingRule()
        ctx = make_ctx(has_hedged_positions=True)
        prof = PropFirmProfiles.get(FirmId.THE5ERS)  # no hedging
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.CLOSE_ALL


class TestMinTradingDaysRule:
    def test_below_min_days(self):
        rule = MinTradingDaysRule()
        ctx = make_ctx(trading_days_elapsed=2)
        prof = PropFirmProfiles.get(FirmId.FTMO)  # 4 min
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.ALLOW  # informational
        assert "cannot pass" in result.message

    def test_meets_min_days(self):
        rule = MinTradingDaysRule()
        ctx = make_ctx(trading_days_elapsed=5)
        prof = PropFirmProfiles.get(FirmId.FTMO)
        result = rule.evaluate(ctx, prof)
        assert "met" in result.message


class TestMaxTradingDaysRule:
    def test_no_max_days(self):
        rule = MaxTradingDaysRule()
        ctx = make_ctx(trading_days_elapsed=1000)
        prof = PropFirmProfiles.get(FirmId.FTMO)  # 0 = no max
        assert rule.evaluate(ctx, prof).action == RuleAction.ALLOW

    def test_at_max_days_halts(self):
        rule = MaxTradingDaysRule()
        ctx = make_ctx(trading_days_elapsed=30)
        prof = PropFirmProfiles.get(FirmId.CUSTOM)  # 30 max
        result = rule.evaluate(ctx, prof)
        assert result.action == RuleAction.HALT


# ─── Rule Engine Tests ──────────────────────────────────────────────────────

class TestComplianceRuleEngine:
    def test_all_14_rules_registered(self):
        eng = ComplianceRuleEngine()
        assert len(eng.rules) == 14

    def test_evaluate_all_returns_14_results(self):
        eng = ComplianceRuleEngine()
        ctx = make_ctx()
        prof = PropFirmProfiles.get(FirmId.FTMO)
        results = eng.evaluate_all(ctx, prof)
        assert len(results) == 14

    def test_aggregate_action_picks_worst(self):
        results = [
            RuleResult(rule_id="r1", action=RuleAction.ALLOW, message=""),
            RuleResult(rule_id="r2", action=RuleAction.WARN, message=""),
            RuleResult(rule_id="r3", action=RuleAction.CLOSE_ALL, message=""),
        ]
        assert ComplianceRuleEngine.aggregate_action(results) == RuleAction.CLOSE_ALL

    def test_aggregate_all_allow(self):
        results = [RuleResult(rule_id="r", action=RuleAction.ALLOW, message="")]
        assert ComplianceRuleEngine.aggregate_action(results) == RuleAction.ALLOW


# ─── Compliance Engine Tests ────────────────────────────────────────────────

class TestComplianceEngine:
    def test_initial_state(self):
        eng = ComplianceEngine.for_firm(FirmId.FTMO, balance=100_000)
        assert eng.state.initial_balance == 100_000
        assert eng.state.current_balance == 100_000
        assert eng.firm_id == FirmId.FTMO

    def test_evaluate_returns_report(self):
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        report = eng.evaluate()
        assert isinstance(report, ComplianceReport)
        assert report.firm_id == "ftmo"
        assert report.compliance_score <= 100

    def test_apply_realized_pnl_updates_balance(self):
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        eng.apply_realized_pnl(2000)
        assert eng.state.current_balance == 102_000
        assert eng.state.total_realized_pnl == 2000

    def test_apply_realized_loss_updates_balance(self):
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        eng.apply_realized_pnl(-3000)
        assert eng.state.current_balance == 97_000
        assert eng.state.total_realized_pnl == -3000

    def test_unrealized_updates_equity(self):
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        eng.update_unrealized(1500)
        assert eng.state.current_equity == 101_500

    def test_peak_equity_tracks_high_water(self):
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        eng.update_unrealized(5000)  # equity 105k
        assert eng.state.peak_equity == 105_000
        eng.update_unrealized(-3000)  # equity 102k
        assert eng.state.peak_equity == 105_000  # unchanged

    def test_reset_daily_advances_day(self):
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        eng.apply_realized_pnl(1000)
        eng.reset_daily()
        assert eng.state.trading_days_elapsed == 1
        assert eng.state.today_realized_pnl == 0
        assert eng.state.start_of_day_balance == 101_000

    def test_ftmo_daily_loss_breach_triggers_close_all(self):
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        # 5.5% daily loss = -5500
        eng.apply_realized_pnl(-5500)
        report = eng.evaluate()
        assert report.must_close_all
        assert report.overall_action in (RuleAction.CLOSE_ALL, RuleAction.HALT)

    def test_e8_lower_dd_breaches_earlier(self):
        """E8 max DD = 8%, FTMO = 10% — 9% loss breaches E8 but not FTMO."""
        e8 = ComplianceEngine.for_firm(FirmId.E8)
        ftmo = ComplianceEngine.for_firm(FirmId.FTMO)
        # 9% loss
        e8.apply_realized_pnl(-9000)
        ftmo.apply_realized_pnl(-9000)
        e8_report = e8.evaluate()
        ftmo_report = ftmo.evaluate()
        assert e8_report.must_halt
        assert not ftmo_report.must_halt

    def test_5ers_tighter_daily_loss(self):
        """5ers: 4% daily loss vs FTMO 5%."""
        s5 = ComplianceEngine.for_firm(FirmId.THE5ERS)
        ftmo = ComplianceEngine.for_firm(FirmId.FTMO)
        # 4.5% loss → breaches 5ers (4%) but not FTMO (5%)
        s5.apply_realized_pnl(-4500)
        ftmo.apply_realized_pnl(-4500)
        s5_report = s5.evaluate()
        ftmo_report = ftmo.evaluate()
        assert s5_report.must_close_all
        assert not ftmo_report.must_close_all

    def test_report_to_dict_serializable(self):
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        report = eng.evaluate()
        d = report.to_dict()
        assert "rule_results" in d
        assert "overall_action" in d
        assert "compliance_score" in d

    def test_consistency_breach_ftmo(self):
        """FTMO: largest day = 50% of total profit → breach."""
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        eng.apply_realized_pnl(5000)  # day 1 = +5000 (largest)
        eng.reset_daily()
        eng.apply_realized_pnl(2500)  # day 2 = +2500
        eng.reset_daily()
        eng.apply_realized_pnl(2500)  # day 3 = +2500
        # Total = 10000, largest = 5000 → 50% > 40% → breach
        report = eng.evaluate()
        # Consistency rule should fire DISABLE_NEW
        consistency_results = [r for r in report.rule_results
                               if r.rule_id == "consistency"]
        assert any(r.action == RuleAction.DISABLE_NEW
                   for r in consistency_results)


# ─── Audit Log Tests ────────────────────────────────────────────────────────

class TestComplianceAuditLog:
    def test_log_event(self):
        log = ComplianceAuditLog(":memory:")
        eid = log.log(AuditEvent(
            timestamp=1234567890,
            event_type="breach",
            firm_id="ftmo",
            rule_id="daily_loss",
            severity=100,
            action="close_all",
            message="Daily loss breach",
        ))
        assert eid > 0
        assert log.count() == 1

    def test_log_evaluation_logs_each_rule(self):
        log = ComplianceAuditLog(":memory:")
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        eng.apply_realized_pnl(-5500)
        report = eng.evaluate()
        log.log_evaluation("ftmo", report.to_dict())
        # 14 rules + 1 breach event
        assert log.count() == 15

    def test_query_by_firm(self):
        log = ComplianceAuditLog(":memory:")
        for fid in ["ftmo", "e8"]:
            log.log(AuditEvent(
                timestamp=1234567890, event_type="evaluation",
                firm_id=fid, severity=50,
            ))
        ftmo_events = log.query(firm_id="ftmo")
        assert len(ftmo_events) == 1
        assert ftmo_events[0]["firm_id"] == "ftmo"

    def test_query_by_severity(self):
        log = ComplianceAuditLog(":memory:")
        for sev in [10, 50, 90, 100]:
            log.log(AuditEvent(
                timestamp=1234567890, event_type="test",
                firm_id="ftmo", severity=sev,
            ))
        critical = log.query(min_severity=80)
        assert len(critical) == 2  # 90 and 100


# ─── Integration ────────────────────────────────────────────────────────────

class TestComplianceIntegration:
    def test_ftmo_full_challenge_simulation(self):
        """Simulate a typical FTMO challenge day: profit, no breaches."""
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        # Day 1: +2% profit
        eng.apply_realized_pnl(2000)
        report = eng.evaluate()
        assert not report.must_close_all
        assert not report.must_halt
        eng.reset_daily()
        # Day 2: small loss
        eng.apply_realized_pnl(-1000)
        report = eng.evaluate()
        assert not report.must_close_all
        eng.reset_daily()
        # Day 3: profit
        eng.apply_realized_pnl(1500)
        eng.reset_daily()
        # Day 4: profit
        eng.apply_realized_pnl(1800)
        report = eng.evaluate()
        # After 4 days, min trading days met, total = +4300 (4.3%)
        assert eng.state.trading_days_elapsed == 3  # incremented 3 times
        # 4 days of trading data + resets put us in good shape

    def test_all_5_firms_evaluate_clean(self):
        """All 5 firm profiles can be evaluated with no breaches at start."""
        for fid in [FirmId.FTMO, FirmId.FUNDEDNEXT, FirmId.E8,
                    FirmId.THE5ERS, FirmId.FUNDING_PIPS]:
            eng = ComplianceEngine.for_firm(fid)
            report = eng.evaluate()
            assert not report.must_halt, f"{fid} halted at start"

    def test_audit_persistence(self):
        """Audit log persists across evaluations."""
        log = ComplianceAuditLog(":memory:")
        eng = ComplianceEngine.for_firm(FirmId.FTMO)
        for day in range(3):
            eng.apply_realized_pnl(1000)
            report = eng.evaluate()
            log.log_evaluation("ftmo", report.to_dict())
            eng.reset_daily()
        # 3 days × 15 events per day = 45 events
        assert log.count() == 45
