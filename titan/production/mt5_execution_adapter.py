"""
TITAN XAU AI — MT5ExecutionAdapter (Sprint 9.9.3.17)
=====================================================

Universal, production-grade MT5 broker execution adapter for DEMO micro
execution. Stops the per-retcode patch cycle by centralizing ALL
broker-interaction logic in one reusable class.

Responsibilities:
  1. Pre-send broker state snapshot (account_info, terminal_info,
     symbol_info, symbol tick, spread, volume_min/step/max, trade_mode,
     trade_execution, filling_mode).
  2. Build a valid market order request dynamically from the snapshot.
  3. Run mt5.order_check() before mt5.order_send().
  4. Send-level filling fallback (FOK → IOC → RETURN, RETURN only if
     the symbol's trade_execution mode permits requotes).
  5. Refresh tick before every order_send attempt (BUY price = latest
     ask, SELL price = latest bid). Log bid/ask/spread per attempt.
  6. Never send duplicate orders — after every failed send, immediately
     query positions_get(symbol) filtered by magic to detect whether
     a position actually opened despite the failure retcode.
  7. If a position appears after a failed send, return an
     emergency_close_required signal so the caller can close it.
  8. Apply the same logic to close_position (close uses opposite side
     + position ticket in the request).
  9. Log every attempt with retcode, comment, price, bid, ask, spread,
     filling mode, broker response.
 10. Build a broker_execution_profile.json snapshot for operator review.
 11. Fail closed if the adapter cannot prove a safe valid request.

This module is broker-agnostic. It does NOT contain any strategy logic,
risk logic, or lot-sizing logic. It only knows how to safely send ONE
market order to MT5 with full fallback + diagnostics.

Safety invariants (NEVER violated):
  - Never sends more than ONE order per call (no duplicate sends).
  - Never sends with a filling mode that the symbol does not support.
  - Never sends with a filling mode that failed order_check (unless
    no filling modes passed check, in which case fail closed).
  - Always checks positions_get after a failed send.
  - Always returns emergency_close_required=True if a position is
    detected after a failed send.
  - Never raises — always returns a result dict.
"""
from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

# Sprint 9.9.3.21 patch — path to the raw MT5 working profile saved by
# scripts/audit/raw_mt5_probe.py. When this file exists, the adapter can
# load it and mirror the exact request shape that succeeded on this broker.
RAW_WORKING_PROFILE_PATH = (
    REPO_ROOT / "data" / "audit" / "demo_micro" / "raw_mt5_working_profile.json"
)

# MT5 constants (defined locally to avoid importing MT5 at module load on Linux)
_TRADE_ACTION_DEAL = 1
_ORDER_TYPE_BUY = 0
_ORDER_TYPE_SELL = 1
_TRADE_RETCODE_DONE = 10009

# MQL5 ORDER_TYPE_FILLING enum values (for MqlTradeRequest.type_filling).
# These are the DEFAULT values used when the mt5 Python module is not
# available (e.g. on Linux). At runtime, the adapter reads the actual
# constants from mt5.ORDER_FILLING_* to ensure correctness across MT5
# builds. NEVER use SYMBOL_FILLING bitmask flag values here — they are
# a different enum space even though FOK/IOC happen to share values.
#
# Reference (MQL5 ORDER_TYPE_FILLING enum):
#   ORDER_FILLING_FOK    = 1  (Fill or Kill)
#   ORDER_FILLING_IOC    = 2  (Immediate or Cancel)
#   ORDER_FILLING_BOC    = 3  (Book or Cancel — MT5 build 3500+)
#   ORDER_FILLING_RETURN = 4  (Return — requotes allowed)
ORDER_FILLING_FOK_DEFAULT = 1
ORDER_FILLING_IOC_DEFAULT = 2
ORDER_FILLING_BOC_DEFAULT = 3
ORDER_FILLING_RETURN_DEFAULT = 4

# Sprint 9.9.3.20 backward-compat aliases — the old names (ORDER_FILLING_FOK
# etc.) are kept for tests and callers that import them directly. They equal
# the DEFAULT values, which match the standard MQL5 enum. At runtime, the
# adapter reads the actual values from the mt5 module via
# _get_order_filling_constants() — these aliases are only for static imports.
ORDER_FILLING_FOK = ORDER_FILLING_FOK_DEFAULT
ORDER_FILLING_IOC = ORDER_FILLING_IOC_DEFAULT
ORDER_FILLING_BOC = ORDER_FILLING_BOC_DEFAULT
ORDER_FILLING_RETURN = ORDER_FILLING_RETURN_DEFAULT

# Sprint 9.9.3.20 patch — SYMBOL_FILLING bitmask flags.
# These are bit positions in symbol_info.filling_mode used to DETECT
# which filling modes the symbol supports. They are NOT the same as
# ORDER_FILLING enum values and must NEVER be used directly as
# request["type_filling"].
#
# Reference (MQL5 SYMBOL_FILLING_* constants):
#   SYMBOL_FILLING_FOK = 1  (bit 0 — FOK supported)
#   SYMBOL_FILLING_IOC = 2  (bit 1 — IOC supported)
#   SYMBOL_FILLING_BOC = 4  (bit 2 — BOC supported, build 3500+)
#
# NOTE: There is NO SYMBOL_FILLING_RETURN flag. RETURN mode is NOT
# detected from the bitmask — it is allowed when trade_exemode is
# INSTANT (0) or REQUEST (1). The old _SYMBOL_FILLING_RETURN_BIT=8
# was wrong and has been removed.
_SYMBOL_FILLING_FOK_FLAG = 1   # bit 0
_SYMBOL_FILLING_IOC_FLAG = 2   # bit 1
_SYMBOL_FILLING_BOC_FLAG = 4   # bit 2

# Sprint 9.9.3.20 patch — filling mode descriptor list.
# Each entry maps a human-readable filling name to:
#   - symbol_flag: the SYMBOL_FILLING bitmask bit used to detect support
#     (None for RETURN, which is not flag-based)
#   - order_enum_key: the key used to look up the ORDER_FILLING enum
#     value from the mt5 module at runtime
#
# Preference order for market orders: FOK → IOC → RETURN.
# BOC is excluded — only valid for pending orders in market depth,
# not for TRADE_ACTION_DEAL (market) orders.
_FILLING_MODES = [
    {
        "name": "FOK",
        "symbol_flag": _SYMBOL_FILLING_FOK_FLAG,    # 1
        "order_enum_key": "ORDER_FILLING_FOK",
        "order_enum_default": ORDER_FILLING_FOK_DEFAULT,
    },
    {
        "name": "IOC",
        "symbol_flag": _SYMBOL_FILLING_IOC_FLAG,    # 2
        "order_enum_key": "ORDER_FILLING_IOC",
        "order_enum_default": ORDER_FILLING_IOC_DEFAULT,
    },
    {
        "name": "RETURN",
        "symbol_flag": None,   # NOT flag-based — determined by trade_exemode
        "order_enum_key": "ORDER_FILLING_RETURN",
        "order_enum_default": ORDER_FILLING_RETURN_DEFAULT,
    },
]

# Default bitmask when symbol_info.filling_mode is missing or 0
# (older MT5 builds / permissive fallback). Only FOK + IOC flags —
# RETURN is not a flag, it's determined by trade_exemode.
_DEFAULT_FILLING_MASK = (
    _SYMBOL_FILLING_FOK_FLAG
    | _SYMBOL_FILLING_IOC_FLAG
)

# SYMBOL_TRADE_EXECUTION enum (MQL5)
# 0 = INSTANT  — requotes allowed, RETURN may be valid
# 1 = REQUEST  — requotes allowed, RETURN may be valid
# 2 = MARKET   — no requotes, only FOK/IOC valid (RETURN is NOT valid)
# 3 = EXCHANGE — exchange execution
# When trade_execution is MARKET (2), we must NOT send RETURN even if
# the filling_mode bitmask claims it is supported (the bitmask lies on
# some brokers, but trade_execution is authoritative).
_TRADE_EXECUTION_INSTANT = 0
_TRADE_EXECUTION_REQUEST = 1
_TRADE_EXECUTION_MARKET = 2
_TRADE_EXECUTION_EXCHANGE = 3
_TRADE_EXECUTIONS_THAT_ALLOW_RETURN = frozenset({
    _TRADE_EXECUTION_INSTANT,
    _TRADE_EXECUTION_REQUEST,
})

# Canonical retcode → meaning mapping (universal — covers all common codes).
_RETCODE_MEANINGS = {
    0: "order_check passed (request is valid)",
    10004: "requote (TRADE_RETCODE_REQUOTE)",
    10006: "request rejected (TRADE_RETCODE_REJECT)",
    10009: "request completed (TRADE_RETCODE_DONE)",
    10010: "request completed partially (TRADE_RETCODE_DONE_PARTIAL)",
    10013: "invalid request (TRADE_RETCODE_INVALID_REQUEST)",
    10014: "invalid volume (TRADE_RETCODE_INVALID_VOLUME)",
    10015: "invalid price (TRADE_RETCODE_INVALID_PRICE)",
    10016: "invalid stops (TRADE_RETCODE_INVALID_STOPS)",
    10018: "market closed (TRADE_RETCODE_MARKET_CLOSED)",
    10019: "not enough money (TRADE_RETCODE_NO_MONEY)",
    10020: "price changed (TRADE_RETCODE_PRICE_CHANGED)",
    10021: "no quotes / price off (TRADE_RETCODE_PRICE_OFF)",
    10027: "client terminal autotrading disabled",
    10030: "invalid order filling type (TRADE_RETCODE_INVALID_FILL)",
}

# Success retcodes — order was placed (fully or partially).
_SUCCESS_RETCODES = frozenset({10009, 10010})

# Retryable retcodes — broker rejected, but we can try the next filling
# mode (filling-related) or refresh tick + retry (price-related).
_RETRYABLE_RETCODES = frozenset({
    10004,   # REQUOTE — price moved
    10006,   # REJECT — broker rejected filling mode
    10020,   # PRICE_CHANGED
    10021,   # PRICE_OFF
    10030,   # INVALID_FILL — filling mode not supported
})

# Sprint 9.9.3.19 patch — TRADE_ACTION_SLTP for modifying position SL/TP.
# Sprint 9.9.3.25.1 hotfix — this is now a FALLBACK DEFAULT only.
# At runtime, the adapter reads mt5.TRADE_ACTION_SLTP via
# _get_trade_action_constants() to ensure the correct value is used
# for the installed MT5 Python build. The hardcoded 2 was causing
# retcode=10013 (Invalid request) on MetaQuotes-Demo.
_TRADE_ACTION_SLTP_DEFAULT = 2

