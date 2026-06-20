"""Tests for Training Preparation Module — data acquisition, ingestion,
feature engine, validator, quality scorer"""
import os
import shutil
import tempfile
import warnings
import pytest
import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

from titan.training.data_acquisition import (
    DataAcquisitionPipeline, DataSource, Timeframe, BarData, AcquisitionResult,
)
from titan.training.historical_ingestion import (
    HistoricalIngestionEngine, IngestionResult, SyntheticDataGenerator,
)
from titan.training.feature_engine import (
    FeatureEngine, FeatureSet, FeatureConfig, TargetConfig,
)
from titan.training.dataset_validator import (
    DatasetValidator, ValidationReport, ValidationCheck, ValidationSeverity,
)
from titan.training.quality_scorer import (
    DataQualityScorer, QualityScore, QualityDimension,
)


@pytest.fixture
def tmp_storage():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def synthetic_bars():
    """1 week of M1 bars for feature engine tests."""
    gen = SyntheticDataGenerator(seed=42)
    return gen.generate("2024-01-01", "2024-01-08", timeframe=Timeframe.M1)


# ─── Data Acquisition Tests ─────────────────────────────────────────────────

class TestDataAcquisition:
    def test_synthetic_source_acquires_bars(self, tmp_storage):
        pipe = DataAcquisitionPipeline(storage_dir=tmp_storage)
        result = pipe.acquire(
            source=DataSource.SYNTHETIC, symbol="XAUUSD",
            timeframe=Timeframe.M1,
            start="2024-01-01", end="2024-01-08",
        )
        assert result.bars_fetched > 0
        assert result.source == DataSource.SYNTHETIC
        assert result.symbol == "XAUUSD"
        assert result.first_timestamp is not None
        assert result.last_timestamp is not None
        assert result.output_path is not None
        assert os.path.exists(result.output_path)

    def test_invalid_date_range_raises(self, tmp_storage):
        pipe = DataAcquisitionPipeline(storage_dir=tmp_storage)
        with pytest.raises(ValueError, match="end .* must be after start"):
            pipe.acquire(
                source=DataSource.SYNTHETIC, symbol="XAUUSD",
                timeframe=Timeframe.M1,
                start="2024-02-01", end="2024-01-01",
            )

    def test_persistence_creates_year_month_partitions(self, tmp_storage):
        pipe = DataAcquisitionPipeline(storage_dir=tmp_storage)
        # Span 2 months
        pipe.acquire(
            source=DataSource.SYNTHETIC, symbol="XAUUSD",
            timeframe=Timeframe.H1,
            start="2024-01-15", end="2024-02-15",
        )
        m1_dir = os.path.join(tmp_storage, "XAUUSD", "H1")
        files = os.listdir(m1_dir)
        assert "2024-01.parquet" in files
        assert "2024-02.parquet" in files

    def test_incremental_ingestion_skips_existing(self, tmp_storage):
        pipe = DataAcquisitionPipeline(storage_dir=tmp_storage)
        # First acquisition
        r1 = pipe.acquire(
            source=DataSource.SYNTHETIC, symbol="XAUUSD",
            timeframe=Timeframe.H1,
            start="2024-01-01", end="2024-01-08",
        )
        assert r1.bars_fetched > 0
        assert r1.bars_skipped == 0
        # Second acquisition of same range → all skipped
        r2 = pipe.acquire(
            source=DataSource.SYNTHETIC, symbol="XAUUSD",
            timeframe=Timeframe.H1,
            start="2024-01-01", end="2024-01-08",
        )
        assert r2.bars_fetched == 0
        assert r2.bars_skipped > 0

    def test_csv_source(self, tmp_storage):
        # Create a CSV with synthetic data
        gen = SyntheticDataGenerator(seed=42)
        df = gen.generate("2024-01-01", "2024-01-08", timeframe=Timeframe.H1)
        df = df.reset_index()
        df = df.rename(columns={"timestamp": "time"})
        csv_path = os.path.join(tmp_storage, "test.csv")
        df.to_csv(csv_path, index=False)
        pipe = DataAcquisitionPipeline(storage_dir=tmp_storage)
        result = pipe.acquire(
            source=DataSource.CSV, symbol="XAUUSD",
            timeframe=Timeframe.H1,
            start="2024-01-01", end="2024-01-08",
            csv_path=csv_path,
        )
        assert result.bars_fetched > 0

    def test_csv_missing_file_raises(self, tmp_storage):
        pipe = DataAcquisitionPipeline(storage_dir=tmp_storage)
        with pytest.raises(FileNotFoundError):
            pipe.acquire(
                source=DataSource.CSV, symbol="XAUUSD",
                timeframe=Timeframe.H1,
                start="2024-01-01", end="2024-01-08",
                csv_path="/nonexistent/path.csv",
            )

    def test_bardata_roundtrip(self):
        ts = pd.Timestamp("2024-01-01 12:00", tz="UTC")
        b = BarData(timestamp=ts, open=2000, high=2005, low=1995, close=2002,
                    volume=100, spread=0.2)
        d = b.to_dict()
        b2 = BarData.from_dict(d)
        assert b2.open == 2000
        assert b2.close == 2002

    def test_timeframe_minutes(self):
        assert Timeframe.M1.minutes == 1
        assert Timeframe.H1.minutes == 60
        assert Timeframe.D1.minutes == 1440

    def test_schema_validation_fixes_bad_ohlc(self, tmp_storage):
        """Validator should auto-fix bars where high < max(o, c, l)."""
        pipe = DataAcquisitionPipeline(storage_dir=tmp_storage)
        # Create a dataframe with bad OHLC
        bad_df = pd.DataFrame({
            "open": [2000, 2001], "high": [1990, 1995],   # bad
            "low": [1995, 1994], "close": [2002, 2003],
            "volume": [100, 200], "spread": [0.2, 0.3],
        }, index=pd.date_range("2024-01-01", periods=2, freq="1min", tz="UTC"))
        bad_df.index.name = "timestamp"
        fixed = pipe._validate_schema(bad_df)
        # High should now be >= max(o, c, l)
        assert (fixed["high"] >= fixed[["open", "close", "low"]].max(axis=1)).all()


