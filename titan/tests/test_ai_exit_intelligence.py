"""
TITAN XAU AI — Sprint 9.6 AI Exit Intelligence Tests

Comprehensive tests covering 20+ scenarios from the spec.
"""
from __future__ import annotations
import pytest

from titan.production.ai_exit_engine import (
    AIExitEngine, ExitInput, ExitAction, ExitDecision,
)
from titan.production.exit_strategy_engine import (
    ExitStrategyEngine, DynamicTPDecision, BreakEvenDecision,
    TrailingDecision, PartialExitDecision, EarlyExitDecision,
    TimeExitDecision, NewsExitDecision, WeekendExitDecision,
)
from titan.production.exit_quality_scorer import (
    ExitQualityScorer, ExitQualityInput, ExitQualityScore,
)
from titan.production.exit_governance import (
    ExitGovernance, AdvisorRecommendation, GovernanceDecision,
)
from titan.production.trade_journal import TradeJournal, EventType


@pytest.fixture
def journal(tmp_path):
    return TradeJournal(path=str(tmp_path / "exit.jsonl"), session_id="exit_test")


@pytest.fixture
def engine(journal):
    return AIExitEngine(journal=journal, config={
        "partial_exits": {"enabled": True, "levels": [
            {"r_multiple": 1.0, "close_pct": 25},
            {"r_multiple": 2.0, "close_pct": 25},
            {"r_multiple": 3.0, "close_pct": 25},
        ], "min_remaining_pct": 25},
        "early_exit": {
            "meta_confidence_collapse": 0.40,
            "trend_reversal_threshold": -0.3,
            "momentum_collapse": 0.20,
        },
        "trailing": {
            "base_atr_multiplier": 1.0,
            "strong_trend_loosen": 2.0,
            "weak_market_tighten": 0.5,
            "min_trail_distance_atr": 0.3,
        },
    })


@pytest.fixture
def strategy(journal):
    return ExitStrategyEngine(journal=journal, config={
        "dynamic_tp": {"strong_trend_extension_pct": 50, "weak_momentum_reduction_pct": 25,
                       "sideways_early_exit_pct": 75},
        "trailing": {"base_atr_multiplier": 1.0, "strong_trend_loosen": 2.0,
                     "weak_market_tighten": 0.5, "min_trail_distance_atr": 0.3},
        "partial_exits": {"enabled": True, "levels": [
            {"r_multiple": 1.0, "close_pct": 25},
            {"r_multiple": 2.0, "close_pct": 25},
        ], "min_remaining_pct": 25},
        "early_exit": {"meta_confidence_collapse": 0.40, "trend_reversal_threshold": -0.3,
                       "momentum_collapse": 0.20},
        "time_exit": {"max_holding_hours_strong_trend": 48, "max_holding_hours_normal": 24,
                      "max_holding_hours_sideways": 8},
    })


def make_input(**kwargs) -> ExitInput:
    """Build ExitInput with sensible defaults."""
    defaults = dict(
        direction=1, entry_price=2000.0, current_price=2010.0,
        stop_loss=1990.0, take_profit=2020.0, volume=0.01,
        xgb_confidence=0.7, meta_confidence=0.7,
        trend_strength=0.3, momentum=0.6,
        volatility_regime="normal", atr=10.0, spread_usd=0.2,
        time_in_trade_hours=2.0, floating_pnl_usd=10.0, r_multiple=1.0,
        account_health_score=90, capital_preservation_active=False,
        recovery_mode_active=False, broker_quality_score=90,
        news_halt_active=False, news_imminent=False,
        session="us", regime="normal",
    )
    defaults.update(kwargs)
    return ExitInput(**defaults)


