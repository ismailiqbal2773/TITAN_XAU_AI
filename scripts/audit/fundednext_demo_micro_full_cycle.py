"""
TITAN XAU AI — Sprint 9.9.3 FundedNext Demo Micro Full-Cycle Harness
=====================================================================

Two modes:
  DRY_ARM_CHECK_ONLY  — checks gates, no order, safe to run anywhere
  DEMO_MICRO_EXECUTE  — operator-only, requires arm token + DEMO account
                        ACTUALLY opens AND closes ONE DEMO MT5 order

Z AI must NEVER run DEMO_MICRO_EXECUTE.
Only the operator may run this on local Windows MT5 DEMO.

Safety invariants:
  - DEMO account only (hard block on REAL/CONTEST)
  - lot <= 0.01 (hard block above)
  - max_open_positions = 1 (block if any existing open position for symbol)
  - max_trades_per_run = 1 by default (no duplicates ever sent)
  - No martingale, no grid, no averaging, no lot escalation
  - Arm token TITAN_DEMO_MICRO_ARMED=1 required
  - Hard gate verdict DEMO_MICRO_ARMED required
  - Force-close on end is default true
  - Position sync verifies exactly one matching position before monitoring
  - Close uses opposite side (BUY -> SELL, SELL -> BUY) with same volume
  - Final verdict DEMO_FULL_CYCLE_PASS only when no open positions remain
  - On any failure: DEMO_MANUAL_REVIEW_REQUIRED or DEMO_FULL_CYCLE_FAIL
"""
from __future__ import annotations
import argparse, asyncio, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from scripts.audit.demo_micro_hard_gate import evaluate as hard_gate_evaluate
from scripts.audit.demo_micro_config import load_demo_micro_config
from titan.production.trade_journal import TradeJournal  # noqa: F401 (kept for compat)

OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

JOURNAL_PATH = OUTPUT_DIR / "demo_micro_journal.jsonl"

# Magic number for TITAN DEMO MICRO (distinct from production magic 202619)
DEMO_MICRO_MAGIC = 20261993

# MT5 constants (defined here to avoid importing MT5 at module load on Linux)
_TRADE_ACTION_DEAL = 1
_ORDER_TYPE_BUY = 0
_ORDER_TYPE_SELL = 1
_TRADE_RETCODE_DONE = 10009

# Sprint 9.9.3.14 patch — retcode 10027 means client terminal autotrading
# is disabled (account_info.trade_expert=False). Hard gate must block before
# order_send is ever attempted in this state.
_TRADE_RETCODE_AUTOTRADING_DISABLED = 10027
_RETCODE_10027_MEANING = "client terminal autotrading disabled"

# Sprint 9.9.3.15 patch — retcode 10030 means the order filling type is
# not supported by the symbol/broker (TRADE_RETCODE_INVALID_FILL).
# FBS XAUUSD returns this when type_filling=ORDER_FILLING_RETURN (4)
# is sent blindly — we must auto-detect supported modes instead.
_TRADE_RETCODE_INVALID_FILL = 10030
_RETCODE_10030_MEANING = "invalid order filling type (TRADE_RETCODE_INVALID_FILL)"

# Sprint 9.9.3.15 patch — MT5 order filling modes (MQL5 ORDER_TYPE_FILLING enum).
# Reference: https://www.mql5.com/en/docs/constants/tradingconstants/orderproperties
# Used as values for the `type_filling` field in mt5.order_send() request dicts.
ORDER_FILLING_FOK = 1     # Fill or Kill — entire volume or none
ORDER_FILLING_IOC = 2     # Immediate or Cancel — partial fills allowed
ORDER_FILLING_BOC = 3     # Book or Cancel — market depth only, NOT for market orders
ORDER_FILLING_RETURN = 4  # Return — requotes allowed, older default

# Bitmask bit positions in symbol_info.filling_mode (each bit = supported mode).
# These are different from the ORDER_FILLING_* enum values above — they are
# powers of two used as flags in the symbol's filling_mode attribute.
_SYMBOL_FILLING_FOK_BIT = 1     # bit 0
_SYMBOL_FILLING_IOC_BIT = 2     # bit 1
_SYMBOL_FILLING_BOC_BIT = 4     # bit 2
_SYMBOL_FILLING_RETURN_BIT = 8  # bit 3

# Preference order for market orders: FOK → IOC → RETURN.
# BOC is excluded because it is only valid for pending orders in market depth,
# not for TRADE_ACTION_DEAL (market) orders used by DEMO_MICRO_EXECUTE.
_FILLING_PREFERENCE = [
    (ORDER_FILLING_FOK,    "FOK",    _SYMBOL_FILLING_FOK_BIT),
    (ORDER_FILLING_IOC,    "IOC",    _SYMBOL_FILLING_IOC_BIT),
    (ORDER_FILLING_RETURN, "RETURN", _SYMBOL_FILLING_RETURN_BIT),
]

# Default bitmask to use when symbol_info.filling_mode is missing or 0.
# Older MT5 builds or some brokers may not populate this attribute. We treat
# all three market-order-valid modes as supported in that case (legacy
# behavior — broker must accept at least one, and the harness will probe
# via the actual order_send result if our first guess is wrong).
_DEFAULT_FILLING_MASK = (
    _SYMBOL_FILLING_FOK_BIT
    | _SYMBOL_FILLING_IOC_BIT
    | _SYMBOL_FILLING_RETURN_BIT
)

# Canonical retcode → meaning mapping table. Used by both _send_open_order
# and _close_position failure paths to enrich journal entries.
_RETCODE_MEANINGS = {
    _TRADE_RETCODE_DONE: "request completed",
    _TRADE_RETCODE_AUTOTRADING_DISABLED: _RETCODE_10027_MEANING,
    _TRADE_RETCODE_INVALID_FILL: _RETCODE_10030_MEANING,
}


