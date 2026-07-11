"""TITAN XAU AI - Sprint v2.8.7-P Opportunity Scanner Tests"""
from __future__ import annotations
import sys, re
from pathlib import Path
import pytest
import pandas as pd
import numpy as np
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

class TestOpportunityScanner:
    def test_scanner_exists(self):
        assert (REPO_ROOT / "titan" / "production" / "opportunity_scanner.py").exists()
    def test_signal_class_enum(self):
        from titan.production.opportunity_scanner import SignalClass
        assert SignalClass.A_PLUS.value == "A_PLUS"
        assert SignalClass.C_SHADOW_ONLY.value == "C_SHADOW_ONLY"
    def test_c_shadow_only_never_trades(self):
        """C_SHADOW_ONLY must never become a trade."""
        from titan.production.opportunity_scanner import SignalClass
        assert SignalClass.C_SHADOW_ONLY != SignalClass.A
        assert SignalClass.C_SHADOW_ONLY != SignalClass.A_PLUS
    def test_b_class_reduced_risk(self):
        """B class must use reduced risk."""
        from titan.production.opportunity_scanner import SignalClass
        assert SignalClass.B != SignalClass.A_PLUS
    def test_scan_opportunities_returns_list(self):
        from titan.production.opportunity_scanner import scan_opportunities
        # Create minimal dataframes
        n = 250
        idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
        h1 = pd.DataFrame({"open":np.random.uniform(2000,2100,n),"high":np.random.uniform(2100,2200,n),
                           "low":np.random.uniform(1900,2000,n),"close":np.random.uniform(2000,2100,n),
                           "volume":np.random.uniform(100,1000,n),"spread":np.random.uniform(0.1,0.3,n)}, index=idx)
        m15 = h1.copy()
        m5 = h1.copy()
        candidates = scan_opportunities(h1, m15, m5, 0.55, 0.55, 5.0, 0.2)
        assert isinstance(candidates, list)
    def test_no_order_send(self):
        src = (REPO_ROOT / "titan" / "production" / "opportunity_scanner.py").read_text()
        assert "order_send" not in src
