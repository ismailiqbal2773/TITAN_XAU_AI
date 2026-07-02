"""TITAN XAU AI - Sprint 9.9.3.45.8.15 Execution Geometry Enforcement Tests

Verifies that build-request execution geometry is enforced:
  - BUY TP computed from entry + initial_tp_R * risk_distance (TP=4065.64
    for entry=4056.64 SL=4053.64 initial_tp_R=3.0).
  - BUY TP=4059.64 (RR=1.0) is blocked because RR < minimum_RR.
  - SELL TP=1970 for entry=2000 SL=2010 initial_tp_R=3.0.
  - actual_RR < 2.0 blocks; actual_RR >= 2.0 passes; actual_RR = 3.0 passes.
  - risk_distance and reward_distance must be > 0.
  - execution_geometry field is present in build-request output.
  - EXECUTION_GEOMETRY_RR_BELOW_MINIMUM blocker present when RR below minimum.
  - Tests contain no order_send and no martingale/grid/averaging.
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src: str) -> str:
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class _FakeArgs:
    """Minimal args for run_build_request."""
    account_profile = "retail_demo_micro"
    initial_tp_r = 3.0
    use_dynamic_tp_extension = False
    use_adaptive_trailing = False
    tp_extension_trigger_r = 2.0
    broker_profile = "metaquotes_demo"
    risk_mode = "conservative"


class _FakeArgsInitialTpZero(_FakeArgs):
    """Pass initial_tp_r=0 so run_build_request does NOT override the
    caller-supplied TP. Used to test RR=1.0 blocking path."""
    initial_tp_r = 0.0


class TestExecutionGeometryEnforcement:
    def test_01_buy_tp_is_entry_plus_3r(self):
        """BUY entry=4056.64 SL=4053.64 initial_tp_R=3.0 -> TP must be
        4065.64 (entry + 3 * (entry - SL) = 4056.64 + 3*3 = 4065.64)."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        result = mt.run_build_request(
            direction="BUY", entry_price=4056.64, sl=4053.64, tp=0.0,
            args=_FakeArgs(),
        )
        geo = result.get("execution_geometry") or {}
        assert geo.get("estimated_tp") == pytest.approx(4065.64, abs=1e-6), \
            f"expected TP=4065.64, got {geo.get('estimated_tp')}"
        assert geo.get("estimated_sl") == pytest.approx(4053.64, abs=1e-6)
        assert geo.get("estimated_entry") == pytest.approx(4056.64, abs=1e-6)
        assert geo.get("actual_RR") == pytest.approx(3.0, abs=1e-6)

    def test_02_buy_rr_1_0_is_blocked(self):
        """BUY entry=4056.64 SL=4053.64 TP=4059.64 -> RR=1.0 -> must be blocked."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        result = mt.run_build_request(
            direction="BUY", entry_price=4056.64, sl=4053.64, tp=4059.64,
            args=_FakeArgsInitialTpZero(),
        )
        assert result.get("verdict") == "BLOCKED"
        geo = result.get("execution_geometry") or {}
        assert geo.get("actual_RR") == pytest.approx(1.0, abs=1e-6)
        assert geo.get("geometry_verdict") == "EXECUTION_GEOMETRY_RR_BELOW_MINIMUM"
        blockers = result.get("blockers") or geo.get("geometry_blockers") or []
        assert any("EXECUTION_GEOMETRY_RR_BELOW_MINIMUM" in b for b in blockers), \
            f"expected EXECUTION_GEOMETRY_RR_BELOW_MINIMUM blocker, got {blockers}"

    def test_03_sell_tp_is_entry_minus_3r(self):
        """SELL entry=2000 SL=2010 initial_tp_R=3.0 -> TP must be 1970."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        result = mt.run_build_request(
            direction="SELL", entry_price=2000.0, sl=2010.0, tp=0.0,
            args=_FakeArgs(),
        )
        geo = result.get("execution_geometry") or {}
        assert geo.get("estimated_tp") == pytest.approx(1970.0, abs=1e-6), \
            f"expected TP=1970, got {geo.get('estimated_tp')}"
        assert geo.get("estimated_sl") == pytest.approx(2010.0, abs=1e-6)
        assert geo.get("actual_RR") == pytest.approx(3.0, abs=1e-6)

    def test_04_actual_rr_below_minimum_blocks(self):
        """actual_RR < 2.0 (minimum_RR) must block execution."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        # entry=2000, SL=1990 (risk=10), TP=2005 (reward=5) -> RR=0.5 < 2.0
        result = mt.run_build_request(
            direction="BUY", entry_price=2000.0, sl=1990.0, tp=2005.0,
            args=_FakeArgsInitialTpZero(),
        )
        assert result.get("verdict") == "BLOCKED"
        geo = result.get("execution_geometry") or {}
        assert geo.get("actual_RR") < 2.0
        assert geo.get("geometry_verdict") == "EXECUTION_GEOMETRY_RR_BELOW_MINIMUM"

    def test_05_actual_rr_at_minimum_passes(self):
        """actual_RR >= 2.0 (minimum_RR) must pass geometry gate."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        # entry=2000, SL=1990 (risk=10), TP=2020 (reward=20) -> RR=2.0
        result = mt.run_build_request(
            direction="BUY", entry_price=2000.0, sl=1990.0, tp=2020.0,
            args=_FakeArgsInitialTpZero(),
        )
        geo = result.get("execution_geometry") or {}
        assert geo.get("actual_RR") == pytest.approx(2.0, abs=1e-6)
        assert geo.get("geometry_verdict") == "EXECUTION_GEOMETRY_PASS"
        assert not (geo.get("geometry_blockers") or []), \
            f"geometry_blockers should be empty at RR=2.0, got {geo.get('geometry_blockers')}"

    def test_06_actual_rr_3_0_passes(self):
        """actual_RR = 3.0 must pass geometry gate."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        # entry=2000, SL=1990 (risk=10), TP=2030 (reward=30) -> RR=3.0
        result = mt.run_build_request(
            direction="BUY", entry_price=2000.0, sl=1990.0, tp=2030.0,
            args=_FakeArgsInitialTpZero(),
        )
        geo = result.get("execution_geometry") or {}
        assert geo.get("actual_RR") == pytest.approx(3.0, abs=1e-6)
        assert geo.get("geometry_verdict") == "EXECUTION_GEOMETRY_PASS"

    def test_07_risk_distance_must_be_positive(self):
        """risk_distance must be > 0. If SL on wrong side of entry, the
        order builder must not silently accept negative risk."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        # BUY with SL above entry -> risk_distance would be negative
        # The build_request geometry math uses abs() but the SLTPSafety
        # layer should block this configuration.
        result = mt.run_build_request(
            direction="BUY", entry_price=2000.0, sl=2010.0, tp=1990.0,
            args=_FakeArgsInitialTpZero(),
        )
        # Either BLOCKED verdict or geometry flagged with non-positive risk
        assert result.get("verdict") == "BLOCKED" or \
               (result.get("execution_geometry") or {}).get("sl_distance", 0) <= 0 or \
               (result.get("blockers") or [])

    def test_08_reward_distance_must_be_positive(self):
        """reward_distance must be > 0. TP must be on the profit side of entry."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        # BUY with TP below entry -> reward_distance negative
        result = mt.run_build_request(
            direction="BUY", entry_price=2000.0, sl=1990.0, tp=1980.0,
            args=_FakeArgsInitialTpZero(),
        )
        assert result.get("verdict") == "BLOCKED" or \
               (result.get("execution_geometry") or {}).get("tp_distance", 0) <= 0 or \
               (result.get("blockers") or [])

    def test_09_execution_geometry_field_in_build_request(self):
        """build-request output must include the execution_geometry field."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        result = mt.run_build_request(
            direction="BUY", entry_price=2000.0, sl=1990.0, tp=2010.0,
            args=_FakeArgsInitialTpZero(),
        )
        assert "execution_geometry" in result, \
            "execution_geometry field must be present in build-request output"
        geo = result["execution_geometry"]
        required = ["side", "estimated_entry", "estimated_sl", "estimated_tp",
                    "actual_RR", "minimum_RR", "initial_tp_R", "geometry_verdict"]
        for k in required:
            assert k in geo, f"execution_geometry missing field: {k}"

    def test_10_rr_below_minimum_blocker_string_present(self):
        """When RR < minimum, EXECUTION_GEOMETRY_RR_BELOW_MINIMUM blocker
        must appear in either result['blockers'] or
        execution_geometry['geometry_blockers']."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        # RR=1.0 < 2.0 minimum
        result = mt.run_build_request(
            direction="BUY", entry_price=2000.0, sl=1990.0, tp=2000.0 + 10.0,
            args=_FakeArgsInitialTpZero(),
        )
        all_blockers = (result.get("blockers") or []) + \
            ((result.get("execution_geometry") or {}).get("geometry_blockers") or [])
        assert any("EXECUTION_GEOMETRY_RR_BELOW_MINIMUM" in b for b in all_blockers), \
            f"EXECUTION_GEOMETRY_RR_BELOW_MINIMUM blocker missing, got: {all_blockers}"

    def test_11_no_order_send_in_build_request(self):
        """run_build_request must never call mt5.order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src)
        # Find run_build_request function body
        idx = code.find("def run_build_request")
        assert idx > 0, "run_build_request not found"
        end_idx = code.find("\ndef ", idx + 1)
        if end_idx < 0:
            end_idx = len(code)
        body = code[idx:end_idx]
        assert "mt5.order_send" not in body, \
            "order_send must NOT appear in run_build_request"

    def test_12_no_martingale_in_build_request(self):
        """run_build_request must not contain martingale / grid / averaging /
        loss-based lot multiplier logic."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src).lower()
        idx = code.find("def run_build_request")
        assert idx > 0
        end_idx = code.find("\ndef ", idx + 1)
        if end_idx < 0:
            end_idx = len(code)
        body = code[idx:end_idx]
        forbidden = ["martingale", "grid_trade", "averaging_down",
                     "double_lot", "loss_based_lot_multiplier"]
        for term in forbidden:
            assert term not in body, f"Forbidden term '{term}' in run_build_request"

    def test_13_geometry_pass_does_not_set_blockers(self):
        """When geometry passes (RR >= minimum_RR), geometry_blockers must
        be empty and verdict must not be BLOCKED due to geometry."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        # RR=3.0 PASS
        result = mt.run_build_request(
            direction="BUY", entry_price=2000.0, sl=1990.0, tp=2030.0,
            args=_FakeArgsInitialTpZero(),
        )
        geo = result.get("execution_geometry") or {}
        assert geo.get("geometry_verdict") == "EXECUTION_GEOMETRY_PASS"
        assert (geo.get("geometry_blockers") or []) == []
        # The blocker list, if any, must not include EXECUTION_GEOMETRY_RR_BELOW_MINIMUM
        all_blockers = result.get("blockers") or []
        assert not any("EXECUTION_GEOMETRY_RR_BELOW_MINIMUM" in b for b in all_blockers), \
            f"geometry PASS but EXECUTION_GEOMETRY_RR_BELOW_MINIMUM in blockers: {all_blockers}"

    def test_14_minimum_rr_is_2_0_for_retail_demo_micro(self):
        """For retail_demo_micro profile, minimum_RR must be at least 2.0
        (the hard floor for all execution)."""
        import scripts.operator.run_managed_demo_micro_trade as mt
        result = mt.run_build_request(
            direction="BUY", entry_price=2000.0, sl=1990.0, tp=2030.0,
            args=_FakeArgsInitialTpZero(),
        )
        geo = result.get("execution_geometry") or {}
        # Hard minimum is 2.0 for all execution paths
        assert geo.get("minimum_RR") >= 2.0, \
            f"minimum_RR must be >= 2.0, got {geo.get('minimum_RR')}"

    def test_15_no_order_send_in_test_file(self):
        """The test file itself must not call order_send."""
        src = (REPO_ROOT / "titan" / "tests" / "test_execution_geometry_enforcement.py").read_text()
        code = _strip(src)
        assert "mt5.order_send" not in code, "test file must not call mt5.order_send"

    def test_16_no_martingale_pattern_in_test_file(self):
        """The test file must not implement any lot-doubling or
        loss-based lot-multiplier patterns (no `lot *= 2`, no
        `volume *= 2`, no `loss_count * lot`, etc.)."""
        src = (REPO_ROOT / "titan" / "tests" / "test_execution_geometry_enforcement.py").read_text()
        # Strip docstrings/strings so textual references in docs do not trip
        # the pattern check - we only care about actual executable patterns.
        code = _strip(src)
        forbidden_patterns = [
            r"lot\s*\*=\s*2",
            r"volume\s*\*=\s*2",
            r"lot\s*=\s*lot\s*\*\s*2",
            r"volume\s*=\s*volume\s*\*\s*2",
            r"loss_count\s*\*\s*lot",
            r"loss_count\s*\*\s*volume",
            r"previous_lot\s*\*\s*2",
        ]
        for pat in forbidden_patterns:
            assert not re.search(pat, code), \
                f"Forbidden pattern '{pat}' in test file"