# ─── Historical Ingestion Tests ─────────────────────────────────────────────

class TestHistoricalIngestion:
    def test_multi_timeframe_ingestion(self, tmp_storage):
        eng = HistoricalIngestionEngine(storage_dir=tmp_storage)
        results = eng.ingest(
            symbol="XAUUSD", start="2024-01-01", end="2024-01-08",
            timeframes=[Timeframe.M1, Timeframe.H1, Timeframe.D1],
            source=DataSource.SYNTHETIC,
        )
        assert Timeframe.M1 in results
        assert Timeframe.H1 in results
        assert Timeframe.D1 in results
        # M1 should have many more bars than D1
        assert results[Timeframe.M1].bars_new > results[Timeframe.D1].bars_new

    def test_coverage_pct_calculated(self, tmp_storage):
        eng = HistoricalIngestionEngine(storage_dir=tmp_storage)
        results = eng.ingest(
            symbol="XAUUSD", start="2024-01-01", end="2024-01-08",
            timeframes=[Timeframe.H1],
            source=DataSource.SYNTHETIC,
        )
        r = results[Timeframe.H1]
        # Synthetic data should have ~100% coverage
        assert r.coverage_pct >= 95.0
        assert r.bars_new > 0

    def test_idempotent_reingest(self, tmp_storage):
        eng = HistoricalIngestionEngine(storage_dir=tmp_storage)
        # First run
        r1 = eng.ingest(
            symbol="XAUUSD", start="2024-01-01", end="2024-01-03",
            timeframes=[Timeframe.H1],
            source=DataSource.SYNTHETIC,
        )
        first_bars = r1[Timeframe.H1].bars_new
        # Second run same range
        r2 = eng.ingest(
            symbol="XAUUSD", start="2024-01-01", end="2024-01-03",
            timeframes=[Timeframe.H1],
            source=DataSource.SYNTHETIC,
        )
        # All bars should be skipped on second run
        assert r2[Timeframe.H1].bars_new == 0
        assert r2[Timeframe.H1].bars_skipped == first_bars

    def test_aggregate_timeframe(self, tmp_storage):
        eng = HistoricalIngestionEngine(storage_dir=tmp_storage)
        # First ingest M1
        eng.ingest(
            symbol="XAUUSD", start="2024-01-01", end="2024-01-03",
            timeframes=[Timeframe.M1], source=DataSource.SYNTHETIC,
        )
        # Now aggregate to H1
        result = eng.aggregate_timeframe(
            symbol="XAUUSD", source_tf=Timeframe.M1, target_tf=Timeframe.H1,
            start="2024-01-01", end="2024-01-03",
        )
        assert result.bars_new > 0
        assert result.timeframe == Timeframe.H1

    def test_synthetic_generator_with_regimes(self):
        gen = SyntheticDataGenerator(seed=42)
        df = gen.generate_with_regimes("2024-01-01", "2024-01-08",
                                        timeframe=Timeframe.H1)
        assert len(df) > 0
        assert all(c in df.columns for c in ("open", "high", "low", "close"))


# ─── Feature Engine Tests ───────────────────────────────────────────────────