def _lookup_retcode_meaning(retcode) -> Optional[str]:
    """Return the canonical English meaning for a known MT5 retcode, else None."""
    if retcode is None:
        return None
    try:
        return _RETCODE_MEANINGS.get(int(retcode))
    except (TypeError, ValueError):
        return None


def _select_filling_mode(mt5, symbol: str) -> Optional[dict]:
    """Sprint 9.9.3.15 patch — auto-detect supported MT5 filling mode.

    Reads symbol_info.filling_mode bitmask and selects the most preferred
    filling mode that is supported for this symbol. Falls back to a
    permissive default if filling_mode is missing (older MT5 builds).

    Preference order for market orders:
        1. FOK   (strictest, best for market orders — entire volume or none)
        2. IOC   (partial fills allowed)
        3. RETURN (requotes — older brokers)
    BOC is excluded because it is only valid for pending orders in market
    depth, not for TRADE_ACTION_DEAL (market) orders used by DEMO_MICRO_EXECUTE.

    Args:
        mt5: MetaTrader5 module (or mock) — must expose symbol_info().
        symbol: e.g. "XAUUSD"

    Returns:
        dict with keys:
            - filling_type (int): value for `type_filling` in order_send request
            - filling_name (str): "FOK" | "IOC" | "RETURN"
            - filling_mask (int): the raw bitmask from symbol_info (or default)
            - filling_source (str): "symbol_info" | "default"
        OR None if no supported filling mode is available (fail-closed case).
    """
    try:
        info = mt5.symbol_info(symbol)
    except Exception:
        info = None
    if info is None:
        # Cannot query symbol info at all — caller should fail closed.
        return None

    mask = getattr(info, "filling_mode", None)
    filling_source = "symbol_info"
    if mask is None or mask == 0:
        # Older MT5 builds may not expose filling_mode — assume all
        # standard market-order modes are supported (legacy behavior).
        mask = _DEFAULT_FILLING_MASK
        filling_source = "default"

    for filling_type, filling_name, bit in _FILLING_PREFERENCE:
        if mask & bit:
            return {
                "filling_type": filling_type,
                "filling_name": filling_name,
                "filling_mask": mask,
                "filling_source": filling_source,
            }
    # Bitmask is set but no supported mode matches our preference
    # (e.g., only BOC is set, which is invalid for market orders).
    return None


# ─── Journal helper ────────────────────────────────────────────────────────────

def _journal_event(event_type: str, payload: dict) -> None:
    """Append a JSONL event to the demo micro journal."""
    entry = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "event": event_type,
        **payload,
    }
    JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(JOURNAL_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ─── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="FundedNext Demo Micro Full-Cycle")
    p.add_argument("--mode", choices=["DRY_ARM_CHECK_ONLY", "DEMO_MICRO_EXECUTE"],
                   default="DRY_ARM_CHECK_ONLY")
    p.add_argument("--max-trades", type=int, default=1)
    p.add_argument("--max-duration-minutes", type=int, default=240)
    p.add_argument("--symbol", type=str, default="XAUUSD")
    p.add_argument("--lot", type=float, default=0.01)
    p.add_argument("--side", choices=["BUY", "SELL"], default=None,
                   help="Operator test side. Required if no AI signal available.")
    p.add_argument("--max-hold-seconds", type=int, default=None,
                   help="If set, close position after N seconds (operator test mode).")
    p.add_argument("--force-close-on-end", choices=["true", "false"], default="true",
                   help="Force-close any remaining position on exit (default true).")
    return p.parse_args()


# ─── MT5 access helpers ────────────────────────────────────────────────────────

def _get_mt5():
    """Import MT5 module. Returns None if not installed (Z AI / Linux)."""
    try:
        import MetaTrader5 as mt5  # type: ignore
        return mt5
    except ImportError:
        return None


def _is_demo_account(account_info) -> bool:
    if account_info is None:
        return False
    # trade_mode: 0=DEMO, 1=CONTEST, 2=REAL
    return getattr(account_info, "trade_mode", 2) == 0


def _resolve_side(args, cfg) -> Optional[str]:
    """
    Resolve trade side:
      1. Try to load latest AI signal (best-effort, never raises)
      2. Fall back to --side CLI arg
      3. If neither, return None (BLOCKED — refuse to guess)
    """
    try:
        signal = _load_latest_ai_signal()
        if signal and signal.get("side") in ("BUY", "SELL"):
            return signal["side"]
    except Exception:
        pass
    if args.side in ("BUY", "SELL"):
        return args.side
    return None


def _load_latest_ai_signal() -> Optional[dict]:
    """Best-effort load of latest AI signal from titan journal."""
    journal_path = REPO_ROOT / "data" / "runtime" / "titan_journal.jsonl"
    if not journal_path.exists():
        return None
    try:
        with open(journal_path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-50:]
        for line in reversed(lines):
            try:
                evt = json.loads(line)
            except Exception:
                continue
            if evt.get("event") == "SIGNAL_CREATED":
                side = evt.get("side") or evt.get("direction")
                if side in ("BUY", "SELL"):
                    ts_str = evt.get("timestamp_utc", "")
                    if ts_str:
                        try:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            age = (datetime.now(timezone.utc) - ts).total_seconds()
                            if age > 300:  # 5 min stale
                                continue
                        except Exception:
                            pass
                    return {"side": side, "source": "ai_signal", "raw": evt}
    except Exception:
        pass
    return None


def _check_existing_position(mt5, symbol: str) -> tuple[bool, list]:
    """Returns (has_position, positions_list)."""
    try:
        positions = mt5.positions_get(symbol=symbol)
    except Exception:
        positions = []
    if positions is None:
        positions = []
    return len(positions) > 0, list(positions)


