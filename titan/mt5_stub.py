"""
MetaTrader5 mock for Linux development/testing.
Provides the same interface as the real MetaTrader5 package.

Sprint 9.9.3.45.5: Extended with history_deals_get / history_orders_get
and richer _OrderResult / _Position fields so truthfulness tests can
exercise receipt mapping, position detection, and forensics matching
without contacting a real broker.

Tests can monkeypatch the module-level _POSITIONS, _HISTORY_DEALS,
_HISTORY_ORDERS, _ORDER_RESULT lists/dict to inject scenarios. No test
ever calls order_send against a real broker.
"""
# Order types
ORDER_TYPE_BUY = 0
ORDER_TYPE_SELL = 1
ORDER_TYPE_BUY_LIMIT = 2
ORDER_TYPE_SELL_LIMIT = 3
ORDER_TYPE_BUY_STOP = 4
ORDER_TYPE_SELL_STOP = 5

# Position types
POSITION_TYPE_BUY = 0
POSITION_TYPE_SELL = 1

# Trade actions
TRADE_ACTION_DEAL = 1
TRADE_ACTION_PENDING = 5
TRADE_ACTION_REMOVE = 3
TRADE_ACTION_SLTP = 6  # Sprint 9.9.3.45.6: SL/TP modify action

# Filling modes
ORDER_FILLING_IOC = 1
ORDER_FILLING_FOK = 0
ORDER_FILLING_RETURN = 2

# Order time
ORDER_TIME_GTC = 0

# Return codes
TRADE_RETCODE_DONE = 10009
TRADE_RETCODE_DONE_PARTIAL = 10010
TRADE_RETCODE_PLACED = 10008
TRADE_RETCODE_REQUOTE = 10004
TRADE_RETCODE_REJECT = 10006
TRADE_RETCODE_CANCELLED = 10018

_initialized = False
_last_error = (1, "No error")

# Module-level mutable state - tests can monkeypatch these.
_POSITIONS: list = []
_HISTORY_DEALS: list = []
_HISTORY_ORDERS: list = []
_ORDER_RESULT: dict = {
    "retcode": TRADE_RETCODE_DONE,
    "comment": "TRADE_RETCODE_DONE",
    "order": 0,
    "deal": 0,
    "position_id": 0,
    "volume": 0.01,
    "price": 2000.10,
    "bid": 2000.00,
    "ask": 2000.18,
    "request_id": 0,
    "retcode_external": 0,
}
# Sprint 9.9.3.45.6: order_modify result and call tracking
_ORDER_MODIFY_RESULT: dict = {
    "retcode": TRADE_RETCODE_DONE,
    "comment": "TRADE_RETCODE_DONE",
}
_ORDER_SEND_CALLS: list = []
_ORDER_MODIFY_CALLS: list = []


def _reset_state():
    """Reset all mutable state. Tests should call this in setup."""
    global _POSITIONS, _HISTORY_DEALS, _HISTORY_ORDERS, _ORDER_RESULT
    global _ORDER_MODIFY_RESULT, _ORDER_SEND_CALLS, _ORDER_MODIFY_CALLS
    global _initialized, _last_error
    _POSITIONS = []
    _HISTORY_DEALS = []
    _HISTORY_ORDERS = []
    _ORDER_RESULT = {
        "retcode": TRADE_RETCODE_DONE,
        "comment": "TRADE_RETCODE_DONE",
        "order": 0,
        "deal": 0,
        "position_id": 0,
        "volume": 0.01,
        "price": 2000.10,
        "bid": 2000.00,
        "ask": 2000.18,
        "request_id": 0,
        "retcode_external": 0,
    }
    _ORDER_MODIFY_RESULT = {
        "retcode": TRADE_RETCODE_DONE,
        "comment": "TRADE_RETCODE_DONE",
    }
    _ORDER_SEND_CALLS = []
    _ORDER_MODIFY_CALLS = []
    _initialized = False
    _last_error = (1, "No error")


class _TerminalInfo:
    def __init__(self):
        self.company = "MetaQuotes Software Corp."
        self.name = "MetaQuotes-Demo"
        self.trade_allowed = True