class TestFeatureEngine:
    def test_generate_returns_featureset(self, synthetic_bars):
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        assert isinstance(fs, FeatureSet)
        assert fs.n_features > 0
        assert fs.n_bars > 0
        assert len(fs.feature_names) == fs.n_features
        assert len(fs.target_names) > 0

    def test_feature_groups_present(self, synthetic_bars):
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        for group in ("price", "technical", "volatility", "microstructure",
                       "time", "lag"):
            assert group in fs.feature_groups
            assert len(fs.feature_groups[group]) > 0

    def test_targets_are_multi_horizon(self, synthetic_bars):
        tc = TargetConfig(horizons=[1, 5, 15, 60])
        fe = FeatureEngine(target_config=tc)
        fs = fe.generate(synthetic_bars)
        assert "target_ret_1" in fs.target_names
        assert "target_ret_5" in fs.target_names
        assert "target_ret_15" in fs.target_names
        assert "target_ret_60" in fs.target_names

    def test_features_have_no_nan_after_warmup(self, synthetic_bars):
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        # All features should be non-NaN (we drop warmup rows)
        assert not fs.features.isna().any().any()
        assert not fs.targets.isna().any().any()

    def test_features_count(self, synthetic_bars):
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        # We expect ~50-70 features
        assert 40 < fs.n_features < 100

    def test_config_toggles(self, synthetic_bars):
        """Disabling feature groups reduces feature count."""
        full = FeatureEngine()
        full_fs = full.generate(synthetic_bars)
        # Disable microstructure
        cfg = FeatureConfig(microstructure_features=False, time_features=False)
        partial = FeatureEngine(config=cfg)
        partial_fs = partial.generate(synthetic_bars)
        assert partial_fs.n_features < full_fs.n_features

    def test_log_return_targets(self, synthetic_bars):
        tc = TargetConfig(target_type="log_return", horizons=[1, 5])
        fe = FeatureEngine(target_config=tc)
        fs = fe.generate(synthetic_bars)
        # Targets should be log returns
        assert "target_ret_1" in fs.target_names

    def test_performance_under_5s_for_week_of_M1(self, synthetic_bars):
        """Feature generation for 1 week of M1 should take < 5s."""
        import time
        fe = FeatureEngine()
        t0 = time.perf_counter()
        fs = fe.generate(synthetic_bars)
        elapsed = time.perf_counter() - t0
        assert elapsed < 5.0
        assert fs.n_bars > 0


# ─── Dataset Validator Tests ────────────────────────────────────────────────

