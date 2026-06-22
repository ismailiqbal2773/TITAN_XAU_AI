"""
TITAN XAU AI — News Filter (Production Sprint 4)

Economic calendar filter — blocks new trades around high-impact news events.

Two modes:
  1. CSV file (offline, no API required) — manual download from ForexFactory
  2. Programmatic (for future API integration)

Supports: NFP, CPI, FOMC, ECB, BOE + custom event types.

Block window:
  - 30 minutes BEFORE high-impact event
  - 30 minutes AFTER high-impact event

Usage:
    nf = NewsFilter(csv_path="data/economic_calendar.csv")
    if nf.is_halt_active(now=datetime.utcnow()):
        # block new trades
        ...
"""
from __future__ import annotations

import csv
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ─── High-impact event type keywords ──────────────────────────────────────────
HIGH_IMPACT_KEYWORDS = {
    "NFP": ["nonfarm", "non-farm", "nfp", "employment change"],
    "CPI": ["cpi", "consumer price", "inflation"],
    "FOMC": ["fomc", "federal open market", "rate decision", "interest rate"],
    "ECB": ["ecb", "european central bank", "deposit rate"],
    "BOE": ["boe", "bank of england", "official bank rate"],
}

DEFAULT_BLOCK_WINDOW_MINUTES = 30


@dataclass
class NewsEvent:
    """Single economic calendar event."""
    timestamp: datetime          # UTC
    event_type: str              # NFP, CPI, FOMC, ECB, BOE, or custom
    description: str = ""
    impact: str = "HIGH"         # HIGH | MEDIUM | LOW
    currency: str = "USD"        # USD, EUR, GBP, etc.
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None

    def is_high_impact(self) -> bool:
        return self.impact.upper() == "HIGH"

    def block_window_start(self, block_minutes: int = DEFAULT_BLOCK_WINDOW_MINUTES) -> datetime:
        return self.timestamp - timedelta(minutes=block_minutes)

    def block_window_end(self, block_minutes: int = DEFAULT_BLOCK_WINDOW_MINUTES) -> datetime:
        return self.timestamp + timedelta(minutes=block_minutes)

    def is_in_block_window(self, now: datetime,
                           block_minutes: int = DEFAULT_BLOCK_WINDOW_MINUTES) -> bool:
        return self.block_window_start(block_minutes) <= now <= self.block_window_end(block_minutes)


@dataclass
class NewsHaltStatus:
    """Result of news halt check."""
    is_halt_active: bool
    reason: str = ""
    blocking_event: Optional[NewsEvent] = None
    next_event: Optional[NewsEvent] = None
    minutes_until_next: Optional[float] = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __repr__(self) -> str:
        if self.is_halt_active:
            return (f"NewsHaltStatus(HALT, reason={self.reason}, "
                    f"event={self.blocking_event.event_type if self.blocking_event else 'unknown'})")
        return f"NewsHaltStatus(CLEAR, next={self.next_event.event_type if self.next_event else 'none'})"