def _safe_request(req: dict) -> dict:
    """Make request JSON-serializable (MT5 enums etc)."""
    safe = {}
    for k, v in req.items():
        try:
            json.dumps(v)
            safe[k] = v
        except Exception:
            safe[k] = str(v)
    return safe


def _safe_position(p) -> dict:
    """Convert MT5 position to dict."""
    out = {}
    for attr in ("ticket", "identifier", "type", "volume", "price_open",
                 "price_current", "sl", "tp", "time", "magic", "symbol",
                 "profit", "swap", "commission"):
        try:
            out[attr] = getattr(p, attr, None)
        except Exception:
            out[attr] = None
    return out


def _send_open_order(mt5, symbol: str, side: str, lot: float, magic: int,
                     deviation: int = 20, comment: str = "TITAN_DEMO_MICRO") -> dict:
    """Send ONE market order. Returns dict with result info.

    Sprint 9.9.3.15 patch — filling mode is now auto-detected via
    _select_filling_mode() rather than hard-coded. If no supported
    filling mode is found, returns an error dict WITHOUT calling
    order_send (fail-closed before any broker interaction).
    """
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"ok": False, "error": "symbol_info_tick returned None", "retcode": None}

    # Sprint 9.9.3.15 patch — auto-detect supported filling mode
    filling = _select_filling_mode(mt5, symbol)
    if filling is None:
        # Fail closed BEFORE order_send — do not attempt to send with an
        # unsupported filling type (would return retcode=10030).
        return {
            "ok": False,
            "error": "no supported filling mode detected for symbol "
                     f"(symbol_info.filling_mode has no FOK/IOC/RETURN bit set)",
            "retcode": None,
            "filling_mode_selected": None,
            "filling_type_used": None,
        }

    # Entry price based on side
    if side == "BUY":
        price = float(getattr(tick, "ask", 0.0) or 0.0)
    else:
        price = float(getattr(tick, "bid", 0.0) or 0.0)

    # DEMO safety: small fixed SL/TP around current price (prevents runaway)
    sl_distance = 5.0   # $5 SL
    tp_distance = 10.0  # $10 TP
    if side == "BUY":
        sl = price - sl_distance
        tp = price + tp_distance
    else:
        sl = price + sl_distance
        tp = price - tp_distance

    request = {
        "action": _TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(lot),
        "type": _ORDER_TYPE_BUY if side == "BUY" else _ORDER_TYPE_SELL,
        "price": price,
        "sl": float(sl),
        "tp": float(tp),
        "deviation": deviation,
        "magic": magic,
        "comment": comment,
        "type_time": 0,        # ORDER_TIME_GTC
        "type_filling": filling["filling_type"],   # auto-detected (Sprint 9.9.3.15)
    }

    result = mt5.order_send(request)
    if result is None:
        return {"ok": False, "error": "order_send returned None", "retcode": None,
                "request": _safe_request(request),
                "filling_mode_selected": filling["filling_name"],
                "filling_type_used": filling["filling_type"]}
    return {
        "ok": getattr(result, "retcode", 0) == _TRADE_RETCODE_DONE,
        "retcode": getattr(result, "retcode", None),
        "order": getattr(result, "order", None),
        "deal": getattr(result, "deal", None),
        "volume": getattr(result, "volume", None),
        "price": getattr(result, "price", None),
        "comment": getattr(result, "comment", ""),
        "request": _safe_request(request),
        "filling_mode_selected": filling["filling_name"],
        "filling_type_used": filling["filling_type"],
        "filling_source": filling["filling_source"],
        "filling_mask": filling["filling_mask"],
    }


