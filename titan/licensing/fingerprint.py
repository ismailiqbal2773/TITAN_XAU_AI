"""
TITAN XAU AI — Hardware Fingerprint Engine (M21.1)

Generates a deterministic, tamper-resistant hardware fingerprint from
multiple machine-local components. Used to bind a license to a single
physical machine (anti-piracy, anti-sharing).

Design:
- 6 component collectors (CPU, motherboard, disk, MAC, hostname, OS uuid)
- SHA-256 composite digest with versioned salt
- Tolerance: any 5 of 6 components must match (handles HW replacement)
- No elevated privileges required
- Pure-Python, cross-platform (Windows/Linux/macOS)
"""
from __future__ import annotations

import hashlib
import platform
import socket
import subprocess
import sys
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional

SALT = b"TITAN-XAU-AI::HW-FP::v1.0"


class FingerprintComponent(str, Enum):
    CPU = "cpu"
    MOTHERBOARD = "motherboard"
    DISK = "disk"
    MAC = "mac"
    HOSTNAME = "hostname"
    OS_UUID = "os_uuid"


@dataclass
class ComponentReading:
    name: FingerprintComponent
    raw: str
    digest: str          # SHA-256 hex of (SALT + name + raw)


def _safe_subprocess(cmd: list[str], timeout: float = 2.0) -> str:
    """Run a system command, return stdout, swallow errors."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, timeout=timeout, text=True, check=False
        )
        return (out.stdout or "").strip()
    except Exception:
        return ""


def _read_cpu() -> str:
    if sys.platform == "win32":
        out = _safe_subprocess(
            ["wmic", "cpu", "get", "ProcessorId"]
        )
        # second non-empty line is the id
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return lines[1] if len(lines) > 1 else ""
    elif sys.platform.startswith("linux"):
        out = _safe_subprocess(["cat", "/proc/cpuinfo"])
        for line in out.splitlines():
            if line.startswith("model name") or line.startswith("Serial"):
                return line.split(":", 1)[1].strip()
        return ""
    elif sys.platform == "darwin":
        return _safe_subprocess(["sysctl", "-n", "machdep.cpu.brand_string"])
    return ""


def _read_motherboard() -> str:
    if sys.platform == "win32":
        out = _safe_subprocess(["wmic", "baseboard", "get", "SerialNumber"])
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return lines[1] if len(lines) > 1 else ""
    elif sys.platform.startswith("linux"):
        return _safe_subprocess(["cat", "/sys/class/dmi/id/board_serial"])
    elif sys.platform == "darwin":
        return _safe_subprocess(["ioreg", "-l"]).split("IOPlatformUUID")[1].split('"')[1] \
            if "IOPlatformUUID" in _safe_subprocess(["ioreg", "-l"]) else ""
    return ""


def _read_disk() -> str:
    if sys.platform == "win32":
        out = _safe_subprocess(["wmic", "diskdrive", "get", "SerialNumber"])
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return lines[1] if len(lines) > 1 else ""
    elif sys.platform.startswith("linux"):
        return _safe_subprocess(["cat", "/etc/machine-id"]) or \
               _safe_subprocess(["cat", "/var/lib/dbus/machine-id"])
    elif sys.platform == "darwin":
        return _safe_subprocess(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"]).split("IOPlatformUUID")[1].split('"')[1] \
            if "IOPlatformUUID" in _safe_subprocess(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"]) else ""
    return ""


def _read_mac() -> str:
    try:
        return uuid.getnode().to_bytes(6, "big").hex(":")
    except Exception:
        return ""


def _read_hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return ""


def _read_os_uuid() -> str:
    # Cross-platform: uuid.getnode on Linux gives MAC, on Win it gives MAC too;
    # use platform-specific OS install UUID instead.
    if sys.platform == "win32":
        out = _safe_subprocess(["wmic", "csproduct", "get", "UUID"])
        lines = [l.strip() for l in out.splitlines() if l.strip()]
        return lines[1] if len(lines) > 1 else ""
    elif sys.platform.startswith("linux"):
        return _safe_subprocess(["cat", "/etc/machine-id"])
    elif sys.platform == "darwin":
        out = _safe_subprocess(["ioreg", "-d2", "-c", "IOPlatformExpertDevice"])
        for line in out.splitlines():
            if "IOPlatformUUID" in line:
                return line.split('"')[-2]
        return ""
    return ""


_READERS = {
    FingerprintComponent.CPU: _read_cpu,
    FingerprintComponent.MOTHERBOARD: _read_motherboard,
    FingerprintComponent.DISK: _read_disk,
    FingerprintComponent.MAC: _read_mac,
    FingerprintComponent.HOSTNAME: _read_hostname,
    FingerprintComponent.OS_UUID: _read_os_uuid,
}


def _digest_component(name: FingerprintComponent, raw: str) -> str:
    h = hashlib.sha256()
    h.update(SALT)
    h.update(name.value.encode())
    h.update(raw.encode())
    return h.hexdigest()


class HardwareFingerprint:
    """
    Collects 6 component readings, produces a composite fingerprint.
    Tolerates single-component drift (HW replacement) via 5/6 match policy.
    """

    MIN_MATCH_RATIO = 5 / 6  # 5 of 6 components must match for valid match

    def __init__(self, readings: Optional[dict[FingerprintComponent, ComponentReading]] = None):
        # Allow injection for testing; default to live collection.
        if readings is None:
            readings = self._collect()
        self._readings = readings

    @staticmethod
    def _collect() -> dict[FingerprintComponent, ComponentReading]:
        out: dict[FingerprintComponent, ComponentReading] = {}
        for name, reader in _READERS.items():
            try:
                raw = reader() or "unknown"
            except Exception:
                raw = "unknown"
            out[name] = ComponentReading(
                name=name, raw=raw,
                digest=_digest_component(name, raw),
            )
        return out

    @classmethod
    def collect(cls) -> "HardwareFingerprint":
        """Factory: collect from the current machine."""
        return cls()

    def composite_digest(self) -> str:
        """Deterministic composite digest. Order-independent."""
        digests = sorted(r.digest for r in self._readings.values())
        h = hashlib.sha256()
        h.update(SALT)
        for d in digests:
            h.update(d.encode())
        return h.hexdigest()

    def short_id(self) -> str:
        """Human-readable short fingerprint (first 16 hex chars)."""
        return self.composite_digest()[:16].upper()

    def machine_id(self) -> str:
        """Alias for composite_digest, used as JWT subject."""
        return self.composite_digest()

    def to_dict(self) -> dict:
        """Serialize for storage / transmission (digests only, raw redacted)."""
        return {
            "salt_version": "1.0",
            "composite": self.composite_digest(),
            "components": {
                r.name.value: r.digest for r in self._readings.values()
            },
        }

    def match(self, other: "HardwareFingerprint") -> tuple[bool, float]:
        """
        Compare to another fingerprint with 5/6 tolerance.
        Returns (matched: bool, match_ratio: float).
        """
        a = {n: r.digest for n, r in self._readings.items()}
        b = {n: r.digest for n, r in other._readings.items()}
        if set(a.keys()) != set(b.keys()):
            return False, 0.0
        matches = sum(1 for k in a if a[k] == b[k])
        ratio = matches / len(a)
        return ratio >= self.MIN_MATCH_RATIO, ratio

    def component_count(self) -> int:
        return len(self._readings)

    def get_reading(self, name: FingerprintComponent) -> Optional[ComponentReading]:
        return self._readings.get(name)


__all__ = [
    "HardwareFingerprint", "FingerprintComponent", "ComponentReading",
]
