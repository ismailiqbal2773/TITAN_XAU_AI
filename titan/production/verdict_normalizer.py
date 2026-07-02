"""TITAN XAU AI - Verdict Normalizer (Sprint v2.8.3.1)
=====================================================
Central helpers for checking pass verdicts.

Never compare pass verdicts with only verdict == "PASS".
Use these helpers instead to handle all pass-equivalent verdicts.
"""
from __future__ import annotations


def is_alpha_entry_pass(verdict: str) -> bool:
    """True for ALPHA_REGIME_ENTRY_PASS and PASS."""
    if not verdict:
        return False
    v = verdict.strip().upper()
    return v in ("ALPHA_REGIME_ENTRY_PASS", "PASS")


def is_entry_gate_pass(verdict: str) -> bool:
    """True for ENTRY_GATE_FULL_PASS and PASS."""
    if not verdict:
        return False
    v = verdict.strip().upper()
    return v in ("ENTRY_GATE_FULL_PASS", "PASS")


def is_autonomous_readiness_pass(verdict: str) -> bool:
    """True for AUTONOMOUS_DEMO_READY_SUPERVISED, PASS, SUPERVISED_READY."""
    if not verdict:
        return False
    v = verdict.strip().upper()
    return v in ("AUTONOMOUS_DEMO_READY_SUPERVISED", "PASS", "SUPERVISED_READY")


def is_production_autonomous_pass(status: str) -> bool:
    """True for SUPERVISED_READY, AUTONOMOUS_DEMO_READY_SUPERVISED, PASS."""
    if not status:
        return False
    s = status.strip().upper()
    return s in ("SUPERVISED_READY", "AUTONOMOUS_DEMO_READY_SUPERVISED", "PASS")