class NewsFilter:
    """
    Economic calendar news filter.

    Usage:
        nf = NewsFilter(csv_path="economic_calendar.csv")
        status = nf.check(now=datetime.now(timezone.utc))
        if status.is_halt_active:
            # block new trades
    """

    def __init__(
        self,
        csv_path: Optional[str] = None,
        block_window_minutes: int = DEFAULT_BLOCK_WINDOW_MINUTES,
        event_types: Optional[set[str]] = None,
    ):
        """
        Args:
            csv_path: Path to CSV file with columns: timestamp,event_type,impact,currency,description
            block_window_minutes: Block window before/after each event
            event_types: Set of event types to filter (default: NFP, CPI, FOMC, ECB, BOE)
        """
        self.csv_path = csv_path
        self.block_window_minutes = block_window_minutes
        self.event_types = event_types or set(HIGH_IMPACT_KEYWORDS.keys())
        self._events: list[NewsEvent] = []
        if csv_path and os.path.exists(csv_path):
            self.load_csv(csv_path)
        logger.info(
            f"NewsFilter initialized: {len(self._events)} events loaded, "
            f"block_window=±{block_window_minutes}min"
        )

    # ─── CSV loading ────────────────────────────────────────────────────

    def load_csv(self, path: str) -> int:
        """
        Load events from CSV. Expected columns (header row required):
            timestamp, event_type, impact, currency, description

        Timestamp format: ISO 8601 (e.g., "2026-06-23T12:30:00Z")
        or "2026-06-23 12:30:00" (UTC assumed).

        Returns number of events loaded.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"News CSV not found: {path}")

        events = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts_str = row.get("timestamp") or row.get("time") or row.get("date")
                    if not ts_str:
                        continue
                    # Parse timestamp (assume UTC if no tz info)
                    ts = self._parse_timestamp(ts_str)
                    event_type = (row.get("event_type") or row.get("type") or "").upper().strip()
                    impact = (row.get("impact") or "HIGH").upper().strip()
                    currency = (row.get("currency") or "USD").upper().strip()
                    description = row.get("description") or row.get("event") or ""

                    # Auto-classify event type if not provided
                    if not event_type or event_type == "":
                        event_type = self._classify_event(description)

                    # Only keep if it's a tracked type or HIGH impact
                    if event_type in self.event_types or impact == "HIGH":
                        events.append(NewsEvent(
                            timestamp=ts,
                            event_type=event_type or "UNKNOWN",
                            description=description,
                            impact=impact,
                            currency=currency,
                        ))
                except Exception as e:
                    logger.warning(f"Skipping CSV row {row}: {e}")
                    continue

        self._events = sorted(events, key=lambda e: e.timestamp)
        self.csv_path = path
        logger.info(f"Loaded {len(self._events)} news events from {path}")
        return len(self._events)

    def _parse_timestamp(self, ts_str: str) -> datetime:
        """Parse timestamp string to UTC datetime."""
        ts_str = ts_str.strip()
        # Try ISO format with Z
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(ts_str)
        except ValueError:
            # Try "YYYY-MM-DD HH:MM:SS"
            dt = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _classify_event(self, description: str) -> str:
        """Auto-classify event type from description text."""
        desc_lower = description.lower()
        for event_type, keywords in HIGH_IMPACT_KEYWORDS.items():
            if any(kw in desc_lower for kw in keywords):
                return event_type
        return "UNKNOWN"

    # ─── Programmatic event API ─────────────────────────────────────────

    def add_event(self, event: NewsEvent) -> None:
        """Add an event programmatically (no CSV required)."""
        if event.timestamp.tzinfo is None:
            event.timestamp = event.timestamp.replace(tzinfo=timezone.utc)
        self._events.append(event)
        self._events.sort(key=lambda e: e.timestamp)

    def add_events(self, events: list[NewsEvent]) -> None:
        """Add multiple events."""
        for e in events:
            self.add_event(e)

    # ─── Halt check ─────────────────────────────────────────────────────

    def is_halt_active(self, now: Optional[datetime] = None) -> bool:
        """Quick boolean check — True if any high-impact event is in block window."""
        return self.check(now).is_halt_active

    def check(self, now: Optional[datetime] = None) -> NewsHaltStatus:
        """
        Check if news halt should be active.

        Args:
            now: Current datetime (UTC). Defaults to datetime.now(timezone.utc).
        Returns:
            NewsHaltStatus with halt flag + blocking event info
        """
        if now is None:
            now = datetime.now(timezone.utc)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # Find any event currently in block window
        for event in self._events:
            if not event.is_high_impact():
                continue
            if event.event_type not in self.event_types and event.event_type != "UNKNOWN":
                continue
            if event.is_in_block_window(now, self.block_window_minutes):
                return NewsHaltStatus(
                    is_halt_active=True,
                    reason=f"high_impact_news ({event.event_type})",
                    blocking_event=event,
                )

        # Find next upcoming event
        next_event = None
        for event in self._events:
            if event.timestamp > now and event.is_high_impact():
                if event.event_type in self.event_types or event.event_type == "UNKNOWN":
                    next_event = event
                    break

        minutes_until = None
        if next_event:
            delta = next_event.timestamp - now
            minutes_until = delta.total_seconds() / 60.0

        return NewsHaltStatus(
            is_halt_active=False,
            reason="clear",
            next_event=next_event,
            minutes_until_next=minutes_until,
        )

    # ─── Accessors ──────────────────────────────────────────────────────

    @property
    def event_count(self) -> int:
        return len(self._events)

    @property
    def events(self) -> list[NewsEvent]:
        return list(self._events)

    def get_events_in_window(self, start: datetime, end: datetime) -> list[NewsEvent]:
        """Return events between start and end (UTC)."""
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return [e for e in self._events if start <= e.timestamp <= end]


if __name__ == "__main__":
    # Smoke test with programmatic events
    from datetime import timedelta

    print("=" * 70)
    print("TITAN NewsFilter — Smoke Test")
    print("=" * 70)
    nf = NewsFilter()

    # Add NFP event 10 minutes from now
    now = datetime.now(timezone.utc)
    nf.add_event(NewsEvent(
        timestamp=now + timedelta(minutes=10),
        event_type="NFP",
        description="Non-Farm Employment Change",
        impact="HIGH",
        currency="USD",
    ))
    print(f"\nEvents loaded: {nf.event_count}")
    status = nf.check()
    print(f"Status (now): {status}")

    # Check 5 minutes before event (should be in block window)
    status2 = nf.check(now=now + timedelta(minutes=5))
    print(f"Status (5 min later, 5 min before event): {status2}")

    # Check 40 minutes after event (should be clear)
    status3 = nf.check(now=now + timedelta(minutes=50))
    print(f"Status (50 min later, 10 min after event): {status3}")
