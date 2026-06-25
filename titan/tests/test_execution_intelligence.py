"""
TITAN XAU AI — Sprint 9.5 Execution Profile + Risk Adapter + History + Self-Protection Tests
"""
from __future__ import annotations
import pytest
from datetime import datetime, timezone

from titan.production.broker_quality_engine import (
    BrokerQualityEngine, BrokerQualityInput, BrokerQualityScore,
    BAND_INSTITUTIONAL, BAND_EXCELLENT, BAND_GOOD, BAND_AVERAGE, BAND_UNSAFE,
)
from titan.production.execution_profile import (
    ExecutionProfileSelector, ExecutionProfile, PROFILES,
)
from titan.production.broker_risk_adapter import (
    BrokerRiskAdapter, RiskAdaptation,
)
from titan.production.broker_score_history import (
    BrokerScoreHistory, HistoryBucket,
)
from titan.production.execution_self_protection import (
    ExecutionSelfProtection, SelfProtectionConfig, ProtectionState,
)
from titan.production.trade_journal import TradeJournal, EventType
from titan.production.trade_loop import TradeLoopConfig, MAX_LOT_CAP


@pytest.fixture
def journal(tmp_path):
    return TradeJournal(path=str(tmp_path / "ep.jsonl"), session_id="ep_test")


def make_score(score: float) -> BrokerQualityScore:
    band = (
        BAND_INSTITUTIONAL if score >= 95 else
        BAND_EXCELLENT if score >= 85 else
        BAND_GOOD if score >= 75 else
        BAND_AVERAGE if score >= 60 else
        BAND_UNSAFE
    )
    return BrokerQualityScore(score=score, band=band, components={})


# ════════════════════════════════════════════════════════════════════════════
# ExecutionProfileSelector
# ════════════════════════════════════════════════════════════════════════════
class TestExecutionProfileSelector:
    @pytest.fixture
    def selector(self, journal):
        return ExecutionProfileSelector(journal=journal)

    def test_unsafe_score_selects_unsafe_profile(self, selector):
        profile = selector.select(make_score(50))
        assert profile.name == "unsafe"
        assert profile.allow_new_entries is False
        assert profile.risk_multiplier == 0.0

    def test_institutional_score_ecn(self, selector):
        from titan.production.broker_intelligence import BrokerInfo
        info = BrokerInfo(broker_name="ICMarkets", account_spread_type="ecn")
        profile = selector.select(make_score(97), info)
        assert profile.name == "ultra_low_spread"

    def test_excellent_score_raw(self, selector):
        from titan.production.broker_intelligence import BrokerInfo
        info = BrokerInfo(broker_name="ICMarkets", account_spread_type="raw")
        profile = selector.select(make_score(90), info)
        assert profile.name == "raw"

    def test_prop_firm_selects_prop_challenge(self, selector):
        from titan.production.broker_intelligence import BrokerInfo
        info = BrokerInfo(broker_name="FTMO", account_category="prop")
        profile = selector.select(make_score(80), info)
        assert profile.name == "prop_challenge"
        assert profile.atr_profile == "challenge"

    def test_cent_account_selects_cent(self, selector):
        from titan.production.broker_intelligence import BrokerInfo
        info = BrokerInfo(broker_name="Exness", account_size="cent")
        profile = selector.select(make_score(80), info)
        assert profile.name == "cent"
        assert profile.risk_multiplier == 0.5

    def test_retail_good_score(self, selector):
        from titan.production.broker_intelligence import BrokerInfo
        info = BrokerInfo(broker_name="Exness", account_category="retail")
        profile = selector.select(make_score(80), info)
        assert profile.name == "retail"
        assert profile.risk_multiplier == 0.8

    def test_average_score_selects_conservative(self, selector):
        profile = selector.select(make_score(65))
        assert profile.name == "conservative"

    def test_profile_selection_journaled(self, selector, journal):
        selector.select(make_score(80))
        records = journal.read_all()
        selected = [r for r in records if r.get("event_type") == EventType.BROKER_PROFILE_SELECTED.value]
        assert len(selected) == 1

    def test_profile_transition_journaled(self, selector, journal):
        selector.select(make_score(80))  # retail or aggressive
        selector.select(make_score(50))  # unsafe
        records = journal.read_all()
        transitions = [r for r in records if r.get("event_type") == EventType.EXECUTION_PROFILE_CHANGED.value]
        assert len(transitions) == 1

    def test_no_transition_on_same_profile(self, selector, journal):
        selector.select(make_score(80))
        selector.select(make_score(80))
        records = journal.read_all()
        transitions = [r for r in records if r.get("event_type") == EventType.EXECUTION_PROFILE_CHANGED.value]
        assert len(transitions) == 0

    def test_all_9_profiles_exist(self):
        assert len(PROFILES) == 9
        for name in ["ultra_low_spread", "ecn", "raw", "prop_challenge",
                     "retail", "cent", "aggressive", "conservative", "unsafe"]:
            assert name in PROFILES

    def test_risk_multiplier_never_exceeds_1(self):
        for profile in PROFILES.values():
            assert profile.risk_multiplier <= 1.0
            assert profile.max_lot_multiplier <= 1.0


