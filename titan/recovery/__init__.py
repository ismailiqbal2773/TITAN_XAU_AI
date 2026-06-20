"""
TITAN XAU AI — Recovery Module
================================
Production recovery infrastructure. Extends existing architecture
WITHOUT modifying it. Adds:

  - Checkpointing (system snapshots every N seconds)
  - State persistence (CEO/Weighting/Risk/Models → SQLite + JSON)
  - Auto recovery on restart (loads last good state)
  - Crash recovery procedure
  - Trade / Position / Order reconciliation (DB vs broker)
  - DB / Redis / MT5 / API auto-reconnect with exponential backoff
  - Heartbeat watchdog (detects hung components)
  - Recovery journal (every recovery action logged)
  - Recovery audit trail (separate from compliance audit)

Usage:
    from titan.recovery import RecoveryManager
    rm = RecoveryManager(db, redis, broker, execution, ceo, weighting, risk)
    await rm.initialize()
    await rm.start()  # starts watchdog + checkpoint loops

On startup after crash:
    state = await rm.load_last_known_state()
    await rm.reconcile_with_broker()  # fix any drift
    await rm.restore_state(state)
"""
from .manager import RecoveryManager, RecoveryState
from .journal import RecoveryJournal, AuditTrail
from .checkpoint import CheckpointManager, CheckpointPayload
from .reconcile import ReconciliationEngine, ReconciliationReport
from .watchdog import HeartbeatWatchdog
from .reconnect import (
    AutoReconnectDB, AutoReconnectRedis, AutoReconnectMT5,
    ReconnectPolicy,
)

__all__ = [
    "RecoveryManager", "RecoveryState",
    "RecoveryJournal", "AuditTrail",
    "CheckpointManager", "CheckpointPayload",
    "ReconciliationEngine", "ReconciliationReport",
    "HeartbeatWatchdog",
    "AutoReconnectDB", "AutoReconnectRedis", "AutoReconnectMT5",
    "ReconnectPolicy",
]
