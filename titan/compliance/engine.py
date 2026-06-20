"""
TITAN XAU AI — Compliance Engine (M22.3)

High-level wrapper around the rule engine. Maintains account state,
runs rule evaluation cycle, and produces a ComplianceReport for the
CEO Supervisor / Risk Engine.

Integration points:
- Risk Engine: receives ComplianceReport → applies CLOSE_ALL/HALT actions
- CEO Supervisor: receives compliance_score → factors into system status
- Database: persists state in compliance_state / compliance_audit tables
- License Guard: compliance is gated to PRO/ENTERPRISE license feature
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from titan.compliance.profiles import FirmProfile, FirmId, PropFirmProfiles
from titan.compliance.rule_engine import (
    ComplianceRuleEngine, RuleAction, RuleResult, RuleContext,
)

logger = logging.getLogger(__name__)


@dataclass
class ComplianceState:
    """Mutable account state tracked across the trading day."""
    initial_balance: float
    current_balance: float
    current_equity: float
    peak_equity: float
    start_of_day_balance: float
    start_of_day_equity: float
    trading_days_elapsed: int = 0
    today_realized_pnl: float = 0.0
    today_unrealized_pnl: float = 0.0
    largest_single_day_profit: float = 0.0
    total_realized_pnl: float = 0.0
    last_sod_reset: Optional[datetime] = None

    def update_pnl(self, realized: float = 0.0, unrealized: float = 0.0) -> None:
        if realized:
            self.today_realized_pnl += realized
            self.total_realized_pnl += realized
            if self.today_realized_pnl > self.largest_single_day_profit:
                self.largest_single_day_profit = self.today_realized_pnl
        if unrealized:
            self.today_unrealized_pnl = unrealized
        # Update equity
        self.current_equity = self.current_balance + self.today_unrealized_pnl
        if self.current_equity > self.peak_equity:
            self.peak_equity = self.current_equity

    def reset_daily(self, now: datetime) -> None:
        """Called at firm's daily reset time."""
        self.start_of_day_balance = self.current_balance
        self.start_of_day_equity = self.current_equity
        self.today_realized_pnl = 0.0
        self.today_unrealized_pnl = 0.0
        self.trading_days_elapsed += 1
        self.last_sod_reset = now

    def apply_realized(self, pnl: float) -> None:
        """Apply a closed-trade P&L."""
        self.current_balance += pnl
        self.update_pnl(realized=pnl)


@dataclass
class ComplianceReport:
    timestamp: float
    firm_id: str
    firm_name: str
    overall_action: RuleAction
    rule_results: list[RuleResult] = field(default_factory=list)
    compliance_score: float = 100.0       # 0-100 (100 = fully compliant)
    can_open_new: bool = True
    must_close_all: bool = False
    must_halt: bool = False
    warnings: list[str] = field(default_factory=list)
    breaches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "firm_id": self.firm_id,
            "firm_name": self.firm_name,
            "overall_action": self.overall_action.value,
            "rule_results": [
                {"rule_id": r.rule_id, "action": r.action.value,
                 "message": r.message, "severity": r.severity}
                for r in self.rule_results
            ],
            "compliance_score": self.compliance_score,
            "can_open_new": self.can_open_new,
            "must_close_all": self.must_close_all,
            "must_halt": self.must_halt,
            "warnings": self.warnings,
            "breaches": self.breaches,
        }


