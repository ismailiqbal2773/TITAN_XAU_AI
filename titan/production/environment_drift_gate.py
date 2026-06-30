"""
TITAN XAU AI - Environment Drift Gate (Sprint 9.9.3.43.1)
==========================================================
Compares current runtime environment against frozen signature.
NEVER imports MetaTrader5. NEVER sends orders. NEVER pip installs.
"""
from __future__ import annotations
import hashlib, json, sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
SIGNATURE_PATH = REPO_ROOT / "config" / "environment" / "environment_signature.json"

CRITICAL_IMPORTS = ["xgboost", "sklearn", "pandas", "numpy", "yaml", "MetaTrader5", "joblib"]


class DriftVerdict(str, Enum):
    ENVIRONMENT_LOCK_READY = "ENVIRONMENT_LOCK_READY"
    ENVIRONMENT_LOCK_READY_WITH_WARNINGS = "ENVIRONMENT_LOCK_READY_WITH_WARNINGS"
    ENVIRONMENT_LOCK_BLOCKED = "ENVIRONMENT_LOCK_BLOCKED"


@dataclass
class DriftResult:
    verdict: DriftVerdict = DriftVerdict.ENVIRONMENT_LOCK_BLOCKED
    signature_exists: bool = False
    python_version: str = ""
    frozen_python_version: str = ""
    packages: dict = field(default_factory=dict)
    ok_checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["verdict"] = self.verdict.value
        return d


def _pkg_version(imp: str) -> str | None:
    try:
        mod = __import__(imp)
        return getattr(mod, "__version__", "unknown")
    except ImportError:
        return None
    except Exception:
        return None


def _file_hash(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


class EnvironmentDriftGate:
    """Environment drift gate. Never auto-installs or upgrades."""

    def __init__(self, signature_path: Optional[Path] = None):
        self.signature_path = signature_path or SIGNATURE_PATH

    def evaluate(self) -> DriftResult:
        result = DriftResult()
        result.python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

        # Load frozen signature
        if not self.signature_path.exists():
            result.blockers.append("Environment signature not found — freeze current environment first")
            result.verdict = DriftVerdict.ENVIRONMENT_LOCK_BLOCKED
            return result

        result.signature_exists = True
        try:
            with open(self.signature_path, "r", encoding="utf-8") as f:
                sig = json.load(f)
        except Exception as e:
            result.blockers.append(f"Failed to load environment signature: {e}")
            result.verdict = DriftVerdict.ENVIRONMENT_LOCK_BLOCKED
            return result

        result.frozen_python_version = sig.get("python_version", "")
        frozen_major_minor = ".".join(result.frozen_python_version.split(".")[:2])
        current_major_minor = f"{sys.version_info.major}.{sys.version_info.minor}"

        # Check Python version
        if frozen_major_minor != current_major_minor:
            result.blockers.append(
                f"Python major/minor drift: frozen={frozen_major_minor} current={current_major_minor}"
            )
        else:
            result.ok_checks.append(f"Python version matches: {current_major_minor}")

        # Check critical packages
        frozen_packages = sig.get("critical_packages", {})
        for imp in CRITICAL_IMPORTS:
            frozen_ver = frozen_packages.get(imp)
            current_ver = _pkg_version(imp)
            result.packages[imp] = {"frozen": frozen_ver, "current": current_ver}

            if frozen_ver is None and current_ver is None:
                continue  # Both missing (optional package)
            if frozen_ver is not None and current_ver is None:
                result.blockers.append(f"Package {imp} missing (was {frozen_ver} in frozen env)")
            elif frozen_ver is not None and current_ver is not None:
                frozen_major = frozen_ver.split(".")[0]
                current_major = current_ver.split(".")[0]
                if frozen_major != current_major:
                    result.blockers.append(
                        f"Package {imp} major version drift: frozen={frozen_ver} current={current_ver}"
                    )
                elif frozen_ver != current_ver:
                    result.warnings.append(
                        f"DEPENDENCY_VERSION_DRIFT_WARNING: {imp} frozen={frozen_ver} current={current_ver}"
                    )
                else:
                    result.ok_checks.append(f"Package {imp} matches: {current_ver}")

        # Check model file hashes
        frozen_models = sig.get("model_files", {})
        models_dir = REPO_ROOT / "titan" / "data" / "models"
        for name, frozen_info in frozen_models.items():
            model_path = models_dir / name
            if not model_path.exists():
                result.blockers.append(f"Model file missing: {name}")
                continue
            current_hash = _file_hash(model_path)
            if current_hash != frozen_info.get("sha256", ""):
                result.blockers.append(f"Model file hash drift: {name}")
            else:
                result.ok_checks.append(f"Model file hash matches: {name}")

        # Determine verdict
        if result.blockers:
            result.verdict = DriftVerdict.ENVIRONMENT_LOCK_BLOCKED
        elif result.warnings:
            result.verdict = DriftVerdict.ENVIRONMENT_LOCK_READY_WITH_WARNINGS
        else:
            result.verdict = DriftVerdict.ENVIRONMENT_LOCK_READY

        return result
