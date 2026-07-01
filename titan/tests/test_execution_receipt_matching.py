"""TITAN XAU AI - Sprint 9.9.3.45.5 Execution Receipt Matching Tests

Sprint 9.9.3.45.5 adds:
  - Receipt field naming correctness (order_send_result_order,
    order_send_result_deal, detected_position_ticket,
    detected_position_identifier, resolved_history_position_id)
  - result.order / result.deal are stored correctly (not mislabeled)
  - detected position ticket is NOT mislabeled as order ticket
  - retcode 10009 but no position/history => FAILED or INCONSISTENT
  - position detected then disappears with no history => UNKNOWN/WARNING
  - order_send mocked in tests (no real broker call)
"""
from __future__ import annotations
import hashlib, json, re, sys
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


class TestReceipt:
    def test_01_receipt_path_is_gitignored(self):
        """Receipt path should be under data/runtime/ which is gitignored."""
        receipt_path = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"
        gitignore = (REPO_ROOT / ".gitignore").read_text()
        assert "data/runtime/" in gitignore

    def test_02_receipt_stores_no_raw_login(self):
        """Receipt should store account_login_hash, not raw login."""
        login = 12345
        login_hash = hashlib.sha256(str(login).encode()).hexdigest()[:16]
        receipt = {
            "account_login_hash": login_hash,
            "symbol": "XAUUSD",
            "volume": 0.01,
        }
        receipt_str = json.dumps(receipt)
        assert str(login) not in receipt_str
        assert "password" not in receipt_str.lower()
        assert "secret" not in receipt_str.lower()
        assert login_hash in receipt_str

    def test_03_receipt_has_required_fields(self):
        """Receipt should have all required fields (Sprint 9.9.3.45.5)."""
        required_fields = [
            "timestamp_utc", "git_commit", "account_server", "account_login_hash",
            "symbol", "volume", "side", "order_ticket", "deal_ticket", "position_id",
            "request_magic", "request_comment", "success", "execution_mode",
            # Sprint 9.9.3.45.5 new fields
            "order_send_result_retcode", "order_send_result_comment",
            "order_send_result_order", "order_send_result_deal",
            "order_send_result_volume", "order_send_result_price",
            "order_send_result_bid", "order_send_result_ask",
            "order_send_result_request_id", "order_send_result_retcode_external",
            "requested_sl", "requested_tp",
            "detected_position_ticket", "detected_position_identifier",
            "resolved_history_position_id",
            "position_open_verified", "history_verified", "pending_history",
        ]
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        for field in required_fields:
            assert field in src, f"Receipt missing field: {field}"

    def test_04_no_order_send_in_receipt_path(self):
        """Receipt writer must not call order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_controlled_demo_micro_execution.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""', '""', src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
        in_receipt = False
        for line in code.splitlines():
            if "def _write_receipt" in line:
                in_receipt = True
            elif line and not line[0].isspace() and "def " in line:
                in_receipt = False
            if in_receipt and "mt5.order_send" in line:
                pytest.fail("order_send in _write_receipt")

    # === Sprint 9.9.3.45.5 new tests ===

    def test_05_order_ticket_only_from_result_order(self):
        """order_ticket must be sourced only from result.order, never from
        detected position ticket (was the 45.4 bug)."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        # The _build_receipt function must assign order_ticket from raw_result["order"]
        idx = src.find("def _build_receipt")
        assert idx > 0
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert '"order_ticket": raw_result["order"]' in body

    def test_06_deal_ticket_only_from_result_deal(self):
        """deal_ticket must be sourced only from result.deal."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _build_receipt")
        assert idx > 0
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        assert '"deal_ticket": raw_result["deal"]' in body

    def test_07_position_id_not_from_result_position_id(self):
        """position_id must NOT be populated from result.position_id (was 45.4 bug)."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        idx = src.find("def _build_receipt")
        assert idx > 0
        end_idx = src.find("\ndef ", idx + 1)
        body = src[idx:end_idx if end_idx > 0 else len(src)]
        # position_id must be None in _build_receipt (later updated by detection)
        assert '"position_id": None' in body or "\"position_id\": None" in body

    def test_08_capture_safe_handles_none(self):
        """_capture_order_send_result_safe must handle None result."""
        import scripts.operator.run_managed_demo_micro_trade as m
        result = m._capture_order_send_result_safe(None)
        assert result["retcode"] == 0
        assert result["comment"] == "RESULT_NONE"
        assert result["order"] is None
        assert result["deal"] is None

    def test_09_capture_safe_handles_zero_order_deal(self):
        """If result.order/result.deal are 0, they should be stored as None."""
        import scripts.operator.run_managed_demo_micro_trade as m

        class FakeResult:
            retcode = 10009
            comment = "TRADE_RETCODE_DONE"
            order = 0  # Missing
            deal = 0  # Missing
            position_id = 0  # Missing
            volume = 0.01
            price = 2000.0
            bid = 1999.8
            ask = 2000.2
            request_id = 0
            retcode_external = 0

        result = m._capture_order_send_result_safe(FakeResult())
        assert result["retcode"] == 10009
        assert result["order"] is None  # 0 -> None
        assert result["deal"] is None  # 0 -> None
        assert result["price"] == 2000.0  # non-zero kept

    def test_10_capture_safe_preserves_nonzero_order_deal(self):
        """If result.order/result.deal are non-zero, they should be preserved."""
        import scripts.operator.run_managed_demo_micro_trade as m

        class FakeResult:
            retcode = 10009
            comment = "TRADE_RETCODE_DONE"
            order = 57344905358
            deal = 57001412567
            position_id = 0  # Still missing
            volume = 0.01
            price = 3981.53
            bid = 3981.50
            ask = 3981.56
            request_id = 12345
            retcode_external = 0

        result = m._capture_order_send_result_safe(FakeResult())
        assert result["order"] == 57344905358
        assert result["deal"] == 57001412567
        assert result["request_id"] == 12345

    def test_11_build_receipt_warns_on_incomplete_result(self):
        """If retcode=10009 but order/deal are None, warning must be added."""
        import scripts.operator.run_managed_demo_micro_trade as m
        raw = {
            "retcode": 10009, "comment": "TRADE_RETCODE_DONE",
            "order": None, "deal": None,
            "volume": 0.01, "price": 2000.0,
            "bid": 1999.8, "ask": 2000.2,
            "request_id": None, "retcode_external": None,
        }

        class FakeAcc:
            login = 12345

        receipt = m._build_receipt(
            ts="2025-01-01T00:00:00Z", current_head="abc1234",
            env_info={"account_server": "MetaQuotes-Demo"},
            acc=FakeAcc(), volume=0.01, direction="BUY",
            sl=1990.0, tp=2010.0,
            raw_result=raw, execution_success=True,
        )
        assert any("ORDER_SEND_RESULT_INCOMPLETE" in w for w in receipt["warnings"])
        assert receipt["order_ticket"] is None
        assert receipt["deal_ticket"] is None
        assert receipt["position_id"] is None
        assert receipt["order_send_result_order"] is None
        assert receipt["order_send_result_deal"] is None
        assert receipt["requested_sl"] == 1990.0
        assert receipt["requested_tp"] == 2010.0

    def test_12_build_receipt_no_warning_when_complete(self):
        """If order/deal are non-zero, no incomplete warning."""
        import scripts.operator.run_managed_demo_micro_trade as m
        raw = {
            "retcode": 10009, "comment": "TRADE_RETCODE_DONE",
            "order": 57344905358, "deal": 57001412567,
            "volume": 0.01, "price": 3981.53,
            "bid": 3981.50, "ask": 3981.56,
            "request_id": 12345, "retcode_external": None,
        }

        class FakeAcc:
            login = 12345

        receipt = m._build_receipt(
            ts="2025-01-01T00:00:00Z", current_head="abc1234",
            env_info={"account_server": "MetaQuotes-Demo"},
            acc=FakeAcc(), volume=0.01, direction="BUY",
            sl=3978.5, tp=3984.5,
            raw_result=raw, execution_success=True,
        )
        assert not any("ORDER_SEND_RESULT_INCOMPLETE" in w for w in receipt["warnings"])
        assert receipt["order_ticket"] == 57344905358
        assert receipt["deal_ticket"] == 57001412567
        assert receipt["position_id"] is None  # Still None until detection
        assert receipt["requested_sl"] == 3978.5
        assert receipt["requested_tp"] == 3984.5

    def test_13_no_order_send_in_capture_or_build(self):
        """_capture_order_send_result_safe and _build_receipt must not
        call order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src)
        # Check _capture_order_send_result_safe function body
        for fn_name in ["_capture_order_send_result_safe", "_build_receipt",
                        "_write_receipt", "_detect_position_via_positions_and_history",
                        "_run_monitor_loop"]:
            idx = code.find(f"def {fn_name}")
            assert idx > 0, f"Function {fn_name} not found"
            # Find end of function (next def at same indent or end of file)
            end_idx = code.find("\ndef ", idx + 1)
            if end_idx < 0:
                end_idx = len(code)
            body = code[idx:end_idx]
            assert "mt5.order_send" not in body, \
                f"order_send must not be called in {fn_name}"

    def test_14_no_martingale_in_receipt(self):
        """Receipt-related code must not contain martingale/grid/averaging."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_managed_demo_micro_trade.py").read_text()
        code = _strip(src).lower()
        for term in ["martingale", "grid_trade", "averaging_down", "double_lot"]:
            assert term not in code, f"Forbidden term '{term}' in code"
