"""
TITAN XAU AI — Metrics Collector (Sprint 6)

Collects forward-test metrics from the journal (source of truth).
NO in-memory state — all metrics computed from journal records.

Persists to:
  - JSON (snapshot)
  - CSV (time series)

Usage:
    collector = MetricsCollector(journal_path="data/runtime/journal.jsonl",
                                  output_dir="data/metrics")
    collector.collect()
    snapshot = collector.get_snapshot()
    collector.save_json(snapshot)
    collector.save_csv(snapshot)
"""
from __future__ import annotations

import csv
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


@dataclass
class MetricsSnapshot:
    """Point-in-time metrics snapshot."""
    timestamp: float
    utc_timestamp: str
    # Signal metrics
    signals_generated: int = 0
    signals_accepted: int = 0
    signals_rejected: int = 0
    # Order metrics
    orders_created: int = 0
    orders_blocked: int = 0
    # Position metrics
    positions_opened: int = 0
    positions_closed: int = 0
    # Trade metrics
    trades_closed: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_rr: float = 0.0
    total_pnl_usd: float = 0.0
    daily_pnl_usd: float = 0.0
    weekly_pnl_usd: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_trade_duration_hours: float = 0.0
    # Safety metrics
    kill_switch_events: int = 0
    kill_switch_blocks: int = 0
    news_halts: int = 0
    drift_alerts: int = 0
    drift_emergencies: int = 0
    slippage_alerts: int = 0
    slippage_halts: int = 0
    watchdog_restarts: int = 0
    # Slippage stats
    slippage_mean_pips: float = 0.0
    slippage_p95_pips: float = 0.0
    # Drift stats
    drift_psi: float = 0.0
    drift_ece: float = 0.0
    drift_brier: float = 0.0


