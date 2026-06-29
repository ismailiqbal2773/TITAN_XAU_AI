"""
TITAN XAU AI — Backward-compatible wrapper for demo_micro_full_cycle.py
=======================================================================

Sprint 9.9.3.22 — this file has been renamed to demo_micro_full_cycle.py
(broker-agnostic). This wrapper preserves backward compatibility for
scripts and docs that still import from the old path.

All imports, function calls, and CLI behavior are delegated to the new
module. A deprecation warning is printed on import.

Usage:
    # OLD (deprecated, still works):
    python scripts/audit/fundednext_demo_micro_full_cycle.py --mode DRY_ARM_CHECK_ONLY

    # NEW (recommended):
    python scripts/audit/demo_micro_full_cycle.py --mode DRY_ARM_CHECK_ONLY
"""
from __future__ import annotations
import sys
import warnings

# Sprint 9.9.3.22 — emit DeprecationWarning on import
warnings.warn(
    "scripts.audit.fundednext_demo_micro_full_cycle has been renamed to "
    "scripts.audit.demo_micro_full_cycle. Please update your imports. "
    "This backward-compatible wrapper will be removed in a future sprint.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from the new module
from scripts.audit.demo_micro_full_cycle import *  # noqa: F401, F403
from scripts.audit.demo_micro_full_cycle import (  # noqa: F401
    parse_args, run, main, _run_execute, _send_open_order, _close_position,
    _get_mt5, _is_demo_account, _resolve_side, _load_latest_ai_signal,
    _check_existing_position, _safe_request, _safe_position,
    _sync_position, _journal_event, _save_report, _build_order_diagnostics,
    _attempt_filling_modes, _select_filling_mode, _list_supported_filling_modes,
    _lookup_retcode_meaning, _TRADE_ACTION_DEAL, _ORDER_TYPE_BUY,
    _ORDER_TYPE_SELL, _TRADE_RETCODE_DONE, DEMO_MICRO_MAGIC,
    JOURNAL_PATH, OUTPUT_DIR, REPO_ROOT,
)

# Also re-export the module-level constants that tests import
from scripts.audit.demo_micro_full_cycle import (  # noqa: F401
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_BOC,
    ORDER_FILLING_RETURN, _SYMBOL_FILLING_FOK_BIT, _SYMBOL_FILLING_IOC_BIT,
    _SYMBOL_FILLING_BOC_BIT, _FILLING_PREFERENCE, _DEFAULT_FILLING_MASK,
    _RETCODE_MEANINGS, _TRADE_RETCODE_CHECK_PASSED, _RETCODE_0_MEANING,
    _TRADE_RETCODE_REJECT, _RETCODE_10006_MEANING,
    _TRADE_RETCODE_AUTOTRADING_DISABLED, _RETCODE_10027_MEANING,
    _TRADE_RETCODE_INVALID_FILL, _RETCODE_10030_MEANING,
)


if __name__ == "__main__":
    # When run directly, delegate to the new module's main()
    print("⚠ DEPRECATION WARNING: This script has been renamed to "
          "demo_micro_full_cycle.py. Please use the new path.", file=sys.stderr)
    from scripts.audit.demo_micro_full_cycle import main as _new_main
    sys.exit(_new_main())
