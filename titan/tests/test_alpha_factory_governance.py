"""TITAN XAU AI - Sprint 9.9.3.36 Alpha Factory Governance Tests"""
from __future__ import annotations
import inspect, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.alpha_factory_governance import (
    AlphaFactoryGovernance, AlphaCandidate,
    AlphaCandidateType, AlphaCandidateStatus,
)


class TestEnums:
    def test_01_all_candidate_types_present(self):
        types = [t.value for t in AlphaCandidateType]
        for t in ["FEATURE_SET", "LABEL_VARIANT", "MODEL_VARIANT",
                  "ENSEMBLE_VARIANT", "THRESHOLD_VARIANT", "REGIME_SPECIALIST",
                  "EXIT_POLICY_VARIANT"]:
            assert t in types

    def test_02_all_candidate_statuses_present(self):
        statuses = [s.value for s in AlphaCandidateStatus]
        for s in ["GENERATED", "VALIDATING", "PASSED_INITIAL_FILTER",
                  "REJECTED", "QUARANTINED", "READY_FOR_SHADOW", "NEEDS_REVIEW"]:
            assert s in statuses


class TestCandidateDataclass:
    def test_03_candidate_has_all_required_fields(self):
        c = AlphaCandidate(
            candidate_id="c1",
            candidate_type=AlphaCandidateType.FEATURE_SET,
            description="test",
            source="test",
        )
        required = ["candidate_id", "candidate_type", "description", "source",
                    "created_utc", "metrics", "validation_status", "leakage_flags",
                    "broker_split_status", "walk_forward_status", "shadow_ready",
                    "notes"]
        for f in required:
            assert hasattr(c, f), f"Missing: {f}"

    def test_04_candidate_defaults_to_generated(self):
        c = AlphaCandidate(
            candidate_id="c1",
            candidate_type=AlphaCandidateType.FEATURE_SET,
            description="test",
            source="test",
        )
        assert c.validation_status == AlphaCandidateStatus.GENERATED
        assert c.shadow_ready is False


class TestRegistration:
    def test_05_alpha_candidate_can_register(self):
        gov = AlphaFactoryGovernance()
        c = gov.register_candidate(
            candidate_id="c1",
            candidate_type=AlphaCandidateType.FEATURE_SET,
            description="test feature set",
            source="research_session_1",
            metrics={"oos_sharpe": 1.5},
        )
        assert c.candidate_id == "c1"
        assert c.validation_status == AlphaCandidateStatus.GENERATED
        assert gov.get_candidate("c1") is not None

    def test_06_duplicate_registration_raises(self):
        gov = AlphaFactoryGovernance()
        gov.register_candidate(
            candidate_id="c1",
            candidate_type=AlphaCandidateType.FEATURE_SET,
            description="test",
            source="test",
        )
        with pytest.raises(ValueError):
            gov.register_candidate(
                candidate_id="c1",
                candidate_type=AlphaCandidateType.MODEL_VARIANT,
                description="test2",
                source="test",
            )


class TestLeakageRejection:
    def test_07_alpha_candidate_with_leakage_quarantined(self):
        gov = AlphaFactoryGovernance()
        c = gov.register_candidate(
            candidate_id="c1",
            candidate_type=AlphaCandidateType.FEATURE_SET,
            description="test",
            source="test",
        )
        c.leakage_flags = ["future_peek_in_features"]
        rejected, reasons = gov.reject_if_leakage_flags(c)
        assert rejected is True
        assert c.validation_status == AlphaCandidateStatus.QUARANTINED
        assert c.shadow_ready is False
        assert len(reasons) >= 1


