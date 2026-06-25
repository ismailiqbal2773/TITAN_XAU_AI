"""
TITAN XAU AI — Runtime Launcher (Sprint 5)

Fail-closed launcher that wires all Sprint 1-5 components together.
Loads config/runtime.yaml, validates safety constraints, and starts
the system in dry_run mode by default.

FAIL-CLOSED BEHAVIOR:
  - If dry_run is not explicitly true → refuse to start
  - If live_trading is true but TITAN_LIVE_TRADING env var != 1 → refuse
  - If model files missing → refuse to start
  - If config file missing or invalid → refuse to start
  - If kill_switch_fsm fails to initialize → refuse to start
  - Any runtime error → emergency stop + journal entry

Usage:
    from titan.runtime.launcher import TitanLauncher, LauncherConfig
    launcher = TitanLauncher(config_path="config/runtime.yaml")
    launcher.start()  # runs until Ctrl+C
"""
from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# ─── Hard safety constants ───────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "runtime.yaml"


def _compute_current_atr(feature_stream, period: int = 14) -> float:
    """
    Compute current ATR(period) from an H1FeatureStream's bar buffer.

    Mirrors AutonomousRuntime._compute_current_atr() exactly so the launcher
    smoke test uses the SAME ATR definition as the production inference loop.

    Returns 0.0 if insufficient data — in which case TradeLoop._compute_sl_tp
    will detect the zero ATR and emit a fallback_used=True warning.
    """
    try:
        import numpy as np
        import pandas as pd
        bars = feature_stream._bars
        if bars is None or len(bars) < period + 1:
            return 0.0
        h, l, c = bars["high"], bars["low"], bars["close"]
        tr = pd.concat([
            (h - l),
            (h - c.shift(1)).abs(),
            (l - c.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean().iloc[-1]
        return float(atr) if not np.isnan(atr) else 0.0
    except Exception as e:
        logger.warning(f"_compute_current_atr failed: {e}")
        return 0.0


@dataclass
class LauncherConfig:
    """Parsed launcher config (validated)."""
    dry_run: bool = True
    live_trading: bool = False
    log_level: str = "INFO"
    journal_path: str = "data/runtime/titan_journal.jsonl"
    session_id: str = "auto"

    # Symbol
    symbol_name: str = "XAUUSD"
    timeframe: str = "H1"

    # Model paths (absolute)
    xgb_path: str = ""
    meta_path: str = ""
    canonical_path: str = ""

    # Feature
    feature_window: int = 300
    feature_source: str = "canonical"

    # Inference
    xgb_threshold: float = 0.55
    meta_threshold: float = 0.65

    # Risk
    max_lot: float = 0.01
    max_open_positions: int = 1
    sl_pips: float = 50
    tp_pips: float = 100
    sl_mode: str = "atr"               # Sprint 8.4 — ATR is production default
    atr_period: int = 14
    atr_sl_multiplier: float = 2.0     # balanced profile
    atr_tp_multiplier: float = 4.0
    max_spread_usd: float = 1.0
    deviation_points: int = 20
    magic_number: int = 202619

    # Kill-switch
    ks_max_daily_loss_pct: float = 3.0
    ks_max_drawdown_pct: float = 5.0
    ks_emergency_drawdown_pct: float = 8.0

    # News filter
    news_csv_path: str = "data/economic_calendar.csv"
    news_block_window_minutes: int = 30

    # Position sync
    sync_broker_source: str = "stub"
    sync_interval_seconds: float = 10.0

    # Watchdog
    watchdog_dry_run: bool = True
    watchdog_check_interval_s: float = 10.0

    # Prop Firm Adaptive Risk Layer (Sprint 9.0)
    prop_firm_enabled: bool = False             # DEFAULT: false — no behavior change
    prop_firm_profile: str = "none"             # none | auto | <profile_id>
    prop_firm_phase: str = "challenge"
    prop_firm_auto_detect_on_start: bool = True
    prop_firm_lock_after_load: bool = True
    prop_firm_initial_balance: float = 100000.0
    prop_firm_custom_overrides: dict = field(default_factory=dict)

    # Adaptive Capital Protection Layer (Sprint 9.2)
    capital_protection_enabled: bool = False    # DEFAULT: false — no behavior change

    # Raw config (for debugging)
    raw: dict = field(default_factory=dict)


class LauncherError(Exception):
    """Raised when launcher cannot safely start."""


class TitanLauncher:
    """
    Fail-closed system launcher.

    Verifies:
      1. Config file exists and is valid YAML
      2. dry_run=True (refuses if false without env var)
      3. live_trading=False (refuses if true without env var)
      4. Model files exist
      5. Canonical data exists (if feature_source=canonical)
      6. Journal directory writable
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self.config: Optional[LauncherConfig] = None
        self._started = False
        self._components: dict = {}

    # ─── Public API ─────────────────────────────────────────────────────

    def load_config(self) -> LauncherConfig:
        """Load + validate config. Raises LauncherError on any safety violation."""
        if not self.config_path.exists():
            raise LauncherError(f"Config file not found: {self.config_path}")

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise LauncherError(f"Invalid YAML in config: {e}")
        if not isinstance(raw, dict):
            raise LauncherError("Config must be a YAML mapping")

        cfg = LauncherConfig(raw=raw)

        # Parse runtime section
        rt = raw.get("runtime", {})
        cfg.dry_run = bool(rt.get("dry_run", True))
        cfg.live_trading = bool(rt.get("live_trading", False))
        cfg.log_level = str(rt.get("log_level", "INFO"))
        cfg.journal_path = str(rt.get("journal_path", cfg.journal_path))
        cfg.session_id = str(rt.get("session_id", "auto"))

        # Symbol
        sym = raw.get("symbol", {})
        cfg.symbol_name = str(sym.get("name", "XAUUSD"))
        cfg.timeframe = str(sym.get("timeframe", "H1"))

        # Models
        models = raw.get("models", {})
        cfg.xgb_path = self._resolve_path(models.get("xgb_path", ""))
        cfg.meta_path = self._resolve_path(models.get("meta_path", ""))

        # Features
        feats = raw.get("features", {})
        cfg.feature_window = int(feats.get("window", 300))
        cfg.feature_source = str(feats.get("source", "canonical"))
        cfg.canonical_path = self._resolve_path(feats.get("canonical_path", ""))

        # Inference
        inf = raw.get("inference", {})
        cfg.xgb_threshold = float(inf.get("xgb_threshold", 0.55))
        cfg.meta_threshold = float(inf.get("meta_threshold", 0.65))

        # Risk
        risk = raw.get("risk", {})
        cfg.max_lot = float(risk.get("max_lot", 0.01))
        cfg.max_open_positions = int(risk.get("max_open_positions", 1))
        cfg.sl_pips = float(risk.get("sl_pips", 50))
        cfg.tp_pips = float(risk.get("tp_pips", 100))
        cfg.sl_mode = str(risk.get("sl_mode", "atr"))
        cfg.atr_period = int(risk.get("atr_period", 14))
        cfg.atr_sl_multiplier = float(risk.get("atr_sl_multiplier", 2.0))
        cfg.atr_tp_multiplier = float(risk.get("atr_tp_multiplier", 4.0))
        cfg.max_spread_usd = float(risk.get("max_spread_usd", 1.0))
        cfg.deviation_points = int(risk.get("deviation_points", 20))
        cfg.magic_number = int(risk.get("magic_number", 202619))

        # Kill-switch
        ks = raw.get("kill_switch", {})
        cfg.ks_max_daily_loss_pct = float(ks.get("max_daily_loss_pct", 3.0))
        cfg.ks_max_drawdown_pct = float(ks.get("max_drawdown_pct", 5.0))
        cfg.ks_emergency_drawdown_pct = float(ks.get("emergency_drawdown_pct", 8.0))

        # News
        nf = raw.get("news_filter", {})
        cfg.news_csv_path = self._resolve_path(nf.get("csv_path", "data/economic_calendar.csv"))
        cfg.news_block_window_minutes = int(nf.get("block_window_minutes", 30))

        # Position sync
        sync = raw.get("position_sync", {})
        cfg.sync_broker_source = str(sync.get("broker_source", "stub"))
        cfg.sync_interval_seconds = float(sync.get("interval_seconds", 10.0))

        # Watchdog
        wd = raw.get("watchdog", {})
        cfg.watchdog_dry_run = bool(wd.get("dry_run", True))
        cfg.watchdog_check_interval_s = float(wd.get("check_interval_s", 10.0))

        # Prop Firm Adaptive Risk Layer (Sprint 9.0)
        pf = raw.get("prop_firm", {}) or {}
        cfg.prop_firm_enabled = bool(pf.get("enabled", False))
        cfg.prop_firm_profile = str(pf.get("profile", "none"))
        cfg.prop_firm_phase = str(pf.get("phase", "challenge"))
        cfg.prop_firm_auto_detect_on_start = bool(pf.get("auto_detect_on_start", True))
        cfg.prop_firm_lock_after_load = bool(pf.get("lock_after_load", True))
        cfg.prop_firm_initial_balance = float(pf.get("initial_balance", 100000.0))
        cfg.prop_firm_custom_overrides = dict(pf.get("custom_overrides", {}) or {})

        # Adaptive Capital Protection Layer (Sprint 9.2)
        cp = raw.get("capital_protection", {}) or {}
        cfg.capital_protection_enabled = bool(cp.get("enabled", False))

        # ─── SAFETY VALIDATION ──
        self._validate_safety(cfg)

        self.config = cfg
        logger.info(f"Config loaded + validated: {self.config_path}")
        return cfg

    def validate_runtime(self) -> bool:
        """
        Verify all components can be initialized.
        Does NOT start anything — just checks.
        """
        if self.config is None:
            self.load_config()

        cfg = self.config
        errors = []

        # Model files
        if not os.path.exists(cfg.xgb_path):
            errors.append(f"XGB model not found: {cfg.xgb_path}")
        if not os.path.exists(cfg.meta_path):
            errors.append(f"Meta-label model not found: {cfg.meta_path}")

        # Canonical data (if source=canonical)
        if cfg.feature_source == "canonical" and not os.path.exists(cfg.canonical_path):
            errors.append(f"Canonical data not found: {cfg.canonical_path}")

        # Journal directory writable
        journal_dir = os.path.dirname(cfg.journal_path)
        if journal_dir:
            try:
                os.makedirs(journal_dir, exist_ok=True)
                test_file = os.path.join(journal_dir, ".write_test")
                # Sprint 9.0.1: explicit UTF-8 (defensive — content is ASCII).
                with open(test_file, "w", encoding="utf-8") as f:
                    f.write("test")
                os.unlink(test_file)
            except IOError as e:
                errors.append(f"Journal directory not writable: {journal_dir} ({e})")

        if errors:
            for e in errors:
                logger.error(f"Validation failed: {e}")
            return False
        logger.info("✓ Runtime validation passed")
        return True

    def start(self, autonomous: bool = False) -> None:
        """
        Start the TITAN system.
        If autonomous=True, starts the full 6-loop trading runtime (Sprint 8).
        If autonomous=False, runs smoke test only.
        Blocks until Ctrl+C or shutdown signal.
        """
        if self._started:
            raise LauncherError("Launcher already started")

        # Load + validate
        self.load_config()
        if not self.validate_runtime():
            raise LauncherError("Runtime validation failed — refusing to start")

        cfg = self.config
        logging.basicConfig(level=getattr(logging, cfg.log_level.upper(), logging.INFO),
                             format="%(asctime)s %(levelname)s %(name)s: %(message)s")

        logger.info("=" * 70)
        logger.info("TITAN XAU AI — Launcher Starting")
        logger.info("=" * 70)
        logger.info(f"dry_run: {cfg.dry_run}")
        logger.info(f"live_trading: {cfg.live_trading}")
        logger.info(f"symbol: {cfg.symbol_name} {cfg.timeframe}")
        logger.info(f"journal: {cfg.journal_path}")

        # ─── Initialize components ──
        try:
            from titan.production.trade_journal import TradeJournal
            from titan.production.kill_switch_fsm import (
                KillSwitchFSM, KillSwitchConfig,
            )
            from titan.production.inference import InferenceEngine
            from titan.production.trade_loop import TradeLoop, TradeLoopConfig
            from titan.production.position_sync import PositionSync
            from titan.production.cold_start import ColdStartReconciler

            # Journal
            journal = TradeJournal(path=cfg.journal_path,
                                    session_id=None if cfg.session_id == "auto" else cfg.session_id)
            self._components["journal"] = journal

            # Kill-switch
            ks_cfg = KillSwitchConfig(
                max_daily_loss_pct=cfg.ks_max_daily_loss_pct,
                max_drawdown_pct=cfg.ks_max_drawdown_pct,
                emergency_drawdown_pct=cfg.ks_emergency_drawdown_pct,
            )
            ks_callback = lambda t: journal.log_heartbeat({
                "event": "kill_switch_transition",
                "from": t.from_state.value, "to": t.to_state.value,
                "trigger": t.trigger,
            })
            kill_switch = KillSwitchFSM(config=ks_cfg, journal_callback=ks_callback)
            self._components["kill_switch"] = kill_switch

            # Inference
            engine = InferenceEngine(
                xgb_threshold=cfg.xgb_threshold,
                meta_threshold=cfg.meta_threshold,
                feature_window=cfg.feature_window,
            )
            self._components["inference"] = engine

            # Trade loop
            loop_cfg = TradeLoopConfig(
                dry_run=cfg.dry_run,
                max_lot=cfg.max_lot,
                max_open_positions=cfg.max_open_positions,
                sl_pips=cfg.sl_pips,
                tp_pips=cfg.tp_pips,
                sl_mode=cfg.sl_mode,
                atr_sl_multiplier=cfg.atr_sl_multiplier,
                atr_tp_multiplier=cfg.atr_tp_multiplier,
                max_spread_usd=cfg.max_spread_usd,
                deviation_points=cfg.deviation_points,
                magic_number=cfg.magic_number,
            )
            trade_loop = TradeLoop(config=loop_cfg, journal=journal,
                                    kill_switch=kill_switch)
            self._components["trade_loop"] = trade_loop

            # Position sync
            sync = PositionSync(
                interval_seconds=cfg.sync_interval_seconds,
                broker_source=cfg.sync_broker_source,
                magic_filter=cfg.magic_number,
                on_position_closed=trade_loop.notify_position_closed,
            )
            self._components["position_sync"] = sync

            # Cold start
            reconciler = ColdStartReconciler(position_sync=sync)
            self._components["cold_start"] = reconciler

            # ─── Sprint 9.0: Prop Firm Adaptive Risk Layer ───────────────
            # When prop_firm.enabled=true, load profile from
            # config/prop_firm_profiles.yaml and apply to KillSwitchFSM +
            # TradeLoop + NewsFilter + ATR multipliers.
            # When prop_firm.enabled=false (default), no behavior change.
            prop_firm_mgr = None
            if cfg.prop_firm_enabled:
                from titan.production.prop_firm_manager import (
                    PropFirmProfileManager,
                    apply_profile_to_kill_switch,
                    apply_profile_to_trade_loop,
                    apply_profile_to_news_filter,
                    apply_profile_to_atr,
                )
                profiles_yaml = REPO_ROOT / "config" / "prop_firm_profiles.yaml"
                prop_firm_mgr = PropFirmProfileManager(
                    profiles_path=str(profiles_yaml),
                    journal=journal,
                )
                logger.info(f"PropFirmProfileManager loaded "
                            f"({len(prop_firm_mgr.list_profiles())} profiles available)")

                # Handle profile=auto, profile=none, profile=<id>
                profile_id = cfg.prop_firm_profile
                if profile_id == "none":
                    logger.warning(
                        "prop_firm.enabled=true but profile=none — "
                        "refusing to start challenge mode (fail-closed)"
                    )
                    raise LauncherError(
                        "prop_firm.enabled=true requires profile != 'none'. "
                        "Set prop_firm.profile to a valid profile_id or 'auto'."
                    )
                elif profile_id == "auto":
                    # Auto-detect (advisory only) — refuse to start
                    # until operator confirms
                    suggestion = None
                    if cfg.prop_firm_auto_detect_on_start:
                        try:
                            import MetaTrader5 as mt5
                            if mt5.initialize():
                                acc = mt5.account_info()
                                mt5.shutdown()
                                suggestion = prop_firm_mgr.auto_detect(acc)
                        except Exception as e:
                            logger.warning(f"MT5 auto-detect failed: {e}")
                    if suggestion is None:
                        logger.error(
                            "prop_firm.profile=auto but no suggestion found — "
                            "refusing to start. Set prop_firm.profile explicitly."
                        )
                        raise LauncherError(
                            "prop_firm.profile=auto requires operator confirmation. "
                            "Set prop_firm.profile to a specific profile_id."
                        )
                    else:
                        logger.error(
                            f"Auto-detect suggested {suggestion!r} but auto-apply "
                            f"is disabled. Set prop_firm.profile={suggestion!r} "
                            f"explicitly to confirm."
                        )
                        raise LauncherError(
                            f"Auto-detect suggested {suggestion!r}. Set "
                            f"prop_firm.profile={suggestion!r} explicitly to confirm."
                        )
                else:
                    # Explicit profile load
                    profile = prop_firm_mgr.load_profile(
                        profile_id,
                        custom_overrides=cfg.prop_firm_custom_overrides if profile_id == "custom" else None,
                    )
                    logger.info(f"Prop firm profile loaded: {profile_id} ({profile.name})")

                    # Apply profile to components
                    apply_profile_to_kill_switch(profile, ks_cfg)
                    # Re-init kill_switch with updated config
                    kill_switch = KillSwitchFSM(
                        config=ks_cfg, journal_callback=ks_callback,
                    )
                    self._components["kill_switch"] = kill_switch
                    apply_profile_to_trade_loop(profile, loop_cfg)
                    apply_profile_to_news_filter(profile, self._components.get("news_filter"))
                    apply_profile_to_atr(profile, loop_cfg)

                    # Re-init trade_loop with updated config + new kill_switch
                    trade_loop = TradeLoop(
                        config=loop_cfg, journal=journal, kill_switch=kill_switch,
                    )
                    self._components["trade_loop"] = trade_loop

                    # Lock profile if configured
                    if cfg.prop_firm_lock_after_load:
                        prop_firm_mgr.lock()

                    self._components["prop_firm_manager"] = prop_firm_mgr
                    logger.info(f"✓ Prop firm layer ACTIVE: profile={profile_id} "
                                f"locked={prop_firm_mgr.is_locked}")
            else:
                logger.info("Prop firm layer DISABLED (prop_firm.enabled=false) — "
                            "existing runtime behavior unchanged")

            # ─── Sprint 9.2: Adaptive Capital Protection Layer ────────────
            # When capital_protection.enabled=true, initialize AccountHealthEngine,
            # DynamicRiskEngine, RecoveryMode, CapitalPreservation, ProfitLock,
            # EquityProtection. Engines are stored in _components for the
            # AutonomousRuntime to query during heartbeat. They DO NOT modify
            # any existing risk logic — they only provide dynamic limits that
            # downstream consumers may optionally apply.
            # When capital_protection.enabled=false (default), no behavior change.
            if cfg.capital_protection_enabled:
                from titan.production.account_health_engine import (
                    AccountHealthEngine, HealthWeights,
                )
                from titan.production.dynamic_risk_engine import DynamicRiskEngine
                from titan.production.capital_protection import (
                    RecoveryMode, RecoveryConfig,
                    CapitalPreservation, CapitalPreservationConfig,
                    ProfitLock, ProfitLockConfig,
                    EquityProtection,
                )
                cp_cfg = (raw or {}).get("capital_protection", {}) or {}
                weights_cfg = cp_cfg.get("weights", {}) or {}
                weights = HealthWeights(
                    daily_dd=float(weights_cfg.get("daily_dd", 0.20)),
                    total_dd=float(weights_cfg.get("total_dd", 0.20)),
                    consecutive_losses=float(weights_cfg.get("consecutive_losses", 0.15)),
                    winning_streak=float(weights_cfg.get("winning_streak", 0.10)),
                    equity_slope=float(weights_cfg.get("equity_slope", 0.10)),
                    volatility_regime=float(weights_cfg.get("volatility_regime", 0.05)),
                    kill_switch_state=float(weights_cfg.get("kill_switch_state", 0.15)),
                    recovery_status=float(weights_cfg.get("recovery_status", 0.05)),
                )
                health_engine = AccountHealthEngine(journal=journal, weights=weights)
                dynamic_risk = DynamicRiskEngine(journal=journal)

                rec_cfg = cp_cfg.get("recovery", {}) or {}
                recovery = RecoveryMode(
                    config=RecoveryConfig(
                        losing_streak_threshold=int(rec_cfg.get("losing_streak_threshold", 3)),
                        min_confidence_threshold=float(rec_cfg.get("min_confidence_threshold", 0.75)),
                        recovery_target_trades=int(rec_cfg.get("recovery_target_trades", 2)),
                        risk_multiplier=float(rec_cfg.get("risk_multiplier", 0.5)),
                    ),
                    journal=journal,
                )

                cap_cfg = cp_cfg.get("capital_preservation", {}) or {}
                capital_pres = CapitalPreservation(
                    config=CapitalPreservationConfig(
                        trigger_dd_pct=float(cap_cfg.get("trigger_dd_pct", 8.0)),
                        halt_new_entries_dd_pct=float(cap_cfg.get("halt_new_entries_dd_pct", 9.0)),
                        risk_multiplier=float(cap_cfg.get("risk_multiplier", 0.25)),
                    ),
                    journal=journal,
                )

                pl_cfg = cp_cfg.get("profit_lock", {}) or {}
                profit_lock = ProfitLock(
                    config=ProfitLockConfig(
                        enabled=bool(pl_cfg.get("enabled", False)),
                        lock_distance_pct=float(pl_cfg.get("lock_distance_pct", 2.0)),
                        trail_distance_pct=float(pl_cfg.get("trail_distance_pct", 1.0)),
                    ),
                    initial_balance=cfg.prop_firm_initial_balance,
                    journal=journal,
                )

                equity_prot = EquityProtection(
                    initial_balance=cfg.prop_firm_initial_balance,
                    journal=journal,
                )

                self._components["health_engine"] = health_engine
                self._components["dynamic_risk_engine"] = dynamic_risk
                self._components["recovery_mode"] = recovery
                self._components["capital_preservation"] = capital_pres
                self._components["profit_lock"] = profit_lock
                self._components["equity_protection"] = equity_prot
                logger.info("✓ Capital protection layer ACTIVE "
                            "(health_engine + dynamic_risk + recovery + "
                            "capital_preservation + profit_lock + equity_protection)")
            else:
                logger.info("Capital protection layer DISABLED "
                            "(capital_protection.enabled=false) — "
                            "existing runtime behavior unchanged")

            logger.info("✓ All components initialized")

            # ─── Run smoke test (single inference cycle) ──
            logger.info("Running single inference cycle...")
            import asyncio
            async def smoke():
                # Cold start
                report = await reconciler.reconcile()
                logger.info(f"Cold start: {report}")
                # Inference
                signal = engine.generate(source=cfg.feature_source,
                                          symbol=cfg.symbol_name)
                logger.info(f"Signal: dir={signal.direction.name} "
                            f"conf={signal.confidence:.3f} tradeable={signal.is_tradeable}")
                # Sprint 8.5 fix: compute current ATR from the inference
                # engine's feature stream and pass it to process_signal so
                # the smoke test exercises the ATR SL/TP path instead of
                # silently falling back to fixed-pip mode.
                current_atr = _compute_current_atr(
                    engine.feature_stream, period=cfg.atr_period,
                )
                # Use latest close as entry price (matches production behaviour)
                entry_price = float(engine.feature_stream._bars["close"].iloc[-1]) \
                    if len(engine.feature_stream._bars) > 0 else 2000.0
                logger.info(
                    f"Smoke ATR context: current_atr={current_atr:.6f} "
                    f"entry_price={entry_price:.2f} "
                    f"sl_mode={cfg.sl_mode} "
                    f"atr_sl_mult={cfg.atr_sl_multiplier} "
                    f"atr_tp_mult={cfg.atr_tp_multiplier}"
                )
                # Trade decision
                decision = await trade_loop.process_signal(
                    signal=signal,
                    entry_price=entry_price,
                    spread_usd=0.20,
                    current_atr=current_atr,
                )
                logger.info(f"Decision: accepted={decision.accepted} "
                            f"dry_run={decision.dry_run} reason={decision.reject_reason}")
                if decision.accepted and decision.order_request:
                    logger.info(
                        f"Order: {decision.order_request.get('order_type')} "
                        f"vol={decision.order_request.get('volume')} "
                        f"SL={decision.order_request.get('sl')} "
                        f"TP={decision.order_request.get('tp')} "
                        f"mode_used={decision.sl_tp_mode_used} "
                        f"fallback={decision.fallback_used}"
                    )
                return decision

            decision = asyncio.run(smoke())
            journal.flush()
            logger.info(f"✓ Smoke test complete — journal: {journal.record_count} records")

            self._started = True
            logger.info("=" * 70)
            logger.info("TITAN launcher smoke test PASSED — system is demo-ready")
            logger.info(f"Journal: {cfg.journal_path}")
            logger.info("=" * 70)

            # ─── Start autonomous runtime (Sprint 8) ──
            if autonomous:
                logger.info("Starting autonomous runtime (6 async loops)...")
                from titan.runtime.autonomous_loops import (
                    AutonomousRuntime, RuntimeConfig,
                )
                rt_cfg = RuntimeConfig(
                    dry_run=cfg.dry_run,
                    symbol=cfg.symbol_name,
                    feature_source=cfg.feature_source,
                    feature_window=cfg.feature_window,
                    xgb_threshold=cfg.xgb_threshold,
                    meta_threshold=cfg.meta_threshold,
                )
                runtime = AutonomousRuntime(
                    config=rt_cfg,
                    journal=self._components["journal"],
                    # Sprint 9.3.1: pass capital-protection engines when active
                    health_engine=self._components.get("health_engine"),
                    dynamic_risk_engine=self._components.get("dynamic_risk_engine"),
                    recovery_mode=self._components.get("recovery_mode"),
                    capital_preservation=self._components.get("capital_preservation"),
                    profit_lock=self._components.get("profit_lock"),
                    equity_protection=self._components.get("equity_protection"),
                    prop_firm_manager=self._components.get("prop_firm_manager"),
                )
                runtime.initialize()
                self._components["autonomous_runtime"] = runtime

                # Start runtime (blocks until shutdown)
                import asyncio
                asyncio.run(runtime.start())

        except Exception as e:
            logger.error(f"Launcher failed: {e}", exc_info=True)
            # Fail-closed: log to journal if available
            if "journal" in self._components:
                self._components["journal"].log_heartbeat({
                    "event": "launcher_failed",
                    "error": str(e),
                })
                self._components["journal"].flush()
            raise

    def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("TITAN launcher shutting down...")
        if "journal" in self._components:
            self._components["journal"].log_heartbeat({
                "event": "launcher_shutdown",
            })
            self._components["journal"].flush()
        self._started = False
        logger.info("✓ Shutdown complete")

    # ─── Internal ───────────────────────────────────────────────────────

    def _resolve_path(self, path: str) -> str:
        """Resolve relative paths against repo root."""
        if not path:
            return ""
        p = Path(path)
        if not p.is_absolute():
            p = REPO_ROOT / p
        return str(p)

    def _validate_safety(self, cfg: LauncherConfig) -> None:
        """Enforce safety constraints. Raises LauncherError on violation."""
        # Rule 1: dry_run must be True unless TITAN_LIVE_TRADING=1
        if not cfg.dry_run:
            flag = os.environ.get("TITAN_LIVE_TRADING", "0")
            if flag != "1":
                raise LauncherError(
                    "dry_run=false in config but TITAN_LIVE_TRADING env var is not '1'. "
                    "Set TITAN_LIVE_TRADING=1 to enable live trading."
                )
        # Rule 2: live_trading flag must match dry_run
        if cfg.live_trading and cfg.dry_run:
            raise LauncherError(
                "live_trading=true but dry_run=true — contradictory config"
            )
        # Rule 3: max_lot cannot exceed 0.01 (hard cap)
        if cfg.max_lot > 0.01:
            raise LauncherError(
                f"max_lot={cfg.max_lot} exceeds hard cap 0.01"
            )
        # Rule 4: max_open_positions cannot exceed 1 (hard cap)
        if cfg.max_open_positions > 1:
            raise LauncherError(
                f"max_open_positions={cfg.max_open_positions} exceeds hard cap 1"
            )
        # Rule 5: watchdog must be dry_run unless live
        if not cfg.watchdog_dry_run and cfg.dry_run:
            raise LauncherError(
                "watchdog.dry_run=false but runtime.dry_run=true — "
                "watchdog auto-restart requires live mode"
            )
        logger.info("✓ Safety validation passed")


if __name__ == "__main__":
    # CLI entry point
    import argparse
    parser = argparse.ArgumentParser(description="TITAN XAU AI Launcher")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH),
                        help="Path to runtime.yaml")
    parser.add_argument("--validate-only", action="store_true",
                        help="Validate config + runtime without starting")
    args = parser.parse_args()

    launcher = TitanLauncher(config_path=args.config)
    if args.validate_only:
        try:
            launcher.load_config()
            ok = launcher.validate_runtime()
            print(f"Validation: {'PASS' if ok else 'FAIL'}")
            sys.exit(0 if ok else 1)
        except LauncherError as e:
            print(f"Validation FAIL: {e}", file=sys.stderr)
            sys.exit(2)
    else:
        try:
            launcher.start()
        except (LauncherError, KeyboardInterrupt) as e:
            print(f"Launcher stopped: {e}")
            launcher.shutdown()
