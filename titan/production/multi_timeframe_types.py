"""TITAN XAU AI - Multi-Timeframe Types (Sprint v2.8.6)
======================================================
Typed dataclasses for regime-first M5/M15/H1 multi-timeframe validation.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


@dataclass
class TimeframeDataStatus:
    """Status of MT5 data fetch for a single timeframe."""
    timeframe: str = ""
    symbol: str = "XAUUSD"
    rates_requested: int = 0
    rates_received: int = 0
    last_bar_time: str = ""
    data_ok: bool = False
    error: str = ""


@dataclass
class TimeframeSignalStatus:
    """Signal status for a single timeframe."""
    timeframe: str = ""
    feature_build_ok: bool = False
    feature_count: int = 0
    regime_detected: bool = False
    regime_value: str = "UNKNOWN"
    alpha_confidence: float = 0.0
    alpha_pass: bool = False
    meta_label_confidence: float = 0.0
    meta_label_pass: bool = False
    rule_confirmation_pass: bool = False
    error: str = ""


@dataclass
class RegimeTimeframePolicy:
    """Regime policy mapping for timeframe validation."""
    regime_value: str = "UNKNOWN"
    allowed: bool = False
    allowed_timeframes: list = field(default_factory=list)
    strategy_mode: str = "BLOCKED"
    risk_posture: str = "NORMAL"
    confirmation_strictness: str = "STANDARD"
    block_reason: str = ""


@dataclass
class MultiTimeframeDecision:
    """Final multi-timeframe decision object."""
    timestamp_utc: str = ""
    timeframe_mode: str = "h1_only"
    signal_source: str = "unavailable"
    is_fresh_signal: bool = False
    cache_used: bool = True
    symbol: str = "XAUUSD"
    h1_status: Optional[TimeframeSignalStatus] = None
    m15_status: Optional[TimeframeSignalStatus] = None
    m5_status: Optional[TimeframeSignalStatus] = None
    regime_value: str = "UNKNOWN"
    regime_policy: Optional[RegimeTimeframePolicy] = None
    h1_context_pass: bool = False
    m15_confirmation_pass: bool = False
    m5_entry_trigger_pass: bool = False
    alpha_confidence: float = 0.0
    alpha_pass: bool = False
    meta_label_confidence: float = 0.0
    meta_label_pass: bool = False
    final_direction: str = "FLAT"
    final_timeframe_used: str = "H1"
    ceo_allowed: bool = False
    ceo_final_decision: str = "BLOCKED"
    blockers: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    reasoning_codes: list = field(default_factory=list)
    # Data diagnostics
    h1_rates_received: int = 0
    m15_rates_received: int = 0
    m5_rates_received: int = 0
    h1_data_ok: bool = False
    m15_data_ok: bool = False
    m5_data_ok: bool = False
    h1_feature_build_ok: bool = False
    h1_feature_count: int = 0
    h1_model_load_ok: bool = False
    h1_inference_ok: bool = False
    h1_meta_label_ok: bool = False
    fallback_reason: str = ""
    account_equity: float = 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp_utc": self.timestamp_utc,
            "timeframe_mode": self.timeframe_mode,
            "signal_source": self.signal_source,
            "is_fresh_signal": self.is_fresh_signal,
            "cache_used": self.cache_used,
            "symbol": self.symbol,
            "h1_rates_received": self.h1_rates_received,
            "m15_rates_received": self.m15_rates_received,
            "m5_rates_received": self.m5_rates_received,
            "h1_data_ok": self.h1_data_ok,
            "m15_data_ok": self.m15_data_ok,
            "m5_data_ok": self.m5_data_ok,
            "h1_feature_build_ok": self.h1_feature_build_ok,
            "h1_feature_count": self.h1_feature_count,
            "h1_model_load_ok": self.h1_model_load_ok,
            "h1_inference_ok": self.h1_inference_ok,
            "h1_meta_label_ok": self.h1_meta_label_ok,
            "regime_value": self.regime_value,
            "regime_policy_allowed": self.regime_policy.allowed if self.regime_policy else False,
            "regime_strategy_mode": self.regime_policy.strategy_mode if self.regime_policy else "BLOCKED",
            "regime_risk_posture": self.regime_policy.risk_posture if self.regime_policy else "NORMAL",
            "h1_context_pass": self.h1_context_pass,
            "m15_confirmation_pass": self.m15_confirmation_pass,
            "m5_entry_trigger_pass": self.m5_entry_trigger_pass,
            "alpha_confidence": self.alpha_confidence,
            "alpha_pass": self.alpha_pass,
            "meta_label_confidence": self.meta_label_confidence,
            "meta_label_pass": self.meta_label_pass,
            "final_direction": self.final_direction,
            "final_timeframe_used": self.final_timeframe_used,
            "ceo_final_decision": self.ceo_final_decision,
            "ceo_allowed_to_trade": self.ceo_allowed,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "reasoning_codes": self.reasoning_codes,
            "fallback_reason": self.fallback_reason,
            "account_equity": self.account_equity,
        }