class TestShadowReadiness:
    def test_08_alpha_candidate_ready_for_shadow_only_after_validations(self):
        gov = AlphaFactoryGovernance()
        c = gov.register_candidate(
            candidate_id="c1",
            candidate_type=AlphaCandidateType.FEATURE_SET,
            description="test",
            source="test",
            metrics={
                "reality_gap_sharpe": 0.1,
                "reality_gap_drawdown": 0.02,
            },
        )
        # Initially not ready
        ok, blockers = gov.mark_ready_for_shadow(c)
        assert ok is False
        assert len(blockers) >= 1
        assert c.validation_status == AlphaCandidateStatus.NEEDS_REVIEW

        # Pass all gates
        c.walk_forward_status = "PASS"
        c.broker_split_status = "PASS"
        ok, blockers = gov.mark_ready_for_shadow(c)
        assert ok is True
        assert len(blockers) == 0
        assert c.validation_status == AlphaCandidateStatus.READY_FOR_SHADOW
        assert c.shadow_ready is True

    def test_09_alpha_candidate_blocked_from_shadow_if_leakage(self):
        gov = AlphaFactoryGovernance()
        c = gov.register_candidate(
            candidate_id="c1",
            candidate_type=AlphaCandidateType.FEATURE_SET,
            description="test",
            source="test",
            metrics={"reality_gap_sharpe": 0.1, "reality_gap_drawdown": 0.02},
        )
        c.leakage_flags = ["suspicious_pattern"]
        c.walk_forward_status = "PASS"
        c.broker_split_status = "PASS"
        ok, blockers = gov.mark_ready_for_shadow(c)
        assert ok is False
        assert any("leakage" in b.lower() for b in blockers)

    def test_10_alpha_candidate_blocked_if_walk_forward_pending(self):
        gov = AlphaFactoryGovernance()
        c = gov.register_candidate(
            candidate_id="c1",
            candidate_type=AlphaCandidateType.FEATURE_SET,
            description="test",
            source="test",
            metrics={"reality_gap_sharpe": 0.1, "reality_gap_drawdown": 0.02},
        )
        c.walk_forward_status = "PENDING"
        c.broker_split_status = "PASS"
        ok, blockers = gov.mark_ready_for_shadow(c)
        assert ok is False
        assert any("walk-forward" in b.lower() for b in blockers)

    def test_11_alpha_candidate_blocked_if_broker_split_pending(self):
        gov = AlphaFactoryGovernance()
        c = gov.register_candidate(
            candidate_id="c1",
            candidate_type=AlphaCandidateType.FEATURE_SET,
            description="test",
            source="test",
            metrics={"reality_gap_sharpe": 0.1, "reality_gap_drawdown": 0.02},
        )
        c.walk_forward_status = "PASS"
        c.broker_split_status = "PENDING"
        ok, blockers = gov.mark_ready_for_shadow(c)
        assert ok is False
        assert any("broker" in b.lower() for b in blockers)

    def test_12_alpha_candidate_blocked_if_reality_gap_missing(self):
        gov = AlphaFactoryGovernance()
        c = gov.register_candidate(
            candidate_id="c1",
            candidate_type=AlphaCandidateType.FEATURE_SET,
            description="test",
            source="test",
            metrics={},  # no reality gap metrics
        )
        c.walk_forward_status = "PASS"
        c.broker_split_status = "PASS"
        ok, blockers = gov.mark_ready_for_shadow(c)
        assert ok is False
        assert any("reality_gap" in b for b in blockers)


class TestNeverPromoteToChampion:
    def test_13_never_promote_to_champion_returns_false(self):
        gov = AlphaFactoryGovernance()
        assert gov.never_promote_to_champion() is False


class TestSummary:
    def test_14_summary_returns_dict(self):
        gov = AlphaFactoryGovernance()
        gov.register_candidate(
            candidate_id="c1",
            candidate_type=AlphaCandidateType.FEATURE_SET,
            description="test",
            source="test",
        )
        s = gov.summary()
        assert "total_candidates" in s
        assert s["total_candidates"] == 1
        assert s["can_promote_to_champion"] is False


class TestSafetyInvariants:
    def test_15_no_metatrader5_import(self):
        from titan.production import alpha_factory_governance
        src = inspect.getsource(alpha_factory_governance)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_16_no_order_send_calls(self):
        import re
        from titan.production import alpha_factory_governance
        src = inspect.getsource(alpha_factory_governance)
        call_pattern = r"(?<!['\"#])\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_17_no_model_training_execution(self):
        from titan.production import alpha_factory_governance
        src = inspect.getsource(alpha_factory_governance)
        assert ".fit(" not in src
        assert "train_model(" not in src
        assert "retrain(" not in src
        assert "run_hpo(" not in src

    def test_18_no_champion_replacement(self):
        from titan.production import alpha_factory_governance
        src = inspect.getsource(alpha_factory_governance)
        assert "shutil.copy" not in src
        assert "shutil.move" not in src
        assert "pickle.dump" not in src

    def test_19_no_runtime_config_modification(self):
        from titan.production import alpha_factory_governance
        src = inspect.getsource(alpha_factory_governance)
        assert "runtime.yaml" not in src
        assert "config/runtime" not in src

    def test_20_no_demo_micro_execute(self):
        from titan.production import alpha_factory_governance
        src = inspect.getsource(alpha_factory_governance)
        assert "import demo_micro_execute" not in src
        assert "from demo_micro_execute" not in src
        assert "DEMO_MICRO_EXECUTE(" not in src
