"""TITAN XAU AI — Direction Logic (Sprint v2.8.7-P1.1)
======================================================
Corrected long/short direction interpretation for binary upward-probability model.

For a binary upward-probability model:
  LONG when p_up >= 0.50
  SHORT when p_up < 0.50
  directional_confidence = max(p_up, 1 - p_up)

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations


def interpret_direction(p_up: float) -> tuple[str, float]:
    """Interpret alpha probability as direction + confidence.

    Args:
        p_up: Probability of upward movement (from XGBoost column 1).

    Returns:
        (direction, confidence) where direction is "LONG" or "SHORT"
        and confidence is max(p_up, 1-p_up).
    """
    if p_up >= 0.50:
        return "LONG", p_up
    else:
        return "SHORT", 1.0 - p_up


__all__ = ["interpret_direction"]
