"""
conftest.py — Injects MT5 mock for Linux testing.
On Windows with real MT5 installed, this is skipped.
"""
import sys

try:
    import MetaTrader5  # noqa
except ImportError:
    # Linux/dev environment — use mock
    from titan import mt5_stub
    sys.modules['MetaTrader5'] = mt5_stub
    print("[conftest] Using MT5 mock for non-Windows testing")
