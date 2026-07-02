"""TITAN XAU AI - Sprint v2.8.3 Prop-Funded Verdict Mapper Tests"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestPropFundedVerdictMapper:
    def test_01_module_imports(self):
        from titan.production.prop_funded_verdict_mapper import (
            map_verdict, check_conservative_restrictions,
            PropFundedVerdictMapping, ALL_STATUSES,
        )
        assert callable(map_verdict)
        assert callable(check_conservative_restrictions)

    def test_02_all_statuses_supported(self):
        from titan.production.prop_funded_verdict_mapper import ALL_STATUSES
        assert "PASS" in ALL_STATUSES
        assert "PASS_CONSERVATIVE" in ALL_STATUSES
        assert "PENDING_VALIDATION" in ALL_STATUSES
        assert "BLOCKED" in ALL_STATUSES
        assert "UNKNOWN" in ALL_STATUSES

    def test_03_ready_conservative_maps_to_pass_conservative(self):
        """PROP_FUNDED_READY_CONSERVATIVE maps to PASS_CONSERVATIVE."""
        from titan.production.prop_funded_verdict_mapper import map_verdict
        m = map_verdict("PROP_FUNDED_READY_CONSERVATIVE")
        assert m.canonical_status == "PASS_CONSERVATIVE"
        assert m.gate_pass is True
        assert m.gate_status == "PASS_CONSERVATIVE"
        assert m.conservative_mode is True
        assert any("CONSERVATIVE_MODE_ACTIVE" in w for w in m.warnings)

    def test_04_ready_maps_to_pass_conservative(self):
        """PROP_FUNDED_READY maps to PASS_CONSERVATIVE."""
        from titan.production.prop_funded_verdict_mapper import map_verdict
        m = map_verdict("PROP_FUNDED_READY")
        assert m.canonical_status == "PASS_CONSERVATIVE"
        assert m.gate_pass is True

    def test_05_optimal_ready_maps_to_pass(self):
        """PROP_FUNDED_OPTIMAL_READY maps to PASS."""
        from titan.production.prop_funded_verdict_mapper import map_verdict
        m = map_verdict("PROP_FUNDED_OPTIMAL_READY")
        assert m.canonical_status == "PASS"
        assert m.gate_pass is True
        assert m.conservative_mode is False

    def test_06_blocked_maps_to_blocked(self):
        """PROP_FUNDED_BLOCKED maps to BLOCKED."""
        from titan.production.prop_funded_verdict_mapper import map_verdict
        m = map_verdict("PROP_FUNDED_BLOCKED")
        assert m.canonical_status == "BLOCKED"
        assert m.gate_pass is False

    def test_07_pending_broker_maps_to_pending(self):
        """PROP_FUNDED_GATE_PENDING_BROKER_VALIDATION maps to PENDING_VALIDATION."""
        from titan.production.prop_funded_verdict_mapper import map_verdict
        m = map_verdict("PROP_FUNDED_GATE_PENDING_BROKER_VALIDATION")
        assert m.canonical_status == "PENDING_VALIDATION"
        assert m.gate_pass is False

    def test_08_unknown_verdict_maps_to_unknown(self):
        """Unknown verdict maps to UNKNOWN, not pass."""
        from titan.production.prop_funded_verdict_mapper import map_verdict
        m = map_verdict("SOME_RANDOM_VERDICT")
        assert m.canonical_status == "UNKNOWN"
        assert m.gate_pass is False
        assert any("UNKNOWN_VERDICT" in w for w in m.warnings)

    def test_09_conservative_mode_restrictions(self):
        """Conservative mode has correct restrictions."""
        from titan.production.prop_funded_verdict_mapper import CONSERVATIVE_RESTRICTIONS
        assert CONSERVATIVE_RESTRICTIONS["max_lot"] == 0.01
        assert CONSERVATIVE_RESTRICTIONS["max_open_positions"] == 1
        assert CONSERVATIVE_RESTRICTIONS["max_risk_per_trade_pct"] == 0.005
        assert CONSERVATIVE_RESTRICTIONS["allowed_broker"] == "MetaQuotes-Demo"
        assert CONSERVATIVE_RESTRICTIONS["no_real_funded_live"] is True
        assert CONSERVATIVE_RESTRICTIONS["no_martingale"] is True
        assert CONSERVATIVE_RESTRICTIONS["minimum_RR"] == 2.0

    def test_10_check_conservative_restrictions_pass(self):
        """check_conservative_restrictions passes with valid values."""
        from titan.production.prop_funded_verdict_mapper import check_conservative_restrictions
        result = check_conservative_restrictions(
            lot=0.01, max_open_positions=1, risk_per_trade_pct=0.005,
            broker_server="MetaQuotes-Demo", account_type="demo",
            actual_RR=3.0,
        )
        assert result["restrictions_pass"] is True
        assert len(result["violations"]) == 0

    def test_11_check_conservative_restrictions_fail_lot(self):
        """check_conservative_restrictions fails when lot > 0.01."""
        from titan.production.prop_funded_verdict_mapper import check_conservative_restrictions
        result = check_conservative_restrictions(lot=0.02)
        assert result["restrictions_pass"] is False
        assert any("LOT_EXCEEDS" in v for v in result["violations"])

    def test_12_check_conservative_restrictions_fail_rr(self):
        """check_conservative_restrictions fails when RR < 2.0."""
        from titan.production.prop_funded_verdict_mapper import check_conservative_restrictions
        result = check_conservative_restrictions(actual_RR=1.5)
        assert result["restrictions_pass"] is False
        assert any("RR_BELOW" in v for v in result["violations"])

    def test_13_check_conservative_restrictions_fail_broker(self):
        """check_conservative_restrictions fails when broker is not MetaQuotes-Demo."""
        from titan.production.prop_funded_verdict_mapper import check_conservative_restrictions
        result = check_conservative_restrictions(broker_server="FundedNext-Demo")
        assert result["restrictions_pass"] is False
        assert any("BROKER_NOT_METAQUOTES" in v for v in result["violations"])

    def test_14_mapping_to_dict(self):
        """PropFundedVerdictMapping.to_dict includes all fields."""
        from titan.production.prop_funded_verdict_mapper import map_verdict
        m = map_verdict("PROP_FUNDED_READY_CONSERVATIVE")
        d = m.to_dict()
        assert "raw_verdict" in d
        assert "canonical_status" in d
        assert "gate_pass" in d
        assert "gate_status" in d
        assert "gate_reason" in d
        assert "conservative_mode" in d
        assert "warnings" in d
        assert "conservative_restrictions" in d
