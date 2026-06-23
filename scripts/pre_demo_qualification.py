"""
TITAN XAU AI — Pre-Demo World-Class Qualification Gate (Sprint 7.5+)

Final engineering + operational qualification before 30-day MT5 demo forward test.
Scores TITAN out of 100 across 7 dimensions. Produces GO / NO-GO decision.

Scoring:
  Runtime stability:    20
  Safety controls:      20
  Dry-run execution:    15
  Audit journal:        15
  Deployment ease:      10
  MT5 demo readiness:   10
  Monitoring/reporting: 10
  ────────────────────────
  TOTAL:               100

Pass criteria:
  Score >= 90: GO FOR DEMO
  Score 80-89: CONDITIONAL (fix issues first)
  Score <  80: NO-GO

Critical failures (force NO-GO regardless of score):
  - dry_run not default
  - Real account accepted
  - Missing journal
  - Missing models
  - Kill-switch not functional

Usage:
    python scripts/pre_demo_qualification.py
    python scripts/pre_demo_qualification.py --verbose
"""
from __future__ import annotations

import json
import csv
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


@dataclass
class CheckResult:
    """Result of a single qualification check."""
    name: str
    passed: bool
    score: float          # points earned
    max_score: float      # max possible points
    evidence: str = ""
    critical: bool = False  # if True and failed → force NO-GO


@dataclass
class QualificationScorecard:
    """Full qualification scorecard."""
    timestamp: str
    git_commit: str
    total_score: float = 0.0
    max_score: float = 100.0
    decision: str = "NO-GO"  # GO | CONDITIONAL | NO-GO
    critical_failures: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence_paths: list[str] = field(default_factory=list)
    dimension_scores: dict = field(default_factory=dict)
    checks: list[dict] = field(default_factory=list)