class ComplianceEngine:
    """
    Top-level compliance engine for a single firm profile.
    Holds state, runs rule cycle, produces ComplianceReport.
    """

    def __init__(self, profile: FirmProfile, phase: str = "phase1"):
        self.profile = profile
        self._rule_engine = ComplianceRuleEngine(phase=phase)
        self._state = ComplianceState(
            initial_balance=profile.initial_balance,
            current_balance=profile.initial_balance,
            current_equity=profile.initial_balance,
            peak_equity=profile.initial_balance,
            start_of_day_balance=profile.initial_balance,
            start_of_day_equity=profile.initial_balance,
        )

    @classmethod
    def for_firm(cls, firm_id: FirmId, balance: float = 100_000.0,
                 phase: str = "phase1") -> "ComplianceEngine":
        profile = PropFirmProfiles.get(firm_id, balance)
        return cls(profile, phase=phase)

    # ─── State mutations ──────────────────────────────────────────────

    def apply_realized_pnl(self, pnl: float) -> None:
        self._state.apply_realized(pnl)

    def update_unrealized(self, pnl: float) -> None:
        self._state.update_pnl(unrealized=pnl)

    def reset_daily(self, now: Optional[datetime] = None) -> None:
        self._state.reset_daily(now or datetime.now(timezone.utc))

    def set_open_positions(self, count: int, net_lots: float = 0.0,
                           gross_lots: float = 0.0, hedged: bool = False) -> None:
        self._open_positions = count
        self._net_lots = net_lots
        self._gross_lots = gross_lots
        self._hedged = hedged

    def set_pending_lot(self, lots: float) -> None:
        self._pending_lot = lots

    def set_news_state(self, is_news: bool, minutes_since: int = 0) -> None:
        self._is_news = is_news
        self._minutes_since_news = minutes_since

    # ─── Cycle ─────────────────────────────────────────────────────────

    def evaluate(self, now: Optional[datetime] = None) -> ComplianceReport:
        """Run all rules against current state. Returns ComplianceReport."""
        now = now or datetime.now(timezone.utc)
        is_weekend = now.weekday() >= 5  # Sat=5, Sun=6

        ctx = RuleContext(
            initial_balance=self._state.initial_balance,
            current_balance=self._state.current_balance,
            current_equity=self._state.current_equity,
            peak_equity=self._state.peak_equity,
            start_of_day_balance=self._state.start_of_day_balance,
            start_of_day_equity=self._state.start_of_day_equity,
            now=now,
            trading_days_elapsed=self._state.trading_days_elapsed,
            is_weekend=is_weekend,
            is_high_impact_news=getattr(self, "_is_news", False),
            minutes_since_news=getattr(self, "_minutes_since_news", 0),
            open_positions=getattr(self, "_open_positions", 0),
            net_exposure=getattr(self, "_net_lots", 0.0),
            gross_exposure=getattr(self, "_gross_lots", 0.0),
            pending_lot_size=getattr(self, "_pending_lot", 0.0),
            has_hedged_positions=getattr(self, "_hedged", False),
            today_realized_pnl=self._state.today_realized_pnl,
            today_unrealized_pnl=self._state.today_unrealized_pnl,
            largest_single_day_profit=self._state.largest_single_day_profit,
            total_realized_pnl=self._state.total_realized_pnl,
        )

        results = self._rule_engine.evaluate_all(ctx, self.profile)
        overall = ComplianceRuleEngine.aggregate_action(results)

        # Score: average severity across all rules (inverted)
        avg_severity = sum(r.severity for r in results) / max(1, len(results))
        compliance_score = max(0.0, 100.0 - avg_severity)

        # Derive flags
        can_open_new = overall not in (RuleAction.DISABLE_NEW, RuleAction.REDUCE_POSITION,
                                       RuleAction.CLOSE_ALL, RuleAction.HALT)
        must_close_all = overall in (RuleAction.CLOSE_ALL, RuleAction.HALT)
        must_halt = overall == RuleAction.HALT

        warnings = [r.message for r in results if r.action == RuleAction.WARN]
        breaches = [r.message for r in results
                    if r.action in (RuleAction.DISABLE_NEW, RuleAction.REDUCE_POSITION,
                                    RuleAction.CLOSE_ALL, RuleAction.HALT)]

        return ComplianceReport(
            timestamp=time.time(),
            firm_id=self.profile.firm_id.value,
            firm_name=self.profile.name,
            overall_action=overall,
            rule_results=results,
            compliance_score=compliance_score,
            can_open_new=can_open_new,
            must_close_all=must_close_all,
            must_halt=must_halt,
            warnings=warnings,
            breaches=breaches,
        )

    @property
    def state(self) -> ComplianceState:
        return self._state

    @property
    def firm_id(self) -> FirmId:
        return self.profile.firm_id

    @property
    def firm_name(self) -> str:
        return self.profile.name


__all__ = ["ComplianceEngine", "ComplianceState", "ComplianceReport"]
