"""
TITAN XAU AI — Daily/Weekly Report Generator (Sprint 6)

Generates daily_report.json and weekly_report.json from journal data.
Journal is the single source of truth — NO in-memory state.

Usage:
    generator = ReportGenerator(journal_path="data/runtime/journal.jsonl",
                                 output_dir="data/reports")
    generator.generate_daily_report(date="2026-06-23")
    generator.generate_weekly_report(week_start="2026-06-17")
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta, date as date_class
from pathlib import Path
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


@dataclass
class DailyReport:
    """Daily trading report."""
    date: str
    utc_generated: str
    # Signal metrics
    signals_generated: int = 0
    signals_accepted: int = 0
    signals_rejected: int = 0
    # Trade metrics
    trades_closed: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    pnl_usd: float = 0.0
    best_trade_usd: float = 0.0
    worst_trade_usd: float = 0.0
    avg_trade_duration_hours: float = 0.0
    max_drawdown_pct: float = 0.0
    # Safety metrics
    kill_switch_events: int = 0
    kill_switch_blocks: int = 0
    news_halts: int = 0
    drift_alerts: int = 0
    drift_emergencies: int = 0
    slippage_alerts: int = 0
    slippage_halts: int = 0
    watchdog_restarts: int = 0
    # Runtime
    runtime_uptime_hours: float = 0.0
    # Raw data
    journal_records_processed: int = 0


@dataclass
class WeeklyReport:
    """Weekly trading report."""
    week_start: str
    week_end: str
    utc_generated: str
    # Aggregate metrics
    total_signals: int = 0
    total_trades: int = 0
    total_pnl_usd: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    best_day_pnl: float = 0.0
    worst_day_pnl: float = 0.0
    max_drawdown_pct: float = 0.0
    # Safety
    total_kill_switch_events: int = 0
    total_drift_alerts: int = 0
    total_slippage_halts: int = 0
    total_watchdog_restarts: int = 0
    # Daily breakdown
    daily_reports: list[dict] = field(default_factory=list)
    runtime_uptime_hours: float = 0.0


class ReportGenerator:
    """
    Generates daily + weekly reports from journal data.
    Journal is the ONLY source of truth.
    """

    def __init__(self, journal_path: str, output_dir: str = "data/reports"):
        self.journal_path = journal_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_daily_report(self, date: Optional[str] = None) -> DailyReport:
        """
        Generate daily report for a specific date.
        Date format: "YYYY-MM-DD" (defaults to today UTC).
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Parse date range (UTC day)
        target = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        start_ts = target.timestamp()
        end_ts = (target + timedelta(days=1)).timestamp()

        # Read journal + filter by date
        journal = TradeJournal(path=self.journal_path)
        journal.flush()
        all_records = journal.read_all()
        day_records = [r for r in all_records if start_ts <= r.get("timestamp", 0) < end_ts]

        report = DailyReport(
            date=date,
            utc_generated=datetime.now(timezone.utc).isoformat(),
            journal_records_processed=len(day_records),
        )

        # ── Aggregate metrics ──
        pnls = []
        durations = []
        for r in day_records:
            rt = r.get("record_type", "")
            et = r.get("event_type", "")
            data = r.get("data", {})

            if rt == "SIGNAL":
                report.signals_generated += 1
            elif rt == "DECISION":
                if data.get("accepted"):
                    report.signals_accepted += 1
                else:
                    report.signals_rejected += 1
            elif rt == "EXIT":
                report.trades_closed += 1
                pnl = data.get("pnl_usd", 0.0)
                pnls.append(pnl)
                report.pnl_usd += pnl
                if pnl > 0:
                    report.winning_trades += 1
                    if pnl > report.best_trade_usd:
                        report.best_trade_usd = pnl
                elif pnl < 0:
                    report.losing_trades += 1
                    if pnl < report.worst_trade_usd:
                        report.worst_trade_usd = pnl
                dur = data.get("holding_time_seconds", 0)
                if dur > 0:
                    durations.append(dur / 3600.0)

            # Event types
            if et == EventType.KILL_SWITCH_TRANSITION.value:
                report.kill_switch_events += 1
            elif et == EventType.KILL_SWITCH_BLOCK.value:
                report.kill_switch_blocks += 1
            elif et == EventType.NEWS_HALT.value:
                report.news_halts += 1
            elif et == EventType.DRIFT_ALERT.value:
                report.drift_alerts += 1
            elif et == EventType.DRIFT_EMERGENCY.value:
                report.drift_emergencies += 1
            elif et == EventType.SLIPPAGE_ALERT.value:
                report.slippage_alerts += 1
            elif et == EventType.SLIPPAGE_HALT.value:
                report.slippage_halts += 1
            elif et == EventType.WATCHDOG_RESTART.value:
                report.watchdog_restarts += 1

        # Derived
        if report.trades_closed > 0:
            report.win_rate = report.winning_trades / report.trades_closed
            gross_profit = sum(p for p in pnls if p > 0)
            gross_loss = abs(sum(p for p in pnls if p < 0))
            report.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
            if durations:
                report.avg_trade_duration_hours = sum(durations) / len(durations)

        # Runtime uptime (from STARTUP to SHUTDOWN events in the day)
        startups = [r for r in day_records if r.get("event_type") == EventType.STARTUP.value]
        shutdowns = [r for r in day_records if r.get("event_type") == EventType.SHUTDOWN.value]
        if startups:
            first_startup = min(r["timestamp"] for r in startups)
            if shutdowns:
                last_shutdown = max(r["timestamp"] for r in shutdowns)
                report.runtime_uptime_hours = (last_shutdown - first_startup) / 3600.0
            else:
                report.runtime_uptime_hours = (time.time() - first_startup) / 3600.0

        # ── Save report ──
        path = self.output_dir / f"daily_report_{date}.json"
        # Sprint 9.0.1: explicit UTF-8 for Windows cp1252 compatibility.
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, default=str)
        logger.info(f"Daily report saved: {path}")

        # ── Journal the summary ──
        journal.log_daily_summary(asdict(report))

        return report

    def generate_weekly_report(self, week_start: Optional[str] = None) -> WeeklyReport:
        """
        Generate weekly report starting from week_start.
        Date format: "YYYY-MM-DD" (defaults to 7 days ago).
        """
        if week_start is None:
            week_start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

        target_start = datetime.strptime(week_start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        target_end = target_start + timedelta(days=7)
        start_ts = target_start.timestamp()
        end_ts = target_end.timestamp()

        report = WeeklyReport(
            week_start=week_start,
            week_end=target_end.strftime("%Y-%m-%d"),
            utc_generated=datetime.now(timezone.utc).isoformat(),
        )

        # Generate daily reports for each day
        daily_pnls = []
        for i in range(7):
            day = (target_start + timedelta(days=i)).strftime("%Y-%m-%d")
            daily = self.generate_daily_report(date=day)
            report.daily_reports.append(asdict(daily))
            report.total_signals += daily.signals_generated
            report.total_trades += daily.trades_closed
            report.total_pnl_usd += daily.pnl_usd
            report.total_kill_switch_events += daily.kill_switch_events
            report.total_drift_alerts += daily.drift_alerts
            report.total_slippage_halts += daily.slippage_halts
            report.total_watchdog_restarts += daily.watchdog_restarts
            report.runtime_uptime_hours += daily.runtime_uptime_hours
            if daily.pnl_usd > 0 and daily.pnl_usd > report.best_day_pnl:
                report.best_day_pnl = daily.pnl_usd
            if daily.pnl_usd < 0 and daily.pnl_usd < report.worst_day_pnl:
                report.worst_day_pnl = daily.pnl_usd
            daily_pnls.append(daily.pnl_usd)

        if report.total_trades > 0:
            total_wins = sum(d["winning_trades"] for d in report.daily_reports)
            report.win_rate = total_wins / report.total_trades

        # Max drawdown across the week
        running_pnl = 0
        peak = 0
        max_dd = 0
        for pnl in daily_pnls:
            running_pnl += pnl
            if running_pnl > peak:
                peak = running_pnl
            dd = peak - running_pnl
            if dd > max_dd:
                max_dd = dd
        report.max_drawdown_pct = (max_dd / abs(peak) * 100) if peak != 0 else 0

        # ── Save weekly report ──
        path = self.output_dir / f"weekly_report_{week_start}.json"
        # Sprint 9.0.1: explicit UTF-8 for Windows cp1252 compatibility.
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2, default=str)
        logger.info(f"Weekly report saved: {path}")

        # ── Journal the summary ──
        journal = TradeJournal(path=self.journal_path)
        journal.log_weekly_summary(asdict(report))

        return report