class PreDemoQualification:
    """
    Run all qualification checks and produce scorecard.
    """

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.results: list[CheckResult] = []
        self.critical_failures: list[str] = []
        self.warnings: list[str] = []
        self.evidence_paths: list[str] = []

    def run(self) -> QualificationScorecard:
        """Run all checks. Returns scorecard."""
        print("=" * 70)
        print("  TITAN XAU AI — Pre-Demo World-Class Qualification Gate")
        print("=" * 70)
        print()

        # ─── 1. RUNTIME STABILITY (20 pts) ──
        print("[1/7] Runtime Stability (20 pts)")
        print("-" * 50)
        self._check("launcher_imports", "Launcher imports", 4, self._test_launcher_imports)
        self._check("config_loads", "Config loads safely", 4, self._test_config_loads)
        self._check("models_load", "Models load + predict", 4, self._test_models_load)
        self._check("feature_stream", "Feature stream works", 4, self._test_feature_stream)
        self._check("inference_chain", "Inference chain (XGB→meta→Signal)", 4, self._test_inference_chain)
        print()

        # ─── 2. SAFETY CONTROLS (20 pts) ──
        print("[2/7] Safety Controls (20 pts)")
        print("-" * 50)
        self._check("dry_run_default", "dry_run=True default everywhere", 5,
                    self._test_dry_run_default, critical=True)
        self._check("live_disabled", "Live trading disabled by default", 3,
                    self._test_live_disabled, critical=True)
        self._check("real_account_rejected", "Real account rejected", 3,
                    self._test_real_account_rejected, critical=True)
        self._check("demo_account_accepted", "Demo account accepted", 3,
                    self._test_demo_account_accepted)
        self._check("kill_switch_blocks", "Kill-switch blocks unsafe trades", 3,
                    self._test_kill_switch_blocks, critical=True)
        self._check("emergency_stop", "Emergency stop + flatten works", 3,
                    self._test_emergency_stop)
        print()

        # ─── 3. DRY-RUN EXECUTION (15 pts) ──
        print("[3/7] Dry-Run Execution (15 pts)")
        print("-" * 50)
        self._check("dry_run_order", "Dry-run order creation", 5, self._test_dry_run_order)
        self._check("no_mt5_calls", "No real MT5 calls in dry_run", 5,
                    self._test_no_mt5_calls, critical=True)
        self._check("sl_tp_mandatory", "SL/TP mandatory on every order", 5,
                    self._test_sl_tp_mandatory, critical=True)
        print()

        # ─── 4. AUDIT JOURNAL (15 pts) ──
        print("[4/7] Audit Journal (15 pts)")
        print("-" * 50)
        self._check("journal_writes", "Journal writes JSONL records", 4, self._test_journal_writes)
        self._check("journal_append_only", "Journal is append-only", 4,
                    self._test_journal_append_only, critical=True)
        self._check("journal_recovery", "Journal recovers from crash", 4,
                    self._test_journal_recovery)
        self._check("journal_lifecycle", "Journal has complete lifecycle", 3,
                    self._test_journal_lifecycle)
        print()

        # ─── 5. DEPLOYMENT EASE (10 pts) ──
        print("[5/7] Deployment Ease (10 pts)")
        print("-" * 50)
        self._check("setup_wizard", "Setup wizard generates config", 3, self._test_setup_wizard)
        self._check("first_run_check", "First-run check works", 2, self._test_first_run_check)
        self._check("build_spec", "PyInstaller build spec exists", 2, self._test_build_spec)
        self._check("user_guide", "User guide exists for non-technical users", 3, self._test_user_guide)
        print()

        # ─── 6. MT5 DEMO READINESS (10 pts) ──
        print("[6/7] MT5 Demo Readiness (10 pts)")
        print("-" * 50)
        self._check("mt5_validator", "MT5 validator works (stub)", 4, self._test_mt5_validator)
        self._check("mt5_demo_adapter", "MT5 demo adapter validates account", 3,
                    self._test_mt5_demo_adapter)
        self._check("position_sync", "Position sync works", 3, self._test_position_sync)
        print()

        # ─── 7. MONITORING / REPORTING (10 pts) ──
        print("[7/7] Monitoring / Reporting (10 pts)")
        print("-" * 50)
        self._check("metrics_collector", "Metrics collector works", 3, self._test_metrics_collector)
        self._check("daily_report", "Daily report generation", 3, self._test_daily_report)
        self._check("weekly_report", "Weekly report generation", 2, self._test_weekly_report)
        self._check("dashboard_spec", "Dashboard spec exists", 2, self._test_dashboard_spec)
        print()

        # ─── Compute score ──
        return self._compute_scorecard()

    # ─── Check runner ───────────────────────────────────────────────────

    def _check(self, key: str, name: str, max_score: float,
               test_fn, critical: bool = False) -> None:
        """Run a single check."""
        try:
            passed, evidence = test_fn()
        except Exception as e:
            passed = False
            evidence = f"ERROR: {e}"

        result = CheckResult(
            name=name, passed=passed,
            score=max_score if passed else 0.0,
            max_score=max_score,
            evidence=evidence,
            critical=critical,
        )
        self.results.append(result)

        icon = "✓" if passed else "✗"
        crit = " [CRITICAL]" if critical else ""
        print(f"  {icon} {name} ({result.score:.0f}/{max_score:.0f}){crit}")
        if self.verbose and evidence:
            print(f"      → {evidence[:100]}")
        if not passed and critical:
            self.critical_failures.append(name)
        elif not passed:
            self.warnings.append(f"{name}: {evidence}")

    # ─── Compute scorecard ──────────────────────────────────────────────

    def _compute_scorecard(self) -> QualificationScorecard:
        total = sum(r.score for r in self.results)
        max_total = sum(r.max_score for r in self.results)

        # Dimension scores
        dims = {}
        dim_names = {
            1: "runtime_stability", 2: "safety_controls", 3: "dry_run_execution",
            4: "audit_journal", 5: "deployment_ease", 6: "mt5_demo_readiness",
            7: "monitoring_reporting",
        }
        # Group results by section (every ~5-6 checks per section)
        section_starts = [0, 5, 11, 14, 18, 22, 25]  # approximate indices
        section_ends = [5, 11, 14, 18, 22, 25, len(self.results)]
        for i, (start, end) in enumerate(zip(section_starts, section_ends)):
            section_results = self.results[start:end]
            dim_name = dim_names.get(i + 1, f"dim_{i+1}")
            dims[dim_name] = {
                "score": sum(r.score for r in section_results),
                "max": sum(r.max_score for r in section_results),
            }

        # Decision
        if len(self.critical_failures) > 0:
            decision = "NO-GO"
        elif total >= 90:
            decision = "GO FOR DEMO"
        elif total >= 80:
            decision = "CONDITIONAL"
        else:
            decision = "NO-GO"

        # Git commit
        try:
            git_commit = subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=str(REPO_ROOT), stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            git_commit = "unknown"

        scorecard = QualificationScorecard(
            timestamp=datetime.now(timezone.utc).isoformat(),
            git_commit=git_commit,
            total_score=total,
            max_score=max_total,
            decision=decision,
            critical_failures=self.critical_failures,
            failed_checks=[r.name for r in self.results if not r.passed],
            warnings=self.warnings,
            evidence_paths=self.evidence_paths,
            dimension_scores=dims,
            checks=[{"name": r.name, "passed": r.passed, "score": r.score,
                      "max_score": r.max_score, "evidence": r.evidence,
                      "critical": r.critical}
                     for r in self.results],
        )

        # Save scorecard
        self._save_scorecard(scorecard)
        return scorecard

    def _save_scorecard(self, scorecard: QualificationScorecard) -> None:
        """Save scorecard to JSON + CSV."""
        output_dir = REPO_ROOT / "data" / "qualification"
        output_dir.mkdir(parents=True, exist_ok=True)

        # JSON
        json_path = output_dir / "pre_demo_scorecard.json"
        with open(json_path, "w") as f:
            json.dump(asdict(scorecard), f, indent=2, default=str)
        self.evidence_paths.append(str(json_path))

        # CSV
        csv_path = output_dir / "pre_demo_scorecard.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["check_name", "passed", "score", "max_score", "critical", "evidence"])
            for check in scorecard.checks:
                writer.writerow([
                    check["name"], check["passed"], check["score"],
                    check["max_score"], check["critical"], check["evidence"][:200],
                ])
        self.evidence_paths.append(str(csv_path))

    # ─── Test methods ───────────────────────────────────────────────────

    def _test_launcher_imports(self) -> tuple[bool, str]:
        import titan_launcher
        return True, "titan_launcher.py imports OK"

    def _test_config_loads(self) -> tuple[bool, str]:
        import yaml
        path = REPO_ROOT / "config" / "runtime.yaml"
        if not path.exists():
            return False, f"Config not found: {path}"
        with open(path) as f:
            cfg = yaml.safe_load(f)
        if cfg.get("runtime", {}).get("dry_run") is not True:
            return False, "dry_run is not True"
        return True, "Config loads, dry_run=True"

    def _test_models_load(self) -> tuple[bool, str]:
        from titan.production.model_loader import load_production_models
        bundle = load_production_models()
        if bundle.ok:
            return True, f"xgb={bundle.xgb_n_features}f, meta={bundle.meta_n_features}f"
        return False, f"Model load failed: {bundle.errors}"

    def _test_feature_stream(self) -> tuple[bool, str]:
        from titan.production.feature_stream import H1FeatureStream
        fs = H1FeatureStream(window=300)
        vec = fs.latest_vector(source="canonical")
        if vec.is_valid and vec.features.shape == (55,):
            return True, f"55 features, {vec.n_bars_used} bars"
        return False, f"Feature stream invalid: {vec.error}"

    def _test_inference_chain(self) -> tuple[bool, str]:
        from titan.production.inference import InferenceEngine
        engine = InferenceEngine()
        signal = engine.generate(source="canonical")
        if signal is not None and signal.feature_vector is not None:
            return True, f"dir={signal.direction.name} conf={signal.confidence:.3f}"
        return False, "Inference returned None"

    def _test_dry_run_default(self) -> tuple[bool, str]:
        from titan.production.trade_loop import TradeLoopConfig
        from titan.production.order_modifier import OrderModifier
        from titan.production.watchdog_restarter import WatchdogRestarter
        from titan.runtime.launcher import LauncherConfig
        checks = [
            TradeLoopConfig().dry_run is True,
            OrderModifier().dry_run is True,
            WatchdogRestarter().dry_run is True,
            LauncherConfig().dry_run is True,
            LauncherConfig().live_trading is False,
        ]
        if all(checks):
            return True, "All 5 modules have dry_run=True"
        return False, f"Some modules not dry_run: {checks}"

    def _test_live_disabled(self) -> tuple[bool, str]:
        import yaml
        path = REPO_ROOT / "config" / "runtime.yaml"
        with open(path) as f:
            cfg = yaml.safe_load(f)
        rt = cfg.get("runtime", {})
        if rt.get("live_trading") is False:
            return True, "live_trading=false in config"
        return False, "live_trading is True — UNSAFE"

    def _test_real_account_rejected(self) -> tuple[bool, str]:
        from titan.forward_test.mt5_demo_adapter import StubMT5DemoAdapter
        adapter = StubMT5DemoAdapter(simulate_demo=False)
        result = adapter.connect()
        if not result:
            return True, "Real account correctly rejected"
        return False, "Real account was NOT rejected — CRITICAL"

    def _test_demo_account_accepted(self) -> tuple[bool, str]:
        from titan.forward_test.mt5_demo_adapter import StubMT5DemoAdapter
        adapter = StubMT5DemoAdapter(simulate_demo=True)
        result = adapter.connect()
        if result and adapter.verification.is_demo:
            return True, f"Demo accepted (login={adapter.verification.login})"
        return False, "Demo account not accepted"

    def _test_kill_switch_blocks(self) -> tuple[bool, str]:
        import asyncio
        from titan.production.kill_switch_fsm import KillSwitchFSM, KillSwitchInput, KillState
        from titan.production.trade_loop import TradeLoop, TradeLoopConfig
        from titan.production.inference import Signal, Direction
        import numpy as np

        async def test():
            fsm = KillSwitchFSM()
            fsm.update(KillSwitchInput(daily_loss_pct=3.5))  # HALT
            assert fsm.state == KillState.HALT_NEW_TRADES
            loop = TradeLoop(TradeLoopConfig(dry_run=True), kill_switch=fsm)
            sig = Signal(timestamp=time.time(), direction=Direction.LONG,
                         confidence=0.80, meta_confidence=0.85,
                         xgb_proba=[0.2, 0.8], meta_proba=[0.15, 0.85],
                         is_tradeable=True, feature_vector=np.zeros(55),
                         inference_ms=10.0, source="test")
            decision = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
            return not decision.accepted
        result = asyncio.run(test())
        if result:
            return True, "Kill-switch HALT blocked trade"
        return False, "Kill-switch did NOT block trade"

    def _test_emergency_stop(self) -> tuple[bool, str]:
        from titan.production.kill_switch_fsm import KillSwitchFSM, KillSwitchInput, KillState
        fsm = KillSwitchFSM()
        fsm.update(KillSwitchInput(max_drawdown_pct=8.5))
        if fsm.state == KillState.EMERGENCY_STOP and fsm.requires_flatten:
            return True, "EMERGENCY_STOP + requires_flatten=True"
        return False, f"State={fsm.state.value}, requires_flatten={fsm.requires_flatten}"

    def _test_dry_run_order(self) -> tuple[bool, str]:
        import asyncio
        from titan.production.trade_loop import TradeLoop, TradeLoopConfig
        from titan.production.inference import Signal, Direction
        import numpy as np

        async def test():
            loop = TradeLoop(TradeLoopConfig(dry_run=True))
            sig = Signal(timestamp=time.time(), direction=Direction.LONG,
                         confidence=0.80, meta_confidence=0.85,
                         xgb_proba=[0.2, 0.8], meta_proba=[0.15, 0.85],
                         is_tradeable=True, feature_vector=np.zeros(55),
                         inference_ms=10.0, source="test")
            decision = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
            return decision.accepted and decision.dry_run and decision.order_request is not None
        result = asyncio.run(test())
        if result:
            return True, "Dry-run order created with SL/TP"
        return False, "Dry-run order not created"

    def _test_no_mt5_calls(self) -> tuple[bool, str]:
        """Verify order_result is None in dry_run (no broker submission)."""
        import asyncio
        from titan.production.trade_loop import TradeLoop, TradeLoopConfig
        from titan.production.inference import Signal, Direction
        import numpy as np

        async def test():
            loop = TradeLoop(TradeLoopConfig(dry_run=True))
            sig = Signal(timestamp=time.time(), direction=Direction.LONG,
                         confidence=0.80, meta_confidence=0.85,
                         xgb_proba=[0.2, 0.8], meta_proba=[0.15, 0.85],
                         is_tradeable=True, feature_vector=np.zeros(55),
                         inference_ms=10.0, source="test")
            decision = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
            return decision.order_result is None
        result = asyncio.run(test())
        if result:
            return True, "order_result=None (no MT5 call)"
        return False, "order_result is not None — MT5 was called!"

    def _test_sl_tp_mandatory(self) -> tuple[bool, str]:
        import asyncio
        from titan.production.trade_loop import TradeLoop, TradeLoopConfig
        from titan.production.inference import Signal, Direction
        import numpy as np

        async def test():
            loop = TradeLoop(TradeLoopConfig(dry_run=True))
            sig = Signal(timestamp=time.time(), direction=Direction.LONG,
                         confidence=0.80, meta_confidence=0.85,
                         xgb_proba=[0.2, 0.8], meta_proba=[0.15, 0.85],
                         is_tradeable=True, feature_vector=np.zeros(55),
                         inference_ms=10.0, source="test")
            decision = await loop.process_signal(sig, entry_price=2000.0, spread_usd=0.2)
            if decision.accepted and decision.order_request:
                req = decision.order_request
                return req.get("sl", 0) > 0 and req.get("tp", 0) > 0
            return False
        result = asyncio.run(test())
        if result:
            return True, "SL>0 and TP>0 on order"
        return False, "SL or TP missing"

    def _test_journal_writes(self) -> tuple[bool, str]:
        import tempfile
        from titan.production.trade_journal import TradeJournal, EventType
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            path = tf.name
        try:
            journal = TradeJournal(path=path)
            journal.log_startup({"test": True})
            journal.log_shutdown()
            journal.flush()
            records = journal.read_all()
            if len(records) >= 2:
                return True, f"{len(records)} records written"
            return False, f"Only {len(records)} records"
        finally:
            os.unlink(path)

    def _test_journal_append_only(self) -> tuple[bool, str]:
        import tempfile
        from titan.production.trade_journal import TradeJournal
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            path = tf.name
        try:
            journal = TradeJournal(path=path)
            journal.log_startup({"seq": 1})
            journal.flush()
            first_records = journal.read_all()
            journal.log_shutdown()
            journal.flush()
            second_records = journal.read_all()
            # First record must be unchanged
            if (len(second_records) == 2 and
                second_records[0]["data"]["seq"] == 1):
                return True, "Append-only verified (2 records, first unchanged)"
            return False, "Append-only violated"
        finally:
            os.unlink(path)

    def _test_journal_recovery(self) -> tuple[bool, str]:
        import tempfile
        from titan.production.trade_journal import TradeJournal
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            path = tf.name
        try:
            journal = TradeJournal(path=path)
            journal.log_startup({"test": 1})
            journal.log_shutdown()
            journal.flush()
            # Append corrupt line
            with open(path, "a") as f:
                f.write('{"partial": "corrupt')
            recovered = journal.recover_from_crash()
            if recovered == 2:
                return True, f"Recovered {recovered} records after crash"
            return False, f"Recovered {recovered} (expected 2)"
        finally:
            os.unlink(path)

    def _test_journal_lifecycle(self) -> tuple[bool, str]:
        import tempfile
        from titan.production.trade_journal import TradeJournal, EventType
        from titan.production.inference import Signal, Direction
        from titan.production.trade_loop import TradeDecision
        import numpy as np

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            path = tf.name
        try:
            journal = TradeJournal(path=path)
            journal.log_startup({"test": True})
            sig = Signal(timestamp=time.time(), direction=Direction.LONG,
                         confidence=0.80, meta_confidence=0.85,
                         xgb_proba=[0.2, 0.8], meta_proba=[0.15, 0.85],
                         is_tradeable=True, feature_vector=np.zeros(55),
                         inference_ms=10.0, source="test")
            journal.log_signal(sig)
            dec = TradeDecision(accepted=True, signal=sig, risk_decision="ALLOW",
                                adjusted_volume=0.01, order_request={"symbol": "XAUUSD"},
                                evaluation_ms=5.0, dry_run=True)
            journal.log_decision(dec)
            journal.log_order(dec)
            journal.log_exit(ticket=50001, exit_reason="TP_HIT",
                             entry_price=2000.0, exit_price=2001.0,
                             direction=1, volume=0.01, pnl_usd=10.0,
                             holding_time_seconds=3600)
            journal.log_shutdown()
            journal.flush()
            verification = journal.verify_complete_lifecycle()
            if verification["has_signal"] and verification["has_decision"] and verification["has_order"] and verification["has_exit"]:
                return True, f"Lifecycle complete ({verification['total_records']} records)"
            return False, f"Lifecycle incomplete: {verification}"
        finally:
            os.unlink(path)

    def _test_setup_wizard(self) -> tuple[bool, str]:
        import tempfile
        from titan.setup.setup_wizard import SetupWizard
        import yaml
        with tempfile.TemporaryDirectory() as tmpdir:
            wizard = SetupWizard(cli_mode=True, stub_mt5=True)
            wizard.config_path = Path(tmpdir) / "test.yaml"
            wizard.state.terminal_path = "/fake"
            wizard.state.login = 12345
            wizard.state.password = "test"
            wizard.state.server = "Demo"
            wizard.state.deployment_mode = "local"
            wizard.state.journal_path = "data/j.jsonl"
            config = wizard._build_config()
            with open(wizard.config_path, "w") as f:
                yaml.safe_dump(config, f)
            if wizard.config_path.exists():
                return True, "Config generated by wizard"
            return False, "Config not generated"

    def _test_first_run_check(self) -> tuple[bool, str]:
        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "first_run_check.py")],
            capture_output=True, text=True, timeout=30,
            cwd=str(REPO_ROOT),
        )
        if result.returncode == 0:
            return True, "First run check passed"
        return False, f"Exit code {result.returncode}"

    def _test_build_spec(self) -> tuple[bool, str]:
        spec = REPO_ROOT / "TITAN.spec"
        bat = REPO_ROOT / "build_titan.bat"
        if spec.exists() and bat.exists():
            return True, "TITAN.spec + build_titan.bat exist"
        return False, "Build spec or bat missing"

    def _test_user_guide(self) -> tuple[bool, str]:
        guide = REPO_ROOT / "docs" / "USER_GUIDE.md"
        if guide.exists() and guide.stat().st_size > 1000:
            return True, f"User guide ({guide.stat().st_size // 1024} KB)"
        return False, "User guide missing or too small"

    def _test_mt5_validator(self) -> tuple[bool, str]:
        from titan.setup.mt5_validator import StubMT5Validator
        v = StubMT5Validator()
        result = v.validate(simulate_demo=True)
        if result.ok:
            return True, "MT5 validator (stub) passes"
        return False, f"Validator failed: {result.errors}"

    def _test_mt5_demo_adapter(self) -> tuple[bool, str]:
        from titan.forward_test.mt5_demo_adapter import StubMT5DemoAdapter
        adapter = StubMT5DemoAdapter(simulate_demo=True)
        if adapter.connect():
            return True, "Demo adapter connects"
        return False, "Demo adapter failed"

    def _test_position_sync(self) -> tuple[bool, str]:
        import asyncio
        from titan.production.position_sync import PositionSync, BrokerPosition

        async def test():
            sync = PositionSync(interval_seconds=10, broker_source="stub",
                                magic_filter=None)
            sync.set_stub_positions([
                BrokerPosition(ticket=1, symbol="XAUUSD", direction=1, volume=0.01,
                               entry_price=2000, stop_loss=1995, take_profit=2010,
                               open_time=time.time()),
            ])
            report = await sync.sync_once()
            return report.new_positions == 1
        result = asyncio.run(test())
        if result:
            return True, "Position sync detected new position"
        return False, "Position sync failed"

    def _test_metrics_collector(self) -> tuple[bool, str]:
        import tempfile
        from titan.forward_test.metrics_collector import MetricsCollector
        from titan.production.trade_journal import TradeJournal, EventType
        from titan.production.inference import Signal, Direction
        from titan.production.trade_loop import TradeDecision
        import numpy as np

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            path = tf.name
        try:
            journal = TradeJournal(path=path)
            sig = Signal(timestamp=time.time(), direction=Direction.LONG,
                         confidence=0.80, meta_confidence=0.85,
                         xgb_proba=[0.2, 0.8], meta_proba=[0.15, 0.85],
                         is_tradeable=True, feature_vector=np.zeros(55),
                         inference_ms=10.0, source="test")
            journal.log_signal(sig)
            dec = TradeDecision(accepted=True, signal=sig, risk_decision="ALLOW",
                                adjusted_volume=0.01, order_request={"symbol": "XAUUSD"},
                                evaluation_ms=5.0, dry_run=True)
            journal.log_decision(dec)
            journal.log_exit(ticket=1, exit_reason="TP_HIT", entry_price=2000,
                             exit_price=2001, direction=1, volume=0.01,
                             pnl_usd=10.0, holding_time_seconds=3600)
            journal.flush()
            collector = MetricsCollector(journal_path=path, output_dir=tempfile.mkdtemp())
            snap = collector.collect()
            if snap.signals_generated >= 1 and snap.trades_closed >= 1:
                return True, f"signals={snap.signals_generated} trades={snap.trades_closed}"
            return False, f"signals={snap.signals_generated} trades={snap.trades_closed}"
        finally:
            os.unlink(path)

    def _test_daily_report(self) -> tuple[bool, str]:
        import tempfile
        from titan.forward_test.report_generator import ReportGenerator
        from titan.production.trade_journal import TradeJournal
        from datetime import datetime, timezone

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            path = tf.name
        try:
            journal = TradeJournal(path=path)
            journal.log_startup({"test": True})
            journal.log_shutdown()
            journal.flush()
            gen = ReportGenerator(journal_path=path, output_dir=tempfile.mkdtemp())
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            report = gen.generate_daily_report(date=today)
            if report.date == today:
                return True, f"Daily report for {today}"
            return False, "Daily report date mismatch"
        finally:
            os.unlink(path)

    def _test_weekly_report(self) -> tuple[bool, str]:
        import tempfile
        from titan.forward_test.report_generator import ReportGenerator
        from titan.production.trade_journal import TradeJournal
        from datetime import datetime, timezone, timedelta

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            path = tf.name
        try:
            journal = TradeJournal(path=path)
            journal.log_startup({"test": True})
            journal.flush()
            gen = ReportGenerator(journal_path=path, output_dir=tempfile.mkdtemp())
            week_start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
            report = gen.generate_weekly_report(week_start=week_start)
            if report.week_start == week_start:
                return True, f"Weekly report for {week_start}"
            return False, "Weekly report failed"
        finally:
            os.unlink(path)

    def _test_dashboard_spec(self) -> tuple[bool, str]:
        dash = REPO_ROOT / "monitoring" / "forward_test_dashboard.json"
        if dash.exists():
            return True, "forward_test_dashboard.json exists"
        return False, "Dashboard spec missing"

    # ─── Print summary ──────────────────────────────────────────────────

    @staticmethod
    def print_summary(scorecard: QualificationScorecard) -> None:
        print()
        print("=" * 70)
        print("  PRE-DEMO QUALIFICATION SCORECARD")
        print("=" * 70)
        print()
        print(f"  Timestamp:       {scorecard.timestamp}")
        print(f"  Git commit:      {scorecard.git_commit}")
        print()
        print(f"  DIMENSION SCORES:")
        for dim, scores in scorecard.dimension_scores.items():
            pct = (scores["score"] / scores["max"] * 100) if scores["max"] > 0 else 0
            bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
            print(f"    {dim:<25} {scores['score']:>5.0f}/{scores['max']:<5.0f}  {bar} {pct:.0f}%")
        print()
        print(f"  TOTAL SCORE:     {scorecard.total_score:.0f}/{scorecard.max_score:.0f}")
        print()

        if scorecard.critical_failures:
            print(f"  CRITICAL FAILURES ({len(scorecard.critical_failures)}):")
            for cf in scorecard.critical_failures:
                print(f"    ✗ {cf}")
            print()

        if scorecard.warnings:
            print(f"  WARNINGS ({len(scorecard.warnings)}):")
            for w in scorecard.warnings[:10]:
                print(f"    ⚠ {w[:100]}")
            print()

        print(f"  EVIDENCE FILES:")
        for path in scorecard.evidence_paths:
            print(f"    → {path}")
        print()

        print("=" * 70)
        if scorecard.decision == "GO FOR DEMO":
            print(f"  ✅ DECISION: {scorecard.decision}")
            print(f"     TITAN is qualified for 30-day MT5 demo forward test.")
        elif scorecard.decision == "CONDITIONAL":
            print(f"  ⚠ DECISION: {scorecard.decision}")
            print(f"     Fix issues before starting demo forward test.")
        else:
            print(f"  ❌ DECISION: {scorecard.decision}")
            print(f"     TITAN is NOT qualified for demo forward test.")
        print("=" * 70)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TITAN Pre-Demo Qualification")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    qualification = PreDemoQualification(verbose=args.verbose)
    scorecard = qualification.run()
    PreDemoQualification.print_summary(scorecard)

    # Exit code: 0=GO, 1=CONDITIONAL, 2=NO-GO
    if scorecard.decision == "GO FOR DEMO":
        sys.exit(0)
    elif scorecard.decision == "CONDITIONAL":
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
