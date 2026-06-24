"""
TITAN XAU AI — Main Orchestrator
Service startup, dependency injection, health checks,
graceful shutdown, recovery logic.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
import time
from typing import Optional

import yaml

from titan.observability import MetricsRegistry, AlertManager, setup_logging

logger = logging.getLogger(__name__)


class TitanSystem:
    """
    Main orchestrator. Wires all components together.
    Manages lifecycle: initialize → start → run → shutdown.
    """

    def __init__(self, config_path: str = "config/titan.yaml"):
        self._config = self._load_config(config_path)
        setup_logging(level=self._config.get("system", {}).get("log_level", "INFO"))

        # Core components (lazy initialized)
        self._db = None
        self._redis = None
        self._broker = None
        self._market_data = None
        self._execution = None
        self._risk = None
        self._regime = None
        self._trend_strategy = None
        self._range_strategy = None
        self._volatility_strategy = None
        self._ensemble = None
        self._xgb_model = None
        self._lstm_model = None
        self._transformer_model = None
        self._ceo = None
        self._weighting = None
        self._metrics = None
        self._alerts = None
        self._api_app = None
        # Commercial layer
        self._license_guard = None
        self._license_store = None
        self._compliance_engine = None
        self._compliance_audit = None
        # Recovery layer (production recovery)
        self._recovery_manager = None

        # State
        self._running = False
        self._tasks: list[asyncio.Task] = []
        self._start_time = 0.0
        self._shutdown_event = asyncio.Event()

    def _load_config(self, path: str) -> dict:
        # Sprint 9.0.1: explicit UTF-8 for Windows cp1252 compatibility.
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    async def _initialize_licensing(self) -> None:
        """M21 — Hardware-locked JWT license enforcement."""
        from titan.licensing import (
            JWTLicenseEngine, LicenseStore, LicenseGuard, HardwareFingerprint,
        )
        lic_cfg = self._config.get("licensing", {})
        # Resolve secret from env var if placeholder
        secret = lic_cfg.get("jwt_secret", "")
        if secret.startswith("${") and secret.endswith("}"):
            env_var = secret[2:-1]
            secret = os.environ.get(env_var, "titan-default-dev-secret-2024-not-for-prod")
        if not secret:
            secret = "titan-default-dev-secret-2024-not-for-prod"
            logger.warning("⚠ License secret not set — using dev default")
        self._license_engine = JWTLicenseEngine(secret)
        self._license_store = LicenseStore(lic_cfg.get("store_path", ":memory:"))
        self._license_guard = LicenseGuard(
            self._license_engine, self._license_store,
            fingerprint=HardwareFingerprint.collect(),
            on_violation=self._on_license_violation,
        )
        # If a license exists for this machine, startup-check it
        try:
            mt5_login = str(self._config.get("mt5", {}).get("login", 0))
            if mt5_login != "0":
                self._license_guard.startup_check(account_id=mt5_login)
                logger.info(f"✓ License validated (account={mt5_login})")
            else:
                logger.warning("⚠ No MT5 login configured — skipping license startup check (dev mode)")
        except Exception as e:
            logger.error(f"✗ License startup check failed: {e}")
            # In production we would HALT here; in dev we continue

    def _on_license_violation(self, violation) -> None:
        """Callback for license guard violations."""
        from titan.licensing.guard import GuardAction
        if violation.action == GuardAction.HALT:
            logger.critical(f"[HALT] License violation: {violation.code} — {violation.message}")
            # Schedule shutdown
            self._shutdown_event.set()
        elif violation.action == GuardAction.DEGRADE:
            logger.warning(f"[DEGRADE] License violation: {violation.code}")

    async def _initialize_compliance(self) -> None:
        """M22 — Prop firm compliance engine."""
        from titan.compliance import ComplianceEngine, ComplianceAuditLog, FirmId
        comp_cfg = self._config.get("compliance", {})
        if not comp_cfg.get("enabled", True):
            logger.info("✓ Compliance disabled in config")
            return
        firm_id_str = comp_cfg.get("firm_id", "ftmo")
        try:
            firm_id = FirmId(firm_id_str)
        except ValueError:
            logger.error(f"Unknown firm_id '{firm_id_str}', defaulting to FTMO")
            firm_id = FirmId.FTMO
        balance = float(comp_cfg.get("initial_balance", 100_000))
        phase = comp_cfg.get("phase", "phase1")
        self._compliance_engine = ComplianceEngine.for_firm(
            firm_id, balance=balance, phase=phase,
        )
        self._compliance_audit = ComplianceAuditLog(
            comp_cfg.get("audit_db_path", ":memory:")
        )
        logger.info(
            f"✓ Compliance Engine initialized (firm={firm_id.value}, "
            f"balance={balance:.0f}, phase={phase})"
        )

    async def initialize(self) -> None:
        """Initialize all components in dependency order."""
        logger.info("═══ TITAN XAU AI — INITIALIZING ═══")
        self._start_time = time.time()

        # 1. Observability
        self._metrics = MetricsRegistry()
        self._alerts = AlertManager()
        logger.info("✓ Observability initialized")

        # 1b. License Guard (M21) — must run before any trading component
        await self._initialize_licensing()
        # 1c. Compliance Engine (M22) — must run before strategies
        await self._initialize_compliance()

        # 2. Database
        from titan.database.layer import Database, RedisCache
        db_path = self._config.get("database", {}).get("sqlite_path", "data/titan.db")
        self._db = Database(db_path)
        await self._db.initialize()
        logger.info("✓ Database initialized")

        # 3. Redis (optional)
        redis_cfg = self._config.get("database", {})
        self._redis = RedisCache(
            host=redis_cfg.get("redis_host", "localhost"),
            port=redis_cfg.get("redis_port", 6379),
        )
        await self._redis.connect()
        logger.info(f"✓ Redis: {'connected' if self._redis.connected else 'degraded (no Redis)'}")

        # 4. Broker
        from titan.broker.engine import BrokerCompatibilityEngine
        self._broker = BrokerCompatibilityEngine("config/titan.yaml")
        if self._broker.initialize():
            self._broker.detect_broker()
            self._broker.resolve_symbol()
            logger.info(f"✓ Broker: {self._broker.profile.broker_id.value if self._broker.profile else 'unknown'}")
        else:
            logger.warning("✗ Broker: MT5 not available (running in degraded mode)")

        # 5. Market Data
        from titan.market_data.engine import MarketDataEngine
        symbol = self._broker.symbol_info.name if self._broker.symbol_info else "XAUUSD"
        self._market_data = MarketDataEngine(self._config, symbol)
        logger.info("✓ Market Data Engine initialized")

        # 6. Execution
        from titan.execution.engine import ExecutionEngine
        self._execution = ExecutionEngine(self._config)
        logger.info("✓ Execution Engine initialized")

        # 7. Risk
        from titan.risk.engine import RiskEngine
        self._risk = RiskEngine(self._config, self._execution)
        logger.info("✓ Risk Engine initialized")

        # 8. Regime Detection
        from titan.regime.engine import RegimeDetector
        self._regime = RegimeDetector()
        logger.info("✓ Regime Detector initialized")

        # 9. Strategies
        from titan.strategies.trend_engine import TrendStrategyEngine
        from titan.strategies.range_engine import RangeStrategyEngine
        from titan.strategies.volatility_engine import VolatilityEngine
        self._trend_strategy = TrendStrategyEngine()
        self._range_strategy = RangeStrategyEngine()
        self._volatility_strategy = VolatilityEngine()
        logger.info("✓ Strategies initialized (Trend + Range + Volatility)")

        # 10. AI Models
        from titan.ai.xgboost_model import XGBoostModel
        from titan.ai.lstm_model import LSTMModel
        from titan.ai.transformer_model import TransformerModel
        self._xgb_model = XGBoostModel()
        self._lstm_model = LSTMModel()
        self._transformer_model = TransformerModel()
        logger.info("✓ AI Models initialized (XGBoost + LSTM + Transformer)")

        # 11. Ensemble Voter
        from titan.ai.ensemble_voter import EnsembleVoter
        self._ensemble = EnsembleVoter(self._config)
        self._ensemble.register_model(self._xgb_model)
        self._ensemble.register_model(self._lstm_model)
        self._ensemble.register_model(self._transformer_model)
        logger.info("✓ Ensemble Voter initialized (3 models)")

        # 12. CEO Supervisor
        from titan.ceo.supervisor import CEOSupervisor
        model_ids = ["xgboost", "lstm", "transformer"]
        self._ceo = CEOSupervisor(model_ids, self._ensemble, self._risk)
        logger.info("✓ CEO Supervisor initialized")

        # 13. Weighting Engine
        from titan.weighting.engine import WeightingEngine
        self._weighting = WeightingEngine(self._ensemble, self._ceo)
        logger.info("✓ Weighting Engine initialized")

        # 14. API Server
        from titan.api.server import create_app
        self._api_app = create_app(
            metrics_registry=self._metrics,
            broker_engine=self._broker,
            risk_engine=self._risk,
            execution_engine=self._execution,
            ceo_supervisor=self._ceo,
            weighting_engine=self._weighting,
            ensemble_voter=self._ensemble,
            database=self._db,
            alert_manager=self._alerts,
        )
        logger.info("✓ API Server initialized")

        # 15. Recovery Manager (production recovery layer)
        from titan.recovery import RecoveryManager
        self._recovery_manager = RecoveryManager(
            db=self._db,
            redis=self._redis,
            broker=self._broker,
            execution=self._execution,
            ceo=self._ceo,
            weighting=self._weighting,
            risk=self._risk,
            alert_manager=self._alerts,
            checkpoint_interval_s=30.0,
            reconcile_interval_s=60.0,
        )
        await self._recovery_manager.initialize()
        # Crash recovery: load last known state
        last_state = await self._recovery_manager.load_last_known_state()
        if last_state:
            await self._recovery_manager.restore_state(last_state)
            logger.info("✓ Recovery: state restored from last checkpoint")
        else:
            logger.info("✓ Recovery: cold start (no previous checkpoint)")
        logger.info("✓ Recovery Manager initialized")

        elapsed = time.time() - self._start_time
        logger.info(f"═══ TITAN XAU AI — READY ({elapsed:.1f}s) ═══")

    async def start(self) -> None:
        """Start all async loops."""
        self._running = True

        # Start market data ingestion
        if self._market_data:
            await self._market_data.start()
            self._tasks.append(asyncio.create_task(self._market_data._tick_loop()))

        # Start CEO cycle
        self._tasks.append(asyncio.create_task(self._ceo_cycle_loop()))

        # Start weighting cycle
        self._tasks.append(asyncio.create_task(self._weighting_cycle_loop()))

        # Start license guard heartbeat (M21)
        if self._license_guard:
            self._tasks.append(asyncio.create_task(self._license_heartbeat_loop()))

        # Start compliance evaluation cycle (M22)
        if self._compliance_engine:
            self._tasks.append(asyncio.create_task(self._compliance_cycle_loop()))

        # Start API server (in background)
        import uvicorn
        config = uvicorn.Config(
            self._api_app, host="0.0.0.0", port=8000,
            log_level="info", access_log=False,
        )
        server = uvicorn.Server(config)
        self._tasks.append(asyncio.create_task(server.serve()))

        # Start Recovery Manager (watchdog + checkpoint + reconcile loops)
        if self._recovery_manager:
            await self._recovery_manager.start()
            logger.info("✓ Recovery Manager started (watchdog + checkpoint + reconcile)")

        logger.info("All services started. System running.")

        # Wait for shutdown signal
        await self._shutdown_event.wait()
        await self.shutdown()

    async def _license_heartbeat_loop(self) -> None:
        """License Guard heartbeat — re-verifies every 60s."""
        if not self._license_guard:
            return
        await self._license_guard.start_heartbeat()
        # The heartbeat_loop runs internally; this wrapper just holds the task alive
        while self._running:
            await asyncio.sleep(60)

    async def _compliance_cycle_loop(self) -> None:
        """Compliance Engine evaluation cycle — every 30s."""
        while self._running:
            try:
                if not self._compliance_engine:
                    await asyncio.sleep(30)
                    continue
                # In a real deployment, we'd pull live state from broker/MT5.
                # For now we evaluate with the current internal state.
                report = self._compliance_engine.evaluate()
                # Log to audit
                if self._compliance_audit:
                    self._compliance_audit.log_evaluation(
                        self._compliance_engine.firm_id.value,
                        report.to_dict(),
                    )
                # Update metrics (if available)
                if self._metrics and hasattr(self._metrics, "compliance_score"):
                    self._metrics.compliance_score.set(report.compliance_score)
                # Alert on hard breaches
                if report.must_halt:
                    await self._alerts.send_alert(
                        "P1", "Compliance HALT",
                        f"Breaches: {' | '.join(report.breaches[:3])}",
                    )
                    self._shutdown_event.set()
                elif report.must_close_all:
                    await self._alerts.send_alert(
                        "P2", "Compliance Close-All",
                        f"Breaches: {' | '.join(report.breaches[:3])}",
                    )
            except Exception as e:
                logger.error(f"Compliance cycle error: {e}")
            await asyncio.sleep(30)

    async def _ceo_cycle_loop(self) -> None:
        """CEO Supervisor 60-second cycle."""
        while self._running:
            try:
                risk_score = 90.0
                eqs = 90.0
                regime_conf = 85.0
                if self._risk:
                    state = self._risk.get_state()
                    risk_score = state.risk_utilization * 100
                    eqs = 90.0
                    regime_conf = 85.0

                status, scores = self._ceo.run_cycle(
                    risk_score=100 - risk_score, eqs=eqs, regime_conf=regime_conf
                )

                # Update metrics
                self._metrics.system_status.set(
                    {"GREEN": 0, "YELLOW": 1, "RED": 2, "RED_PRESERVE": 3}[status.value]
                )
                self._metrics.system_health.set(scores.overall)

                # Persist state
                from titan.database.layer import StateRepository
                state_repo = StateRepository(self._db)
                await state_repo.save_ceo_state(
                    status.value, scores.overall, scores.model_health,
                    scores.execution_quality, scores.risk,
                    scores.regime_confidence, self._ceo.cycle_count
                )

                # Alert on RED
                if status.value in ("RED", "RED_PRESERVE"):
                    await self._alerts.send_alert(
                        "P1", "System Status Critical",
                        f"CEO status: {status.value}, health: {scores.overall:.1f}"
                    )

            except Exception as e:
                logger.error(f"CEO cycle error: {e}")
                await self._alerts.send_alert("P2", "CEO Cycle Error", str(e))

            await asyncio.sleep(60)

    async def _weighting_cycle_loop(self) -> None:
        """Weighting Engine 60-second cycle."""
        while self._running:
            try:
                from titan.weighting.engine import ModelMetrics, WeightingInputs

                # Build metrics from recent trades (simplified)
                metrics = {
                    m: ModelMetrics(accuracy=0.6, profit_factor=1.8, sharpe=2.0,
                                   dd_contribution=0.3, slippage_sensitivity=0.2,
                                   latency_sensitivity=0.1, regime_performance=0.65)
                    for m in ["xgboost", "lstm", "transformer", "rl_manager"]
                }

                inputs = WeightingInputs(
                    regime=self._regime.current_regime.value if self._regime else "trend",
                    eqs=90, risk_score=90, broker_score=90,
                    ceo_caps={}, ceo_disabled=set(),
                    confidence={m: 0.7 for m in ["xgboost", "lstm", "transformer", "rl_manager"]},
                )

                result = self._weighting.run_cycle(metrics, inputs)

                # Update metrics
                for mid, w in result.weights.items():
                    self._metrics.weighting_weights.labels(model_id=mid).set(w)

                # Persist state
                from titan.database.layer import StateRepository
                state_repo = StateRepository(self._db)
                await state_repo.save_weighting_state(
                    result.algorithm_used, result.regime,
                    result.weights, self._weighting.cycle_count
                )

            except Exception as e:
                logger.error(f"Weighting cycle error: {e}")

            await asyncio.sleep(60)

    async def shutdown(self) -> None:
        """Graceful shutdown."""
        logger.info("═══ TITAN XAU AI — SHUTTING DOWN ═══")
        self._running = False

        # Stop Recovery Manager FIRST (saves final checkpoint)
        if self._recovery_manager:
            try:
                await self._recovery_manager.stop()
                logger.info("✓ Recovery Manager stopped (final checkpoint saved)")
            except Exception as e:
                logger.error(f"Recovery Manager shutdown error: {e}")

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

        # Close components in reverse order
        if self._market_data:
            await self._market_data.stop()
        if self._broker:
            self._broker.shutdown()
        # Commercial layer
        if self._license_guard:
            await self._license_guard.stop_heartbeat()
        if self._license_store:
            self._license_store.close()
        if self._compliance_audit:
            self._compliance_audit.close()
        if self._redis:
            await self._redis.close()
        if self._db:
            await self._db.close()

        elapsed = time.time() - self._start_time
        logger.info(f"═══ TITAN XAU AI — STOPPED (uptime: {elapsed:.0f}s) ═══")

    def install_signal_handlers(self) -> None:
        """Install SIGINT/SIGTERM handlers for graceful shutdown."""
        def handler(signum, frame):
            logger.info(f"Signal {signum} received — initiating shutdown")
            self._shutdown_event.set()

        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)


async def main():
    """Entry point."""
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config/titan.yaml"
    system = TitanSystem(config_path)
    system.install_signal_handlers()
    await system.initialize()
    await system.start()


if __name__ == "__main__":
    asyncio.run(main())
