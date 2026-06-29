"""
TITAN XAU AI — Broker Compatibility Matrix (Sprint 9.9.3.27)
=============================================================

Tracks known broker/server compatibility for demo micro execution.
Encodes verified facts from live testing so operators know which
brokers work, which reject, and which must not be used.

Status values:
  PASS     — single demo micro full-cycle passed
  REJECT   — broker rejects order_send (e.g. retcode 10006)
  BLOCKED  — broker blocks EA/Python automation entirely
  PENDING  — not yet tested
  UNKNOWN  — custom/unknown broker

Risk levels:
  LOW      — known to work
  MEDIUM   — not yet tested
  HIGH     — known to reject but may work with fallbacks
  CRITICAL — must not be used

Priority:
  HIGH       — primary test target
  MEDIUM     — secondary test target
  LOW        — low priority, known issues
  DO_NOT_USE — must not be used
"""
from __future__ import annotations
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class BrokerStatus(Enum):
    PASS = "PASS"
    REJECT = "REJECT"
    BLOCKED = "BLOCKED"
    PENDING = "PENDING"
    UNKNOWN = "UNKNOWN"


class BrokerRiskLevel(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class BrokerPriority(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    DO_NOT_USE = "DO_NOT_USE"


# ─── Known broker facts ───────────────────────────────────────────────────────
# These are VERIFIED facts from live testing across Sprints 9.9.3.14–9.9.3.26.

KNOWN_BROKERS = {
    "MetaQuotes-Demo": {
        "server_name": "MetaQuotes-Demo",
        "status": BrokerStatus.PASS.value,
        "account_type": "DEMO",
        "automation_allowed": True,
        "python_mt5_allowed": True,
        "ea_allowed": True,
        "raw_probe_status": "PASS",
        "raw_probe_retcode": 10009,
        "titan_micro_status": "PASS",
        "repeatability_status": "PENDING",
        "preferred_filling_mode": "IOC",
        "order_send_behavior": "ACCEPTS_IOC_NAKED_THEN_SLTP_MODIFY",
        "known_reject_reason": None,
        "risk_level": BrokerRiskLevel.LOW.value,
        "priority": BrokerPriority.HIGH.value,
        "notes": (
            "Raw MT5 probe PASSED. TITAN demo micro full-cycle PASSED. "
            "Uses raw working profile: naked IOC order (sl=0, tp=0) + "
            "SLTP modify after open. Repeatability 3-cycle PENDING until "
            "market opens (retcode 10018 MARKET_CLOSED on weekend)."
        ),
        "last_verified_utc": "2026-06-29T00:00:00Z",
    },
    "FBS-Demo": {
        "server_name": "FBS-Demo",
        "status": BrokerStatus.REJECT.value,
        "account_type": "DEMO",
        "automation_allowed": True,
        "python_mt5_allowed": True,
        "ea_allowed": True,
        "raw_probe_status": "NOT_RUN",
        "raw_probe_retcode": None,
        "titan_micro_status": "REJECT",
        "repeatability_status": "NOT_APPLICABLE",
        "preferred_filling_mode": None,
        "order_send_behavior": "REJECTS_PROTECTED_AND_NAKED_WITH_10006",
        "known_reject_reason": (
            "order_send returns retcode=10006 (TRADE_RETCODE_REJECT) for both "
            "protected (SL/TP attached) and naked (sl=0/tp=0) FOK orders. "
            "IOC order_check fails with retcode=10030 (INVALID_FILL). "
            "Automation appears enabled (trade_expert=True) but broker "
            "server rejects execution."
        ),
        "risk_level": BrokerRiskLevel.HIGH.value,
        "priority": BrokerPriority.LOW.value,
        "notes": (
            "FBS DEMO rejected all order_send attempts despite passing hard "
            "gate checks (trade_expert=True, demo account, armed). Broker "
            "compatibility fallback (naked + SLTP modify) also rejected. "
            "Low priority — may require broker-specific configuration."
        ),
        "last_verified_utc": "2026-06-29T00:00:00Z",
    },
    "FundedNext Free Trial": {
        "server_name": "FundedNext Free Trial",
        "status": BrokerStatus.BLOCKED.value,
        "account_type": "DEMO",
        "automation_allowed": False,
        "python_mt5_allowed": False,
        "ea_allowed": False,
        "raw_probe_status": "BLOCKED",
        "raw_probe_retcode": None,
        "titan_micro_status": "BLOCKED",
        "repeatability_status": "NOT_APPLICABLE",
        "preferred_filling_mode": None,
        "order_send_behavior": "AUTOMATION_NOT_ALLOWED",
        "known_reject_reason": (
            "FundedNext support confirmed: Free Trial accounts do not allow "
            "EA/Python automated trading. account_trade_expert may appear "
            "True but broker server blocks automated orders."
        ),
        "risk_level": BrokerRiskLevel.CRITICAL.value,
        "priority": BrokerPriority.DO_NOT_USE.value,
        "notes": (
            "DO NOT USE. FundedNext Free Trial blocks EA/Python automation. "
            "Support confirmed this is by design. Must upgrade to paid "
            "FundedNext account for automation support."
        ),
        "last_verified_utc": "2026-06-29T00:00:00Z",
    },
    "Exness Demo": {
        "server_name": "Exness Demo",
        "status": BrokerStatus.PENDING.value,
        "account_type": "DEMO",
        "automation_allowed": None,
        "python_mt5_allowed": None,
        "ea_allowed": None,
        "raw_probe_status": "PENDING",
        "raw_probe_retcode": None,
        "titan_micro_status": "PENDING",
        "repeatability_status": "PENDING",
        "preferred_filling_mode": None,
        "order_send_behavior": "UNKNOWN",
        "known_reject_reason": None,
        "risk_level": BrokerRiskLevel.MEDIUM.value,
        "priority": BrokerPriority.MEDIUM.value,
        "notes": "Not yet tested. Run raw_mt5_probe.py to verify.",
        "last_verified_utc": None,
    },
    "ICMarkets Demo": {
        "server_name": "ICMarkets Demo",
        "status": BrokerStatus.PENDING.value,
        "account_type": "DEMO",
        "automation_allowed": None,
        "python_mt5_allowed": None,
        "ea_allowed": None,
        "raw_probe_status": "PENDING",
        "raw_probe_retcode": None,
        "titan_micro_status": "PENDING",
        "repeatability_status": "PENDING",
        "preferred_filling_mode": None,
        "order_send_behavior": "UNKNOWN",
        "known_reject_reason": None,
        "risk_level": BrokerRiskLevel.MEDIUM.value,
        "priority": BrokerPriority.MEDIUM.value,
        "notes": "Not yet tested. Run raw_mt5_probe.py to verify.",
        "last_verified_utc": None,
    },
}


def get_broker_info(server_name: str) -> dict:
    """Get broker info by server name. Returns UNKNOWN entry if not found."""
    if server_name in KNOWN_BROKERS:
        return dict(KNOWN_BROKERS[server_name])
    return {
        "server_name": server_name,
        "status": BrokerStatus.UNKNOWN.value,
        "account_type": "UNKNOWN",
        "automation_allowed": None,
        "python_mt5_allowed": None,
        "ea_allowed": None,
        "raw_probe_status": "UNKNOWN",
        "raw_probe_retcode": None,
        "titan_micro_status": "UNKNOWN",
        "repeatability_status": "UNKNOWN",
        "preferred_filling_mode": None,
        "order_send_behavior": "UNKNOWN",
        "known_reject_reason": None,
        "risk_level": BrokerRiskLevel.MEDIUM.value,
        "priority": BrokerPriority.MEDIUM.value,
        "notes": "Unknown broker — run raw_mt5_probe.py to verify.",
        "last_verified_utc": None,
    }


def get_all_brokers() -> dict:
    """Return all known brokers as a dict."""
    return {k: dict(v) for k, v in KNOWN_BROKERS.items()}


def get_broker_summary() -> dict:
    """Return summary counts by status."""
    counts = {"PASS": 0, "REJECT": 0, "BLOCKED": 0, "PENDING": 0, "UNKNOWN": 0}
    for b in KNOWN_BROKERS.values():
        status = b["status"]
        counts[status] = counts.get(status, 0) + 1
    return {
        "total_brokers": len(KNOWN_BROKERS),
        "counts": counts,
        "next_broker_to_test": "MetaQuotes-Demo (repeatability pending — market closed)",
        "do_not_use": ["FundedNext Free Trial"],
    }


def get_priority_ranking() -> list:
    """Return brokers sorted by priority (HIGH first, DO_NOT_USE last)."""
    priority_order = {
        BrokerPriority.HIGH.value: 0,
        BrokerPriority.MEDIUM.value: 1,
        BrokerPriority.LOW.value: 2,
        BrokerPriority.DO_NOT_USE.value: 3,
    }
    brokers = list(KNOWN_BROKERS.values())
    brokers.sort(key=lambda b: priority_order.get(b["priority"], 99))
    return [{"server_name": b["server_name"], "priority": b["priority"],
             "status": b["status"], "risk_level": b["risk_level"]}
            for b in brokers]