class _AccountInfo:
    def __init__(self):
        self.balance = 10000.0
        self.equity = 10000.0
        self.margin = 0.0
        self.margin_level = 999.0
        self.profit = 0.0
        self.currency = "USD"
        self.leverage = 500
        self.server = "MetaQuotes-Demo"
        self.login = 12345678
        self.trade_mode = 0  # 0 = DEMO


class _SymbolInfo:
    def __init__(self, name="XAUUSD"):
        self.name = name
        self.digits = 2
        self.point = 0.01
        self.spread = 18
        self.trade_contract_size = 100
        self.volume_min = 0.01
        self.volume_max = 100.0
        self.volume_step = 0.01
        self.trade_mode = 4
        self.visible = True


class _TickInfo:
    def __init__(self):
        self.bid = 2000.00
        self.ask = 2000.18
        self.time = 1700000000
        self.time_msc = 1700000000000
        self.volume = 100
        self.flags = 2


class _OrderResult:
    """Mock of MqlTradeResult.

    Sprint 9.9.3.45.5: Fields mirror the real MT5 SendResult object so
    receipt-capture code can exercise every safe field. ``order`` and
    ``deal`` default to 0 to simulate the operator's bug case where
    retcode=10009 but order/deal were zero/missing.
    """
    def __init__(self):
        cfg = _ORDER_RESULT or {}
        self.retcode = cfg.get("retcode", TRADE_RETCODE_DONE)
        self.comment = cfg.get("comment", "TRADE_RETCODE_DONE")
        self.order = cfg.get("order", 0)
        self.deal = cfg.get("deal", 0)
        self.position_id = cfg.get("position_id", 0)
        self.volume = cfg.get("volume", 0.01)
        self.price = cfg.get("price", 2000.10)
        self.bid = cfg.get("bid", 2000.00)
        self.ask = cfg.get("ask", 2000.18)
        self.request_id = cfg.get("request_id", 0)
        self.retcode_external = cfg.get("retcode_external", 0)


class _OrderModifyResult:
    """Sprint 9.9.3.45.6: Mock of MqlTradeResult for order_modify.

    Tests can override _ORDER_MODIFY_RESULT to simulate success or
    failure of SL modification.
    """
    def __init__(self):
        cfg = _ORDER_MODIFY_RESULT or {}
        self.retcode = cfg.get("retcode", TRADE_RETCODE_DONE)
        self.comment = cfg.get("comment", "TRADE_RETCODE_DONE")
        self.order = cfg.get("order", 0)
        self.volume = cfg.get("volume", 0.01)
        self.price = cfg.get("price", 0.0)
        self.bid = cfg.get("bid", 0.0)
        self.ask = cfg.get("ask", 0.0)


class _Position:
    """Mock of MqlTradePosition.

    Sprint 9.9.3.45.5: ticket and identifier are distinct. ``identifier``
    is the original position id assigned at open; ``ticket`` may change
    if the position is partially closed. Tests can construct positions
    with specific ticket/identifier/magic/comment to drive detection
    and forensics scenarios.
    """
    def __init__(self, ticket=1001, identifier=None, magic=202619,
                 comment="TITAN_DEMO_MICRO", symbol="XAUUSD",
                 type_=POSITION_TYPE_BUY, volume=0.01,
                 price_open=2000.0, price_current=2000.0,
                 sl=0.0, tp=0.0):
        self.ticket = ticket
        self.identifier = identifier if identifier is not None else ticket
        self.symbol = symbol
        self.type = type_
        self.volume = volume
        self.magic = magic
        self.comment = comment
        self.price_open = price_open
        self.price_current = price_current
        self.sl = sl
        self.tp = tp
        self.time = 1700000000
        self.time_msc = 1700000000000


