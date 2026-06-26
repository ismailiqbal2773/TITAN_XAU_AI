"""
TITAN XAU AI — Sprint 9.9.2 Demo Micro Config Loader (Shared)
================================================================
Shared config loading for hard gate + harness. Reads top-level
demo_micro section from config/runtime.yaml.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "config" / "runtime.yaml"


def load_demo_micro_config(config_path: Optional[str] = None) -> dict:
    """
    Load demo_micro config section from runtime.yaml.

    Returns dict with:
      - config_path_used: str
      - demo_micro_config_found: bool
      - demo_micro_enabled_raw: bool | None
      - demo_micro_enabled_effective: bool
      - demo_micro: dict (full section if found)
      - max_lot: float
      - max_open_positions: int
      - max_trades_per_run: int
      - force_close_on_end: bool
      - max_spread_usd: float
      - allow_weekend: bool
      - arm_token_env: str
    """
    path = Path(config_path) if config_path else CONFIG_PATH
    result = {
        "config_path_used": str(path),
        "demo_micro_config_found": False,
        "demo_micro_enabled_raw": None,
        "demo_micro_enabled_effective": False,
        "demo_micro": {},
        "max_lot": 0.01,
        "max_open_positions": 1,
        "max_trades_per_run": 1,
        "force_close_on_end": True,
        "max_spread_usd": 1.0,
        "allow_weekend": False,
        "arm_token_env": "TITAN_DEMO_MICRO_ARMED",
    }

    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except Exception:
        return result

    demo_micro = cfg.get("demo_micro")
    if demo_micro is None:
        return result

    if not isinstance(demo_micro, dict):
        return result

    result["demo_micro_config_found"] = True
    result["demo_micro"] = demo_micro

    enabled = demo_micro.get("enabled")
    result["demo_micro_enabled_raw"] = enabled
    result["demo_micro_enabled_effective"] = bool(enabled) if enabled is not None else False

    # Read all relevant fields
    result["max_lot"] = float(demo_micro.get("max_lot", 0.01))
    result["max_open_positions"] = int(demo_micro.get("max_open_positions", 1))
    result["max_trades_per_run"] = int(demo_micro.get("max_trades_per_run", 1))
    result["force_close_on_end"] = bool(demo_micro.get("force_close_on_end", True))
    result["max_spread_usd"] = float(demo_micro.get("max_spread_usd", 1.0))
    result["allow_weekend"] = bool(demo_micro.get("allow_weekend", False))
    result["arm_token_env"] = str(demo_micro.get("arm_token_env", "TITAN_DEMO_MICRO_ARMED"))

    return result
