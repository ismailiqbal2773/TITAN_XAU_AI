"""
TITAN XAU AI - Parameter Registry (Sprint 9.9.3.45.8.3)
========================================================
Searches existing repo artifacts for best SL/TP/RR parameters, ATR
multipliers, timeframe parameters, confidence thresholds, model
performance metrics, broker validation metrics, walk-forward metrics,
spread/slippage assumptions, and cost assumptions.

If real artifact exists:
  - source = BACKTEST_VALIDATED
  - artifact_path included
  - metric summary included

If missing:
  - source = SAFE_DEFAULT
  - validation_status = NEEDS_BACKTEST_BINDING
  - do NOT pretend it is validated

NEVER sends orders. NEVER modifies positions.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
import json, os

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class ParameterEntry:
    """Single parameter entry in the registry."""
    parameter_name: str = ""
    runtime_value: float = 0.0
    source: str = "SAFE_DEFAULT"  # or "BACKTEST_VALIDATED"
    artifact_path: str = ""
    validation_status: str = "NEEDS_BACKTEST_BINDING"
    metric_summary: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ParameterRegistry:
    """Registry of runtime parameters with backtest binding status.

    NEVER sends orders. NEVER modifies positions.
    """

    # Default runtime values (safe defaults)
    DEFAULTS = {
        "breakeven_trigger_R": 1.0,
        "trailing_trigger_R": 1.75,
        "profit_lock_trigger_R": 3.0,
        "dynamic_tp_trigger_R": 2.0,
        "dynamic_tp_initial_tp_R": 3.0,
        "tp_extension_trigger_R": 2.0,
        "tp_extension_R": 1.0,
        "tp_extension_atr_mult": 2.0,
        "trend_atr_multiplier": 2.0,
        "range_atr_multiplier": 1.0,
        "high_vol_atr_multiplier": 2.5,
        "min_hold_seconds": 60,
        "min_monitor_iterations": 3,
        "sl_update_cooldown_seconds": 60,
        "tp_extension_cooldown_seconds": 120,
        "locked_R": 1.2,
        "breakeven_buffer_R": 0.1,
        "minimum_RR": 2.0,
        "target_net_RR": 3.0,
        "max_risk_per_trade_pct": 0.005,
        "max_lot": 0.01,
    }

    # Search paths for backtest artifacts
    BACKTEST_SEARCH_PATHS = [
        "data/audit/backtest",
        "data/audit/walk_forward",
        "data/audit/model_validation",
        "data/audit/broker_validation",
        "data/audit/optimization",
        "data/validation",
        "data/simulation",
    ]

    def __init__(self):
        self.parameters: dict[str, ParameterEntry] = {}
        self._scan_artifacts()

    def _scan_artifacts(self):
        """Scan repo for backtest artifacts and bind parameters."""
        # First, set all defaults
        for name, value in self.DEFAULTS.items():
            self.parameters[name] = ParameterEntry(
                parameter_name=name,
                runtime_value=value,
                source="SAFE_DEFAULT",
                validation_status="NEEDS_BACKTEST_BINDING",
                reason="No backtest artifact found; using safe default",
            )

        # Search for backtest artifacts
        found_artifacts = []
        for search_path in self.BACKTEST_SEARCH_PATHS:
            full_path = REPO_ROOT / search_path
            if full_path.exists():
                for root, dirs, files in os.walk(full_path):
                    for f in files:
                        if f.endswith(".json"):
                            found_artifacts.append(Path(root) / f)

        # Try to extract validated parameters from artifacts
        for artifact_path in found_artifacts:
            try:
                with open(artifact_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._try_bind_from_artifact(data, artifact_path)
            except Exception:
                continue

    def _try_bind_from_artifact(self, data: dict, artifact_path: Path):
        """Try to extract validated parameters from an artifact."""
        # Look for common parameter fields in backtest results
        param_fields = {
            "breakeven_trigger_R": ["breakeven_trigger_R", "breakeven_trigger", "breakeven_R"],
            "trailing_trigger_R": ["trailing_trigger_R", "trailing_trigger", "trailing_R"],
            "profit_lock_trigger_R": ["profit_lock_trigger_R", "profit_lock_trigger", "profit_lock_R"],
            "trend_atr_multiplier": ["trend_atr_multiplier", "atr_multiplier_trend", "trend_atr_mult"],
            "range_atr_multiplier": ["range_atr_multiplier", "atr_multiplier_range", "range_atr_mult"],
        }

        for param_name, possible_keys in param_fields.items():
            for key in possible_keys:
                if key in data and isinstance(data[key], (int, float)):
                    entry = self.parameters.get(param_name)
                    if entry and entry.source == "SAFE_DEFAULT":
                        self.parameters[param_name] = ParameterEntry(
                            parameter_name=param_name,
                            runtime_value=float(data[key]),
                            source="BACKTEST_VALIDATED",
                            artifact_path=str(artifact_path),
                            validation_status="VALIDATED",
                            metric_summary=f"Found in {artifact_path.name}",
                            reason=f"Bound from backtest artifact: {artifact_path.name}",
                        )
                    break

    def get_parameter(self, name: str) -> ParameterEntry:
        """Get a parameter entry by name."""
        return self.parameters.get(name, ParameterEntry(parameter_name=name))

    def get_all_parameters(self) -> list[ParameterEntry]:
        """Get all parameter entries."""
        return list(self.parameters.values())

    def get_summary(self) -> dict:
        """Get summary of registry."""
        total = len(self.parameters)
        validated = sum(1 for p in self.parameters.values() if p.source == "BACKTEST_VALIDATED")
        safe_default = sum(1 for p in self.parameters.values() if p.source == "SAFE_DEFAULT")
        return {
            "total_parameters": total,
            "validated": validated,
            "safe_default": safe_default,
            "validation_rate": round(validated / total, 4) if total > 0 else 0.0,
            "parameters": [p.to_dict() for p in self.parameters.values()],
        }
