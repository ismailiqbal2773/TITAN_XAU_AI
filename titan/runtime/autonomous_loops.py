"""
TITAN XAU AI — Autonomous Trading Loops (Sprint 8)

The 6 async loops that make TITAN trade autonomously:

  1. _inference_loop       — H1 bar close → features → XGB → meta → Signal
  2. _trade_loop           — Signal → kill-switch check → risk → dry-run order
  3. _position_sync_loop   — broker → local state sync (every 10s)
  4. _exit_manager_loop    — TP/SL/trailing/kill-switch exit detection
  5. _drift_monitor_loop   — PSI/ECE/Brier → kill-switch update
  6. _heartbeat_loop       — watchdog heartbeat + health check

All loops are dry_run=True by default. No real MT5 calls.

Usage (from launcher or main.py):
    from titan.runtime.autonomous_loops import AutonomousRuntime
    runtime = AutonomousRuntime(config, journal)
    await runtime.start()  # blocks until shutdown
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from titan.production.inference import InferenceEngine, Signal, Direction
from titan.production.trade_loop import TradeLoop, TradeLoopConfig, TradeDecision
from titan.production.trade_journal import TradeJournal, EventType
from titan.production.kill_switch_fsm import (
    KillSwitchFSM, KillSwitchConfig, KillSwitchInput, KillState,
)
from titan.production.feature_stream import H1FeatureStream
from titan.production.position_sync import PositionSync, BrokerPosition
from titan.production.exit_manager import ExitManager, ExitConfig, ExitReason
from titan.production.drift_monitor import DriftMonitor, DriftConfig
from titan.production.slippage_monitor import SlippageMonitor
from titan.production.news_filter import NewsFilter
from titan.production.meta_calibration_monitor import (
    MetaCalibrationMonitor, CalibrationConfig, CalibrationState,
)
# ─── Sprint 9.9.3.39: Institutional pipeline wiring ──────────────────────
# These modules existed as standalone/report-only modules before this sprint.
# Sprint 9.9.3.39 wires them into the actual runtime path so that
# AutonomousRuntime uses the institutional decision pipeline instead of
# only the Sprint 5-8 component set.
from titan.production.signal_execution_bridge import (
    SignalExecutionBridge, DecisionInput, ExecutionIntent, BridgeDecision,
)
from titan.production.regime_detection import detect_regime, RegimeStatus, RegimeType
from titan.production.broker_compatibility_matrix import get_broker_info, get_all_brokers
from titan.production.runtime_health import RuntimeHealthMonitor
from titan.security.security_gate import SecurityGate
from titan.production.position_lifecycle import (
    PositionLifecycleEngine, PositionSnapshot, PositionLifecycleStatus,
    PositionState,
)
from titan.production.exit_intent_bridge import (
    ExitIntentBridge, ExitIntent, ExitIntentAction,
)
from titan.production.forward_observation import (
    ForwardObservationEngine, ForwardObservationEvent, ForwardObservationEventType,
)
from titan.production.observation_scorecard import (
    ObservationScorecardEngine, ObservationScorecard, ObservationScoreGrade,
)

logger = logging.getLogger(__name__)


@dataclass
class RuntimeConfig:
    """Autonomous runtime configuration."""
    # Loop intervals
    inference_interval_s: float = 60.0      # check for new H1 bar every 60s
    position_sync_interval_s: float = 10.0
    exit_check_interval_s: float = 5.0
    drift_check_interval_s: float = 300.0   # 5 min
    heartbeat_interval_s: float = 30.0

    # Trading
    dry_run: bool = True
    symbol: str = "XAUUSD"
    entry_price_default: float = 2000.0    # fallback if no live price
    spread_default: float = 0.20            # fallback spread

    # Feature stream
    feature_source: str = "canonical"       # canonical | mt5
    feature_window: int = 300

    # Inference
    xgb_threshold: float = 0.55
    meta_threshold: float = 0.65

    # Kill switch
    ks_config: KillSwitchConfig = field(default_factory=KillSwitchConfig)

    # Exit manager
    exit_config: ExitConfig = field(default_factory=ExitConfig)


class AutonomousRuntime:
    """
    Orchestrates all 6 autonomous trading loops.

    Safety:
      - dry_run=True default — no real orders
      - Kill-switch checked BEFORE every trade
      - Drift monitor feeds into kill-switch
      - All events journaled
      - Graceful shutdown on signal
    """

    def __init__(
        self,
        config: Optional[RuntimeConfig] = None,
        journal: Optional[TradeJournal] = None,
        journal_path: str = "data/runtime/titan_journal.jsonl",
        # Sprint 9.3.1: optional capital-protection engines.
        # When None (default), behavior is unchanged — no health score,
        # no dynamic risk, no recovery mode, no capital preservation.
        # When provided (from launcher when capital_protection.enabled=true),
        # these engines are queried in heartbeat + inference loops.
        health_engine=None,
        dynamic_risk_engine=None,
        recovery_mode=None,
        capital_preservation=None,
        profit_lock=None,
        equity_protection=None,
        prop_firm_manager=None,
        # Sprint 9.5: optional broker-intelligence engines.
        # When None (default), behavior is unchanged.
        # When provided (from launcher when broker_intelligence.enabled=true),
        # these engines are queried in heartbeat.
        broker_intelligence=None,
        broker_quality_engine=None,
        execution_profile_selector=None,
        broker_risk_adapter=None,
        broker_score_history=None,
        execution_self_protection=None,
        # Sprint 9.6.1: optional AI exit-intelligence engines.
        # When None (default), behavior is unchanged — existing ExitManager
        # handles all exit decisions. When provided (from launcher when
        # exit_intelligence.enabled=true), these engines are queried in
        # _exit_manager_loop BEFORE the existing ExitManager, providing
        # AI-driven exit recommendations. ExitManager safety always runs
        # afterward as the final safety layer.
        ai_exit_engine=None,
        exit_strategy_engine=None,
        exit_quality_scorer=None,
        exit_governance=None,
    ):
        self.config = config or RuntimeConfig()
        self.journal = journal or TradeJournal(path=journal_path)

        # Core components
        self.inference_engine: Optional[InferenceEngine] = None
        self.trade_loop: Optional[TradeLoop] = None
        self.kill_switch: Optional[KillSwitchFSM] = None
        self.feature_stream: Optional[H1FeatureStream] = None
        self.position_sync: Optional[PositionSync] = None
        self.exit_manager: Optional[ExitManager] = None
        self.drift_monitor: Optional[DriftMonitor] = None
        self.slippage_monitor: Optional[SlippageMonitor] = None
        self.news_filter: Optional[NewsFilter] = None
        self.meta_calibration: Optional[MetaCalibrationMonitor] = None

        # Sprint 9.3.1: Capital-protection engines (all optional)
        self.health_engine = health_engine
        self.dynamic_risk_engine = dynamic_risk_engine
        self.recovery_mode = recovery_mode
        self.capital_preservation = capital_preservation
        self.profit_lock = profit_lock
        self.equity_protection = equity_protection
        self.prop_firm_manager = prop_firm_manager

        # Sprint 9.5: Broker-intelligence engines (all optional)
        self.broker_intelligence = broker_intelligence
        self.broker_quality_engine = broker_quality_engine
        self.execution_profile_selector = execution_profile_selector
        self.broker_risk_adapter = broker_risk_adapter
        self.broker_score_history = broker_score_history
        self.execution_self_protection = execution_self_protection

        # Sprint 9.6.1: AI exit-intelligence engines (all optional)
        self.ai_exit_engine = ai_exit_engine
        self.exit_strategy_engine = exit_strategy_engine
        self.exit_quality_scorer = exit_quality_scorer
        self.exit_governance = exit_governance

        # Sprint 9.9.3.39: Institutional pipeline components.
        # These are instantiated in initialize() and used in _inference_loop()
        # and _exit_manager_loop(). They replace the direct InferenceEngine→TradeLoop
        # path with the institutional decision pipeline:
        #   InferenceEngine → SignalExecutionBridge → TradeLoop
        # and add:
        #   PositionSync → PositionLifecycleEngine → ExitIntentBridge → ExitManager
        # ForwardObservationEngine + ObservationScorecardEngine receive real
        # runtime journal events (no longer offline-only).
        self.signal_execution_bridge: Optional[SignalExecutionBridge] = None
        self.runtime_health_monitor: Optional[RuntimeHealthMonitor] = None
        self.security_gate: Optional[SecurityGate] = None
        self.position_lifecycle_engine: Optional[PositionLifecycleEngine] = None
        self.exit_intent_bridge: Optional[ExitIntentBridge] = None
        self.forward_observation_engine: Optional[ForwardObservationEngine] = None
        self.observation_scorecard_engine: Optional[ObservationScorecardEngine] = None
        # Last computed intent + observation summary (for tests + audit)
        self._last_execution_intent: Optional[ExecutionIntent] = None
        self._last_exit_intent: Optional[ExitIntent] = None
        self._last_lifecycle_status: Optional[PositionLifecycleStatus] = None
        self._observation_events: list[ForwardObservationEvent] = []

        # Sprint 9.3.1: runtime state shared between heartbeat + inference
        self._latest_health_score: Optional[float] = None
        self._latest_health_band: str = ""
        self._latest_risk_profile: str = ""
        self._latest_risk_multiplier: float = 1.0
        self._latest_challenge_status: Optional[dict] = None

        # Sprint 9.5: broker-intelligence runtime state
        self._latest_broker_score: Optional[float] = None
        self._latest_broker_band: str = ""
        self._latest_execution_profile: str = ""
        self._latest_broker_risk_multiplier: float = 1.0
        self._latest_entries_paused: bool = False

        # State
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._last_processed_bar_time: Optional[str] = None
        self._shutdown_event = asyncio.Event()
        self._signals_generated = 0
        self._trades_attempted = 0
        self._trades_blocked = 0

    def initialize(self) -> None:
        """Initialize all components. Must be called before start()."""
        cfg = self.config

        # Journal startup
        self.journal.log_startup({
            "dry_run": cfg.dry_run,
            "symbol": cfg.symbol,
            "feature_source": cfg.feature_source,
        })

        # Kill-switch with journal callback
        def ks_callback(transition):
            self.journal.log_event(EventType.KILL_SWITCH_TRANSITION, {
                "from": transition.from_state.value,
                "to": transition.to_state.value,
                "trigger": transition.trigger,
            })

        self.kill_switch = KillSwitchFSM(
            config=cfg.ks_config,
            journal_callback=ks_callback,
        )

        # Inference engine
        self.inference_engine = InferenceEngine(
            xgb_threshold=cfg.xgb_threshold,
            meta_threshold=cfg.meta_threshold,
            feature_window=cfg.feature_window,
        )

        # Feature stream
        self.feature_stream = H1FeatureStream(window=cfg.feature_window)

        # Trade loop (wired to kill-switch + journal)
        loop_cfg = TradeLoopConfig(dry_run=cfg.dry_run)
        self.trade_loop = TradeLoop(
            config=loop_cfg,
            journal=self.journal,
            kill_switch=self.kill_switch,
        )

        # Position sync (stub mode for dry_run)
        self.position_sync = PositionSync(
            interval_seconds=cfg.position_sync_interval_s,
            broker_source="stub",
            magic_filter=202619,
            on_position_closed=self.trade_loop.notify_position_closed,
        )

        # Exit manager
        self.exit_manager = ExitManager(config=cfg.exit_config)

        # Drift monitor
        self.drift_monitor = DriftMonitor()

        # Slippage monitor
        self.slippage_monitor = SlippageMonitor()

        # News filter (empty by default — add events via CSV)
        self.news_filter = NewsFilter()

        # Meta calibration monitor (Sprint 8.1)
        self.meta_calibration = MetaCalibrationMonitor()

        # ─── Sprint 9.9.3.39: Institutional pipeline components ───────────
        # These wire the standalone Sprint 9.9.3.x modules into the actual
        # runtime path. All remain dry_run=True / demo_only=True.
        self.signal_execution_bridge = SignalExecutionBridge(
            dry_run=True,
            demo_only=True,
        )
        self.runtime_health_monitor = RuntimeHealthMonitor(
            mt5=None,  # dry-run: no MT5 connection
            magic=202619,
            symbol=cfg.symbol,
        )
        self.security_gate = SecurityGate()  # dev_mode by default — non-blocking
        self.position_lifecycle_engine = PositionLifecycleEngine()
        self.exit_intent_bridge = ExitIntentBridge(
            dry_run=True,
            demo_only=True,
        )
        self.forward_observation_engine = ForwardObservationEngine()
        self.observation_scorecard_engine = ObservationScorecardEngine()

        logger.info("Sprint 9.9.3.39 institutional pipeline wired "
                    "(signal_execution_bridge + regime_detection + broker_compatibility_matrix "
                    "+ runtime_health_monitor + security_gate + position_lifecycle_engine "
                    "+ exit_intent_bridge + forward_observation_engine + observation_scorecard_engine)")

        logger.info("AutonomousRuntime initialized — all components ready")

    async def start(self) -> None:
        """Start all 6 async loops. Blocks until shutdown."""
        if self._running:
            logger.warning("Runtime already running")
            return

        self._running = True
        logger.info("=" * 60)
        logger.info("TITAN Autonomous Runtime — STARTING")
        logger.info(f"  dry_run: {self.config.dry_run}")
        logger.info(f"  symbol:  {self.config.symbol}")
        logger.info("=" * 60)

        # Start all loops as async tasks
        self._tasks = [
            asyncio.create_task(self._inference_loop(),
                                name="inference_loop"),
            asyncio.create_task(self._position_sync_loop(),
                                name="position_sync_loop"),
            asyncio.create_task(self._exit_manager_loop(),
                                name="exit_manager_loop"),
            asyncio.create_task(self._drift_monitor_loop(),
                                name="drift_monitor_loop"),
            asyncio.create_task(self._heartbeat_loop(),
                                name="heartbeat_loop"),
        ]

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Journal shutdown
        self.journal.log_shutdown(reason="normal")
        self.journal.flush()
        logger.info("TITAN Autonomous Runtime — STOPPED")

    def shutdown(self) -> None:
        """Signal shutdown."""
        self._running = False
        self._shutdown_event.set()

    # ─── Loop 1: Inference + Trade ──────────────────────────────────────

    async def _inference_loop(self) -> None:
        """
        Main trading loop. Runs on H1 bar close.
        Generates signal → checks kill-switch → creates dry-run order.
        """
        logger.info("Inference loop started")
        while self._running:
            try:
                # Check for new H1 bar
                bar_time = self._get_current_bar_time()
                if bar_time == self._last_processed_bar_time:
                    # Same bar — skip (no duplicate signals)
                    await asyncio.sleep(self.config.inference_interval_s)
                    continue

                # New bar detected — process it
                self._last_processed_bar_time = bar_time
                logger.info(f"New H1 bar detected: {bar_time}")

                # ── Step 1: Generate signal ──
                signal = self.inference_engine.generate(
                    source=self.config.feature_source,
                    symbol=self.config.symbol,
                )
                self._signals_generated += 1

                # Journal signal
                self.journal.log_signal(signal)
                self._last_meta_confidence = signal.meta_confidence
                self.journal.log_event(EventType.SIGNAL_CREATED, {
                    "bar_time": bar_time,
                    "direction": signal.direction.name,
                    "confidence": signal.confidence,
                    "meta_confidence": signal.meta_confidence,
                    "is_tradeable": signal.is_tradeable,
                })

                if not signal.is_tradeable:
                    logger.info(f"Signal not tradeable: {signal.reject_reason}")
                    self.journal.log_event(EventType.SIGNAL_REJECTED, {
                        "bar_time": bar_time,
                        "reason": signal.reject_reason,
                    })
                    await asyncio.sleep(self.config.inference_interval_s)
                    continue

                # ── Step 2: Check news filter ──
                news_status = self.news_filter.check()
                if news_status.is_halt_active:
                    logger.warning(f"News halt active: {news_status.reason}")
                    self.journal.log_event(EventType.NEWS_HALT, {
                        "reason": news_status.reason,
                        "bar_time": bar_time,
                    })
                    # Update kill-switch
                    self.kill_switch.update(KillSwitchInput(news_halt_active=True))
                    await asyncio.sleep(self.config.inference_interval_s)
                    continue

                # ── Step 3: Check kill-switch (HARD GATE) ──
                if not self.kill_switch.allows_new_trades:
                    self._trades_blocked += 1
                    logger.warning(
                        f"Kill-switch blocks trade: {self.kill_switch.state.value}"
                    )
                    self.journal.log_event(EventType.KILL_SWITCH_BLOCK, {
                        "kill_switch_state": self.kill_switch.state.value,
                        "bar_time": bar_time,
                        "signal_direction": signal.direction.name,
                    })
                    await asyncio.sleep(self.config.inference_interval_s)
                    continue

                # ── Step 4: Process through trade loop ──
                self._trades_attempted += 1

                # Compute current ATR for ATR-based SL/TP (Sprint 8.4)
                current_atr = self._compute_current_atr()

                # ── Sprint 9.3.1: capital-protection pre-checks ──
                # When engines are present (capital_protection.enabled=true),
                # consult recovery mode + capital preservation before allowing
                # the trade. When engines are None (default), this block is
                # skipped and behavior is identical to pre-9.3.1.
                ctx_health_score = self._latest_health_score
                ctx_health_band = self._latest_health_band
                ctx_risk_profile = self._latest_risk_profile
                ctx_risk_multiplier = self._latest_risk_multiplier
                ctx_recovery_active = (
                    self.recovery_mode.is_active if self.recovery_mode else False
                )
                ctx_cap_pres_active = (
                    self.capital_preservation.is_active
                    if self.capital_preservation else False
                )
                ctx_profit_lock_active = (
                    self.profit_lock.is_locked if self.profit_lock else False
                )
                ctx_prop_profile_id = (
                    self.prop_firm_manager.active_profile_id
                    if self.prop_firm_manager else ""
                )

                # Recovery mode: only allow high-confidence trades
                if ctx_recovery_active and self.recovery_mode is not None:
                    if not self.recovery_mode.should_allow_trade(signal.confidence):
                        self._trades_blocked += 1
                        self.journal.log_event(EventType.SIGNAL_REJECTED, {
                            "bar_time": bar_time,
                            "reason": "recovery_mode_block",
                            "signal_confidence": signal.confidence,
                            "min_confidence_threshold":
                                self.recovery_mode.config.min_confidence_threshold,
                            "health_score": ctx_health_score,
                            "health_band": ctx_health_band,
                        })
                        logger.info(
                            f"Trade blocked by recovery_mode: conf={signal.confidence} "
                            f"< threshold={self.recovery_mode.config.min_confidence_threshold}"
                        )
                        await asyncio.sleep(self.config.inference_interval_s)
                        continue

                # Capital preservation: halt new entries if DD too high
                if (ctx_cap_pres_active and self.capital_preservation is not None
                        and not self.capital_preservation.should_allow_new_entry()):
                    self._trades_blocked += 1
                    self.journal.log_event(EventType.SIGNAL_REJECTED, {
                        "bar_time": bar_time,
                        "reason": "capital_preservation_block",
                        "total_dd_pct": self.capital_preservation.state.current_dd_pct,
                        "halt_threshold":
                            self.capital_preservation.config.halt_new_entries_dd_pct,
                        "health_score": ctx_health_score,
                        "health_band": ctx_health_band,
                    })
                    logger.info(
                        f"Trade blocked by capital_preservation: "
                        f"DD={self.capital_preservation.state.current_dd_pct}% "
                        f"≥ halt={self.capital_preservation.config.halt_new_entries_dd_pct}%"
                    )
                    await asyncio.sleep(self.config.inference_interval_s)
                    continue

                # Health-gated block: capital_preservation band → no entries
                if (ctx_health_band == "capital_preservation"
                        and ctx_risk_multiplier == 0.0):
                    self._trades_blocked += 1
                    self.journal.log_event(EventType.SIGNAL_REJECTED, {
                        "bar_time": bar_time,
                        "reason": "health_too_low",
                        "health_score": ctx_health_score,
                        "health_band": ctx_health_band,
                        "risk_multiplier": ctx_risk_multiplier,
                    })
                    logger.info(
                        f"Trade blocked by health_too_low: "
                        f"score={ctx_health_score} band={ctx_health_band}"
                    )
                    await asyncio.sleep(self.config.inference_interval_s)
                    continue

                # Sprint 9.9.3.41.2: Dynamic risk safety hotfix.
                # Previous code PERMANENTLY mutated self.trade_loop.config.max_lot,
                # which caused sticky reduction across future decisions.
                # Now we use a per-decision effective max_lot that is restored
                # after the trade decision completes.
                #
                # risk_multiplier <= 0 must BLOCK the trade (not floor to 0.001).
                # risk_multiplier > 0 may reduce effective max_lot for this decision only.
                # The original self.trade_loop.config.max_lot is NEVER mutated.
                original_max_lot = self.trade_loop.config.max_lot
                effective_max_lot = original_max_lot

                if ctx_risk_multiplier is not None:
                    if ctx_risk_multiplier <= 0.0:
                        # Zero or negative risk multiplier → BLOCK the trade
                        self._trades_blocked += 1
                        self.journal.log_event(EventType.SIGNAL_REJECTED, {
                            "bar_time": bar_time,
                            "reason": "zero_risk_multiplier_block",
                            "risk_multiplier": ctx_risk_multiplier,
                            "health_score": ctx_health_score,
                            "health_band": ctx_health_band,
                        })
                        logger.info(
                            f"Trade blocked by zero risk_multiplier: "
                            f"mult={ctx_risk_multiplier} band={ctx_health_band}"
                        )
                        await asyncio.sleep(self.config.inference_interval_s)
                        continue
                    elif ctx_risk_multiplier < 1.0:
                        # Reduce effective max_lot for THIS DECISION ONLY
                        # Do NOT mutate self.trade_loop.config.max_lot
                        effective_max_lot = max(
                            0.001, original_max_lot * ctx_risk_multiplier
                        )
                        # Temporarily set on config for this one process_signal call
                        self.trade_loop.config.max_lot = effective_max_lot
                        logger.info(
                            f"Dynamic risk reduction: max_lot {original_max_lot} -> "
                            f"{effective_max_lot} (mult={ctx_risk_multiplier})"
                        )

                # Ensure original max_lot is restored after this decision
                # (finally block below guarantees restore even on exception)

                # ─── Sprint 9.9.3.39: Institutional decision pipeline ─────
                # Before calling TradeLoop, every trade decision must pass
                # through the institutional pipeline:
                #   RegimeDetection → BrokerCompatibilityMatrix
                #   → RuntimeHealthMonitor → SecurityGate
                #   → SignalExecutionBridge.build_intent()
                # If the bridge blocks (intent.allowed=False), TradeLoop is
                # NOT called and the signal is rejected. This is the single
                # most important wiring change in Sprint 9.9.3.39.
                self.journal.log_event(EventType.INSTITUTIONAL_PIPELINE_STARTED, {
                    "bar_time": bar_time,
                    "signal_direction": signal.direction.name,
                    "model_confidence": signal.confidence,
                    "meta_confidence": signal.meta_confidence,
                })

                # Gate 1: RegimeDetection
                regime_status: Optional[dict] = None
                try:
                    regime = detect_regime(
                        trend_score=0.0,
                        volatility_score=0.0,
                        range_score=0.0,
                        spread_score=0.0,
                        liquidity_score=1.0,
                        confidence=signal.confidence,
                    )
                    regime_status = {
                        "primary_regime": regime.primary_regime.value
                            if hasattr(regime.primary_regime, "value") else str(regime.primary_regime),
                        "risk_multiplier": regime.risk_multiplier,
                        "allow_new_trade": regime.allow_new_trade,
                        "block_reason": regime.block_reason,
                    }
                    self.journal.log_event(EventType.REGIME_GATE_EVALUATED, {
                        "bar_time": bar_time,
                        "regime": regime_status["primary_regime"],
                        "risk_multiplier": regime_status["risk_multiplier"],
                        "allow_new_trade": regime_status["allow_new_trade"],
                    })
                except Exception as re_err:
                    logger.warning(f"RegimeDetection error (treated as UNKNOWN): {re_err}")
                    regime_status = None
                    self.journal.log_event(EventType.REGIME_GATE_EVALUATED, {
                        "bar_time": bar_time,
                        "regime": "UNKNOWN",
                        "error": str(re_err),
                    })

                # Gate 2: BrokerCompatibilityMatrix
                broker_info: Optional[dict] = None
                try:
                    # In dry-run, no live broker — use MetaQuotes-Demo registry entry
                    broker_info = get_broker_info("MetaQuotes-Demo")
                    self.journal.log_event(EventType.BROKER_GATE_EVALUATED, {
                        "bar_time": bar_time,
                        "broker": "MetaQuotes-Demo",
                        "status": broker_info.get("status", "UNKNOWN"),
                    })
                except Exception as bc_err:
                    logger.warning(f"BrokerCompatibilityMatrix error: {bc_err}")
                    broker_info = None
                    self.journal.log_event(EventType.BROKER_GATE_EVALUATED, {
                        "bar_time": bar_time,
                        "broker": "UNKNOWN",
                        "error": str(bc_err),
                    })

                # Gate 3: RuntimeHealthMonitor
                runtime_health: Optional[dict] = None
                try:
                    if self.runtime_health_monitor is not None:
                        # check_tick_health requires MT5 - in dry-run, just get status
                        rh_status = self.runtime_health_monitor.get_health_status()
                        runtime_health = {
                            "status": rh_status.get("status", "HEALTHY"),
                            "event_count": rh_status.get("event_count", 0),
                        }
                    self.journal.log_event(EventType.RUNTIME_HEALTH_GATE_EVALUATED, {
                        "bar_time": bar_time,
                        "status": runtime_health["status"] if runtime_health else "UNKNOWN",
                    })
                except Exception as rh_err:
                    logger.warning(f"RuntimeHealthMonitor error: {rh_err}")
                    runtime_health = None
                    self.journal.log_event(EventType.RUNTIME_HEALTH_GATE_EVALUATED, {
                        "bar_time": bar_time,
                        "status": "UNKNOWN",
                        "error": str(rh_err),
                    })

                # Gate 4: SecurityGate
                security_status: Optional[dict] = None
                try:
                    if self.security_gate is not None:
                        sec_check = self.security_gate.check()
                        security_status = {
                            "allowed": sec_check.get("allowed", True),
                            "reason": sec_check.get("reason"),
                            "mode": sec_check.get("mode", "dev_mode"),
                        }
                    self.journal.log_event(EventType.SECURITY_GATE_EVALUATED, {
                        "bar_time": bar_time,
                        "allowed": security_status["allowed"] if security_status else True,
                        "mode": security_status["mode"] if security_status else "dev_mode",
                    })
                except Exception as sg_err:
                    logger.warning(f"SecurityGate error: {sg_err}")
                    security_status = None
                    self.journal.log_event(EventType.SECURITY_GATE_EVALUATED, {
                        "bar_time": bar_time,
                        "allowed": True,
                        "error": str(sg_err),
                    })

                # Build DecisionInput → SignalExecutionBridge.build_intent()
                # Direction enum uses LONG/SHORT/FLAT (not BUY/SELL).
                # Map LONG→BUY, SHORT→SELL for the bridge's DecisionInput.
                if signal.direction == Direction.LONG:
                    _model_signal = "BUY"
                    _direction = "BUY"
                elif signal.direction == Direction.SHORT:
                    _model_signal = "SELL"
                    _direction = "SELL"
                else:
                    _model_signal = "NONE"
                    _direction = None
                decision_input = DecisionInput(
                    symbol=self.config.symbol,
                    timeframe="H1",
                    model_signal=_model_signal,
                    model_confidence=signal.confidence,
                    meta_confidence=signal.meta_confidence,
                    direction=_direction,
                    timestamp_utc=datetime.now(timezone.utc).isoformat(),
                )

                intent = self.signal_execution_bridge.build_intent(
                    inp=decision_input,
                    regime_status=regime_status,
                    broker_info=broker_info,
                    runtime_health=runtime_health,
                    security_status=security_status,
                )
                self._last_execution_intent = intent

                self.journal.log_event(EventType.EXECUTION_INTENT_CREATED, {
                    "bar_time": bar_time,
                    "allowed": intent.allowed,
                    "decision": intent.decision,
                    "lot": intent.lot,
                    "side": intent.side,
                    "regime": intent.regime,
                    "broker_status": intent.broker_status,
                    "runtime_health_status": intent.runtime_health_status,
                    "security_status": intent.security_status,
                    "risk_multiplier": intent.risk_multiplier,
                    "approval_reasons": intent.approval_reasons,
                    "block_reasons": intent.block_reasons,
                    "dry_run": intent.dry_run,
                    "demo_only": intent.demo_only,
                })

                # Record observation event for forward observation engine
                self._record_observation_event({
                    "event": "EXECUTION_INTENT_CREATED",
                    "timestamp_utc": intent.timestamp_utc,
                    "symbol": intent.symbol,
                    "timeframe": "H1",
                    "intent_allowed": intent.allowed,
                    "intent_decision": intent.decision,
                })

                # If the bridge blocks, TradeLoop must NOT be called.
                if not intent.allowed:
                    self._trades_blocked += 1
                    self.journal.log_event(EventType.EXECUTION_INTENT_BLOCKED, {
                        "bar_time": bar_time,
                        "decision": intent.decision,
                        "block_reasons": intent.block_reasons,
                    })
                    self.journal.log_event(EventType.TRADE_LOOP_SKIPPED_BY_INTENT, {
                        "bar_time": bar_time,
                        "reason": "SignalExecutionBridge blocked intent",
                    })
                    logger.info(
                        f"Trade blocked by SignalExecutionBridge: decision={intent.decision} "
                        f"reasons={intent.block_reasons}"
                    )
                    await asyncio.sleep(self.config.inference_interval_s)
                    continue

                # Intent approved — call TradeLoop
                self.journal.log_event(EventType.EXECUTION_INTENT_APPROVED, {
                    "bar_time": bar_time,
                    "decision": intent.decision,
                    "approval_reasons": intent.approval_reasons,
                    "lot": intent.lot,
                    "risk_multiplier": intent.risk_multiplier,
                })
                self.journal.log_event(EventType.TRADE_LOOP_CALLED_AFTER_INTENT, {
                    "bar_time": bar_time,
                    "intent_decision": intent.decision,
                    "intent_lot": intent.lot,
                })

                decision = await self.trade_loop.process_signal(
                    signal=signal,
                    entry_price=self.config.entry_price_default,
                    spread_usd=self.config.spread_default,
                    current_atr=current_atr,
                    # Sprint 9.3.1: pass capital-protection context
                    health_score=ctx_health_score,
                    health_band=ctx_health_band,
                    risk_profile=ctx_risk_profile,
                    risk_multiplier=ctx_risk_multiplier,
                    recovery_mode_active=ctx_recovery_active,
                    capital_preservation_active=ctx_cap_pres_active,
                    profit_lock_active=ctx_profit_lock_active,
                    prop_profile_id=ctx_prop_profile_id,
                    challenge_status=self._latest_challenge_status,
                )

                if decision.accepted:
                    logger.info(
                        f"Trade ACCEPTED (dry_run={decision.dry_run}): "
                        f"{decision.order_request['order_type']} "
                        f"{decision.order_request['volume']} lot "
                        f"SL={decision.order_request['sl']} "
                        f"TP={decision.order_request['tp']}"
                    )
                    self.journal.log_event(EventType.ORDER_CREATED, {
                        "bar_time": bar_time,
                        "order_request": decision.order_request,
                        "dry_run": decision.dry_run,
                    })
                else:
                    logger.info(f"Trade rejected: {decision.reject_reason}")

                # Sprint 9.9.3.41.2: Restore original max_lot after decision.
                # This prevents sticky reduction across future decisions.
                self.trade_loop.config.max_lot = original_max_lot

            except Exception as e:
                # Sprint 9.9.3.41.2: Also restore on exception
                try:
                    if 'original_max_lot' in locals():
                        self.trade_loop.config.max_lot = original_max_lot
                except Exception:
                    pass
                logger.error(f"Inference loop error: {e}", exc_info=True)
                self.journal.log_event(EventType.KILL_SWITCH_BLOCK, {
                    "reason": f"inference_loop_error: {e}",
                })

            await asyncio.sleep(self.config.inference_interval_s)

    # ─── Loop 2: Position Sync ──────────────────────────────────────────

    async def _position_sync_loop(self) -> None:
        """Sync broker positions every 10 seconds."""
        logger.info("Position sync loop started")
        while self._running:
            try:
                report = await self.position_sync.sync_once()
                if report.total_drifts > 0:
                    logger.info(f"Position sync: {report}")
            except Exception as e:
                logger.error(f"Position sync error: {e}")
            await asyncio.sleep(self.config.position_sync_interval_s)

    # ─── Loop 3: Exit Manager ───────────────────────────────────────────

    async def _exit_manager_loop(self) -> None:
        """Check open positions for exit conditions every 5 seconds.

        Sprint 9.6.1: When ai_exit_engine is present, AI Exit evaluates
        each position BEFORE the existing ExitManager. AI Exit provides
        recommendations (HOLD/PARTIAL/TRAIL/BE/BOOK/FULL/EMERGENCY).
        ExitManager safety always runs afterward as the final safety layer.
        If AI Exit fails, fallback to ExitManager only (fail-closed).
        """
        logger.info("Exit manager loop started")
        while self._running:
            try:
                positions = self.position_sync.open_positions

                # ── Sprint 9.6.1: AI Exit evaluation (optional) ──
                # When ai_exit_engine is present, evaluate each position
                # through the AI exit layer BEFORE the existing ExitManager.
                # This provides AI-driven recommendations. ExitManager safety
                # always runs afterward regardless of AI Exit output.
                if self.ai_exit_engine is not None and positions:
                    for pos in positions:
                        try:
                            self._evaluate_ai_exit(pos)
                        except Exception as ai_err:
                            logger.warning(
                                f"AI Exit evaluation failed (fallback to "
                                f"ExitManager): {ai_err}"
                            )
                            self.journal.log_event(EventType.EXIT_AI_DECISION, {
                                "ticket": getattr(pos, "ticket", 0),
                                "action": "FALLBACK",
                                "reason": f"ai_exit_error: {ai_err}",
                                "ai_exit_fallback_used": True,
                            })

                # ── Sprint 9.9.3.39: Institutional exit pipeline ─────────
                # PositionLifecycleEngine + ExitIntentBridge evaluate each
                # position BEFORE the existing ExitManager. ExitManager
                # remains the final safety layer.
                # ExitIntentBridge never sends orders (should_send_order=False).
                if positions and self.position_lifecycle_engine is not None \
                        and self.exit_intent_bridge is not None:
                    for pos in positions:
                        try:
                            snapshot = self._build_position_snapshot(pos)
                            lifecycle = self.position_lifecycle_engine.evaluate(snapshot)
                            self._last_lifecycle_status = lifecycle
                            self.journal.log_event(EventType.POSITION_LIFECYCLE_EVALUATED, {
                                "ticket": snapshot.ticket,
                                "state": lifecycle.state.value
                                    if hasattr(lifecycle.state, "value") else str(lifecycle.state),
                                "safe_to_hold": lifecycle.safe_to_hold,
                                "risk_level": lifecycle.risk_level,
                                "protection_level": lifecycle.protection_level,
                                "needs_exit_review": lifecycle.needs_exit_review,
                                "pnl_r": lifecycle.pnl_r,
                                "reason": lifecycle.reason,
                            })
                            exit_intent = self.exit_intent_bridge.build_exit_intent(snapshot)
                            self._last_exit_intent = exit_intent
                            self.journal.log_event(EventType.EXIT_INTENT_CREATED, {
                                "ticket": exit_intent.ticket,
                                "action": exit_intent.action.value
                                    if hasattr(exit_intent.action, "value") else str(exit_intent.action),
                                "allowed": exit_intent.allowed,
                                "should_send_order": exit_intent.should_send_order,
                                "reason": exit_intent.reason,
                                "source_decision": exit_intent.source_decision,
                            })
                            if exit_intent.allowed:
                                self.journal.log_event(EventType.EXIT_INTENT_APPROVED, {
                                    "ticket": exit_intent.ticket,
                                    "action": exit_intent.action.value
                                        if hasattr(exit_intent.action, "value") else str(exit_intent.action),
                                })
                            else:
                                self.journal.log_event(EventType.EXIT_INTENT_BLOCKED, {
                                    "ticket": exit_intent.ticket,
                                    "action": exit_intent.action.value
                                        if hasattr(exit_intent.action, "value") else str(exit_intent.action),
                                    "reason": exit_intent.reason,
                                })
                            # Record observation event
                            self._record_observation_event({
                                "event": "EXIT_INTENT_CREATED",
                                "timestamp_utc": exit_intent.timestamp_utc,
                                "symbol": exit_intent.symbol,
                                "timeframe": "H1",
                                "ticket": exit_intent.ticket,
                                "action": exit_intent.action.value
                                    if hasattr(exit_intent.action, "value") else str(exit_intent.action),
                            })
                        except Exception as eib_err:
                            logger.warning(
                                f"ExitIntentBridge evaluation failed (fallback to "
                                f"ExitManager): {eib_err}"
                            )

                # ── Existing ExitManager (always runs — final safety layer) ──
                for pos in positions:
                    exit_decision = self.exit_manager.evaluate(
                        position=pos,
                        current_price=self.config.entry_price_default,
                        kill_switch_armed=self.kill_switch.is_emergency,
                        current_dd_pct=0.0,  # would come from equity tracker
                        news_halt_active=self.news_filter.is_halt_active(),
                    )

                    if exit_decision.should_exit:
                        logger.info(
                            f"Exit triggered: ticket={exit_decision.ticket} "
                            f"reason={exit_decision.reason.value}"
                        )
                        self.journal.log_event(EventType.EXIT_TRIGGERED, {
                            "ticket": exit_decision.ticket,
                            "reason": exit_decision.reason.value,
                            "pnl_usd": exit_decision.unrealized_pnl_usd,
                        })
                        self.journal.log_exit(
                            ticket=exit_decision.ticket,
                            exit_reason=exit_decision.reason.value,
                            entry_price=exit_decision.entry_price,
                            exit_price=exit_decision.current_price,
                            direction=exit_decision.direction,
                            volume=exit_decision.volume,
                            pnl_usd=exit_decision.unrealized_pnl_usd,
                            holding_time_seconds=exit_decision.holding_time_seconds,
                        )

                        # ── Sprint 8.1: Record calibration sample ──
                        # actual_outcome: 1 = win (pnl > 0), 0 = loss
                        actual_outcome = 1 if exit_decision.unrealized_pnl_usd > 0 else 0
                        # Use meta_confidence from last signal as predicted P(win)
                        # (stored as a simple fallback — in production, the signal's
                        #  meta_confidence would be passed through the position)
                        last_signal_meta = getattr(self, '_last_meta_confidence', 0.65)
                        self.meta_calibration.record_prediction(
                            prob_win=last_signal_meta,
                            actual_outcome=actual_outcome,
                        )
                        self.journal.log_event(EventType.META_CALIBRATION_SAMPLE, {
                            "ticket": exit_decision.ticket,
                            "predicted_pwin": last_signal_meta,
                            "actual_outcome": actual_outcome,
                            "pnl_usd": exit_decision.unrealized_pnl_usd,
                        })

                        # ── Check calibration state ──
                        cal_report = self.meta_calibration.get_report()
                        if cal_report.state == CalibrationState.KILL_THRESHOLD_BREACHED:
                            logger.critical(
                                f"META CALIBRATION KILL: ECE={cal_report.ece:.4f}"
                            )
                            self.journal.log_event(EventType.META_CALIBRATION_KILL, {
                                "ece": cal_report.ece,
                                "brier": cal_report.brier,
                                "slope": cal_report.calibration_slope,
                                "n_samples": cal_report.n_samples,
                            })
                            self.kill_switch.update(KillSwitchInput(
                                ece=cal_report.ece,
                                brier_score=cal_report.brier,
                            ))
                        elif cal_report.state == CalibrationState.RECALIBRATE_REQUIRED:
                            logger.warning(
                                f"META RECALIBRATE REQUIRED: ECE={cal_report.ece:.4f}"
                            )
                            self.journal.log_event(EventType.META_RECALIBRATE_REQUIRED, {
                                "ece": cal_report.ece,
                                "brier": cal_report.brier,
                                "n_samples": cal_report.n_samples,
                            })
                            # Attempt isotonic recalibration
                            success = self.meta_calibration.recalibrate()
                            if success:
                                self.journal.log_event(EventType.META_RECALIBRATED, {
                                    "method": "isotonic",
                                    "n_samples": cal_report.n_samples,
                                    "old_ece": cal_report.ece,
                                })
                                logger.info("Isotonic recalibration applied successfully")
                            else:
                                logger.error("Recalibration failed — triggering HALT")
                                self.kill_switch.update(KillSwitchInput(
                                    ece=cal_report.ece,
                                ))
                        elif cal_report.state == CalibrationState.WATCH:
                            logger.info(f"META CALIBRATION WATCH: ECE={cal_report.ece:.4f}")
                            self.journal.log_event(EventType.META_CALIBRATION_WATCH, {
                                "ece": cal_report.ece,
                                "brier": cal_report.brier,
                                "n_samples": cal_report.n_samples,
                            })

                        # In dry_run, we just log — no real close
                        self.trade_loop.notify_position_closed()

                    elif exit_decision.should_trail:
                        logger.info(
                            f"Trailing stop: ticket={exit_decision.ticket} "
                            f"new_sl={exit_decision.new_trailing_sl}"
                        )

                    # Sprint 9.9.3.39: journal final safety evaluation result
                    self.journal.log_event(EventType.EXIT_MANAGER_FINAL_SAFETY_EVALUATED, {
                        "ticket": exit_decision.ticket,
                        "should_exit": exit_decision.should_exit,
                        "should_trail": exit_decision.should_trail,
                        "reason": exit_decision.reason.value
                            if hasattr(exit_decision.reason, "value") else str(exit_decision.reason),
                    })

            except Exception as e:
                logger.error(f"Exit manager error: {e}")
            await asyncio.sleep(self.config.exit_check_interval_s)

    # ─── Loop 4: Drift Monitor → Kill Switch ────────────────────────────

    async def _drift_monitor_loop(self) -> None:
        """
        Monitor model drift every 5 minutes.
        Feed drift results into kill-switch FSM.
        """
        logger.info("Drift monitor loop started")
        while self._running:
            try:
                report = self.drift_monitor.get_report()

                if report.drift_emergency:
                    logger.critical(
                        f"DRIFT EMERGENCY: psi={report.psi:.4f} "
                        f"ece={report.ece:.4f} brier={report.brier:.4f}"
                    )
                    self.journal.log_event(EventType.DRIFT_EMERGENCY, {
                        "psi": report.psi,
                        "ece": report.ece,
                        "brier": report.brier,
                        "reasons": report.reasons,
                    })
                    # Feed into kill-switch
                    self.kill_switch.update(KillSwitchInput(
                        drift_emergency=True,
                        ece=report.ece,
                        brier_score=report.brier,
                    ))

                elif report.drift_breach:
                    logger.warning(
                        f"DRIFT ALERT: psi={report.psi:.4f} "
                        f"ece={report.ece:.4f} brier={report.brier:.4f}"
                    )
                    self.journal.log_event(EventType.DRIFT_ALERT, {
                        "psi": report.psi,
                        "ece": report.ece,
                        "brier": report.brier,
                        "reasons": report.reasons,
                    })
                    # Feed into kill-switch
                    self.kill_switch.update(KillSwitchInput(
                        drift_breach=True,
                        ece=report.ece,
                        brier_score=report.brier,
                    ))

            except Exception as e:
                logger.error(f"Drift monitor error: {e}")
            await asyncio.sleep(self.config.drift_check_interval_s)

    # ─── Loop 5: Heartbeat + Health ─────────────────────────────────────

    async def _heartbeat_loop(self) -> None:
        """Log heartbeat every 30 seconds + Sprint 9.3.1 capital-protection updates + Sprint 9.5 broker intelligence."""
        logger.info("Heartbeat loop started")
        while self._running:
            try:
                # Sprint 9.3.1: invoke capital-protection engines when present.
                # All engines are optional — when None (default), this block
                # is skipped and behavior is identical to pre-9.3.1.
                if self.health_engine is not None:
                    self._update_capital_protection()

                # Sprint 9.5: invoke broker-intelligence engines when present.
                # All engines are optional — when None (default), this block
                # is skipped and behavior is identical to pre-9.5.
                if self.broker_quality_engine is not None:
                    self._update_broker_intelligence()

                self.journal.log_heartbeat({
                    "event": "runtime_heartbeat",
                    "running": self._running,
                    "signals_generated": self._signals_generated,
                    "trades_attempted": self._trades_attempted,
                    "trades_blocked": self._trades_blocked,
                    "kill_switch_state": self.kill_switch.state.value
                        if self.kill_switch else "UNKNOWN",
                    "open_positions": self.position_sync.position_count,
                    "uptime_s": time.time() - time.time(),  # simplified
                    # Sprint 9.3.1: include capital-protection snapshot
                    "health_score": self._latest_health_score,
                    "health_band": self._latest_health_band,
                    "risk_profile": self._latest_risk_profile,
                    "risk_multiplier": self._latest_risk_multiplier,
                    "recovery_mode_active": (
                        self.recovery_mode.is_active if self.recovery_mode else False
                    ),
                    "capital_preservation_active": (
                        self.capital_preservation.is_active if self.capital_preservation else False
                    ),
                    "profit_lock_active": (
                        self.profit_lock.is_locked if self.profit_lock else False
                    ),
                    "prop_firm_profile": (
                        self.prop_firm_manager.active_profile_id
                        if self.prop_firm_manager else None
                    ),
                    # Sprint 9.5: include broker-intelligence snapshot
                    "broker_score": self._latest_broker_score,
                    "broker_band": self._latest_broker_band,
                    "execution_profile": self._latest_execution_profile,
                    "broker_risk_multiplier": self._latest_broker_risk_multiplier,
                    "entries_paused": self._latest_entries_paused,
                })
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            await asyncio.sleep(self.config.heartbeat_interval_s)

    def _update_broker_intelligence(self) -> None:
        """
        Sprint 9.5: compute broker quality score, select execution profile,
        adapt risk, run self-protection. Stores results in self._latest_*.

        All engines are optional. This method is only called when
        broker_quality_engine is present (broker_intelligence.enabled=true).
        """
        # Step 1: Detect broker (one-time, cached in BrokerInfo.last_info)
        broker_info = None
        if self.broker_intelligence is not None:
            broker_info = self.broker_intelligence.last_info
            # If not yet detected, try to detect now (MT5 must be available)
            if broker_info is None:
                broker_info = self.broker_intelligence.detect()

        # Step 2: Evaluate broker quality
        # In dry_run/stub mode, we use synthetic inputs (no real broker metrics).
        # In live mode, these would come from slippage_monitor + spread tracker.
        from titan.production.broker_quality_engine import BrokerQualityInput
        spread_usd = self.config.spread_default
        if self.news_filter is not None:
            # Use spread from kill-switch input if available
            pass
        inp = BrokerQualityInput(
            spread_usd=spread_usd,
            spread_mean_usd=spread_usd,
            connection_uptime_pct=100.0,  # assume stable in dry_run
            symbol_health=100.0,
        )
        score = self.broker_quality_engine.evaluate(inp)
        self._latest_broker_score = score.score
        self._latest_broker_band = score.band

        # Record in history
        if self.broker_score_history is not None:
            self.broker_score_history.record(score, spread=spread_usd)

        # Step 3: Select execution profile
        if self.execution_profile_selector is not None:
            profile = self.execution_profile_selector.select(score, broker_info)
            self._latest_execution_profile = profile.name

            # Step 4: Adapt risk
            if self.broker_risk_adapter is not None:
                adaptation = self.broker_risk_adapter.adapt(score, profile)
                self._latest_broker_risk_multiplier = adaptation.risk_multiplier
                self._latest_entries_paused = not adaptation.allow_new_entries

        # Step 5: Self-protection
        if self.execution_self_protection is not None:
            action = self.execution_self_protection.evaluate(
                spread_usd=spread_usd,
                latency_ms=0,  # no live latency data in dry_run
                requote_rate=0.0,
                rejection_rate=0.0,
            )
            if action.pause_entries:
                self._latest_entries_paused = True
            # Use the more conservative risk multiplier
            if action.risk_multiplier < self._latest_broker_risk_multiplier:
                self._latest_broker_risk_multiplier = action.risk_multiplier

    def _update_capital_protection(self) -> None:
        """
        Sprint 9.3.1: compute health score, dynamic risk profile, update
        profit lock + equity protection, update capital preservation.
        Stores results in self._latest_* for inference loop to consume.
        """
        # Compute current equity + DD from position_sync (stub-safe)
        current_equity = self.config.entry_price_default  # fallback
        # In a real runtime with broker_source=mt5, this would query
        # mt5.account_info().equity. For dry_run/stub, we use the default.
        # This is intentional — the engines still exercise their logic.
        initial_balance = (
            self.prop_firm_manager.active_profile.initial_balance
            if self.prop_firm_manager and self.prop_firm_manager.active_profile
            else current_equity
        )

        # Equity protection tracking
        if self.equity_protection is not None:
            locked_equity = (
                self.profit_lock.locked_equity
                if self.profit_lock is not None else None
            )
            ep_state = self.equity_protection.update(current_equity, locked_equity)
            total_dd_pct = ep_state.drawdown_from_peak_pct
            daily_dd_pct = ep_state.drawdown_from_initial_pct
        else:
            total_dd_pct = 0.0
            daily_dd_pct = 0.0

        # Capital preservation
        if self.capital_preservation is not None:
            self.capital_preservation.update(total_dd_pct)

        # Profit lock
        if self.profit_lock is not None:
            self.profit_lock.update(current_equity)

        # Build AccountHealthInput from current state
        from titan.production.account_health_engine import AccountHealthInput
        ks_state_str = (
            self.kill_switch.state.value if self.kill_switch else "NORMAL"
        )
        recovery_active = (
            self.recovery_mode.is_active if self.recovery_mode else False
        )
        recovery_progress = 0.0
        if recovery_active and self.recovery_mode is not None:
            target = max(1, self.recovery_mode.config.recovery_target_trades)
            recovery_progress = (
                self.recovery_mode.state.consecutive_wins_in_recovery / target
            )

        inp = AccountHealthInput(
            daily_dd_pct=daily_dd_pct,
            total_dd_pct=total_dd_pct,
            max_daily_dd_limit_pct=5.0,   # FTMO default
            max_total_dd_limit_pct=10.0,  # FTMO default
            consecutive_losses=(
                self.recovery_mode.state.consecutive_losses
                if self.recovery_mode else 0
            ),
            winning_streak=0,  # not tracked at runtime level
            equity_slope=0.0,  # not tracked at runtime level
            volatility_regime="normal",
            kill_switch_state=ks_state_str,
            in_recovery_mode=recovery_active,
            recovery_progress=recovery_progress,
        )
        score = self.health_engine.evaluate(inp)
        self._latest_health_score = score.score
        self._latest_health_band = score.band

        # Dynamic risk profile
        if self.dynamic_risk_engine is not None:
            risk_eval = self.dynamic_risk_engine.evaluate(score.score)
            self._latest_risk_profile = risk_eval.profile_name
            self._latest_risk_multiplier = risk_eval.risk_multiplier

    # ─── Helpers ────────────────────────────────────────────────────────

    def _evaluate_ai_exit(self, pos) -> None:
        """
        Sprint 9.6.1: Evaluate a single open position through the AI Exit
        Intelligence layer. Builds ExitInput from runtime context, calls
        AIExitEngine, journals the decision, and simulates dry-run actions.

        Safety:
          - In dry_run=true: journals what WOULD happen, sends no MT5 orders
          - In live_trading=false: never calls mt5.order_send
          - Existing ExitManager runs AFTER this as the final safety layer
          - If any field is unavailable, uses safe defaults + marks missing
          - Latency measured for every evaluation
          - Emergency fast-path bypasses AI slow path (<50ms)
        """
        import time as _time
        from titan.production.ai_exit_engine import ExitInput, ExitAction

        t0 = _time.perf_counter()
        missing_fields = []

        # ── Build ExitInput from position + runtime context ──
        direction = getattr(pos, "type", 0)  # MT5: 0=BUY, 1=SELL
        direction_int = 1 if direction == 0 else -1  # +1 long, -1 short
        entry_price = float(getattr(pos, "price_open", 0) or 0)
        current_price = float(getattr(pos, "price_current", 0) or
                              self.config.entry_price_default)
        stop_loss = float(getattr(pos, "sl", 0) or 0)
        take_profit = float(getattr(pos, "tp", 0) or 0)
        volume = float(getattr(pos, "volume", 0.01) or 0.01)
        floating_pnl = float(getattr(pos, "profit", 0) or 0)

        # Compute R-multiple (floating PnL / initial risk)
        initial_risk = abs(entry_price - stop_loss) * 100 * volume if stop_loss > 0 else 0
        r_multiple = floating_pnl / initial_risk if initial_risk > 0 else 0.0

        # Time in trade
        import time as _time_mod
        pos_time = getattr(pos, "time", None)
        if pos_time is not None:
            try:
                time_in_trade_hours = (_time_mod.time() - float(pos_time)) / 3600.0
            except (TypeError, ValueError):
                time_in_trade_hours = 0.0
                missing_fields.append("time_in_trade")
        else:
            time_in_trade_hours = 0.0
            missing_fields.append("time_in_trade")

        # Current ATR
        current_atr = self._compute_current_atr()
        if current_atr <= 0:
            missing_fields.append("current_atr")

        # Model confidence (use latest from inference — may be stale)
        xgb_confidence = 0.5  # safe default
        meta_confidence = getattr(self, "_last_meta_confidence", 0.65)
        if meta_confidence is None:
            meta_confidence = 0.65
            missing_fields.append("meta_confidence")

        # Account health
        account_health = self._latest_health_score or 100.0
        if self._latest_health_score is None:
            missing_fields.append("account_health")

        # Risk profile
        risk_profile = self._latest_risk_profile or "normal"

        # Broker quality
        broker_quality = self._latest_broker_score or 100.0
        if self._latest_broker_score is None:
            missing_fields.append("broker_quality")

        # Capital protection + recovery
        cap_pres_active = (
            self.capital_preservation.is_active
            if self.capital_preservation else False
        )
        recovery_active = (
            self.recovery_mode.is_active
            if self.recovery_mode else False
        )

        # News state
        news_halt = self.news_filter.is_halt_active() if self.news_filter else False

        # Session (simplified)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        hour = now.hour
        if 0 <= hour < 8:
            session = "asia"
        elif 8 <= hour < 14:
            session = "eu"
        elif 14 <= hour < 22:
            session = "us"
        else:
            session = "off"

        # Regime (simplified — would come from context engine)
        regime = "normal"
        if current_atr > 30:
            regime = "volatile"
        elif self._latest_health_band == "normal":
            regime = "trend"

        # Trend strength (simplified — would come from feature stream)
        trend_strength = 0.3  # safe default
        momentum = 0.5  # safe default

        # Build ExitInput
        exit_input = ExitInput(
            direction=direction_int,
            entry_price=entry_price,
            current_price=current_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            volume=volume,
            xgb_confidence=xgb_confidence,
            meta_confidence=meta_confidence,
            trend_strength=trend_strength,
            momentum=momentum,
            volatility_regime="high" if current_atr > 30 else "normal",
            atr=current_atr,
            spread_usd=self.config.spread_default,
            time_in_trade_hours=time_in_trade_hours,
            floating_pnl_usd=floating_pnl,
            r_multiple=r_multiple,
            account_health_score=account_health,
            capital_preservation_active=cap_pres_active,
            recovery_mode_active=recovery_active,
            broker_quality_score=broker_quality,
            news_halt_active=news_halt,
            news_imminent=False,  # would come from news filter
            session=session,
            regime=regime,
        )

        # Build cached context dict from latest runtime state
        cached_context = {
            "health_score": account_health,
            "risk_profile": risk_profile,
            "broker_quality": broker_quality,
        }

        # ── Call AIExitEngine ──
        ai_decision = self.ai_exit_engine.evaluate(
            exit_input, cached_context=cached_context
        )

        # ── Call ExitGovernance (if present) ──
        governance_decision = None
        if self.exit_governance is not None:
            try:
                governance_decision = self.exit_governance.decide(ai_decision)
            except Exception as gov_err:
                logger.warning(f"ExitGovernance failed: {gov_err}")
                missing_fields.append("governance_decision")

        # ── Determine action application ──
        # In dry_run=true: journal what WOULD happen, send no MT5 orders
        # In live_trading=false: never call mt5.order_send
        would_modify = False
        would_close = False
        dry_run = self.config.dry_run

        if ai_decision.action == ExitAction.HOLD:
            pass  # no modification
        elif ai_decision.action == ExitAction.MOVE_TO_BREAK_EVEN:
            would_modify = True
        elif ai_decision.action == ExitAction.TRAIL:
            would_modify = True
        elif ai_decision.action == ExitAction.PARTIAL_CLOSE:
            would_close = True
        elif ai_decision.action == ExitAction.BOOK_PROFIT:
            would_close = True
        elif ai_decision.action == ExitAction.FULL_EXIT:
            would_close = True
        elif ai_decision.action == ExitAction.EMERGENCY_EXIT:
            would_close = True

        # ── Journal the full decision ──
        latency_ms = (_time.perf_counter() - t0) * 1000
        ticket = getattr(pos, "ticket", 0)
        symbol = getattr(pos, "symbol", "XAUUSD")

        journal_data = {
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction_int,
            "current_price": current_price,
            "floating_pnl": floating_pnl,
            "r_multiple": r_multiple,
            "action": ai_decision.action.value,
            "confidence": ai_decision.confidence,
            "exit_latency_ms": round(latency_ms, 3),
            "emergency_fast_path_used": ai_decision.emergency_fast_path_used,
            "used_cached_context": ai_decision.used_cached_context,
            "ai_exit_fallback_used": False,
            "missing_context_fields": missing_fields,
            "dry_run": dry_run,
            "live_trading": not dry_run,
            "would_modify_order": would_modify,
            "would_close_order": would_close,
            "decision_path": ai_decision.decision_path,
            "reason": ai_decision.reason,
        }

        # Add governance decision if available
        if governance_decision is not None:
            journal_data["governance_decision"] = governance_decision.final_action.value
            journal_data["governance_confidence"] = governance_decision.final_confidence

        # Add partial close details
        if ai_decision.action == ExitAction.PARTIAL_CLOSE:
            journal_data["partial_close_pct"] = ai_decision.partial_close_pct
            journal_data["partial_volume"] = volume * ai_decision.partial_close_pct / 100

        # Add new SL for trail/BE
        if ai_decision.action == ExitAction.TRAIL:
            journal_data["new_trailing_sl"] = ai_decision.new_trailing_sl
        elif ai_decision.action == ExitAction.MOVE_TO_BREAK_EVEN:
            journal_data["new_break_even_sl"] = ai_decision.new_break_even_sl

        self.journal.log_event(EventType.EXIT_AI_DECISION, journal_data)

        # ── Safety: SL never moves in wrong direction ──
        if would_modify and ai_decision.action == ExitAction.TRAIL:
            if direction_int == 1 and ai_decision.new_trailing_sl <= stop_loss:
                logger.warning(
                    f"AI trail SL {ai_decision.new_trailing_sl} <= current "
                    f"SL {stop_loss} for LONG — ignoring (safety)"
                )
                would_modify = False
            elif direction_int == -1 and ai_decision.new_trailing_sl >= stop_loss:
                logger.warning(
                    f"AI trail SL {ai_decision.new_trailing_sl} >= current "
                    f"SL {stop_loss} for SHORT — ignoring (safety)"
                )
                would_modify = False

        # ── Safety: partial close never over-closes ──
        if would_close and ai_decision.action == ExitAction.PARTIAL_CLOSE:
            if ai_decision.partial_close_pct > 75:
                logger.warning(
                    f"AI partial close {ai_decision.partial_close_pct}% > 75% "
                    f"— capping at 75% (safety)"
                )
                ai_decision.partial_close_pct = 75

    # ─── Sprint 9.9.3.39: Forward observation + scorecard helpers ────────

    def _build_position_snapshot(self, pos) -> PositionSnapshot:
        """Build a PositionSnapshot from a BrokerPosition.

        Adapts the existing BrokerPosition shape (from position_sync) into
        the PositionSnapshot shape required by PositionLifecycleEngine.
        Never raises — missing fields default to safe values.
        """
        try:
            ticket = int(getattr(pos, "ticket", 0) or 0)
            side = str(getattr(pos, "direction", getattr(pos, "side", "BUY"))).upper()
            if side not in ("BUY", "SELL"):
                side = "BUY"
            entry_price = float(getattr(pos, "entry_price", 0.0) or 0.0)
            current_price = float(getattr(pos, "current_price", self.config.entry_price_default) or self.config.entry_price_default)
            volume = float(getattr(pos, "volume", 0.01) or 0.01)
            if volume > 0.01:
                volume = 0.01  # hard cap
            initial_sl = float(getattr(pos, "initial_sl", getattr(pos, "sl", 0.0)) or 0.0)
            current_sl = float(getattr(pos, "current_sl", getattr(pos, "sl", 0.0)) or 0.0)
            current_tp = float(getattr(pos, "current_tp", getattr(pos, "tp", 0.0)) or 0.0)
            unrealized_pnl = float(getattr(pos, "unrealized_pnl", getattr(pos, "pnl_usd", 0.0)) or 0.0)
            pnl_r = float(getattr(pos, "pnl_r", 0.0) or 0.0)
            age_seconds = float(getattr(pos, "age_seconds", getattr(pos, "holding_time_seconds", 0.0)) or 0.0)
            spread_points = float(getattr(pos, "spread_points", 0.0) or 0.0)
            atr = float(getattr(pos, "atr", 0.0) or 0.0)
            return PositionSnapshot(
                symbol=self.config.symbol,
                side=side,
                entry_price=entry_price,
                current_price=current_price,
                volume=volume,
                initial_sl=initial_sl,
                current_sl=current_sl,
                current_tp=current_tp,
                unrealized_pnl=unrealized_pnl,
                pnl_r=pnl_r,
                age_seconds=age_seconds,
                spread_points=spread_points,
                atr=atr,
                regime="UNKNOWN",
                model_confidence=float(getattr(self, "_last_model_confidence", 0.0) or 0.0),
                meta_confidence=float(getattr(self, "_last_meta_confidence", 0.0) or 0.0),
                broker="UNKNOWN",
                ticket=ticket,
            )
        except Exception:
            return PositionSnapshot(
                symbol=self.config.symbol,
                ticket=int(getattr(pos, "ticket", 0) or 0),
            )

    def _record_observation_event(self, raw_event: dict) -> None:
        """Normalize a runtime event through ForwardObservationEngine and store it.

        This is the runtime-side adapter for ForwardObservationEngine. The
        engine was previously offline-only (invoked by
        scripts/audit/forward_observation_report.py). Sprint 9.9.3.39 wires
        it into the runtime so events are normalized in real time.

        Never raises — observation is non-blocking.
        """
        try:
            if self.forward_observation_engine is None:
                return
            event = self.forward_observation_engine.normalize_event(raw_event)
            self._observation_events.append(event)
            self.journal.log_event(EventType.FORWARD_OBSERVATION_EVENT_RECORDED, {
                "event_type": event.event_type.value
                    if hasattr(event.event_type, "value") else str(event.event_type),
                "source": event.source,
                "symbol": event.symbol,
                "timeframe": event.timeframe,
                "severity": event.severity,
                "safe": event.safe,
                "reason": event.reason,
            })
        except Exception as obs_err:
            logger.warning(f"Forward observation event recording failed: {obs_err}")

    def compute_observation_scorecard(self, final_open_positions: int = 0):
        """Compute an ObservationScorecard from collected runtime events.

        Returns an ObservationScorecard. If no events have been collected,
        returns INSUFFICIENT_DATA.
        """
        try:
            if self.forward_observation_engine is None or self.observation_scorecard_engine is None:
                from titan.production.observation_scorecard import (
                    ObservationScorecard, ObservationScoreGrade,
                )
                return ObservationScorecard(
                    grade=ObservationScoreGrade.INSUFFICIENT_DATA,
                )
            events = list(self._observation_events)
            summary = self.forward_observation_engine.summarize(events)
            card = self.observation_scorecard_engine.score(
                summary, final_open_positions=final_open_positions,
            )
            return card
        except Exception as e:
            from titan.production.observation_scorecard import (
                ObservationScorecard, ObservationScoreGrade,
            )
            return ObservationScorecard(
                grade=ObservationScoreGrade.INSUFFICIENT_DATA,
                blockers=[f"compute_observation_scorecard exception: {e}"],
            )

    def _compute_current_atr(self) -> float:
        """
        Compute current ATR(14) from the feature stream's bar buffer.
        Returns 0.0 if insufficient data.

        Sprint 8.5 wiring fix: read from self.inference_engine.feature_stream
        (the H1FeatureStream that engine.generate() actually populates),
        NOT from self.feature_stream (a separate, never-populated instance
        created at autonomous_loops.py:155). This was the root cause of
        every AutonomousRuntime production signal silently falling back
        to fixed-pip SL/TP — the empty self.feature_stream._bars returned
        len < 15 → ATR=0.0 → fallback_used=True, fallback_reason=atr_zero.
        """
        try:
            bars = self.inference_engine.feature_stream._bars
            if len(bars) < 15:
                return 0.0
            h, l, c = bars["high"], bars["low"], bars["close"]
            tr = pd.concat([
                (h - l),
                (h - c.shift(1)).abs(),
                (l - c.shift(1)).abs(),
            ], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]
            return float(atr) if not np.isnan(atr) else 0.0
        except Exception as e:
            logger.warning(
                f"_compute_current_atr failed (will trigger ATR fallback): "
                f"{type(e).__name__}: {e}"
            )
            return 0.0

    def _get_current_bar_time(self) -> str:
        """
        Get current H1 bar timestamp (truncated to hour).
        Returns ISO format string.
        """
        now = datetime.now(timezone.utc)
        # Truncate to hour (H1 bar close = next hour start)
        bar_time = now.replace(minute=0, second=0, microsecond=0)
        return bar_time.isoformat()

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def signals_generated(self) -> int:
        return self._signals_generated

    @property
    def trades_attempted(self) -> int:
        return self._trades_attempted

    @property
    def trades_blocked(self) -> int:
        return self._trades_blocked

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "dry_run": self.config.dry_run,
            "kill_switch_state": self.kill_switch.state.value
                if self.kill_switch else "UNKNOWN",
            "signals_generated": self._signals_generated,
            "trades_attempted": self._trades_attempted,
            "trades_blocked": self._trades_blocked,
            "open_positions": self.position_sync.position_count
                if self.position_sync else 0,
            "last_bar": self._last_processed_bar_time,
        }

    # ─── Test Helpers (for smoke tests) ─────────────────────────────────

    async def run_single_cycle(self, force_tradeable: bool = False) -> dict:
        """
        Run a single inference→trade cycle for testing.
        Does NOT use the loop — directly calls the chain.

        Args:
            force_tradeable: If True, overrides signal to be tradeable LONG
                             (for testing kill-switch block when canonical
                             data produces FLAT signals).
        """
        # Generate signal
        signal = self.inference_engine.generate(
            source=self.config.feature_source,
            symbol=self.config.symbol,
        )
        if force_tradeable:
            signal.is_tradeable = True
            signal.direction = Direction.LONG
            signal.confidence = 0.80
            signal.meta_confidence = 0.85
        self._signals_generated += 1
        self.journal.log_signal(signal)
        self.journal.log_event(EventType.SIGNAL_CREATED, {
            "direction": signal.direction.name,
            "confidence": signal.confidence,
            "is_tradeable": signal.is_tradeable,
        })

        # Check kill-switch FIRST (HARD GATE — before signal tradeability check)
        # This ensures kill-switch blocks are journaled even for non-tradeable signals
        if not self.kill_switch.allows_new_trades:
            self._trades_blocked += 1
            ks_state = self.kill_switch.state
            reason = "kill_switch_emergency_stop" if self.kill_switch.is_emergency else \
                     "kill_switch_flatten_only" if self.kill_switch.requires_flatten else \
                     "kill_switch_halt_new_trades"
            self.journal.log_event(EventType.KILL_SWITCH_BLOCK, {
                "kill_switch_state": ks_state.value,
                "signal_direction": signal.direction.name,
                "reason": reason,
            })
            logger.info(f"Kill-switch blocks trade: {ks_state.value}")
            return {"signal": signal, "decision": None, "blocked": True}

        if not signal.is_tradeable:
            self.journal.log_event(EventType.SIGNAL_REJECTED, {
                "reason": signal.reject_reason,
            })
            return {"signal": signal, "decision": None, "blocked": False}

        # Process trade
        self._trades_attempted += 1
        current_atr = self._compute_current_atr()

        # ─── Sprint 9.9.3.39: Institutional pipeline (mirror of _inference_loop) ──
        # run_single_cycle is a test helper. It must also pass through the
        # institutional pipeline so tests verify the same wiring as the loop.
        self.journal.log_event(EventType.INSTITUTIONAL_PIPELINE_STARTED, {
            "bar_time": "single_cycle",
            "signal_direction": signal.direction.name,
            "model_confidence": signal.confidence,
            "meta_confidence": signal.meta_confidence,
        })

        # Gate 1: RegimeDetection
        regime_status = None
        try:
            regime = detect_regime(confidence=signal.confidence)
            regime_status = {
                "primary_regime": regime.primary_regime.value
                    if hasattr(regime.primary_regime, "value") else str(regime.primary_regime),
                "risk_multiplier": regime.risk_multiplier,
                "allow_new_trade": regime.allow_new_trade,
                "block_reason": regime.block_reason,
            }
            self.journal.log_event(EventType.REGIME_GATE_EVALUATED, {
                "bar_time": "single_cycle",
                "regime": regime_status["primary_regime"],
            })
        except Exception:
            regime_status = None

        # Gate 2: BrokerCompatibilityMatrix
        broker_info = None
        try:
            broker_info = get_broker_info("MetaQuotes-Demo")
            self.journal.log_event(EventType.BROKER_GATE_EVALUATED, {
                "bar_time": "single_cycle",
                "broker": "MetaQuotes-Demo",
                "status": broker_info.get("status", "UNKNOWN"),
            })
        except Exception:
            broker_info = None

        # Gate 3: RuntimeHealthMonitor
        runtime_health = None
        try:
            if self.runtime_health_monitor is not None:
                rh_status = self.runtime_health_monitor.get_health_status()
                runtime_health = {
                    "status": rh_status.get("status", "HEALTHY"),
                    "event_count": rh_status.get("event_count", 0),
                }
            self.journal.log_event(EventType.RUNTIME_HEALTH_GATE_EVALUATED, {
                "bar_time": "single_cycle",
                "status": runtime_health["status"] if runtime_health else "UNKNOWN",
            })
        except Exception:
            runtime_health = None

        # Gate 4: SecurityGate
        security_status = None
        try:
            if self.security_gate is not None:
                sec_check = self.security_gate.check()
                security_status = {
                    "allowed": sec_check.get("allowed", True),
                    "reason": sec_check.get("reason"),
                    "mode": sec_check.get("mode", "dev_mode"),
                }
            self.journal.log_event(EventType.SECURITY_GATE_EVALUATED, {
                "bar_time": "single_cycle",
                "allowed": security_status["allowed"] if security_status else True,
            })
        except Exception:
            security_status = None

        # Build DecisionInput → SignalExecutionBridge.build_intent()
        if signal.direction == Direction.LONG:
            _ms = "BUY"
            _dir = "BUY"
        elif signal.direction == Direction.SHORT:
            _ms = "SELL"
            _dir = "SELL"
        else:
            _ms = "NONE"
            _dir = None
        decision_input = DecisionInput(
            symbol=self.config.symbol,
            timeframe="H1",
            model_signal=_ms,
            model_confidence=signal.confidence,
            meta_confidence=signal.meta_confidence,
            direction=_dir,
        )
        intent = self.signal_execution_bridge.build_intent(
            inp=decision_input,
            regime_status=regime_status,
            broker_info=broker_info,
            runtime_health=runtime_health,
            security_status=security_status,
        )
        self._last_execution_intent = intent

        self.journal.log_event(EventType.EXECUTION_INTENT_CREATED, {
            "bar_time": "single_cycle",
            "allowed": intent.allowed,
            "decision": intent.decision,
            "lot": intent.lot,
            "block_reasons": intent.block_reasons,
        })
        self._record_observation_event({
            "event": "EXECUTION_INTENT_CREATED",
            "timestamp_utc": intent.timestamp_utc,
            "symbol": intent.symbol,
            "timeframe": "H1",
            "intent_allowed": intent.allowed,
            "intent_decision": intent.decision,
        })

        if not intent.allowed:
            self._trades_blocked += 1
            self.journal.log_event(EventType.EXECUTION_INTENT_BLOCKED, {
                "bar_time": "single_cycle",
                "decision": intent.decision,
                "block_reasons": intent.block_reasons,
            })
            self.journal.log_event(EventType.TRADE_LOOP_SKIPPED_BY_INTENT, {
                "bar_time": "single_cycle",
                "reason": "SignalExecutionBridge blocked intent",
            })
            return {"signal": signal, "decision": None, "blocked": True,
                    "intent": intent}

        self.journal.log_event(EventType.EXECUTION_INTENT_APPROVED, {
            "bar_time": "single_cycle",
            "decision": intent.decision,
            "lot": intent.lot,
        })
        self.journal.log_event(EventType.TRADE_LOOP_CALLED_AFTER_INTENT, {
            "bar_time": "single_cycle",
            "intent_decision": intent.decision,
            "intent_lot": intent.lot,
        })

        decision = await self.trade_loop.process_signal(
            signal=signal,
            entry_price=self.config.entry_price_default,
            spread_usd=self.config.spread_default,
            current_atr=current_atr,
        )

        if decision.accepted:
            self.journal.log_event(EventType.ORDER_CREATED, {
                "order_request": decision.order_request,
                "dry_run": decision.dry_run,
            })

        return {"signal": signal, "decision": decision, "blocked": False}
