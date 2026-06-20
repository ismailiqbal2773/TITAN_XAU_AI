"""TITAN XAU AI — Backtest Package"""
from .engine import (
    TickReplayExecutor, CostEngine, BacktestResult, BacktestTrade,
    TickData, Verdict, generate_synthetic_ticks, generate_synthetic_signals,
)

__all__ = [
    "TickReplayExecutor", "CostEngine", "BacktestResult", "BacktestTrade",
    "TickData", "Verdict", "generate_synthetic_ticks", "generate_synthetic_signals",
]
