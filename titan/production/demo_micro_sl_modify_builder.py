"""
TITAN XAU AI - Demo Micro SL Modify Builder (Sprint 9.9.3.45)
==============================================================
Builds SL modification request PREVIEW only. NEVER sends orders.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class SLModifyPreview:
    action: str = "SLTP_MODIFY"
    ticket: int = 0
    symbol: str = "XAUUSD"
    new_sl: float = 0.0
    tp: float = 0.0  # Preserved
    magic: int = 202619
    comment: str = "TITAN_DEMO_MICRO"
    favorable: bool = True
    reason: str = ""
    blockers: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)


class DemoMicroSLModifyBuilder:
    """Builds SL modify preview. NEVER sends orders."""

    def build_preview(self, ticket: int, new_sl: float, tp: float,
                       favorable: bool, reason: str = "",
                       blockers: list[str] = None) -> dict:
        ok_checks = []
        warnings = []
        preview_blockers = list(blockers or [])

        if ticket <= 0:
            preview_blockers.append("Invalid ticket")

        if new_sl <= 0:
            preview_blockers.append("New SL must be > 0")

        if tp <= 0:
            preview_blockers.append("TP must be > 0 (preserved)")

        if not favorable:
            preview_blockers.append("SL move is not favorable - blocked")

        if not preview_blockers:
            ok_checks.append(f"SL modify preview: ticket={ticket}, new_sl={new_sl}, tp={tp}")
            ok_checks.append("Favorable direction verified")
            ok_checks.append("TP preserved")
            verdict = "PASS"
        else:
            verdict = "BLOCKED"

        preview = SLModifyPreview(
            ticket=ticket, new_sl=new_sl, tp=tp,
            favorable=favorable, reason=reason, blockers=preview_blockers,
        )

        return {
            "preview": preview.to_dict(),
            "verdict": verdict,
            "ok_checks": ok_checks,
            "blockers": preview_blockers,
            "warnings": warnings,
            "important_note": "This is a PREVIEW only. No mt5.order_send was called. No position was modified.",
        }
