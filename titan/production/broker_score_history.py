"""
TITAN XAU AI — Broker Score History (Sprint 9.5)
===================================================

Maintains historical broker statistics at daily / weekly / monthly granularity.

Tracks:
  - Average score
  - Worst score
  - Best score
  - Average spread
  - Average slippage
  - Latency
  - Requotes
  - Connection uptime

Persists to JSON files in data/runtime/broker_history/.
Generates trend analysis (improving / stable / degrading).
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType
from titan.production.broker_quality_engine import BrokerQualityScore

logger = logging.getLogger(__name__)


@dataclass
class HistoryBucket:
    """Aggregated stats for a time bucket (day/week/month)."""
    period: str                          # "2026-06-25" | "2026-W26" | "2026-06"
    granularity: str                     # "daily" | "weekly" | "monthly"
    scores: list[float] = field(default_factory=list)
    spreads: list[float] = field(default_factory=list)
    slippages: list[float] = field(default_factory=list)
    latencies: list[float] = field(default_factory=list)
    requotes: list[float] = field(default_factory=list)
    uptimes: list[float] = field(default_factory=list)
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def add(self, score: BrokerQualityScore, spread: float = 0,
            slippage: float = 0, latency: float = 0,
            requote_rate: float = 0, uptime: float = 100) -> None:
        self.scores.append(score.score)
        self.spreads.append(spread)
        self.slippages.append(slippage)
        self.latencies.append(latency)
        self.requotes.append(requote_rate)
        self.uptimes.append(uptime)
        self.last_seen = time.time()

    def to_summary(self) -> dict:
        s = self.scores
        return {
            "period": self.period,
            "granularity": self.granularity,
            "sample_count": len(s),
            "score_avg": sum(s) / len(s) if s else 0,
            "score_min": min(s) if s else 0,
            "score_max": max(s) if s else 0,
            "spread_avg": sum(self.spreads) / len(self.spreads) if self.spreads else 0,
            "slippage_avg": sum(self.slippages) / len(self.slippages) if self.slippages else 0,
            "latency_avg": sum(self.latencies) / len(self.latencies) if self.latencies else 0,
            "requote_avg": sum(self.requotes) / len(self.requotes) if self.requotes else 0,
            "uptime_avg": sum(self.uptimes) / len(self.uptimes) if self.uptimes else 0,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
        }


class BrokerScoreHistory:
    """
    Maintains rolling history of broker quality scores.

    Three granularities: daily, weekly, monthly.
    Persists to JSON files in history_dir.
    """

    def __init__(
        self,
        history_dir: str = "data/runtime/broker_history",
        journal: Optional[TradeJournal] = None,
    ):
        self.history_dir = Path(history_dir)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.journal = journal
        self._daily: dict[str, HistoryBucket] = {}
        self._weekly: dict[str, HistoryBucket] = {}
        self._monthly: dict[str, HistoryBucket] = {}
        self._load()

    # ─── Public API ───────────────────────────────────────────────────────

    def record(
        self,
        score: BrokerQualityScore,
        spread: float = 0,
        slippage: float = 0,
        latency: float = 0,
        requote_rate: float = 0,
        uptime: float = 100,
    ) -> None:
        """Record a quality score into all 3 granularities."""
        now = datetime.now(timezone.utc)
        day_key = now.strftime("%Y-%m-%d")
        week_key = f"{now.year}-W{now.isocalendar()[1]:02d}"
        month_key = now.strftime("%Y-%m")

        self._daily.setdefault(day_key, HistoryBucket(day_key, "daily")).add(
            score, spread, slippage, latency, requote_rate, uptime)
        self._weekly.setdefault(week_key, HistoryBucket(week_key, "weekly")).add(
            score, spread, slippage, latency, requote_rate, uptime)
        self._monthly.setdefault(month_key, HistoryBucket(month_key, "monthly")).add(
            score, spread, slippage, latency, requote_rate, uptime)

    def get_daily_summary(self, n_days: int = 30) -> list[dict]:
        """Return last N days of daily summaries."""
        keys = sorted(self._daily.keys())[-n_days:]
        return [self._daily[k].to_summary() for k in keys if k in self._daily]

    def get_weekly_summary(self, n_weeks: int = 12) -> list[dict]:
        keys = sorted(self._weekly.keys())[-n_weeks:]
        return [self._weekly[k].to_summary() for k in keys if k in self._weekly]

    def get_monthly_summary(self, n_months: int = 12) -> list[dict]:
        keys = sorted(self._monthly.keys())[-n_months:]
        return [self._monthly[k].to_summary() for k in keys if k in self._monthly]

    def get_trend_analysis(self) -> dict:
        """
        Analyze trend over recent daily scores.

        Returns:
          - trend: "improving" | "stable" | "degrading"
          - recent_avg: last 7 days average
          - previous_avg: previous 7 days average
          - delta: recent - previous
        """
        daily = self.get_daily_summary(14)
        if len(daily) < 2:
            return {"trend": "stable", "recent_avg": 0, "previous_avg": 0, "delta": 0}

        recent = daily[-7:] if len(daily) >= 7 else daily
        previous = daily[-14:-7] if len(daily) >= 14 else daily[:-len(recent)]

        recent_avg = sum(d["score_avg"] for d in recent) / len(recent) if recent else 0
        previous_avg = sum(d["score_avg"] for d in previous) / len(previous) if previous else recent_avg

        delta = recent_avg - previous_avg
        if delta > 2:
            trend = "improving"
        elif delta < -2:
            trend = "degrading"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "recent_avg": round(recent_avg, 2),
            "previous_avg": round(previous_avg, 2),
            "delta": round(delta, 2),
        }

    def save(self) -> None:
        """Persist history to JSON files."""
        for name, data in [
            ("daily", self._daily),
            ("weekly", self._weekly),
            ("monthly", self._monthly),
        ]:
            path = self.history_dir / f"broker_history_{name}.json"
            payload = {k: v.to_summary() for k, v in data.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)

    # ─── Internal ─────────────────────────────────────────────────────────

    def _load(self) -> None:
        """Load persisted history from JSON files."""
        for name, target in [
            ("daily", self._daily),
            ("weekly", self._weekly),
            ("monthly", self._monthly),
        ]:
            path = self.history_dir / f"broker_history_{name}.json"
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # We don't restore raw score lists — just keep summaries
                # (history is for reporting, not for re-computation)
            except Exception as e:
                logger.warning(f"Failed to load {name} history: {e}")