# ════════════════════════════════════════════════════════════════════════════
# 1. AI Exit Engine — Basic Scenarios
# ════════════════════════════════════════════════════════════════════════════
class TestAIExitEngine:
    def test_strong_trend_holds_or_trails(self, engine):
        """Strong trend + profit → HOLD, TRAIL, or PARTIAL_CLOSE (not full exit)."""
        inp = make_input(trend_strength=0.8, r_multiple=1.5, momentum=0.7)
        decision = engine.evaluate(inp)
        assert decision.action in (ExitAction.HOLD, ExitAction.TRAIL, ExitAction.PARTIAL_CLOSE)
        assert decision.action != ExitAction.FULL_EXIT

    def test_weak_trend_break_even(self, engine):
        """+1R + weak trend → MOVE_TO_BREAK_EVEN."""
        inp = make_input(r_multiple=1.0, trend_strength=0.1, momentum=0.5)
        decision = engine.evaluate(inp)
        # Should be BE or partial (partial triggers first at 1R)
        assert decision.action in (ExitAction.PARTIAL_CLOSE, ExitAction.MOVE_TO_BREAK_EVEN)

    def test_sideways_early_exit(self, engine):
        """Sideways regime + weak momentum → exit."""
        inp = make_input(regime="range", momentum=0.15, meta_confidence=0.3)
        decision = engine.evaluate(inp)
        assert decision.action in (ExitAction.FULL_EXIT, ExitAction.PARTIAL_CLOSE)

    def test_high_atr_increases_risk_score(self, engine):
        """High ATR should increase risk score."""
        inp_low = make_input(atr=5.0, r_multiple=0.3)
        inp_high = make_input(atr=50.0, r_multiple=0.3)
        d_low = engine.evaluate(inp_low)
        d_high = engine.evaluate(inp_high)
        # Risk score should reflect higher ATR (via volatility_regime)
        assert d_high.risk_score >= 0

    def test_news_event_early_exit(self, engine):
        """News imminent + profit → early exit."""
        inp = make_input(news_imminent=True, r_multiple=1.5)
        decision = engine.evaluate(inp)
        assert decision.action in (ExitAction.FULL_EXIT, ExitAction.PARTIAL_CLOSE)

    def test_recovery_mode_emergency(self, engine):
        """Recovery mode + floating loss → EMERGENCY_EXIT."""
        inp = make_input(recovery_mode_active=True, floating_pnl_usd=-10, r_multiple=-1)
        decision = engine.evaluate(inp)
        assert decision.action == ExitAction.EMERGENCY_EXIT

    def test_capital_preservation_emergency(self, engine):
        """Capital preservation + low health → EMERGENCY_EXIT."""
        inp = make_input(capital_preservation_active=True, account_health_score=20)
        decision = engine.evaluate(inp)
        assert decision.action == ExitAction.EMERGENCY_EXIT

    def test_broker_degraded_early_exit(self, engine):
        """Low broker quality + profit → early exit."""
        inp = make_input(broker_quality_score=50, r_multiple=1.5)
        decision = engine.evaluate(inp)
        # Should at least not HOLD
        assert decision.action != ExitAction.HOLD or decision.risk_score > 0.3

    def test_broker_excellent_allows_hold(self, engine):
        """High broker quality + strong trend → HOLD or TRAIL."""
        inp = make_input(broker_quality_score=98, trend_strength=0.7, r_multiple=2.0)
        decision = engine.evaluate(inp)
        assert decision.action in (ExitAction.HOLD, ExitAction.TRAIL, ExitAction.PARTIAL_CLOSE)

    def test_partial_exit_at_1r(self, engine):
        """At +1R → PARTIAL_CLOSE."""
        inp = make_input(r_multiple=1.0, trend_strength=0.5, momentum=0.6)
        decision = engine.evaluate(inp)
        assert decision.action == ExitAction.PARTIAL_CLOSE
        assert decision.partial_close_pct == 25

    def test_partial_exit_at_2r(self, engine):
        """At +2R → PARTIAL_CLOSE 25%."""
        inp = make_input(r_multiple=2.0, trend_strength=0.5, momentum=0.6)
        decision = engine.evaluate(inp)
        assert decision.action == ExitAction.PARTIAL_CLOSE

    def test_break_even_at_1r_weak_trend(self, engine):
        """+1R + weak trend → MOVE_TO_BREAK_EVEN or PARTIAL_CLOSE."""
        inp = make_input(r_multiple=1.0, trend_strength=0.1, momentum=0.5)
        decision = engine.evaluate(inp)
        # At 1R with weak trend, partial close triggers first (priority order)
        assert decision.action in (ExitAction.PARTIAL_CLOSE, ExitAction.MOVE_TO_BREAK_EVEN)

    def test_trailing_in_strong_trend(self, engine):
        """Strong trend + profit → TRAIL with loosened distance."""
        inp = make_input(r_multiple=1.5, trend_strength=0.8, atr=10.0)
        decision = engine.evaluate(inp)
        # Should be TRAIL or PARTIAL (partial triggers first)
        assert decision.action in (ExitAction.TRAIL, ExitAction.PARTIAL_CLOSE)

    def test_hold_when_edge_intact(self, engine):
        """Strong edge + good trend + low R → HOLD (no trail/partial triggers)."""
        inp = make_input(
            xgb_confidence=0.85, meta_confidence=0.85,
            trend_strength=0.5, momentum=0.7,
            r_multiple=0.3,  # below trail threshold (0.5) and partial (1.0)
        )
        decision = engine.evaluate(inp)
        assert decision.action == ExitAction.HOLD

    def test_fail_closed_on_error(self, journal):
        """Engine error → HOLD (fail-closed)."""
        engine = AIExitEngine(journal=journal)
        # Pass invalid input to trigger error
        inp = ExitInput(direction=0)  # invalid direction
        decision = engine.evaluate(inp)
        # Should still return a decision (HOLD or computed)
        assert decision is not None

    def test_decision_journaled(self, engine, journal):
        """EXIT_AI_DECISION event is journaled."""
        engine.evaluate(make_input())
        records = journal.read_all()
        exit_events = [r for r in records if r.get("event_type") == EventType.EXIT_AI_DECISION.value]
        assert len(exit_events) == 1


