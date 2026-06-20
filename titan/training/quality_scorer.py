"""
TITAN XAU AI — Data Quality Scorer (M28.5)

5-dimensional 0-100 quality scoring:
- Completeness: % of expected bars present (gap analysis)
- Accuracy: schema integrity + outlier rate
- Consistency: monotonicity, no duplicates, dtypes
- Timeliness: freshness relative to expected update cadence
- Validity: range checks, OHLC sanity, NaN/Inf rate

Each dimension produces a 0-100 score. The aggregate score is a
weighted mean. Weights favor Completeness and Accuracy (the two
most important for ML training).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class QualityDimension(str, Enum):
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    CONSISTENCY = "consistency"
    TIMELINESS = "timeliness"
    VALIDITY = "validity"


@dataclass
class QualityScore:
    """Multi-dimensional quality score for a dataset."""
    overall: float                  # 0-100
    completeness: float = 0.0
    accuracy: float = 0.0
    consistency: float = 0.0
    timeliness: float = 0.0
    validity: float = 0.0
    details: dict = field(default_factory=dict)
    grade: str = "F"                # A+ to F

    def to_dict(self) -> dict:
        return {
            "overall": round(self.overall, 1),
            "completeness": round(self.completeness, 1),
            "accuracy": round(self.accuracy, 1),
            "consistency": round(self.consistency, 1),
            "timeliness": round(self.timeliness, 1),
            "validity": round(self.validity, 1),
            "grade": self.grade,
            "details": self.details,
        }


class DataQualityScorer:
    """
    Score a dataset across 5 quality dimensions.
    """

    DEFAULT_WEIGHTS = {
        QualityDimension.COMPLETENESS: 0.30,
        QualityDimension.ACCURACY:    0.25,
        QualityDimension.CONSISTENCY: 0.20,
        QualityDimension.TIMELINESS:  0.10,
        QualityDimension.VALIDITY:    0.15,
    }

    def __init__(self, weights: Optional[dict[QualityDimension, float]] = None,
                 expected_minutes_per_bar: int = 1):
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.expected_minutes_per_bar = expected_minutes_per_bar

    def score(self, df: pd.DataFrame,
              expected_start: Optional[pd.Timestamp] = None,
              expected_end: Optional[pd.Timestamp] = None) -> QualityScore:
        """Score the dataset."""
        if df.empty:
            return QualityScore(
                overall=0.0,
                grade="F",
                details={"error": "Empty DataFrame"},
            )
        details: dict = {}
        completeness, d1 = self._score_completeness(df, expected_start, expected_end)
        accuracy, d2 = self._score_accuracy(df)
        consistency, d3 = self._score_consistency(df)
        timeliness, d4 = self._score_timeliness(df, expected_end)
        validity, d5 = self._score_validity(df)
        details.update(d1); details.update(d2); details.update(d3)
        details.update(d4); details.update(d5)
        overall = (
            self.weights[QualityDimension.COMPLETENESS] * completeness +
            self.weights[QualityDimension.ACCURACY] * accuracy +
            self.weights[QualityDimension.CONSISTENCY] * consistency +
            self.weights[QualityDimension.TIMELINESS] * timeliness +
            self.weights[QualityDimension.VALIDITY] * validity
        )
        grade = self._grade(overall)
        return QualityScore(
            overall=overall,
            completeness=completeness, accuracy=accuracy,
            consistency=consistency, timeliness=timeliness,
            validity=validity, details=details, grade=grade,
        )

    # ─── Dimensions ───────────────────────────────────────────────────

    def _score_completeness(self, df: pd.DataFrame,
                             expected_start: Optional[pd.Timestamp],
                             expected_end: Optional[pd.Timestamp]) -> tuple[float, dict]:
        """% of expected bars present."""
        if len(df) < 2:
            return 0.0, {"expected_bars": 0, "actual_bars": len(df)}
        start = expected_start or df.index.min()
        end = expected_end or df.index.max()
        expected_bars = int((end - start).total_seconds() / 60 / self.expected_minutes_per_bar)
        actual_bars = len(df)
        if expected_bars == 0:
            return 100.0, {"expected_bars": 0, "actual_bars": actual_bars}
        score = min(100.0, 100.0 * actual_bars / expected_bars)
        return score, {
            "expected_bars": expected_bars,
            "actual_bars": actual_bars,
            "missing_bars": max(0, expected_bars - actual_bars),
        }

    def _score_accuracy(self, df: pd.DataFrame) -> tuple[float, dict]:
        """OHLC sanity: high >= max(o, c, l), low <= min(o, c, h)."""
        if not all(c in df.columns for c in ("open", "high", "low", "close")):
            return 50.0, {"note": "OHLC columns missing"}
        bad_high = (df["high"] < df[["open", "close", "low"]].max(axis=1)).sum()
        bad_low = (df["low"] > df[["open", "close", "high"]].min(axis=1)).sum()
        total_bad = bad_high + bad_low
        score = max(0.0, 100.0 - 100.0 * total_bad / len(df))
        return score, {
            "bad_highs": int(bad_high),
            "bad_lows": int(bad_low),
            "total_violations": int(total_bad),
        }

    def _score_consistency(self, df: pd.DataFrame) -> tuple[float, dict]:
        """Monotonic index, no duplicates, dtypes numeric."""
        deductions = 0.0
        if not df.index.is_monotonic_increasing:
            deductions += 30.0
        dups = df.index.duplicated().sum()
        if dups > 0:
            deductions += min(30.0, 30.0 * dups / len(df))
        non_numeric = sum(1 for d in df.dtypes if not np.issubdtype(d, np.number))
        if non_numeric > 0:
            deductions += min(40.0, 40.0 * non_numeric / df.shape[1])
        score = max(0.0, 100.0 - deductions)
        return score, {
            "monotonic": df.index.is_monotonic_increasing,
            "duplicates": int(dups),
            "non_numeric_cols": int(non_numeric),
            "deductions": deductions,
        }

    def _score_timeliness(self, df: pd.DataFrame,
                           expected_end: Optional[pd.Timestamp]) -> tuple[float, dict]:
        """Freshness: how recent is the last bar?"""
        if expected_end is None:
            expected_end = pd.Timestamp.utcnow()
        last = df.index.max()
        # Coerce tz-awareness to match
        if hasattr(last, "tz") and last.tz is not None:
            if expected_end.tz is None:
                expected_end = expected_end.tz_localize(last.tz)
        else:
            if expected_end.tz is not None:
                expected_end = expected_end.tz_localize(None)
        lag = (expected_end - last).total_seconds() / 3600  # hours
        if lag < 0:  # data newer than expected (clock skew) — full score
            return 100.0, {"lag_hours": float(lag), "expected_end": str(expected_end)}
        # Deduct 1 point per hour of lag, capped at 100
        score = max(0.0, 100.0 - lag)
        return score, {
            "lag_hours": float(lag),
            "last_bar": str(last),
            "expected_end": str(expected_end),
        }

    def _score_validity(self, df: pd.DataFrame) -> tuple[float, dict]:
        """NaN rate, Inf rate, price range sanity."""
        total_cells = df.size
        nan_pct = df.isna().sum().sum() / total_cells if total_cells > 0 else 0
        numeric = df.select_dtypes(include=np.number)
        inf_count = np.isinf(numeric).sum().sum() if not numeric.empty else 0
        inf_pct = inf_count / numeric.size if numeric.size > 0 else 0
        # Price range sanity for OHLC
        price_violations = 0
        if "close" in df.columns:
            # XAUUSD realistic range: $100–$5000
            prices = df["close"]
            price_violations = int(((prices < 100) | (prices > 5000)).sum())
        # Deduct
        deductions = (
            100 * nan_pct * 2 +
            100 * inf_pct * 5 +
            (100 * price_violations / len(df) if len(df) > 0 else 0)
        )
        score = max(0.0, 100.0 - deductions)
        return score, {
            "nan_pct": float(nan_pct * 100),
            "inf_count": int(inf_count),
            "price_range_violations": price_violations,
            "deductions": float(deductions),
        }

    @staticmethod
    def _grade(score: float) -> str:
        if score >= 95: return "A+"
        if score >= 90: return "A"
        if score >= 85: return "A-"
        if score >= 80: return "B+"
        if score >= 75: return "B"
        if score >= 70: return "B-"
        if score >= 65: return "C+"
        if score >= 60: return "C"
        if score >= 50: return "D"
        return "F"


__all__ = ["DataQualityScorer", "QualityScore", "QualityDimension"]
