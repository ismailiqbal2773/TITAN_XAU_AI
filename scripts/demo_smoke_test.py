"""
TITAN XAU AI — Demo Smoke Test (Sprint 5)

End-to-end verification that the system can:
  1. Load models (xgboost_v1 + meta_label_v2_context)
  2. Generate features from canonical H1 data
  3. Run inference (XGB → meta-label)
  4. Pass risk gate
  5. Create a dry-run order
  6. Write journal record
  7. Check kill-switch state

CRITICAL: This script NEVER places a real order. dry_run=True is enforced.

Usage:
    python scripts/demo_smoke_test.py
    python scripts/demo_smoke_test.py --config config/runtime.yaml
    python scripts/demo_smoke_test.py --verbose
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

logger = logging.getLogger("titan.smoke_test")


class SmokeTestResult:
    """Single test step result."""
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error: str | None = None
        self.details: dict = {}
        self.duration_ms: float = 0.0

    def __repr__(self) -> str:
        status = "✓ PASS" if self.passed else "✗ FAIL"
        return f"{status} {self.name} ({self.duration_ms:.1f}ms)"


async def run_smoke_test(config_path: str | None = None, verbose: bool = False) -> bool:
    """
    Run full smoke test. Returns True iff all steps pass.
    """
    print("=" * 70)
    print("TITAN XAU AI — Demo Smoke Test")
    print("=" * 70)
    print(f"Repository: {REPO_ROOT}")
    print(f"Mode: dry_run (NO real orders)")
    print()

    results: list[SmokeTestResult] = []

    # ─── STEP 1: Load Models ───
    r = SmokeTestResult("Model Load")
    t0 = time.perf_counter()
    try:
        from titan.production.model_loader import load_production_models
        bundle = load_production_models()
        r.passed = bundle.ok
        r.details = {
            "xgb_loaded": bundle.xgb is not None,
            "meta_loaded": bundle.meta is not None,
            "xgb_n_features": bundle.xgb_n_features,
            "meta_n_features": bundle.meta_n_features,
            "xgb_verified": bundle.xgb_verified,
            "meta_verified": bundle.meta_verified,
        }
        if not r.passed:
            r.error = f"Model load failed: {bundle.errors}"
    except Exception as e:
        r.error = str(e)
    r.duration_ms = (time.perf_counter() - t0) * 1000
    results.append(r)
    print(f"  {r}")
    if verbose and r.details:
        for k, v in r.details.items():
            print(f"      {k}: {v}")

    if not r.passed:
        return _print_summary(results)

    # ─── STEP 2: Feature Stream ───
    r = SmokeTestResult("Feature Stream")
    t0 = time.perf_counter()
    try:
        from titan.production.feature_stream import H1FeatureStream, N_FEATURES
        fs = H1FeatureStream(window=300)
        n_bars = fs.load_canonical()
        vec = fs.latest_vector(source="canonical")
        r.passed = vec.is_valid and vec.features.shape == (N_FEATURES,)
        r.details = {
            "bars_loaded": n_bars,
            "feature_shape": vec.features.shape,
            "timestamp": str(vec.timestamp),
            "any_nan": bool(__import__("numpy").isnan(vec.features).any()),
            "any_inf": bool(__import__("numpy").isinf(vec.features).any()),
        }
        if not r.passed:
            r.error = f"Feature stream invalid: {vec.error}"
    except Exception as e:
        r.error = str(e)
    r.duration_ms = (time.perf_counter() - t0) * 1000
    results.append(r)
    print(f"  {r}")
    if verbose and r.details:
        for k, v in r.details.items():
            print(f"      {k}: {v}")

    if not r.passed:
        return _print_summary(results)

    # ─── STEP 3: Inference ───
    r = SmokeTestResult("Inference (XGB + Meta-Label)")
    t0 = time.perf_counter()
    try:
        from titan.production.inference import InferenceEngine
        engine = InferenceEngine()
        signal = engine.generate(source="canonical")
        r.passed = signal is not None and signal.feature_vector is not None
        r.details = {
            "direction": signal.direction.name,
            "confidence": round(signal.confidence, 4),
            "meta_confidence": round(signal.meta_confidence, 4),
            "is_tradeable": signal.is_tradeable,
            "xgb_proba": [round(p, 4) for p in signal.xgb_proba],
            "meta_proba": [round(p, 4) for p in signal.meta_proba],
            "inference_ms": round(signal.inference_ms, 2),
        }
    except Exception as e:
        r.error = str(e)
    r.duration_ms = (time.perf_counter() - t0) * 1000
    results.append(r)
    print(f"  {r}")
    if verbose and r.details:
        for k, v in r.details.items():
            print(f"      {k}: {v}")

    if not r.passed:
        return _print_summary(results)

    # ─── STEP 4: Risk Gate ───
    r = SmokeTestResult("Risk Gate (dry_run order creation)")
    t0 = time.perf_counter()
    try:
        from titan.production.trade_loop import TradeLoop, TradeLoopConfig
        from titan.production.trade_journal import TradeJournal
        from titan.production.kill_switch_fsm import KillSwitchFSM

        # Use temp journal
        import tempfile
        journal_path = tempfile.mktemp(suffix=".jsonl")
        journal = TradeJournal(path=journal_path)
        fsm = KillSwitchFSM(journal_callback=lambda t: journal.log_heartbeat({
            "event": "kill_switch_transition",
            "to": t.to_state.value,
        }))

        loop = TradeLoop(
            TradeLoopConfig(dry_run=True),  # MANDATORY
            journal=journal,
            kill_switch=fsm,
        )
        decision = await loop.process_signal(
            signal=signal, entry_price=2000.0, spread_usd=0.20,
        )
        r.passed = decision.dry_run is True  # dry_run enforced
        r.details = {
            "accepted": decision.accepted,
            "dry_run": decision.dry_run,
            "reject_reason": decision.reject_reason,
            "kill_switch_state": fsm.state.value,
            "order_request": decision.order_request,
        }
        if decision.accepted:
            # Verify SL/TP present
            req = decision.order_request
            r.details["has_sl"] = req.get("sl", 0) > 0
            r.details["has_tp"] = req.get("tp", 0) > 0
            r.details["volume"] = req.get("volume", 0)
            r.passed = r.details["has_sl"] and r.details["has_tp"] and r.details["volume"] <= 0.01
        journal.flush()
        # Clean up
        try:
            os.unlink(journal_path)
        except:
            pass
    except Exception as e:
        r.error = str(e)
    r.duration_ms = (time.perf_counter() - t0) * 1000
    results.append(r)
    print(f"  {r}")
    if verbose and r.details:
        for k, v in r.details.items():
            if k != "order_request":
                print(f"      {k}: {v}")

    # ─── STEP 5: Journal Write ───
    r = SmokeTestResult("Journal Write")
    t0 = time.perf_counter()
    try:
        import tempfile
        journal_path = tempfile.mktemp(suffix=".jsonl")
        journal = TradeJournal(path=journal_path)
        journal.log_signal(signal)
        journal.log_decision(decision)
        if decision.accepted:
            journal.log_order(decision)
        journal.flush()
        records = journal.read_all()
        r.passed = len(records) >= 2  # at least SIGNAL + DECISION
        r.details = {
            "records_written": len(records),
            "record_types": [r["record_type"] for r in records],
            "file_size_bytes": journal.file_size_bytes,
        }
        try:
            os.unlink(journal_path)
        except:
            pass
    except Exception as e:
        r.error = str(e)
    r.duration_ms = (time.perf_counter() - t0) * 1000
    results.append(r)
    print(f"  {r}")
    if verbose and r.details:
        for k, v in r.details.items():
            print(f"      {k}: {v}")

    # ─── STEP 6: Kill-Switch Check ───
    r = SmokeTestResult("Kill-Switch Check")
    t0 = time.perf_counter()
    try:
        from titan.production.kill_switch_fsm import KillSwitchFSM, KillSwitchInput, KillState
        fsm = KillSwitchFSM()
        r.details = {
            "initial_state": fsm.state.value,
            "allows_new_trades": fsm.allows_new_trades,
            "requires_flatten": fsm.requires_flatten,
            "is_emergency": fsm.is_emergency,
        }
        # Verify kill-switch can escalate
        fsm.update(KillSwitchInput(daily_loss_pct=3.5))
        r.details["after_daily_loss_3.5"] = fsm.state.value
        r.passed = (fsm.state == KillState.HALT_NEW_TRADES and
                    not fsm.allows_new_trades)
    except Exception as e:
        r.error = str(e)
    r.duration_ms = (time.perf_counter() - t0) * 1000
    results.append(r)
    print(f"  {r}")
    if verbose and r.details:
        for k, v in r.details.items():
            print(f"      {k}: {v}")

    # ─── STEP 7: No Real Order Verification ───
    r = SmokeTestResult("No Real Order (mt5.order_send NOT called)")
    t0 = time.perf_counter()
    try:
        # In dry_run, ExecutionEngine.place_order is never called.
        # Verify by checking that decision.order_result is None (no submission).
        loop = TradeLoop(TradeLoopConfig(dry_run=True))
        sig = engine.generate(source="canonical")
        decision = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
        # dry_run means no order_result, no mt5 call
        r.passed = decision.dry_run is True and decision.order_result is None
        r.details = {
            "dry_run": decision.dry_run,
            "order_result_is_none": decision.order_result is None,
            "accepted": decision.accepted,
        }
    except Exception as e:
        r.error = str(e)
    r.duration_ms = (time.perf_counter() - t0) * 1000
    results.append(r)
    print(f"  {r}")

    return _print_summary(results)


def _print_summary(results: list[SmokeTestResult]) -> bool:
    """Print final summary. Returns True iff all passed."""
    print()
    print("=" * 70)
    print("SMOKE TEST SUMMARY")
    print("=" * 70)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total = len(results)
    print(f"  Total steps: {total}")
    print(f"  Passed:      {passed}")
    print(f"  Failed:      {failed}")
    print()
    if failed > 0:
        print("FAILED STEPS:")
        for r in results:
            if not r.passed:
                print(f"  ✗ {r.name}: {r.error}")
    print()
    if failed == 0:
        print("✓ ALL SMOKE TEST STEPS PASSED")
        print("✓ System is demo-ready (dry_run mode)")
        print("✓ No real orders were placed")
        return True
    else:
        print("✗ SMOKE TEST FAILED — do not proceed to demo")
        return False


def main():
    parser = argparse.ArgumentParser(description="TITAN Demo Smoke Test")
    parser.add_argument("--config", default=None, help="Path to runtime.yaml")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    success = asyncio.run(run_smoke_test(args.config, args.verbose))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
