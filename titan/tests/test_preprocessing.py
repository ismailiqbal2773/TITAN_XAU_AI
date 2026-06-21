"""
TITAN Preprocessing Test Suite
================================
Validates every transformation preserves data integrity.
"""
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT))

from titan.preprocessing import (
    SchemaUnifier, SpreadNormalizer, CrossBrokerOutlierDetector,
    GapFiller, Deduplicator, RegimeTagger, ClassBalancer, CanonicalMerger,
    PreprocessingPipeline,
)


# Fixtures
@pytest.fixture
def sample_broker_data():
    """Sample data mimicking 2 brokers."""
    idx = pd.date_range("2024-01-01", periods=100, freq="1h", tz="UTC")
    return {
        "exness": pd.DataFrame({
            "open": np.random.uniform(2000, 2050, 100),
            "high": np.random.uniform(2050, 2070, 100),
            "low": np.random.uniform(1990, 2000, 100),
            "close": np.random.uniform(2000, 2050, 100),
            "tick_volume": np.random.randint(100, 1000, 100),
            "spread": np.random.randint(30, 100, 100),
            "real_volume": np.random.randint(0, 50, 100),
        }, index=idx),
        "icmarkets": pd.DataFrame({
            "open": np.random.uniform(2000, 2050, 100),
            "high": np.random.uniform(2050, 2070, 100),
            "low": np.random.uniform(1990, 2000, 100),
            "close": np.random.uniform(2000, 2050, 100),
            "tick_volume": np.random.randint(100, 1000, 100),
            "spread": np.random.randint(2, 20, 100),
            "real_volume": np.random.randint(0, 50, 100),
        }, index=idx),
    }


# ====== SchemaUnifier Tests ======

def test_schema_unifier_creates_broker_column(sample_broker_data):
    su = SchemaUnifier()
    out = su.unify(sample_broker_data["exness"], "exness")
    assert "broker" in out.columns
    assert (out["broker"] == "exness").all()


def test_schema_unifier_renames_spread_to_spread_points(sample_broker_data):
    su = SchemaUnifier()
    out = su.unify(sample_broker_data["exness"], "exness")
    assert "spread_points" in out.columns
    assert "spread" not in out.columns


def test_schema_unifier_preserves_row_count(sample_broker_data):
    su = SchemaUnifier()
    out = su.unify(sample_broker_data["exness"], "exness")
    assert len(out) == len(sample_broker_data["exness"])


# ====== SpreadNormalizer Tests ======

def test_spread_normalizer_exness():
    """Exness: digits=3, point=0.001 → spread_usd = pts × 0.001"""
    df = pd.DataFrame({"spread_points": [100, 200, 300]})
    sn = SpreadNormalizer()
    out = sn.normalize(df.assign(broker="exness"), "exness")
    assert out["spread_usd"].iloc[0] == pytest.approx(0.10)
    assert out["spread_usd"].iloc[1] == pytest.approx(0.20)
    assert out["spread_usd"].iloc[2] == pytest.approx(0.30)


def test_spread_normalizer_icmarkets():
    """IC Markets: digits=2, point=0.01 → spread_usd = pts × 0.01"""
    df = pd.DataFrame({"spread_points": [10, 20, 30]})
    sn = SpreadNormalizer()
    out = sn.normalize(df.assign(broker="icmarkets"), "icmarkets")
    assert out["spread_usd"].iloc[0] == pytest.approx(0.10)
    assert out["spread_usd"].iloc[1] == pytest.approx(0.20)
    assert out["spread_usd"].iloc[2] == pytest.approx(0.30)


def test_spread_normalizer_makes_brokers_comparable():
    """After normalization, 1 USD spread should be ~equal across brokers."""
    sn = SpreadNormalizer()
    exness_df = sn.normalize(
        pd.DataFrame({"spread_points": [100]}).assign(broker="exness"), "exness"
    )
    icm_df = sn.normalize(
        pd.DataFrame({"spread_points": [10]}).assign(broker="icmarkets"), "icmarkets"
    )
    # 100 pts × 0.001 = $0.10
    # 10 pts × 0.01 = $0.10
    assert exness_df["spread_usd"].iloc[0] == pytest.approx(icm_df["spread_usd"].iloc[0])


# ====== CrossBrokerOutlierDetector Tests ======

