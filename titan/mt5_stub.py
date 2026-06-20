"""
MetaTrader5 mock for Linux development/testing.
Provides the same interface as the real MetaTrader5 package.
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

# Filling modes
ORDER_FILLING_IOC = 1
ORDER_FILLING_FOK = 0
ORDER_FILLING_RETURN = 2

# Return codes
TRADE_RETCODE_DONE = 10009
TRADE_RETCODE_DONE_PARTIAL = 10010
TRADE_RETCODE_PLACED = 10008
TRADE_RETCODE_REQUOTE = 10004
TRADE_RETCODE_REJECT = 10006
TRADE_RETCODE_CANCELLED = 10018

_initialized = False
_last_error = (1, "No error")


class _TerminalInfo:
    def __init__(self):
        self.company = "IC Markets"
        self.name = "ICMarketsSC-Live06"
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
    def __init__(self, retcode=TRADE_RETCODE_DONE):
        self.retcode = retcode
        self.deal = 12345
        self.order = 67890
        self.volume = 0.10
        self.price = 2000.10
        self.bid = 2000.00
        self.ask = 2000.18
        self.comment = "TITAN"
        self.request_id = 1
        self.result_id = 1


class _Position:
    def __init__(self, ticket=1001):
        self.ticket = ticket
        self.symbol = "XAUUSD"
        self.type = POSITION_TYPE_BUY
        self.volume = 0.10
        self.magic = 202619


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
    return _OrderResult()


def positions_get(ticket=None):
    if not _initialized:
        return None
    if ticket is not None:
        return None  # No positions by default
    return []  # Empty positions
