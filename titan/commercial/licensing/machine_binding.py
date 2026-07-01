"""
TITAN XAU AI — Machine Binding (Commercial Licensing Subsystem)
================================================================

Generates a deterministic machine signature from platform / OS information
and verifies that a license is bound to the current machine.

Design:
  - Pure-Python (no native deps, no MetaTrader5).
  - Deterministic: same machine ⇒ same signature (within a single OS boot).
  - Tolerant: a single component may change (HW swap) — 5 of 6 components
    must still match.
  - Fail-closed: any tamper signal ⇒ verify_binding() returns False.

NEVER imports MetaTrader5. NEVER calls mt5.order_send.
"""
from __future__ import annotations

import hashlib
import platform
import socket
import sys
import uuid
from dataclasses import dataclass, field
from typing import Optional

SALT = b"TITAN-XAU-AI::COMMERCIAL::MACHINE-BINDING::v1.0"


@dataclass
class MachineSignature:
    """Composite machine signature + per-component digests."""
    composite: str
    components: dict[str, str] = field(default_factory=dict)
    short_id: str = ""

    def to_dict(self) -> dict:
        return {
            "composite": self.composite,
            "short_id": self.short_id,
            "components": dict(self.components),
        }


def _safe(fn) -> str:
    try:
        v = fn()
        if v is None:
            return ""
        return str(v).strip()
    except Exception:
        return ""


def _digest(name: str, raw: str) -> str:
    h = hashlib.sha256()
    h.update(SALT)
    h.update(name.encode())
    h.update(raw.encode())
    return h.hexdigest()


class MachineBinding:
    """
    Generates a machine signature from platform information and verifies
    that a license-bound signature matches the current machine.

    Components collected (cross-platform):
      - platform.node()           (hostname)
      - platform.platform()       (os string)
      - platform.processor()      (cpu identifier)
      - platform.machine()        (arch)
      - platform.python_version() (runtime)
      - uuid.getnode()            (MAC-derived)

    Match policy: 5 of 6 components must match (tolerance for HW drift).
    """

    MIN_MATCH_RATIO: float = 5.0 / 6.0
    COMPONENT_NAMES: tuple[str, ...] = (
        "node", "platform", "processor", "machine", "python_version", "mac_node",
    )

    def __init__(self, readings: Optional[dict[str, str]] = None) -> None:
        if readings is None:
            readings = self._collect()
        self._readings: dict[str, str] = dict(readings)

    # ─── Collection ─────────────────────────────────────────────────────

    @classmethod
    def _collect(cls) -> dict[str, str]:
        return {
            "node": _safe(platform.node) or "unknown",
            "platform": _safe(platform.platform) or "unknown",
            "processor": _safe(platform.processor) or "unknown",
            "machine": _safe(platform.machine) or "unknown",
            "python_version": _safe(platform.python_version) or "unknown",
            "mac_node": _safe(lambda: f"{uuid.getnode():012x}") or "unknown",
        }

    @classmethod
    def collect(cls) -> "MachineBinding":
        return cls()

    # ─── Signature ──────────────────────────────────────────────────────

    def get_machine_signature(self) -> MachineSignature:
        """Return the composite signature for the current machine."""
        components = {
            name: _digest(name, raw)
            for name, raw in self._readings.items()
        }
        # Deterministic, order-independent composite
        parts = sorted(f"{k}={v}" for k, v in components.items())
        h = hashlib.sha256()
        h.update(SALT)
        for p in parts:
            h.update(p.encode())
        composite = h.hexdigest()
        return MachineSignature(
            composite=composite,
            components=components,
            short_id=composite[:16].upper(),
        )

    # ─── Verification ───────────────────────────────────────────────────

    def verify_binding(self, expected_signature: str | MachineSignature) -> tuple[bool, float, str]:
        """
        Verify that the current machine matches the expected signature.

        Returns:
            (matched: bool, match_ratio: float, reason: str)
        """
        if not expected_signature:
            return False, 0.0, "expected signature is empty"

        expected_components: dict[str, str]
        if isinstance(expected_signature, MachineSignature):
            expected_components = dict(expected_signature.components)
            expected_composite = expected_signature.composite
        else:
            expected_composite = str(expected_signature)
            expected_components = {}

        current = self.get_machine_signature()

        # Fast path: exact composite match
        if current.composite == expected_composite:
            return True, 1.0, "exact composite match"

        # Tolerant path: compare components if available
        if not expected_components:
            return False, 0.0, "composite mismatch and no component-level data"

        if set(expected_components.keys()) != set(current.components.keys()):
            return False, 0.0, "component set mismatch — possible tamper"

        matches = sum(
            1 for k in expected_components
            if expected_components[k] == current.components.get(k)
        )
        ratio = matches / len(expected_components) if expected_components else 0.0

        if ratio >= self.MIN_MATCH_RATIO:
            return True, ratio, f"tolerant match ({matches}/{len(expected_components)})"
        return False, ratio, f"machine binding mismatch ({matches}/{len(expected_components)})"

    # ─── Introspection ──────────────────────────────────────────────────

    @property
    def readings(self) -> dict[str, str]:
        return dict(self._readings)

    def short_id(self) -> str:
        return self.get_machine_signature().short_id


__all__ = ["MachineBinding", "MachineSignature", "SALT"]