class MetricsCollector:
    """
    Collects metrics from journal. NO in-memory state.
    Every call to collect() re-reads the journal from disk.
    """

    def __init__(self, journal_path: str, output_dir: str = "data/metrics"):
        self.journal_path = journal_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._last_snapshot: Optional[MetricsSnapshot] = None

    def collect(self) -> MetricsSnapshot:
        """Collect metrics from journal. Returns snapshot."""
        journal = TradeJournal(path=self.journal_path)
        journal.flush()
        records = journal.read_all()

        now = time.time()
        now_dt = datetime.now(timezone.utc)
        snapshot = MetricsSnapshot(
            timestamp=now,
            utc_timestamp=now_dt.isoformat(),
        )

        # ── Count by record_type ──
        for r in records:
            rt = r.get("record_type", "")
            et = r.get("event_type", "")
            data = r.get("data", {})

            if rt == "SIGNAL":
                snapshot.signals_generated += 1
            elif rt == "DECISION":
                if data.get("accepted"):
                    snapshot.signals_accepted += 1
                else:
                    snapshot.signals_rejected += 1
            elif rt == "ORDER":
                snapshot.orders_created += 1
            elif rt == "EXIT":
                snapshot.positions_closed += 1
                snapshot.trades_closed += 1
                pnl = data.get("pnl_usd", 0.0)
                snapshot.total_pnl_usd += pnl
                if pnl > 0:
                    snapshot.winning_trades += 1
                elif pnl < 0:
                    snapshot.losing_trades += 1
                # Trade duration
                duration = data.get("holding_time_seconds", 0)
                if duration > 0:
                    snapshot.avg_trade_duration_hours = (
                        (snapshot.avg_trade_duration_hours * (snapshot.trades_closed - 1) +
                         duration / 3600.0) / snapshot.trades_closed
                    )

            # ── Count by event_type (audit events) ──
            if et == EventType.ORDER_BLOCKED.value:
                snapshot.orders_blocked += 1
            elif et == EventType.POSITION_OPENED.value:
                snapshot.positions_opened += 1
            elif et == EventType.KILL_SWITCH_TRANSITION.value:
                snapshot.kill_switch_events += 1
            elif et == EventType.KILL_SWITCH_BLOCK.value:
                snapshot.kill_switch_blocks += 1
            elif et == EventType.NEWS_HALT.value:
                snapshot.news_halts += 1
            elif et == EventType.DRIFT_ALERT.value:
                snapshot.drift_alerts += 1
            elif et == EventType.DRIFT_EMERGENCY.value:
                snapshot.drift_emergencies += 1
            elif et == EventType.SLIPPAGE_ALERT.value:
                snapshot.slippage_alerts += 1
            elif et == EventType.SLIPPAGE_HALT.value:
                snapshot.slippage_halts += 1
            elif et == EventType.WATCHDOG_RESTART.value:
                snapshot.watchdog_restarts += 1

        # ── Derived metrics ──
        if snapshot.trades_closed > 0:
            snapshot.win_rate = snapshot.winning_trades / snapshot.trades_closed
            gross_profit = sum(
                r["data"].get("pnl_usd", 0)
                for r in records if r.get("record_type") == "EXIT"
                and r["data"].get("pnl_usd", 0) > 0
            )
            gross_loss = abs(sum(
                r["data"].get("pnl_usd", 0)
                for r in records if r.get("record_type") == "EXIT"
                and r["data"].get("pnl_usd", 0) < 0
            ))
            snapshot.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
            # Average RR (simplified: avg win / avg loss)
            if snapshot.losing_trades > 0:
                avg_win = gross_profit / snapshot.winning_trades if snapshot.winning_trades > 0 else 0
                avg_loss = gross_loss / snapshot.losing_trades
                snapshot.avg_rr = avg_win / avg_loss if avg_loss > 0 else 0

        # ── Daily PnL (last 24h) ──
        cutoff_24h = now - 86400
        snapshot.daily_pnl_usd = sum(
            r["data"].get("pnl_usd", 0) for r in records
            if r.get("record_type") == "EXIT"
            and r.get("timestamp", 0) >= cutoff_24h
        )

        # ── Weekly PnL (last 7 days) ──
        cutoff_7d = now - 7 * 86400
        snapshot.weekly_pnl_usd = sum(
            r["data"].get("pnl_usd", 0) for r in records
            if r.get("record_type") == "EXIT"
            and r.get("timestamp", 0) >= cutoff_7d
        )

        # ── Max drawdown (simplified: from peak equity) ──
        equity_curve = []
        running_pnl = 0
        for r in records:
            if r.get("record_type") == "EXIT":
                running_pnl += r["data"].get("pnl_usd", 0)
                equity_curve.append(running_pnl)
        if equity_curve:
            peak = equity_curve[0]
            max_dd = 0
            for eq in equity_curve:
                if eq > peak:
                    peak = eq
                dd = peak - eq
                if dd > max_dd:
                    max_dd = dd
            snapshot.max_drawdown_pct = (max_dd / abs(peak) * 100) if peak != 0 else 0

        # ── Slippage stats (from HEARTBEAT or slippage events) ──
        slip_values = []
        for r in records:
            if r.get("record_type") == "HEARTBEAT":
                data = r.get("data", {})
                if "slippage_pips" in data:
                    slip_values.append(data["slippage_pips"])
        if slip_values:
            snapshot.slippage_mean_pips = sum(slip_values) / len(slip_values)
            sorted_slip = sorted(slip_values)
            snapshot.slippage_p95_pips = sorted_slip[int(len(sorted_slip) * 0.95)]

        # ── Drift stats (from HEARTBEAT) ──
        for r in records:
            if r.get("record_type") == "HEARTBEAT":
                data = r.get("data", {})
                if "psi" in data:
                    snapshot.drift_psi = data["psi"]
                if "ece" in data:
                    snapshot.drift_ece = data["ece"]
                if "brier" in data:
                    snapshot.drift_brier = data["brier"]

        self._last_snapshot = snapshot
        return snapshot

    def get_snapshot(self) -> Optional[MetricsSnapshot]:
        """Return last collected snapshot (or None if not collected yet)."""
        return self._last_snapshot

    def save_json(self, snapshot: Optional[MetricsSnapshot] = None) -> str:
        """Save snapshot as JSON. Returns path."""
        snap = snapshot or self._last_snapshot
        if snap is None:
            raise ValueError("No snapshot to save — call collect() first")
        path = self.output_dir / "metrics_snapshot.json"
        with open(path, "w") as f:
            json.dump(asdict(snap), f, indent=2, default=str)
        logger.info(f"Metrics snapshot saved: {path}")
        return str(path)

    def save_csv(self, snapshot: Optional[MetricsSnapshot] = None) -> str:
        """Append snapshot to CSV time series. Returns path."""
        snap = snapshot or self._last_snapshot
        if snap is None:
            raise ValueError("No snapshot to save — call collect() first")
        path = self.output_dir / "metrics_timeseries.csv"
        write_header = not path.exists()
        with open(path, "a", newline="") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(asdict(snap).keys())
            writer.writerow(asdict(snap).values())
        logger.info(f"Metrics CSV appended: {path}")
        return str(path)
