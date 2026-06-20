"""
TITAN XAU AI — Prop Firm Compliance Module (Module 22)
Universal compliance engine for 5+ prop firms.
"""
from titan.compliance.profiles import (
    FirmProfile, FirmId, DailyLossMode, DrawdownMode, NewsMode, WeekendMode,
    PropFirmProfiles, PROFIT_TARGET_PCT,
)
from titan.compliance.rule_engine import (
    ComplianceRule, RuleResult, RuleAction, ComplianceRuleEngine,
    RuleContext, ConsistencyResult,
)
from titan.compliance.engine import ComplianceEngine, ComplianceState, ComplianceReport
from titan.compliance.audit import ComplianceAuditLog, AuditEvent

__all__ = [
    "FirmProfile", "FirmId", "DailyLossMode", "DrawdownMode", "NewsMode", "WeekendMode",
    "PropFirmProfiles", "PROFIT_TARGET_PCT",
    "ComplianceRule", "RuleResult", "RuleAction", "ComplianceRuleEngine",
    "RuleContext", "ConsistencyResult",
    "ComplianceEngine", "ComplianceState", "ComplianceReport",
    "ComplianceAuditLog", "AuditEvent",
]
