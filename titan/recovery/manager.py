"""
TITAN Recovery Manager
=======================
Top-level orchestrator for production recovery.

Responsibilities:
  1. Initialize journal, checkpoint manager, watchdog, reconciliation
  2. Start checkpoint loop (save state every N seconds)
  3. Start watchdog loop (detect hung components)
  4. Provide crash recovery procedure: load_last_known_state() + reconcile
  5. Provide graceful shutdown procedure (save final checkpoint)
  6. Auto-restart dead components via watchdog callback

Wires into existing TitanSystem via initialize() and start() hooks.
Does NOT modify existing components — only wraps them.
"""
from __future__ import annotations
import asyncio
import logging
import time
import os
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Any

from .journal import RecoveryJournal, AuditTrail
from .checkpoint import CheckpointManager, CheckpointPayload
from .reconcile import ReconciliationEngine, ReconciliationReport
from .watchdog import HeartbeatWatchdog
from .reconnect import (
    AutoReconnectDB, AutoReconnectRedis, AutoReconnectMT5, ReconnectPolicy
)

logger = logging.getLogger(__name__)


@dataclass
class RecoveryState:
    """Captured state for restore-on-restart."""
    initialized_at: float
    last_checkpoint_id: int | None = None
    last_checkpoint_ts: float = 0.0
    db_reconnect_count: int = 0
    redis_reconnect_count: int = 0
    mt5_reconnect_count: int = 0
    reconciliations_run: int = 0
    last_reconciliation_clean: bool | None = None
    crash_recovery_count: int = 0


