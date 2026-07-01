"""TITAN XAU AI - Sprint 9.9.3.45.8.2 Paired SLTP Modify Builder Tests

Tests for titan/production/paired_sltp_modify_builder.py:
  - paired SLTP modify preserves action safety
  - no TP reduction
  - no SL widening
  - TP cannot be removed
  - SL profit floor enforced
  - broker stop/freeze level enforced
  - action = TRADE_ACTION_SLTP
  - one modify request per call
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.paired_sltp_modify_builder import (
    PairedSLTPModifyBuilder, PairedSLTPModifyPreview,
)


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class TestPairedSLTPModifyBuilder:
    def test_01_module_imports(self):
        from titan.production import paired_sltp_modify_builder
        assert hasattr(paired_sltp_modify_builder, "PairedSLTPModifyBuilder")
        assert hasattr(paired_sltp_modify_builder, "PairedSLTPModifyPreview")

    def test_02_build_preview_pass_buy(self):
        """Build preview for valid BUY paired modify."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="BUY",
            old_sl=2012.0, new_sl=2015.0,
            old_tp=2025.0, new_tp=2030.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="TP extension paired with SL raise",
            stops_level_points=0, point=0.01,
            current_price=2020.0,
        )
        assert result["verdict"] == "PASS"
        assert result["action"] == "TRADE_ACTION_SLTP"
        preview = result["preview"]
        assert preview["new_sl"] == 2015.0
        assert preview["new_tp"] == 2030.0
        assert preview["favorable_sl"] is True
        assert preview["no_tp_reduction"] is True
        assert preview["no_sl_widening"] is True
        assert preview["tp_preserved_or_extended"] is True

    def test_03_build_preview_pass_sell(self):
        """Build preview for valid SELL paired modify."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="SELL",
            old_sl=1988.0, new_sl=1985.0,
            old_tp=1975.0, new_tp=1970.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="TP extension paired with SL raise",
            stops_level_points=0, point=0.01,
            current_price=1980.0,
        )
        assert result["verdict"] == "PASS"
        preview = result["preview"]
        assert preview["new_sl"] == 1985.0
        assert preview["new_tp"] == 1970.0
        assert preview["favorable_sl"] is True
        assert preview["no_tp_reduction"] is True
        assert preview["no_sl_widening"] is True

    def test_04_no_tp_reduction_buy(self):
        """BUY: new_tp < old_tp must be blocked."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="BUY",
            old_sl=2012.0, new_sl=2015.0,
            old_tp=2030.0, new_tp=2025.0,  # Reduced!
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert result["verdict"] == "BLOCKED"
        assert any("TP_REDUCTION_BLOCKED" in b for b in result["blockers"])

    def test_05_no_tp_reduction_sell(self):
        """SELL: new_tp > old_tp must be blocked."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="SELL",
            old_sl=1988.0, new_sl=1985.0,
            old_tp=1970.0, new_tp=1975.0,  # Reduced (increased for SELL)!
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert result["verdict"] == "BLOCKED"
        assert any("TP_REDUCTION_BLOCKED" in b for b in result["blockers"])

    def test_06_no_sl_widening_buy(self):
        """BUY: new_sl < old_sl must be blocked."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="BUY",
            old_sl=2015.0, new_sl=2012.0,  # Widened (reduced for BUY)!
            old_tp=2025.0, new_tp=2030.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert result["verdict"] == "BLOCKED"
        assert any("SL_WIDENING_BLOCKED" in b for b in result["blockers"])

    def test_07_no_sl_widening_sell(self):
        """SELL: new_sl > old_sl must be blocked."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="SELL",
            old_sl=1985.0, new_sl=1988.0,  # Widened (increased for SELL)!
            old_tp=1975.0, new_tp=1970.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert result["verdict"] == "BLOCKED"
        assert any("SL_WIDENING_BLOCKED" in b for b in result["blockers"])

    def test_08_tp_cannot_be_removed(self):
        """new_tp = 0 must be blocked (TP cannot be removed)."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="BUY",
            old_sl=2012.0, new_sl=2015.0,
            old_tp=2025.0, new_tp=0,  # Removed!
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert result["verdict"] == "BLOCKED"
        assert any("TP must be > 0" in b for b in result["blockers"])

    def test_09_sl_profit_floor_enforced_buy(self):
        """BUY: new_sl < entry + locked_R * R must be blocked."""
        builder = PairedSLTPModifyBuilder()
        # locked_R=1.2, R=10 => locked_profit_value=12
        # entry + locked_profit_value = 2000 + 12 = 2012
        # new_sl=2010 < 2012 -> blocked
        result = builder.build_preview(
            ticket=99999, direction="BUY",
            old_sl=2008.0, new_sl=2010.0,  # Below profit floor
            old_tp=2025.0, new_tp=2030.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert result["verdict"] == "BLOCKED"
        assert any("SL_PROFIT_FLOOR_NOT_MET" in b for b in result["blockers"])

    def test_10_sl_profit_floor_enforced_sell(self):
        """SELL: new_sl > entry - locked_R * R must be blocked."""
        builder = PairedSLTPModifyBuilder()
        # locked_R=1.2, R=10 => locked_profit_value=12
        # entry - locked_profit_value = 2000 - 12 = 1988
        # new_sl=1990 > 1988 -> blocked
        result = builder.build_preview(
            ticket=99999, direction="SELL",
            old_sl=1992.0, new_sl=1990.0,  # Above profit floor
            old_tp=1975.0, new_tp=1970.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert result["verdict"] == "BLOCKED"
        assert any("SL_PROFIT_FLOOR_NOT_MET" in b for b in result["blockers"])

    def test_11_stop_level_buffer_enforced(self):
        """Stop level buffer must be enforced."""
        builder = PairedSLTPModifyBuilder()
        # current_price=2020, new_sl=2019.5, stops_level_points=100, point=0.01
        # min_distance = 100 * 0.01 = 1.0
        # current_price - new_sl = 0.5 < 1.0 -> blocked
        result = builder.build_preview(
            ticket=99999, direction="BUY",
            old_sl=2012.0, new_sl=2019.5,  # Too close to current price
            old_tp=2025.0, new_tp=2030.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
            stops_level_points=100, point=0.01,
            current_price=2020.0,
        )
        assert result["verdict"] == "BLOCKED"
        assert any("STOP_LEVEL_TOO_CLOSE" in b for b in result["blockers"])

    def test_12_tp_below_sl_blocked_buy(self):
        """BUY: new_tp <= new_sl must be blocked."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="BUY",
            old_sl=2012.0, new_sl=2030.0,
            old_tp=2025.0, new_tp=2025.0,  # new_tp <= new_sl
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert result["verdict"] == "BLOCKED"
        assert any("TP_BELOW_SL" in b for b in result["blockers"])

    def test_13_invalid_ticket_blocked(self):
        """ticket <= 0 must be blocked."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=0, direction="BUY",
            old_sl=2012.0, new_sl=2015.0,
            old_tp=2025.0, new_tp=2030.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert result["verdict"] == "BLOCKED"
        assert any("Invalid ticket" in b for b in result["blockers"])

    def test_14_invalid_direction_blocked(self):
        """Invalid direction must be blocked."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="INVALID",
            old_sl=2012.0, new_sl=2015.0,
            old_tp=2025.0, new_tp=2030.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert result["verdict"] == "BLOCKED"
        assert any("Invalid direction" in b for b in result["blockers"])

    def test_15_action_is_trade_action_sltp(self):
        """Action must be TRADE_ACTION_SLTP."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="BUY",
            old_sl=2012.0, new_sl=2015.0,
            old_tp=2025.0, new_tp=2030.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert result["action"] == "TRADE_ACTION_SLTP"

    def test_16_preview_has_required_fields(self):
        """Preview must have all required fields."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="BUY",
            old_sl=2012.0, new_sl=2015.0,
            old_tp=2025.0, new_tp=2030.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        preview = result["preview"]
        required = [
            "action", "ticket", "symbol", "direction",
            "old_sl", "new_sl", "old_tp", "new_tp",
            "magic", "comment", "favorable_sl",
            "no_tp_reduction", "no_sl_widening",
            "tp_preserved_or_extended", "sl_profit_floor_R",
            "locked_profit_value", "reason", "blockers",
        ]
        for field in required:
            assert field in preview, f"Missing field: {field}"

    def test_17_no_order_send_in_builder(self):
        """Builder must NOT call mt5.order_send or mt5.order_modify."""
        src = (REPO_ROOT / "titan" / "production" / "paired_sltp_modify_builder.py").read_text()
        code = _strip(src)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
        assert not re.search(r"\bmt5\.order_modify\s*\(", code)

    def test_18_no_martingale_in_builder(self):
        """Builder must NOT contain martingale/grid/averaging."""
        src = (REPO_ROOT / "titan" / "production" / "paired_sltp_modify_builder.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot",
                     "loss_based_lot", "recovery_multiplier"]:
            assert term not in code, f"Forbidden term '{term}' in builder"

    def test_19_no_loss_based_lot_multiplier(self):
        """Builder must NOT implement loss-based lot multiplier."""
        src = (REPO_ROOT / "titan" / "production" / "paired_sltp_modify_builder.py").read_text()
        code = _strip(src).lower()
        assert "loss_based_lot" not in code
        assert "double_after_loss" not in code

    def test_20_no_mojibake(self):
        src = (REPO_ROOT / "titan" / "production" / "paired_sltp_modify_builder.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src

    def test_21_important_note_present(self):
        """Result must include important note about no order_send."""
        builder = PairedSLTPModifyBuilder()
        result = builder.build_preview(
            ticket=99999, direction="BUY",
            old_sl=2012.0, new_sl=2015.0,
            old_tp=2025.0, new_tp=2030.0,
            entry_price=2000.0, R=10.0, locked_R=1.2,
            reason="test",
        )
        assert "important_note" in result
        assert "PREVIEW only" in result["important_note"]
        assert "No mt5.order_send" in result["important_note"]
