"""
Preprocessing Pipeline (Orchestrator)
=======================================
End-to-end pipeline that processes 4 broker datasets into 1 unified
canonical dataset ready for feature engineering + model training.

Pipeline steps:
  1. Load broker data (parquet files from titan/data/sources/mt5_brokers/)
  2. Schema unification (4 brokers → canonical schema)
  3. Spread normalization (points → USD)
  4. Deduplication (per broker)
  5. Gap filling (per broker, intra-session only)
  6. Cross-broker outlier detection + imputation
  7. Canonical merge (4 brokers → 1 unified dataset)
  8. Regime tagging (TREND_UP/DOWN/RANGE/VOLATILE)
  9. Save canonical dataset (parquet)

Usage:
    pipeline = PreprocessingPipeline(timeframe="H1")
    canonical = pipeline.run()
    # canonical is ready for feature_engine.py
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from .schema_unifier import SchemaUnifier
from .spread_normalizer import SpreadNormalizer
from .outlier_detector import CrossBrokerOutlierDetector
from .gap_filler import GapFiller
from .deduplicator import Deduplicator
from .regime_tagger import RegimeTagger
from .canonical_merger import CanonicalMerger

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# Default paths
PROJECT_ROOT = Path("/home/z/my-project")
DEFAULT_INPUT_DIR = PROJECT_ROOT / "titan" / "data" / "sources" / "mt5_brokers"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "titan" / "data" / "canonical"

DEFAULT_BROKERS = ["exness", "fundednext", "fbs", "icmarkets"]


class PreprocessingPipeline:
    """End-to-end preprocessing orchestrator."""

    def __init__(self,
                 timeframe: str = "H1",
                 input_dir: Path = None,
                 output_dir: Path = None,
                 brokers: list = None):
        self.timeframe = timeframe
        self.input_dir = input_dir or DEFAULT_INPUT_DIR
        self.output_dir = output_dir or DEFAULT_OUTPUT_DIR
        self.brokers = brokers or DEFAULT_BROKERS

        # Initialize components
        self.schema_unifier = SchemaUnifier()
        self.spread_normalizer = SpreadNormalizer()
        self.deduplicator = Deduplicator()
        self.gap_filler = GapFiller(timeframe=timeframe)
        self.outlier_detector = CrossBrokerOutlierDetector(threshold_pct=0.5)
        self.regime_tagger = RegimeTagger()
        self.canonical_merger = CanonicalMerger(min_brokers=2)

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_broker_data(self) -> Dict[str, pd.DataFrame]:
        """Load raw parquet for each broker."""
        logger.info("=" * 70)
        logger.info(f"STEP 1: Loading {self.timeframe} data for {len(self.brokers)} brokers")
        logger.info("=" * 70)

        broker_data = {}
        for broker in self.brokers:
            path = self.input_dir / broker / f"XAUUSD_{self.timeframe}.parquet"
            if not path.exists():
                logger.warning(f"  {broker}: MISSING {path}")
                continue
            df = pd.read_parquet(path)
            unified = self.schema_unifier.unify(df, broker)
            broker_data[broker] = unified
            logger.info(f"  {broker}: {len(unified):,} bars loaded")
        return broker_data

    def normalize_spreads(self, broker_data: Dict[str, pd.DataFrame]
                          ) -> Dict[str, pd.DataFrame]:
        """Add spread_usd column to each broker."""
        logger.info("")
        logger.info("=" * 70)
        logger.info("STEP 2: Spread normalization (points → USD)")
        logger.info("=" * 70)
        return self.spread_normalizer.normalize_all(broker_data)

    def deduplicate(self, broker_data: Dict[str, pd.DataFrame]
                    ) -> Dict[str, pd.DataFrame]:
        """Remove duplicate timestamps per broker."""
        logger.info("")
        logger.info("=" * 70)
        logger.info("STEP 3: Deduplication (per broker)")
        logger.info("=" * 70)
        return {b: self.deduplicator.deduplicate(df) for b, df in broker_data.items()}

    def fill_gaps(self, broker_data: Dict[str, pd.DataFrame]
                  ) -> Dict[str, pd.DataFrame]:
        """Fill intra-session gaps per broker."""
        logger.info("")
        logger.info("=" * 70)
        logger.info("STEP 4: Gap filling (intra-session only)")
        logger.info("=" * 70)
        return {b: self.gap_filler.fill_gaps(df) for b, df in broker_data.items()}

    def detect_outliers(self, broker_data: Dict[str, pd.DataFrame]
                        ) -> Dict[str, pd.DataFrame]:
        """Detect + impute cross-broker outliers."""
        logger.info("")
        logger.info("=" * 70)
        logger.info("STEP 5: Cross-broker outlier detection (threshold: 0.5%)")
        logger.info("=" * 70)
        cleaned, reports = self.outlier_detector.detect(broker_data, column="close")
        if reports:
            for r in reports:
                logger.info(f"  {r['broker']}: {r['outliers_detected']} outliers imputed")
        else:
            logger.info("  No outliers detected — all brokers consistent")
        return cleaned

    def merge_brokers(self, broker_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Merge 4 brokers → 1 canonical dataset."""
        logger.info("")
        logger.info("=" * 70)
        logger.info("STEP 6: Canonical merge (4 brokers → 1 unified dataset)")
        logger.info("=" * 70)
        return self.canonical_merger.merge(broker_data)

    def tag_regimes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add regime classification column."""
        logger.info("")
        logger.info("=" * 70)
        logger.info("STEP 7: Regime tagging (TREND_UP/DOWN/RANGE/VOLATILE)")
        logger.info("=" * 70)
        return self.regime_tagger.tag(df)

    def save_canonical(self, df: pd.DataFrame) -> Path:
        """Save canonical dataset to parquet."""
        out_path = self.output_dir / f"XAUUSD_{self.timeframe}_canonical.parquet"
        df.to_parquet(out_path, compression="snappy")
        size_mb = out_path.stat().st_size / (1024 * 1024)
        logger.info("")
        logger.info(f"  Saved: {out_path}")
        logger.info(f"  Size: {size_mb:.2f} MB ({len(df):,} bars)")
        return out_path

    def run(self) -> pd.DataFrame:
        """Execute full preprocessing pipeline."""
        # Step 1: Load
        broker_data = self.load_broker_data()
        if not broker_data:
            raise RuntimeError("No broker data loaded — check input paths")

        # Step 2: Normalize spreads
        broker_data = self.normalize_spreads(broker_data)

        # Step 3: Deduplicate
        broker_data = self.deduplicate(broker_data)

        # Step 4: Fill gaps (per broker, BEFORE merging)
        # NOTE: We fill gaps AFTER merging to avoid creating fake bars
        # where multiple brokers had no data. So we skip this step here.
        # broker_data = self.fill_gaps(broker_data)

        # Step 5: Detect outliers
        broker_data = self.detect_outliers(broker_data)

        # Step 6: Merge
        canonical = self.merge_brokers(broker_data)

        # Step 7: Regime tagging
        canonical = self.tag_regimes(canonical)

        # Step 8: Save
        out_path = self.save_canonical(canonical)

        logger.info("")
        logger.info("=" * 70)
        logger.info(f"  PREPROCESSING COMPLETE")
        logger.info("=" * 70)
        logger.info(f"  Output: {out_path}")
        logger.info(f"  Bars: {len(canonical):,}")
        logger.info(f"  Columns: {list(canonical.columns)}")
        logger.info(f"  Date range: {canonical.index[0]} → {canonical.index[-1]}")

        return canonical


if __name__ == "__main__":
    import sys
    timeframe = sys.argv[1] if len(sys.argv) > 1 else "H1"
    pipeline = PreprocessingPipeline(timeframe=timeframe)
    canonical = pipeline.run()
    print(f"\nCanonical dataset shape: {canonical.shape}")
    print(f"\nFirst 5 rows:")
    print(canonical.head())
    print(f"\nLast 5 rows:")
    print(canonical.tail())