class TestDatasetValidator:
    @pytest.fixture
    def valid_featureset(self, synthetic_bars):
        fe = FeatureEngine()
        return fe.generate(synthetic_bars)

    def test_valid_dataset_passes(self, valid_featureset):
        dv = DatasetValidator()
        report = dv.validate(valid_featureset.features, valid_featureset.targets)
        assert report.overall_severity in (ValidationSeverity.PASS, ValidationSeverity.WARN)
        assert report.ready_for_training

    def test_empty_dataset_fails(self):
        dv = DatasetValidator()
        report = dv.validate(pd.DataFrame(), pd.DataFrame())
        assert report.overall_severity == ValidationSeverity.CRITICAL
        assert not report.ready_for_training

    def test_duplicate_index_detected(self, valid_featureset):
        # Duplicate the first row
        feats = pd.concat([valid_featureset.features.iloc[:1], valid_featureset.features])
        targets = pd.concat([valid_featureset.targets.iloc[:1], valid_featureset.targets])
        dv = DatasetValidator()
        report = dv.validate(feats, targets)
        # Should detect duplicates
        dup_check = next(c for c in report.checks if c.check_id == "V03_NO_DUPLICATE_INDEX")
        assert not dup_check.passed

    def test_nan_detected(self, valid_featureset):
        feats = valid_featureset.features.copy()
        feats.iloc[0, 0] = np.nan
        dv = DatasetValidator()
        report = dv.validate(feats, valid_featureset.targets)
        nan_check = next(c for c in report.checks if c.check_id == "V06_NO_NAN_FEATURES")
        assert not nan_check.passed

    def test_inf_detected(self, valid_featureset):
        feats = valid_featureset.features.copy()
        feats.iloc[0, 0] = np.inf
        dv = DatasetValidator()
        report = dv.validate(feats, valid_featureset.targets)
        inf_check = next(c for c in report.checks if c.check_id == "V07_NO_INF_FEATURES")
        assert not inf_check.passed

    def test_zero_variance_detected(self):
        feats = pd.DataFrame({"const": [1.0] * 100, "var": np.random.rand(100)})
        targets = pd.DataFrame({"target": np.random.rand(100)})
        dv = DatasetValidator()
        report = dv.validate(feats, targets)
        zv_check = next(c for c in report.checks if c.check_id == "V08_NO_ZERO_VARIANCE")
        assert not zv_check.passed

    def test_train_test_overlap_detected(self, valid_featureset):
        feats = valid_featureset.features
        # Make train_end and test_start overlap
        train_end = feats.index[60]
        test_start = feats.index[10]  # earlier → overlap
        dv = DatasetValidator()
        report = dv.validate(feats, valid_featureset.targets,
                              train_end=train_end, test_start=test_start)
        overlap_check = next(c for c in report.checks
                              if c.check_id == "V12_NO_TRAIN_TEST_OVERLAP")
        assert not overlap_check.passed
        assert report.overall_severity == ValidationSeverity.CRITICAL

    def test_no_train_test_overlap_passes(self, valid_featureset):
        feats = valid_featureset.features
        # Split in the middle, no overlap
        train_end = feats.index[len(feats) // 2]
        test_start = feats.index[len(feats) // 2 + 1]
        dv = DatasetValidator()
        report = dv.validate(feats, valid_featureset.targets,
                              train_end=train_end, test_start=test_start)
        overlap_check = next(c for c in report.checks
                              if c.check_id == "V12_NO_TRAIN_TEST_OVERLAP")
        assert overlap_check.passed

    def test_report_to_dict(self, valid_featureset):
        dv = DatasetValidator()
        report = dv.validate(valid_featureset.features, valid_featureset.targets)
        d = report.to_dict()
        assert "overall_severity" in d
        assert "score" in d
        assert "checks" in d
        assert "ready_for_training" in d


# ─── Quality Scorer Tests ───────────────────────────────────────────────────

class TestDataQualityScorer:
    def test_perfect_synthetic_data_scores_high(self, synthetic_bars):
        scorer = DataQualityScorer(expected_minutes_per_bar=1)
        score = scorer.score(synthetic_bars,
                              expected_start=pd.Timestamp("2024-01-01", tz="UTC"),
                              expected_end=pd.Timestamp("2024-01-08", tz="UTC"))
        assert score.overall > 80
        assert score.completeness >= 95
        assert score.consistency == 100.0  # synthetic is monotonic, no dups
        assert score.accuracy == 100.0

    def test_grade_scale(self, synthetic_bars):
        scorer = DataQualityScorer(expected_minutes_per_bar=1)
        score = scorer.score(synthetic_bars,
                              expected_start=pd.Timestamp("2024-01-01", tz="UTC"),
                              expected_end=pd.Timestamp("2024-01-08", tz="UTC"))
        # Should be A or A-
        assert score.grade.startswith("A")

    def test_empty_dataset_scores_zero(self):
        scorer = DataQualityScorer()
        score = scorer.score(pd.DataFrame())
        assert score.overall == 0.0
        assert score.grade == "F"

    def test_duplicate_index_lowers_consistency(self, synthetic_bars):
        df = pd.concat([synthetic_bars.iloc[:1], synthetic_bars])
        scorer = DataQualityScorer(expected_minutes_per_bar=1)
        score = scorer.score(df,
                              expected_start=pd.Timestamp("2024-01-01", tz="UTC"),
                              expected_end=pd.Timestamp("2024-01-08", tz="UTC"))
        assert score.consistency < 100.0

    def test_bad_ohlc_lowers_accuracy(self):
        df = pd.DataFrame({
            "open": [2000, 2001], "high": [1990, 1995],
            "low": [1995, 1994], "close": [2002, 2003],
            "volume": [100, 200], "spread": [0.2, 0.3],
        }, index=pd.date_range("2024-01-01", periods=2, freq="1min", tz="UTC"))
        scorer = DataQualityScorer(expected_minutes_per_bar=1)
        score = scorer.score(df)
        assert score.accuracy < 100.0

    def test_nan_lowers_validity(self, synthetic_bars):
        df = synthetic_bars.copy()
        df.iloc[0, 0] = np.nan
        scorer = DataQualityScorer(expected_minutes_per_bar=1)
        score = scorer.score(df,
                              expected_start=pd.Timestamp("2024-01-01", tz="UTC"),
                              expected_end=pd.Timestamp("2024-01-08", tz="UTC"))
        assert score.validity < 100.0

    def test_score_to_dict(self, synthetic_bars):
        scorer = DataQualityScorer(expected_minutes_per_bar=1)
        score = scorer.score(synthetic_bars,
                              expected_start=pd.Timestamp("2024-01-01", tz="UTC"),
                              expected_end=pd.Timestamp("2024-01-08", tz="UTC"))
        d = score.to_dict()
        assert "overall" in d
        assert "completeness" in d
        assert "grade" in d


# ─── Integration ────────────────────────────────────────────────────────────

class TestTrainingPipelineIntegration:
    def test_full_pipeline(self, tmp_storage):
        """End-to-end: acquire → features → validate → score."""
        # 1. Acquire
        pipe = DataAcquisitionPipeline(storage_dir=tmp_storage)
        result = pipe.acquire(
            source=DataSource.SYNTHETIC, symbol="XAUUSD",
            timeframe=Timeframe.M1,
            start="2024-01-01", end="2024-01-08",
        )
        assert result.bars_fetched > 0
        df = pd.read_parquet(result.output_path)

        # 2. Generate features
        fe = FeatureEngine()
        fs = fe.generate(df)
        assert fs.n_features > 0

        # 3. Validate
        dv = DatasetValidator()
        report = dv.validate(fs.features, fs.targets)
        assert report.ready_for_training

        # 4. Quality score
        scorer = DataQualityScorer(expected_minutes_per_bar=1)
        score = scorer.score(df,
                              expected_start=pd.Timestamp("2024-01-01", tz="UTC"),
                              expected_end=pd.Timestamp("2024-01-08", tz="UTC"))
        assert score.overall > 50


# ─── B1: Anchored WFA Mode Tests ──────────────────────────────────────────

class TestAnchoredWFAMode:
    """B1: Verify true anchored expansion (train_start stays at 0)."""

    def test_anchored_train_start_always_zero(self):
        from titan.walk_forward.engine import WalkForwardEngine
        from titan.backtest.engine import (
            generate_synthetic_ticks, generate_synthetic_signals,
        )
        ticks = generate_synthetic_ticks(n_ticks=5000)
        sigs = generate_synthetic_signals(ticks, frequency=100)
        wfa = WalkForwardEngine(train_size=500, test_size=100, step=200)
        result = wfa.run(ticks, sigs, method="anchored")
        assert len(result.folds) > 0
        # B1 fix: every fold's train_start must be 0 (anchored)
        for f in result.folds:
            assert f.train_start == 0, (
                f"Anchored fold {f.fold_num} has train_start={f.train_start} (expected 0)"
            )

    def test_anchored_train_window_grows(self):
        from titan.walk_forward.engine import WalkForwardEngine
        from titan.backtest.engine import (
            generate_synthetic_ticks, generate_synthetic_signals,
        )
        ticks = generate_synthetic_ticks(n_ticks=5000)
        sigs = generate_synthetic_signals(ticks, frequency=100)
        wfa = WalkForwardEngine(train_size=500, test_size=100, step=200)
        result = wfa.run(ticks, sigs, method="anchored")
        # train_end should grow across folds
        train_ends = [f.train_end for f in result.folds]
        assert train_ends == sorted(train_ends), "Train_end should be increasing"
        assert train_ends[-1] > train_ends[0], "Train window should grow"

    def test_rolling_train_window_slides(self):
        from titan.walk_forward.engine import WalkForwardEngine
        from titan.backtest.engine import (
            generate_synthetic_ticks, generate_synthetic_signals,
        )
        ticks = generate_synthetic_ticks(n_ticks=5000)
        sigs = generate_synthetic_signals(ticks, frequency=100)
        wfa = WalkForwardEngine(train_size=500, test_size=100, step=200)
        result = wfa.run(ticks, sigs, method="rolling")
        # Rolling: train_start advances
        train_starts = [f.train_start for f in result.folds]
        assert train_starts[0] == 0
        assert train_starts[-1] > 0

    def test_unknown_method_raises(self):
        from titan.walk_forward.engine import WalkForwardEngine
        from titan.backtest.engine import generate_synthetic_ticks
        ticks = generate_synthetic_ticks(n_ticks=500)
        wfa = WalkForwardEngine(train_size=200, test_size=50, step=50)
        with pytest.raises(ValueError, match="Unknown method"):
            wfa.run(ticks, [], method="invalid")


# ─── B4: Purge / Embargo Tests ────────────────────────────────────────────

class TestPurgeEmbargo:
    """B4: Verify purge gap and embargo in WFA and split function."""

    def test_wfa_purge_gap_applied(self):
        from titan.walk_forward.engine import WalkForwardEngine
        from titan.backtest.engine import (
            generate_synthetic_ticks, generate_synthetic_signals,
        )
        ticks = generate_synthetic_ticks(n_ticks=5000)
        sigs = generate_synthetic_signals(ticks, frequency=100)
        wfa = WalkForwardEngine(train_size=500, test_size=100, step=200, purge=60)
        result = wfa.run(ticks, sigs, method="rolling")
        for f in result.folds:
            gap = f.test_start - f.train_end
            assert gap == 60, f"Fold {f.fold_num} gap={gap} (expected 60)"

    def test_wfa_purge_zero_no_gap(self):
        from titan.walk_forward.engine import WalkForwardEngine
        from titan.backtest.engine import (
            generate_synthetic_ticks, generate_synthetic_signals,
        )
        ticks = generate_synthetic_ticks(n_ticks=5000)
        sigs = generate_synthetic_signals(ticks, frequency=100)
        wfa = WalkForwardEngine(train_size=500, test_size=100, step=200, purge=0)
        result = wfa.run(ticks, sigs, method="rolling")
        for f in result.folds:
            assert f.test_start == f.train_end

    def test_wfa_embargo_advances_cursor(self):
        from titan.walk_forward.engine import WalkForwardEngine
        from titan.backtest.engine import (
            generate_synthetic_ticks, generate_synthetic_signals,
        )
        ticks = generate_synthetic_ticks(n_ticks=5000)
        sigs = generate_synthetic_signals(ticks, frequency=100)
        # With embargo, fewer folds fit; without embargo, more folds
        wfa_no_emb = WalkForwardEngine(train_size=500, test_size=100, step=200, embargo=0)
        wfa_emb = WalkForwardEngine(train_size=500, test_size=100, step=200, embargo=50)
        r_no = wfa_no_emb.run(ticks, sigs, method="rolling")
        r_emb = wfa_emb.run(ticks, sigs, method="rolling")
        assert len(r_emb.folds) <= len(r_no.folds), (
            f"Embargo should reduce folds: emb={len(r_emb.folds)}, no_emb={len(r_no.folds)}"
        )

    def test_time_series_split_basic(self, synthetic_bars):
        from titan.training import FeatureEngine, time_series_train_val_test_split
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        split = time_series_train_val_test_split(
            fs.features, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2, purge=60,
        )
        assert len(split.train) > 0
        assert len(split.val) > 0
        assert len(split.test) > 0
        # Train + val + test should be ≤ total (purge drops bars)
        total_used = len(split.train) + len(split.val) + len(split.test)
        assert total_used <= len(fs.features)

    def test_time_series_split_purge_gap(self, synthetic_bars):
        from titan.training import FeatureEngine, time_series_train_val_test_split
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        split = time_series_train_val_test_split(
            fs.features, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2, purge=60,
        )
        # val_idx[0] should be train_idx[1] + 60
        assert split.val_idx[0] == split.train_idx[1] + 60
        assert split.test_idx[0] == split.val_idx[1] + 60

    def test_time_series_split_no_purge(self, synthetic_bars):
        from titan.training import FeatureEngine, time_series_train_val_test_split
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        split = time_series_train_val_test_split(
            fs.features, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2, purge=0,
        )
        assert split.val_idx[0] == split.train_idx[1]
        assert split.test_idx[0] == split.val_idx[1]

    def test_split_rejects_non_monotonic(self, synthetic_bars):
        from titan.training import FeatureEngine, time_series_train_val_test_split
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        # Shuffle the index
        shuffled = fs.features.sample(frac=1, random_state=42)
        with pytest.raises(ValueError, match="monotonically"):
            time_series_train_val_test_split(shuffled)

    def test_split_rejects_bad_ratios(self, synthetic_bars):
        from titan.training import FeatureEngine, time_series_train_val_test_split
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        with pytest.raises(ValueError, match="sum to 1.0"):
            time_series_train_val_test_split(
                fs.features, train_ratio=0.5, val_ratio=0.3, test_ratio=0.3,
            )

    def test_purged_kfold_basic(self):
        from titan.training import PurgedKFold
        kf = PurgedKFold(n_splits=5, purge=10, embargo=5)
        result = kf.split(n=1000)
        assert result.n_splits == 5
        assert len(result.folds) == 5
        assert result.purge == 10
        assert result.embargo == 5
        # Each fold's train_end should be test_start - purge
        for f in result.folds:
            assert f.train_end == max(0, f.test_start - 10)


# ─── B3: Feature Scaler Tests ─────────────────────────────────────────────

class TestFeatureScalers:
    """B3: StandardScaler and RobustScaler with train-only fit."""

    @pytest.fixture
    def split_data(self, synthetic_bars):
        from titan.training import (
            FeatureEngine, time_series_train_val_test_split,
        )
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        split = time_series_train_val_test_split(
            fs.features, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15, purge=60,
        )
        return split

    def test_standard_scaler_fit_transform_train(self, split_data):
        from titan.training import StandardScaler
        scaler = StandardScaler()
        train_scaled = scaler.fit_transform(split_data.train)
        # Train should have ~0 mean and ~1 std per column
        assert abs(train_scaled.mean().mean()) < 0.01
        assert abs(train_scaled.std().mean() - 1.0) < 0.1

    def test_standard_scaler_transform_only(self, split_data):
        from titan.training import StandardScaler
        scaler = StandardScaler()
        scaler.fit(split_data.train)
        # Transform val (should NOT have mean=0 — that would imply leakage)
        val_scaled = scaler.transform(split_data.val)
        # Val mean is NOT 0 (correct behavior — no leakage)
        assert val_scaled.mean().mean() != 0.0

    def test_standard_scaler_transform_before_fit_raises(self, split_data):
        from titan.training import StandardScaler
        scaler = StandardScaler()
        with pytest.raises(RuntimeError, match="before fit"):
            scaler.transform(split_data.val)

    def test_standard_scaler_clip(self, split_data):
        from titan.training import StandardScaler
        scaler = StandardScaler(clip=3.0)
        train_scaled = scaler.fit_transform(split_data.train)
        # No value should exceed ±3
        assert (train_scaled.abs() <= 3.0).all().all()

    def test_robust_scaler_fit_transform(self, split_data):
        from titan.training import RobustScaler
        scaler = RobustScaler()
        train_scaled = scaler.fit_transform(split_data.train)
        # Median should be ~0
        assert abs(train_scaled.median().median()) < 0.01

    def test_robust_scaler_transform_only(self, split_data):
        from titan.training import RobustScaler
        scaler = RobustScaler()
        scaler.fit(split_data.train)
        val_scaled = scaler.transform(split_data.val)
        # Val median is NOT 0 (no leakage)
        assert val_scaled.median().median() != 0.0

    def test_robust_scaler_transform_before_fit_raises(self, split_data):
        from titan.training import RobustScaler
        scaler = RobustScaler()
        with pytest.raises(RuntimeError, match="before fit"):
            scaler.transform(split_data.val)

    def test_scalers_handle_zero_variance(self):
        from titan.training import StandardScaler, RobustScaler
        df = pd.DataFrame({
            "a": [1.0, 1.0, 1.0, 1.0],   # zero variance
            "b": [1.0, 2.0, 3.0, 4.0],
        })
        ss = StandardScaler()
        out = ss.fit_transform(df)
        # Should not produce NaN/Inf for zero-variance col
        assert not out["a"].isna().any()
        assert not np.isinf(out["a"]).any()


# ─── B5: Feature Selector Tests ───────────────────────────────────────────

class TestFeatureSelector:
    """B5: Drop zero-variance + highly-correlated features."""

    @pytest.fixture
    def split_data(self, synthetic_bars):
        from titan.training import (
            FeatureEngine, time_series_train_val_test_split,
        )
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        return time_series_train_val_test_split(
            fs.features, train_ratio=0.7, val_ratio=0.15, test_ratio=0.15, purge=60,
        )

    def test_drops_zero_variance(self):
        from titan.training import FeatureSelector
        df = pd.DataFrame({
            "const": [1.0] * 100,
            "var": np.random.rand(100),
        })
        sel = FeatureSelector(variance_threshold=1e-10)
        out = sel.fit_transform(df)
        assert "const" not in out.columns
        assert "var" in out.columns
        assert sel.report_.dropped_zero_variance == ["const"]

    def test_drops_high_correlation(self):
        from titan.training import FeatureSelector
        # x and y are perfectly correlated
        x = np.random.rand(100)
        df = pd.DataFrame({"x": x, "y": x * 2 + 1, "z": np.random.rand(100)})
        sel = FeatureSelector(correlation_threshold=0.95)
        out = sel.fit_transform(df)
        # Exactly one of x/y should be dropped
        assert ("x" in out.columns) ^ ("y" in out.columns), (
            f"Expected one of x/y dropped; kept: {out.columns.tolist()}"
        )
        assert "z" in out.columns

    def test_keeps_higher_variance_partner(self):
        from titan.training import FeatureSelector
        # x has higher variance than y; both are perfectly correlated
        x = np.random.rand(100) * 100  # large variance
        df = pd.DataFrame({"x": x, "y": x + 1})  # y has tiny variance
        sel = FeatureSelector(correlation_threshold=0.95)
        out = sel.fit_transform(df)
        # x has higher variance → keep x, drop y
        assert "x" in out.columns
        assert "y" not in out.columns

    def test_no_high_corr_in_output(self, split_data):
        from titan.training import FeatureSelector
        sel = FeatureSelector(variance_threshold=1e-10, correlation_threshold=0.95)
        train_sel = sel.fit_transform(split_data.train)
        if train_sel.shape[1] > 1:
            corr = train_sel.corr().abs()
            np.fill_diagonal(corr.values, 0)
            max_corr = corr.max().max()
            assert max_corr < 0.95, f"Max |r|={max_corr} ≥ 0.95"

    def test_transform_uses_kept_features(self, split_data):
        from titan.training import FeatureSelector
        sel = FeatureSelector(correlation_threshold=0.95)
        sel.fit(split_data.train)
        val_sel = sel.transform(split_data.val)
        # Val columns should match train kept features
        assert list(val_sel.columns) == sel.kept_features_

    def test_transform_before_fit_raises(self, split_data):
        from titan.training import FeatureSelector
        sel = FeatureSelector()
        with pytest.raises(RuntimeError, match="before fit"):
            sel.transform(split_data.val)

    def test_report_to_dict(self, split_data):
        from titan.training import FeatureSelector
        sel = FeatureSelector()
        sel.fit(split_data.train)
        d = sel.report_.to_dict()
        assert "n_input" in d
        assert "n_output" in d
        assert "dropped_zero_variance" in d
        assert "dropped_high_correlation" in d
        assert "high_correlation_pairs" in d
        assert d["n_input"] == 61
        assert d["n_output"] < d["n_input"]

    def test_reduces_feature_count(self, split_data):
        from titan.training import FeatureSelector
        sel = FeatureSelector()
        train_sel = sel.fit_transform(split_data.train)
        # Should drop at least the known redundant features
        assert train_sel.shape[1] < split_data.train.shape[1]
        # Known redundancies: logret_1, logret_5, bb_lower or bb_upper, macd_signal
        # At least 4 features should be dropped
        n_dropped = split_data.train.shape[1] - train_sel.shape[1]
        assert n_dropped >= 4, f"Only dropped {n_dropped} features"


# ─── B2: HPO Tests ────────────────────────────────────────────────────────

class TestHyperparameterOptimizer:
    """B2: Optuna-based HPO with purged k-fold CV."""

    def test_xgboost_hpo_returns_result(self):
        from titan.ai.ensemble_voter import HyperparameterOptimizer
        np.random.seed(42)
        X = np.random.randn(300, 5)
        y = np.random.choice([0, 1, 2], size=300)
        hpo = HyperparameterOptimizer(n_trials=2, purge=10, n_splits=2)
        result = hpo.optimize_xgboost(X, y)
        assert result.model_type == "xgboost"
        assert result.n_trials == 2
        assert "max_depth" in result.best_params
        assert "learning_rate" in result.best_params
        assert 0.0 <= result.best_score <= 1.0

    def test_lstm_hpo_returns_result(self):
        from titan.ai.ensemble_voter import HyperparameterOptimizer
        np.random.seed(42)
        X = np.random.randn(300, 5)
        y = np.random.choice([0, 1, 2], size=300)
        hpo = HyperparameterOptimizer(n_trials=2, purge=10, n_splits=2)
        result = hpo.optimize_lstm(X, y)
        assert result.model_type == "lstm"
        assert "hidden_size" in result.best_params
        assert "learning_rate" in result.best_params

    def test_transformer_hpo_returns_result(self):
        from titan.ai.ensemble_voter import HyperparameterOptimizer
        np.random.seed(42)
        X = np.random.randn(300, 5)
        y = np.random.choice([0, 1, 2], size=300)
        hpo = HyperparameterOptimizer(n_trials=2, purge=10, n_splits=2)
        result = hpo.optimize_transformer(X, y)
        assert result.model_type == "transformer"
        assert "num_heads" in result.best_params

    def test_hpo_too_few_samples_raises(self):
        from titan.ai.ensemble_voter import HyperparameterOptimizer
        X = np.random.randn(50, 5)
        y = np.random.choice([0, 1, 2], size=50)
        hpo = HyperparameterOptimizer(n_trials=2)
        with pytest.raises(ValueError, match="Too few"):
            hpo.optimize_xgboost(X, y)

    def test_hpo_result_to_dict(self):
        from titan.ai.ensemble_voter import HyperparameterOptimizer
        X = np.random.randn(200, 5)
        y = np.random.choice([0, 1, 2], size=200)
        hpo = HyperparameterOptimizer(n_trials=2, purge=10, n_splits=2)
        result = hpo.optimize_xgboost(X, y)
        d = result.to_dict()
        assert "best_params" in d
        assert "best_score" in d
        assert "n_trials" in d
        assert "trials" in d

    def test_hpo_with_sqlite_storage(self, tmp_path):
        from titan.ai.ensemble_voter import HyperparameterOptimizer
        X = np.random.randn(200, 5)
        y = np.random.choice([0, 1, 2], size=200)
        storage = f"sqlite:///{tmp_path}/hpo_test.db"
        hpo = HyperparameterOptimizer(n_trials=2, purge=10, n_splits=2,
                                       storage_path=storage)
        r1 = hpo.optimize_xgboost(X, y)
        assert r1.storage_path == storage
        # Re-run with same storage → should load existing study
        hpo2 = HyperparameterOptimizer(n_trials=1, purge=10, n_splits=2,
                                        storage_path=storage)
        r2 = hpo2.optimize_xgboost(X, y)
        assert r2.n_trials >= 1

    def test_hpo_reproducible_with_seed(self):
        from titan.ai.ensemble_voter import HyperparameterOptimizer
        np.random.seed(42)
        X = np.random.randn(200, 5)
        y = np.random.choice([0, 1, 2], size=200)
        hpo1 = HyperparameterOptimizer(n_trials=3, purge=10, n_splits=2, seed=42)
        hpo2 = HyperparameterOptimizer(n_trials=3, purge=10, n_splits=2, seed=42)
        r1 = hpo1.optimize_xgboost(X, y)
        r2 = hpo2.optimize_xgboost(X, y)
        # Same seed → same best params (TPESampler is deterministic)
        assert r1.best_params == r2.best_params


# ─── B1-B5 Integration: full remediated pipeline ─────────────────────────

class TestRemediatedPipeline:
    """End-to-end: acquire → features → split → scale → select → HPO."""

    def test_full_remediated_pipeline(self, synthetic_bars):
        from titan.training import (
            FeatureEngine, time_series_train_val_test_split,
            StandardScaler, FeatureSelector,
        )
        # 1. Features
        fe = FeatureEngine()
        fs = fe.generate(synthetic_bars)
        # 2. Split with purge gap = max(target horizons) = 60
        split = time_series_train_val_test_split(
            fs.features, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2,
            purge=60,
        )
        # 3. Scale (fit on train only)
        scaler = StandardScaler(clip=5.0)
        train_scaled = scaler.fit_transform(split.train)
        val_scaled = scaler.transform(split.val)
        test_scaled = scaler.transform(split.test)
        # 4. Select (fit on train only)
        selector = FeatureSelector(variance_threshold=1e-10, correlation_threshold=0.95)
        train_selected = selector.fit_transform(train_scaled)
        val_selected = selector.transform(val_scaled)
        test_selected = selector.transform(test_scaled)
        # All splits should have the same columns
        assert list(train_selected.columns) == list(val_selected.columns)
        assert list(train_selected.columns) == list(test_selected.columns)
        # No high-correlation pairs
        if train_selected.shape[1] > 1:
            corr = train_selected.corr().abs()
            np.fill_diagonal(corr.values, 0)
            assert corr.max().max() < 0.95
        # No zero-variance features
        assert (train_selected.var() > 0).all()