# ════════════════════════════════════════════════════════════════════════════
# BrokerRiskAdapter
# ════════════════════════════════════════════════════════════════════════════
class TestBrokerRiskAdapter:
    @pytest.fixture
    def adapter(self, journal):
        return BrokerRiskAdapter(journal=journal)

    def test_institutional_keeps_full_risk(self, adapter):
        from titan.production.execution_profile import PROFILES
        adaptation = adapter.adapt(make_score(97), PROFILES["ultra_low_spread"])
        assert adaptation.risk_multiplier == 1.0

    def test_unsafe_zeros_risk(self, adapter):
        from titan.production.execution_profile import PROFILES
        adaptation = adapter.adapt(make_score(50), PROFILES["conservative"])
        assert adaptation.risk_multiplier == 0.0
        assert adaptation.allow_new_entries is False

    def test_good_band_reduces_risk(self, adapter):
        from titan.production.execution_profile import PROFILES
        # Good band (75-84) → multiplier 0.8
        adaptation = adapter.adapt(make_score(80), PROFILES["retail"])
        # retail profile risk_multiplier=0.8, good band=0.8 → min=0.8
        assert adaptation.risk_multiplier == 0.8

    def test_band_can_only_decrease(self, adapter):
        """Band multiplier should never INCREASE risk above profile."""
        from titan.production.execution_profile import PROFILES
        # Conservative profile has risk_multiplier=0.5
        # Institutional band would give 1.0 — but min(0.5, 1.0) = 0.5
        adaptation = adapter.adapt(make_score(97), PROFILES["conservative"])
        assert adaptation.risk_multiplier == 0.5  # profile wins (more conservative)

    def test_apply_to_trade_loop_respects_hard_cap(self, adapter):
        from titan.production.execution_profile import PROFILES
        adaptation = adapter.adapt(make_score(97), PROFILES["ultra_low_spread"])
        loop_cfg = TradeLoopConfig(dry_run=True)
        adapter.apply_to_trade_loop(adaptation, loop_cfg)
        assert loop_cfg.max_lot <= MAX_LOT_CAP

    def test_apply_to_trade_loop_decreases_for_low_quality(self, adapter):
        from titan.production.execution_profile import PROFILES
        adaptation = adapter.adapt(make_score(65), PROFILES["conservative"])
        loop_cfg = TradeLoopConfig(dry_run=True)
        adapter.apply_to_trade_loop(adaptation, loop_cfg)
        # Average band → multiplier 0.6 → max_lot < 0.01
        assert loop_cfg.max_lot < MAX_LOT_CAP

    def test_unsafe_zeros_max_lot(self, adapter):
        from titan.production.execution_profile import PROFILES
        adaptation = adapter.adapt(make_score(50), PROFILES["conservative"])
        loop_cfg = TradeLoopConfig(dry_run=True)
        adapter.apply_to_trade_loop(adaptation, loop_cfg)
        assert loop_cfg.max_lot == 0.0


# ════════════════════════════════════════════════════════════════════════════
# BrokerScoreHistory
# ════════════════════════════════════════════════════════════════════════════
class TestBrokerScoreHistory:
    @pytest.fixture
    def history(self, tmp_path, journal):
        return BrokerScoreHistory(history_dir=str(tmp_path / "bh"), journal=journal)

    def test_record_creates_buckets(self, history):
        history.record(make_score(85), spread=0.20)
        assert len(history._daily) >= 1
        assert len(history._weekly) >= 1
        assert len(history._monthly) >= 1

    def test_daily_summary(self, history):
        for score in [80, 85, 90]:
            history.record(make_score(score), spread=0.20)
        daily = history.get_daily_summary(7)
        assert len(daily) >= 1
        assert daily[-1]["sample_count"] == 3
        assert daily[-1]["score_avg"] == 85.0

    def test_trend_analysis_stable(self, history):
        for _ in range(14):
            history.record(make_score(80))
        trend = history.get_trend_analysis()
        assert trend["trend"] == "stable"

    def test_trend_analysis_improving(self, history):
        # Simulate 7 days of low scores, then 7 days of high scores.
        # We do this by directly populating the daily buckets with
        # different period keys (since same-day records aggregate).
        from titan.production.broker_score_history import HistoryBucket
        from titan.production.broker_quality_engine import BrokerQualityScore, BAND_AVERAGE, BAND_EXCELLENT
        # Mock 14 daily buckets: 7 low + 7 high
        for i in range(7):
            bucket = HistoryBucket(period=f"2026-01-{i+1:02d}", granularity="daily")
            bucket.scores = [60.0]
            history._daily[bucket.period] = bucket
        for i in range(7):
            bucket = HistoryBucket(period=f"2026-01-{i+8:02d}", granularity="daily")
            bucket.scores = [90.0]
            history._daily[bucket.period] = bucket
        trend = history.get_trend_analysis()
        assert trend["trend"] == "improving"
        assert trend["delta"] > 0

    def test_persist_and_load(self, tmp_path):
        h1 = BrokerScoreHistory(history_dir=str(tmp_path / "bh2"))
        h1.record(make_score(85), spread=0.20)
        h1.save()
        assert (tmp_path / "bh2" / "broker_history_daily.json").exists()
        # Load (summaries only — not raw scores)
        h2 = BrokerScoreHistory(history_dir=str(tmp_path / "bh2"))
        assert h2 is not None


