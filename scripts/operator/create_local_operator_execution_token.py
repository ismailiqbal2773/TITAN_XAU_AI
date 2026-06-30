#!/usr/bin/env python3
"""
TITAN XAU AI - Local Operator Execution Token (Sprint 9.9.3.44.4)
==================================================================
Creates a short-lived local execution token for the operator's Windows machine.
NEVER contains password/account/secret. Gitignored. Expires.
"""
from __future__ import annotations
import argparse, hashlib, json, platform, subprocess, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOKEN_DIR = REPO_ROOT / "data" / "runtime" / "operator_tokens"
TOKEN_PATH = TOKEN_DIR / "demo_micro_execute_once.token"


def _git_head_short() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def create_token(symbol: str = "XAUUSD", lot: float = 0.01,
                  broker: str = "MetaQuotes-Demo", expiry_minutes: int = 10) -> dict:
    ts = datetime.now(timezone.utc)
    expiry = ts + timedelta(minutes=expiry_minutes)
    head = _git_head_short()
    machine_sig = f"{platform.platform()}-{platform.machine()}-{sys.version_info.major}.{sys.version_info.minor}"

    token = {
        "created_utc": ts.isoformat(),
        "expires_utc": expiry.isoformat(),
        "git_commit": head,
        "machine_signature": machine_sig,
        "symbol": symbol,
        "lot": lot,
        "broker": broker,
        "token_hash": hashlib.sha256(f"{ts.isoformat()}-{head}-{machine_sig}".encode()).hexdigest()[:32],
        "consumed": False,
        "warning": "This token is local-only, short-lived, and contains no secrets. Do not commit.",
    }
    TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
        json.dump(token, f, indent=2, ensure_ascii=False)
    return token


def load_and_validate_token() -> dict:
    """Load token and check validity. Returns {valid, reason, token}."""
    if not TOKEN_PATH.exists():
        return {"valid": False, "reason": "Token file not found", "token": None}
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as f:
            token = json.load(f)
    except Exception as e:
        return {"valid": False, "reason": f"Token read error: {e}", "token": None}
    if token.get("consumed"):
        return {"valid": False, "reason": "Token already consumed", "token": token}
    expiry_str = token.get("expires_utc", "")
    try:
        expiry = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > expiry:
            return {"valid": False, "reason": "Token expired", "token": token}
    except Exception:
        return {"valid": False, "reason": "Token expiry parse error", "token": token}
    return {"valid": True, "reason": "Token valid", "token": token}


def consume_token() -> None:
    """Mark token as consumed."""
    if not TOKEN_PATH.exists():
        return
    try:
        with open(TOKEN_PATH, "r", encoding="utf-8") as f:
            token = json.load(f)
        token["consumed"] = True
        token["consumed_utc"] = datetime.now(timezone.utc).isoformat()
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            json.dump(token, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Create local operator execution token")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--lot", type=float, default=0.01)
    parser.add_argument("--broker", default="MetaQuotes-Demo")
    parser.add_argument("--expiry-minutes", type=int, default=10)
    args = parser.parse_args()

    print("=" * 70)
    print("  TITAN XAU AI - Local Operator Execution Token (Sprint 9.9.3.44.4)")
    print("=" * 70)
    token = create_token(args.symbol, args.lot, args.broker, args.expiry_minutes)
    print(f"\n  Token created: {TOKEN_PATH}")
    print(f"  Expires: {token['expires_utc']}")
    print(f"  Symbol: {token['symbol']}")
    print(f"  Lot: {token['lot']}")
    print(f"  Broker: {token['broker']}")
    print(f"  Git: {token['git_commit']}")
    print(f"\n  WARNING: Token is local-only, short-lived, and gitignored.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
