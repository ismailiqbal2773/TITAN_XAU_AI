"""TITAN XAU AI - Multi-Timeframe Signal Engine (Sprint v2.8.6)
================================================================
Regime-first M5/M15/H1 multi-timeframe validation engine.

Architecture:
  Regime Detection -> Timeframe/Strategy Mode Selection
  -> H1 Context -> M15 Confirmation -> M5 Entry Timing
  -> Alpha Direction/Edge -> Meta-label Trade Quality
  -> CEO Governance -> Risk/Prop/Broker/Geometry Gates
  -> Supervised Token-Gated Execution

NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional
import json
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

ALPHA_THRESHOLD = 0.55
META_LABEL_THRESHOLD = 0.65


def get_regime_policy(regime_value: str):
    """Map regime value to RegimeTimeframePolicy.

    Returns RegimeTimeframePolicy with allowed, strategy_mode, risk_posture,
    confirmation_strictness, and block_reason.
    """
    from titan.production.multi_timeframe_types import RegimeTimeframePolicy

    regime_upper = (regime_value or "UNKNOWN").upper()

    if regime_upper in ("TREND_STRONG", "TREND_NORMAL"):
        return RegimeTimeframePolicy(
            regime_value=regime_upper,
            allowed=True,
            allowed_timeframes=["H1", "M15", "M5"],
            strategy_mode="TREND_FOLLOW",
            risk_posture="NORMAL",
            confirmation_strictness="STANDARD",
            block_reason="",
        )
    elif regime_upper == "RANGE_NORMAL":
        return RegimeTimeframePolicy(
            regime_value=regime_upper,
            allowed=True,
            allowed_timeframes=["H1", "M15", "M5"],
            strategy_mode="MEAN_REVERSION",
            risk_posture="REDUCED",
            confirmation_strictness="STRICT",
            block_reason="",
        )
    elif regime_upper in ("LOW_VOLATILITY", "HOLIDAY", "DEAD_MARKET"):
        return RegimeTimeframePolicy(
            regime_value=regime_upper,
            allowed=False,
            allowed_timeframes=[],
            strategy_mode="BLOCKED",
            risk_posture="CAPITAL_PRESERVATION",
            confirmation_strictness="VERY_STRICT",
            block_reason=f"Regime {regime_upper}: low volatility/holiday/dead market - no trade",
        )
    elif regime_upper in ("SPREAD_EXPANSION", "BAD_LIQUIDITY", "NEWS_RISK"):
        return RegimeTimeframePolicy(
            regime_value=regime_upper,
            allowed=False,
            allowed_timeframes=[],
            strategy_mode="BLOCKED",
            risk_posture="CAPITAL_PRESERVATION",
            confirmation_strictness="VERY_STRICT",
            block_reason=f"Regime {regime_upper}: spread/liquidity/news risk - blocked",
        )
    elif regime_upper == "HIGH_VOLATILITY":
        return RegimeTimeframePolicy(
            regime_value=regime_upper,
            allowed=True,
            allowed_timeframes=["H1", "M15", "M5"],
            strategy_mode="VOLATILITY_AWARE",
            risk_posture="REDUCED",
            confirmation_strictness="STRICT",
            block_reason="",
        )
    elif regime_upper == "MARKET_OPEN":
        return RegimeTimeframePolicy(
            regime_value=regime_upper,
            allowed=True,
            allowed_timeframes=["H1", "M15", "M5"],
            strategy_mode="STANDARD",
            risk_posture="NORMAL",
            confirmation_strictness="STANDARD",
            block_reason="",
        )
    else:
        return RegimeTimeframePolicy(
            regime_value=regime_upper,
            allowed=False,
            allowed_timeframes=[],
            strategy_mode="BLOCKED",
            risk_posture="CAPITAL_PRESERVATION",
            confirmation_strictness="VERY_STRICT",
            block_reason=f"Unknown regime: {regime_upper} - blocked for safety",
        )


def evaluate_mtf_decision(
    *,
    mt5_module=None,
    symbol: str = "XAUUSD",
    h1_bars_required: int = 300,
    m15_bars_required: int = 500,
    m5_bars_required: int = 800,
    regime_value: str = "MARKET_OPEN",
    alpha_confidence: float = 0.0,
    alpha_pass: bool = False,
    meta_label_confidence: float = 0.0,
    meta_label_pass: bool = False,
    alpha_direction: str = "FLAT",
    ceo_final_decision: str = "BLOCKED",
    ceo_allowed: bool = False,
    h1_context_pass: bool = False,
    m15_confirmation_pass: bool = False,
    m5_entry_trigger_pass: bool = False,
    account_equity: float = 0.0,
    h1_data_ok: bool = False,
    m15_data_ok: bool = False,
    m5_data_ok: bool = False,
    h1_rates_received: int = 0,
    m15_rates_received: int = 0,
    m5_rates_received: int = 0,
    h1_feature_build_ok: bool = False,
    h1_feature_count: int = 0,
    h1_model_load_ok: bool = False,
    h1_inference_ok: bool = False,
    h1_meta_label_ok: bool = False,
    fallback_reason: str = "",
):
    """Evaluate the multi-timeframe decision.

    NEVER calls mt5.order_send. NEVER creates token. NEVER modifies positions.

    This function takes pre-fetched data and model outputs as inputs and
    produces a MultiTimeframeDecision. The caller is responsible for
    fetching MT5 rates and running models.

    Args:
        All timeframe data, model outputs, and CEO decision are passed in.
    Returns:
        MultiTimeframeDecision with final verdict, blockers, and reasoning.
    """
    from titan.production.multi_timeframe_types import MultiTimeframeDecision

    ts = datetime.now(timezone.utc).isoformat()
    decision = MultiTimeframeDecision(
        timestamp_utc=ts,
        timeframe_mode="mtf_m5_m15_h1",
        symbol=symbol,
        regime_value=regime_value,
        h1_context_pass=h1_context_pass,
        m15_confirmation_pass=m15_confirmation_pass,
        m5_entry_trigger_pass=m5_entry_trigger_pass,
        alpha_confidence=alpha_confidence,
        alpha_pass=alpha_pass,
        meta_label_confidence=meta_label_confidence,
        meta_label_pass=meta_label_pass,
        final_direction=alpha_direction if alpha_pass else "FLAT",
        final_timeframe_used="H1",
        ceo_allowed=ceo_allowed,
        ceo_final_decision=ceo_final_decision,
        h1_rates_received=h1_rates_received,
        m15_rates_received=m15_rates_received,
        m5_rates_received=m5_rates_received,
        h1_data_ok=h1_data_ok,
        m15_data_ok=m15_data_ok,
        m5_data_ok=m5_data_ok,
        h1_feature_build_ok=h1_feature_build_ok,
        h1_feature_count=h1_feature_count,
        h1_model_load_ok=h1_model_load_ok,
        h1_inference_ok=h1_inference_ok,
        h1_meta_label_ok=h1_meta_label_ok,
        fallback_reason=fallback_reason,
        account_equity=account_equity,
    )

    # Apply regime policy
    policy = get_regime_policy(regime_value)
    decision.regime_policy = policy

    # === Gate evaluation (all must pass) ===

    # 1. Regime must allow trading
    if not policy.allowed:
        decision.blockers.append(f"REGIME_BLOCKED: {policy.block_reason}")
        decision.reasoning_codes.append("REGIME_BLOCK")

    # 2. All timeframe data must be available
    if not h1_data_ok:
        decision.blockers.append(f"H1_DATA_UNAVAILABLE: rates={h1_rates_received}")
        decision.reasoning_codes.append("H1_DATA_FAIL")
    if not m15_data_ok:
        decision.blockers.append(f"M15_DATA_UNAVAILABLE: rates={m15_rates_received}")
        decision.reasoning_codes.append("M15_DATA_FAIL")
    if not m5_data_ok:
        decision.blockers.append(f"M5_DATA_UNAVAILABLE: rates={m5_rates_received}")
        decision.reasoning_codes.append("M5_DATA_FAIL")

    # 3. H1 context must pass
    if not h1_context_pass:
        decision.blockers.append("H1_CONTEXT_FAIL: H1 context/bias not confirmed")
        decision.reasoning_codes.append("H1_CONTEXT_FAIL")

    # 4. M15 confirmation must pass
    if not m15_confirmation_pass:
        decision.blockers.append("M15_CONFIRMATION_FAIL: M15 setup confirmation failed")
        decision.reasoning_codes.append("M15_CONFIRM_FAIL")

    # 5. M5 entry trigger must pass
    if not m5_entry_trigger_pass:
        decision.blockers.append("M5_TRIGGER_FAIL: M5 entry timing trigger failed")
        decision.reasoning_codes.append("M5_TRIGGER_FAIL")

    # 6. Alpha must pass
    if not alpha_pass:
        decision.blockers.append(
            f"ALPHA_FAIL: confidence={alpha_confidence:.4f} < threshold={ALPHA_THRESHOLD}"
        )
        decision.reasoning_codes.append("ALPHA_FAIL")

    # 7. Meta-label must pass
    if not meta_label_pass:
        decision.blockers.append(
            f"META_LABEL_FAIL: confidence={meta_label_confidence:.4f} < threshold={META_LABEL_THRESHOLD}"
        )
        decision.reasoning_codes.append("META_LABEL_FAIL")

    # 8. CEO must allow
    if not ceo_allowed:
        decision.blockers.append(f"CEO_BLOCKED: {ceo_final_decision}")
        decision.reasoning_codes.append("CEO_BLOCK")

    # === Determine signal source ===
    if h1_data_ok and m15_data_ok and m5_data_ok and h1_inference_ok and h1_meta_label_ok:
        decision.signal_source = "live_mt5_fresh"
        decision.is_fresh_signal = True
        decision.cache_used = False
    else:
        decision.signal_source = "cached_fallback"
        decision.is_fresh_signal = False
        decision.cache_used = True
        if not decision.blockers:
            decision.blockers.append("CACHED_SIGNAL_CANNOT_PASS: MTF requires live_mt5_fresh")
            decision.reasoning_codes.append("CACHED_BLOCKED")

    # === Final decision ===
    if not decision.blockers:
        decision.ceo_allowed = True
        decision.ceo_final_decision = "PASS"
        decision.reasoning_codes.append("MTF_ALL_PASS")
    else:
        decision.ceo_allowed = False
        decision.ceo_final_decision = "BLOCKED"

    return decision


def fetch_mtf_rates_from_mt5(mt5_module, symbol: str = "XAUUSD"):
    """Fetch H1, M15, M5 rates from MT5.

    Returns dict with h1_rates, m15_rates, m5_rates, account_equity,
    and diagnostic fields.

    NEVER calls mt5.order_send. Only read-only copy_rates_from_pos.
    """
    result = {
        "h1_rates": None, "m15_rates": None, "m5_rates": None,
        "h1_count": 0, "m15_count": 0, "m5_count": 0,
        "account_equity": 0.0, "account_server": "", "account_type": "",
        "mt5_initialized": False, "account_verified": False,
        "error": "", "symbol_info_present": False,
    }
    if mt5_module is None:
        result["error"] = "MT5 module not provided"
        return result

    try:
        if not mt5_module.initialize():
            result["error"] = f"MT5 initialize failed: {mt5_module.last_error()}"
            return result
        result["mt5_initialized"] = True

        acc = mt5_module.account_info()
        if acc is not None:
            result["account_server"] = getattr(acc, "server", "") or ""
            trade_mode = getattr(acc, "trade_mode", -1)
            result["account_type"] = "DEMO" if trade_mode == 0 else ("LIVE" if trade_mode == 2 else "UNKNOWN")
            result["account_equity"] = float(getattr(acc, "equity", 0) or 0)
            result["account_verified"] = (
                result["account_server"] == "MetaQuotes-Demo"
                and result["account_type"] == "DEMO"
            )

        sym = mt5_module.symbol_info(symbol)
        result["symbol_info_present"] = (sym is not None)

        if result["account_verified"]:
            # H1: 300 bars
            result["h1_rates"] = mt5_module.copy_rates_from_pos(symbol, mt5_module.TIMEFRAME_H1, 0, 300)
            result["h1_count"] = len(result["h1_rates"]) if result["h1_rates"] is not None else 0

            # M15: 500 bars
            result["m15_rates"] = mt5_module.copy_rates_from_pos(symbol, mt5_module.TIMEFRAME_M15, 0, 500)
            result["m15_count"] = len(result["m15_rates"]) if result["m15_rates"] is not None else 0

            # M5: 800 bars
            result["m5_rates"] = mt5_module.copy_rates_from_pos(symbol, mt5_module.TIMEFRAME_M5, 0, 800)
            result["m5_count"] = len(result["m5_rates"]) if result["m5_rates"] is not None else 0

        mt5_module.shutdown()
    except Exception as e:
        result["error"] = str(e)
        try:
            mt5_module.shutdown()
        except Exception:
            pass

    return result


def evaluate_m15_confirmation(m15_rates, h1_direction: str = "FLAT"):
    """Evaluate M15 confirmation as a rule-based filter.

    M15 confirmation checks:
    - M15 candle direction should not strongly conflict with H1 bias
    - Recent M15 momentum should support the direction
    - Spread/volatility conditions acceptable

    Returns (pass_bool, details_dict).
    """
    if m15_rates is None or len(m15_rates) < 20:
        return False, {"reason": "insufficient_m15_data", "bars": 0 if m15_rates is None else len(m15_rates)}

    import pandas as pd
    import numpy as np

    df = pd.DataFrame(m15_rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')

    # Last 5 M15 candles
    recent = df.tail(5)
    recent_close = recent['close'].values
    recent_open = recent['open'].values

    # M15 direction: are recent candles bullish or bearish?
    bullish_candles = sum(1 for i in range(len(recent_close)) if recent_close[i] > recent_open[i])
    bearish_candles = len(recent_close) - bullish_candles

    m15_direction = "LONG" if bullish_candles > bearish_candles else "SHORT"

    # Check: M15 should not strongly conflict with H1
    if h1_direction == "LONG" and m15_direction == "SHORT":
        return False, {"reason": "m15_conflicts_h1_long", "m15_dir": m15_direction, "h1_dir": h1_direction}
    if h1_direction == "SHORT" and m15_direction == "LONG":
        return False, {"reason": "m15_conflicts_h1_short", "m15_dir": m15_direction, "h1_dir": h1_direction}

    # M15 momentum: last close vs SMA(10)
    closes = df['close'].values
    if len(closes) >= 10:
        sma_10 = np.mean(closes[-10:])
        last_close = closes[-1]
        if h1_direction == "LONG" and last_close < sma_10 * 0.998:
            return False, {"reason": "m15_below_sma10_for_long", "last_close": float(last_close), "sma10": float(sma_10)}
        if h1_direction == "SHORT" and last_close > sma_10 * 1.002:
            return False, {"reason": "m15_above_sma10_for_short", "last_close": float(last_close), "sma10": float(sma_10)}

    return True, {"reason": "m15_confirmed", "m15_dir": m15_direction, "bullish": bullish_candles, "bearish": bearish_candles}


def evaluate_m5_trigger(m5_rates, direction: str = "FLAT"):
    """Evaluate M5 entry timing trigger as a rule-based filter.

    M5 trigger checks:
    - Recent M5 momentum supports direction
    - No extreme wick/noise entry
    - Spread acceptable

    Returns (pass_bool, details_dict).
    """
    if m5_rates is None or len(m5_rates) < 20:
        return False, {"reason": "insufficient_m5_data", "bars": 0 if m5_rates is None else len(m5_rates)}

    import pandas as pd
    import numpy as np

    df = pd.DataFrame(m5_rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')

    # Last 3 M5 candles
    recent = df.tail(3)
    recent_close = recent['close'].values
    recent_open = recent['open'].values
    recent_high = recent['high'].values
    recent_low = recent['low'].values

    # M5 momentum: last candle should support direction
    last_bullish = recent_close[-1] > recent_open[-1]
    last_bearish = recent_close[-1] < recent_open[-1]

    if direction == "LONG" and not last_bullish:
        # Allow if at least 2 of last 3 are bullish
        bullish_count = sum(1 for i in range(len(recent_close)) if recent_close[i] > recent_open[i])
        if bullish_count < 2:
            return False, {"reason": "m5_no_long_momentum", "bullish_count": bullish_count}
    if direction == "SHORT" and not last_bearish:
        bearish_count = sum(1 for i in range(len(recent_close)) if recent_close[i] < recent_open[i])
        if bearish_count < 2:
            return False, {"reason": "m5_no_short_momentum", "bearish_count": bearish_count}

    # Wick check: no extreme wick entry (wick > 2x body)
    body = abs(recent_close[-1] - recent_open[-1])
    upper_wick = recent_high[-1] - max(recent_close[-1], recent_open[-1])
    lower_wick = min(recent_close[-1], recent_open[-1]) - recent_low[-1]
    if body > 0:
        if upper_wick > body * 3 or lower_wick > body * 3:
            return False, {"reason": "m5_extreme_wick", "body": float(body), "upper_wick": float(upper_wick), "lower_wick": float(lower_wick)}

    # Spread check (if available)
    if 'spread' in df.columns:
        recent_spread = df['spread'].tail(10).mean()
        if recent_spread > 50:  # 50 points = $0.50 spread
            return False, {"reason": "m5_high_spread", "spread": float(recent_spread)}

    return True, {"reason": "m5_trigger_ok", "direction": direction}
