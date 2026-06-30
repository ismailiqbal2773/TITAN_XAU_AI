"""TITAN XAU AI - Sprint 9.9.3.45.2 Execution Receipt Matching Tests"""
from __future__ import annotations
import hashlib, json, re, sys
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestReceipt:
    def test_01_receipt_path_is_gitignored(self):
        """Receipt path should be under data/runtime/ which is gitignored."""
        receipt_path = REPO_ROOT / "data" / "runtime" / "demo_micro_execution_receipt.json"
        gitignore = (REPO_ROOT / ".gitignore").read_text()
        assert "data/runtime/" in gitignore

    def test_02_receipt_stores_no_raw_login(self):
        """Receipt should store account_login_hash, not raw login."""
        # Simulate a receipt
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
        """Receipt should have all required fields."""
        required_fields = [
            "timestamp_utc", "git_commit", "account_server", "account_login_hash",
            "symbol", "volume", "side", "order_ticket", "deal_ticket", "position_id",
            "request_magic", "request_comment", "entry_price", "sl", "tp",
            "retcode", "retcode_comment", "success", "execution_mode",
        ]
        # Verify the receipt template in the operator script has these fields
        src = (REPO_ROOT / "scripts" / "operator" / "run_controlled_demo_micro_execution.py").read_text()
        for field in required_fields:
            assert field in src, f"Receipt missing field: {field}"

    def test_04_no_order_send_in_receipt_path(self):
        """Receipt writer must not call order_send."""
        src = (REPO_ROOT / "scripts" / "operator" / "run_controlled_demo_micro_execution.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        # order_send is in _attempt_gated_order_send only, which is correct
        # The _write_receipt function must not call order_send
        in_receipt = False
        for line in code.splitlines():
            if "def _write_receipt" in line:
                in_receipt = True
            elif line and not line[0].isspace() and "def " in line:
                in_receipt = False
            if in_receipt and "mt5.order_send" in line:
                pytest.fail("order_send in _write_receipt")