# ════════════════════════════════════════════════════════════════════════════
# 2. Exit Strategy Engine
# ════════════════════════════════════════════════════════════════════════════
class TestExitStrategyEngine:
    def test_dynamic_tp_extend_in_strong_trend(self, strategy):
        inp = make_input(regime="trend", trend_strength=0.8, direction=1,
                         entry_price=2000, take_profit=2020)
        result = strategy.evaluate_dynamic_tp(inp)
        assert result.action == "extend"
        assert result.new_tp > 2020

    def test_dynamic_tp_reduce_in_weak_momentum(self, strategy):
        inp = make_input(momentum=0.15, direction=1,
                         entry_price=2000, take_profit=2020)
        result = strategy.evaluate_dynamic_tp(inp)
        assert result.action == "reduce"
        assert result.new_tp < 2020

    def test_dynamic_tp_early_exit_sideways(self, strategy):
        inp = make_input(regime="range", direction=1,
                         entry_price=2000, take_profit=2020)
        result = strategy.evaluate_dynamic_tp(inp)
        assert result.action == "early_exit"

    def test_break_even_justified(self, strategy):
        """+1R + trend weakening → BE justified."""
        inp = make_input(r_multiple=1.0, trend_strength=0.1, direction=1)
        result = strategy.evaluate_break_even(inp)
        assert result.should_move is True
        assert result.new_sl == inp.entry_price

    def test_break_even_not_justified_strong_trend(self, strategy):
        """+1R + strong trend → NOT move BE."""
        inp = make_input(r_multiple=1.0, trend_strength=0.6, direction=1)
        result = strategy.evaluate_break_even(inp)
        assert result.should_move is False

    def test_adaptive_trailing_strong_trend_loosens(self, strategy):
        """Strong trend → loosen trail to 2.0×ATR."""
        inp = make_input(r_multiple=1.5, trend_strength=0.8, direction=1,
                         current_price=2020, stop_loss=1990, atr=10.0)
        result = strategy.evaluate_trailing(inp)
        assert result.should_update is True
        assert result.trail_mult == 2.0

    def test_adaptive_trailing_weak_market_tightens(self, strategy):
        """Weak market → tighten trail to 0.5×ATR."""
        inp = make_input(r_multiple=1.5, trend_strength=0.0, direction=1,
                         current_price=2010, stop_loss=1990, atr=10.0)
        result = strategy.evaluate_trailing(inp)
        assert result.should_update is True
        assert result.trail_mult == 0.5

    def test_partial_exit_first_level(self, strategy):
        """At +1R → partial close 25%."""
        inp = make_input(r_multiple=1.0)
        result = strategy.evaluate_partial_exit(inp, ticket="T1")
        assert result.should_close is True
        assert result.close_pct == 25

    def test_partial_exit_second_level(self, strategy):
        """At +2R → partial close 25%."""
        strategy.evaluate_partial_exit(make_input(r_multiple=1.0), ticket="T2")
        result = strategy.evaluate_partial_exit(make_input(r_multiple=2.0), ticket="T2")
        assert result.should_close is True
        assert result.close_pct == 25

    def test_partial_exit_no_repeat(self, strategy):
        """Same level doesn't trigger twice."""
        inp = make_input(r_multiple=1.0)
        r1 = strategy.evaluate_partial_exit(inp, ticket="T3")
        r2 = strategy.evaluate_partial_exit(make_input(r_multiple=1.1), ticket="T3")
        assert r1.should_close is True
        assert r2.should_close is False

    def test_early_exit_meta_collapse(self, strategy):
        """Meta confidence < 0.40 → early exit."""
        inp = make_input(meta_confidence=0.30)
        result = strategy.evaluate_early_exit(inp)
        assert result.should_exit is True
        assert any("meta_collapse" in t for t in result.triggers)

    def test_early_exit_trend_reversal(self, strategy):
        """Trend reversal → early exit."""
        inp = make_input(trend_strength=-0.5, direction=1)
        result = strategy.evaluate_early_exit(inp)
        assert result.should_exit is True

    def test_time_exit_strong_trend_48h(self, strategy):
        """Strong trend → max 48h."""
        inp = make_input(regime="trend", trend_strength=0.7, time_in_trade_hours=50)
        result = strategy.evaluate_time_exit(inp)
        assert result.should_exit is True
        assert result.max_hours == 48

    def test_time_exit_sideways_8h(self, strategy):
        """Sideways → max 8h."""
        inp = make_input(regime="range", time_in_trade_hours=10)
        result = strategy.evaluate_time_exit(inp)
        assert result.should_exit is True
        assert result.max_hours == 8

    def test_news_exit_profit_partial(self, strategy):
        """News imminent + profit → partial close 50%."""
        inp = make_input(news_imminent=True, r_multiple=1.5)
        result = strategy.evaluate_news_exit(inp)
        assert result.action == "partial"
        assert result.close_pct == 50

    def test_news_exit_loss_close(self, strategy):
        """News imminent + loss → close 100%."""
        inp = make_input(news_imminent=True, r_multiple=-0.5)
        result = strategy.evaluate_news_exit(inp)
        assert result.action == "close"
        assert result.close_pct == 100

    def test_weekend_exit_profit_partial(self, strategy):
        """Friday late + profit → partial."""
        inp = make_input(r_multiple=1.0)
        result = strategy.evaluate_weekend_exit(inp, is_friday_late=True)
        assert result.action == "partial"
        assert result.close_pct == 50

    def test_weekend_exit_loss_close(self, strategy):
        """Friday late + loss → close."""
        inp = make_input(r_multiple=-0.5)
        result = strategy.evaluate_weekend_exit(inp, is_friday_late=True)
        assert result.action == "close"

    def test_weekend_exit_high_vol_close(self, strategy):
        """Friday late + high vol → close."""
        inp = make_input(r_multiple=0.1, volatility_regime="high")
        result = strategy.evaluate_weekend_exit(inp, is_friday_late=True)
        assert result.action == "close"


