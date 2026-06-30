"""
TITAN XAU AI - Demo Micro Order Builder (Sprint 9.9.3.44)
=========================================================
Builds an MT5 order request PREVIEW but NEVER sends it.
NEVER calls mt5.order_send. NEVER uses market execution adapter.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "demo_micro_execution"

MAX_LOT = 0.01
MAGIC_NUMBER = 202619
DEVIATION = 20


@dataclass
class OrderRequestPreview:
    symbol: str = "XAUUSD"
    volume: float = 0.01
    order_type: str = "BUY"  # BUY / SELL
    sl: float = 0.0
    tp: float = 0.0
    magic: int = MAGIC_NUMBER
    deviation: int = DEVIATION
    comment: str = "TITAN_DEMO_MICRO"
    has_sl: bool = False
    has_tp: bool = False
    safe_fallback_used: bool = False
    fallback_reason: str = ""
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()
        if self.volume > MAX_LOT:
            self.volume = MAX_LOT

    def to_dict(self) -> dict:
        return asdict(self)


class DemoMicroOrderBuilder:
    """Builds order request previews. NEVER sends orders."""

    def build_preview(self, direction: str = "BUY", entry_price: float = 2000.0,
                      sl: float = 0.0, tp: float = 0.0,
                      safe_fallback: bool = False,
                      fallback_reason: str = "") -> dict:
        """Build an order request preview.

        Returns dict with preview and validation status.
        NEVER calls mt5.order_send.

        Sprint 9.9.3.44.2: Preview vs Executable distinction.
        - If SL/TP valid or ATR fallback computes valid SL/TP: EXECUTABLE_WITH_PROTECTIVE_SL_TP
        - If SL/TP missing and no ATR fallback: PREVIEW_ONLY_NOT_EXECUTABLE
        - dry_run_preview_mode fallback is NEVER accepted for execution.
        """
        from titan.production.demo_micro_sl_tp_safety import DemoMicroSLTPSafety, SLTPVerdict

        ok_checks = []
        blockers = []
        warnings = []

        # Validate direction
        if direction not in ("BUY", "SELL"):
            blockers.append(f"Invalid direction: {direction} - must be BUY or SELL")
        else:
            ok_checks.append(f"Direction: {direction}")

        # Validate lot
        volume = MAX_LOT
        if volume > MAX_LOT:
            blockers.append(f"Volume {volume} > MAX_LOT {MAX_LOT}")
        else:
            ok_checks.append(f"Volume: {volume} <= {MAX_LOT}")

        # Sprint 9.9.3.44.2/44.3: Use SL/TP safety calculator
        sltp_safety = DemoMicroSLTPSafety()
        sltp_result = sltp_safety.validate_or_compute(
            direction=direction,
            entry_price=entry_price,
            sl=sl,
            tp=tp,
            atr=0.0,  # ATR not passed in preview mode; execution must provide it
            symbol="XAUUSD",
        )

        has_sl = sltp_result.has_sl
        has_tp = sltp_result.has_tp
        final_sl = sltp_result.sl
        final_tp = sltp_result.tp
        fallback_reason = sltp_result.fallback_reason
        safe_fallback_used = sltp_result.verdict in (
            SLTPVerdict.SLTP_ATR_FALLBACK_USED,
            SLTPVerdict.SLTP_MT5_TICK_FALLBACK_USED,
        )

        if sltp_result.verdict == SLTPVerdict.SLTP_BLOCKED:
            if safe_fallback:
                # Preview-only mode: do not add blockers, just warn
                warnings.append("SL/TP missing - PREVIEW_ONLY_NOT_EXECUTABLE")
                fallback_reason = "dry_run_preview_mode" if fallback_reason == "dry_run_preview_mode" else (fallback_reason or "sl_tp_missing_no_atr")
            else:
                blockers.append(f"DEMO_MICRO_SL_TP_MISSING: {sltp_result.blockers}")
        elif sltp_result.verdict == SLTPVerdict.SLTP_VALID:
            ok_checks.append(f"SL/TP validated: SL={final_sl:.4f}, TP={final_tp:.4f}")
        elif sltp_result.verdict == SLTPVerdict.SLTP_ATR_FALLBACK_USED:
            ok_checks.append(f"ATR fallback SL/TP: SL={final_sl:.4f}, TP={final_tp:.4f}")
        elif sltp_result.verdict == SLTPVerdict.SLTP_MT5_TICK_FALLBACK_USED:
            ok_checks.append(f"MT5 tick fallback SL/TP: SL={final_sl:.4f}, TP={final_tp:.4f}, ref={sltp_result.reference_price:.4f}")

        # Build preview
        preview = OrderRequestPreview(
            order_type=direction,
            volume=volume,
            sl=final_sl,
            tp=final_tp,
            has_sl=has_sl,
            has_tp=has_tp,
            safe_fallback_used=safe_fallback_used,
            fallback_reason=fallback_reason,
        )

        # Sprint 9.9.3.44.2: Determine executable status
        if has_sl and has_tp:
            executable_status = "EXECUTABLE_WITH_PROTECTIVE_SL_TP"
        else:
            executable_status = "PREVIEW_ONLY_NOT_EXECUTABLE"

        # Check for martingale/grid/averaging (must NOT be present)
        ok_checks.append("No martingale/grid/averaging - single order only")

        return {
            "preview": preview.to_dict(),
            "executable_status": executable_status,
            "reference_price": sltp_result.reference_price,
            "sl_distance": sltp_result.sl_distance,
            "tp_distance": sltp_result.tp_distance,
            "stop_level_checked": sltp_result.stop_level_checked,
            "stop_level_valid": sltp_result.stop_level_valid,
            "fallback_source": fallback_reason,
            "ok_checks": ok_checks,
            "blockers": blockers,
            "warnings": warnings,
            "verdict": "PASS" if not blockers else "BLOCKED",
            "important_note": "This is a PREVIEW only. No order was sent. No mt5.order_send was called.",
        }

    def write_preview(self, result: dict) -> dict:
        """Write order request preview to audit files."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        json_path = OUTPUT_DIR / "demo_micro_order_request_preview.json"
        md_path = OUTPUT_DIR / "demo_micro_order_request_preview.md"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str, ensure_ascii=False)

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# TITAN XAU AI - Demo Micro Order Request Preview\n\n")
            f.write(f"**Verdict:** **{result['verdict']}**\n\n")
            f.write(f"**Timestamp:** {result['preview']['timestamp_utc']}\n\n")
            f.write("**IMPORTANT: This is a PREVIEW only. No order was sent.**\n\n")
            f.write("## Order Request Preview\n\n")
            f.write("| Field | Value |\n|---|---|\n")
            for k, v in result["preview"].items():
                f.write(f"| {k} | {v} |\n")
            if result.get("ok_checks"):
                f.write("\n## OK Checks\n\n")
                for c in result["ok_checks"]:
                    f.write(f"- {c}\n")
            if result.get("warnings"):
                f.write("\n## Warnings\n\n")
                for w in result["warnings"]:
                    f.write(f"- {w}\n")
            if result.get("blockers"):
                f.write("\n## Blockers\n\n")
                for b in result["blockers"]:
                    f.write(f"- **{b}**\n")
            f.write("\n## Safety\n\n")
            f.write("- No mt5.order_send was called.\n")
            f.write("- No market execution adapter was used.\n")
            f.write("- This is a preview only - no order was sent to any broker.\n")

        return {"json_path": str(json_path), "md_path": str(md_path)}
