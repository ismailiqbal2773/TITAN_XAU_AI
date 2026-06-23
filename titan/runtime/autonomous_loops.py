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
                decision = await self.trade_loop.process_signal(
                    signal=signal,
                    entry_price=self.config.entry_price_default,
                    spread_usd=self.config.spread_default,
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

            except Exception as e:
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
        """Check open positions for exit conditions every 5 seconds."""
        logger.info("Exit manager loop started")
        while self._running:
            try:
                positions = self.position_sync.open_positions
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
                        # In dry_run, we just log — no real close
                        self.trade_loop.notify_position_closed()

                    elif exit_decision.should_trail:
                        logger.info(
                            f"Trailing stop: ticket={exit_decision.ticket} "
                            f"new_sl={exit_decision.new_trailing_sl}"
                        )

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
        """Log heartbeat every 30 seconds."""
        logger.info("Heartbeat loop started")
        while self._running:
            try:
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
                })
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            await asyncio.sleep(self.config.heartbeat_interval_s)

    # ─── Helpers ────────────────────────────────────────────────────────

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
        decision = await self.trade_loop.process_signal(
            signal=signal,
            entry_price=self.config.entry_price_default,
            spread_usd=self.config.spread_default,
        )

        if decision.accepted:
            self.journal.log_event(EventType.ORDER_CREATED, {
                "order_request": decision.order_request,
                "dry_run": decision.dry_run,
            })

        return {"signal": signal, "decision": decision, "blocked": False}
