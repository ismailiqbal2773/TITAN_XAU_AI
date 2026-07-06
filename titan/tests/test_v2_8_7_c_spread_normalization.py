"""TITAN XAU AI - Sprint v2.8.7-C Spread Normalization Tests

Verifies that:
  - canonical spread_usd is NOT double-converted
  - broker spread points are converted to USD
  - MT5 spread points (simulated) are converted to USD
  - spread_normalized flag exists after normalization
  - spread_pct distribution is not 100x inflated post-normalization
  - no order_send / token / trade in source
  - production_ready remains False in parameter discovery

NEVER sends orders. NEVER creates tokens. NEVER trades.
"""
from __future__ import annotations
import sys, re, os
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

OUTPUT_DIR = REPO_ROOT / "data" / "reports" / "parameter_discovery"


class TestSpreadNormalizationUtility:
    def test_canonical_spread_usd_not_double_converted(self):
        """spread_usd column must be used as-is - never multiplied again."""
        import pandas as pd
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd

        df = pd.DataFrame({
            "open": [2000.0, 2010.0],
            "high": [2010.0, 2020.0],
            "low":  [1990.0, 2000.0],
            "close":[2005.0, 2015.0],
            "spread_usd": [0.10, 0.20],
        })
        out = normalize_xauusd_spread_to_usd(df.copy(), symbol="XAUUSD", source="canonical")
        assert out["spread_usd"].iloc[0] == 0.10
        assert out["spread_usd"].iloc[1] == 0.20
        assert out["spread_unit_detected"].iloc[0] == "USD"

    def test_broker_spread_points_converted_to_usd(self):
        """Median(spread) > 2.0 must trigger POINTS -> USD conversion (x0.01)."""
        import pandas as pd
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd

        df = pd.DataFrame({
            "open": [2000.0]*5,
            "high": [2010.0]*5,
            "low":  [1990.0]*5,
            "close":[2005.0]*5,
            "spread": [20.0]*5,
        })
        out = normalize_xauusd_spread_to_usd(df.copy(), symbol="XAUUSD", source="broker")
        assert out["spread_unit_detected"].iloc[0] == "POINTS_CONVERTED"
        assert out["spread_usd"].iloc[0] == pytest.approx(0.20, abs=1e-9)
        assert out["spread"].iloc[0] == pytest.approx(0.20, abs=1e-9)

    def test_broker_spread_small_treated_as_usd(self):
        """Median(spread) <= 2.0 must be treated as already USD."""
        import pandas as pd
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd

        df = pd.DataFrame({
            "open": [2000.0]*5,
            "high": [2010.0]*5,
            "low":  [1990.0]*5,
            "close":[2005.0]*5,
            "spread": [0.10, 0.15, 0.20, 0.25, 0.30],
        })
        out = normalize_xauusd_spread_to_usd(df.copy(), symbol="XAUUSD", source="broker_small")
        assert out["spread_unit_detected"].iloc[0] == "USD"
        assert out["spread_usd"].iloc[0] == pytest.approx(0.10, abs=1e-9)

    def test_mt5_spread_points_converted(self):
        """Simulated MT5 integer points spread must be converted via 0.01."""
        import pandas as pd
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd

        df = pd.DataFrame({
            "open": [2000.0]*10,
            "high": [2010.0]*10,
            "low":  [1990.0]*10,
            "close":[2005.0]*10,
            "spread": [15, 18, 20, 22, 25, 27, 30, 32, 35, 40],
        })
        out = normalize_xauusd_spread_to_usd(df.copy(), symbol="XAUUSD", source="mt5_live")
        assert out["spread_unit_detected"].iloc[0] == "POINTS_CONVERTED"
        assert out["spread_usd"].iloc[0] == pytest.approx(0.15, abs=1e-9)
        assert out["spread_usd"].iloc[-1] == pytest.approx(0.40, abs=1e-9)

    def test_missing_spread_defaults_to_zero(self):
        """No spread column at all -> default 0.0, MISSING_DEFAULT_ZERO."""
        import pandas as pd
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd

        df = pd.DataFrame({
            "open": [2000.0],
            "high": [2010.0],
            "low":  [1990.0],
            "close":[2005.0],
        })
        out = normalize_xauusd_spread_to_usd(df.copy(), symbol="XAUUSD", source="missing")
        assert out["spread_unit_detected"].iloc[0] == "MISSING_DEFAULT_ZERO"
        assert out["spread_usd"].iloc[0] == 0.0
        assert out["spread"].iloc[0] == 0.0

    def test_spread_normalized_flag_exists(self):
        """spread_normalized=True must be set on output DataFrame."""
        import pandas as pd
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd

        df = pd.DataFrame({
            "open": [2000.0],
            "high": [2010.0],
            "low":  [1990.0],
            "close":[2005.0],
            "spread": [10.0],
        })
        out = normalize_xauusd_spread_to_usd(df.copy(), symbol="XAUUSD", source="flag_test")
        assert "spread_normalized" in out.columns
        assert bool(out["spread_normalized"].iloc[0]) is True

    def test_original_spread_preserved(self):
        """original_spread column must preserve raw input values."""
        import pandas as pd
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd

        df = pd.DataFrame({
            "open": [2000.0, 2005.0],
            "high": [2010.0, 2015.0],
            "low":  [1990.0, 1995.0],
            "close":[2005.0, 2010.0],
            "spread": [25.0, 30.0],
        })
        out = normalize_xauusd_spread_to_usd(df.copy(), symbol="XAUUSD", source="preserve_test")
        assert "original_spread" in out.columns
        assert out["original_spread"].iloc[0] == 25.0
        assert out["original_spread"].iloc[1] == 30.0
        assert out["spread_usd"].iloc[0] == pytest.approx(0.25, abs=1e-9)

    def test_non_xauusd_symbol_raises(self):
        """Non-XAUUSD symbols must raise NotImplementedError."""
        import pandas as pd
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd

        df = pd.DataFrame({"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0]})
        with pytest.raises(NotImplementedError):
            normalize_xauusd_spread_to_usd(df, symbol="EURUSD", source="other")


class TestH1FeatureStreamSpreadIntegration:
    def test_load_canonical_does_not_double_convert(self):
        """load_canonical must NOT inflate spread_usd (already USD)."""
        from titan.production.feature_stream import H1FeatureStream

        fs = H1FeatureStream()
        n = fs.load_canonical()
        assert n > 0
        median_spread = float(fs._bars["spread"].median())
        assert 0.01 <= median_spread <= 1.0, (
            f"canonical spread median {median_spread} looks wrong - "
            f"double conversion suspected"
        )

    def test_push_bars_converts_broker_points_to_usd(self):
        """push_bars must convert broker points spread to USD."""
        from titan.production.feature_stream import H1FeatureStream
        import pandas as pd

        fs = H1FeatureStream()
        bars = pd.DataFrame({
            "open": [2000.0]*10,
            "high": [2010.0]*10,
            "low":  [1990.0]*10,
            "close":[2005.0]*10,
            "volume": [100]*10,
            "spread": [20]*10,
        }, index=pd.date_range("2024-01-01", periods=10, freq="h", tz="UTC"))
        fs.push_bars(bars)
        tail_spread = float(fs._bars["spread"].tail(10).median())
        assert tail_spread == pytest.approx(0.20, abs=1e-6), (
            f"expected 0.20 USD, got {tail_spread}"
        )

    def test_push_bar_single_dict_normalizes_spread(self):
        """push_bar must normalize spread for single bar dict."""
        from titan.production.feature_stream import H1FeatureStream

        fs = H1FeatureStream()
        for i in range(5):
            bar = {
                "timestamp": f"2024-01-01T{i:02d}:00:00Z",
                "open": 2000.0, "high": 2010.0, "low": 1990.0, "close": 2005.0,
                "volume": 100, "spread": 25.0,
            }
            fs.push_bar(bar)
        tail = fs._bars["spread"].tail(5)
        for v in tail:
            assert v == pytest.approx(0.25, abs=1e-6), f"expected 0.25, got {v}"


class TestRealBrokerSpreadNormalization:
    def test_broker_spread_pct_not_100x_inflated(self):
        """Post-normalization, broker spread_pct must NOT be 100x of canonical."""
        import pandas as pd
        import numpy as np
        from titan.production.spread_normalization import normalize_xauusd_spread_to_usd

        canon_path = REPO_ROOT / "titan" / "data" / "canonical" / "XAUUSD_H1_canonical.parquet"
        exness_path = REPO_ROOT / "titan" / "data" / "sources" / "mt5_brokers" / "exness" / "XAUUSD_H1.parquet"
        if not canon_path.exists() or not exness_path.exists():
            pytest.skip("broker data files not present")

        canon = normalize_xauusd_spread_to_usd(
            pd.read_parquet(canon_path), symbol="XAUUSD", source="canonical"
        )
        exness = normalize_xauusd_spread_to_usd(
            pd.read_parquet(exness_path), symbol="XAUUSD", source="exness"
        )

        canon_pct = (canon["spread_usd"] / canon["close"]).replace([np.inf, -np.inf], 0).fillna(0)
        exness_pct = (exness["spread_usd"] / exness["close"]).replace([np.inf, -np.inf], 0).fillna(0)

        canon_mean = float(canon_pct.mean())
        exness_mean = float(exness_pct.mean())

        ratio = exness_mean / max(canon_mean, 1e-12)
        assert ratio < 50.0, (
            f"exness spread_pct {exness_mean} / canonical {canon_mean} = {ratio}x "
            f"- 100x inflation NOT fixed"
        )

    def test_audit_files_generated(self):
        """spread_normalization_audit.{csv,md} must exist after diagnostic run."""
        csv_path = OUTPUT_DIR / "spread_normalization_audit.csv"
        md_path = OUTPUT_DIR / "spread_normalization_audit.md"
        assert csv_path.exists(), f"missing {csv_path}"
        assert md_path.exists(), f"missing {md_path}"
        md_text = md_path.read_text()
        assert "POINTS_CONVERTED" in md_text
        assert "USD" in md_text


class TestSafety:
    def test_no_order_send_in_spread_normalization(self):
        src = (REPO_ROOT / "titan" / "production" / "spread_normalization.py").read_text()
        assert "order_send" not in src

    def test_no_token_in_spread_normalization(self):
        src = (REPO_ROOT / "titan" / "production" / "spread_normalization.py").read_text()
        assert "create_local_operator_execution_token" not in src
        assert "execution_token" not in src.lower()

    def test_no_order_send_in_feature_stream(self):
        src = (REPO_ROOT / "titan" / "production" / "feature_stream.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        assert "order_send" not in stripped

    def test_no_order_send_in_diagnostic(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_meta_label_broker_diagnostic.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        assert "order_send" not in stripped

    def test_no_order_send_in_parameter_discovery(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        assert "order_send" not in stripped

    def test_no_token_in_parameter_discovery(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "create_local_operator_execution_token" not in src

    def test_production_ready_remains_false(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "production_ready" in src
        assert '"production_ready": False' in src or "'production_ready': False" in src

    def test_no_martingale(self):
        files = [
            REPO_ROOT / "titan" / "production" / "spread_normalization.py",
            REPO_ROOT / "titan" / "production" / "feature_stream.py",
            REPO_ROOT / "scripts" / "research" / "run_meta_label_broker_diagnostic.py",
            REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py",
        ]
        for f in files:
            if f.exists():
                src = f.read_text().lower()
                assert "martingale" not in src, f"martingale found in {f}"

    def test_no_trade_calls_in_spread_normalization(self):
        src = (REPO_ROOT / "titan" / "production" / "spread_normalization.py").read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        for forbidden in ["order_send", "positions_add", "trade_request", "PositionSend"]:
            assert forbidden not in stripped, f"{forbidden} found in spread_normalization.py"


class TestMetaLabelDiagnosticPostFix:
    def test_diagnostic_md_exists_with_v2_8_7_c_header(self):
        md_path = OUTPUT_DIR / "meta_label_broker_diagnostic.md"
        assert md_path.exists()
        text = md_path.read_text()
        assert "v2.8.7-C" in text or "post-spread-normalization" in text.lower()

    def test_broker_shift_false_post_normalization(self):
        md_path = OUTPUT_DIR / "meta_label_broker_diagnostic.md"
        text = md_path.read_text()
        assert "META_LABEL_BROKER_SHIFT:** False" in text or \
               "META_LABEL_BROKER_SHIFT: False" in text, \
               "META_LABEL_BROKER_SHIFT should be False after spread normalization"


class TestParameterDiscoverySafety:
    def test_demo_go_decision_md_exists(self):
        path = OUTPUT_DIR / "demo_go_decision.md"
        assert path.exists()
        text = path.read_text()
        assert "DEMO_SHADOW_ALLOWED" in text or "NO_SAFE_PARAMETER_FOUND" in text or \
               "NEEDS_MORE_DATA" in text or "INVALID_IMPLEMENTATION" in text

    def test_progress_every_flag_in_source(self):
        src = (REPO_ROOT / "scripts" / "research" / "run_safe_parameter_discovery.py").read_text()
        assert "--progress-every" in src
        assert "progress_every" in src

    def test_production_component_audit_csv_exists(self):
        path = OUTPUT_DIR / "production_component_audit.csv"
        assert path.exists()
        text = path.read_text()
        assert "PRODUCTION_XGBOOST" in text or "alpha_source" in text
        assert "PRODUCTION_META_LABEL" in text or "meta_source" in text

    def test_top_20_parameter_sets_csv_exists(self):
        path = OUTPUT_DIR / "top_20_parameter_sets.csv"
        assert path.exists()

    def test_parameter_search_summary_md_exists(self):
        path = OUTPUT_DIR / "parameter_search_summary.md"
        assert path.exists()
        text = path.read_text()
        assert "Verdict:" in text or "Demo Go Decision:" in text