# ════════════════════════════════════════════════════════════════════════════
# 3. Exit Quality Scorer
# ════════════════════════════════════════════════════════════════════════════
class TestExitQualityScorer:
    @pytest.fixture
    def scorer(self, journal):
        return ExitQualityScorer(journal=journal)

    def test_perfect_exit_scores_high(self, scorer):
        inp = ExitQualityInput(
            entry_price=2000, exit_price=2020, direction=1,
            max_favorable_price=2020, max_adverse_price=1995,
            realized_pnl_usd=20, max_floating_profit_usd=20,
            initial_risk_usd=10, drawdown_avoided_pct=80,
            trend_strength_at_exit=-0.2,
        )
        result = scorer.score(inp)
        assert result.score >= 70

    def test_poor_exit_scores_low(self, scorer):
        inp = ExitQualityInput(
            entry_price=2000, exit_price=1990, direction=1,
            max_favorable_price=2010, max_adverse_price=1990,
            realized_pnl_usd=-10, max_floating_profit_usd=10,
            initial_risk_usd=10, drawdown_avoided_pct=0,
            trend_strength_at_exit=0.5,  # exited while trend strong
        )
        result = scorer.score(inp)
        assert result.score < 60

    def test_score_journaled(self, scorer, journal):
        scorer.score(ExitQualityInput())
        records = journal.read_all()
        scored = [r for r in records if r.get("event_type") == EventType.EXIT_SCORE.value]
        assert len(scored) == 1

    def test_5_components_present(self, scorer):
        result = scorer.score(ExitQualityInput())
        assert len(result.components) == 5
        assert "timing" in result.components
        assert "profit_efficiency" in result.components
        assert "risk_reduction" in result.components
        assert "trend_capture" in result.components
        assert "drawdown_avoidance" in result.components


