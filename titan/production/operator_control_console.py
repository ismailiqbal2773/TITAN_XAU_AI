"""
TITAN XAU AI — Operator Control Console (Sprint 9.9.3.35)
==========================================================

Safe operator-facing command center for release-candidate checks,
reports, observation summaries, and safety status.

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER enables live trading.

The console exposes a small, intentional command set:
  STATUS              — summarize current RC mode + safety state
  RC_CHECK            — run ProductionRuntimeAssembly and return RC verdict
  SAFETY_CHECK        — confirm all safety gates are closed
  BROKER_STATUS       — summarize the broker registry (verified/rejected/blocked)
  OBSERVATION_REPORT  — generate forward observation report (journal-optional)
  DAILY_SCORECARD     — generate daily observation scorecard (INSUFFICIENT_DATA if no journals)
  FULL_AUDIT          — run safe report generation only (4 reports)
  HELP                — list available commands and safe usage

Every command returns an OperatorCommandResult. Every command writes a
combined command report (JSON + MD) to data/audit/operator/.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = REPO_ROOT / "data" / "audit" / "operator"
JSON_PATH = OUTPUT_DIR / "operator_command_report.json"
MD_PATH = OUTPUT_DIR / "operator_command_report.md"


class OperatorCommand(str, Enum):
    STATUS = "status"
    RC_CHECK = "rc-check"
    SAFETY_CHECK = "safety-check"
    BROKER_STATUS = "broker-status"
    OBSERVATION_REPORT = "observation-report"
    DAILY_SCORECARD = "daily-scorecard"
    FULL_AUDIT = "full-audit"
    HELP = "help"


@dataclass
class OperatorCommandResult:
    command: str
    ok: bool
    verdict: str
    message: str
    reports_generated: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str, ensure_ascii=False)


class OperatorControlConsole:
    """Safe operator command console.

    Never imports MetaTrader5. Never sends orders. Never enables live trading.
    """

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = Path(repo_root) if repo_root else REPO_ROOT

    # ──────────────────────────────────────────────────────────────────────
    # Public command surface
    # ──────────────────────────────────────────────────────────────────────

    def run_status(self) -> OperatorCommandResult:
        """Summarize current RC mode, live-blocked, broker registry, components."""
        try:
            from titan.production.production_runtime_assembly import (
                ProductionRuntimeAssembly, ProductionRuntimeMode,
            )
            asm = ProductionRuntimeAssembly(mode=ProductionRuntimeMode.DRY_RUN)
            status = asm.build_status()

            blockers: list[str] = []
            warnings: list[str] = []
            next_steps: list[str] = []

            # Safety hard invariants
            if status.live_trading_enabled:
                blockers.append("live_trading_enabled=True (must be False)")
            if status.mt5_order_send_allowed:
                blockers.append("mt5_order_send_allowed=True (must be False)")
            if status.max_lot > 0.01:
                blockers.append(f"max_lot={status.max_lot} exceeds 0.01 cap")
            if status.max_open_positions > 1:
                blockers.append(f"max_open_positions={status.max_open_positions} exceeds 1")

            # Component status
            if status.components_missing:
                blockers.append(f"Missing components: {', '.join(status.components_missing)}")

            # Broker registry warnings
            mq = status.broker_status.get("MetaQuotes-Demo", {})
            fn = status.broker_status.get("FundedNext Free Trial", {})
            if mq.get("status") != "PASS":
                warnings.append("MetaQuotes-Demo not verified for demo micro")
            if fn.get("status") == "BLOCKED":
                warnings.append("FundedNext Free Trial remains DO_NOT_USE")

            ok = not blockers
            verdict = status.verdict.value
            message = (
                f"RC mode={status.mode.value} | live_blocked={not status.live_trading_enabled} "
                f"| dry_run={status.dry_run} | demo_only={status.demo_only} "
                f"| components={len(status.components_loaded)}/{len(status.components_loaded) + len(status.components_missing)} "
                f"| brokers={len(status.broker_status)}"
            )
            next_steps = [
                "Run rc-check to verify release candidate readiness",
                "Run safety-check to confirm all safety gates closed",
                "Run broker-status to review broker registry",
                "Do not enable live trading",
            ]
            return OperatorCommandResult(
                command=OperatorCommand.STATUS.value,
                ok=ok,
                verdict=verdict,
                message=message,
                reports_generated=[],
                blockers=blockers,
                warnings=warnings,
                next_steps=next_steps,
            )
        except Exception as e:
            return self._fail_closed(OperatorCommand.STATUS.value, f"status exception: {e}")

    def run_rc_check(self) -> OperatorCommandResult:
        """Run ProductionRuntimeAssembly and return RC_READY / RC_READY_WITH_WARNINGS / RC_BLOCKED."""
        try:
            from titan.production.production_runtime_assembly import (
                ProductionRuntimeAssembly, ProductionRuntimeMode,
                ProductionAssemblyVerdict,
            )
            asm = ProductionRuntimeAssembly(mode=ProductionRuntimeMode.DRY_RUN)
            status = asm.build_status()

            blockers: list[str] = list(status.blockers)
            warnings: list[str] = list(status.warnings)

            # Hard safety re-check
            if status.live_trading_enabled:
                blockers.append("live_trading_enabled=True")
            if status.mt5_order_send_allowed:
                blockers.append("mt5_order_send_allowed=True")
            if status.max_lot > 0.01:
                blockers.append(f"max_lot={status.max_lot} > 0.01")
            if status.max_open_positions > 1:
                blockers.append(f"max_open_positions={status.max_open_positions} > 1")

            if blockers and status.verdict == ProductionAssemblyVerdict.RC_READY:
                verdict = ProductionAssemblyVerdict.RC_BLOCKED.value
            elif blockers and status.verdict == ProductionAssemblyVerdict.RC_READY_WITH_WARNINGS:
                verdict = ProductionAssemblyVerdict.RC_BLOCKED.value
            else:
                verdict = status.verdict.value

            ok = verdict != ProductionAssemblyVerdict.RC_BLOCKED.value
            message = (
                f"RC verdict={verdict} | components_loaded={len(status.components_loaded)} "
                f"| components_missing={len(status.components_missing)} "
                f"| safety_gates={len(status.safety_gates_enabled)}"
            )
            next_steps = []
            if verdict == ProductionAssemblyVerdict.RC_BLOCKED.value:
                next_steps.append("Resolve blockers before observation")
            elif verdict == ProductionAssemblyVerdict.RC_READY_WITH_WARNINGS.value:
                next_steps.append("Review warnings — observation may proceed")
            else:
                next_steps.append("RC ready — proceed with safe observation workflow")
            next_steps.append("Run safety-check to confirm all safety gates closed")
            next_steps.append("Do not enable live trading")

            return OperatorCommandResult(
                command=OperatorCommand.RC_CHECK.value,
                ok=ok,
                verdict=verdict,
                message=message,
                reports_generated=[],
                blockers=blockers,
                warnings=warnings,
                next_steps=next_steps,
            )
        except Exception as e:
            return self._fail_closed(OperatorCommand.RC_CHECK.value, f"rc-check exception: {e}")

    def run_safety_check(self) -> OperatorCommandResult:
        """Confirm all hard safety gates are closed."""
        try:
            from titan.production.production_runtime_assembly import (
                ProductionRuntimeAssembly, ProductionRuntimeMode,
            )
            asm = ProductionRuntimeAssembly(mode=ProductionRuntimeMode.DRY_RUN)
            status = asm.build_status()

            blockers: list[str] = []
            warnings: list[str] = []
            gates_ok: list[str] = []

            # Hard invariants
            if status.live_trading_enabled:
                blockers.append("live_trading_enabled=True (must be False)")
            else:
                gates_ok.append("live_trading_enabled=False")

            if status.mt5_order_send_allowed:
                blockers.append("mt5_order_send_allowed=True (must be False)")
            else:
                gates_ok.append("mt5_order_send_allowed=False")

            if status.max_lot > 0.01:
                blockers.append(f"max_lot={status.max_lot} exceeds 0.01 cap")
            else:
                gates_ok.append(f"max_lot={status.max_lot} (<=0.01)")

            if status.max_open_positions > 1:
                blockers.append(f"max_open_positions={status.max_open_positions} exceeds 1")
            else:
                gates_ok.append(f"max_open_positions={status.max_open_positions} (<=1)")

            if not status.dry_run:
                blockers.append("dry_run=False (must be True)")
            else:
                gates_ok.append("dry_run=True")

            if not status.demo_only:
                blockers.append("demo_only=False (must be True)")
            else:
                gates_ok.append("demo_only=True")

            # FundedNext Free Trial must remain blocked
            fn = status.broker_status.get("FundedNext Free Trial", {})
            if fn.get("status") != "BLOCKED":
                blockers.append("FundedNext Free Trial not blocked")
            else:
                gates_ok.append("FundedNext Free Trial BLOCKED")

            # Raw evidence must remain ignored (we never import it from this console)
            gates_ok.append("raw runtime evidence ignored (no raw probe, no repeatability)")

            ok = len(blockers) == 0
            verdict = "SAFETY_OK" if ok else "SAFETY_BLOCKED"
            message = (
                f"gates_ok={len(gates_ok)} | blockers={len(blockers)} | "
                f"live_blocked={not status.live_trading_enabled}"
            )
            next_steps = []
            if ok:
                next_steps.append("All safety gates closed — observation may proceed")
            else:
                next_steps.append("Resolve blockers before any observation")
            next_steps.append("Do not enable live trading")
            next_steps.append("Do not run raw_mt5_probe from this console")
            next_steps.append("Do not run repeatability execution from this console")

            return OperatorCommandResult(
                command=OperatorCommand.SAFETY_CHECK.value,
                ok=ok,
                verdict=verdict,
                message=message,
                reports_generated=[],
                blockers=blockers,
                warnings=warnings,
                next_steps=next_steps,
            )
        except Exception as e:
            return self._fail_closed(OperatorCommand.SAFETY_CHECK.value, f"safety-check exception: {e}")

    def run_broker_status(self) -> OperatorCommandResult:
        """Summarize broker registry + broker observation gate eligibility."""
        try:
            from titan.production.broker_compatibility_matrix import get_all_brokers
            from titan.production.broker_observation_gate import BrokerObservationGate
            brokers = get_all_brokers()

            lines: list[str] = []
            blockers: list[str] = []
            warnings: list[str] = []

            # Required broker assertions
            mq = brokers.get("MetaQuotes-Demo", {})
            fbs = brokers.get("FBS-Demo", {})
            fn = brokers.get("FundedNext Free Trial", {})
            ex = brokers.get("Exness Demo", {})
            ic = brokers.get("ICMarkets Demo", {})

            if mq.get("status") != "PASS":
                blockers.append("MetaQuotes-Demo not PASS")
            else:
                lines.append("MetaQuotes-Demo VERIFIED_FOR_DEMO_MICRO (PASS)")

            if fbs.get("status") != "REJECT":
                warnings.append("FBS-Demo status drift (expected REJECT)")
            else:
                lines.append("FBS-Demo REJECTED/LOW priority (retcode 10006)")

            if fn.get("status") != "BLOCKED":
                blockers.append("FundedNext Free Trial not BLOCKED")
            else:
                lines.append("FundedNext Free Trial DO_NOT_USE (BLOCKED)")

            if ex.get("status") != "PENDING":
                warnings.append("Exness Demo status drift (expected PENDING)")
            else:
                lines.append("Exness Demo PENDING")

            if ic.get("status") != "PENDING":
                warnings.append("ICMarkets Demo status drift (expected PENDING)")
            else:
                lines.append("ICMarkets Demo PENDING")

            # Sprint 9.9.3.41.1: Broker observation gate evaluation
            # Uses the thin adapter that reuses existing BrokerCompatibilityMatrix
            try:
                gate = BrokerObservationGate()
                gate_result = gate.evaluate(broker_name="MetaQuotes-Demo")
                if gate_result.verdict.value == "ALLOWED":
                    lines.append(f"OBSERVATION ELIGIBLE: MetaQuotes-Demo allowed for 7-day observation")
                else:
                    blockers.append(f"Observation gate: {gate_result.reason}")
                # Show observation eligibility summary
                lines.append(f"Allowed for 7-day observation: {gate.list_allowed_brokers()}")
                lines.append(f"Blocked brokers: {list(gate.list_blocked_brokers().keys())}")
                lines.append(f"Pending brokers: {list(gate.list_pending_brokers().keys())}")
            except Exception as gate_err:
                warnings.append(f"Broker observation gate evaluation failed: {gate_err}")

            ok = len(blockers) == 0
            verdict = "BROKER_REGISTRY_OK" if ok else "BROKER_REGISTRY_DRIFT"
            message = (
                f"brokers={len(brokers)} | verified={sum(1 for b in brokers.values() if b.get('status') == 'PASS')} "
                f"| rejected={sum(1 for b in brokers.values() if b.get('status') == 'REJECT')} "
                f"| blocked={sum(1 for b in brokers.values() if b.get('status') == 'BLOCKED')} "
                f"| pending={sum(1 for b in brokers.values() if b.get('status') == 'PENDING')}"
            )
            next_steps = [
                "MetaQuotes-Demo is the only verified broker for 7-day observation",
                "Do not use FundedNext Free Trial (DO_NOT_USE)",
                "Do not use FBS-Demo (REJECTED, requires compatibility retest)",
                "Exness/ICMarkets are PENDING - do not use until verified",
                "Do not enable live trading from this console",
                "Do not run DEMO_MICRO_EXECUTE from this console",
            ]
            return OperatorCommandResult(
                command=OperatorCommand.BROKER_STATUS.value,
                ok=ok,
                verdict=verdict,
                message=message + " | " + " | ".join(lines),
                reports_generated=[],
                blockers=blockers,
                warnings=warnings,
                next_steps=next_steps,
            )
        except Exception as e:
            return self._fail_closed(OperatorCommand.BROKER_STATUS.value, f"broker-status exception: {e}")

    def run_observation_report(self, since_hours: Optional[int] = None) -> OperatorCommandResult:
        """Generate forward observation report. Does NOT require journals."""
        try:
            import scripts.audit.forward_observation_report as rep
            result = rep.write_report(since_hours=since_hours)
            json_path = result["json_path"]
            md_path = result["md_path"]

            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            verdict = data.get("verdict", "OBSERVATION_UNKNOWN")
            missing = data.get("missing_journals", [])
            counts = data.get("counts", {})
            total_events = counts.get("total_events", 0)

            blockers: list[str] = []
            warnings: list[str] = []
            if missing:
                warnings.append(f"Missing journals: {', '.join(Path(m).name for m in missing)}")
            if total_events == 0:
                warnings.append("No events observed yet — observation not started")

            ok = True
            message = (
                f"verdict={verdict} | total_events={total_events} "
                f"| missing_journals={len(missing)}"
            )
            next_steps = [
                "Run demo micro in DRY_ARM_CHECK_ONLY to produce journal events",
                "Do not enable live trading",
                "Do not commit raw journal files with private account data",
            ]
            return OperatorCommandResult(
                command=OperatorCommand.OBSERVATION_REPORT.value,
                ok=ok,
                verdict=verdict,
                message=message,
                reports_generated=[json_path, md_path],
                blockers=blockers,
                warnings=warnings,
                next_steps=next_steps,
            )
        except Exception as e:
            return self._fail_closed(
                OperatorCommand.OBSERVATION_REPORT.value,
                f"observation-report exception: {e}",
            )

    def run_daily_scorecard(self, since_hours: int = 24) -> OperatorCommandResult:
        """Generate daily observation scorecard. Returns INSUFFICIENT_DATA if no journals."""
        try:
            import scripts.audit.daily_demo_observation_runner as runner
            report = runner.run_scorecard(since_hours=since_hours)
            json_path = str(runner.JSON_PATH)
            md_path = str(runner.MD_PATH)

            card = report.get("scorecard", {})
            grade = card.get("grade", "INSUFFICIENT_DATA")
            missing = report.get("missing_journals", [])

            blockers: list[str] = []
            warnings: list[str] = []
            if missing:
                warnings.append(f"Missing journals: {', '.join(Path(m).name for m in missing)}")
            if grade == "INSUFFICIENT_DATA":
                warnings.append("No observation data yet — scorecard INSUFFICIENT_DATA")
            if card.get("blockers"):
                blockers.extend(card["blockers"])
            if card.get("warnings"):
                warnings.extend(card["warnings"])

            ok = grade != "FAIL"
            message = (
                f"grade={grade} | total_events={card.get('total_events', 0)} "
                f"| safety_score={card.get('safety_score', 0)} "
                f"| quality_score={card.get('observation_quality_score', 0)}"
            )
            next_steps = report.get("operator_next_steps", [
                "Run demo micro in DRY_ARM_CHECK_ONLY to produce events",
                "Do not enable live trading",
            ])
            return OperatorCommandResult(
                command=OperatorCommand.DAILY_SCORECARD.value,
                ok=ok,
                verdict=grade,
                message=message,
                reports_generated=[json_path, md_path],
                blockers=blockers,
                warnings=warnings,
                next_steps=next_steps,
            )
        except Exception as e:
            return self._fail_closed(
                OperatorCommand.DAILY_SCORECARD.value,
                f"daily-scorecard exception: {e}",
            )

    def run_full_audit(self) -> OperatorCommandResult:
        """Run safe report generation only.

        Generates:
          - production assembly report
          - forward observation report
          - daily observation scorecard
          - redacted registry presence check
        Never executes trades. Never imports MT5.
        """
        try:
            reports: list[str] = []
            blockers: list[str] = []
            warnings: list[str] = []

            # 1) Production assembly report
            try:
                import scripts.audit.production_assembly_report as rep
                r = rep.write_report()
                reports.append(r["json_path"])
                reports.append(r["md_path"])
            except Exception as e:
                blockers.append(f"production_assembly_report failed: {e}")

            # 2) Forward observation report
            try:
                import scripts.audit.forward_observation_report as rep2
                r2 = rep2.write_report()
                reports.append(r2["json_path"])
                reports.append(r2["md_path"])
            except Exception as e:
                blockers.append(f"forward_observation_report failed: {e}")

            # 3) Daily observation scorecard
            try:
                import scripts.audit.daily_demo_observation_runner as runner
                report = runner.run_scorecard(since_hours=24)
                reports.append(str(runner.JSON_PATH))
                reports.append(str(runner.MD_PATH))
                grade = report.get("scorecard", {}).get("grade", "")
                if grade == "INSUFFICIENT_DATA":
                    warnings.append("daily scorecard INSUFFICIENT_DATA (no journals yet)")
            except Exception as e:
                blockers.append(f"daily_demo_observation_runner failed: {e}")

            # 4) Redacted registry presence check
            registry_path = self.repo_root / "docs" / "audit" / "demo_micro_repeatability_metaquotes_redacted.json"
            registry_md_path = self.repo_root / "docs" / "audit" / "demo_micro_repeatability_metaquotes_redacted.md"
            if registry_path.exists():
                reports.append(str(registry_path))
            else:
                warnings.append("redacted repeatability registry JSON missing")
            if registry_md_path.exists():
                reports.append(str(registry_md_path))
            else:
                warnings.append("redacted repeatability registry MD missing")

            ok = len(blockers) == 0
            verdict = "FULL_AUDIT_OK" if ok else "FULL_AUDIT_BLOCKED"
            message = (
                f"reports_generated={len(reports)} | blockers={len(blockers)} "
                f"| warnings={len(warnings)}"
            )
            next_steps = [
                "Review generated reports under data/audit/",
                "Do not enable live trading",
                "Do not run DEMO_MICRO_EXECUTE from this console",
                "Do not run raw_mt5_probe from this console",
            ]
            return OperatorCommandResult(
                command=OperatorCommand.FULL_AUDIT.value,
                ok=ok,
                verdict=verdict,
                message=message,
                reports_generated=reports,
                blockers=blockers,
                warnings=warnings,
                next_steps=next_steps,
            )
        except Exception as e:
            return self._fail_closed(OperatorCommand.FULL_AUDIT.value, f"full-audit exception: {e}")

    def run_help(self) -> OperatorCommandResult:
        """List available commands and safe usage."""
        lines = [
            "TITAN XAU AI — Operator Control Console",
            "",
            "Available commands:",
            "  status              — summarize current RC mode + safety state",
            "  rc-check            — run ProductionRuntimeAssembly + return RC verdict",
            "  safety-check        — confirm all safety gates closed",
            "  broker-status       — summarize broker registry",
            "  observation-report  — generate forward observation report",
            "  daily-scorecard     — generate daily observation scorecard",
            "  full-audit          — run safe report generation only",
            "  help                — show this help",
            "",
            "Safe workflow before observation:",
            "  1. status            — verify RC mode and live-blocked",
            "  2. safety-check      — confirm safety gates closed",
            "  3. broker-status     — confirm MetaQuotes verified, FundedNext blocked",
            "  4. rc-check          — confirm RC_READY or RC_READY_WITH_WARNINGS",
            "  5. observation-report — generate observation report",
            "  6. daily-scorecard   — generate daily scorecard",
            "  7. full-audit        — generate all reports",
            "",
            "What NOT to run:",
            "  - Do not enable live trading",
            "  - Do not run DEMO_MICRO_EXECUTE from this console",
            "  - Do not run raw_mt5_probe from this console",
            "  - Do not run repeatability execution from this console",
            "  - Do not commit raw journal files with private account data",
            "  - Do not import the MT5 Python package from this console",
            "",
            "Live trading remains BLOCKED.",
            "Market execution is NOT available from this console.",
        ]
        message = "\n".join(lines)
        next_steps = [
            "Run status to begin the safe workflow",
            "Run safety-check to confirm gates closed",
            "Do not enable live trading",
        ]
        return OperatorCommandResult(
            command=OperatorCommand.HELP.value,
            ok=True,
            verdict="HELP_OK",
            message=message,
            reports_generated=[],
            blockers=[],
            warnings=[],
            next_steps=next_steps,
        )

    def execute(self, command) -> OperatorCommandResult:
        """Dispatch a command by enum or string. Returns OperatorCommandResult."""
        try:
            if isinstance(command, OperatorCommand):
                cmd = command
            else:
                cmd = OperatorCommand(str(command).strip().lower())
        except Exception:
            return self._fail_closed(str(command), "unknown command")

        if cmd == OperatorCommand.STATUS:
            result = self.run_status()
        elif cmd == OperatorCommand.RC_CHECK:
            result = self.run_rc_check()
        elif cmd == OperatorCommand.SAFETY_CHECK:
            result = self.run_safety_check()
        elif cmd == OperatorCommand.BROKER_STATUS:
            result = self.run_broker_status()
        elif cmd == OperatorCommand.OBSERVATION_REPORT:
            result = self.run_observation_report()
        elif cmd == OperatorCommand.DAILY_SCORECARD:
            result = self.run_daily_scorecard()
        elif cmd == OperatorCommand.FULL_AUDIT:
            result = self.run_full_audit()
        elif cmd == OperatorCommand.HELP:
            result = self.run_help()
        else:
            return self._fail_closed(cmd.value, "unknown command")

        # Persist combined command report
        try:
            self._write_command_report(result)
        except Exception:
            pass
        return result

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _fail_closed(self, command: str, reason: str) -> OperatorCommandResult:
        return OperatorCommandResult(
            command=str(command),
            ok=False,
            verdict="CONSOLE_FAILED",
            message=reason,
            reports_generated=[],
            blockers=[reason],
            warnings=[],
            next_steps=["Investigate console error before retrying"],
        )

    def _write_command_report(self, result: OperatorCommandResult) -> dict:
        """Write a combined operator command report (JSON + MD)."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = result.timestamp_utc or datetime.now(timezone.utc).isoformat()

        payload = {
            "timestamp_utc": ts,
            "last_command": result.command,
            "result": result.to_dict(),
            "safety": {
                "live_trading_enabled": False,
                "mt5_order_send_allowed": False,
                "metatrader5_imported": False,
                "market_execution_run": False,
                "demo_micro_execute_run": False,
            },
            "general_warnings": [
                "Operator control console never imports MetaTrader5.",
                "Operator control console never sends orders.",
                "Operator control console never enables live trading.",
                "Live trading remains BLOCKED.",
                "Market execution is NOT available from this console.",
            ],
        }

        with open(JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str, ensure_ascii=False)

        with open(MD_PATH, "w", encoding="utf-8") as f:
            f.write("# TITAN XAU AI — Operator Command Report\n\n")
            f.write(f"**Generated:** {ts}\n\n")
            f.write(f"**Last Command:** `{result.command}`\n\n")
            f.write(f"**OK:** {result.ok}\n\n")
            f.write(f"**Verdict:** {result.verdict}\n\n")
            f.write(f"**Message:**\n\n```\n{result.message}\n```\n\n")
            f.write("## Safety\n\n")
            f.write("| Field | Value |\n|---|---|\n")
            for k, v in payload["safety"].items():
                f.write(f"| {k} | {v} |\n")
            f.write("\n## Reports Generated\n\n")
            if result.reports_generated:
                for p in result.reports_generated:
                    f.write(f"- `{p}`\n")
            else:
                f.write("- (none)\n")
            if result.blockers:
                f.write("\n## Blockers\n\n")
                for b in result.blockers:
                    f.write(f"- **{b}**\n")
            if result.warnings:
                f.write("\n## Warnings\n\n")
                for w in result.warnings:
                    f.write(f"- {w}\n")
            f.write("\n## Next Steps\n\n")
            for s in result.next_steps:
                f.write(f"- {s}\n")
            f.write("\n## General Warnings\n\n")
            for w in payload["general_warnings"]:
                f.write(f"- **{w}**\n")

        return {"json_path": str(JSON_PATH), "md_path": str(MD_PATH)}