# Sprint 9.9.3.25.1 — keep backward-compat alias
_TRADE_ACTION_SLTP = _TRADE_ACTION_SLTP_DEFAULT

# Sprint 9.9.3.19 patch — retcodes that indicate the broker rejected the
# PROTECTED order (SL/TP attached) but might accept a naked order.
# These trigger the two-step fallback: naked open → SLTP modify.
_PROTECTED_ORDER_REJECT_RETCODES = frozenset({
    10006,   # REJECT
    10016,   # INVALID_STOPS
})


def lookup_retcode_meaning(retcode) -> Optional[str]:
    """Return the canonical English meaning for a known MT5 retcode, else None."""
    if retcode is None:
        return None
    try:
        return _RETCODE_MEANINGS.get(int(retcode))
    except (TypeError, ValueError):
        return None


def _safe(obj, attr, default=None):
    """getattr that swallows exceptions and returns default."""
    try:
        return getattr(obj, attr, default)
    except Exception:
        return default


def _mask_login(login) -> str:
    """Sprint 9.9.3.23 — mask login for privacy: show first 2 and last 2 chars."""
    if login is None:
        return "N/A"
    s = str(login)
    if len(s) <= 4:
        return s[:1] + "***" + s[-1:]
    return s[:2] + "***" + s[-2:]


def _to_jsonable(v):
    """Convert any value to something json.dumps can serialize."""
    try:
        json.dumps(v)
        return v
    except (TypeError, ValueError):
        return str(v)