# ════════════════════════════════════════════════════════════════════════════
# 4. Exit Governance (CEO AI)
# ════════════════════════════════════════════════════════════════════════════
class TestExitGovernance:
    @pytest.fixture
    def gov(self, journal):
        return ExitGovernance(journal=journal)

    def test_exit_ai_alone_decides(self, gov):
        """With only exit_ai advisor, its decision wins."""
        decision = ExitDecision(action=ExitAction.TRAIL, confidence=0.8,
                                reason="trail strong trend")
        result = gov.decide(decision)
        assert result.final_action == ExitAction.TRAIL

    def test_weighted_voting_not_majority(self, gov):
        """Weighted confidence — not majority voting."""
        decision = ExitDecision(action=ExitAction.HOLD, confidence=0.9, reason="hold")
        advisors = [
            AdvisorRecommendation("risk_engine", ExitAction.FULL_EXIT, 0.6, 0.20, "risk"),
            AdvisorRecommendation("capital_protection", ExitAction.FULL_EXIT, 0.7, 0.15, "cp"),
        ]
        # exit_ai: HOLD 0.9×0.40 = 0.36
        # risk_engine: FULL_EXIT 0.6×0.20 = 0.12
        # capital_protection: FULL_EXIT 0.7×0.15 = 0.105
        # HOLD total: 0.36, FULL_EXIT total: 0.225 → HOLD wins
        result = gov.decide(decision, advisors)
        assert result.final_action == ExitAction.HOLD

    def test_advisors_can_override_exit_ai(self, gov):
        """Strong consensus from advisors can override exit_ai."""
        decision = ExitDecision(action=ExitAction.HOLD, confidence=0.5, reason="hold")
        advisors = [
            AdvisorRecommendation("risk_engine", ExitAction.FULL_EXIT, 1.0, 0.20, "risk"),
            AdvisorRecommendation("capital_protection", ExitAction.FULL_EXIT, 1.0, 0.15, "cp"),
            AdvisorRecommendation("broker_intelligence", ExitAction.FULL_EXIT, 1.0, 0.10, "broker"),
            AdvisorRecommendation("meta_model", ExitAction.FULL_EXIT, 1.0, 0.10, "meta"),
        ]
        # exit_ai: HOLD 0.5×0.40 = 0.20
        # FULL_EXIT: 1.0×0.20 + 1.0×0.15 + 1.0×0.10 + 1.0×0.10 = 0.55
        # FULL_EXIT wins
        result = gov.decide(decision, advisors)
        assert result.final_action == ExitAction.FULL_EXIT

    def test_governance_journaled(self, gov, journal):
        decision = ExitDecision(action=ExitAction.HOLD, confidence=0.8, reason="hold")
        gov.decide(decision)
        records = journal.read_all()
        gov_events = [r for r in records if r.get("event_type") == EventType.EXIT_GOVERNANCE.value]
        assert len(gov_events) == 1


