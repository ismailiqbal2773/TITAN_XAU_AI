"""TITAN XAU AI - Audit Artifact Hygiene Helpers (Sprint v2.8.5-C)

Provides freshness metadata and validation for audit artifacts so production
closure / build-request / final activation cannot infer SUPERVISED_READY or
valid growth profile values from stale/cached/test-mode audit files.

NEVER sends orders. NEVER creates token. NEVER modifies positions.
"""
from __future__ import annotations
import json
import os
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]

# Audit artifacts older than this are considered stale (hours)
STALE_THRESHOLD_HOURS = 24


def get_git_commit() -> str:
    """Get current git HEAD commit hash."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        return out
    except Exception:
        return ""


def get_git_dirty() -> bool:
    """Check if git working tree is dirty."""
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL, timeout=5
        ).decode().strip()
        return bool(out)
    except Exception:
        return False


def make_freshness_metadata(audit_name: str, source_mode: str = "production",
                            environment_mode: str = "unknown",
                            session_id: str = "") -> dict:
    """Build freshness metadata for an audit artifact.

    Args:
        audit_name: Name of the audit (e.g. "model_artifact_health_audit")
        source_mode: "production" | "test" | "ci"
        environment_mode: "windows" | "linux_zai" | "unknown"
        session_id: Optional session identifier
    Returns:
        Dict with generated_at_utc, git_commit, audit_name, source_mode,
        environment_mode, session_id
    """
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit(),
        "audit_name": audit_name,
        "source_mode": source_mode,
        "environment_mode": environment_mode,
        "session_id": session_id,
    }


def validate_artifact_freshness(artifact_path: Path, expected_audit_name: str = "",
                                 current_git_commit: str = "",
                                 max_age_hours: int = STALE_THRESHOLD_HOURS) -> dict:
    """Validate that an audit artifact is fresh and from production source.

    Returns dict with:
        - exists: bool
        - fresh: bool (True if exists AND not stale AND not test-mode AND commit matches)
        - stale: bool (True if older than max_age_hours)
        - test_mode: bool (True if source_mode == "test")
        - commit_mismatch: bool (True if artifact commit != current commit)
        - missing_metadata: bool (True if freshness metadata absent)
        - reason: str (explanation if not fresh)
        - artifact_generated_at: str
        - artifact_git_commit: str
        - artifact_source_mode: str
    """
    out = {
        "exists": False, "fresh": False, "stale": False,
        "test_mode": False, "commit_mismatch": False,
        "missing_metadata": False, "reason": "",
        "artifact_generated_at": "", "artifact_git_commit": "",
        "artifact_source_mode": "",
    }
    if not artifact_path.exists():
        out["reason"] = f"artifact_not_found: {artifact_path.name}"
        return out
    out["exists"] = True
    try:
        with open(artifact_path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception as e:
        out["reason"] = f"artifact_corrupt: {e}"
        return out

    # Check freshness metadata
    gen_at = data.get("generated_at_utc", "") or data.get("timestamp_utc", "")
    art_commit = data.get("git_commit", "")
    source_mode = data.get("source_mode", "production")
    out["artifact_generated_at"] = gen_at
    out["artifact_git_commit"] = art_commit
    out["artifact_source_mode"] = source_mode

    if not gen_at or not art_commit:
        out["missing_metadata"] = True
        out["reason"] = "missing_freshness_metadata: no generated_at_utc or git_commit"
        out["fresh"] = False
        return out

    # Check source mode (test mode artifacts are never fresh for production use)
    if source_mode == "test":
        out["test_mode"] = True
        out["reason"] = "test_mode_artifact: source_mode=test, cannot use for production readiness"
        out["fresh"] = False
        return out

    # Check staleness (age > max_age_hours)
    try:
        gen_dt = datetime.fromisoformat(gen_at.replace("Z", "+00:00"))
        age_hours = (datetime.now(timezone.utc) - gen_dt).total_seconds() / 3600.0
        if age_hours > max_age_hours:
            out["stale"] = True
            out["reason"] = f"stale_artifact: age={int(age_hours)}h > {max_age_hours}h"
            out["fresh"] = False
            return out
        # Negative age = generated in future (clock skew) - treat as not fresh
        if age_hours < -1:
            out["stale"] = True
            out["reason"] = f"future_dated_artifact: age={int(age_hours)}h (clock skew?)"
            out["fresh"] = False
            return out
    except Exception as e:
        out["reason"] = f"timestamp_parse_error: {e}"
        out["fresh"] = False
        return out

    # Check commit match (if current commit provided)
    if current_git_commit and art_commit:
        if art_commit != current_git_commit:
            out["commit_mismatch"] = True
            out["reason"] = (
                f"commit_mismatch: artifact={art_commit[:12]} != "
                f"current={current_git_commit[:12]}"
            )
            out["fresh"] = False
            return out

    # All checks passed
    out["fresh"] = True
    out["reason"] = "fresh"
    return out


def load_growth_profile_config() -> dict:
    """Load growth profile values DIRECTLY from config YAML (source of truth).

    Returns dict with:
        - config_exists: bool
        - config_path: str
        - monthly_target_pct: float
        - prop_challenge_target_pct: float
        - daily_dd_soft_limit_pct: float
        - daily_dd_hard_limit_pct: float
        - max_total_dd_pct: float
        - max_open_positions: int
        - max_lot_cap_demo: float
        - base_risk_per_trade_pct: float
        - min_RR: float
        - preferred_RR: float
        - valid: bool (True if all required values present and non-zero)
        - errors: list of str
    """
    cfg_path = REPO_ROOT / "config" / "prop_challenge_growth_profile.yaml"
    out = {
        "config_exists": False, "config_path": str(cfg_path),
        "monthly_target_pct": 0.0, "prop_challenge_target_pct": 0.0,
        "daily_dd_soft_limit_pct": 0.0, "daily_dd_hard_limit_pct": 0.0,
        "max_total_dd_pct": 0.0,
        "max_open_positions": 0, "max_lot_cap_demo": 0.0,
        "base_risk_per_trade_pct": 0.0, "min_RR": 0.0, "preferred_RR": 0.0,
        "valid": False, "errors": [],
    }
    if not cfg_path.exists():
        out["errors"].append(f"GROWTH_PROFILE_CONFIG_MISSING: {cfg_path}")
        return out
    out["config_exists"] = True
    try:
        import yaml
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception as e:
        out["errors"].append(f"GROWTH_PROFILE_CONFIG_PARSE_ERROR: {e}")
        return out
    profile = cfg.get("profile") or {}
    targets = profile.get("targets") or {}
    risk_bands = profile.get("risk_bands") or {}
    pos_sizing = profile.get("position_sizing") or {}
    out["monthly_target_pct"] = float(targets.get("monthly_growth_target_pct", 0) or 0)
    out["prop_challenge_target_pct"] = float(targets.get("prop_challenge_target_pct", 0) or 0)
    out["daily_dd_soft_limit_pct"] = float(risk_bands.get("daily_dd_soft_limit_pct", 0) or 0)
    out["daily_dd_hard_limit_pct"] = float(risk_bands.get("daily_dd_hard_limit_pct", 0) or 0)
    out["max_total_dd_pct"] = float(risk_bands.get("max_total_dd_pct", 0) or 0)
    out["max_open_positions"] = int(pos_sizing.get("max_open_positions", 0) or 0)
    out["max_lot_cap_demo"] = float(pos_sizing.get("max_lot_cap_demo", 0) or 0)
    out["base_risk_per_trade_pct"] = float(pos_sizing.get("base_risk_per_trade_pct", 0) or 0)
    out["min_RR"] = float(pos_sizing.get("min_RR", 0) or 0)
    out["preferred_RR"] = float(pos_sizing.get("preferred_RR", 0) or 0)
    # Validate: all critical values must be present and non-zero
    if out["monthly_target_pct"] <= 0:
        out["errors"].append("GROWTH_PROFILE_CONFIG_INVALID: monthly_target_pct missing or zero")
    if out["daily_dd_soft_limit_pct"] <= 0:
        out["errors"].append("GROWTH_PROFILE_CONFIG_INVALID: daily_dd_soft_limit_pct missing or zero")
    if out["daily_dd_hard_limit_pct"] <= 0:
        out["errors"].append("GROWTH_PROFILE_CONFIG_INVALID: daily_dd_hard_limit_pct missing or zero")
    if out["max_total_dd_pct"] <= 0:
        out["errors"].append("GROWTH_PROFILE_CONFIG_INVALID: max_total_dd_pct missing or zero")
    out["valid"] = len(out["errors"]) == 0
    return out


def detect_environment_mode() -> str:
    """Detect environment mode: windows | linux_zai | unknown."""
    import platform
    sys_name = platform.system()
    if sys_name == "Windows":
        return "windows"
    elif sys_name == "Linux":
        return "linux_zai"
    return "unknown"
