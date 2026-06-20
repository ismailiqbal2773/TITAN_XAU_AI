"""TITAN XAU AI — Strategies Package"""
from .trend_engine import TrendStrategyEngine, TrendSignal, TrendPattern
from .range_engine import RangeStrategyEngine, RangeSignal, RangePattern
from .volatility_engine import VolatilityEngine, VolatilitySignal, VolPattern

__all__ = [
    "TrendStrategyEngine", "TrendSignal", "TrendPattern",
    "RangeStrategyEngine", "RangeSignal", "RangePattern",
    "VolatilityEngine", "VolatilitySignal", "VolPattern",
]
