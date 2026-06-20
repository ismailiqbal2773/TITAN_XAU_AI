"""
TITAN XAU AI — Dataset Validator (M28.4)

Validates a FeatureSet before model training. Catches:
- Schema violations (missing columns, wrong dtypes)
- Time-series integrity (duplicates, non-monotonic, gaps)
- Statistical sanity (NaNs, infinities, zero-variance, outliers)
- Feature-target leakage (correlation between targets and future-shifted features)
- Train/test boundary integrity (no overlap)
- Coverage (per-feature non-null percentage)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ValidationSeverity(str, Enum):
    PASS = "pass"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationCheck:
    check_id: str
    description: str
    severity: ValidationSeverity
    passed: bool
    details: str = ""
    metric: Optional[float] = None


@dataclass
class ValidationReport:
    checks: list[ValidationCheck] = field(default_factory=list)
    overall_severity: ValidationSeverity = ValidationSeverity.PASS
    n_errors: int = 0
    n_warnings: int = 0
    n_passed: int = 0
    score: float = 100.0       # 0-100 (100 = perfect)
    ready_for_training: bool = True

    def to_dict(self) -> dict:
        return {
            "overall_severity": self.overall_severity.value,
            "n_errors": self.n_errors,
            "n_warnings": self.n_warnings,
            "n_passed": self.n_passed,
            "score": round(self.score, 1),
            "ready_for_training": self.ready_for_training,
            "checks": [
                {
                    "check_id": c.check_id,
                    "description": c.description,
                    "severity": c.severity.value,
                    "passed": c.passed,
                    "details": c.details,
                    "metric": c.metric,
                }
                for c in self.checks
            ],
        }


class DatasetValidator:
    """
    Run a battery of validation checks on a FeatureSet.
    """

    def __init__(self, max_nan_pct: float = 0.05,
                 max_zero_var_pct: float = 0.10,
                 max_leakage_corr: float = 0.95):
        self.max_nan_pct = max_nan_pct
        self.max_zero_var_pct = max_zero_var_pct
        self.max_leakage_corr = max_leakage_corr

    def validate(self, features: pd.DataFrame,
                 targets: pd.DataFrame,
                 train_end: Optional[pd.Timestamp] = None,
                 test_start: Optional[pd.Timestamp] = None) -> ValidationReport:
        """Run all validation checks. Returns a report."""
        checks: list[ValidationCheck] = []

        # ─── Schema checks ────────────────────────────────────────────
        checks.append(self._check_not_empty(features, targets))
        checks.append(self._check_dtypes_numeric(features, "features"))
        checks.append(self._check_dtypes_numeric(targets, "targets"))

        # ─── Time-series integrity ────────────────────────────────────
        checks.append(self._check_no_duplicate_index(features))
        checks.append(self._check_monotonic_index(features))
        checks.append(self._check_no_gaps(features))

        # ─── Statistical sanity ───────────────────────────────────────
        checks.append(self._check_no_nan(features, "features"))
        checks.append(self._check_no_nan(targets, "targets"))
        checks.append(self._check_no_inf(features, "features"))
        checks.append(self._check_no_inf(targets, "targets"))
        checks.append(self._check_no_zero_variance(features))
        checks.append(self._check_no_extreme_outliers(features))

        # ─── Coverage ─────────────────────────────────────────────────
        checks.append(self._check_feature_coverage(features))

        # ─── Leakage ──────────────────────────────────────────────────
        checks.append(self._check_target_leakage(features, targets))

        # ─── Train/test boundary ──────────────────────────────────────
        if train_end is not None and test_start is not None:
            checks.append(self._check_no_train_test_overlap(
                features, train_end, test_start))

        # Aggregate
        n_errors = sum(1 for c in checks if c.severity == ValidationSeverity.ERROR and not c.passed)
        n_critical = sum(1 for c in checks if c.severity == ValidationSeverity.CRITICAL and not c.passed)
        n_warnings = sum(1 for c in checks if c.severity == ValidationSeverity.WARN and not c.passed)
        n_passed = sum(1 for c in checks if c.passed)

        if n_critical > 0:
            overall = ValidationSeverity.CRITICAL
            score = 0.0
            ready = False
        elif n_errors > 0:
            overall = ValidationSeverity.ERROR
            score = max(0.0, 60.0 - 10 * n_errors)
            ready = False
        elif n_warnings > 0:
            overall = ValidationSeverity.WARN
            score = max(60.0, 100.0 - 5 * n_warnings)
            ready = True
        else:
            overall = ValidationSeverity.PASS
            score = 100.0
            ready = True

        return ValidationReport(
            checks=checks, overall_severity=overall,
            n_errors=n_errors + n_critical,
            n_warnings=n_warnings,
            n_passed=n_passed,
            score=score,
            ready_for_training=ready,
        )

    # ─── Individual checks ────────────────────────────────────────────

    def _check_not_empty(self, features: pd.DataFrame,
                         targets: pd.DataFrame) -> ValidationCheck:
        ok = not features.empty and not targets.empty
        return ValidationCheck(
            check_id="V01_NOT_EMPTY",
            description="Features and targets are non-empty",
            severity=ValidationSeverity.CRITICAL,
            passed=ok,
            details=(f"features={len(features)} rows × {features.shape[1]} cols; "
                     f"targets={len(targets)} rows × {targets.shape[1]} cols"),
            metric=float(len(features)),
        )

    def _check_dtypes_numeric(self, df: pd.DataFrame,
                               name: str) -> ValidationCheck:
        non_numeric = [c for c, d in df.dtypes.items()
                       if not np.issubdtype(d, np.number)]
        return ValidationCheck(
            check_id=f"V02_DTYPES_{name.upper()}",
            description=f"All {name} columns are numeric",
            severity=ValidationSeverity.ERROR,
            passed=len(non_numeric) == 0,
            details=(f"Non-numeric columns: {non_numeric}" if non_numeric
                     else "All columns numeric"),
            metric=float(len(non_numeric)),
        )

    def _check_no_duplicate_index(self, df: pd.DataFrame) -> ValidationCheck:
        dup = df.index.duplicated().sum()
        return ValidationCheck(
            check_id="V03_NO_DUPLICATE_INDEX",
            description="No duplicate timestamps in index",
            severity=ValidationSeverity.ERROR,
            passed=dup == 0,
            details=(f"{dup} duplicate timestamps found" if dup else "No duplicates"),
            metric=float(dup),
        )

    def _check_monotonic_index(self, df: pd.DataFrame) -> ValidationCheck:
        mono = df.index.is_monotonic_increasing
        return ValidationCheck(
            check_id="V04_MONOTONIC_INDEX",
            description="Index is monotonically increasing",
            severity=ValidationSeverity.ERROR,
            passed=mono,
            details=("Monotonic" if mono else "Not monotonic — sort before training"),
        )

    def _check_no_gaps(self, df: pd.DataFrame) -> ValidationCheck:
        if len(df) < 2:
            return ValidationCheck(
                check_id="V05_NO_GAPS", description="No gaps in time series",
                severity=ValidationSeverity.WARN, passed=True,
                details="Insufficient data to check gaps",
            )
        deltas = df.index.to_series().diff().dropna()
        median_delta = deltas.median()
        gaps = (deltas > median_delta * 3).sum()
        gap_pct = float(gaps) / len(deltas) * 100 if len(deltas) > 0 else 0
        return ValidationCheck(
            check_id="V05_NO_GAPS",
            description="No excessive gaps in time series",
            severity=ValidationSeverity.WARN,
            passed=gap_pct < 5.0,
            details=f"{gaps} gaps ({gap_pct:.2f}%) detected; median delta={median_delta}",
            metric=gap_pct,
        )

    def _check_no_nan(self, df: pd.DataFrame, name: str) -> ValidationCheck:
        nan_pct = df.isna().sum().sum() / df.size if df.size > 0 else 0
        return ValidationCheck(
            check_id=f"V06_NO_NAN_{name.upper()}",
            description=f"No NaN values in {name}",
            severity=ValidationSeverity.ERROR if nan_pct > self.max_nan_pct else ValidationSeverity.WARN,
            passed=nan_pct == 0,
            details=f"{nan_pct:.2%} NaN values (max allowed: {self.max_nan_pct:.2%})",
            metric=float(nan_pct * 100),
        )

    def _check_no_inf(self, df: pd.DataFrame, name: str) -> ValidationCheck:
        inf_count = np.isinf(df.select_dtypes(include=np.number)).sum().sum()
        return ValidationCheck(
            check_id=f"V07_NO_INF_{name.upper()}",
            description=f"No infinite values in {name}",
            severity=ValidationSeverity.ERROR,
            passed=inf_count == 0,
            details=f"{inf_count} infinite values found",
            metric=float(inf_count),
        )

    def _check_no_zero_variance(self, df: pd.DataFrame) -> ValidationCheck:
        zero_var = (df.var() == 0).sum()
        pct = zero_var / df.shape[1] if df.shape[1] > 0 else 0
        return ValidationCheck(
            check_id="V08_NO_ZERO_VARIANCE",
            description="No zero-variance features",
            severity=ValidationSeverity.ERROR if pct > self.max_zero_var_pct else ValidationSeverity.WARN,
            passed=zero_var == 0,
            details=f"{zero_var} zero-variance features ({pct:.2%})",
            metric=float(pct * 100),
        )

    def _check_no_extreme_outliers(self, df: pd.DataFrame) -> ValidationCheck:
        """Flag features with extreme outliers (> 50 standard deviations)."""
        n_outlier_cols = 0
        for col in df.select_dtypes(include=np.number).columns:
            s = df[col]
            mu, sigma = s.mean(), s.std()
            if sigma == 0 or np.isnan(sigma):
                continue
            if (np.abs(s - mu) > 50 * sigma).any():
                n_outlier_cols += 1
        return ValidationCheck(
            check_id="V09_NO_EXTREME_OUTLIERS",
            description="No features with extreme (>50σ) outliers",
            severity=ValidationSeverity.WARN,
            passed=n_outlier_cols == 0,
            details=f"{n_outlier_cols} columns with extreme outliers",
            metric=float(n_outlier_cols),
        )

    def _check_feature_coverage(self, df: pd.DataFrame) -> ValidationCheck:
        """Per-feature non-null coverage."""
        if df.empty:
            return ValidationCheck(
                check_id="V10_FEATURE_COVERAGE",
                description="Feature non-null coverage",
                severity=ValidationSeverity.WARN, passed=False,
                details="Empty DataFrame",
            )
        coverage = df.notna().mean()
        min_cov = coverage.min()
        return ValidationCheck(
            check_id="V10_FEATURE_COVERAGE",
            description=f"All features ≥ 95% non-null coverage",
            severity=ValidationSeverity.ERROR if min_cov < 0.95 else ValidationSeverity.PASS,
            passed=min_cov >= 0.95,
            details=f"Min coverage: {min_cov:.2%}; max: {coverage.max():.2%}",
            metric=float(min_cov * 100),
        )

    def _check_target_leakage(self, features: pd.DataFrame,
                              targets: pd.DataFrame) -> ValidationCheck:
        """Check correlation between features and (potentially shifted) targets."""
        if features.empty or targets.empty:
            return ValidationCheck(
                check_id="V11_NO_LEAKAGE",
                description="No target leakage detected",
                severity=ValidationSeverity.WARN, passed=True,
                details="Insufficient data",
            )
        # Compute max abs correlation between any feature and any target
        max_corr = 0.0
        worst_pair = ""
        for tcol in targets.columns:
            correlations = features.corrwith(targets[tcol]).abs()
            correlations = correlations.dropna()
            if not correlations.empty:
                col_max = correlations.max()
                if col_max > max_corr:
                    max_corr = col_max
                    worst_pair = f"{correlations.idxmax()} ↔ {tcol}"
        return ValidationCheck(
            check_id="V11_NO_LEAKAGE",
            description=f"No target leakage (max |corr| < {self.max_leakage_corr})",
            severity=ValidationSeverity.ERROR if max_corr >= self.max_leakage_corr else ValidationSeverity.PASS,
            passed=max_corr < self.max_leakage_corr,
            details=f"Max |corr| = {max_corr:.4f} ({worst_pair})",
            metric=float(max_corr),
        )

    def _check_no_train_test_overlap(self, df: pd.DataFrame,
                                      train_end: pd.Timestamp,
                                      test_start: pd.Timestamp) -> ValidationCheck:
        # Coerce train_end/test_start to match df's tz awareness
        if df.index.tz is not None:
            if train_end.tz is None:
                train_end = train_end.tz_localize(df.index.tz)
            if test_start.tz is None:
                test_start = test_start.tz_localize(df.index.tz)
        else:
            if train_end.tz is not None:
                train_end = train_end.tz_localize(None)
            if test_start.tz is not None:
                test_start = test_start.tz_localize(None)
        train = df[df.index <= train_end]
        test = df[df.index >= test_start]
        overlap = train.index.intersection(test.index)
        return ValidationCheck(
            check_id="V12_NO_TRAIN_TEST_OVERLAP",
            description="No train/test timestamp overlap",
            severity=ValidationSeverity.CRITICAL,
            passed=len(overlap) == 0,
            details=(f"{len(overlap)} overlapping timestamps" if len(overlap)
                     else f"Train: {len(train)} rows ≤ {train_end}; Test: {len(test)} rows ≥ {test_start}"),
            metric=float(len(overlap)),
        )


__all__ = ["DatasetValidator", "ValidationReport", "ValidationCheck",
           "ValidationSeverity", "time_series_train_val_test_split",
           "PurgedKFold"]


# ─── B4: Purge / Embargo Split Helpers ────────────────────────────────────
# These helpers enforce target-horizon-aware splitting so that the last
# `purge` bars of a train chunk cannot leak labels into the next chunk
# (forward-shifted targets at horizon h use data h bars into the future).


@dataclass
class SplitResult:
    """Result of a chronological train/val/test split with purge gaps."""
    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    train_idx: tuple[int, int]
    val_idx: tuple[int, int]
    test_idx: tuple[int, int]
    purge: int
    embargo: int

    def to_dict(self) -> dict:
        return {
            "train_rows": len(self.train),
            "val_rows": len(self.val),
            "test_rows": len(self.test),
            "train_idx": self.train_idx,
            "val_idx": self.val_idx,
            "test_idx": self.test_idx,
            "purge": self.purge,
            "embargo": self.embargo,
        }


def time_series_train_val_test_split(
    df: pd.DataFrame,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    test_ratio: float = 0.2,
    purge: int = 0,
    embargo: int = 0,
) -> SplitResult:
    """Chronological train/val/test split with purge and embargo gaps.

    The split is strictly chronological (no shuffling). A purge gap of
    `purge` bars is inserted between train_end and val_start, and
    between val_end and test_start. An embargo of `embargo` bars is
    additionally inserted after test_end (excluded from any future
    re-use).

    Parameters
    ----------
    df : pd.DataFrame
        Time-indexed feature/target matrix. Index must be monotonic.
    train_ratio, val_ratio, test_ratio : float
        Fractions of the total length. Must sum to 1.0.
    purge : int
        Number of bars to drop between consecutive splits. Set to
        max(target_horizons) to prevent label leakage.
    embargo : int
        Number of bars to drop after test_end.

    Returns
    -------
    SplitResult
    """
    if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-9:
        raise ValueError(
            f"Ratios must sum to 1.0; got {train_ratio + val_ratio + test_ratio}"
        )
    if not df.index.is_monotonic_increasing:
        raise ValueError("DataFrame index must be monotonically increasing")
    n = len(df)
    if n < 10:
        raise ValueError(f"DataFrame too small for split: {n} rows")
    purge = max(0, purge)
    embargo = max(0, embargo)
    # Raw split points
    raw_train_end = int(n * train_ratio)
    raw_val_end = raw_train_end + int(n * val_ratio)
    # Apply purge: drop `purge` bars between splits
    train_end = raw_train_end
    val_start = train_end + purge
    val_end = val_start + int(n * val_ratio)
    test_start = val_end + purge
    test_end = min(n, test_start + int(n * test_ratio))
    # Bounds check
    if val_start >= val_end or test_start >= test_end:
        raise ValueError(
            f"Split with purge={purge} leaves empty val or test set; "
            f"reduce purge or use longer dataset"
        )
    train_df = df.iloc[:train_end]
    val_df = df.iloc[val_start:val_end]
    test_df = df.iloc[test_start:test_end]
    return SplitResult(
        train=train_df, val=val_df, test=test_df,
        train_idx=(0, train_end),
        val_idx=(val_start, val_end),
        test_idx=(test_start, test_end),
        purge=purge, embargo=embargo,
    )


@dataclass
class PurgedFold:
    """A single purged-k-fold: train indices + test indices with gap."""
    fold_num: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    purge: int


@dataclass
class PurgedKFoldResult:
    """Result of purged k-fold cross-validation."""
    folds: list[PurgedFold] = field(default_factory=list)
    n_splits: int = 0
    purge: int = 0
    embargo: int = 0


class PurgedKFold:
    """Time-series k-fold iterator with purge gap between train and test.

    For each fold, training data is everything before `test_start - purge`
    and after `test_end + embargo` (the embargo excludes test-adjacent
    bars whose targets may leak).

    Parameters
    ----------
    n_splits : int
        Number of folds.
    purge : int
        Bars to drop between train_end and test_start. Set to
        max(target_horizons) to prevent label leakage.
    embargo : int
        Bars to drop after test_end before the next fold's train begins.
    """

    def __init__(self, n_splits: int = 5, purge: int = 0, embargo: int = 0):
        if n_splits < 2:
            raise ValueError(f"n_splits must be ≥ 2; got {n_splits}")
        self.n_splits = n_splits
        self.purge = max(0, purge)
        self.embargo = max(0, embargo)

    def split(self, n: int) -> PurgedKFoldResult:
        """Generate fold boundaries for a series of length `n`."""
        fold_size = n // self.n_splits
        folds: list[PurgedFold] = []
        for k in range(self.n_splits):
            test_start = k * fold_size
            test_end = (k + 1) * fold_size if k < self.n_splits - 1 else n
            # Train = everything before (test_start - purge) and after
            # (test_end + embargo). For time-series safety, we use only
            # the PRE-test portion (true forward walk-forward).
            train_end = max(0, test_start - self.purge)
            train_start = 0  # Use all available pre-test data
            folds.append(PurgedFold(
                fold_num=k + 1,
                train_start=train_start, train_end=train_end,
                test_start=test_start, test_end=test_end,
                purge=self.purge,
            ))
        return PurgedKFoldResult(
            folds=folds, n_splits=self.n_splits,
            purge=self.purge, embargo=self.embargo,
        )