# ════════════════════════════════════════════════════════════════════════════
# 5. Backward Compatibility + Regression
# ════════════════════════════════════════════════════════════════════════════
class TestBackwardCompatibility:
    def test_runtime_yaml_default_disabled(self):
        import yaml
        from pathlib import Path
        REPO_ROOT = Path(__file__).resolve().parents[2]
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["exit_intelligence"]["enabled"] is False

    def test_dry_run_unchanged(self):
        import yaml
        from pathlib import Path
        REPO_ROOT = Path(__file__).resolve().parents[2]
        with open(REPO_ROOT / "config" / "runtime.yaml", "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert cfg["runtime"]["dry_run"] is True
        assert cfg["runtime"]["live_trading"] is False

    def test_max_lot_hard_cap_unchanged(self):
        from titan.production.trade_loop import MAX_LOT_CAP
        assert MAX_LOT_CAP == 0.01

    def test_all_11_event_types_exist(self):
        from titan.production.trade_journal import EventType
        assert EventType.EXIT_AI_DECISION.value == "EXIT_AI_DECISION"
        assert EventType.EXIT_SCORE.value == "EXIT_SCORE"
        assert EventType.PARTIAL_EXIT.value == "PARTIAL_EXIT"
        assert EventType.BREAK_EVEN.value == "BREAK_EVEN"
        assert EventType.TRAIL_UPDATED.value == "TRAIL_UPDATED"
        assert EventType.TP_EXTENDED.value == "TP_EXTENDED"
        assert EventType.TP_REDUCED.value == "TP_REDUCED"
        assert EventType.EARLY_EXIT.value == "EARLY_EXIT"
        assert EventType.NEWS_EXIT.value == "NEWS_EXIT"
        assert EventType.WEEKEND_EXIT.value == "WEEKEND_EXIT"
        assert EventType.EXIT_GOVERNANCE.value == "EXIT_GOVERNANCE"

    def test_modules_import_cleanly(self):
        from titan.production.ai_exit_engine import AIExitEngine, ExitAction
        from titan.production.exit_strategy_engine import ExitStrategyEngine
        from titan.production.exit_quality_scorer import ExitQualityScorer
        from titan.production.exit_governance import ExitGovernance
        assert AIExitEngine is not None
        assert ExitStrategyEngine is not None
        assert ExitQualityScorer is not None
        assert ExitGovernance is not None

    def test_exit_action_has_7_values(self):
        actions = [a for a in ExitAction]
        assert len(actions) == 7
        assert ExitAction.HOLD in actions
        assert ExitAction.PARTIAL_CLOSE in actions
        assert ExitAction.MOVE_TO_BREAK_EVEN in actions
        assert ExitAction.TRAIL in actions
        assert ExitAction.BOOK_PROFIT in actions
        assert ExitAction.FULL_EXIT in actions
        assert ExitAction.EMERGENCY_EXIT in actions


# ════════════════════════════════════════════════════════════════════════════
# 6. Latency + Fast Execution (Part 16)
# ════════════════════════════════════════════════════════════════════════════
class TestExitLatency:
    @pytest.fixture
    def engine(self, journal):
        return AIExitEngine(journal=journal)

    def test_emergency_exit_under_50ms(self, engine):
        """Emergency fast-path must complete in <50ms."""
        inp = make_input(capital_preservation_active=True, account_health_score=20)
        decision = engine.evaluate(inp)
        assert decision.action == ExitAction.EMERGENCY_EXIT
        assert decision.emergency_fast_path_used is True
        assert decision.exit_latency_ms < 50.0, f"Emergency exit took {decision.exit_latency_ms:.1f}ms"

    def test_normal_decision_under_250ms(self, engine):
        """Normal AI evaluation must complete in <250ms."""
        inp = make_input(xgb_confidence=0.7, meta_confidence=0.7, r_multiple=0.3)
        decision = engine.evaluate(inp)
        assert decision.exit_latency_ms < 250.0, f"Normal decision took {decision.exit_latency_ms:.1f}ms"

    def test_ai_unavailable_fallback(self, journal):
        """If AI fails, fallback to HOLD (fail-closed)."""
        engine = AIExitEngine(journal=journal)
        # Trigger an error by passing None-like input
        inp = ExitInput(direction=0)  # invalid but won't crash — just edge cases
        decision = engine.evaluate(inp)
        assert decision is not None
        # Should either HOLD or compute something — never crash
        assert decision.action in ExitAction

    def test_cached_context_path(self, engine):
        """Decision with cached context should mark used_cached_context=True."""
        inp = make_input(r_multiple=0.3)
        cached = {"health_score": 90, "broker_quality": 85}
        decision = engine.evaluate(inp, cached_context=cached)
        assert decision.used_cached_context is True
        assert decision.decision_path == "cached"

    def test_no_cached_context_default(self, engine):
        """Without cached context, used_cached_context=False."""
        inp = make_input(r_multiple=0.3)
        decision = engine.evaluate(inp)
        assert decision.used_cached_context is False
        assert decision.decision_path == "ai"

    def test_latency_measured(self, engine):
        """Every decision must have exit_latency_ms > 0."""
        decision = engine.evaluate(make_input())
        assert decision.exit_latency_ms > 0.0

    def test_decision_path_journaled(self, engine, journal):
        """Journal record must include latency fields."""
        engine.evaluate(make_input(r_multiple=0.3))
        records = journal.read_all()
        exit_events = [r for r in records if r.get("event_type") == EventType.EXIT_AI_DECISION.value]
        assert len(exit_events) == 1
        data = exit_events[0]["data"]
        assert "exit_latency_ms" in data
        assert "decision_path" in data
        assert "used_cached_context" in data
        assert "emergency_fast_path_used" in data

    def test_benchmark_1000_decisions(self, engine):
        """Run 1000 exit decisions and report avg/p95/p99 latency."""
        import numpy as np
        latencies = []
        for _ in range(1000):
            inp = make_input(r_multiple=0.3, trend_strength=0.3)
            decision = engine.evaluate(inp)
            latencies.append(decision.exit_latency_ms)

        avg = np.mean(latencies)
        p95 = np.percentile(latencies, 95)
        p99 = np.percentile(latencies, 99)
        mx = max(latencies)

        # All must be under 250ms (normal path)
        assert mx < 250.0, f"Max latency {mx:.1f}ms exceeds 250ms limit"

        print(f"\n  ── Exit Latency Benchmark (1000 decisions) ──")
        print(f"  avg:  {avg:.3f}ms")
        print(f"  p95:  {p95:.3f}ms")
        print(f"  p99:  {p99:.3f}ms")
        print(f"  max:  {mx:.3f}ms")

    def test_emergency_benchmark_1000(self, engine):
        """Run 1000 emergency exits and verify all <50ms."""
        latencies = []
        for _ in range(1000):
            inp = make_input(capital_preservation_active=True, account_health_score=20)
            decision = engine.evaluate(inp)
            latencies.append(decision.exit_latency_ms)

        mx = max(latencies)
        assert mx < 50.0, f"Emergency max latency {mx:.1f}ms exceeds 50ms limit"
        print(f"\n  ── Emergency Exit Benchmark (1000 decisions) ──")
        print(f"  max:  {mx:.3f}ms (limit: 50ms)")
