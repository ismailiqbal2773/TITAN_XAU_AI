"""
TITAN XAU AI - First-Run Wizard (Sprint 9.9.3.40)
==================================================

Non-technical operator first-run wizard. Verifies that the RC environment
is safe and ready before the operator runs the operator console or starts
long observation.

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER runs DEMO_MICRO_EXECUTE.
NEVER runs raw_mt5_probe.
NEVER asks for account password or API key.

The wizard produces a PASS / WARN / FAIL / SKIP summary for each check.
A single FAIL on any critical safety check blocks the RC environment.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


REPO_ROOT = Path(__file__).resolve().parents[2]


class FirstRunCheckStatus(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class FirstRunWizardResult:
    check_name: str
    status: FirstRunCheckStatus
    message: str
    details: dict = field(default_factory=dict)
    next_step: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class FirstRunWizardSummary:
    overall_status: FirstRunCheckStatus = FirstRunCheckStatus.PASS
    passed: int = 0
    warnings: int = 0
    failed: int = 0
    skipped: int = 0
    results: list[FirstRunWizardResult] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["overall_status"] = self.overall_status.value
        d["results"] = [r.to_dict() for r in self.results]
        return d


class FirstRunWizard:
    """First-run wizard for non-technical operators.

    Verifies the RC environment is safe without executing any trades,
    importing MT5, or asking for credentials.
    """

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = Path(repo_root) if repo_root else REPO_ROOT

    # ──────────────────────────────────────────────────────────────────────
    # Individual checks
    # ──────────────────────────────────────────────────────────────────────

    def check_python_version(self) -> FirstRunWizardResult:
        """Verify Python version is 3.10+."""
        try:
            major, minor = sys.version_info[:2]
            if major < 3 or (major == 3 and minor < 10):
                return FirstRunWizardResult(
                    check_name="python_version",
                    status=FirstRunCheckStatus.FAIL,
                    message=f"Python {major}.{minor} is too old (need 3.10+)",
                    details={"major": major, "minor": minor},
                    next_step="Install Python 3.10 or newer from https://python.org",
                )
            return FirstRunWizardResult(
                check_name="python_version",
                status=FirstRunCheckStatus.PASS,
                message=f"Python {major}.{minor} is supported",
                details={"major": major, "minor": minor},
                next_step="Continue to next check",
            )
        except Exception as e:
            return FirstRunWizardResult(
                check_name="python_version",
                status=FirstRunCheckStatus.FAIL,
                message=f"Python version check failed: {e}",
                next_step="Verify Python installation",
            )

    def check_virtualenv(self) -> FirstRunWizardResult:
        """Check if a virtual environment is active or available."""
        try:
            in_venv = (
                hasattr(sys, "real_prefix")
                or (hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix)
            )
            venv_dir = self.repo_root / "venv"
            venv_dir_alt = self.repo_root / ".venv"
            venv_available = in_venv or venv_dir.exists() or venv_dir_alt.exists()
            if in_venv:
                return FirstRunWizardResult(
                    check_name="virtualenv",
                    status=FirstRunCheckStatus.PASS,
                    message="Virtual environment is active",
                    details={"prefix": sys.prefix, "in_venv": True},
                    next_step="Continue to next check",
                )
            if venv_available:
                return FirstRunWizardResult(
                    check_name="virtualenv",
                    status=FirstRunCheckStatus.WARN,
                    message="Virtual environment exists but is not active",
                    details={"venv_dir": str(venv_dir), "in_venv": False},
                    next_step="Activate venv: venv\\Scripts\\activate.bat",
                )
            return FirstRunWizardResult(
                check_name="virtualenv",
                status=FirstRunCheckStatus.WARN,
                message="No virtual environment found (optional but recommended)",
                details={"in_venv": False},
                next_step="Create venv: python -m venv venv",
            )
        except Exception as e:
            return FirstRunWizardResult(
                check_name="virtualenv",
                status=FirstRunCheckStatus.WARN,
                message=f"Virtualenv check failed: {e}",
                next_step="Continue (virtualenv is optional)",
            )

    def check_required_files(self) -> FirstRunWizardResult:
        """Verify required RC files exist."""
        required = [
            "titan/production/operator_control_console.py",
            "scripts/operator/titan_operator.py",
            "scripts/operator/titan_first_run.py",
            "run_titan_operator.bat",
            "run_titan_first_run.bat",
            "config/runtime.yaml",
        ]
        missing = []
        for rel in required:
            if not (self.repo_root / rel).exists():
                missing.append(rel)
        if missing:
            return FirstRunWizardResult(
                check_name="required_files",
                status=FirstRunCheckStatus.FAIL,
                message=f"Missing required files: {', '.join(missing)}",
                details={"missing": missing, "required": required},
                next_step="Restore missing files from git",
            )
        return FirstRunWizardResult(
            check_name="required_files",
            status=FirstRunCheckStatus.PASS,
            message=f"All {len(required)} required files present",
            details={"required": required, "missing": []},
            next_step="Continue to next check",
        )

    def check_operator_console(self) -> FirstRunWizardResult:
        """Verify operator console module loads and exposes no live trading."""
        try:
            console_path = self.repo_root / "titan" / "production" / "operator_control_console.py"
            if not console_path.exists():
                return FirstRunWizardResult(
                    check_name="operator_console",
                    status=FirstRunCheckStatus.FAIL,
                    message="Operator console module missing",
                    next_step="Restore operator_control_console.py",
                )
            src = console_path.read_text(encoding="utf-8")
            # Strip strings/comments
            code = re.sub(r'"""[\s\S]*?"""', '""', src)
            code = re.sub(r"'''[\s\S]*?'''", "''", code)
            code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
            code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
            # Check for forbidden exposure
            if "DEMO_MICRO_EXECUTE(" in code:
                return FirstRunWizardResult(
                    check_name="operator_console",
                    status=FirstRunCheckStatus.FAIL,
                    message="Operator console exposes DEMO_MICRO_EXECUTE",
                    next_step="Remove DEMO_MICRO_EXECUTE from operator console",
                )
            if re.search(r"\bmt5\.order_send\s*\(", code):
                return FirstRunWizardResult(
                    check_name="operator_console",
                    status=FirstRunCheckStatus.FAIL,
                    message="Operator console calls mt5.order_send",
                    next_step="Remove order_send from operator console",
                )
            return FirstRunWizardResult(
                check_name="operator_console",
                status=FirstRunCheckStatus.PASS,
                message="Operator console safe (no live trading, no DEMO_MICRO_EXECUTE, no order_send)",
                details={"path": str(console_path)},
                next_step="Continue to next check",
            )
        except Exception as e:
            return FirstRunWizardResult(
                check_name="operator_console",
                status=FirstRunCheckStatus.FAIL,
                message=f"Operator console check failed: {e}",
                next_step="Inspect operator_control_console.py",
            )

    def check_production_runtime_assembly(self) -> FirstRunWizardResult:
        """Verify ProductionRuntimeAssembly returns RC_READY or RC_READY_WITH_WARNINGS."""
        try:
            from titan.production.production_runtime_assembly import (
                ProductionRuntimeAssembly, ProductionRuntimeMode,
                ProductionAssemblyVerdict,
            )
            asm = ProductionRuntimeAssembly(mode=ProductionRuntimeMode.DRY_RUN)
            status = asm.build_status()
            if status.verdict == ProductionAssemblyVerdict.RC_BLOCKED:
                return FirstRunWizardResult(
                    check_name="production_runtime_assembly",
                    status=FirstRunCheckStatus.FAIL,
                    message=f"ProductionRuntimeAssembly verdict=RC_BLOCKED",
                    details={"verdict": status.verdict.value, "blockers": status.blockers},
                    next_step="Resolve blockers in production_runtime_assembly",
                )
            return FirstRunWizardResult(
                check_name="production_runtime_assembly",
                status=FirstRunCheckStatus.PASS,
                message=f"ProductionRuntimeAssembly verdict={status.verdict.value}",
                details={
                    "verdict": status.verdict.value,
                    "live_trading_enabled": status.live_trading_enabled,
                    "mt5_order_send_allowed": status.mt5_order_send_allowed,
                    "max_lot": status.max_lot,
                },
                next_step="Continue to next check",
            )
        except Exception as e:
            return FirstRunWizardResult(
                check_name="production_runtime_assembly",
                status=FirstRunCheckStatus.FAIL,
                message=f"ProductionRuntimeAssembly check failed: {e}",
                next_step="Inspect production_runtime_assembly.py",
            )

    def check_master_integration_audit(self) -> FirstRunWizardResult:
        """Verify MasterIntegrationAudit is not INTEGRATION_BLOCKED."""
        try:
            # Import the audit module and run a fresh report
            import scripts.audit.master_integration_audit as audit_mod
            # Use a temp dir to avoid writing to the real audit location
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                old_dir, old_json, old_md = audit_mod.OUTPUT_DIR, audit_mod.JSON_PATH, audit_mod.MD_PATH
                audit_mod.OUTPUT_DIR = Path(td)
                audit_mod.JSON_PATH = Path(td) / "audit.json"
                audit_mod.MD_PATH = Path(td) / "audit.md"
                try:
                    result = audit_mod.write_report()
                finally:
                    audit_mod.OUTPUT_DIR, audit_mod.JSON_PATH, audit_mod.MD_PATH = old_dir, old_json, old_md
            verdict = result["verdict"]
            if verdict == "INTEGRATION_BLOCKED":
                return FirstRunWizardResult(
                    check_name="master_integration_audit",
                    status=FirstRunCheckStatus.FAIL,
                    message=f"MasterIntegrationAudit verdict=INTEGRATION_BLOCKED",
                    details={"verdict": verdict},
                    next_step="Resolve integration blockers",
                )
            return FirstRunWizardResult(
                check_name="master_integration_audit",
                status=FirstRunCheckStatus.PASS,
                message=f"MasterIntegrationAudit verdict={verdict}",
                details={"verdict": verdict},
                next_step="Continue to next check",
            )
        except Exception as e:
            return FirstRunWizardResult(
                check_name="master_integration_audit",
                status=FirstRunCheckStatus.WARN,
                message=f"MasterIntegrationAudit check failed: {e}",
                next_step="Run master_integration_audit.py manually",
            )

    def check_release_docs(self) -> FirstRunWizardResult:
        """Verify required release docs exist (WARN if missing, not FAIL)."""
        required = [
            "docs/release/production_release_candidate_plan.md",
            "docs/release/windows_rc_package_guide.md",
            "docs/audit/master_integration_gap_report.md",
            "docs/operator/operator_control_console.md",
        ]
        missing = [r for r in required if not (self.repo_root / r).exists()]
        if missing:
            return FirstRunWizardResult(
                check_name="release_docs",
                status=FirstRunCheckStatus.WARN,
                message=f"Missing release docs: {', '.join(missing)}",
                details={"missing": missing, "required": required},
                next_step="Restore missing docs (optional but recommended)",
            )
        return FirstRunWizardResult(
            check_name="release_docs",
            status=FirstRunCheckStatus.PASS,
            message=f"All {len(required)} release docs present",
            details={"required": required, "missing": []},
            next_step="Continue to next check",
        )

    def check_git_clean_hint(self) -> FirstRunWizardResult:
        """Hint about git working tree state (WARN if dirty, not FAIL)."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                dirty = bool(result.stdout.strip())
                if dirty:
                    return FirstRunWizardResult(
                        check_name="git_clean_hint",
                        status=FirstRunCheckStatus.WARN,
                        message="Git working tree has uncommitted changes",
                        details={"dirty": True},
                        next_step="Commit or stash changes before packaging",
                    )
                return FirstRunWizardResult(
                    check_name="git_clean_hint",
                    status=FirstRunCheckStatus.PASS,
                    message="Git working tree is clean",
                    details={"dirty": False},
                    next_step="Continue to next check",
                )
            return FirstRunWizardResult(
                check_name="git_clean_hint",
                status=FirstRunCheckStatus.SKIP,
                message="Git not available or not a git repo",
                next_step="Continue (git check is optional)",
            )
        except Exception:
            return FirstRunWizardResult(
                check_name="git_clean_hint",
                status=FirstRunCheckStatus.SKIP,
                message="Git check skipped",
                next_step="Continue (git check is optional)",
            )

    def check_raw_evidence_ignored(self) -> FirstRunWizardResult:
        """Verify .gitignore excludes raw evidence files."""
        try:
            gitignore_path = self.repo_root / ".gitignore"
            if not gitignore_path.exists():
                return FirstRunWizardResult(
                    check_name="raw_evidence_ignored",
                    status=FirstRunCheckStatus.WARN,
                    message=".gitignore missing",
                    next_step="Create .gitignore with raw evidence exclusions",
                )
            content = gitignore_path.read_text(encoding="utf-8")
            required_exclusions = [
                "data/runtime/",
                "data/audit/demo_micro/demo_micro_journal.jsonl",
                "data/audit/demo_micro/demo_micro_repeatability_journal.jsonl",
                "data/audit/demo_micro/raw_mt5_working_profile.json",
                "data/audit/demo_micro/broker_execution_profile.json",
                ".env",
            ]
            missing = [r for r in required_exclusions if r not in content]
            if missing:
                return FirstRunWizardResult(
                    check_name="raw_evidence_ignored",
                    status=FirstRunCheckStatus.FAIL,
                    message=f".gitignore missing exclusions: {', '.join(missing)}",
                    details={"missing": missing},
                    next_step="Add missing exclusions to .gitignore",
                )
            return FirstRunWizardResult(
                check_name="raw_evidence_ignored",
                status=FirstRunCheckStatus.PASS,
                message=".gitignore excludes all raw evidence files",
                details={"checked": required_exclusions, "missing": []},
                next_step="Continue to next check",
            )
        except Exception as e:
            return FirstRunWizardResult(
                check_name="raw_evidence_ignored",
                status=FirstRunCheckStatus.FAIL,
                message=f"Raw evidence check failed: {e}",
                next_step="Inspect .gitignore",
            )

    def check_live_trading_blocked(self) -> FirstRunWizardResult:
        """Verify live trading is blocked in config/runtime.yaml."""
        try:
            config_path = self.repo_root / "config" / "runtime.yaml"
            if not config_path.exists():
                return FirstRunWizardResult(
                    check_name="live_trading_blocked",
                    status=FirstRunCheckStatus.FAIL,
                    message="config/runtime.yaml missing",
                    next_step="Restore config/runtime.yaml",
                )
            content = config_path.read_text(encoding="utf-8")
            if "live_trading: false" not in content:
                return FirstRunWizardResult(
                    check_name="live_trading_blocked",
                    status=FirstRunCheckStatus.FAIL,
                    message="live_trading is not set to false in runtime.yaml",
                    next_step="Set live_trading: false in config/runtime.yaml",
                )
            return FirstRunWizardResult(
                check_name="live_trading_blocked",
                status=FirstRunCheckStatus.PASS,
                message="live_trading: false in runtime.yaml",
                details={"config_path": str(config_path)},
                next_step="Continue to next check",
            )
        except Exception as e:
            return FirstRunWizardResult(
                check_name="live_trading_blocked",
                status=FirstRunCheckStatus.FAIL,
                message=f"Live trading check failed: {e}",
                next_step="Inspect config/runtime.yaml",
            )

    def check_market_execution_absent(self) -> FirstRunWizardResult:
        """Verify no market execution option in operator batch / first-run batch."""
        try:
            batch_files = [
                self.repo_root / "run_titan_operator.bat",
                self.repo_root / "run_titan_first_run.bat",
            ]
            for batch_path in batch_files:
                if not batch_path.exists():
                    continue
                content = batch_path.read_text(encoding="utf-8")
                # Check PYTHON lines (actual command execution) for forbidden scripts
                for line in content.splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    upper = stripped.upper()
                    if not upper.startswith("PYTHON"):
                        continue
                    lower = stripped.lower()
                    if "demo_micro_execute" in lower or "demo_micro_full_cycle" in lower:
                        return FirstRunWizardResult(
                            check_name="market_execution_absent",
                            status=FirstRunCheckStatus.FAIL,
                            message=f"Market execution found in {batch_path.name}: {stripped}",
                            next_step=f"Remove DEMO_MICRO_EXECUTE from {batch_path.name}",
                        )
                    if "raw_mt5_probe" in lower:
                        return FirstRunWizardResult(
                            check_name="market_execution_absent",
                            status=FirstRunCheckStatus.FAIL,
                            message=f"Raw probe found in {batch_path.name}: {stripped}",
                            next_step=f"Remove raw_mt5_probe from {batch_path.name}",
                        )
                    if "demo_micro_repeatability" in lower:
                        return FirstRunWizardResult(
                            check_name="market_execution_absent",
                            status=FirstRunCheckStatus.FAIL,
                            message=f"Repeatability execution found in {batch_path.name}: {stripped}",
                            next_step=f"Remove demo_micro_repeatability from {batch_path.name}",
                        )
            return FirstRunWizardResult(
                check_name="market_execution_absent",
                status=FirstRunCheckStatus.PASS,
                message="No market execution in operator/first-run batch files",
                details={"checked": [p.name for p in batch_files if p.exists()]},
                next_step="Continue to next check",
            )
        except Exception as e:
            return FirstRunWizardResult(
                check_name="market_execution_absent",
                status=FirstRunCheckStatus.FAIL,
                message=f"Market execution check failed: {e}",
                next_step="Inspect batch files",
            )

    def check_no_order_send_exposed(self) -> FirstRunWizardResult:
        """Verify safe modules do not call order_send."""
        try:
            safe_modules = [
                "titan/production/operator_control_console.py",
                "titan/production/first_run_wizard.py",
                "titan/production/production_runtime_assembly.py",
                "titan/production/model_lifecycle_governance.py",
                "titan/production/alpha_factory_governance.py",
                "titan/production/auto_calibration_governance.py",
                "titan/production/model_registry.py",
                "titan/production/offline_retraining_pipeline.py",
                "titan/production/retraining_trigger_monitor.py",
                "titan/production/forward_observation.py",
                "titan/production/observation_scorecard.py",
                "scripts/operator/titan_operator.py",
                "scripts/operator/titan_first_run.py",
            ]
            violations = []
            for rel in safe_modules:
                path = self.repo_root / rel
                if not path.exists():
                    continue
                src = path.read_text(encoding="utf-8")
                code = re.sub(r'"""[\s\S]*?"""', '""', src)
                code = re.sub(r"'''[\s\S]*?'''", "''", code)
                code = re.sub(r'"(?:[^"\\]|\\.)*"', '""', code)
                code = re.sub(r"'(?:[^'\\]|\\.)*'", "''", code)
                if re.search(r"\bmt5\.order_send\s*\(", code):
                    violations.append(rel)
                if re.search(r"\b(adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\(", code):
                    violations.append(rel)
            if violations:
                return FirstRunWizardResult(
                    check_name="no_order_send_exposed",
                    status=FirstRunCheckStatus.FAIL,
                    message=f"order_send found in safe modules: {', '.join(violations)}",
                    details={"violations": violations},
                    next_step="Remove order_send from safe modules",
                )
            return FirstRunWizardResult(
                check_name="no_order_send_exposed",
                status=FirstRunCheckStatus.PASS,
                message="No order_send calls in safe modules",
                details={"checked": safe_modules, "violations": []},
                next_step="Continue to next check",
            )
        except Exception as e:
            return FirstRunWizardResult(
                check_name="no_order_send_exposed",
                status=FirstRunCheckStatus.FAIL,
                message=f"order_send check failed: {e}",
                next_step="Inspect safe modules",
            )

    # ──────────────────────────────────────────────────────────────────────
    # Aggregate
    # ──────────────────────────────────────────────────────────────────────

    def run_all(self) -> FirstRunWizardSummary:
        """Run all checks and return a summary."""
        summary = FirstRunWizardSummary()
        checks = [
            self.check_python_version(),
            self.check_virtualenv(),
            self.check_required_files(),
            self.check_operator_console(),
            self.check_production_runtime_assembly(),
            self.check_master_integration_audit(),
            self.check_release_docs(),
            self.check_git_clean_hint(),
            self.check_raw_evidence_ignored(),
            self.check_live_trading_blocked(),
            self.check_market_execution_absent(),
            self.check_no_order_send_exposed(),
        ]
        summary.results = checks
        for r in checks:
            if r.status == FirstRunCheckStatus.PASS:
                summary.passed += 1
            elif r.status == FirstRunCheckStatus.WARN:
                summary.warnings += 1
                summary.next_steps.append(f"{r.check_name}: {r.next_step}")
            elif r.status == FirstRunCheckStatus.FAIL:
                summary.failed += 1
                summary.blockers.append(f"{r.check_name}: {r.message}")
                summary.next_steps.append(f"BLOCKER - {r.check_name}: {r.next_step}")
            elif r.status == FirstRunCheckStatus.SKIP:
                summary.skipped += 1

        # Overall status: FAIL if any FAIL, WARN if any WARN, else PASS
        if summary.failed > 0:
            summary.overall_status = FirstRunCheckStatus.FAIL
        elif summary.warnings > 0:
            summary.overall_status = FirstRunCheckStatus.WARN
        else:
            summary.overall_status = FirstRunCheckStatus.PASS

        # Always add final next steps
        if summary.overall_status == FirstRunCheckStatus.PASS:
            summary.next_steps.append("RC environment is ready. Run operator console: run_titan_operator.bat")
        elif summary.overall_status == FirstRunCheckStatus.WARN:
            summary.next_steps.append("RC environment has warnings. Review warnings above before proceeding.")
        else:
            summary.next_steps.append("RC environment is BLOCKED. Resolve blockers before proceeding.")

        return summary
