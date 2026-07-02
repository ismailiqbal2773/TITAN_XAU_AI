"""TITAN XAU AI - Alpha/Regime Entry Decision Engine (Sprint v2.8)
==================================================================
Makes a single autonomous entry decision by chaining:
  regime detection -> alpha/model signal -> confidence threshold ->
  meta-label/calibration -> risk gate -> broker gate -> prop/funded gate ->
  spread/slippage/news/session filters -> execution geometry RR gate.

This engine NEVER calls mt5.order_send. NEVER modifies positions.
NEVER creates execution tokens. It only produces a decision object.

Verdicts:
  ALPHA_REGIME_ENTRY_PASS
  ALPHA_REGIME_ENTRY_BLOCKED_NO_REGIME
  ALPHA_REGIME_ENTRY_BLOCKED_NO_ALPHA
  ALPHA_REGIME_ENTRY_BLOCKED_CONFIDENCE
  ALPHA_REGIME_ENTRY_BLOCKED_META_LABEL
  ALPHA_REGIME_ENTRY_BLOCKED_RISK
  ALPHA_REGIME_ENTRY_BLOCKED_BROKER
  ALPHA_REGIME_ENTRY_BLOCKED_SPREAD
  ALPHA_REGIME_ENTRY_BLOCKED_NEWS
  ALPHA_REGIME_ENTRY_BLOCKED_GEOMETRY
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


# ─── Verdicts ────────────────────────────────────────────────────────────────

ALPHA_REGIME_ENTRY_PASS = "ALPHA_REGIME_ENTRY_PASS"
ALPHA_REGIME_ENTRY_BLOCKED_NO_REGIME = "ALPHA_REGIME_ENTRY_BLOCKED_NO_REGIME"
ALPHA_REGIME_ENTRY_BLOCKED_NO_ALPHA = "ALPHA_REGIME_ENTRY_BLOCKED_NO_ALPHA"
ALPHA_REGIME_ENTRY_BLOCKED_CONFIDENCE = "ALPHA_REGIME_ENTRY_BLOCKED_CONFIDENCE"
ALPHA_REGIME_ENTRY_BLOCKED_META_LABEL = "ALPHA_REGIME_ENTRY_BLOCKED_META_LABEL"
ALPHA_REGIME_ENTRY_BLOCKED_RISK = "ALPHA_REGIME_ENTRY_BLOCKED_RISK"
ALPHA_REGIME_ENTRY_BLOCKED_BROKER = "ALPHA_REGIME_ENTRY_BLOCKED_BROKER"
ALPHA_REGIME_ENTRY_BLOCKED_SPREAD = "ALPHA_REGIME_ENTRY_BLOCKED_SPREAD"
ALPHA_REGIME_ENTRY_BLOCKED_NEWS = "ALPHA_REGIME_ENTRY_BLOCKED_NEWS"
ALPHA_REGIME_ENTRY_BLOCKED_GEOMETRY = "ALPHA_REGIME_ENTRY_BLOCKED_GEOMETRY"

ALL_VERDICTS = (
    ALPHA_REGIME_ENTRY_PASS,
    ALPHA_REGIME_ENTRY_BLOCKED_NO_REGIME,
    ALPHA_REGIME_ENTRY_BLOCKED_NO_ALPHA,
    ALPHA_REGIME_ENTRY_BLOCKED_CONFIDENCE,
    ALPHA_REGIME_ENTRY_BLOCKED_META_LABEL,
    ALPHA_REGIME_ENTRY_BLOCKED_RISK,
    ALPHA_REGIME_ENTRY_BLOCKED_BROKER,
    ALPHA_REGIME_ENTRY_BLOCKED_SPREAD,
    ALPHA_REGIME_ENTRY_BLOCKED_NEWS,
    ALPHA_REGIME_ENTRY_BLOCKED_GEOMETRY,
)

DEFAULT_MINIMUM_RR = 2.0
DEFAULT_INITIAL_TP_R = 3.0


@dataclass
class AlphaRegimeEntryDecision:
    """Single autonomous entry decision object."""
    timestamp_utc: str = ""
    symbol: str = ""
    timeframe: str = ""
    selected_profile: str = ""
    side: str = ""  # BUY / SELL / ""
    regime_detected: bool = False
    regime_value: str = ""
    regime_confidence: float = 0.0
    # v2.8.1: regime source/diagnostic fields
    regime_source: str = ""
    regime_artifact_found: bool = False
    regime_detector_available: bool = False
    regime_error: str = ""
    regime_features_available: bool = False
    alpha_signal_detected: bool = False
    alpha_direction: str = ""  # LONG / SHORT / FLAT / ""
    alpha_confidence: float = 0.0
    alpha_threshold: float = 0.0
    alpha_pass: bool = False
    meta_label_pass: bool = False
    calibration_pass: bool = False
    risk_gate_pass: bool = False
    broker_gate_pass: bool = False
    # v2.8.1: broker gate diagnostic fields
    broker_gate_status: str = ""  # PASS / FAILED / UNKNOWN / CONTROLLED_DEMO_ALLOWED
    broker_gate_source: str = ""
    broker_gate_score: float = 0.0
    broker_gate_threshold: float = 70.0
    broker_gate_reason: str = ""
    broker_gate_blockers: list = field(default_factory=list)
    broker_server: str = ""
    broker_account_type: str = ""
    broker_symbol: str = ""
    broker_registry_status: str = ""
    broker_artifact_found: bool = False
    prop_funded_gate_pass: bool = False
    # v2.8.1: prop/funded gate diagnostic fields
    prop_funded_gate_source: str = ""
    prop_funded_gate_reason: str = ""
    prop_funded_gate_blockers: list = field(default_factory=list)
    spread_gate_pass: bool = False
    slippage_gate_pass: bool = False
    news_gate_pass: bool = False
    session_gate_pass: bool = False
    geometry_gate_pass: bool = False
    actual_RR: float = 0.0
    minimum_RR: float = DEFAULT_MINIMUM_RR
    initial_tp_R: float = DEFAULT_INITIAL_TP_R
    final_decision: str = ""
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp_utc": self.timestamp_utc,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "selected_profile": self.selected_profile,
            "side": self.side,
            "regime_detected": self.regime_detected,
            "regime_value": self.regime_value,
            "regime_confidence": self.regime_confidence,
            "regime_source": self.regime_source,
            "regime_artifact_found": self.regime_artifact_found,
            "regime_detector_available": self.regime_detector_available,
            "regime_error": self.regime_error,
            "regime_features_available": self.regime_features_available,
            "alpha_signal_detected": self.alpha_signal_detected,
            "alpha_direction": self.alpha_direction,
            "alpha_confidence": self.alpha_confidence,
            "alpha_threshold": self.alpha_threshold,
            "alpha_pass": self.alpha_pass,
            "meta_label_pass": self.meta_label_pass,
            "calibration_pass": self.calibration_pass,
            "risk_gate_pass": self.risk_gate_pass,
            "broker_gate_pass": self.broker_gate_pass,
            "broker_gate_status": self.broker_gate_status,
            "broker_gate_source": self.broker_gate_source,
            "broker_gate_score": self.broker_gate_score,
            "broker_gate_threshold": self.broker_gate_threshold,
            "broker_gate_reason": self.broker_gate_reason,
            "broker_gate_blockers": list(self.broker_gate_blockers),
            "broker_server": self.broker_server,
            "broker_account_type": self.broker_account_type,
            "broker_symbol": self.broker_symbol,
            "broker_registry_status": self.broker_registry_status,
            "broker_artifact_found": self.broker_artifact_found,
            "prop_funded_gate_pass": self.prop_funded_gate_pass,
            "prop_funded_gate_source": self.prop_funded_gate_source,
            "prop_funded_gate_reason": self.prop_funded_gate_reason,
            "prop_funded_gate_blockers": list(self.prop_funded_gate_blockers),
            "spread_gate_pass": self.spread_gate_pass,
            "slippage_gate_pass": self.slippage_gate_pass,
            "news_gate_pass": self.news_gate_pass,
            "session_gate_pass": self.session_gate_pass,
            "geometry_gate_pass": self.geometry_gate_pass,
            "actual_RR": self.actual_RR,
            "minimum_RR": self.minimum_RR,
            "initial_tp_R": self.initial_tp_R,
            "final_decision": self.final_decision,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "evidence_sources": list(self.evidence_sources),
        }


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        f = float(v)
        return f if f == f else default
    except (TypeError, ValueError):
        return default


def _to_str(v: Any, default: str = "") -> str:
    if v is None:
        return default
    return str(v)


def evaluate_entry(
    *,
    symbol: str = "XAUUSD",
    timeframe: str = "H1",
    selected_profile: str = "",
    regime_result: Optional[dict] = None,
    alpha_signal: Optional[dict] = None,
    confidence_threshold: float = 0.55,
    meta_label_result: Optional[dict] = None,
    calibration_result: Optional[dict] = None,
    risk_gate_result: Optional[dict] = None,
    broker_gate_result: Optional[dict] = None,
    prop_funded_gate_result: Optional[dict] = None,
    spread_gate_result: Optional[dict] = None,
    slippage_gate_result: Optional[dict] = None,
    news_gate_result: Optional[dict] = None,
    session_gate_result: Optional[dict] = None,
    geometry_gate_result: Optional[dict] = None,
    minimum_RR: float = DEFAULT_MINIMUM_RR,
    initial_tp_R: float = DEFAULT_INITIAL_TP_R,
) -> AlphaRegimeEntryDecision:
    """Evaluate the full alpha/regime entry decision chain.

    NEVER calls mt5.order_send. NEVER modifies positions.
    NEVER creates execution tokens.

    All inputs are dicts (or None). The engine reads boolean/float fields
    from them and produces a single decision object.
    """
    ts = datetime.now(timezone.utc).isoformat()
    decision = AlphaRegimeEntryDecision(
        timestamp_utc=ts,
        symbol=symbol,
        timeframe=timeframe,
        selected_profile=selected_profile,
        minimum_RR=minimum_RR,
        initial_tp_R=initial_tp_R,
    )

    # ─── Regime ──────────────────────────────────────────────────────────────
    if regime_result:
        decision.regime_detected = bool(regime_result.get("detected", False) or
                                        regime_result.get("regime_detected", False))
        decision.regime_value = _to_str(
            regime_result.get("regime_value") or
            regime_result.get("primary_regime") or
            regime_result.get("value") or
            regime_result.get("regime")
        )
        decision.regime_confidence = _safe_float(regime_result.get("confidence", 0.0))
        decision.evidence_sources.append("regime_result")
        # v2.8.1: If regime result exists but detected=False, add explicit blocker.
        if not decision.regime_detected:
            decision.blockers.append("REGIME_NOT_DETECTED: regime result provided but detected=False")
    else:
        decision.blockers.append("REGIME_NOT_DETECTED: regime result not provided")
        decision.evidence_sources.append("regime_result:missing")

    # ─── Alpha signal ─────────────────────────────────────────────────────────
    if alpha_signal:
        decision.alpha_signal_detected = bool(
            alpha_signal.get("detected", False) or
            alpha_signal.get("alpha_signal_detected", False) or
            alpha_signal.get("is_tradeable", False)
        )
        raw_dir = (
            alpha_signal.get("alpha_direction") or
            alpha_signal.get("direction") or
            alpha_signal.get("signal_direction") or
            ""
        )
        # Normalize direction to LONG/SHORT/FLAT
        dir_str = _to_str(raw_dir).upper()
        if dir_str in ("LONG", "BUY", "1", "UP"):
            decision.alpha_direction = "LONG"
            decision.side = "BUY"
        elif dir_str in ("SHORT", "SELL", "-1", "DOWN"):
            decision.alpha_direction = "SHORT"
            decision.side = "SELL"
        else:
            decision.alpha_direction = "FLAT"
            decision.side = ""
        decision.alpha_confidence = _safe_float(
            alpha_signal.get("confidence") or
            alpha_signal.get("alpha_confidence") or
            0.0
        )
        decision.alpha_threshold = _safe_float(
            alpha_signal.get("threshold") or
            confidence_threshold
        )
        decision.evidence_sources.append("alpha_signal")
    else:
        decision.blockers.append("NO_ALPHA: alpha signal not provided")
        decision.evidence_sources.append("alpha_signal:missing")

    # Use confidence_threshold param as fallback
    if decision.alpha_threshold == 0.0:
        decision.alpha_threshold = confidence_threshold

    # ─── Alpha pass ────────────────────────────────────────────────────────────
    decision.alpha_pass = (
        decision.alpha_signal_detected
        and decision.alpha_direction in ("LONG", "SHORT")
        and decision.alpha_confidence >= decision.alpha_threshold
    )
    if decision.alpha_signal_detected and decision.alpha_confidence < decision.alpha_threshold:
        decision.blockers.append(
            f"CONFIDENCE_BELOW_THRESHOLD: alpha_confidence={decision.alpha_confidence:.4f} "
            f"< threshold={decision.alpha_threshold:.4f}"
        )

    # ─── Meta-label / calibration ───────────────────────────────────────────────
    if meta_label_result:
        decision.meta_label_pass = bool(meta_label_result.get("pass", False))
        decision.evidence_sources.append("meta_label_result")
        if not decision.meta_label_pass:
            decision.blockers.append("META_LABEL_BLOCKED: meta-label gate did not pass")
    else:
        decision.meta_label_pass = True  # No meta-label = pass (not required)
        decision.warnings.append("meta_label_result not provided - assumed pass")

    if calibration_result:
        decision.calibration_pass = bool(calibration_result.get("pass", False))
        decision.evidence_sources.append("calibration_result")
        if not decision.calibration_pass:
            decision.blockers.append("CALIBRATION_BLOCKED: calibration gate did not pass")
    else:
        decision.calibration_pass = True
        decision.warnings.append("calibration_result not provided - assumed pass")

    # ─── Risk gate ──────────────────────────────────────────────────────────────
    if risk_gate_result:
        decision.risk_gate_pass = bool(risk_gate_result.get("pass", False))
        decision.evidence_sources.append("risk_gate_result")
        if not decision.risk_gate_pass:
            risk_blockers = risk_gate_result.get("blockers", [])
            decision.blockers.append(
                f"RISK_GATE_BLOCKED: risk gate did not pass (blockers={risk_blockers})"
            )
    else:
        decision.risk_gate_pass = False
        decision.blockers.append("RISK_GATE_BLOCKED: risk gate result not provided")
        decision.evidence_sources.append("risk_gate_result:missing")

    # ─── Broker gate ────────────────────────────────────────────────────────────
    if broker_gate_result:
        broker_status = _to_str(broker_gate_result.get("status", "")).upper()
        # v2.8.1: Populate diagnostic fields
        decision.broker_gate_source = _to_str(broker_gate_result.get("source", "broker_gate_result"))
        decision.broker_gate_score = _safe_float(broker_gate_result.get("score", 0.0))
        decision.broker_gate_threshold = _safe_float(broker_gate_result.get("threshold", 70.0))
        decision.broker_server = _to_str(broker_gate_result.get("server", ""))
        decision.broker_account_type = _to_str(broker_gate_result.get("account_type", ""))
        decision.broker_symbol = _to_str(broker_gate_result.get("symbol", ""))
        decision.broker_registry_status = _to_str(broker_gate_result.get("registry_status", ""))
        decision.broker_artifact_found = bool(broker_gate_result.get("artifact_found", True))
        decision.broker_gate_blockers = list(broker_gate_result.get("blockers", []) or [])

        if broker_status == "CONTROLLED_DEMO_ALLOWED":
            decision.broker_gate_pass = True
            decision.broker_gate_status = "CONTROLLED_DEMO_ALLOWED"
            decision.broker_gate_reason = "MetaQuotes-Demo allowed for controlled demo profile"
        elif broker_status == "PASS" or broker_gate_result.get("pass", False):
            decision.broker_gate_pass = True
            decision.broker_gate_status = "PASS"
        elif broker_status in ("UNKNOWN", "UNKNOWN_STALE_OR_MISMATCHED"):
            decision.broker_gate_pass = False
            decision.broker_gate_status = broker_status
            decision.broker_gate_reason = (
                "BROKER_GATE_UNKNOWN_NO_ARTIFACT: no broker score artifact available"
                if broker_status == "UNKNOWN"
                else "BROKER_SCORE_STALE_OR_MISMATCHED: broker score is stale or from mismatched account"
            )
            decision.warnings.append(decision.broker_gate_reason)
        else:
            decision.broker_gate_pass = False
            decision.broker_gate_status = "FAILED"
            score = decision.broker_gate_score
            threshold = decision.broker_gate_threshold
            if decision.broker_artifact_found and score > 0 and score < threshold:
                decision.broker_gate_reason = (
                    f"BROKER_SCORE_BELOW_THRESHOLD: score={score} < threshold={threshold}"
                )
            elif not decision.broker_artifact_found:
                decision.broker_gate_reason = "BROKER_ARTIFACT_NOT_FOUND"
            else:
                decision.broker_gate_reason = _to_str(
                    broker_gate_result.get("reason", "BROKER_NOT_APPROVED_FOR_AUTONOMOUS_DEMO")
                )
            decision.blockers.append(
                f"BROKER_GATE_BLOCKED: status={decision.broker_gate_status}, "
                f"reason={decision.broker_gate_reason}, source={decision.broker_gate_source}"
            )
        decision.evidence_sources.append("broker_gate_result")
    else:
        decision.broker_gate_pass = False
        decision.broker_gate_status = "UNKNOWN"
        decision.broker_gate_reason = "BROKER_GATE_RESULT_NOT_PROVIDED"
        decision.broker_artifact_found = False
        decision.blockers.append("BROKER_GATE_BLOCKED: broker gate result not provided")
        decision.evidence_sources.append("broker_gate_result:missing")

    # ─── Prop/funded gate ────────────────────────────────────────────────────────
    if prop_funded_gate_result:
        decision.prop_funded_gate_pass = bool(prop_funded_gate_result.get("pass", False))
        decision.prop_funded_gate_source = _to_str(prop_funded_gate_result.get("source", "prop_funded_optimizer"))
        decision.prop_funded_gate_blockers = list(prop_funded_gate_result.get("blockers", []) or [])
        decision.evidence_sources.append("prop_funded_gate_result")
        if not decision.prop_funded_gate_pass:
            # v2.8.1: Determine exact reason for prop/funded gate failure.
            reason = _to_str(prop_funded_gate_result.get("reason", ""))
            if reason == "profile_not_found":
                decision.prop_funded_gate_reason = "PROP_FUNDED_PROFILE_ARTIFACT_MISSING"
            elif not decision.broker_gate_pass:
                decision.prop_funded_gate_reason = "PROP_FUNDED_GATE_BLOCKED_BY_BROKER"
            elif decision.prop_funded_gate_blockers:
                decision.prop_funded_gate_reason = "; ".join(str(b) for b in decision.prop_funded_gate_blockers)
            else:
                decision.prop_funded_gate_reason = reason or "PROP_FUNDED_GATE_RULE_FAILED"
            decision.blockers.append(
                f"PROP_FUNDED_GATE_BLOCKED: reason={decision.prop_funded_gate_reason}, "
                f"source={decision.prop_funded_gate_source}"
            )
    else:
        decision.prop_funded_gate_pass = False
        decision.prop_funded_gate_reason = "PROP_FUNDED_GATE_RESULT_NOT_PROVIDED"
        decision.blockers.append("PROP_FUNDED_GATE_BLOCKED: prop/funded gate result not provided")
        decision.evidence_sources.append("prop_funded_gate_result:missing")

    # ─── Spread / slippage ───────────────────────────────────────────────────────
    if spread_gate_result:
        decision.spread_gate_pass = bool(spread_gate_result.get("pass", False))
        decision.evidence_sources.append("spread_gate_result")
        if not decision.spread_gate_pass:
            decision.blockers.append(
                f"SPREAD_GATE_BLOCKED: spread={spread_gate_result.get('spread', 'N/A')} "
                f"> limit={spread_gate_result.get('limit', 'N/A')}"
            )
    else:
        decision.spread_gate_pass = True  # No spread data = pass (passive)
        decision.warnings.append("spread_gate_result not provided - assumed pass")

    if slippage_gate_result:
        decision.slippage_gate_pass = bool(slippage_gate_result.get("pass", False))
        decision.evidence_sources.append("slippage_gate_result")
    else:
        decision.slippage_gate_pass = True
        decision.warnings.append("slippage_gate_result not provided - assumed pass")

    # ─── News gate ────────────────────────────────────────────────────────────────
    if news_gate_result:
        decision.news_gate_pass = bool(news_gate_result.get("pass", False))
        decision.evidence_sources.append("news_gate_result")
        if not decision.news_gate_pass:
            decision.blockers.append(
                f"NEWS_GATE_BLOCKED: news event within blackout "
                f"({news_gate_result.get('reason', 'N/A')})"
            )
    else:
        decision.news_gate_pass = True  # No news data = pass
        decision.warnings.append("news_gate_result not provided - assumed pass")

    # ─── Session gate ─────────────────────────────────────────────────────────────
    if session_gate_result:
        decision.session_gate_pass = bool(session_gate_result.get("pass", False))
        decision.evidence_sources.append("session_gate_result")
        if not decision.session_gate_pass:
            decision.blockers.append("SESSION_GATE_BLOCKED: outside allowed trading session")
    else:
        decision.session_gate_pass = True
        decision.warnings.append("session_gate_result not provided - assumed pass")

    # ─── Geometry gate ────────────────────────────────────────────────────────────
    if geometry_gate_result:
        decision.geometry_gate_pass = bool(geometry_gate_result.get("pass", False))
        decision.actual_RR = _safe_float(geometry_gate_result.get("actual_RR", 0.0))
        decision.evidence_sources.append("geometry_gate_result")
        if not decision.geometry_gate_pass:
            decision.blockers.append(
                f"GEOMETRY_GATE_BLOCKED: actual_RR={decision.actual_RR:.4f} "
                f"< minimum_RR={decision.minimum_RR:.4f}"
            )
    else:
        decision.geometry_gate_pass = False
        decision.blockers.append("GEOMETRY_GATE_BLOCKED: geometry gate result not provided")
        decision.evidence_sources.append("geometry_gate_result:missing")

    # ─── Final decision ───────────────────────────────────────────────────────────
    if not decision.regime_detected:
        decision.final_decision = ALPHA_REGIME_ENTRY_BLOCKED_NO_REGIME
    elif not decision.alpha_signal_detected:
        decision.final_decision = ALPHA_REGIME_ENTRY_BLOCKED_NO_ALPHA
    elif not decision.alpha_pass:
        decision.final_decision = ALPHA_REGIME_ENTRY_BLOCKED_CONFIDENCE
    elif not decision.meta_label_pass:
        decision.final_decision = ALPHA_REGIME_ENTRY_BLOCKED_META_LABEL
    elif not decision.geometry_gate_pass:
        decision.final_decision = ALPHA_REGIME_ENTRY_BLOCKED_GEOMETRY
    elif not decision.risk_gate_pass:
        decision.final_decision = ALPHA_REGIME_ENTRY_BLOCKED_RISK
    elif not decision.broker_gate_pass:
        decision.final_decision = ALPHA_REGIME_ENTRY_BLOCKED_BROKER
    elif not decision.spread_gate_pass:
        decision.final_decision = ALPHA_REGIME_ENTRY_BLOCKED_SPREAD
    elif not decision.news_gate_pass:
        decision.final_decision = ALPHA_REGIME_ENTRY_BLOCKED_NEWS
    elif (decision.prop_funded_gate_pass
          and decision.session_gate_pass
          and decision.slippage_gate_pass
          and decision.calibration_pass):
        decision.final_decision = ALPHA_REGIME_ENTRY_PASS
    else:
        # Should not reach here, but default to BLOCKED_RISK for safety
        decision.final_decision = ALPHA_REGIME_ENTRY_BLOCKED_RISK
        decision.blockers.append("UNCAUGHT_BLOCKER: one or more gates did not pass")

    return decision
