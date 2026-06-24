"""
TITAN XAU AI — Forward Test Manager (Sprint 6)

Orchestrates the forward testing session:
  - Daily session management
  - Runtime health tracking
  - Trading day summaries
  - Forward-test statistics
  - Daily checkpoint creation

Usage:
    manager = ForwardTestManager(journal_path="data/runtime/journal.jsonl",
                                  output_dir="data/forward_test")
    manager.start_session()
    # ... run TITAN for the day ...
    manager.end_day(summary_data)
    manager.end_session()
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, date as date_class
from pathlib import Path
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType
from titan.forward_test.metrics_collector import MetricsCollector
from titan.forward_test.runtime_health import RuntimeHealthMonitor
from titan.forward_test.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


@dataclass
class SessionState:
    """Forward test session state."""
    session_id: str
    started_at: float
    started_utc: str
    ended_at: Optional[float] = None
    ended_utc: Optional[str] = None
    days_completed: int = 0
    last_day: Optional[str] = None
    checkpoints: list[dict] = field(default_factory=list)


@dataclass
class DailyCheckpoint:
    """Daily checkpoint snapshot."""
    date: str
    timestamp: float
    metrics: dict
    health: dict
    journal_records: int
    journal_size_bytes: int


class ForwardTestManager:
    """
    Manages the forward testing session lifecycle.

    Creates daily checkpoints, tracks health, generates reports.
    All data sourced from journal (source of truth).
    """

    def __init__(
        self,
        journal_path: str,
        output_dir: str = "data/forward_test",
        metrics_dir: str = "data/metrics",
        reports_dir: str = "data/reports",
    ):
        self.journal_path = journal_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir = self.output_dir / "checkpoints"
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)

        self.journal = TradeJournal(path=journal_path)
        self.metrics = MetricsCollector(journal_path=journal_path, output_dir=metrics_dir)
        self.health = RuntimeHealthMonitor(journal=self.journal)
        self.reports = ReportGenerator(journal_path=journal_path, output_dir=reports_dir)

        self._state: Optional[SessionState] = None
        self._state_path = self.output_dir / "session_state.json"

    def start_session(self) -> SessionState:
        """Start a new forward test session."""
        # Load existing state if available (resume after restart)
        if self._state_path.exists():
            self._state = self._load_state()
            logger.info(f"Resumed session: {self._state.session_id} "
                        f"({self._state.days_completed} days completed)")
        else:
            session_id = f"ft_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            self._state = SessionState(
                session_id=session_id,
                started_at=time.time(),
                started_utc=datetime.now(timezone.utc).isoformat(),
            )
            self._save_state()
            logger.info(f"Started new session: {session_id}")

        # Log startup
        self.journal.log_startup({
            "session_id": self._state.session_id,
            "resumed": self._state.days_completed > 0,
            "days_completed": self._state.days_completed,
        })

        return self._state

    def end_day(self, daily_summary: Optional[dict] = None) -> DailyCheckpoint:
        """
        End a trading day. Creates checkpoint + generates daily report.
        """
        if self._state is None:
            raise RuntimeError("Session not started — call start_session() first")

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Collect metrics
        snapshot = self.metrics.collect()
        self.metrics.save_json(snapshot)
        self.metrics.save_csv(snapshot)

        # Check health
        health = self.health.check()

        # Generate daily report
        daily_report = self.reports.generate_daily_report(date=today)

        # Create checkpoint
        checkpoint = DailyCheckpoint(
            date=today,
            timestamp=time.time(),
            metrics=asdict(snapshot),
            health=asdict(health),
            journal_records=self.journal.record_count,
            journal_size_bytes=self.journal.file_size_bytes,
        )

        # Save checkpoint
        cp_path = self.checkpoint_dir / f"checkpoint_{today}.json"
        # Sprint 9.0.1: explicit UTF-8 for Windows cp1252 compatibility.
        with open(cp_path, "w", encoding="utf-8") as f:
            json.dump(asdict(checkpoint), f, indent=2, default=str)
        logger.info(f"Daily checkpoint saved: {cp_path}")

        # Update session state
        self._state.days_completed += 1
        self._state.last_day = today
        self._state.checkpoints.append({
            "date": today,
            "path": str(cp_path),
            "pnl_usd": snapshot.total_pnl_usd,
            "trades": snapshot.trades_closed,
        })
        self._save_state()

        # Log daily summary to journal
        if daily_summary is None:
            daily_summary = {
                "date": today,
                "pnl_usd": snapshot.daily_pnl_usd,
                "trades_closed": snapshot.trades_closed,
                "win_rate": snapshot.win_rate,
                "signals_generated": snapshot.signals_generated,
                "kill_switch_events": snapshot.kill_switch_events,
                "health_alert": health.alert,
            }
        self.journal.log_daily_summary(daily_summary)

        return checkpoint

    def end_session(self, reason: str = "normal") -> None:
        """End the forward test session."""
        if self._state is None:
            return

        self._state.ended_at = time.time()
        self._state.ended_utc = datetime.now(timezone.utc).isoformat()
        self._save_state()

        self.journal.log_shutdown(reason=reason)
        self.journal.flush()

        logger.info(f"Session ended: {self._state.session_id} "
                    f"({self._state.days_completed} days)")

    def get_status(self) -> dict:
        """Get current session status."""
        if self._state is None:
            return {"status": "not_started"}
        return {
            "status": "running" if self._state.ended_at is None else "ended",
            "session_id": self._state.session_id,
            "started_utc": self._state.started_utc,
            "days_completed": self._state.days_completed,
            "last_day": self._state.last_day,
            "uptime_hours": self.health.uptime_hours,
            "checkpoints": len(self._state.checkpoints),
        }

    def _save_state(self) -> None:
        """Save session state to disk (for resume after restart)."""
        if self._state is None:
            return
        # Sprint 9.0.1: explicit UTF-8 for Windows cp1252 compatibility.
        with open(self._state_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self._state), f, indent=2, default=str)

    def _load_state(self) -> SessionState:
        """Load session state from disk."""
        # Sprint 9.0.1: explicit UTF-8 for Windows cp1252 compatibility.
        with open(self._state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return SessionState(**data)