def test_outlier_detector_finds_no_outliers_when_consistent():
    """When all brokers agree, no outliers detected."""
    idx = pd.date_range("2024-01-01", periods=50, freq="1h", tz="UTC")
    broker_data = {
        "exness": pd.DataFrame({"close": [2000.0]*50}, index=idx),
        "icmarkets": pd.DataFrame({"close": [2000.0]*50}, index=idx),
    }
    det = CrossBrokerOutlierDetector(threshold_pct=0.5)
    cleaned, reports = det.detect(broker_data, column="close")
    assert len(reports) == 0


def test_outlier_detector_imputes_with_median():
    """Outlier is replaced with median."""
    idx = pd.date_range("2024-01-01", periods=10, freq="1h", tz="UTC")
    broker_data = {
        "exness": pd.DataFrame({
            "close": [2000, 2000, 2000, 5000, 2000, 2000, 2000, 2000, 2000, 2000]
        }, index=idx),
        "icmarkets": pd.DataFrame({"close": [2000]*10}, index=idx),
        "fundednext": pd.DataFrame({"close": [2000]*10}, index=idx),
    }
    det = CrossBrokerOutlierDetector(threshold_pct=0.5)
    cleaned, reports = det.detect(broker_data, column="close")
    assert len(reports) == 1
    # The 5000 outlier should now be replaced with median (2000)
    assert cleaned["exness"]["close"].iloc[3] == pytest.approx(2000.0)


# ====== Deduplicator Tests ======

def test_deduplicator_removes_duplicates():
    idx = pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02"]).tz_localize("UTC")
    df = pd.DataFrame({"close": [100, 200, 300]}, index=idx)
    dedup = Deduplicator(keep="last")
    out = dedup.deduplicate(df)
    assert len(out) == 2
    assert out["close"].iloc[0] == 200  # kept last


def test_deduplicator_no_op_when_no_duplicates():
    idx = pd.to_datetime(["2024-01-01", "2024-01-02"]).tz_localize("UTC")
    df = pd.DataFrame({"close": [100, 200]}, index=idx)
    dedup = Deduplicator()
    out = dedup.deduplicate(df)
    assert len(out) == 2


# ====== RegimeTagger Tests ======

def test_regime_tagger_adds_regime_column():
    idx = pd.date_range("2024-01-01", periods=300, freq="1h", tz="UTC")
    df = pd.DataFrame({"close": np.linspace(2000, 2100, 300)}, index=idx)
    tagger = RegimeTagger()
    out = tagger.tag(df)
    assert "regime" in out.columns
    assert set(out["regime"].unique()).issubset(
        {"TREND_UP", "TREND_DOWN", "RANGE", "VOLATILE", "UNKNOWN"}
    )


def test_regime_tagger_uptrend_detected():
    """Strong uptrend should be classified as TREND_UP."""
    idx = pd.date_range("2024-01-01", periods=500, freq="1h", tz="UTC")
    # Strong linear uptrend
    df = pd.DataFrame({"close": np.linspace(2000, 2500, 500)}, index=idx)
    tagger = RegimeTagger()
    out = tagger.tag(df)
    # Last 100 bars should be TREND_UP
    last_regimes = out["regime"].iloc[-100:]
    assert (last_regimes == "TREND_UP").sum() > 50


# ====== ClassBalancer Tests ======

def test_class_balancer_creates_balanced_classes():
    """After balancing, all classes should have equal counts."""
    np.random.seed(42)
    n = 1000
    labels = pd.Series(
        np.random.choice(["UP", "DOWN", "FLAT"], n, p=[0.6, 0.3, 0.1]),
        index=pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC"),
    )
    df = pd.DataFrame({
        "feature1": np.random.rand(n),
        "feature2": np.random.rand(n),
    }, index=labels.index)

    balancer = ClassBalancer()
    balanced_df, balanced_labels = balancer.balance(df, labels)

    counts = balanced_labels.value_counts()
    assert counts.min() == counts.max()  # All equal
    assert counts.min() == 100  # 10% of 1000 = 100


def test_class_balancer_labels_direction():
    df = pd.DataFrame({"close": [100, 101, 102, 101, 100, 103]})
    balancer = ClassBalancer(flat_threshold_pct=0.5)
    labels = balancer.label_direction(df, horizon=1)
    # Bar 0→1: 100→101 = +1% > 0.5% → UP
    assert labels.iloc[0] == "UP"
    # Bar 2→3: 102→101 = -0.98% < -0.5% → DOWN
    assert labels.iloc[2] == "DOWN"
    # Last bar has no future → None
    assert pd.isna(labels.iloc[-1])


