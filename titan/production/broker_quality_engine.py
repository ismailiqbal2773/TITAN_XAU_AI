"""
TITAN XAU AI — Broker Quality Engine (Sprint 9.5)
====================================================

Continuously measures broker quality across 12 dimensions and computes
a single 0-100 Broker Quality Score.

Score bands:
  95-100 → Institutional
  85-94  → Excellent
  75-84  → Good
  60-74  → Average
  <60    → Unsafe

Dimensions measured:
  - Spread stability
  - Average spread
  - Spread spikes
  - Slippage
  - Requotes
  - Execution latency
  - Order rejection rate
  - Partial fills
  - Price gaps
  - Weekend behaviour
  - Connection stability
  - Symbol health

Journals EventType.BROKER_SCORE_UPDATED on every score update.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Optional

from titan.production.trade_journal import TradeJournal, EventType

logger = logging.getLogger(__name__)


# ─── Score bands ─────────────────────────────────────────────────────────────
BAND_INSTITUTIONAL = "institutional"     # 95-100
BAND_EXCELLENT = "excellent"             # 85-94
BAND_GOOD = "good"                       # 75-84
BAND_AVERAGE = "average"                 # 60-74
BAND_UNSAFE = "unsafe"                   # <60


def score_to_band(score: float) -> str:
    if score >= 95:
        return BAND_INSTITUTIONAL
    if score >= 85:
        return BAND_EXCELLENT
    if score >= 75:
        return BAND_GOOD
    if score >= 60:
        return BAND_AVERAGE
    return BAND_UNSAFE


# ─── Dataclasses ─────────────────────────────────────────────────────────────
@dataclass
class BrokerQualityInput:
    """Inputs to the quality score computation."""
    # Spread metrics (in USD)
    spread_usd: float = 0.0
    spread_mean_usd: float = 0.0
    spread_std_usd: float = 0.0
    spread_max_usd: float = 0.0
    spread_spike_count: int = 0          # spikes in last window
    # Slippage (in pips)
    slippage_mean_pips: float = 0.0
    slippage_p95_pips: float = 0.0
    # Order metrics
    requote_rate: float = 0.0            # 0-1
    rejection_rate: float = 0.0          # 0-1
    partial_fill_rate: float = 0.0       # 0-1
    # Latency
    latency_mean_ms: float = 0.0
    latency_p99_ms: float = 0.0
    # Price gaps
    gap_count: int = 0                   # gaps > threshold in last window
    # Connection
    connection_uptime_pct: float = 100.0 # 0-100
    reconnect_count: int = 0
    # Symbol health
    symbol_health: float = 100.0         # 0-100 (ticks received vs expected)


@dataclass
class BrokerQualityScore:
    """Computed quality score + breakdown."""
    score: float                          # 0-100
    band: str
    components: dict                      # per-dimension score
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 2),
            "band": self.band,
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "timestamp": self.timestamp,
        }


# ─── Engine ──────────────────────────────────────────────────────────────────
class BrokerQualityEngine:
    """
    Continuously scores broker quality.

    Uses a rolling window of inputs to compute a 0-100 score.
    Journals BROKER_SCORE_UPDATED on every evaluation.
    """

    def __init__(
        self,
        journal: Optional[TradeJournal] = None,
        window_size: int = 100,
    ):
        self.journal = journal
        self.window_size = window_size
        self._history: deque = deque(maxlen=window_size)
        self._last_score: Optional[BrokerQualityScore] = None
        self._last_band: Optional[str] = None
        self._evaluation_count: int = 0

    # ─── Public API ───────────────────────────────────────────────────────

    def evaluate(self, inp: BrokerQualityInput) -> BrokerQualityScore:
        """Compute quality score from inputs. Journals BROKER_SCORE_UPDATED."""
        components = self._compute_components(inp)
        # Weighted average — each component weighted equally (1/12)
        score = sum(components.values()) / len(components) if components else 0.0
        score = max(0.0, min(100.0, score))
        band = score_to_band(score)

        result = BrokerQualityScore(score=score, band=band, components=components)
        self._history.append(result)
        self._last_score = result
        self._evaluation_count += 1

        # Journal score update
        self._journal_event(EventType.BROKER_SCORE_UPDATED, result.to_dict() | {
            "spread_usd": inp.spread_usd,
            "spread_mean_usd": inp.spread_mean_usd,
            "slippage_mean_pips": inp.slippage_mean_pips,
            "requote_rate": inp.requote_rate,
            "rejection_rate": inp.rejection_rate,
            "latency_mean_ms": inp.latency_mean_ms,
            "connection_uptime_pct": inp.connection_uptime_pct,
        })

        return result

    @property
    def last_score(self) -> Optional[BrokerQualityScore]:
        return self._last_score

    @property
    def last_band(self) -> Optional[str]:
        return self._last_band

    @property
    def evaluation_count(self) -> int:
        return self._evaluation_count

    @property
    def score_history(self) -> list[BrokerQualityScore]:
        return list(self._history)

    # ─── Internal: component scoring (0-100 each) ─────────────────────────

    def _compute_components(self, inp: BrokerQualityInput) -> dict[str, float]:
        return {
            "spread_stability": self._score_spread_stability(inp),
            "average_spread": self._score_average_spread(inp),
            "spread_spikes": self._score_spread_spikes(inp),
            "slippage": self._score_slippage(inp),
            "requotes": self._score_requotes(inp),
            "execution_latency": self._score_latency(inp),
            "rejection_rate": self._score_rejection_rate(inp),
            "partial_fills": self._score_partial_fills(inp),
            "price_gaps": self._score_price_gaps(inp),
            "weekend_behavior": self._score_weekend(inp),
            "connection_stability": self._score_connection(inp),
            "symbol_health": self._score_symbol_health(inp),
        }

    def _score_spread_stability(self, inp: BrokerQualityInput) -> float:
        """Lower spread variance = higher score."""
        if inp.spread_mean_usd <= 0:
            return 100.0
        cv = inp.spread_std_usd / inp.spread_mean_usd  # coefficient of variation
        if cv <= 0.1:
            return 100.0
        if cv >= 1.0:
            return 0.0
        return 100.0 * (1.0 - cv)

    def _score_average_spread(self, inp: BrokerQualityInput) -> float:
        """Lower average spread = higher score. XAUUSD: $0.20 good, $1.00 avg, $3.00 bad."""
        s = inp.spread_mean_usd
        if s <= 0.20:
            return 100.0
        if s >= 3.0:
            return 0.0
        return 100.0 * (1.0 - (s - 0.20) / 2.80)

    def _score_spread_spikes(self, inp: BrokerQualityInput) -> float:
        """Fewer spikes = higher score."""
        if inp.spread_spike_count == 0:
            return 100.0
        if inp.spread_spike_count >= 10:
            return 0.0
        return 100.0 * (1.0 - inp.spread_spike_count / 10.0)

    def _score_slippage(self, inp: BrokerQualityInput) -> float:
        """Lower slippage = higher score. 0 pips = 100, 10 pips = 50, 20+ = 0."""
        s = inp.slippage_mean_pips
        if s <= 0:
            return 100.0
        if s >= 20:
            return 0.0
        return 100.0 * (1.0 - s / 20.0)

    def _score_requotes(self, inp: BrokerQualityInput) -> float:
        """Lower requote rate = higher score."""
        r = inp.requote_rate
        if r <= 0:
            return 100.0
        if r >= 0.20:
            return 0.0
        return 100.0 * (1.0 - r / 0.20)

    def _score_latency(self, inp: BrokerQualityInput) -> float:
        """Lower latency = higher score. <50ms = 100, 500ms = 50, 1000+ = 0."""
        l = inp.latency_mean_ms
        if l <= 50:
            return 100.0
        if l >= 1000:
            return 0.0
        return 100.0 * (1.0 - (l - 50) / 950.0)

    def _score_rejection_rate(self, inp: BrokerQualityInput) -> float:
        """Lower rejection rate = higher score."""
        r = inp.rejection_rate
        if r <= 0:
            return 100.0
        if r >= 0.20:
            return 0.0
        return 100.0 * (1.0 - r / 0.20)

    def _score_partial_fills(self, inp: BrokerQualityInput) -> float:
        """Lower partial fill rate = higher score."""
        r = inp.partial_fill_rate
        if r <= 0:
            return 100.0
        if r >= 0.30:
            return 0.0
        return 100.0 * (1.0 - r / 0.30)

    def _score_price_gaps(self, inp: BrokerQualityInput) -> float:
        """Fewer gaps = higher score."""
        if inp.gap_count == 0:
            return 100.0
        if inp.gap_count >= 5:
            return 0.0
        return 100.0 * (1.0 - inp.gap_count / 5.0)

    def _score_weekend(self, inp: BrokerQualityInput) -> float:
        """Weekend behavior — simplified: assume good unless gaps detected."""
        # Without live weekend data, default to 90 (slight caution)
        if inp.gap_count > 0:
            return 70.0
        return 90.0

    def _score_connection(self, inp: BrokerQualityInput) -> float:
        """Higher uptime = higher score."""
        u = inp.connection_uptime_pct
        return max(0.0, min(100.0, u))

    def _score_symbol_health(self, inp: BrokerQualityInput) -> float:
        """Symbol tick health."""
        return max(0.0, min(100.0, inp.symbol_health))

    def _journal_event(self, event_type: EventType, data: dict) -> None:
        if self.journal is None:
            return
        try:
            self.journal.log_event(event_type, data)
        except Exception as e:
            logger.error(f"Journal event {event_type.value} failed: {e}")