# ════════════════════════════════════════════════════════════════════════════
# ExecutionSelfProtection
# ════════════════════════════════════════════════════════════════════════════
class TestExecutionSelfProtection:
    @pytest.fixture
    def protection(self, journal):
        return ExecutionSelfProtection(
            config=SelfProtectionConfig(),
            journal=journal,
        )

    def test_clean_evaluation_no_action(self, protection):
        result = protection.evaluate(spread_usd=0.20, latency_ms=50)
        assert result.action == "none"
        assert result.risk_multiplier == 1.0

    def test_spread_spike_triggers_warning(self, protection):
        result = protection.evaluate(spread_usd=5.0)
        assert result.action == "warning"
        assert result.risk_multiplier == 0.5

    def test_latency_spike_triggers_degraded(self, protection):
        result = protection.evaluate(latency_ms=1500)
        assert result.action == "degraded"
        assert result.risk_multiplier == 0.25

    def test_high_rejection_triggers_unsafe(self, protection):
        result = protection.evaluate(rejection_rate=0.15)
        assert result.action == "unsafe"
        assert result.risk_multiplier == 0.0
        assert result.pause_entries is True

    def test_connection_lost_triggers_kill_switch(self, protection):
        result = protection.evaluate(connection_lost=True)
        assert result.action == "kill_switch"
        assert result.trigger_kill_switch is True

    def test_warning_journaled(self, protection, journal):
        protection.evaluate(spread_usd=5.0)
        records = journal.read_all()
        warnings = [r for r in records if r.get("event_type") == EventType.EXECUTION_WARNING.value]
        assert len(warnings) == 1

    def test_degraded_journaled(self, protection, journal):
        protection.evaluate(latency_ms=1500)
        records = journal.read_all()
        degraded = [r for r in records if r.get("event_type") == EventType.EXECUTION_DEGRADED.value]
        assert len(degraded) == 1

    def test_unsafe_journaled(self, protection, journal):
        protection.evaluate(rejection_rate=0.15)
        records = journal.read_all()
        unsafe = [r for r in records if r.get("event_type") == EventType.BROKER_UNSAFE.value]
        assert len(unsafe) == 1

    def test_escalation_ladder(self, protection):
        # Start clean
        protection.evaluate(spread_usd=0.20)
        assert protection.risk_multiplier == 1.0
        # Warning
        protection.evaluate(spread_usd=5.0)
        assert protection.risk_multiplier == 0.5
        # Degraded
        protection.evaluate(latency_ms=1500)
        assert protection.risk_multiplier == 0.25
        # Unsafe
        protection.evaluate(rejection_rate=0.15)
        assert protection.risk_multiplier == 0.0

    def test_de_escalation_requires_clean_streak(self, protection):
        # Trigger warning
        protection.evaluate(spread_usd=5.0)
        assert protection.risk_multiplier == 0.5
        # 1 clean eval — not enough
        protection.evaluate(spread_usd=0.20)
        assert protection.risk_multiplier == 0.5  # still warning
        # 4 more clean = 5 total → de-escalate
        for _ in range(4):
            protection.evaluate(spread_usd=0.20)
        assert protection.risk_multiplier == 1.0  # cleared

    def test_recovery_journaled(self, protection, journal):
        # Trigger warning
        protection.evaluate(spread_usd=5.0)
        # 5 clean evals
        for _ in range(5):
            protection.evaluate(spread_usd=0.20)
        records = journal.read_all()
        recovered = [r for r in records if r.get("event_type") == EventType.EXECUTION_RECOVERED.value]
        assert len(recovered) >= 1

    def test_risk_multiplier_never_exceeds_1(self, protection):
        """Capital protection can only DECREASE risk, never increase."""
        protection.evaluate(spread_usd=0.20, latency_ms=20)
        assert protection.risk_multiplier <= 1.0