# ====== CanonicalMerger Tests ======

def test_canonical_merger_combines_brokers():
    """Merger should combine 2 brokers into 1."""
    idx = pd.date_range("2024-01-01", periods=50, freq="1h", tz="UTC")
    broker_data = {
        "exness": pd.DataFrame({
            "open": [2000.0]*50, "high": [2010.0]*50, "low": [1990.0]*50,
            "close": [2000.0]*50, "tick_volume": [100]*50,
            "spread_usd": [0.05]*50, "real_volume": [10]*50,
            "broker": ["exness"]*50,
        }, index=idx),
        "icmarkets": pd.DataFrame({
            "open": [2001.0]*50, "high": [2011.0]*50, "low": [1991.0]*50,
            "close": [2001.0]*50, "tick_volume": [200]*50,
            "spread_usd": [0.03]*50, "real_volume": [20]*50,
            "broker": ["icmarkets"]*50,
        }, index=idx),
    }
    merger = CanonicalMerger(min_brokers=2)
    merged = merger.merge(broker_data)
    assert len(merged) == 50
    assert merged["n_brokers"].iloc[0] == 2
    # Close should be median of [2000, 2001] = 2000.5
    assert merged["close"].iloc[0] == pytest.approx(2000.5)
    # High should be max(2010, 2011) = 2011
    assert merged["high"].iloc[0] == pytest.approx(2011.0)
    # Low should be min(1990, 1991) = 1990
    assert merged["low"].iloc[0] == pytest.approx(1990.0)
    # Volume should be sum(100, 200) = 300
    assert merged["tick_volume"].iloc[0] == 300


def test_canonical_merger_filters_single_broker_timestamps():
    """Timestamps with only 1 broker should be dropped."""
    idx1 = pd.date_range("2024-01-01", periods=10, freq="1h", tz="UTC")
    idx2 = pd.date_range("2024-01-01 05:00", periods=10, freq="1h", tz="UTC")  # offset
    broker_data = {
        "exness": pd.DataFrame({
            "open": [2000.0]*10, "high": [2010.0]*10, "low": [1990.0]*10,
            "close": [2000.0]*10, "tick_volume": [100]*10,
            "spread_usd": [0.05]*10, "real_volume": [10]*10,
            "broker": ["exness"]*10,
        }, index=idx1),
        "icmarkets": pd.DataFrame({
            "open": [2001.0]*10, "high": [2011.0]*10, "low": [1991.0]*10,
            "close": [2001.0]*10, "tick_volume": [200]*10,
            "spread_usd": [0.03]*10, "real_volume": [20]*10,
            "broker": ["icmarkets"]*10,
        }, index=idx2),
    }
    merger = CanonicalMerger(min_brokers=2)
    merged = merger.merge(broker_data)
    # Overlap: 5 timestamps (idx1[5:] = idx2[:5])
    # All merged bars should have n_brokers == 2
    assert (merged["n_brokers"] >= 2).all()
    assert len(merged) == 5  # Only overlapping timestamps


# ====== Pipeline Integration Test ======

def test_pipeline_runs_without_error(tmp_path):
    """Pipeline should run end-to-end on synthetic data."""
    # Create temp broker data
    for broker in ["exness", "icmarkets"]:
        broker_dir = tmp_path / broker
        broker_dir.mkdir()
        idx = pd.date_range("2024-01-01", periods=500, freq="1h", tz="UTC")
        df = pd.DataFrame({
            "open": np.random.uniform(2000, 2050, 500),
            "high": np.random.uniform(2050, 2070, 500),
            "low": np.random.uniform(1990, 2000, 500),
            "close": np.random.uniform(2000, 2050, 500),
            "tick_volume": np.random.randint(100, 1000, 500),
            "spread": np.random.randint(10, 50, 500),
            "real_volume": np.random.randint(0, 50, 500),
        }, index=idx)
        df.to_parquet(broker_dir / "XAUUSD_H1.parquet")

    pipeline = PreprocessingPipeline(
        timeframe="H1",
        input_dir=tmp_path,
        output_dir=tmp_path / "canonical",
        brokers=["exness", "icmarkets"],
    )
    canonical = pipeline.run()
    assert len(canonical) > 0
    assert "regime" in canonical.columns
    assert "spread_usd" in canonical.columns
    assert "n_brokers" in canonical.columns
    assert canonical["n_brokers"].min() >= 2
