"""TITAN XAU AI - Sprint 9.9.3.45.5 Manage Demo Micro Position Operator Tests

Sprint 9.9.3.45.5 adds:
  - Preview does not write stale recommendation if position no longer exists
  - POSITION_DISAPPEARED_DURING_PREVIEW warning when position disappears
  - POSITION_CLOSED_BEFORE_PREVIEW verdict when all candidates disappear
  - Double-scan verification (found_count vs verified_count)
  - No order_send, no modification
"""
from __future__ import annotations
import re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


def _strip(src):
    src = re.sub(r'"""[\s\S]*?"""', '""', src)
    src = re.sub(r"'''[\s\S]*?'''", "''", src)
    src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
    src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
    return src


class TestManagePosition:
    def test_01_check_only_returns_result(self):
        import scripts.operator.manage_demo_micro_position as mp
        result = mp.run_check_only()
        assert "verdict" in result and result["mode"] == "check_only"

    def test_02_preview_trailing_returns_result(self):
        import scripts.operator.manage_demo_micro_position as mp
        result = mp.run_preview_trailing()
        assert "verdict" in result and result["mode"] == "preview_trailing"

    def test_03_apply_once_blocks_without_confirm(self):
        import scripts.operator.manage_demo_micro_position as mp
        class FakeArgs:
            confirm_local_operator = False
        result = mp.run_apply_once(FakeArgs())
        assert result["verdict"] == "MANAGE_REFUSED"
        assert any("local-operator" in b.lower() for b in result["blockers"])

    def test_04_apply_once_blocks_in_z_ai(self):
        import scripts.operator.manage_demo_micro_position as mp
        class FakeArgs:
            confirm_local_operator = True
        result = mp.run_apply_once(FakeArgs())
        assert result["verdict"] == "MANAGE_REFUSED"

    def test_05_no_order_send_in_preview(self):
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        code = _strip(src)
        lines = code.splitlines()
        in_apply = False
        for line in lines:
            if "def run_apply_once" in line:
                in_apply = True
            elif line and not line[0].isspace() and "def " in line:
                in_apply = False
            if "mt5.order_send" in line and not in_apply:
                pytest.fail(f"order_send found outside apply_once: {line.strip()}")

    def test_06_no_demo_micro_execute(self):
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        code = _strip(src)
        assert not re.search(r"(?<!['\"])\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\(", code)

    def test_07_no_raw_mt5_probe(self):
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        code = _strip(src)
        assert not re.search(r"(?<!['\"])\b(run_raw_probe|raw_mt5_probe)\s*\(", code)

    # === Sprint 9.9.3.45.5 new tests ===

    def test_08_preview_has_found_and_verified_counts(self):
        """Preview must report found_count and verified_count fields."""
        import scripts.operator.manage_demo_micro_position as mp
        result = mp.run_preview_trailing()
        assert "found_count" in result
        assert "verified_count" in result

    def test_09_preview_has_disappeared_tickets_field(self):
        """Preview must report disappeared_tickets field."""
        import scripts.operator.manage_demo_micro_position as mp
        result = mp.run_preview_trailing()
        assert "disappeared_tickets" in result

    def test_10_preview_no_position_found_when_empty(self):
        """When positions_get is empty, verdict must be NO_POSITION_FOUND."""
        import scripts.operator.manage_demo_micro_position as mp
        result = mp.run_preview_trailing()
        # MT5 stub has no positions by default
        assert result["verdict"] == "NO_POSITION_FOUND"
        assert result["found_count"] == 0
        assert result["verified_count"] == 0
        assert result["count"] == 0

    def test_11_preview_double_scan_pattern(self):
        """Preview must use double-scan verification pattern."""
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        # Must call positions_get twice (or use verify_tickets pattern)
        assert "verify_positions" in src or "verify_tickets" in src
        assert "verified_alive" in src
        assert "verification_method" in src

    def test_12_position_disappeared_during_preview_warning(self):
        """If position disappears between scans, must include warning."""
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        assert "POSITION_DISAPPEARED_DURING_PREVIEW" in src

    def test_13_position_closed_before_preview_verdict(self):
        """When all candidates disappear, verdict must be
        POSITION_CLOSED_BEFORE_PREVIEW."""
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        assert "POSITION_CLOSED_BEFORE_PREVIEW" in src

    def test_14_preview_generated_with_warnings_verdict(self):
        """When some candidates disappear and some remain, verdict must be
        PREVIEW_GENERATED_WITH_WARNINGS."""
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        assert "PREVIEW_GENERATED_WITH_WARNINGS" in src

    def test_15_no_mojibake(self):
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        assert "\u2014" not in src
        assert "\u2013" not in src

    def test_16_no_martingale(self):
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot"]:
            assert term not in code, f"Forbidden term '{term}' in code"

    def test_17_no_position_modification_in_preview(self):
        """Preview must NOT call order_modify/positions_modify/order_send.

        Sprint 9.9.3.45.6: apply-once (run_apply_once) is allowed to
        call mt5.order_send, but run_preview_trailing and run_check_only
        must not.
        """
        src = (REPO_ROOT / "scripts" / "operator" / "manage_demo_micro_position.py").read_text()
        code = _strip(src)
        lines = code.splitlines()
        # Track which function we're in
        current_fn = None
        for line in lines:
            m = re.match(r"^def (\w+)", line)
            if m:
                current_fn = m.group(1)
            # Preview and check_only must not call mt5.order_send
            if current_fn in ("run_preview_trailing", "run_check_only"):
                if re.search(r"\bmt5\.(order_modify|positions_modify|order_send)\s*\(", line):
                    pytest.fail(
                        f"mt5 order/modify call in {current_fn}: {line.strip()}"
                    )

    def test_18_preview_with_mock_position_that_disappears(self, monkeypatch):
        """Simulate: first positions_get returns a TITAN position, second
        returns empty. Verdict must include disappeared warning."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub

        # Create a fake TITAN position
        fake_position = stub._Position(ticket=99999, magic=202619, comment="TITAN_DEMO_MICRO")
        call_count = [0]
        original_positions_get = stub.positions_get

        def fake_positions_get(ticket=None, symbol=None):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: return the TITAN position
                return (fake_position,)
            else:
                # Second call: position disappeared
                return ()

        # Patch MetaTrader5 in the manage_demo_micro_position module
        import sys as _sys
        monkeypatch.setattr(stub, "positions_get", fake_positions_get)
        monkeypatch.setattr(_sys.modules["MetaTrader5"], "positions_get", fake_positions_get)

        result = mp.run_preview_trailing()
        # The TITAN position disappeared between first and second scan
        assert result["found_count"] == 1
        assert result["verified_count"] == 0
        assert len(result["disappeared_tickets"]) == 1
        assert 99999 in result["disappeared_tickets"]
        assert any("POSITION_DISAPPEARED_DURING_PREVIEW" in w for w in result["warnings"])

    def test_19_preview_with_mock_position_verified(self, monkeypatch):
        """Simulate: position exists in both scans, recommendation should
        be generated with verified_alive=True."""
        import scripts.operator.manage_demo_micro_position as mp
        import titan.mt5_stub as stub
        import sys as _sys

        fake_position = stub._Position(
            ticket=88888, magic=202619, comment="TITAN_DEMO_MICRO",
            price_open=2000.0, price_current=2003.0, sl=1990.0, tp=2010.0,
        )

        def fake_positions_get(ticket=None, symbol=None):
            return (fake_position,)

        monkeypatch.setattr(stub, "positions_get", fake_positions_get)
        monkeypatch.setattr(_sys.modules["MetaTrader5"], "positions_get", fake_positions_get)

        result = mp.run_preview_trailing()
        assert result["found_count"] == 1
        assert result["verified_count"] == 1
        assert result["verdict"] == "PREVIEW_GENERATED"
        assert len(result["recommendations"]) == 1
        rec = result["recommendations"][0]
        assert rec["ticket"] == 88888
        assert rec["verified_alive"] is True
        assert rec["verification_method"] == "positions_get_double_scan"
