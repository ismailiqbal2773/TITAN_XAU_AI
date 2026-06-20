"""
TITAN XAU AI — FastAPI Server
REST API + WebSocket. Health, metrics, control endpoints.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ControlRequest(BaseModel):
    action: str            # halt / resume / set_mode / set_weights
    target: str = ""
    value: str = ""


def create_app(
    metrics_registry=None,
    broker_engine=None,
    risk_engine=None,
    execution_engine=None,
    ceo_supervisor=None,
    weighting_engine=None,
    ensemble_voter=None,
    database=None,
    alert_manager=None,
) -> FastAPI:
    """Create FastAPI app with all endpoints."""

    app = FastAPI(
        title="TITAN XAU AI",
        description="Institutional AI Trading System for XAUUSD",
        version="1.0.0",
    )

    # ─── Health ───

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        db_ok = database is not None
        return {
            "status": "healthy" if db_ok else "degraded",
            "version": "1.0.0",
            "uptime_seconds": time.time() - (metrics_registry._start_time if metrics_registry else time.time()),
            "components": {
                "database": "ok" if db_ok else "not_initialized",
                "broker": "ok" if broker_engine else "not_initialized",
                "risk": "ok" if risk_engine else "not_initialized",
                "execution": "ok" if execution_engine else "not_initialized",
                "ceo": "ok" if ceo_supervisor else "not_initialized",
                "weighting": "ok" if weighting_engine else "not_initialized",
                "ensemble": "ok" if ensemble_voter else "not_initialized",
            },
        }

    @app.get("/health/live")
    async def liveness():
        """Kubernetes liveness probe."""
        return {"status": "alive"}

    @app.get("/health/ready")
    async def readiness():
        """Kubernetes readiness probe."""
        ready = database is not None
        return JSONResponse(
            status_code=200 if ready else 503,
            content={"ready": ready}
        )

    # ─── Metrics ───

    @app.get("/metrics", response_class=PlainTextResponse)
    async def prometheus_metrics():
        """Prometheus scrape endpoint."""
        if metrics_registry:
            return PlainTextResponse(
                metrics_registry.export(),
                media_type=metrics_registry.content_type,
            )
        return PlainTextResponse("# metrics not available\n")

    # ─── Status ───

    @app.get("/api/status")
    async def system_status():
        """Get current system status."""
        status = {
            "ceo_status": ceo_supervisor.status.value if ceo_supervisor else "UNKNOWN",
            "ceo_cycle": ceo_supervisor.cycle_count if ceo_supervisor else 0,
            "weighting_cycle": weighting_engine.cycle_count if weighting_engine else 0,
            "risk_mode": risk_engine.mode.value if risk_engine else "UNKNOWN",
            "kill_switch": risk_engine.kill_switch_armed if risk_engine else False,
            "exec_halted": execution_engine.is_halted if execution_engine else False,
            "active_models": ensemble_voter.active_models if ensemble_voter else 0,
            "current_weights": ensemble_voter.current_weights if ensemble_voter else {},
            "timestamp": time.time(),
        }
        return status

    @app.get("/api/weights")
    async def get_weights():
        """Get current model weights."""
        if weighting_engine and weighting_engine.current_weights:
            w = weighting_engine.current_weights
            return {
                "weights": w.weights,
                "algorithm": w.algorithm_used,
                "regime": w.regime,
                "timestamp": w.timestamp,
            }
        return {"weights": {}, "algorithm": "none"}

    @app.get("/api/positions")
    async def get_positions():
        """Get open positions."""
        if execution_engine:
            positions = execution_engine.get_positions()
            return {"count": len(positions), "positions": [str(p) for p in positions] if positions else []}
        return {"count": 0, "positions": []}

    @app.get("/api/trades")
    async def get_trades(limit: int = 50):
        """Get recent trades."""
        if database:
            from titan.database.layer import TradeRepository
            repo = TradeRepository(database)
            trades = await repo.get_trade_history(limit)
            return {"count": len(trades), "trades": trades}
        return {"count": 0, "trades": []}

    @app.get("/api/risk")
    async def get_risk_state():
        """Get current risk state."""
        if risk_engine:
            state = risk_engine.get_state()
            return {
                "mode": state.mode.value,
                "equity": state.equity,
                "balance": state.balance,
                "max_drawdown_pct": state.max_drawdown_pct,
                "daily_drawdown_pct": state.daily_drawdown_pct,
                "risk_utilization": state.risk_utilization,
                "kill_switch": state.kill_switch_armed,
                "open_positions": state.open_positions,
                "stats": risk_engine.stats,
            }
        return {"error": "risk engine not initialized"}

    # ─── Control ───

    @app.post("/api/control")
    async def control(req: ControlRequest):
        """Control endpoint — halt/resume/set_mode/set_weights."""
        actions = {
            "halt": _halt,
            "resume": _resume,
            "flatten": _flatten,
            "set_mode": _set_mode,
        }
        handler = actions.get(req.action)
        if handler:
            return await handler(req)
        return JSONResponse(status_code=400, content={"error": f"Unknown action: {req.action}"})

    async def _halt(req):
        if execution_engine:
            execution_engine.set_halt(True)
            return {"status": "halted"}
        return {"error": "execution engine not available"}

    async def _resume(req):
        if execution_engine:
            execution_engine.set_halt(False)
            return {"status": "resumed"}
        return {"error": "execution engine not available"}

    async def _flatten(req):
        if execution_engine:
            closed = await execution_engine.close_all_positions()
            return {"status": "flattened", "closed": closed}
        return {"error": "execution engine not available"}

    async def _set_mode(req):
        if risk_engine:
            risk_engine.set_mode(req.value)
            return {"status": "mode_set", "mode": req.value}
        return {"error": "risk engine not available"}

    # ─── WebSocket ───

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        """WebSocket for real-time updates."""
        await ws.accept()
        try:
            while True:
                # Send status update every 5 seconds
                data = {
                    "type": "status",
                    "timestamp": time.time(),
                    "ceo_status": ceo_supervisor.status.value if ceo_supervisor else "UNKNOWN",
                    "risk_mode": risk_engine.mode.value if risk_engine else "UNKNOWN",
                    "weights": ensemble_voter.current_weights if ensemble_voter else {},
                }
                await ws.send_json(data)
                await asyncio.sleep(5)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")

    return app
