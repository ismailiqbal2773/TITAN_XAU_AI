"""TITAN XAU AI - Sprint 9.9.3.44.4 Local Operator Execution Token Tests"""
from __future__ import annotations
import json, re, sys, time
from pathlib import Path
import pytest
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestToken:
    def test_01_create_token_writes_file(self, tmp_path):
        import scripts.operator.create_local_operator_execution_token as tok
        old = tok.TOKEN_DIR; tok.TOKEN_DIR = tmp_path; tok.TOKEN_PATH = tmp_path / "token.json"
        try:
            token = tok.create_token()
            assert tok.TOKEN_PATH.exists()
            with open(tok.TOKEN_PATH) as f: data = json.load(f)
            assert data["symbol"] == "XAUUSD"
            assert data["lot"] == 0.01
            assert data["broker"] == "MetaQuotes-Demo"
            assert "token_hash" in data
            assert "expires_utc" in data
            assert data["consumed"] is False
        finally: tok.TOKEN_DIR = old; tok.TOKEN_PATH = old / "demo_micro_execute_once.token" if old else tok.TOKEN_PATH

    def test_02_token_expires(self, tmp_path):
        import scripts.operator.create_local_operator_execution_token as tok
        old = tok.TOKEN_DIR; tok.TOKEN_DIR = tmp_path; tok.TOKEN_PATH = tmp_path / "token.json"
        try:
            tok.create_token(expiry_minutes=0)  # Expires immediately
            result = tok.load_and_validate_token()
            assert result["valid"] is False
            assert "expired" in result["reason"].lower()
        finally: tok.TOKEN_DIR = old; tok.TOKEN_PATH = old / "demo_micro_execute_once.token" if old else tok.TOKEN_PATH

    def test_03_token_consumed(self, tmp_path):
        import scripts.operator.create_local_operator_execution_token as tok
        old = tok.TOKEN_DIR; tok.TOKEN_DIR = tmp_path; tok.TOKEN_PATH = tmp_path / "token.json"
        try:
            tok.create_token(expiry_minutes=10)
            tok.consume_token()
            result = tok.load_and_validate_token()
            assert result["valid"] is False
            assert "consumed" in result["reason"].lower()
        finally: tok.TOKEN_DIR = old; tok.TOKEN_PATH = old / "demo_micro_execute_once.token" if old else tok.TOKEN_PATH

    def test_04_token_no_secrets(self, tmp_path):
        import scripts.operator.create_local_operator_execution_token as tok
        old = tok.TOKEN_DIR; tok.TOKEN_DIR = tmp_path; tok.TOKEN_PATH = tmp_path / "token.json"
        try:
            token = tok.create_token()
            token_str = json.dumps(token)
            assert "password" not in token_str.lower()
            assert "login" not in token_str.lower() or "login" not in token
            assert "api_key" not in token_str.lower()
            assert "secret" not in token_str.lower() or "secret" not in token
        finally: tok.TOKEN_DIR = old; tok.TOKEN_PATH = old / "demo_micro_execute_once.token" if old else tok.TOKEN_PATH

    def test_05_no_order_send_in_token_script(self):
        src = (REPO_ROOT / "scripts" / "operator" / "create_local_operator_execution_token.py").read_text()
        code = re.sub(r'"""[\s\S]*?"""','""',src)
        code = re.sub(r'"(?:[^"\\]|\\.)*"','""',code)
        code = re.sub(r"'(?:[^'\\]|\\.)*'","''",code)
        assert not re.search(r"\bmt5\.order_send\s*\(", code)
