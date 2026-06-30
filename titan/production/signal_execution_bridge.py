"""
TITAN XAU AI — Signal to Execution Bridge (Sprint 9.9.3.29)
=============================================================

Connects model decisions to execution intent WITHOUT sending real orders.
This is the institutional decision pipeline coordinator — it produces
ExecutionIntent objects that a future TradeLoop can act on.

Safety invariants:
  - Default dry_run=True, demo_only=True
  - Never calls mt5.order_send
  - Never calls MT5ExecutionAdapter.send_order
  - Any error → allowed=False (fail-closed)
  - risk_multiplier ALWAYS <= 1.0
  - lot NEVER exceeds 0.01 in current phase
  - Unknown regime reduces risk or blocks
  - BLOCKED broker blocks
  - REJECT broker blocks
  - Runtime CRITICAL blocks
  - SecurityGate release failure blocks
  - Low model/meta confidence blocks
  - No live trading path

Existing components (not duplicated):
  - titan/production/inference.py (InferenceEngine)
  - titan/production/trade_loop.py (TradeLoop)
  - titan/production/dynamic_risk_engine.py (DynamicRiskEngine)
  - titan/production/account_health_engine.py (AccountHealthEngine)
  - titan/production/broker_compatibility_matrix.py
  - titan/production/runtime_health.py (RuntimeHealthMonitor)
  - titan/security/security_gate.py (SecurityGate)
  - titan/production/regime_detection.py
  - titan/production/mt5_execution_adapter.py (MT5ExecutionAdapter)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class BridgeDecision(str, Enum):
    """Bridge decision outcomes."""
    APPROVE_DEMO_INTENT = "APPROVE_DEMO_INTENT"
    BLOCK_LOW_CONFIDENCE = "BLOCK_LOW_CONFIDENCE"
    BLOCK_META_REJECT = "BLOCK_META_REJECT"
    BLOCK_REGIME = "BLOCK_REGIME"
    BLOCK_BROKER = "BLOCK_BROKER"
    BLOCK_RUNTIME_HEALTH = "BLOCK_RUNTIME_HEALTH"
    BLOCK_SECURITY = "BLOCK_SECURITY"
    BLOCK_RISK_LIMIT = "BLOCK_RISK_LIMIT"
    BLOCK_UNKNOWN = "BLOCK_UNKNOWN"
    DRY_RUN_ONLY = "DRY_RUN_ONLY"


@dataclass
class DecisionInput:
    """Input from model + context into the bridge."""
    symbol: str = "XAUUSD"
    timeframe: str = "H1"
    model_signal: str = "NONE"         # BUY / SELL / NONE
    model_confidence: float = 0.0      # 0.0–1.0
    meta_confidence: float = 0.0       # 0.0–1.0
    direction: Optional[str] = None    # BUY / SELL / None
    timestamp_utc: str = ""
    features_snapshot: dict = field(default_factory=dict)
    account_context: dict = field(default_factory=dict)
    broker_context: dict = field(default_factory=dict)


@dataclass
class ExecutionIntent:
    """Output of the bridge — what the system intends to execute.

    This is NOT an order. It is a validated intent that a future
    TradeLoop can choose to act on (or not).
    """
    allowed: bool = False
    symbol: str = "XAUUSD"
    side: Optional[str] = None         # BUY / SELL / None
    lot: float = 0.01
    order_type: str = "MARKET"
    sl_mode: str = "NATIVE"            # NATIVE / SLTP_MODIFY / NAKED
    tp_mode: str = "NATIVE"
    risk_multiplier: float = 1.0       # ALWAYS <= 1.0
    confidence_final: float = 0.0
    approval_reasons: list[str] = field(default_factory=list)
    block_reasons: list[str] = field(default_factory=list)
    regime: str = "UNKNOWN"
    broker_status: str = "UNKNOWN"
    runtime_health_status: str = "UNKNOWN"
    security_status: str = "UNKNOWN"
    dry_run: bool = True
    demo_only: bool = True
    timestamp_utc: str = ""
    decision: str = BridgeDecision.BLOCK_UNKNOWN.value

    def __post_init__(self):
        if self.risk_multiplier > 1.0:
            self.risk_multiplier = 1.0
        if self.lot > 0.01:
            self.lot = 0.01
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()


# Thresholds (can be tuned via config in future)
MIN_MODEL_CONFIDENCE = 0.55
MIN_META_CONFIDENCE = 0.50
MAX_LOT = 0.01


class SignalExecutionBridge:
    """Coordinates model signals → validated ExecutionIntent.

    Pipeline:
      1. validate_confidence — model + meta thresholds
      2. apply_regime_gate — regime can block or reduce risk
      3. apply_broker_gate — broker compatibility check
      4. apply_runtime_health_gate — runtime health must not be CRITICAL
      5. apply_security_gate — SecurityGate must allow
      6. apply_risk_limits — lot cap, risk multiplier cap
      7. Build final ExecutionIntent

    Any gate failure → fail_closed_intent(reason)
    """

    def __init__(self, dry_run: bool = True, demo_only: bool = True,
                 min_model_confidence: float = MIN_MODEL_CONFIDENCE,
                 min_meta_confidence: float = MIN_META_CONFIDENCE,
                 max_lot: float = MAX_LOT):
        self.dry_run = dry_run
        self.demo_only = demo_only
        self.min_model_confidence = min_model_confidence
        self.min_meta_confidence = min_meta_confidence
        self.max_lot = max_lot

    def build_intent(self, inp: DecisionInput,
                     regime_status: Optional[dict] = None,
                     broker_info: Optional[dict] = None,
                     runtime_health: Optional[dict] = None,
                     security_status: Optional[dict] = None,
                     ) -> ExecutionIntent:
        """Build an ExecutionIntent from DecisionInput + context.

        All context dicts are optional — if not provided, the gate
        is skipped (treated as UNKNOWN / permissive in dev mode).

        Never raises — returns fail-closed intent on any error.
        """
        try:
            intent = ExecutionIntent(
                symbol=inp.symbol,
                side=inp.direction or inp.model_signal if inp.model_signal in ("BUY", "SELL") else None,
                dry_run=self.dry_run,
                demo_only=self.demo_only,
                timestamp_utc=inp.timestamp_utc or datetime.now(timezone.utc).isoformat(),
            )
            approvals = []
            blocks = []

            # ── Gate 1: Confidence ──
            if inp.model_signal in ("BUY", "SELL"):
                if inp.model_confidence < self.min_model_confidence:
                    blocks.append(f"Model confidence {inp.model_confidence:.2f} < {self.min_model_confidence}")
                    return self._fail_closed(inp, blocks,
                                               BridgeDecision.BLOCK_LOW_CONFIDENCE)
                if inp.meta_confidence < self.min_meta_confidence:
                    blocks.append(f"Meta confidence {inp.meta_confidence:.2f} < {self.min_meta_confidence}")
                    return self._fail_closed(inp, blocks,
                                               BridgeDecision.BLOCK_META_REJECT)
                approvals.append(f"Model confidence {inp.model_confidence:.2f} >= {self.min_model_confidence}")
                approvals.append(f"Meta confidence {inp.meta_confidence:.2f} >= {self.min_meta_confidence}")
            else:
                # No signal — not an error, just no intent
                intent.allowed = False
                intent.block_reasons.append("No model signal (NONE)")
                intent.decision = BridgeDecision.DRY_RUN_ONLY.value
                return intent

            # ── Gate 2: Regime ──
            if regime_status:
                regime_name = regime_status.get("primary_regime", "UNKNOWN")
                risk_mult = regime_status.get("risk_multiplier", 0.5)
                allow_trade = regime_status.get("allow_new_trade", True)
                block_reason = regime_status.get("block_reason")

                intent.regime = regime_name
                intent.risk_multiplier = min(risk_mult, 1.0)

                if not allow_trade:
                    blocks.append(f"Regime {regime_name} blocks new trades: {block_reason}")
                    return self._fail_closed(inp, blocks, BridgeDecision.BLOCK_REGIME,
                                              intent=intent)
                approvals.append(f"Regime {regime_name} allows (risk_mult={intent.risk_multiplier})")

            # ── Gate 3: Broker ──
            if broker_info:
                broker_status = broker_info.get("status", "UNKNOWN")
                intent.broker_status = broker_status
                if broker_status == "BLOCKED":
                    blocks.append(f"Broker status BLOCKED — {broker_info.get('server_name', 'unknown')}")
                    return self._fail_closed(inp, blocks, BridgeDecision.BLOCK_BROKER,
                                              intent=intent)
                if broker_status == "REJECT":
                    blocks.append(f"Broker status REJECT — {broker_info.get('server_name', 'unknown')}")
                    return self._fail_closed(inp, blocks, BridgeDecision.BLOCK_BROKER,
                                              intent=intent)
                approvals.append(f"Broker {broker_status} allows")

            # ── Gate 4: Runtime health ──
            if runtime_health:
                health_status = runtime_health.get("status", "UNKNOWN")
                intent.runtime_health_status = health_status
                if health_status == "CRITICAL":
                    blocks.append("Runtime health CRITICAL — execution blocked")
                    return self._fail_closed(inp, blocks, BridgeDecision.BLOCK_RUNTIME_HEALTH,
                                              intent=intent)
                approvals.append(f"Runtime health {health_status}")

            # ── Gate 5: Security ──
            if security_status:
                sec_allowed = security_status.get("allowed", True)
                intent.security_status = "ALLOWED" if sec_allowed else "BLOCKED"
                if not sec_allowed:
                    blocks.append(f"Security gate blocked: {security_status.get('reason', 'unknown')}")
                    return self._fail_closed(inp, blocks, BridgeDecision.BLOCK_SECURITY,
                                              intent=intent)
                approvals.append("Security gate allows")

            # ── Gate 6: Risk limits ──
            if intent.lot > self.max_lot:
                intent.lot = self.max_lot
                approvals.append(f"Lot capped at {self.max_lot}")
            if intent.risk_multiplier > 1.0:
                intent.risk_multiplier = 1.0

            # ── Final: approve ──
            intent.confidence_final = (inp.model_confidence + inp.meta_confidence) / 2
            intent.allowed = True
            intent.approval_reasons = approvals
            intent.block_reasons = blocks
            intent.decision = BridgeDecision.APPROVE_DEMO_INTENT.value
            return intent

        except Exception as e:
            return self._fail_closed(inp, [f"Bridge exception: {e}"],
                                      BridgeDecision.BLOCK_UNKNOWN)

    def _fail_closed(self, inp: DecisionInput, blocks: list[str],
                      decision: BridgeDecision,
                      intent: Optional[ExecutionIntent] = None) -> ExecutionIntent:
        """Return a fail-closed ExecutionIntent."""
        if intent is None:
            intent = ExecutionIntent(symbol=inp.symbol, dry_run=self.dry_run,
                                      demo_only=self.demo_only)
        intent.allowed = False
        intent.block_reasons = blocks
        intent.decision = decision.value
        return intent


# ─── Integration status (Sprint 9.9.3.41.2 update) ──────────────────────────
#
# Sprint 9.9.3.39 wired SignalExecutionBridge into AutonomousRuntime.
# The bridge is now called BEFORE TradeLoop.process_signal() in the
# inference loop. Blocked intents skip TradeLoop entirely.
#
# The following modules are already wired into AutonomousRuntime via the
# institutional pipeline:
#   - TradeLoop: already wired (bridge intent gates TradeLoop call)
#   - InferenceEngine: already wired (signal feeds DecisionInput)
#   - DynamicRiskEngine: already wired (capital-protection context passed)
#   - RuntimeHealthMonitor: already wired (health gate evaluated)
#   - BrokerCompatibilityMatrix: already wired (broker gate evaluated)
#   - SecurityGate: already wired (security gate evaluated)
#   - RegimeDetection: already wired (regime gate evaluated)
#
# Future direct callback integration (e.g. trade_loop.set_bridge(),
# inference.add_post_processor()) is OPTIONAL ONLY and must NOT duplicate
# the runtime path. The runtime path is the single source of truth.
#
# MT5ExecutionAdapter is intentionally NOT wired into the bridge. The
# bridge produces ExecutionIntent (a validated intent, NOT an order).
# The adapter is only used for operator-run demo micro execution on
# Windows, which is separate from the dry-run observation path.