class _HistoryDeal:
    """Mock of MqlDeal for history_deals_get."""
    def __init__(self, ticket=50001, order=60001, position_id=1001,
                 magic=202619, comment="TITAN_DEMO_MICRO", symbol="XAUUSD",
                 type_=0, entry=0, price=2000.0, profit=0.0, volume=0.01,
                 time=1700000000):
        self.ticket = ticket
        self.order = order
        self.position_id = position_id
        self.magic = magic
        self.comment = comment
        self.symbol = symbol
        self.type = type_
        self.entry = entry  # 0=IN, 1=OUT, 2=INOUT, 3=OUT_BY
        self.price = price
        self.profit = profit
        self.volume = volume
        self.time = time


class _HistoryOrder:
    """Mock of MqlOrder for history_orders_get."""
    def __init__(self, ticket=60001, position_id=1001, magic=202619,
                 comment="TITAN_DEMO_MICRO", symbol="XAUUSD", type_=0,
                 sl=0.0, tp=0.0, price=2000.0, volume_initial=0.01,
                 time_setup=1700000000, time_done=1700000010):
        self.ticket = ticket
        self.position_id = position_id
        self.magic = magic
        self.comment = comment
        self.symbol = symbol
        self.type = type_
        self.sl = sl
        self.tp = tp
        self.price = price
        self.volume_initial = volume_initial
        self.time_setup = time_setup
        self.time_done = time_done


def initialize(path=None, login=0, password="", server="", timeout=60000):
    global _initialized, _last_error
    _initialized = True
    _last_error = (1, "No error")
    return True


def shutdown():
    global _initialized
    _initialized = False


def last_error():
    return _last_error


def terminal_info():
    if not _initialized:
        return None
    return _TerminalInfo()


def account_info():
    if not _initialized:
        return None
    return _AccountInfo()


def symbol_info(symbol):
    if not _initialized:
        return None
    return _SymbolInfo(symbol)


def symbol_info_tick(symbol):
    if not _initialized:
        return None
    return _TickInfo()


def symbol_select(symbol, visible=True):
    return True


def symbols_get(pattern=""):
    if not _initialized:
        return None
    return [_SymbolInfo("XAUUSD"), _SymbolInfo("XAUUSD.c")]


def order_send(request):
    if not _initialized:
        return None
    _ORDER_SEND_CALLS.append(request)
    return _OrderResult()


def order_modify(request):
    """Sprint 9.9.3.45.6: Mock of mt5.order_modify.

    Tracks call so tests can assert it was/was not called. Returns
    _OrderModifyResult populated from _ORDER_MODIFY_RESULT.
    """
    if not _initialized:
        return None
    _ORDER_MODIFY_CALLS.append(request)
    return _OrderModifyResult()


def positions_get(ticket=None, symbol=None):
    """Return all positions, or filter by ticket/symbol.

    Tests can populate _POSITIONS to simulate open positions.
    """
    if not _initialized:
        return None
    if ticket is not None:
        for p in _POSITIONS:
            if getattr(p, "ticket", 0) == ticket:
                return [p]
        return ()  # MT5 returns empty tuple when no match
    if symbol is not None:
        return tuple(p for p in _POSITIONS if getattr(p, "symbol", "") == symbol)
    return tuple(_POSITIONS)


def history_deals_get(from_dt, to_dt):
    """Return deals in time window. Tests populate _HISTORY_DEALS."""
    if not _initialized:
        return None
    from_ts = int(getattr(from_dt, "timestamp", lambda: 0)()) if from_dt else 0
    to_ts = int(getattr(to_dt, "timestamp", lambda: 0)()) if to_dt else 0
    out = []
    for d in _HISTORY_DEALS:
        t = getattr(d, "time", 0)
        if from_ts <= t <= to_ts:
            out.append(d)
    return tuple(out)


def history_orders_get(from_dt, to_dt):
    """Return orders in time window. Tests populate _HISTORY_ORDERS."""
    if not _initialized:
        return None
    from_ts = int(getattr(from_dt, "timestamp", lambda: 0)()) if from_dt else 0
    to_ts = int(getattr(to_dt, "timestamp", lambda: 0)()) if to_dt else 0
    out = []
    for o in _HISTORY_ORDERS:
        t = getattr(o, "time_done", getattr(o, "time_setup", 0))
        if from_ts <= t <= to_ts:
            out.append(o)
    return tuple(out)