class MT5ExecutionAdapter:
    """Universal MT5 broker execution adapter.

    One instance per execution attempt. Construct with an mt5 module
    (real or mock) and a journal_event callable (so the adapter can
    write to whatever journal the caller uses).

    Usage:
        adapter = MT5ExecutionAdapter(mt5, journal_event=_journal_event)
        result = adapter.send_open_order(
            symbol="XAUUSD", side="BUY", lot=0.01, magic=20261993,
        )
        if result["emergency_close_required"]:
            # caller must immediately close the detected position
            ...
    """

    def __init__(self, mt5, journal_event=None, profile_path: Optional[str] = None):
        """Initialize adapter.

        Args:
            mt5: MetaTrader5 module (or mock). Must expose:
                - account_info(), terminal_info(), symbol_info(symbol),
                  symbol_info_tick(symbol), symbol_select(symbol, visible),
                  positions_get(symbol=, ticket=), order_check(request),
                  order_send(request), initialize(), shutdown()
            journal_event: callable(event_type: str, payload: dict) -> None.
                If None, journaling is skipped (silent mode for unit tests).
            profile_path: optional path to write broker_execution_profile.json.
                If None, uses default data/audit/demo_micro/broker_execution_profile.json.
        """
        self.mt5 = mt5
        self._journal = journal_event or (lambda event_type, payload: None)
        if profile_path is None:
            profile_path = str(
                REPO_ROOT / "data" / "audit" / "demo_micro" / "broker_execution_profile.json"
            )
        self._profile_path = profile_path
        # Cached snapshot (built once per adapter instance — assumes the
        # caller creates a fresh adapter per execution attempt).
        self._snapshot: Optional[dict] = None
        # Sprint 9.9.3.20 patch — cache ORDER_FILLING enum constants read
        # from the mt5 module at runtime. This ensures we use the broker's
        # actual enum values, not hard-coded defaults.
        self._order_filling_constants: Optional[dict] = None
        # Sprint 9.9.3.25.1 — cache for TRADE_ACTION_* constants
        self._trade_action_constants: Optional[dict] = None

    # ─── Sprint 9.9.3.20: ORDER_FILLING enum resolution ──────────────────────

    def _get_order_filling_constants(self) -> dict:
        """Sprint 9.9.3.20 — read ORDER_FILLING_* constants from the mt5
        module at runtime.

        The mt5 Python module exposes ORDER_FILLING_FOK, ORDER_FILLING_IOC,
        ORDER_FILLING_RETURN (and optionally ORDER_FILLING_BOC) as module-
        level integers. We read them at runtime to ensure we use the correct
        enum values for request["type_filling"], regardless of MT5 build.

        Falls back to standard MQL5 default values if the mt5 module doesn't
        expose a particular constant (e.g. on Linux without MT5 installed,
        or older MT5 builds that lack ORDER_FILLING_BOC).

        Returns a dict:
            {"FOK": int, "IOC": int, "BOC": int|None, "RETURN": int}
        """
        if self._order_filling_constants is not None:
            return self._order_filling_constants
        result = {}
        for mode in _FILLING_MODES:
            key = mode["order_enum_key"]   # e.g. "ORDER_FILLING_FOK"
            name = mode["name"]            # e.g. "FOK"
            default = mode["order_enum_default"]
            # Try to read from the mt5 module at runtime
            val = None
            try:
                val = getattr(self.mt5, key, None)
            except Exception:
                val = None
            if val is None:
                val = default
            result[name] = val
        # BOC is special — may not exist in older MT5 builds
        try:
            boc_val = getattr(self.mt5, "ORDER_FILLING_BOC", None)
        except Exception:
            boc_val = None
        result["BOC"] = boc_val if boc_val is not None else ORDER_FILLING_BOC_DEFAULT
        self._order_filling_constants = result
        return result

    # ─── Sprint 9.9.3.25.1: TRADE_ACTION constant resolution ─────────────────

    def _get_trade_action_constants(self) -> dict:
        """Sprint 9.9.3.25.1 — read TRADE_ACTION_* constants from the mt5
        module at runtime.

        The mt5 Python module exposes TRADE_ACTION_DEAL and TRADE_ACTION_SLTP
        as module-level integers. We read them at runtime to ensure we use
        the correct enum values for request["action"], regardless of MT5 build.

        Falls back to documented MQL5 defaults if the mt5 module doesn't
        expose a particular constant.

        Returns a dict:
            {"TRADE_ACTION_DEAL": int, "TRADE_ACTION_SLTP": int}
        """
        if self._trade_action_constants is not None:
            return self._trade_action_constants
        result = {}
        # TRADE_ACTION_DEAL
        try:
            val = getattr(self.mt5, "TRADE_ACTION_DEAL", None)
        except Exception:
            val = None
        result["TRADE_ACTION_DEAL"] = val if val is not None else _TRADE_ACTION_DEAL
        # TRADE_ACTION_SLTP
        try:
            val = getattr(self.mt5, "TRADE_ACTION_SLTP", None)
        except Exception:
            val = None
        result["TRADE_ACTION_SLTP"] = val if val is not None else _TRADE_ACTION_SLTP_DEFAULT
        self._trade_action_constants = result
        return result

    def _get_trade_action_sltp(self) -> int:
        """Convenience: return the runtime TRADE_ACTION_SLTP value."""
        return self._get_trade_action_constants()["TRADE_ACTION_SLTP"]

    def _get_trade_action_deal(self) -> int:
        """Convenience: return the runtime TRADE_ACTION_DEAL value."""
        return self._get_trade_action_constants()["TRADE_ACTION_DEAL"]

    # ─── Journal helper ──────────────────────────────────────────────────────

    def _log(self, event_type: str, payload: dict) -> None:
        """Emit a journal event with timestamp."""
        enriched = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), **payload}
        self._journal(event_type, enriched)

    # ─── Broker state snapshot ───────────────────────────────────────────────

    def snapshot_broker_state(self, symbol: str, magic: int) -> dict:
        """Capture full pre-send broker state for diagnostics + profile.

        Reads: account_info, terminal_info, symbol_info, symbol tick,
        spread, volume_min/step/max, trade_mode, trade_execution,
        filling_mode, open positions for this symbol+magic.

        Returns a dict. Never raises — all fields default to None on error.
        """
        snap = {
            "symbol": symbol,
            "magic": magic,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        }
        # Account info
        try:
            acc = self.mt5.account_info()
        except Exception:
            acc = None
        snap["account"] = {
            "login": _safe(acc, "login"),
            "name": _safe(acc, "name"),
            "server": _safe(acc, "server"),
            "currency": _safe(acc, "currency"),
            "leverage": _safe(acc, "leverage"),
            "balance": _safe(acc, "balance"),
            "equity": _safe(acc, "equity"),
            "trade_mode": _safe(acc, "trade_mode"),
            "trade_allowed": _safe(acc, "trade_allowed"),
            "trade_expert": _safe(acc, "trade_expert"),
        } if acc else {}
        # Terminal info
        try:
            term = self.mt5.terminal_info()
        except Exception:
            term = None
        snap["terminal"] = {
            "name": _safe(term, "name"),
            "company": _safe(term, "company"),
            "trade_allowed": _safe(term, "trade_allowed"),
            "tradeapi_disabled": _safe(term, "tradeapi_disabled"),
            "community_account": _safe(term, "community_account"),
            "connected": _safe(term, "connected"),
        } if term else {}
        # Symbol info
        try:
            info = self.mt5.symbol_info(symbol)
        except Exception:
            info = None
        snap["symbol_info"] = {
            "name": _safe(info, "name"),
            "visible": _safe(info, "visible"),
            "digits": _safe(info, "digits"),
            "point": _safe(info, "point"),
            "spread": _safe(info, "spread"),
            "trade_mode": _safe(info, "trade_mode"),
            "trade_exemode": _safe(info, "trade_exemode"),
            "filling_mode": _safe(info, "filling_mode"),
            "volume_min": _safe(info, "volume_min"),
            "volume_max": _safe(info, "volume_max"),
            "volume_step": _safe(info, "volume_step"),
            "trade_contract_size": _safe(info, "trade_contract_size"),
        } if info else {}
        # Sprint 9.9.3.20 — log ORDER_FILLING enum constants resolved from
        # the mt5 module at runtime, so operators can verify the adapter
        # is using the correct enum values (not bitmask flags).
        snap["order_filling_constants"] = self._get_order_filling_constants()
        # Sprint 9.9.3.25.1 — log TRADE_ACTION constants for profile
        snap["trade_action_constants"] = self._get_trade_action_constants()
        # Tick
        try:
            tick = self.mt5.symbol_info_tick(symbol)
        except Exception:
            tick = None
        snap["tick"] = {
            "bid": _safe(tick, "bid"),
            "ask": _safe(tick, "ask"),
            "time": _safe(tick, "time"),
            "spread": (float(_safe(tick, "ask", 0) or 0)
                       - float(_safe(tick, "bid", 0) or 0)) if tick else None,
        } if tick else {}
        # Open positions for this symbol + magic
        try:
            positions = self.mt5.positions_get(symbol=symbol) or []
        except Exception:
            positions = []
        matching = [p for p in positions if _safe(p, "magic") == magic]
        snap["open_positions"] = {
            "count": len(matching),
            "tickets": [_safe(p, "ticket") for p in matching],
        }
        self._snapshot = snap
        return snap

    # ─── Filling mode selection ──────────────────────────────────────────────

    def _list_supported_filling_modes(self, symbol: str) -> list:
        """Sprint 9.9.3.20 — return ordered list of supported filling modes.

        Clearly separates SYMBOL_FILLING bitmask flags (used to detect
        support) from ORDER_FILLING enum values (used in request["type_filling"]).

        For each mode, returns:
          - filling_name: human-readable name ("FOK", "IOC", "RETURN")
          - symbol_filling_flag: the SYMBOL_FILLING bitmask bit (1, 2, or None for RETURN)
          - order_filling_type: the ORDER_FILLING enum value from mt5 module
            (read at runtime via _get_order_filling_constants)
          - filling_mask: the raw bitmask from symbol_info (or default)
          - filling_source: "symbol_info" or "default"

        Filters:
          - FOK: included if bitmask has SYMBOL_FILLING_FOK flag (bit 0)
          - IOC: included if bitmask has SYMBOL_FILLING_IOC flag (bit 1)
          - RETURN: included if trade_exemode allows it (INSTANT/REQUEST),
            NOT based on bitmask (there is no SYMBOL_FILLING_RETURN flag)

        Returns empty list if no mode is supported.
        """
        try:
            info = self.mt5.symbol_info(symbol)
        except Exception:
            info = None
        if info is None:
            return []

        mask = _safe(info, "filling_mode", None)
        filling_source = "symbol_info"
        if mask is None or mask == 0:
            mask = _DEFAULT_FILLING_MASK
            filling_source = "default"

        trade_exec = _safe(info, "trade_exemode", None)
        # Sprint 9.9.3.20 — read ORDER_FILLING enum values from mt5 module
        order_consts = self._get_order_filling_constants()

        modes = []
        for mode_desc in _FILLING_MODES:
            name = mode_desc["name"]
            symbol_flag = mode_desc["symbol_flag"]
            order_enum = order_consts.get(name, mode_desc["order_enum_default"])

            # Determine if this mode is supported
            if symbol_flag is not None:
                # FOK / IOC — check bitmask flag
                if not (mask & symbol_flag):
                    continue
            else:
                # RETURN — not flag-based. Include only if trade_exemode
                # allows requotes (INSTANT or REQUEST execution).
                if trade_exec is not None and trade_exec not in _TRADE_EXECUTIONS_THAT_ALLOW_RETURN:
                    continue
                # If trade_exec is None (unknown), we include RETURN as a
                # last-resort fallback — order_check will catch it if invalid.

            modes.append({
                "filling_name": name,
                # Sprint 9.9.3.20 — clearly separate flag from enum
                "symbol_filling_flag": symbol_flag,
                "order_filling_type": order_enum,
                "filling_mask": mask,
                "filling_source": filling_source,
            })
        return modes

    # ─── Request builder ────────────────────────────────────────────────────

    def _build_open_request(self, symbol: str, side: str, lot: float,
                             magic: int, deviation: int,
                             comment: str, tick) -> dict:
        """Build a market open-order request (WITHOUT type_filling)."""
        if side == "BUY":
            price = float(_safe(tick, "ask", 0.0) or 0.0)
            order_type = _ORDER_TYPE_BUY
            sl = price - 5.0
            tp = price + 10.0
        else:
            price = float(_safe(tick, "bid", 0.0) or 0.0)
            order_type = _ORDER_TYPE_SELL
            sl = price + 5.0
            tp = price - 10.0
        return {
            "action": _TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot),
            "type": order_type,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": deviation,
            "magic": magic,
            "comment": comment,
            "type_time": 0,   # ORDER_TIME_GTC
            # type_filling is set per-attempt by send_with_fallback
        }

    def _build_close_request(self, position: dict, magic: int,
                              deviation: int, comment: str, tick) -> dict:
        """Build a market close-order request (WITHOUT type_filling)."""
        symbol = position["symbol"]
        pos_type = position["type"]
        if pos_type == "BUY":
            close_type = _ORDER_TYPE_SELL
            price = float(_safe(tick, "bid", 0.0) or 0.0)
        else:
            close_type = _ORDER_TYPE_BUY
            price = float(_safe(tick, "ask", 0.0) or 0.0)
        return {
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
            # type_filling is set per-attempt
        }

    def _refresh_tick(self, symbol: str):
        """Fetch the latest tick. Returns tick object or None."""
        try:
            return self.mt5.symbol_info_tick(symbol)
        except Exception:
            return None

    def _tick_diag(self, tick) -> dict:
        """Extract diagnostic fields from a tick."""
        if tick is None:
            return {"bid": None, "ask": None, "spread": None, "tick_time": None}
        bid = _safe(tick, "bid")
        ask = _safe(tick, "ask")
        spread = None
        try:
            spread = float(ask or 0) - float(bid or 0)
        except Exception:
            pass
        return {"bid": bid, "ask": ask, "spread": spread, "tick_time": _safe(tick, "time")}

    # ─── Duplicate order protection ─────────────────────────────────────────

    def _check_position_appeared(self, symbol: str, magic: int) -> dict:
        """After a failed send, check if a position actually opened.

        Returns dict: {appeared: bool, tickets: list, count: int}.
        Filters by both symbol AND magic — never matches positions from
        other EAs or manual trades.
        """
        try:
            positions = self.mt5.positions_get(symbol=symbol) or []
        except Exception:
            positions = []
        matching = [p for p in positions if _safe(p, "magic") == magic]
        return {
            "appeared": len(matching) > 0,
            "tickets": [_safe(p, "ticket") for p in matching],
            "count": len(matching),
        }

    # ─── Core send with fallback ────────────────────────────────────────────

    def _send_with_fallback(self, base_request: dict, supported_modes: list,
                             label: str = "open") -> dict:
        """Send an order with full filling-mode fallback.

        For each supported filling mode (FOK → IOC → RETURN, filtered):
          1. Refresh tick (latest bid/ask)
          2. Update request price + sl/tp based on fresh tick
          3. Set request['type_filling'] = mode.filling_type
          4. Call mt5.order_check(request) — log result
          5. If check passes, call mt5.order_send(request) — log result
          6. If send succeeds → return success
          7. If send fails with retryable retcode → check positions_get
             for duplicate, then try next mode
          8. If send fails with non-retryable retcode → fail closed
          9. If a position appeared after a failed send → set
             emergency_close_required=True and stop

        Returns a result dict. Never raises.
        """
        symbol = base_request["symbol"]
        magic = base_request["magic"]
        side_str = ("BUY" if base_request.get("type") == _ORDER_TYPE_BUY
                    else "SELL" if base_request.get("type") == _ORDER_TYPE_SELL
                    else None)
        is_close = "position" in base_request and base_request.get("position")

        send_attempts = []
        check_attempts = []

        for mode in supported_modes:
            # ── Refresh tick before each attempt ──
            tick = self._refresh_tick(symbol)
            tick_diag = self._tick_diag(tick)
            if tick is None:
                self._log("ADAPTER_TICK_REFRESH_FAILED", {
                    "label": label, "symbol": symbol,
                    "filling_name": mode["filling_name"],
                })
                # Cannot refresh tick — skip this mode
                continue

            # ── Rebuild request with fresh price ──
            req = dict(base_request)
            if side_str == "BUY":
                req["price"] = float(_safe(tick, "ask", 0.0) or 0.0)
                # Adjust SL/TP around fresh price — but ONLY if the
                # base_request had non-zero SL/TP (i.e. protected order).
                # Sprint 9.9.3.19: naked orders (sl=0, tp=0) must stay naked
                # so the broker compatibility fallback works.
                if req.get("sl"):
                    req["sl"] = req["price"] - 5.0
                if req.get("tp"):
                    req["tp"] = req["price"] + 10.0
            elif side_str == "SELL":
                req["price"] = float(_safe(tick, "bid", 0.0) or 0.0)
                if req.get("sl"):
                    req["sl"] = req["price"] + 5.0
                if req.get("tp"):
                    req["tp"] = req["price"] - 10.0
            # For close orders, don't override SL/TP (close has no SL/TP)
            if is_close:
                if side_str == "BUY":
                    req["price"] = float(_safe(tick, "ask", 0.0) or 0.0)
                else:
                    req["price"] = float(_safe(tick, "bid", 0.0) or 0.0)

            req["type_filling"] = mode["order_filling_type"]

            # ── order_check ──
            try:
                check_result = self.mt5.order_check(req)
            except Exception as e:
                check_result = None
                check_attempts.append({
                    "filling_name": mode["filling_name"],
                    "filling_type": mode["order_filling_type"],
                    "symbol_filling_flag": mode.get("symbol_filling_flag"),
                    "order_filling_type": mode["order_filling_type"],
                    "check_retcode": None,
                    "check_comment": f"order_check raised: {e}",
                    "passed": False,
                    **tick_diag,
                })
                self._log("ADAPTER_ORDER_CHECK_RAISED", {
                    "label": label, "symbol": symbol,
                    "filling_name": mode["filling_name"],
                    "error": str(e), **tick_diag,
                })
                continue

            check_retcode = _safe(check_result, "retcode", None) if check_result else None
            check_comment = _safe(check_result, "comment", "") if check_result else ""
            check_passed = (check_retcode == 0)

            check_attempts.append({
                "filling_name": mode["filling_name"],
                "filling_type": mode["order_filling_type"],
                    "symbol_filling_flag": mode.get("symbol_filling_flag"),
                    "order_filling_type": mode["order_filling_type"],
                "check_retcode": check_retcode,
                "check_comment": check_comment,
                "check_retcode_meaning": lookup_retcode_meaning(check_retcode),
                "passed": check_passed,
                **tick_diag,
            })
            self._log("ADAPTER_ORDER_CHECK_ATTEMPTED", {
                "label": label, "symbol": symbol,
                "filling_name": mode["filling_name"],
                "filling_type": mode["order_filling_type"],
                    "symbol_filling_flag": mode.get("symbol_filling_flag"),
                    "order_filling_type": mode["order_filling_type"],
                "check_retcode": check_retcode,
                "check_comment": check_comment,
                "check_retcode_meaning": lookup_retcode_meaning(check_retcode),
                "passed": check_passed,
                **tick_diag,
            })

            if not check_passed:
                # Check failed — try next mode (do NOT call order_send)
                continue

            # ── order_send ──
            self._log("ADAPTER_ORDER_SEND_ATTEMPTED", {
                "label": label, "symbol": symbol,
                "filling_name": mode["filling_name"],
                "filling_type": mode["order_filling_type"],
                    "symbol_filling_flag": mode.get("symbol_filling_flag"),
                    "order_filling_type": mode["order_filling_type"],
                "price": req["price"],
                "volume": req["volume"],
                "type_time": req.get("type_time"),
                **tick_diag,
            })
            try:
                send_result = self.mt5.order_send(req)
            except Exception as e:
                send_result = None
                self._log("ADAPTER_ORDER_SEND_RAISED", {
                    "label": label, "symbol": symbol,
                    "filling_name": mode["filling_name"],
                    "error": str(e), **tick_diag,
                })

            # Sprint 9.9.3.18 patch — initialize None-result tracking vars
            # before the if/else so they're available for attempt_diag
            # regardless of which branch executes.
            mt5_last_error_code = None
            mt5_last_error_message = ""
            order_send_returned_none = False

            if send_result is None:
                # Sprint 9.9.3.18 patch — order_send returned None.
                # This happens when MT5 encounters an internal error (e.g.,
                # request malformed, terminal not connected, or broker
                # rejected before processing). We must:
                #   1. Call mt5.last_error() to get the actual error
                #   2. Log DEMO_MICRO_ORDER_SEND_NONE with full diagnostics
                #   3. Check positions_get — a position may have been
                #      placed despite the None result (MT5 race condition)
                #   4. If no position: treat as retryable, try next mode
                #   5. If position exists: emergency_close_required
                order_send_returned_none = True
                send_retcode = None
                send_comment = ""
                send_ok = False
                # Call mt5.last_error() — returns (code, message) tuple
                try:
                    last_err = self.mt5.last_error()
                    if last_err is not None:
                        # mt5.last_error() returns a tuple (code, message)
                        # in newer MT5 Python builds, or an int in older ones.
                        if isinstance(last_err, (tuple, list)) and len(last_err) >= 2:
                            mt5_last_error_code = last_err[0]
                            mt5_last_error_message = str(last_err[1])
                        elif isinstance(last_err, int):
                            mt5_last_error_code = last_err
                            mt5_last_error_message = f"MT5 error code {last_err}"
                        else:
                            mt5_last_error_code = str(last_err)
                            mt5_last_error_message = str(last_err)
                except Exception as le_exc:
                    mt5_last_error_message = f"mt5.last_error() raised: {le_exc}"

                self._log("DEMO_MICRO_ORDER_SEND_NONE", {
                    "label": label,
                    "symbol": symbol,
                    "filling_name": mode["filling_name"],
                    "filling_type": mode["order_filling_type"],
                    "symbol_filling_flag": mode.get("symbol_filling_flag"),
                    "order_filling_type": mode["order_filling_type"],
                    "price": req["price"],
                    "volume": req["volume"],
                    "request": _safe_request(req),
                    "mt5_last_error_code": mt5_last_error_code,
                    "mt5_last_error_message": mt5_last_error_message,
                    "bid": tick_diag.get("bid"),
                    "ask": tick_diag.get("ask"),
                    "spread": tick_diag.get("spread"),
                    "tick_time": tick_diag.get("tick_time"),
                    "reason": ("mt5.order_send() returned None — internal "
                               "MT5 error, no trade result available"),
                })
            else:
                send_retcode = _safe(send_result, "retcode", None)
                send_comment = _safe(send_result, "comment", "")
                send_ok = send_retcode in _SUCCESS_RETCODES

            attempt_diag = {
                "filling_name": mode["filling_name"],
                "filling_type": mode["order_filling_type"],
                    "symbol_filling_flag": mode.get("symbol_filling_flag"),
                    "order_filling_type": mode["order_filling_type"],
                "send_retcode": send_retcode,
                "send_comment": send_comment,
                "send_retcode_meaning": lookup_retcode_meaning(send_retcode),
                "send_ok": send_ok,
                "price": req["price"],
                # Sprint 9.9.3.18 patch — None-result diagnostics
                "order_send_returned_none": order_send_returned_none,
                "mt5_last_error_code": mt5_last_error_code,
                "mt5_last_error_message": mt5_last_error_message,
                **tick_diag,
            }
            send_attempts.append(attempt_diag)

            self._log("ADAPTER_ORDER_SEND_RESULT", {
                "label": label, "symbol": symbol,
                "filling_name": mode["filling_name"],
                "filling_type": mode["order_filling_type"],
                    "symbol_filling_flag": mode.get("symbol_filling_flag"),
                    "order_filling_type": mode["order_filling_type"],
                "send_retcode": send_retcode,
                "send_comment": send_comment,
                "send_retcode_meaning": lookup_retcode_meaning(send_retcode),
                "send_ok": send_ok,
                "price": req["price"],
                **tick_diag,
            })

            if send_ok:
                # SUCCESS — order placed.
                # Verify a position actually opened (defense in depth).
                pos_check = self._check_position_appeared(symbol, magic)
                return {
                    "ok": True,
                    "retcode": send_retcode,
                    "order": _safe(send_result, "order"),
                    "deal": _safe(send_result, "deal"),
                    "volume": _safe(send_result, "volume"),
                    "price": _safe(send_result, "price"),
                    "comment": send_comment,
                    "request": _safe_request(req),
                    "filling_mode_selected": mode["filling_name"],
                    "filling_type_used": mode["order_filling_type"],
                    "filling_source": mode["filling_source"],
                    "filling_mask": mode["filling_mask"],
                    "check_attempts": check_attempts,
                    "send_attempts": send_attempts,
                    "position_detected_after_send": pos_check,
                    "emergency_close_required": False,
                }

            # ── Send failed — check for duplicate position immediately ──
            # Sprint 9.9.3.17 patch — only check for "ghost position" on OPEN
            # orders. For CLOSE orders, the position we're trying to close is
            # expected to still be open after a failure — that's normal, not
            # an emergency. Ghost position detection is only relevant when
            # we're opening a NEW position and the broker might have placed
            # it despite returning a failure retcode.
            pos_check = self._check_position_appeared(symbol, magic)
            self._log("ADAPTER_POSITION_CHECK_AFTER_FAILURE", {
                "label": label, "symbol": symbol,
                "filling_name": mode["filling_name"],
                "send_retcode": send_retcode,
                "position_appeared": pos_check["appeared"],
                "position_count": pos_check["count"],
                "position_tickets": pos_check["tickets"],
                "is_close_order": is_close,
            })

            if pos_check["appeared"] and not is_close:
                # CRITICAL (OPEN orders only): broker placed the position
                # DESPITE returning a failure retcode. This is a known MT5
                # race condition. Set emergency_close_required and STOP
                # trying more modes (we don't want to open a duplicate).
                self._log("ADAPTER_EMERGENCY_CLOSE_REQUIRED", {
                    "label": label, "symbol": symbol,
                    "filling_name": mode["filling_name"],
                    "send_retcode": send_retcode,
                    "position_tickets": pos_check["tickets"],
                    "severity": "HIGH",
                    "reason": ("broker returned failure retcode but a position "
                               "with our magic is open — immediate close required"),
                })
                return {
                    "ok": False,
                    "retcode": send_retcode,
                    "error": ("position appeared after failed send — "
                              "emergency close required"),
                    "request": _safe_request(req),
                    "filling_mode_selected": mode["filling_name"],
                    "filling_type_used": mode["order_filling_type"],
                    "filling_source": mode["filling_source"],
                    "filling_mask": mode["filling_mask"],
                    "check_attempts": check_attempts,
                    "send_attempts": send_attempts,
                    "position_detected_after_failure": pos_check,
                    "emergency_close_required": True,
                    "emergency_close_tickets": pos_check["tickets"],
                }

            # Send failed but no position opened — decide if retryable.
            # Sprint 9.9.3.18 patch — order_send returning None (send_retcode
            # is None) is treated as RETRYABLE: the broker didn't process
            # the request (internal error), so no position was created by
            # this attempt. It's safe to try the next filling mode.
            is_none_result = send_retcode is None
            is_retryable = is_none_result or (send_retcode in _RETRYABLE_RETCODES)
            if not is_retryable:
                # Non-retryable — fail closed immediately.
                self._log("ADAPTER_NON_RETRYABLE_FAILURE", {
                    "label": label, "symbol": symbol,
                    "filling_name": mode["filling_name"],
                    "send_retcode": send_retcode,
                    "send_retcode_meaning": lookup_retcode_meaning(send_retcode),
                    "reason": "non-retryable retcode — failing closed",
                })
                return {
                    "ok": False,
                    "retcode": send_retcode,
                    "error": (f"non-retryable failure: retcode={send_retcode} "
                              f"({lookup_retcode_meaning(send_retcode) or 'unknown'})"),
                    "request": _safe_request(req),
                    "filling_mode_selected": mode["filling_name"],
                    "filling_type_used": mode["order_filling_type"],
                    "filling_source": mode["filling_source"],
                    "filling_mask": mode["filling_mask"],
                    "check_attempts": check_attempts,
                    "send_attempts": send_attempts,
                    "position_detected_after_failure": pos_check,
                    "emergency_close_required": False,
                }
            # Retryable — fall through to next mode.
            if is_none_result:
                self._log("ADAPTER_RETRYABLE_FAILURE", {
                    "label": label, "symbol": symbol,
                    "filling_name": mode["filling_name"],
                    "send_retcode": send_retcode,
                    "order_send_returned_none": True,
                    "mt5_last_error_code": mt5_last_error_code,
                    "reason": ("order_send returned None — treating as "
                               "retryable, trying next filling mode"),
                })
            else:
                self._log("ADAPTER_RETRYABLE_FAILURE", {
                    "label": label, "symbol": symbol,
                    "filling_name": mode["filling_name"],
                    "send_retcode": send_retcode,
                    "reason": "retryable retcode — trying next filling mode",
                })

        # ── All modes exhausted ──
        self._log("ADAPTER_ALL_MODES_EXHAUSTED", {
            "label": label, "symbol": symbol,
            "check_attempts_count": len(check_attempts),
            "send_attempts_count": len(send_attempts),
            "reason": "all order_send filling attempts rejected",
        })
        # Final position check — defense in depth.
        final_pos_check = self._check_position_appeared(symbol, magic)
        return {
            "ok": False,
            "retcode": None,
            "error": ("all order_send filling attempts rejected — "
                      f"{len(send_attempts)} send attempts, "
                      f"{len(check_attempts)} check attempts"),
            "request": None,
            "filling_mode_selected": None,
            "filling_type_used": None,
            "filling_source": None,
            "filling_mask": None,
            "check_attempts": check_attempts,
            "send_attempts": send_attempts,
            "position_detected_after_failure": final_pos_check,
            "emergency_close_required": final_pos_check["appeared"],
            "emergency_close_tickets": final_pos_check.get("tickets", []),
        }

    # ─── Sprint 9.9.3.19: Broker compatibility fallback ──────────────────────

    def _should_try_naked_fallback(self, fallback_result: dict,
                                     snapshot: dict) -> bool:
        """Sprint 9.9.3.19 — decide if the two-step naked order fallback
        should be attempted after the protected order was rejected.

        Conditions:
          1. demo_micro mode only (caller passes demo_micro=True)
          2. Protected order send failed with a retryable reject code
             (10006 REJECT or 10016 INVALID_STOPS)
          3. Symbol uses MARKET execution (trade_exemode == 2)
          4. No position appeared after the failed send (no ghost)
          5. At least one send attempt was made (order_send was called)

        Returns True if the naked fallback should be tried.
        """
        if fallback_result.get("ok"):
            return False   # Already succeeded — no need
        if fallback_result.get("emergency_close_required"):
            return False   # Ghost position — don't try naked
        # Check trade_execution mode
        trade_exec = snapshot.get("symbol_info", {}).get("trade_exemode")
        if trade_exec != _TRADE_EXECUTION_MARKET:
            return False   # Only for MARKET execution symbols
        # Check send attempts for a protected-order reject
        send_attempts = fallback_result.get("send_attempts") or []
        if not send_attempts:
            return False   # No send was attempted
        # At least one send attempt must have a protected-order reject retcode
        for a in send_attempts:
            if a.get("send_retcode") in _PROTECTED_ORDER_REJECT_RETCODES:
                return True
        return False

    def _modify_position_sltp(self, position_ticket: int, symbol: str,
                               sl: float, tp: float) -> dict:
        """Sprint 9.9.3.19 / 9.9.3.25.1 — modify a position's SL/TP via
        TRADE_ACTION_SLTP.

        Sprint 9.9.3.25.1 hotfix:
          - Uses runtime mt5.TRADE_ACTION_SLTP (not hardcoded 2)
          - Rounds SL/TP to symbol digits
          - Validates SL/TP are non-zero
          - Validates position ticket exists
          - Checks trade_stops_level and trade_freeze_level
          - Returns detailed diagnostics on failure

        Returns dict with ok/retcode/comment/retcode_meaning. Never raises.
        """
        # Sprint 9.9.3.25.1 — resolve runtime TRADE_ACTION_SLTP
        action_sltp = self._get_trade_action_sltp()

        # Sprint 9.9.3.25.1 — validate inputs
        if position_ticket is None or position_ticket <= 0:
            return {"ok": False, "retcode": None, "comment": "Invalid position ticket",
                    "request": {}, "reason": "position_ticket invalid"}
        if sl == 0 or tp == 0:
            return {"ok": False, "retcode": None, "comment": "SL/TP must not be zero",
                    "request": {}, "reason": "sl_or_tp_zero"}

        # Sprint 9.9.3.25.1 — round SL/TP to symbol digits
        try:
            info = self.mt5.symbol_info(symbol)
            digits = _safe(info, "digits", 5) if info else 5
            point = _safe(info, "point", 0.01) if info else 0.01
        except Exception:
            digits = 5
            point = 0.01
        sl_rounded = round(float(sl), digits)
        tp_rounded = round(float(tp), digits)

        # Sprint 9.9.3.25.1 — check trade_stops_level / trade_freeze_level
        trade_stops_level = _safe(info, "trade_stops_level", 0) if info else 0
        trade_freeze_level = _safe(info, "trade_freeze_level", 0) if info else 0
        # Get current price for stop distance check
        try:
            tick = self.mt5.symbol_info_tick(symbol)
            current_price = _safe(tick, "bid", 0) if tick else 0
        except Exception:
            current_price = 0

        if current_price > 0 and trade_stops_level > 0 and point > 0:
            min_stop_distance = trade_stops_level * point
            sl_distance = abs(current_price - sl_rounded)
            if sl_distance < min_stop_distance:
                self._log("ADAPTER_SLTP_MODIFY_STOP_DISTANCE_VIOLATION", {
                    "position_ticket": position_ticket,
                    "sl_distance": sl_distance,
                    "min_stop_distance": min_stop_distance,
                    "trade_stops_level": trade_stops_level,
                    "reason": "SL too close to current price — broker minimum stop level violated",
                })
                return {
                    "ok": False, "retcode": None,
                    "comment": f"SL distance {sl_distance} < min stop distance {min_stop_distance}",
                    "request": {},
                    "reason": "stop_distance_violation",
                    "trade_stops_level": trade_stops_level,
                    "sl_distance": sl_distance,
                    "min_stop_distance": min_stop_distance,
                }

        request = {
            "action": action_sltp,   # Sprint 9.9.3.25.1 — runtime resolved
            "symbol": symbol,
            "position": int(position_ticket),
            "sl": sl_rounded,
            "tp": tp_rounded,
        }
        self._log("ADAPTER_SLTP_MODIFY_ATTEMPTED", {
            "symbol": symbol,
            "position_ticket": position_ticket,
            "sl": sl_rounded,
            "tp": tp_rounded,
            "action": action_sltp,
            "action_source": "runtime_mt5.TRADE_ACTION_SLTP",
            "request": _safe_request(request),
            "digits": digits,
            "trade_stops_level": trade_stops_level,
            "trade_freeze_level": trade_freeze_level,
        })
        try:
            result = self.mt5.order_send(request)
        except Exception as e:
            self._log("ADAPTER_SLTP_MODIFY_RAISED", {
                "position_ticket": position_ticket, "error": str(e),
            })
            return {"ok": False, "retcode": None, "comment": str(e),
                    "request": _safe_request(request)}
        if result is None:
            # Sprint 9.9.3.18 — get last_error on None
            mt5_last_error_code = None
            mt5_last_error_message = ""
            try:
                last_err = self.mt5.last_error()
                if isinstance(last_err, (tuple, list)) and len(last_err) >= 2:
                    mt5_last_error_code = last_err[0]
                    mt5_last_error_message = str(last_err[1])
                elif isinstance(last_err, int):
                    mt5_last_error_code = last_err
                    mt5_last_error_message = f"MT5 error code {last_err}"
            except Exception:
                pass
            self._log("ADAPTER_SLTP_MODIFY_NONE", {
                "position_ticket": position_ticket,
                "mt5_last_error_code": mt5_last_error_code,
                "mt5_last_error_message": mt5_last_error_message,
            })
            return {"ok": False, "retcode": None, "comment": "",
                    "mt5_last_error_code": mt5_last_error_code,
                    "mt5_last_error_message": mt5_last_error_message,
                    "request": _safe_request(request)}
        retcode = _safe(result, "retcode", None)
        comment = _safe(result, "comment", "")
        ok = retcode in _SUCCESS_RETCODES
        retcode_meaning = lookup_retcode_meaning(retcode)
        self._log("ADAPTER_SLTP_MODIFY_RESULT", {
            "position_ticket": position_ticket,
            "retcode": retcode,
            "comment": comment,
            "retcode_meaning": retcode_meaning,
            "ok": ok,
        })
        return {"ok": ok, "retcode": retcode, "comment": comment,
                "retcode_meaning": retcode_meaning,
                "request": _safe_request(request)}

    def _try_naked_order_fallback(self, base_request: dict,
                                    supported_modes: list,
                                    snapshot: dict,
                                    protected_fallback_result: dict) -> dict:
        """Sprint 9.9.3.19 — two-step broker compatibility fallback.

        When a protected market order (SL/TP attached) is rejected by a
        MARKET-execution broker (FBS scenario), try:
          a) Send naked market order (sl=0, tp=0)
          b) If opened, immediately apply SL/TP via TRADE_ACTION_SLTP
          c) If SL/TP modify fails, immediately close the position

        This method is ONLY called when _should_try_naked_fallback() is True.
        Returns a result dict with the same shape as _send_with_fallback.
        """
        symbol = base_request["symbol"]
        magic = base_request["magic"]
        side_str = ("BUY" if base_request.get("type") == _ORDER_TYPE_BUY
                    else "SELL")

        # Log that protected order was rejected
        protected_reject_retcode = None
        for a in reversed(protected_fallback_result.get("send_attempts") or []):
            if a.get("send_retcode") in _PROTECTED_ORDER_REJECT_RETCODES:
                protected_reject_retcode = a.get("send_retcode")
                break
        self._log("ADAPTER_PROTECTED_ORDER_REJECTED", {
            "symbol": symbol,
            "protected_reject_retcode": protected_reject_retcode,
            "protected_reject_meaning": lookup_retcode_meaning(protected_reject_retcode),
            "reason": ("protected market order (SL/TP attached) rejected by "
                       "MARKET-execution broker — trying naked order fallback"),
            "trade_execution": snapshot.get("symbol_info", {}).get("trade_exemode"),
        })

        # Build naked request (sl=0, tp=0)
        naked_request = dict(base_request)
        naked_request["sl"] = 0.0
        naked_request["tp"] = 0.0

        self._log("ADAPTER_NAKED_ORDER_ATTEMPTED", {
            "symbol": symbol,
            "side": side_str,
            "naked_request": _safe_request(naked_request),
            "reason": "sending market order with sl=0, tp=0",
        })

        # Try naked order with the same filling-mode fallback
        naked_result = self._send_with_fallback(naked_request, supported_modes,
                                                  label="open_naked")

        if not naked_result["ok"]:
            # Naked order also failed — return the naked failure
            self._log("ADAPTER_NAKED_ORDER_FAILED", {
                "symbol": symbol,
                "error": naked_result.get("error"),
                "send_attempts": naked_result.get("send_attempts"),
            })
            # Merge send_attempts from both protected and naked attempts
            merged_attempts = (protected_fallback_result.get("send_attempts") or []
                               + naked_result.get("send_attempts") or [])
            return {
                **naked_result,
                "send_attempts": (protected_fallback_result.get("send_attempts") or [])
                                  + (naked_result.get("send_attempts") or []),
                "broker_compatibility_fallback_tried": True,
                "broker_compatibility_fallback_succeeded": False,
            }

        # Naked order succeeded! Now apply SL/TP via TRADE_ACTION_SLTP.
        # Find the position that was just opened.
        pos_check = self._check_position_appeared(symbol, magic)
        if not pos_check["appeared"]:
            # Position didn't appear despite naked success — unusual but
            # treat as failure. The naked order's retcode was success but
            # no position to modify.
            self._log("ADAPTER_NAKED_SUCCESS_NO_POSITION", {
                "symbol": symbol,
                "naked_retcode": naked_result.get("retcode"),
                "reason": "naked order reported success but no position found",
            })
            return {
                **naked_result,
                "ok": False,
                "error": "naked order succeeded but no position appeared for SLTP modify",
                "broker_compatibility_fallback_tried": True,
                "broker_compatibility_fallback_succeeded": False,
            }

        position_ticket = pos_check["tickets"][0] if pos_check["tickets"] else None
        # Reconstruct the intended SL/TP from the original base_request
        original_sl = base_request.get("sl", 0.0)
        original_tp = base_request.get("tp", 0.0)

        self._log("ADAPTER_SLTP_MODIFY_REQUESTED", {
            "symbol": symbol,
            "position_ticket": position_ticket,
            "intended_sl": original_sl,
            "intended_tp": original_tp,
        })

        sltp_result = self._modify_position_sltp(
            position_ticket, symbol, original_sl, original_tp,
        )

        if sltp_result["ok"]:
            # SLTP modify succeeded — full success!
            self._log("ADAPTER_SLTP_MODIFY_SUCCESS", {
                "symbol": symbol,
                "position_ticket": position_ticket,
                "sl": original_sl,
                "tp": original_tp,
            })
            return {
                **naked_result,
                "ok": True,
                "filling_mode_selected": naked_result.get("filling_mode_selected"),
                "filling_type_used": naked_result.get("filling_type_used"),
                "filling_source": naked_result.get("filling_source"),
                "filling_mask": naked_result.get("filling_mask"),
                "check_attempts": (protected_fallback_result.get("check_attempts") or [])
                                   + (naked_result.get("check_attempts") or []),
                "send_attempts": (protected_fallback_result.get("send_attempts") or [])
                                  + (naked_result.get("send_attempts") or []),
                "sltp_modify_result": sltp_result,
                "broker_compatibility_fallback_tried": True,
                "broker_compatibility_fallback_succeeded": True,
                "position_ticket": position_ticket,
            }

        # SLTP modify FAILED — must emergency close the naked position.
        self._log("ADAPTER_EMERGENCY_CLOSE_IF_SLTP_FAILED", {
            "symbol": symbol,
            "position_ticket": position_ticket,
            "sltp_modify_retcode": sltp_result.get("retcode"),
            "sltp_modify_comment": sltp_result.get("comment"),
            "severity": "HIGH",
            "reason": ("SLTP modify failed after naked order succeeded — "
                       "closing position to avoid unprotected exposure"),
        })
        # Build a position dict for closing
        # Determine position type from the naked request
        pos_type = "BUY" if naked_request.get("type") == _ORDER_TYPE_BUY else "SELL"
        ghost_position_dict = {
            "ticket": position_ticket,
            "type": pos_type,
            "volume": naked_request.get("volume", 0.01),
            "symbol": symbol,
            "price_open": naked_result.get("price"),
        }
        close_result = self.send_close_order(
            position=ghost_position_dict, magic=magic,
        )
        self._log("ADAPTER_EMERGENCY_CLOSE_AFTER_SLTP_FAIL_RESULT", {
            "position_ticket": position_ticket,
            "close_ok": close_result.get("ok"),
            "close_retcode": close_result.get("retcode"),
        })
        return {
            **naked_result,
            "ok": False,
            "retcode": naked_result.get("retcode"),
            "error": "OPEN_SUCCEEDED_SLTP_MODIFY_FAILED_EMERGENCY_CLOSED",
            "reason": ("Naked order opened successfully (retcode="
                       f"{naked_result.get('retcode')}) but SLTP modify failed "
                       f"(retcode={sltp_result.get('retcode')}, "
                       f"comment={sltp_result.get('comment', '')}, "
                       f"meaning={sltp_result.get('retcode_meaning', '')}) — "
                       f"emergency close attempted (success={close_result.get('ok', False)})"),
            "open_retcode": naked_result.get("retcode"),
            "sltp_modify_retcode": sltp_result.get("retcode"),
            "sltp_modify_comment": sltp_result.get("comment"),
            "sltp_modify_retcode_meaning": sltp_result.get("retcode_meaning"),
            "emergency_close_required": True,
            "emergency_close_tickets": [position_ticket] if position_ticket else [],
            "emergency_close_attempted": True,
            "emergency_close_success": close_result.get("ok", False),
            "emergency_close_result": close_result,
            "sltp_modify_result": sltp_result,
            "broker_compatibility_fallback_tried": True,
            "broker_compatibility_fallback_succeeded": False,
            "position_ticket": position_ticket,
        }

    # ─── Sprint 9.9.3.21: Raw working profile support ────────────────────────

    def _load_raw_working_profile(self,
                                    profile_path: Optional[str] = None) -> Optional[dict]:
        """Sprint 9.9.3.21 — load raw_mt5_working_profile.json.

        This profile is generated by scripts/audit/raw_mt5_probe.py and
        contains the exact request shape that succeeded on this broker
        (symbol, type_filling, deviation, sl/tp mode, type_time, etc.).

        Returns the profile dict, or None if the file doesn't exist or
        can't be parsed.
        """
        path = Path(profile_path) if profile_path else RAW_WORKING_PROFILE_PATH
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            self._log("ADAPTER_RAW_PROFILE_LOAD_FAILED", {
                "path": str(path), "error": str(e),
            })
            return None

    def _validate_raw_profile_binding(self, raw_profile: dict,
                                        snapshot: dict, symbol: str) -> Optional[dict]:
        """Sprint 9.9.3.23 — validate that the raw profile matches the
        current MT5 broker/account.

        Checks:
          1. raw_profile.server == snapshot.account.server
          2. raw_profile.login == snapshot.account.login
          3. raw_profile.symbol == symbol
          4. Account is DEMO (trade_mode == 0)

        Returns None if all checks pass, or a fail-closed result dict if
        any mismatch is found. The result dict includes a "mismatches"
        list detailing which fields didn't match.
        """
        mismatches = []
        snap_account = snapshot.get("account", {})
        snap_server = snap_account.get("server")
        snap_login = snap_account.get("login")
        snap_trade_mode = snap_account.get("trade_mode")

        raw_server = raw_profile.get("server")
        raw_login = raw_profile.get("login")
        raw_symbol = raw_profile.get("symbol")

        # 1. Server match
        if raw_server and snap_server and raw_server != snap_server:
            mismatches.append({
                "field": "server",
                "raw_profile_value": raw_server,
                "current_value": snap_server,
            })

        # 2. Login match
        if raw_login is not None and snap_login is not None and str(raw_login) != str(snap_login):
            mismatches.append({
                "field": "login",
                "raw_profile_value": _mask_login(raw_login),
                "current_value": _mask_login(snap_login),
            })

        # 3. Symbol match
        if raw_symbol and symbol and raw_symbol != symbol:
            mismatches.append({
                "field": "symbol",
                "raw_profile_value": raw_symbol,
                "current_value": symbol,
            })

        # 4. Account must be DEMO
        if snap_trade_mode is not None and snap_trade_mode != 0:
            mismatches.append({
                "field": "trade_mode",
                "raw_profile_value": "DEMO (0)",
                "current_value": f"{snap_trade_mode} (not DEMO)",
            })

        if mismatches:
            self._log("DEMO_MICRO_PROFILE_MISMATCH_BLOCKED", {
                "mismatches": mismatches,
                "raw_profile_server": raw_server,
                "current_server": snap_server,
                "symbol": symbol,
                "severity": "HIGH",
                "reason": ("raw working profile does not match current MT5 "
                           "broker/account — execution blocked for safety"),
            })
            return {
                "ok": False,
                "retcode": None,
                "error": ("raw profile mismatch — execution blocked: "
                          + ", ".join(m["field"] for m in mismatches)),
                "filling_mode_selected": None,
                "filling_type_used": None,
                "filling_source": None,
                "check_attempts": [],
                "send_attempts": [],
                "position_detected_after_failure": snapshot.get("open_positions", {}),
                "emergency_close_required": False,
                "broker_snapshot": snapshot,
                "raw_working_profile_used": True,
                "profile_mismatch": True,
                "mismatches": mismatches,
            }
        return None

    def _send_raw_compatible_open(self, symbol: str, side: str, lot: float,
                                    magic: int, deviation: int,
                                    comment: str, snapshot: dict,
                                    raw_profile: dict) -> dict:
        """Sprint 9.9.3.21 — send a naked IOC order mirroring the raw
        working profile, then apply SL/TP via TRADE_ACTION_SLTP.

        Flow:
          1. Build naked request (sl=0, tp=0) using the raw profile's
             type_filling (IOC), deviation, and type_time
          2. Send naked order
          3. If opened, apply SL/TP via TRADE_ACTION_SLTP
          4. If SLTP modify fails, emergency close the position

        Returns a result dict with the same shape as _send_with_fallback.
        """
        # Sprint 9.9.3.23 — validate raw profile matches current broker/account
        mismatch_result = self._validate_raw_profile_binding(raw_profile, snapshot, symbol)
        if mismatch_result is not None:
            return mismatch_result

        # Read filling mode from raw profile (prefer IOC)
        raw_filling_type = raw_profile.get("type_filling", 2)  # default IOC=2
        raw_deviation = raw_profile.get("deviation", deviation)
        raw_type_time = raw_profile.get("type_time", 0)

        # Find the matching mode in supported_modes (for diagnostics)
        supported_modes = self._list_supported_filling_modes(symbol)
        raw_mode = None
        for m in supported_modes:
            if m["order_filling_type"] == raw_filling_type:
                raw_mode = m
                break
        if raw_mode is None:
            # Construct a synthetic mode dict from the raw profile
            raw_mode = {
                "filling_name": raw_profile.get("type_filling_name", "IOC"),
                "symbol_filling_flag": None,
                "order_filling_type": raw_filling_type,
                "filling_mask": snapshot.get("symbol_info", {}).get("filling_mode"),
                "filling_source": "raw_working_profile",
            }

        self._log("ADAPTER_RAW_PROFILE_LOADED", {
            "symbol": symbol,
            "raw_profile_server": raw_profile.get("server"),
            "raw_profile_type_filling": raw_filling_type,
            "raw_profile_deviation": raw_deviation,
            "raw_profile_sl_tp_mode": raw_profile.get("sl_tp_mode"),
            "filling_name": raw_mode["filling_name"],
            "filling_source": "raw_working_profile",
        })

        # Refresh tick
        tick = self._refresh_tick(symbol)
        if tick is None:
            return {
                "ok": False, "retcode": None,
                "error": "no tick available for raw-compatible open",
                "filling_mode_selected": None,
                "check_attempts": [], "send_attempts": [],
                "emergency_close_required": False,
                "broker_snapshot": snapshot,
                "raw_working_profile_used": True,
            }

        # Build naked request (sl=0, tp=0) — mirrors the raw probe
        if side == "BUY":
            price = float(_safe(tick, "ask", 0.0) or 0.0)
            order_type = _ORDER_TYPE_BUY
            intended_sl = price - 5.0
            intended_tp = price + 10.0
        else:
            price = float(_safe(tick, "bid", 0.0) or 0.0)
            order_type = _ORDER_TYPE_SELL
            intended_sl = price + 5.0
            intended_tp = price - 10.0

        naked_request = {
            "action": _TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot),
            "type": order_type,
            "price": price,
            "sl": 0.0,        # naked — mirrors raw probe
            "tp": 0.0,        # naked — mirrors raw probe
            "deviation": raw_deviation,
            "magic": magic,
            "comment": comment,
            "type_time": raw_type_time,
            "type_filling": raw_filling_type,
        }

        self._log("ADAPTER_RAW_NAKED_ORDER_ATTEMPTED", {
            "symbol": symbol,
            "side": side,
            "request": _safe_request(naked_request),
            "filling_name": raw_mode["filling_name"],
            "raw_profile_source": raw_profile.get("server"),
        })

        # Run order_check
        try:
            check_result = self.mt5.order_check(naked_request)
        except Exception as e:
            check_result = None
            self._log("ADAPTER_RAW_ORDER_CHECK_RAISED", {"error": str(e)})

        check_retcode = _safe(check_result, "retcode", None) if check_result else None
        if check_retcode != 0:
            self._log("ADAPTER_RAW_ORDER_CHECK_FAILED", {
                "retcode": check_retcode,
                "comment": _safe(check_result, "comment", "") if check_result else "",
            })
            return {
                "ok": False, "retcode": None,
                "error": f"raw order_check failed: retcode={check_retcode}",
                "filling_mode_selected": raw_mode["filling_name"],
                "filling_source": "raw_working_profile",
                "check_attempts": [{"filling_name": raw_mode["filling_name"],
                                     "check_retcode": check_retcode, "passed": False}],
                "send_attempts": [],
                "emergency_close_required": False,
                "broker_snapshot": snapshot,
                "raw_working_profile_used": True,
            }

        # Send the naked order
        try:
            send_result = self.mt5.order_send(naked_request)
        except Exception as e:
            send_result = None
            self._log("ADAPTER_RAW_ORDER_SEND_RAISED", {"error": str(e)})

        if send_result is None:
            # Handle None result (Sprint 9.9.3.18)
            mt5_last_error_code = None
            mt5_last_error_message = ""
            try:
                last_err = self.mt5.last_error()
                if isinstance(last_err, (tuple, list)) and len(last_err) >= 2:
                    mt5_last_error_code = last_err[0]
                    mt5_last_error_message = str(last_err[1])
            except Exception:
                pass
            self._log("DEMO_MICRO_ORDER_SEND_NONE", {
                "label": "raw_open",
                "symbol": symbol,
                "filling_name": raw_mode["filling_name"],
                "mt5_last_error_code": mt5_last_error_code,
                "mt5_last_error_message": mt5_last_error_message,
            })
            return {
                "ok": False, "retcode": None,
                "error": "raw order_send returned None",
                "filling_mode_selected": raw_mode["filling_name"],
                "filling_source": "raw_working_profile",
                "check_attempts": [{"filling_name": raw_mode["filling_name"],
                                     "check_retcode": 0, "passed": True}],
                "send_attempts": [{"filling_name": raw_mode["filling_name"],
                                    "send_retcode": None, "send_ok": False,
                                    "order_send_returned_none": True,
                                    "mt5_last_error_code": mt5_last_error_code}],
                "emergency_close_required": False,
                "broker_snapshot": snapshot,
                "raw_working_profile_used": True,
            }

        send_retcode = _safe(send_result, "retcode", None)
        send_ok = send_retcode in _SUCCESS_RETCODES

        self._log("ADAPTER_RAW_ORDER_SEND_RESULT", {
            "symbol": symbol,
            "filling_name": raw_mode["filling_name"],
            "send_retcode": send_retcode,
            "send_ok": send_ok,
            "price": _safe(send_result, "price"),
        })

        if not send_ok:
            return {
                "ok": False, "retcode": send_retcode,
                "error": f"raw order_send failed: retcode={send_retcode}",
                "filling_mode_selected": raw_mode["filling_name"],
                "filling_source": "raw_working_profile",
                "check_attempts": [{"filling_name": raw_mode["filling_name"],
                                     "check_retcode": 0, "passed": True}],
                "send_attempts": [{"filling_name": raw_mode["filling_name"],
                                    "send_retcode": send_retcode, "send_ok": False}],
                "emergency_close_required": False,
                "broker_snapshot": snapshot,
                "raw_working_profile_used": True,
            }

        # ── Naked order succeeded — apply SL/TP via TRADE_ACTION_SLTP ──
        pos_check = self._check_position_appeared(symbol, magic)
        if not pos_check["appeared"]:
            return {
                "ok": False, "retcode": send_retcode,
                "error": "raw naked order succeeded but no position appeared",
                "filling_mode_selected": raw_mode["filling_name"],
                "filling_source": "raw_working_profile",
                "check_attempts": [{"filling_name": raw_mode["filling_name"],
                                     "check_retcode": 0, "passed": True}],
                "send_attempts": [{"filling_name": raw_mode["filling_name"],
                                    "send_retcode": send_retcode, "send_ok": True}],
                "emergency_close_required": False,
                "broker_snapshot": snapshot,
                "raw_working_profile_used": True,
            }

        position_ticket = pos_check["tickets"][0] if pos_check["tickets"] else None
        sltp_result = self._modify_position_sltp(
            position_ticket, symbol, intended_sl, intended_tp,
        )

        if sltp_result["ok"]:
            self._log("ADAPTER_RAW_SLTP_MODIFY_SUCCESS", {
                "symbol": symbol,
                "position_ticket": position_ticket,
                "sl": intended_sl, "tp": intended_tp,
            })
            return {
                "ok": True, "retcode": send_retcode,
                "order": _safe(send_result, "order"),
                "deal": _safe(send_result, "deal"),
                "volume": _safe(send_result, "volume"),
                "price": _safe(send_result, "price"),
                "comment": _safe(send_result, "comment", ""),
                "request": _safe_request(naked_request),
                "filling_mode_selected": raw_mode["filling_name"],
                "filling_type_used": raw_filling_type,
                "filling_source": "raw_working_profile",
                "filling_mask": raw_mode.get("filling_mask"),
                "check_attempts": [{"filling_name": raw_mode["filling_name"],
                                     "check_retcode": 0, "passed": True}],
                "send_attempts": [{"filling_name": raw_mode["filling_name"],
                                    "send_retcode": send_retcode, "send_ok": True,
                                    "price": _safe(send_result, "price")}],
                "sltp_modify_result": sltp_result,
                "position_ticket": position_ticket,
                "broker_snapshot": snapshot,
                "raw_working_profile_used": True,
                "raw_naked_open_then_sltp": True,
            }

        # SLTP modify failed — emergency close
        self._log("ADAPTER_EMERGENCY_CLOSE_IF_SLTP_FAILED", {
            "symbol": symbol,
            "position_ticket": position_ticket,
            "sltp_modify_retcode": sltp_result.get("retcode"),
            "severity": "HIGH",
            "reason": "SLTP modify failed after raw naked open — closing position",
        })
        pos_type = "BUY" if order_type == _ORDER_TYPE_BUY else "SELL"
        ghost_position_dict = {
            "ticket": position_ticket,
            "type": pos_type,
            "volume": lot,
            "symbol": symbol,
            "price_open": _safe(send_result, "price"),
        }
        close_result = self.send_close_order(
            position=ghost_position_dict, magic=magic,
        )
        return {
            "ok": False, "retcode": send_retcode,
            "error": "OPEN_SUCCEEDED_SLTP_MODIFY_FAILED_EMERGENCY_CLOSED",
            "reason": ("Raw naked order opened successfully (retcode="
                       f"{send_retcode}) but SLTP modify failed "
                       f"(retcode={sltp_result.get('retcode')}, "
                       f"comment={sltp_result.get('comment', '')}, "
                       f"meaning={sltp_result.get('retcode_meaning', '')}) — "
                       f"emergency close attempted (success={close_result.get('ok', False)})"),
            "open_retcode": send_retcode,
            "sltp_modify_retcode": sltp_result.get("retcode"),
            "sltp_modify_comment": sltp_result.get("comment"),
            "sltp_modify_retcode_meaning": sltp_result.get("retcode_meaning"),
            "filling_mode_selected": raw_mode["filling_name"],
            "filling_source": "raw_working_profile",
            "check_attempts": [{"filling_name": raw_mode["filling_name"],
                                 "check_retcode": 0, "passed": True}],
            "send_attempts": [{"filling_name": raw_mode["filling_name"],
                                "send_retcode": send_retcode, "send_ok": True}],
            "sltp_modify_result": sltp_result,
            "emergency_close_required": True,
            "emergency_close_attempted": True,
            "emergency_close_success": close_result.get("ok", False),
            "emergency_close_result": close_result,
            "position_ticket": position_ticket,
            "broker_snapshot": snapshot,
            "raw_working_profile_used": True,
        }

    # ─── Public API ─────────────────────────────────────────────────────────

    def send_open_order(self, symbol: str, side: str, lot: float,
                        magic: int, deviation: int = 20,
                        comment: str = "TITAN_DEMO_MICRO",
                        demo_micro: bool = False,
                        use_raw_working_profile: bool = False,
                        raw_profile_path: Optional[str] = None) -> dict:
        """Send ONE market open order with full fallback + diagnostics.

        Sprint 9.9.3.19 patch — adds demo_micro kwarg for broker compat fallback.
        Sprint 9.9.3.21 patch — adds use_raw_working_profile kwarg. When True,
        the adapter loads raw_mt5_working_profile.json and mirrors the exact
        request shape that succeeded on this broker (IOC naked order + SLTP
        modify after open). This bypasses the normal filling-mode fallback
        and goes straight to the raw-compatible path.

        Returns result dict (see _send_with_fallback for shape).
        Never raises. Never sends more than ONE order per call.
        """
        # Build broker state snapshot for diagnostics + profile.
        snapshot = self.snapshot_broker_state(symbol, magic)
        self._log("ADAPTER_BROKER_STATE_SNAPSHOT", {"label": "open", **snapshot})

        # Pre-check: no existing position for this symbol+magic.
        if snapshot["open_positions"]["count"] > 0:
            self._log("ADAPTER_DUPLICATE_BLOCKED", {
                "label": "open", "symbol": symbol,
                "existing_tickets": snapshot["open_positions"]["tickets"],
                "reason": "position already open for this symbol+magic",
            })
            return {
                "ok": False,
                "retcode": None,
                "error": "duplicate order blocked — position already open",
                "filling_mode_selected": None,
                "filling_type_used": None,
                "filling_source": None,
                "check_attempts": [],
                "send_attempts": [],
                "position_detected_after_failure": snapshot["open_positions"],
                "emergency_close_required": False,
                "broker_snapshot": snapshot,
            }

        # Sprint 9.9.3.21 — raw working profile path.
        # If use_raw_working_profile=True and a raw profile exists, use the
        # raw-compatible execution flow (naked IOC + SLTP modify).
        if use_raw_working_profile:
            raw_profile = self._load_raw_working_profile(raw_profile_path)
            if raw_profile is not None:
                self._log("ADAPTER_RAW_WORKING_PROFILE_MODE", {
                    "symbol": symbol,
                    "raw_profile_server": raw_profile.get("server"),
                    "reason": "using raw working profile — naked IOC + SLTP modify",
                })
                result = self._send_raw_compatible_open(
                    symbol, side, lot, magic, deviation, comment,
                    snapshot, raw_profile,
                )
                # Write broker execution profile.
                verdict = ("SUCCESS" if result.get("ok")
                           else "EMERGENCY_CLOSE_REQUIRED" if result.get("emergency_close_required")
                           else "FAIL")
                self.write_broker_profile(snapshot, label="open", verdict=verdict,
                                           result=result)
                return result
            else:
                self._log("ADAPTER_RAW_PROFILE_NOT_FOUND", {
                    "symbol": symbol,
                    "reason": ("use_raw_working_profile=True but no profile found — "
                               "falling back to normal filling-mode fallback"),
                })

        # Get list of supported filling modes (filtered by trade_execution).
        supported_modes = self._list_supported_filling_modes(symbol)
        if not supported_modes:
            self._log("ADAPTER_NO_SUPPORTED_FILLING_MODE", {
                "label": "open", "symbol": symbol,
                "filling_mode_raw": snapshot["symbol_info"].get("filling_mode"),
                "trade_execution": snapshot["symbol_info"].get("trade_exemode"),
            })
            self.write_broker_profile(snapshot, label="open",
                                       verdict="FAIL_NO_FILLING_MODE")
            return {
                "ok": False,
                "retcode": None,
                "error": "no supported filling mode detected",
                "filling_mode_selected": None,
                "filling_type_used": None,
                "filling_source": None,
                "check_attempts": [],
                "send_attempts": [],
                "position_detected_after_failure": snapshot["open_positions"],
                "emergency_close_required": False,
                "broker_snapshot": snapshot,
            }

        # Initial tick (will be refreshed per attempt in _send_with_fallback).
        tick = self._refresh_tick(symbol)
        if tick is None:
            self._log("ADAPTER_NO_TICK", {"label": "open", "symbol": symbol})
            self.write_broker_profile(snapshot, label="open", verdict="FAIL_NO_TICK")
            return {
                "ok": False,
                "retcode": None,
                "error": "no tick available for symbol",
                "filling_mode_selected": None,
                "filling_type_used": None,
                "filling_source": None,
                "check_attempts": [],
                "send_attempts": [],
                "position_detected_after_failure": snapshot["open_positions"],
                "emergency_close_required": False,
                "broker_snapshot": snapshot,
            }

        # Build base request (type_filling set per-attempt).
        base_request = self._build_open_request(
            symbol, side, lot, magic, deviation, comment, tick,
        )

        # Emit pre-send diagnostics.
        self._log("ADAPTER_PRE_SEND_DIAGNOSTICS", {
            "label": "open",
            "symbol": symbol,
            "side": side,
            "lot": lot,
            "magic": magic,
            "supported_filling_modes": [m["filling_name"] for m in supported_modes],
            "base_request": _safe_request(base_request),
            "broker_snapshot": snapshot,
        })

        # Send with fallback.
        result = self._send_with_fallback(base_request, supported_modes, label="open")
        result["broker_snapshot"] = snapshot

        # Sprint 9.9.3.19 patch — broker compatibility fallback.
        # If the protected order was rejected by a MARKET-execution broker
        # and we're in demo_micro mode, try the two-step naked order approach.
        if (not result.get("ok") and demo_micro
                and self._should_try_naked_fallback(result, snapshot)):
            self._log("ADAPTER_BROKER_COMPATIBILITY_FALLBACK_TRIGGERED", {
                "symbol": symbol,
                "reason": ("protected order rejected by MARKET-execution broker — "
                           "attempting naked order + SLTP modify fallback"),
            })
            result = self._try_naked_order_fallback(
                base_request, supported_modes, snapshot, result,
            )
            result["broker_snapshot"] = snapshot

        # Write broker execution profile.
        verdict = ("SUCCESS" if result.get("ok")
                   else "EMERGENCY_CLOSE_REQUIRED" if result.get("emergency_close_required")
                   else "FAIL")
        self.write_broker_profile(snapshot, label="open", verdict=verdict,
                                   result=result)
        return result

    def send_close_order(self, position: dict, magic: int,
                         deviation: int = 20,
                         comment: str = "TITAN_DEMO_MICRO_CLOSE") -> dict:
        """Close an open position with opposite-side market order.

        Same fallback logic as send_open_order, but the request includes
        a 'position' field (the ticket to close).
        """
        symbol = position["symbol"]
        snapshot = self.snapshot_broker_state(symbol, magic)
        self._log("ADAPTER_BROKER_STATE_SNAPSHOT", {"label": "close", **snapshot})

        supported_modes = self._list_supported_filling_modes(symbol)
        if not supported_modes:
            self.write_broker_profile(snapshot, label="close",
                                       verdict="FAIL_NO_FILLING_MODE")
            return {
                "ok": False,
                "retcode": None,
                "error": "no supported filling mode detected (close)",
                "filling_mode_selected": None,
                "check_attempts": [],
                "send_attempts": [],
                "emergency_close_required": False,
                "broker_snapshot": snapshot,
            }

        tick = self._refresh_tick(symbol)
        if tick is None:
            self.write_broker_profile(snapshot, label="close", verdict="FAIL_NO_TICK")
            return {
                "ok": False,
                "retcode": None,
                "error": "no tick available for symbol (close)",
                "filling_mode_selected": None,
                "check_attempts": [],
                "send_attempts": [],
                "emergency_close_required": False,
                "broker_snapshot": snapshot,
            }

        base_request = self._build_close_request(
            position, magic, deviation, comment, tick,
        )

        self._log("ADAPTER_PRE_SEND_DIAGNOSTICS", {
            "label": "close",
            "symbol": symbol,
            "position_ticket": position["ticket"],
            "supported_filling_modes": [m["filling_name"] for m in supported_modes],
            "base_request": _safe_request(base_request),
            "broker_snapshot": snapshot,
        })

        result = self._send_with_fallback(base_request, supported_modes, label="close")
        result["broker_snapshot"] = snapshot
        verdict = ("SUCCESS" if result.get("ok")
                   else "EMERGENCY_CLOSE_REQUIRED" if result.get("emergency_close_required")
                   else "FAIL")
        self.write_broker_profile(snapshot, label="close", verdict=verdict,
                                   result=result)
        return result

    # ─── Broker execution profile ───────────────────────────────────────────

    def _extract_last_error_from_attempts(self, send_attempts: list) -> Optional[dict]:
        """Sprint 9.9.3.18 patch — extract mt5.last_error from the first
        send attempt that returned None.

        Returns a dict with code + message, or None if no None-result
        attempt occurred.
        """
        for a in send_attempts:
            if a.get("order_send_returned_none"):
                return {
                    "code": a.get("mt5_last_error_code"),
                    "message": a.get("mt5_last_error_message"),
                }
        return None

    def write_broker_profile(self, snapshot: dict, label: str,
                              verdict: str, result: Optional[dict] = None) -> None:
        """Write broker_execution_profile.json for operator review.

        Overwrites the file with the latest execution attempt's profile.
        Includes: broker snapshot, supported filling modes, all check/send
        attempts, final verdict, and selected filling mode.
        """
        try:
            # Re-derive supported modes from snapshot (for the profile).
            mask = snapshot.get("symbol_info", {}).get("filling_mode")
            trade_exec = snapshot.get("symbol_info", {}).get("trade_exemode")
            modes_in_snapshot = []
            if mask is not None:
                # Sprint 9.9.3.20 — use _FILLING_MODES (dict-based) not
                # the old _FILLING_PREFERENCE (tuple-based, removed).
                order_consts = self._get_order_filling_constants()
                for mode_desc in _FILLING_MODES:
                    name = mode_desc["name"]
                    symbol_flag = mode_desc["symbol_flag"]
                    order_enum = order_consts.get(name, mode_desc["order_enum_default"])
                    if symbol_flag is not None:
                        # FOK / IOC — check bitmask flag
                        if not (mask & symbol_flag):
                            continue
                    else:
                        # RETURN — not flag-based
                        pass
                    if (name == "RETURN"
                            and trade_exec is not None
                            and trade_exec not in _TRADE_EXECUTIONS_THAT_ALLOW_RETURN):
                        modes_in_snapshot.append({
                            "filling_name": name,
                            "symbol_filling_flag": symbol_flag,
                            "order_filling_type": order_enum,
                            "in_bitmask": symbol_flag is not None,
                            "filtered_out_by_trade_execution": True,
                            "trade_execution": trade_exec,
                        })
                    else:
                        modes_in_snapshot.append({
                            "filling_name": name,
                            "symbol_filling_flag": symbol_flag,
                            "order_filling_type": order_enum,
                            "in_bitmask": symbol_flag is not None and bool(mask & symbol_flag),
                            "filtered_out_by_trade_execution": False,
                        })

            profile = {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "label": label,
                "verdict": verdict,
                "broker_snapshot": snapshot,
                "filling_modes_in_bitmask": modes_in_snapshot,
                "check_attempts": (result or {}).get("check_attempts", []),
                "send_attempts": (result or {}).get("send_attempts", []),
                "filling_mode_selected": (result or {}).get("filling_mode_selected"),
                "filling_source": (result or {}).get("filling_source"),
                "emergency_close_required": (result or {}).get("emergency_close_required", False),
                "retcode": (result or {}).get("retcode"),
                # Sprint 9.9.3.18 patch — None-result diagnostics in profile
                "order_send_returned_none": any(
                    a.get("order_send_returned_none", False)
                    for a in (result or {}).get("send_attempts", [])
                ),
                "mt5_last_error": self._extract_last_error_from_attempts(
                    (result or {}).get("send_attempts", [])
                ),
            }
            # Ensure dir exists
            Path(self._profile_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self._profile_path, "w", encoding="utf-8") as f:
                json.dump(profile, f, indent=2, default=_to_jsonable)
        except Exception as e:
            # Profile write failure is non-fatal — log and continue.
            self._log("ADAPTER_PROFILE_WRITE_FAILED", {
                "error": str(e), "profile_path": self._profile_path,
            })


# ─── Module-level helpers (re-exported for backward compat) ──────────────────

def _safe_request(req: dict) -> dict:
    """Make request JSON-serializable."""
    safe = {}
    for k, v in req.items():
        safe[k] = _to_jsonable(v)
    return safe