class RecoveryManager:
    """Top-level recovery orchestrator."""

    def __init__(self, db, redis=None, broker=None, execution=None,
                 ceo=None, weighting=None, risk=None,
                 checkpoint_interval_s: float = 30.0,
                 reconcile_interval_s: float = 60.0,
                 alert_manager=None):
        self._db_raw = db
        self._redis_raw = redis
        self._broker_raw = broker
        self._execution = execution
        self._ceo = ceo
        self._weighting = weighting
        self._risk = risk
        self._alerts = alert_manager

        self._checkpoint_interval_s = checkpoint_interval_s
        self._reconcile_interval_s = reconcile_interval_s

        # Components
        self._journal = RecoveryJournal(db)
        self._audit = AuditTrail(db)
        self._checkpoints = CheckpointManager(db, self._journal)
        self._watchdog = HeartbeatWatchdog(self._journal, alert_manager)
        self._reconciler = ReconciliationEngine(db, broker, self._journal)

        # Auto-reconnect wrappers
        self._policy = ReconnectPolicy()
        self._db = AutoReconnectDB(db, self._policy, self._on_reconnect_event)
        self._redis = (AutoReconnectRedis(redis, self._policy, self._on_reconnect_event)
                       if redis else None)
        self._broker = (AutoReconnectMT5(broker, self._policy, self._on_reconnect_event)
                        if broker else None)

        # State
        self._state = RecoveryState(initialized_at=time.time())
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # Register all expected components with watchdog
        for comp, interval in [
            ("market_data", 5), ("ceo", 65), ("weighting", 65),
            ("risk", 30), ("execution", 30), ("broker", 30),
            ("api", 15), ("license_guard", 65), ("compliance", 35),
            ("db", 5), ("redis", 30), ("checkpoint", 35),
        ]:
            self._watchdog.register(comp, expected_interval_s=interval,
                                     threshold_misses=3)

    async def _on_reconnect_event(self, event: str, details: dict) -> None:
        """Callback from auto-reconnect wrappers."""
        await self._journal.log("reconnect", details.get("component", "?"),
                                  event, details,
                                  severity="WARN" if "failed" in event else "INFO")

    # ─── Lifecycle ───

    async def initialize(self) -> None:
        """Initialize journal, checkpoints, audit tables."""
        await self._journal.initialize()
        await self._checkpoints.initialize()
        logger.info("✓ RecoveryManager initialized (journal + checkpoints + audit)")

    async def start(self) -> None:
        """Start watchdog + checkpoint + reconcile loops."""
        if self._running:
            return
        self._running = True
        await self._journal.log("crash_recovery", "system", "start",
                                  {"components": "all"})
        self._tasks.append(asyncio.create_task(self._checkpoint_loop()))
        self._tasks.append(asyncio.create_task(self._watchdog_loop()))
        self._tasks.append(asyncio.create_task(self._reconcile_loop()))
        await self._watchdog.start()
        logger.info(f"✓ RecoveryManager started "
                    f"(checkpoint={self._checkpoint_interval_s}s, "
                    f"reconcile={self._reconcile_interval_s}s)")

    async def stop(self) -> None:
        """Graceful shutdown — save final checkpoint."""
        self._running = False
        # Save final shutdown checkpoint
        try:
            payload = await self._capture_state()
            await self._checkpoints.save_checkpoint(payload, checkpoint_type="shutdown")
            await self._journal.log("crash_recovery", "system", "shutdown_checkpoint_saved",
                                      {"checkpoint_id": self._checkpoints.last_checkpoint_id})
        except Exception as e:
            logger.error(f"Failed to save shutdown checkpoint: {e}")
        # Stop tasks
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._watchdog.stop()
        logger.info("✓ RecoveryManager stopped")

    # ─── Crash recovery ───

    async def load_last_known_state(self) -> CheckpointPayload | None:
        """Load most recent valid checkpoint."""
        payload = await self._checkpoints.load_latest_checkpoint()
        if payload:
            age_s = time.time() - payload.timestamp
            logger.info(f"Last checkpoint: id={self._checkpoints.last_checkpoint_id}, "
                        f"age={age_s:.0f}s")
            await self._journal.log("crash_recovery", "system", "checkpoint_loaded",
                                      {"age_s": age_s,
                                       "positions": len(payload.positions or []),
                                       "orders": len(payload.open_orders or [])})
            self._state.crash_recovery_count += 1
        else:
            logger.warning("No previous checkpoint found — cold start")
            await self._journal.log("crash_recovery", "system", "cold_start", {},
                                     severity="WARN")
        return payload

    async def restore_state(self, payload: CheckpointPayload) -> None:
        """Restore in-memory state from checkpoint payload.

        NOTE: This does NOT reopen positions or resend orders.
        It only restores CEO/Weighting/Risk internal counters and
        re-registers idempotency keys to prevent duplicate submissions.
        """
        from titan.database.layer import StateRepository, OrderRepository
        repo = StateRepository(self._db_raw)

        # Restore CEO cycle_count if available
        if payload.ceo and self._ceo:
            try:
                cc = payload.ceo.get("cycle_count", 0)
                if hasattr(self._ceo, "cycle_count"):
                    self._ceo.cycle_count = cc
                await self._audit.log_change(
                    "ceo", "cycle_count", None, cc,
                    reason="Restored from checkpoint",
                )
            except Exception as e:
                logger.warning(f"CEO restore failed: {e}")

        # Restore Weighting cycle_count
        if payload.weighting and self._weighting:
            try:
                cc = payload.weighting.get("cycle_count", 0)
                if hasattr(self._weighting, "cycle_count"):
                    self._weighting.cycle_count = cc
                await self._audit.log_change(
                    "weighting", "cycle_count", None, cc,
                    reason="Restored from checkpoint",
                )
            except Exception as e:
                logger.warning(f"Weighting restore failed: {e}")

        # Restore kill_switch state
        if payload.kill_switch_armed and self._risk:
            try:
                if hasattr(self._risk, "arm_kill_switch"):
                    self._risk.arm_kill_switch(reason="Restored from checkpoint")
                await self._audit.log_change(
                    "risk", "kill_switch_armed", False, True,
                    reason="Restored from checkpoint",
                )
            except Exception as e:
                logger.warning(f"Risk kill-switch restore failed: {e}")

        # Re-register idempotency keys to prevent duplicate submissions
        if payload.idempotency_keys and self._execution:
            try:
                cache = getattr(self._execution, "_idempotency_cache", None)
                if cache:
                    for key in payload.idempotency_keys:
                        cache.check_and_add(key)
                    logger.info(f"Restored {len(payload.idempotency_keys)} "
                                f"idempotency keys")
            except Exception as e:
                logger.warning(f"Idempotency restore failed: {e}")

        await self._journal.log("crash_recovery", "system", "state_restored",
                                  {"ceo_cycle": payload.ceo.get("cycle_count") if payload.ceo else None,
                                   "weighting_cycle": payload.weighting.get("cycle_count") if payload.weighting else None,
                                   "kill_switch_armed": payload.kill_switch_armed})

    async def reconcile_with_broker(self, auto_fix: bool = False) -> ReconciliationReport:
        """Run full reconciliation against broker truth."""
        report = await self._reconciler.full_reconciliation(auto_fix=auto_fix)
        self._state.reconciliations_run += 1
        self._state.last_reconciliation_clean = report.is_clean
        if not report.is_clean:
            logger.warning(f"Reconciliation found {report.total_drifts} drifts")
            await self._alerts.send_alert(
                "P2", "Reconciliation Drift",
                f"{report.total_drifts} drifts detected",
            ) if self._alerts else None
        return report

    # ─── State capture ───

    async def _capture_state(self) -> CheckpointPayload:
        """Capture current system state."""
        from titan.database.layer import (
            StateRepository, PositionRepository, OrderRepository
        )
        state_repo = StateRepository(self._db_raw)
        pos_repo = PositionRepository(self._db_raw)

        payload = CheckpointPayload(timestamp=time.time())

        # CEO state
        try:
            ceo_state = await state_repo.get_latest_ceo_state()
            if ceo_state:
                payload.ceo = ceo_state
                payload.cycle_counts = {"ceo": ceo_state.get("cycle_count")}
        except Exception as e:
            logger.warning(f"CEO state capture failed: {e}")

        # Weighting state
        try:
            w_state = await state_repo.get_latest_weighting_state()
            if w_state:
                payload.weighting = w_state
                payload.cycle_counts = payload.cycle_counts or {}
                payload.cycle_counts["weighting"] = w_state.get("cycle_count")
        except Exception as e:
            logger.warning(f"Weighting state capture failed: {e}")

        # Risk state
        try:
            r_state = await state_repo.get_latest_risk_state()
            if r_state:
                payload.risk = r_state
                payload.kill_switch_armed = bool(r_state.get("kill_switch_armed", 0))
        except Exception as e:
            logger.warning(f"Risk state capture failed: {e}")

        # Positions snapshot
        try:
            payload.positions = await pos_repo.get_all_positions()
        except Exception as e:
            logger.warning(f"Positions capture failed: {e}")

        # Open orders snapshot
        try:
            payload.open_orders = await self._db_raw.query_all(
                "SELECT * FROM orders WHERE state NOT IN ('FILLED','REJECTED','CANCELLED')"
            )
        except Exception as e:
            logger.warning(f"Orders capture failed: {e}")

        # Idempotency keys (active)
        try:
            if self._execution and hasattr(self._execution, "_idempotency_cache"):
                payload.idempotency_keys = list(
                    self._execution._idempotency_cache._keys[-1000:]
                    if hasattr(self._execution._idempotency_cache, "_keys")
                    else []
                )
        except Exception:
            pass

        # Active regime
        try:
            from titan.regime.engine import RegimeDetector
            # Don't import the singleton; just leave as None if no detector
        except Exception:
            pass

        return payload

    # ─── Background loops ───

    async def _checkpoint_loop(self) -> None:
        """Periodic checkpoint save."""
        while self._running:
            try:
                await asyncio.sleep(self._checkpoint_interval_s)
                payload = await self._capture_state()
                await self._checkpoints.save_checkpoint(payload, "periodic")
                self._state.last_checkpoint_id = self._checkpoints.last_checkpoint_id
                self._state.last_checkpoint_ts = self._checkpoints.last_checkpoint_ts
                self._watchdog.beat("checkpoint")
                # Cleanup old checkpoints daily
                if int(time.time()) % 86400 < self._checkpoint_interval_s:
                    deleted = await self._checkpoints.cleanup_old(keep_count=288)
                    if deleted:
                        logger.info(f"Cleaned up {deleted} old checkpoints")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Checkpoint loop error: {e}")
                await asyncio.sleep(10)

    async def _watchdog_loop(self) -> None:
        """Watchdog monitor loop — pings system components."""
        while self._running:
            try:
                await asyncio.sleep(5)
                # Check DB connection
                try:
                    await self._db_raw.query_one("SELECT 1")
                    self._watchdog.beat("db")
                except Exception:
                    pass
                # Check Redis
                if self._redis_raw and self._redis_raw.connected:
                    self._watchdog.beat("redis")
                # Check MT5
                if self._broker_raw and getattr(self._broker_raw, "_mt5_initialized", False):
                    self._watchdog.beat("broker")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Watchdog loop error: {e}")

    async def _reconcile_loop(self) -> None:
        """Periodic reconciliation with broker."""
        while self._running:
            try:
                await asyncio.sleep(self._reconcile_interval_s)
                if self._broker_raw and getattr(self._broker_raw, "_mt5_initialized", False):
                    report = await self.reconcile_with_broker(auto_fix=False)
                    if not report.is_clean and report.total_drifts > 0:
                        logger.warning(f"Periodic reconcile: {report.total_drifts} drifts")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reconcile loop error: {e}")

    # ─── Public API ───

    def beat(self, component: str) -> None:
        """Public heartbeat API for components to call."""
        self._watchdog.beat(component)

    @property
    def journal(self) -> RecoveryJournal:
        return self._journal

    @property
    def audit(self) -> AuditTrail:
        return self._audit

    @property
    def checkpoints(self) -> CheckpointManager:
        return self._checkpoints

    @property
    def watchdog(self) -> HeartbeatWatchdog:
        return self._watchdog

    @property
    def reconciler(self) -> ReconciliationEngine:
        return self._reconciler

    @property
    def state(self) -> RecoveryState:
        return self._state

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "state": asdict(self._state),
            "watchdog": self._watchdog.status(),
            "last_checkpoint_id": self._checkpoints.last_checkpoint_id,
            "last_checkpoint_ts": self._checkpoints.last_checkpoint_ts,
            "db_reconnect_count": self._db.reconnect_count if self._db else 0,
            "redis_reconnect_count": self._redis.reconnect_count if self._redis else 0,
            "mt5_reconnect_count": self._broker.reconnect_count if self._broker else 0,
        }
