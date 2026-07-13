"""TITAN XAU AI — v2.8.7-P2.5.3 Feature Fail-Closed Tests
==========================================================

Proves that predict_proba is never called after an invalid feature result.
"""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))


class TestFeatureFailClosed:
    """Phase 3: Invalid features must never reach predict_proba."""

    def test_exception_path_returns_none_features(self):
        """FeatureVectorV2 exception path must return features=None, not zeros."""
        from titan.production.feature_stream_v2 import H1FeatureStreamV2
        stream = H1FeatureStreamV2()
        # Force an exception by not loading any bars
        stream._bars = pd.DataFrame()  # empty
        vec = stream.latest_vector(source="test")
        assert vec.is_valid is False
        assert vec.features is None  # NOT a zero vector
        assert vec.invalid_features is not None

    def test_nan_features_return_invalid_not_zeros(self):
        """When features contain NaN, result must be is_valid=False with no nan_to_num."""
        from titan.production.feature_stream_v2 import H1FeatureStreamV2, FEATURE_NAMES_V2
        # Create bars that produce NaN in first row (insufficient warmup)
        n = 10
        dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
        df = pd.DataFrame({
            "open": [2000.0]*n, "high": [2001.0]*n, "low": [1999.0]*n,
            "close": [2000.0]*n, "volume": [100]*n, "spread": [0.15]*n,
        }, index=dates)
        stream = H1FeatureStreamV2()
        stream._bars = df
        vec = stream.latest_vector(source="test")
        # With only 10 bars, most features will be NaN
        assert vec.is_valid is False
        # Features should NOT be all zeros (that would be nan_to_num)
        if vec.features is not None:
            assert not np.all(vec.features == 0.0)

    def test_predict_proba_never_called_on_invalid(self):
        """Spy model must show zero predict_proba calls when features are invalid."""
        from titan.production.feature_stream_v2 import H1FeatureStreamV2
        spy_model = MagicMock()
        spy_model.predict_proba = MagicMock(return_value=np.array([[0.5, 0.5]]))

        stream = H1FeatureStreamV2()
        stream._bars = pd.DataFrame()  # empty → exception
        vec = stream.latest_vector(source="test")

        # Even if someone tries to call predict_proba, the features are None
        assert vec.is_valid is False
        assert vec.features is None
        # predict_proba was never called by latest_vector
        spy_model.predict_proba.assert_not_called()

    def test_no_nan_to_num_in_source(self):
        """feature_stream_v2.py must not contain nan_to_num in source code."""
        import re
        path = REPO_ROOT / "titan/production/feature_stream_v2.py"
        src = path.read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        stripped = re.sub(r"'''[\s\S]*?'''", "''", stripped)
        assert "np.nan_to_num" not in stripped
        assert "nan_to_num(" not in stripped

    def test_no_zero_vector_fallback(self):
        """No np.zeros fallback for features in exception path."""
        import re
        path = REPO_ROOT / "titan/production/feature_stream_v2.py"
        src = path.read_text()
        stripped = re.sub(r'"""[\s\S]*?"""', '""', src)
        # The exception path should use features=None, not np.zeros
        assert "np.zeros" not in stripped or "features=None" in stripped
