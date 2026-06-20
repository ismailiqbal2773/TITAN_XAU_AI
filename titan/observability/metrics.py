"""
TITAN XAU AI — Observability Layer
Prometheus metrics, structured logging, alert hooks.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Optional

from prometheus_client import (
    Counter, Gauge, Histogram, Info, generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry, REGISTRY,
)
import structlog

logger = logging.getLogger(__name__)

# ─── Prometheus Metrics ───

class MetricsRegistry:
    """All Prometheus metrics in one place. Uses custom registry to avoid duplicates in tests."""

    def __init__(self, registry: CollectorRegistry = None):
        self._registry = registry or CollectorRegistry()
        # System
        self.system_status = Gauge("titan_system_status", "System status (0=GREEN,1=YELLOW,2=RED,3=PRESERVE)", registry=self._registry)
        self.system_health = Gauge("titan_system_health", "Overall health score 0-100", registry=self._registry)
        self.cycle_duration = Histogram("titan_cycle_duration_seconds", "Cycle duration", buckets=(0.01, 0.05, 0.1, 0.5, 1.0, 5.0), registry=self._registry)
        self.uptime_seconds = Gauge("titan_uptime_seconds", "System uptime in seconds", registry=self._registry)

        # CEO
        self.ceo_model_health = Gauge("titan_ceo_model_health", "Per-model health score", ["model_id"], registry=self._registry)
        self.ceo_eqs = Gauge("titan_ceo_execution_quality", "Execution quality score", registry=self._registry)
        self.ceo_risk = Gauge("titan_ceo_risk_score", "Risk score (inverted, 100=safe)", registry=self._registry)
        self.ceo_regime_conf = Gauge("titan_ceo_regime_confidence", "Regime confidence", registry=self._registry)
        self.ceo_actions = Counter("titan_ceo_actions_total", "CEO actions", ["action_type"], registry=self._registry)
        self.ceo_detectors = Counter("titan_ceo_detectors_fired_total", "Detectors fired", ["detector_id"], registry=self._registry)

        # Weighting
        self.weighting_weights = Gauge("titan_weighting_model_weight", "Model weight", ["model_id"], registry=self._registry)
        self.weighting_algorithm = Gauge("titan_weighting_algorithm_selected", "Algorithm selected (0-3)", registry=self._registry)
        self.weighting_cycle = Counter("titan_weighting_cycles_total", "Weighting cycles", registry=self._registry)

        # Risk
        self.risk_mode = Gauge("titan_risk_mode", "Risk mode (0=NORMAL,1=AGGRESSIVE,2=DEFENSIVE,3=EMERGENCY)", registry=self._registry)
        self.risk_drawdown = Gauge("titan_risk_drawdown_pct", "Current drawdown %", registry=self._registry)
        self.risk_daily_dd = Gauge("titan_risk_daily_drawdown_pct", "Daily drawdown %", registry=self._registry)
        self.risk_kill_switch = Gauge("titan_risk_kill_switch_armed", "Kill switch armed (0/1)", registry=self._registry)
        self.risk_vetoes = Counter("titan_risk_vetoes_total", "Risk vetoes", registry=self._registry)

        # Execution
        self.exec_orders = Counter("titan_exec_orders_total", "Orders submitted", ["result"], registry=self._registry)
        self.exec_latency = Histogram("titan_exec_latency_ms", "Order latency ms", buckets=(1, 5, 10, 50, 100, 200, 500), registry=self._registry)
        self.exec_throughput = Gauge("titan_exec_throughput_ops", "Current throughput ops/s", registry=self._registry)
        self.exec_halted = Gauge("titan_exec_halted", "Execution halted (0/1)", registry=self._registry)

        # Market Data
        self.md_ticks = Counter("titan_md_ticks_total", "Ticks ingested", registry=self._registry)
        self.md_rejected = Counter("titan_md_ticks_rejected_total", "Ticks rejected", registry=self._registry)
        self.md_spread = Gauge("titan_md_spread_current", "Current spread", registry=self._registry)
        self.md_spread_baseline = Gauge("titan_md_spread_baseline", "Baseline spread", registry=self._registry)

        # Regime
        self.regime_current = Gauge("titan_regime_current", "Current regime (0=TREND,1=RANGE,2=VOLATILE,3=NEWS)", registry=self._registry)
        self.regime_confidence = Gauge("titan_regime_confidence_value", "Regime confidence 0-1", registry=self._registry)

        # AI
        self.ai_inference_ms = Histogram("titan_ai_inference_ms", "AI inference time", ["model_id"], buckets=(1, 5, 10, 50, 100, 200), registry=self._registry)
        self.ai_predictions = Counter("titan_ai_predictions_total", "Predictions made", ["model_id", "direction"], registry=self._registry)

        # Database
        self.db_write_ms = Histogram("titan_db_write_ms", "DB write latency", buckets=(0.1, 0.5, 1, 5, 10, 50), registry=self._registry)
        self.db_errors = Counter("titan_db_errors_total", "DB errors", registry=self._registry)

        self._start_time = time.time()
        self._info = Info("titan", "TITAN XAU AI system info", registry=self._registry)
        self._info.info({"version": "1.0.0", "environment": "production"})

    def update_uptime(self):
        self.uptime_seconds.set(time.time() - self._start_time)

    def export(self) -> str:
        """Export metrics in Prometheus format."""
        self.update_uptime()
        return generate_latest(self._registry).decode("utf-8")

    @property
    def content_type(self) -> str:
        return CONTENT_TYPE_LATEST


# ─── Structured Logging ───

def setup_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Configure structured logging."""
    if json_output:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )
    else:
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    # Reduce noise from libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


# ─── Alert Hooks ───

class AlertManager:
    """Alert hooks for PagerDuty / Slack (degrades gracefully if not configured)."""

    def __init__(self, pagerduty_webhook: str = "", slack_webhook: str = ""):
        self._pagerduty = pagerduty_webhook
        self._slack = slack_webhook
        self._alert_count = 0
        self._alerts_sent: list[dict] = []

    async def send_alert(self, severity: str, title: str, message: str) -> None:
        """Send alert. severity: P1/P2/P3. Degrades to log if no webhook."""
        self._alert_count += 1
        alert = {
            "severity": severity,
            "title": title,
            "message": message,
            "timestamp": time.time(),
        }
        self._alerts_sent.append(alert)

        if severity == "P1":
            logger.critical(f"[P1 ALERT] {title}: {message}")
        elif severity == "P2":
            logger.warning(f"[P2 ALERT] {title}: {message}")
        else:
            logger.info(f"[P3 INFO] {title}: {message}")

        # Real webhook calls would go here (urllib/httpx)
        # Degrades gracefully — alerts are logged even without webhooks

    @property
    def alert_count(self) -> int:
        return self._alert_count

    @property
    def recent_alerts(self) -> list[dict]:
        return self._alerts_sent[-10:]