def _sync_position(mt5, symbol: str, magic: int, timeout_s: float = 5.0) -> Optional[dict]:
    """
    Wait briefly for position to appear, then query positions_get.
    Returns position dict if exactly one matching position found.
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            positions = mt5.positions_get(symbol=symbol)
        except Exception:
            positions = None
        if positions:
            matching = [p for p in positions if getattr(p, "magic", 0) == magic]
            if len(matching) == 1:
                p = matching[0]
                return {
                    "ticket": getattr(p, "ticket", None),
                    "position_id": getattr(p, "identifier", None) or getattr(p, "ticket", None),
                    "type": "BUY" if getattr(p, "type", 1) == 0 else "SELL",
                    "volume": getattr(p, "volume", None),
                    "price_open": getattr(p, "price_open", None),
                    "sl": getattr(p, "sl", None),
                    "tp": getattr(p, "tp", None),
                    "time": getattr(p, "time", None),
                    "magic": getattr(p, "magic", None),
                    "symbol": getattr(p, "symbol", None),
                    "raw": _safe_position(p),
                }
        time.sleep(0.5)
    return None


def _close_position(mt5, position: dict, magic: int,
                    deviation: int = 20,
                    comment: str = "TITAN_DEMO_MICRO_CLOSE") -> dict:
    """Close an open position with opposite-side market order.

    Sprint 9.9.3.15 patch — filling mode auto-detected via _select_filling_mode.
    """
    symbol = position["symbol"]
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return {"ok": False, "error": "symbol_info_tick returned None"}

    # Sprint 9.9.3.15 patch — auto-detect filling mode (same logic as open)
    filling = _select_filling_mode(mt5, symbol)
    if filling is None:
        return {
            "ok": False,
            "error": "no supported filling mode detected for symbol "
                     f"(symbol_info.filling_mode has no FOK/IOC/RETURN bit set)",
            "retcode": None,
            "filling_mode_selected": None,
            "filling_type_used": None,
        }

    pos_type = position["type"]
    # Close BUY with SELL, close SELL with BUY
    if pos_type == "BUY":
        close_type = _ORDER_TYPE_SELL
        price = float(getattr(tick, "bid", 0.0) or 0.0)
    else:
        close_type = _ORDER_TYPE_BUY
        price = float(getattr(tick, "ask", 0.0) or 0.0)

    request = {
        "action": _TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(position["volume"]),
        "type": close_type,
        "position": int(position["ticket"]),
        "price": price,
        "deviation": deviation,
        "magic": magic,
        "comment": comment,
        "type_time": 0,
        "type_filling": filling["filling_type"],   # auto-detected (Sprint 9.9.3.15)
    }
    result = mt5.order_send(request)
    if result is None:
        return {"ok": False, "error": "order_send returned None",
                "request": _safe_request(request),
                "filling_mode_selected": filling["filling_name"],
                "filling_type_used": filling["filling_type"]}
    return {
        "ok": getattr(result, "retcode", 0) == _TRADE_RETCODE_DONE,
        "retcode": getattr(result, "retcode", None),
        "order": getattr(result, "order", None),
        "deal": getattr(result, "deal", None),
        "volume": getattr(result, "volume", None),
        "price": getattr(result, "price", None),
        "comment": getattr(result, "comment", ""),
        "request": _safe_request(request),
        "close_side": "SELL" if close_type == _ORDER_TYPE_SELL else "BUY",
        "filling_mode_selected": filling["filling_name"],
        "filling_type_used": filling["filling_type"],
        "filling_source": filling["filling_source"],
        "filling_mask": filling["filling_mask"],
    }


# ─── Execute mode (the actual implementation) ──────────────────────────────────

async def _run_execute(args, gate, cfg) -> dict:
    """Implement the actual DEMO_MICRO_EXECUTE flow."""

    # Default result skeleton
    base_result = {
        "mode": "DEMO_MICRO_EXECUTE",
        "order_send_called": False,
        "order_send_attempts": 0,
        "order_send_success": 0,
        "close_attempts": 0,
        "close_success": 0,
        "open_positions_remaining": 0,
        "net_pnl": 0,
        # Sprint 9.9.3.15 patch — track filling mode selection in the report
        "filling_mode_selected": None,
        "filling_type_used": None,
    }

    # SAFETY: Z AI must never run this. Block unless explicitly armed.
    arm_env = os.environ.get("TITAN_DEMO_MICRO_ARMED", "0")
    if arm_env != "1":
        _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
            "reason": "TITAN_DEMO_MICRO_ARMED not set to 1",
        })
        return {**base_result,
                "final_verdict": "DEMO_MICRO_BLOCKED",
                "reason": "Arm token not present"}

    if gate["verdict"] != "DEMO_MICRO_ARMED":
        _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
            "reason": f"Hard gate verdict: {gate['verdict']}",
        })
        return {**base_result,
                "final_verdict": "DEMO_MICRO_BLOCKED",
                "reason": f"Hard gate: {gate['verdict']}"}

    # Resolve side
    side = _resolve_side(args, cfg)
    if side is None:
        _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
            "reason": "No AI signal and no --side provided",
        })
        return {**base_result,
                "final_verdict": "DEMO_MICRO_BLOCKED",
                "reason": "No AI signal and no --side provided — refusing to guess"}

    # Lot enforcement
    if args.lot > cfg["max_lot"]:
        _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
            "reason": f"lot {args.lot} > max_lot {cfg['max_lot']}",
        })
        return {**base_result,
                "final_verdict": "DEMO_MICRO_BLOCKED",
                "reason": f"lot {args.lot} > max_lot {cfg['max_lot']}"}

    # MT5 must be reachable
    mt5 = _get_mt5()
    if mt5 is None:
        _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
            "reason": "MetaTrader5 not installed (Z AI / Linux)",
        })
        return {**base_result,
                "final_verdict": "DEMO_MICRO_BLOCKED",
                "reason": "MetaTrader5 not installed — only runs on Windows MT5 DEMO"}

    # Initialize MT5 and verify DEMO account
    if not mt5.initialize():
        _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
            "reason": "mt5.initialize() returned False",
        })
        return {**base_result,
                "final_verdict": "DEMO_MICRO_BLOCKED",
                "reason": "mt5.initialize() failed"}

    try:
        account_info = mt5.account_info()
        if not _is_demo_account(account_info):
            _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
                "reason": "Account is NOT DEMO",
                "trade_mode": getattr(account_info, "trade_mode", None) if account_info else None,
            })
            return {**base_result,
                    "final_verdict": "DEMO_MICRO_BLOCKED",
                    "reason": "Account is NOT DEMO — BLOCKED for safety"}

        # Sprint 9.9.3.14 patch — verify MT5 expert/algo trading is enabled.
        # account_info.trade_expert must be True, otherwise order_send returns
        # retcode=10027 ("client terminal autotrading disabled"). Even though
        # the hard gate already checks this, we re-check here as defense in
        # depth because the operator may have toggled the "Algo Trading"
        # button between the hard-gate run and the execute run.
        trade_expert = getattr(account_info, "trade_expert", None) if account_info else None
        if trade_expert is not True:
            _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
                "reason": "MT5 expert/algo trading disabled at account or terminal level",
                "account_trade_expert": trade_expert,
                "account_trade_allowed": getattr(account_info, "trade_allowed", None) if account_info else None,
                "retcode_10027_meaning": _RETCODE_10027_MEANING,
            })
            return {**base_result,
                    "final_verdict": "DEMO_MICRO_BLOCKED",
                    "reason": ("MT5 expert/algo trading disabled at account or terminal level "
                               f"(account_trade_expert={trade_expert}) — "
                               f"order_send would return retcode={_TRADE_RETCODE_AUTOTRADING_DISABLED} "
                               f"({_RETCODE_10027_MEANING})")}

        # Symbol must be visible and selected
        info = mt5.symbol_info(args.symbol)
        if info is None:
            _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
                "reason": f"symbol_info({args.symbol}) returned None",
            })
            return {**base_result,
                    "final_verdict": "DEMO_MICRO_BLOCKED",
                    "reason": f"Symbol {args.symbol} not visible in MT5"}

        if not getattr(info, "visible", True):
            if not mt5.symbol_select(args.symbol, True):
                _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
                    "reason": f"symbol_select({args.symbol}) failed",
                })
                return {**base_result,
                        "final_verdict": "DEMO_MICRO_BLOCKED",
                        "reason": f"Could not select symbol {args.symbol}"}

        # Fresh tick
        tick = mt5.symbol_info_tick(args.symbol)
        tick_time = getattr(tick, "time", 0) if tick else 0
        if tick is None or (time.time() - tick_time) > 60:
            _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
                "reason": "tick is stale or None",
            })
            return {**base_result,
                    "final_verdict": "DEMO_MICRO_BLOCKED",
                    "reason": "Tick is stale or unavailable"}

        # Spread check
        spread_usd = float(getattr(tick, "ask", 0.0) - getattr(tick, "bid", 0.0))
        if spread_usd > cfg["max_spread_usd"]:
            _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
                "reason": f"spread {spread_usd} > max_spread_usd {cfg['max_spread_usd']}",
            })
            return {**base_result,
                    "final_verdict": "DEMO_MICRO_BLOCKED",
                    "reason": f"Spread too high: {spread_usd} > {cfg['max_spread_usd']}"}

        # No existing open position
        has_pos, _ = _check_existing_position(mt5, args.symbol)
        if has_pos:
            _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
                "reason": "Existing open position for symbol",
                "symbol": args.symbol,
            })
            return {**base_result,
                    "final_verdict": "DEMO_MICRO_BLOCKED",
                    "reason": "Existing open position — refusing to send duplicate",
                    "open_positions_remaining": 1}

        # Sprint 9.9.3.15 patch — pre-check supported filling mode BEFORE
        # sending the order. Fail closed if no FOK/IOC/RETURN bit is set
        # in symbol_info.filling_mode. This prevents the retcode=10030
        # failure mode entirely (order_send is never called).
        filling = _select_filling_mode(mt5, args.symbol)
        if filling is None:
            _journal_event("DEMO_MICRO_EXECUTE_BLOCKED", {
                "reason": "no supported filling mode detected for symbol "
                          "(symbol_info.filling_mode has no FOK/IOC/RETURN bit set)",
                "symbol": args.symbol,
                "filling_mode_raw": getattr(info, "filling_mode", None),
                "retcode_10030_meaning": _RETCODE_10030_MEANING,
            })
            return {**base_result,
                    "final_verdict": "DEMO_FULL_CYCLE_FAIL",
                    "reason": ("no supported filling mode detected for symbol "
                               f"{args.symbol} — symbol_info.filling_mode="
                               f"{getattr(info, 'filling_mode', None)} "
                               f"(would return retcode={_TRADE_RETCODE_INVALID_FILL} "
                               f"({_RETCODE_10030_MEANING}) if order_send attempted)"),
                    "order_send_called": False,
                    "order_send_attempts": 0,
                    "order_send_success": 0,
                    "filling_mode_selected": None}

        # Log selected filling mode for operator visibility.
        _journal_event("DEMO_MICRO_FILLING_MODE_SELECTED", {
            "symbol": args.symbol,
            "filling_mode_selected": filling["filling_name"],
            "filling_type_used": filling["filling_type"],
            "filling_source": filling["filling_source"],
            "filling_mask": filling["filling_mask"],
        })

        # ── Send ONE order ──
        _journal_event("DEMO_MICRO_ORDER_REQUESTED", {
            "symbol": args.symbol,
            "side": side,
            "lot": args.lot,
            "magic": DEMO_MICRO_MAGIC,
            "filling_mode_selected": filling["filling_name"],
            "filling_type_used": filling["filling_type"],
        })

        open_result = _send_open_order(
            mt5, symbol=args.symbol, side=side, lot=args.lot,
            magic=DEMO_MICRO_MAGIC,
        )

        if not open_result["ok"]:
            # Sprint 9.9.3.15 patch — unified retcode diagnostic lookup.
            # Covers both retcode=10027 (autotrading disabled) and
            # retcode=10030 (invalid fill type), plus any future codes
            # added to _RETCODE_MEANINGS.
            retcode = open_result.get("retcode")
            retcode_diagnostic = _lookup_retcode_meaning(retcode)
            _journal_event("DEMO_MICRO_ORDER_FAILED", {
                "retcode": retcode,
                "retcode_meaning": retcode_diagnostic,
                "error": open_result.get("error", ""),
                "request": open_result.get("request", {}),
                "filling_mode_selected": open_result.get("filling_mode_selected"),
                "filling_type_used": open_result.get("filling_type_used"),
            })
            if retcode_diagnostic is not None:
                # Tailor the manual-review hint to the specific retcode.
                if retcode == _TRADE_RETCODE_AUTOTRADING_DISABLED:
                    hint = "enable Algo Trading in MT5 terminal"
                elif retcode == _TRADE_RETCODE_INVALID_FILL:
                    hint = ("filling mode auto-detect failed — check "
                            "symbol_info.filling_mode for this broker/symbol")
                else:
                    hint = "see retcode_meaning in journal"
                _journal_event("DEMO_MICRO_MANUAL_REVIEW_REQUIRED", {
                    "reason": (f"order_send failed: retcode={retcode} "
                               f"({retcode_diagnostic}) — {hint}"),
                })
            else:
                _journal_event("DEMO_MICRO_MANUAL_REVIEW_REQUIRED", {
                    "reason": "order_send failed",
                })
            # Did order_send actually get called? If filling mode was
            # unsupported, _send_open_order returns ok=False WITHOUT
            # calling order_send (filling_mode_selected is None).
            order_send_was_called = open_result.get("filling_mode_selected") is not None
            return {**base_result,
                    "final_verdict": "DEMO_FULL_CYCLE_FAIL",
                    "reason": f"order_send failed: {open_result.get('error', '')} "
                              f"retcode={retcode}"
                              + (f" ({retcode_diagnostic})" if retcode_diagnostic else ""),
                    "order_send_called": order_send_was_called,
                    "order_send_attempts": 1 if order_send_was_called else 0,
                    "order_send_success": 0,
                    "filling_mode_selected": open_result.get("filling_mode_selected"),
                    "filling_type_used": open_result.get("filling_type_used"),
                    "open_order": open_result}

        _journal_event("DEMO_MICRO_ORDER_SENT", {
            "order": open_result.get("order"),
            "deal": open_result.get("deal"),
            "price": open_result.get("price"),
            "volume": open_result.get("volume"),
            "retcode": open_result.get("retcode"),
            "filling_mode_selected": open_result.get("filling_mode_selected"),
            "filling_type_used": open_result.get("filling_type_used"),
        })

        # ── Sync position ──
        position = _sync_position(mt5, args.symbol, DEMO_MICRO_MAGIC, timeout_s=5.0)
        if position is None:
            _journal_event("DEMO_MICRO_POSITION_SYNC_FAILED", {
                "order": open_result.get("order"),
                "deal": open_result.get("deal"),
            })
            _journal_event("DEMO_MICRO_MANUAL_REVIEW_REQUIRED", {
                "reason": "Position did not appear within sync timeout",
            })
            return {**base_result,
                    "final_verdict": "DEMO_MANUAL_REVIEW_REQUIRED",
                    "reason": "Position sync failed — manual review required",
                    "order_send_called": True,
                    "order_send_attempts": 1,
                    "order_send_success": 1,
                    "open_order": open_result,
                    "open_positions_remaining": 1}

        _journal_event("DEMO_MICRO_POSITION_SYNCED", {
            "ticket": position["ticket"],
            "position_id": position["position_id"],
            "type": position["type"],
            "volume": position["volume"],
            "price_open": position["price_open"],
        })

        # ── Monitor & close ──
        max_hold_s = args.max_hold_seconds if args.max_hold_seconds else (
            args.max_duration_minutes * 60
        )
        # Cap max_hold_s for safety
        max_hold_s = min(int(max_hold_s), args.max_duration_minutes * 60)

        # Loss threshold: max_total_loss_pct of initial balance
        demo_micro_cfg = cfg.get("demo_micro", {}) or {}
        max_total_loss_pct = float(demo_micro_cfg.get("max_total_loss_pct", 0.5))
        initial_balance = float(getattr(account_info, "balance", 10000) or 10000)
        loss_threshold = -abs(initial_balance * max_total_loss_pct / 100.0)

        open_price = float(position["price_open"] or 0.0)
        max_floating_dd = 0.0
        close_reason = "max_hold_seconds"
        emergency_stop = False

        monitor_start = time.time()
        last_log = 0.0
        while time.time() - monitor_start < max_hold_s:
            # Check position still open
            try:
                positions = mt5.positions_get(symbol=args.symbol) or []
                matching = [p for p in positions
                            if getattr(p, "magic", 0) == DEMO_MICRO_MAGIC
                            and getattr(p, "ticket", 0) == position["ticket"]]
                if not matching:
                    close_reason = "position_closed_externally"
                    break
                cur = matching[0]
                floating = float(getattr(cur, "profit", 0.0) or 0.0)
                if floating < max_floating_dd:
                    max_floating_dd = floating
                if floating <= loss_threshold:
                    close_reason = "loss_threshold"
                    break
            except Exception:
                pass
            # Emergency stop env (operator can set during run)
            if os.environ.get("TITAN_DEMO_MICRO_EMERGENCY_STOP", "0") == "1":
                emergency_stop = True
                close_reason = "emergency_stop"
                break
            # Kill switch escalates (best-effort)
            try:
                from titan.production.kill_switch_fsm import KillSwitchFSM
                ks = KillSwitchFSM()
                if ks.state.value in ("HALT_NEW_TRADES", "FLATTEN_ONLY", "EMERGENCY_STOP"):
                    close_reason = "kill_switch_escalated"
                    break
            except Exception:
                pass
            # Periodic journal heartbeat every 30s
            now = time.time()
            if now - last_log > 30:
                _journal_event("DEMO_MICRO_MONITOR_HEARTBEAT", {
                    "ticket": position["ticket"],
                    "elapsed_s": int(now - monitor_start),
                    "remaining_s": int(max_hold_s - (now - monitor_start)),
                    "floating_pnl": floating if 'floating' in locals() else 0,
                    "max_floating_dd": max_floating_dd,
                })
                last_log = now
            await asyncio.sleep(1.0)

        # ── Close position ──
        _journal_event("DEMO_MICRO_POSITION_CLOSE_REQUESTED", {
            "ticket": position["ticket"],
            "reason": close_reason,
            "emergency_stop": emergency_stop,
        })

        close_result = _close_position(mt5, position, magic=DEMO_MICRO_MAGIC)
        close_attempts = 1
        close_success = 1 if close_result["ok"] else 0

        if not close_result["ok"]:
            _journal_event("DEMO_MICRO_CLOSE_FAILED", {
                "ticket": position["ticket"],
                "error": close_result.get("error", ""),
                "retcode": close_result.get("retcode"),
            })
            # Verify if position still open
            try:
                positions = mt5.positions_get(symbol=args.symbol) or []
                matching = [p for p in positions
                            if getattr(p, "magic", 0) == DEMO_MICRO_MAGIC
                            and getattr(p, "ticket", 0) == position["ticket"]]
                open_positions_remaining = 1 if matching else 0
            except Exception:
                open_positions_remaining = 1
            _journal_event("DEMO_MICRO_MANUAL_REVIEW_REQUIRED", {
                "reason": "Close order_send failed",
                "ticket": position["ticket"],
            })
            return {**base_result,
                    "final_verdict": "DEMO_MANUAL_REVIEW_REQUIRED",
                    "reason": f"Close failed: {close_result.get('error', '')}",
                    "order_send_called": True,
                    "order_send_attempts": 1,
                    "order_send_success": 1,
                    "open_order": open_result,
                    "position": position,
                    "close_attempts": close_attempts,
                    "close_success": close_success,
                    "open_positions_remaining": open_positions_remaining,
                    "max_floating_dd": max_floating_dd,
                    "close_reason": close_reason,
                    "emergency_stop": emergency_stop}

        # Wait briefly for close to settle
        await asyncio.sleep(1.0)

        # Verify no open positions remain
        try:
            positions = mt5.positions_get(symbol=args.symbol) or []
            matching = [p for p in positions
                        if getattr(p, "magic", 0) == DEMO_MICRO_MAGIC]
            open_positions_remaining = len(matching)
        except Exception:
            open_positions_remaining = 0

        # ── Net PnL ──
        close_price = float(close_result.get("price") or 0.0)
        holding_seconds = int(time.time() - monitor_start)

        from titan.production.net_profit_engine import NetProfitEngine
        engine = NetProfitEngine()
        spread_usd_obs = float(getattr(tick, "ask", 0.0) - getattr(tick, "bid", 0.0))
        # Use same SL convention as open order
        sl_for_pnl = (open_price - 5.0) if position["type"] == "BUY" else (open_price + 5.0)
        pnl_result = engine.calculate(
            direction=position["type"],
            entry_price=open_price,
            close_price=close_price,
            lot=float(position["volume"]),
            sl=sl_for_pnl,
            spread_usd=spread_usd_obs,
            slippage_pips=2.0,
            swap_cost=0.0,
        )

        _journal_event("DEMO_MICRO_POSITION_CLOSED", {
            "ticket": position["ticket"],
            "close_price": close_price,
            "holding_seconds": holding_seconds,
            "gross_pnl": pnl_result.gross_pnl,
            "net_pnl": pnl_result.net_pnl,
            "max_floating_dd": max_floating_dd,
            "close_reason": close_reason,
        })

        if open_positions_remaining == 0:
            verdict = "DEMO_FULL_CYCLE_PASS"
            _journal_event("DEMO_MICRO_FULL_CYCLE_PASS", {
                "ticket": position["ticket"],
                "net_pnl": pnl_result.net_pnl,
            })
        else:
            verdict = "DEMO_MANUAL_REVIEW_REQUIRED"
            _journal_event("DEMO_MICRO_MANUAL_REVIEW_REQUIRED", {
                "reason": "Position still open after close",
                "open_positions_remaining": open_positions_remaining,
            })

        return {**base_result,
                "final_verdict": verdict,
                "order_send_called": True,
                "order_send_attempts": 1,
                "order_send_success": 1,
                "open_order": open_result,
                "position": position,
                "close_result": close_result,
                "close_attempts": close_attempts,
                "close_success": close_success,
                "open_positions_remaining": open_positions_remaining,
                "gross_pnl": pnl_result.gross_pnl,
                "spread_cost": pnl_result.costs.spread_cost,
                "commission_cost": pnl_result.costs.commission_cost,
                "slippage_cost": pnl_result.costs.slippage_cost,
                "swap_cost": pnl_result.costs.swap_cost,
                "net_pnl": pnl_result.net_pnl,
                "holding_seconds": holding_seconds,
                "open_price": open_price,
                "close_price": close_price,
                "max_floating_dd": max_floating_dd,
                "close_reason": close_reason,
                "emergency_stop": emergency_stop,
                # Sprint 9.9.3.15 patch — surface filling mode in success report
                "filling_mode_selected": open_result.get("filling_mode_selected"),
                "filling_type_used": open_result.get("filling_type_used"),
                "filling_source": open_result.get("filling_source"),
                "filling_mask": open_result.get("filling_mask")}

    finally:
        try:
            mt5.shutdown()
        except Exception:
            pass


# ─── Main runner ───────────────────────────────────────────────────────────────

async def run(args):
    print("=" * 78)
    print("  TITAN XAU AI — Sprint 9.9.3 FundedNext Demo Micro Full-Cycle Harness")
    print("=" * 78)
    print(f"  Mode: {args.mode}")
    print(f"  Max trades: {args.max_trades}")
    print(f"  Max duration: {args.max_duration_minutes} min")
    print(f"  Symbol: {args.symbol}")
    print(f"  Lot: {args.lot}")
    if args.side:
        print(f"  Side: {args.side}")
    if args.max_hold_seconds:
        print(f"  Max hold: {args.max_hold_seconds}s")
    print(f"  Force close on end: {args.force_close_on_end}")

    # Load shared config
    cfg = load_demo_micro_config()

    # ── Hard gate ──
    print("\n── Running hard gate ──")
    gate = hard_gate_evaluate()
    for k, v in gate["checks"].items():
        print(f"  [{'✓' if v else '✗'}] {k}: {v}")
    print(f"\n  Gate verdict: {gate['verdict']}")

    # ── Mode: DRY_ARM_CHECK_ONLY ──
    if args.mode == "DRY_ARM_CHECK_ONLY":
        result = {
            "mode": "DRY_ARM_CHECK_ONLY",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "hard_gate_verdict": gate["verdict"],
            "hard_gate_checks": gate["checks"],
            "hard_gate_reasons": gate["reasons"],
            "order_send_called": False,
            "order_send_success": 0,
            "trades_opened": 0,
            "trades_closed": 0,
            "net_pnl": 0,
            "final_verdict": gate["verdict"],
            "message": "DRY_ARM_CHECK_ONLY — no orders sent. "
                       "Execute would be " + ("ARMED" if gate["verdict"] == "DEMO_MICRO_ARMED"
                                              else "BLOCKED") + ".",
        }
        _save_report(result, "DRY_ARM_CHECK_ONLY")
        print(f"\n  >>> DRY_ARM_CHECK_ONLY result: {result['final_verdict']}")
        print(f"  >>> {result['message']}")
        return

    # ── Mode: DEMO_MICRO_EXECUTE ──
    if args.mode == "DEMO_MICRO_EXECUTE":
        result = await _run_execute(args, gate, cfg)
        result["timestamp_utc"] = datetime.now(timezone.utc).isoformat()
        result["hard_gate_verdict"] = gate["verdict"]
        suffix = ("DEMO_MICRO_EXECUTE_BLOCKED" if result["final_verdict"] == "DEMO_MICRO_BLOCKED"
                  else "DEMO_MICRO_EXECUTE")
        _save_report(result, suffix)
        print(f"\n  >>> DEMO_MICRO_EXECUTE result: {result['final_verdict']}")
        if result.get("reason"):
            print(f"  >>> Reason: {result['reason']}")
        # Sprint 9.9.3.15 patch — surface filling mode in console output
        if result.get("filling_mode_selected") is not None:
            print(f"  >>> Filling mode selected: {result['filling_mode_selected']} "
                  f"(type={result.get('filling_type_used')}, "
                  f"source={result.get('filling_source', 'unknown')})")
        elif result.get("order_send_called") is False:
            print(f"  >>> Filling mode selected: None (no supported mode — order_send not called)")
        if result.get("net_pnl") is not None and result.get("order_send_called"):
            print(f"  >>> Net PnL: {result.get('net_pnl')}")
        if result.get("open_positions_remaining") is not None:
            print(f"  >>> Open positions remaining: {result.get('open_positions_remaining')}")
        return


def _save_report(result, suffix):
    json_path = OUTPUT_DIR / "demo_micro_report.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)
    md_path = OUTPUT_DIR / "demo_micro_report.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# Sprint 9.9.3 — Demo Micro Full-Cycle ({suffix})\n\n")
        f.write(f"**Verdict: {result.get('final_verdict', 'UNKNOWN')}**\n\n")
        f.write(f"**Mode: {result.get('mode', 'UNKNOWN')}**\n\n")
        f.write(f"**Order send called: {result.get('order_send_called', False)}**\n\n")
        f.write(f"**Order send attempts: {result.get('order_send_attempts', 0)}**\n\n")
        f.write(f"**Order send success: {result.get('order_send_success', 0)}**\n\n")
        f.write(f"**Close attempts: {result.get('close_attempts', 0)}**\n\n")
        f.write(f"**Close success: {result.get('close_success', 0)}**\n\n")
        f.write(f"**Open positions remaining: {result.get('open_positions_remaining', 0)}**\n\n")
        # Sprint 9.9.3.15 patch — filling mode diagnostics in MD report
        f.write(f"**Filling mode selected: {result.get('filling_mode_selected', 'N/A')}**\n\n")
        if result.get("filling_type_used") is not None:
            f.write(f"**Filling type used: {result.get('filling_type_used')}**\n\n")
        if result.get("filling_source") is not None:
            f.write(f"**Filling source: {result.get('filling_source')}**\n\n")
        if result.get("filling_mask") is not None:
            f.write(f"**Filling mask: {result.get('filling_mask')}**\n\n")
        if "net_pnl" in result:
            f.write(f"**Net PnL: {result.get('net_pnl', 0)}**\n\n")
        if "gross_pnl" in result:
            f.write(f"**Gross PnL: {result.get('gross_pnl', 0)}**\n\n")
        if "holding_seconds" in result:
            f.write(f"**Holding seconds: {result.get('holding_seconds', 0)}**\n\n")
        if "open_price" in result:
            f.write(f"**Open price: {result.get('open_price', 0)}**\n\n")
        if "close_price" in result:
            f.write(f"**Close price: {result.get('close_price', 0)}**\n\n")
        if "max_floating_dd" in result:
            f.write(f"**Max floating DD: {result.get('max_floating_dd', 0)}**\n\n")
        if "close_reason" in result:
            f.write(f"**Close reason: {result.get('close_reason', '')}**\n\n")
        if "message" in result:
            f.write(f"**Message: {result['message']}**\n")
        if "reason" in result:
            f.write(f"**Reason: {result['reason']}**\n")
        if result.get("position"):
            f.write("\n## Position\n\n")
            f.write("| Field | Value |\n|---|---|\n")
            for k, v in result["position"].items():
                if k == "raw":
                    continue
                f.write(f"| {k} | {v} |\n")
        if result.get("open_order"):
            f.write("\n## Open Order\n\n")
            f.write("| Field | Value |\n|---|---|\n")
            for k, v in result["open_order"].items():
                if k == "request":
                    continue
                f.write(f"| {k} | {v} |\n")
    print(f"\n  JSON: {json_path}")
    print(f"  MD:   {md_path}")


def main():
    args = parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
