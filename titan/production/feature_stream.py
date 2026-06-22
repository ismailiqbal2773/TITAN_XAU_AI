"""
TITAN XAU AI — Incremental H1 Feature Stream (Production Sprint 1)

Generates the 55-feature vector that xgboost_v1.pkl was trained on,
incrementally from a rolling window of H1 bars. Supports both:
  - Live MT5 feed (mt5.copy_rates_range)
  - Offline canonical parquet (for backtest / dev / smoke test)

Reuses feature definitions from titan/training/feature_engine.py —
NO new feature math is introduced. We only re-compute the existing
55 features on a rolling window and emit the latest row.

Usage:
    from titan.production.feature_stream import H1FeatureStream
    fs = H1FeatureStream(window=300)
    vec = fs.latest_vector(source="canonical")      # offline
    vec = fs.latest_vector(source="mt5", symbol="XAUUSD")  # live
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ─── Feature schema (matches XAUUSD_H1_X_train.parquet exactly) ──────────────
FEATURE_NAMES: list[str] = [
    "n_brokers", "ret_1", "ret_5", "ret_15", "price_zscore_60", "hl_range",
    "close_pos_in_range", "rsi", "macd_signal", "macd_hist", "bb_upper",
    "bb_width", "bb_pct_b", "atr", "adx", "plus_di", "minus_di", "obv",
    "obv_slope_20", "sma_20_ratio", "sma_200_ratio", "realized_vol_10",
    "vol_of_vol_10", "realized_vol_20", "vol_of_vol_20", "realized_vol_60",
    "vol_of_vol_60", "realized_vol_120", "vol_of_vol_120", "vol_ratio_10_60",
    "atr_ratio_5_20", "spread_pct", "spread_zscore_60", "volume_zscore_60",
    "volume_ratio_5_20", "body_ratio", "upper_wick_ratio", "lower_wick_ratio",
    "body_dir", "hour_sin", "hour_cos", "dow_sin", "dow_cos", "asia_session",
    "eu_session", "us_session", "month_sin", "month_cos", "ret_lag_1",
    "ret_lag_2", "ret_lag_3", "ret_lag_5", "ret_lag_10", "ret_lag_20",
    "ret_lag_60",
]
N_FEATURES: int = len(FEATURE_NAMES)  # = 55

# ─── Indicator periods (mirror FeatureEngine defaults) ───────────────────────
RSI_PERIOD = 14
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
BB_PERIOD, BB_STD = 20, 2.0
ATR_PERIOD, ADX_PERIOD = 14, 14
LAG_HORIZONS = [1, 2, 3, 5, 10, 20, 60]
VOL_WINDOWS = [10, 20, 60, 120]

# Minimum bars needed for all features to be non-NaN
MIN_BARS_FOR_FULL_FEATURES = 220  # sma_200_ratio + buffer


@dataclass
class FeatureVector:
    """Latest computed feature vector."""
    timestamp: pd.Timestamp
    features: np.ndarray           # shape (55,)
    feature_names: list[str]
    n_bars_used: int
    source: str                    # "mt5" | "canonical" | "manual"
    is_valid: bool = True
    error: Optional[str] = None


class H1FeatureStream:
    """
    Rolling H1 feature stream.

    Maintains an in-memory deque of recent H1 OHLCV bars and emits the
    55-feature vector expected by xgboost_v1.pkl. Recomputes indicators
    on the rolling window — same math as titan/training/feature_engine.py,
    refactored to operate on the latest row only.
    """

    def __init__(self, window: int = 300, canonical_path: Optional[str] = None):
        """
        Args:
            window: Number of H1 bars to keep in the rolling buffer.
                    Must be >= MIN_BARS_FOR_FULL_FEATURES (220).
            canonical_path: Path to XAUUSD_H1_canonical.parquet for offline mode.
        """
        if window < MIN_BARS_FOR_FULL_FEATURES:
            raise ValueError(
                f"window must be >= {MIN_BARS_FOR_FULL_FEATURES} bars "
                f"(got {window})"
            )
        self.window = window
        self._bars: pd.DataFrame = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume", "spread"]
        )
        self._canonical_path = canonical_path or self._default_canonical_path()
        self._canonical_loaded = False

    @staticmethod
    def _default_canonical_path() -> str:
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        return os.path.join(repo_root, "titan", "data", "canonical",
                            "XAUUSD_H1_canonical.parquet")

    # ─── Bar ingestion ──────────────────────────────────────────────────

    def push_bar(self, bar: dict) -> None:
        """Push a single H1 bar dict {timestamp, open, high, low, close, volume, spread}."""
        ts = pd.to_datetime(bar.get("timestamp") or bar.get("time"))
        row = {
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
            "volume": float(bar.get("volume", 0.0)),
            "spread": float(bar.get("spread", 0.0)),
        }
        # Append + trim
        self._bars.loc[ts] = row
        if len(self._bars) > self.window:
            self._bars = self._bars.iloc[-self.window:]

    def push_bars(self, bars: pd.DataFrame) -> None:
        """Push a DataFrame of bars (columns: open/high/low/close/volume/spread)."""
        if bars.empty:
            return
        df = bars.copy()
        if "spread" not in df.columns:
            df["spread"] = 0.0
        if not isinstance(df.index, pd.DatetimeIndex):
            if "timestamp" in df.columns or "time" in df.columns:
                df = df.set_index("timestamp" if "timestamp" in df.columns else "time")
            else:
                df.index = pd.to_datetime(df.index)
        df = df[["open", "high", "low", "close", "volume", "spread"]]
        self._bars = pd.concat([self._bars, df]).sort_index()
        self._bars = self._bars[~self._bars.index.duplicated(keep="last")]
        if len(self._bars) > self.window:
            self._bars = self._bars.iloc[-self.window:]

    # ─── Sources ────────────────────────────────────────────────────────

    def load_canonical(self, path: Optional[str] = None) -> int:
        """Load canonical H1 parquet into the buffer. Returns bar count."""
        path = path or self._canonical_path
        if not os.path.exists(path):
            raise FileNotFoundError(f"Canonical H1 parquet not found: {path}")
        df = pd.read_parquet(path)
        # Canonical schema: timestamp, open, high, low, close, tick_volume, spread_usd, n_brokers, regime
        col_map = {"tick_volume": "volume", "spread_usd": "spread"}
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        if "volume" not in df.columns:
            df["volume"] = 0
        if "spread" not in df.columns:
            df["spread"] = 0
        if not isinstance(df.index, pd.DatetimeIndex):
            ts_col = "timestamp" if "timestamp" in df.columns else "time"
            if ts_col in df.columns:
                df = df.set_index(ts_col)
        self._bars = df[["open", "high", "low", "close", "volume", "spread"]].tail(self.window)
        self._canonical_loaded = True
        logger.info(f"Loaded {len(self._bars)} bars from {path}")
        return len(self._bars)

    def load_from_mt5(self, symbol: str = "XAUUSD", n_bars: int = 300) -> int:
        """Load H1 bars from MT5 terminal. Requires Windows + MetaTrader5."""
        try:
            import MetaTrader5 as mt5
        except ImportError:
            raise ImportError(
                "MetaTrader5 package not available — use load_canonical() "
                "for offline mode or run on Windows with MT5 installed."
            )
        if not mt5.initialize():
            raise RuntimeError(f"mt5.initialize() failed: {mt5.last_error()}")
        try:
            rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, n_bars)
            if rates is None or len(rates) == 0:
                raise RuntimeError(f"mt5.copy_rates_from_pos returned no data for {symbol}")
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df = df.rename(columns={"tick_volume": "volume"})
            df = df.set_index("time")
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)
            if "spread" in df.columns:
                df["spread"] = df["spread"].astype(float)
            else:
                df["spread"] = 0.0
            self._bars = df[["open", "high", "low", "close", "volume", "spread"]].tail(self.window)
            logger.info(f"Loaded {len(self._bars)} H1 bars from MT5 for {symbol}")
            return len(self._bars)
        finally:
            mt5.shutdown()

    # ─── Feature computation (mirror FeatureEngine math) ────────────────

    def _compute_features(self) -> pd.DataFrame:
        """Compute all 55 features on the current bar buffer."""
        df = self._bars.copy()
        if len(df) < MIN_BARS_FOR_FULL_FEATURES:
            raise ValueError(
                f"Need >= {MIN_BARS_FOR_FULL_FEATURES} bars, have {len(df)}"
            )

        c, h, l, o, v = df["close"], df["high"], df["low"], df["open"], df["volume"]
        spread = df["spread"]
        feats = pd.DataFrame(index=df.index)

        # ── Price (7) ──
        feats["ret_1"] = c.pct_change(1)
        feats["ret_5"] = c.pct_change(5)
        feats["ret_15"] = c.pct_change(15)
        feats["price_zscore_60"] = (c - c.rolling(60).mean()) / c.rolling(60).std().replace(0, np.nan)
        feats["hl_range"] = (h - l) / c
        rng = (h - l).replace(0, np.nan)
        feats["close_pos_in_range"] = (c - l) / rng
        # n_brokers — for live single-broker feed, default 1; for canonical, preserved separately
        feats["n_brokers"] = 1 if not self._canonical_loaded else getattr(self, "_last_n_brokers", 1)

        # ── Technical (14: rsi, macd_signal, macd_hist, bb_upper, bb_width, bb_pct_b, atr, adx, plus_di, minus_di, obv, obv_slope_20, sma_20_ratio, sma_200_ratio) ──
        delta = c.diff()
        gain = delta.where(delta > 0, 0).rolling(RSI_PERIOD).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(RSI_PERIOD).mean()
        rs = gain / loss.replace(0, np.nan)
        feats["rsi"] = 100 - (100 / (1 + rs))

        ema_fast = c.ewm(span=MACD_FAST, adjust=False).mean()
        ema_slow = c.ewm(span=MACD_SLOW, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=MACD_SIGNAL, adjust=False).mean()
        feats["macd_signal"] = signal_line
        feats["macd_hist"] = macd_line - signal_line

        sma = c.rolling(BB_PERIOD).mean()
        std = c.rolling(BB_PERIOD).std()
        feats["bb_upper"] = sma + BB_STD * std
        bb_lower = sma - BB_STD * std
        feats["bb_width"] = (feats["bb_upper"] - bb_lower) / sma.replace(0, np.nan)
        feats["bb_pct_b"] = (c - bb_lower) / (feats["bb_upper"] - bb_lower).replace(0, np.nan)

        tr = pd.concat([(h - l), (h - c.shift(1)).abs(), (l - c.shift(1)).abs()], axis=1).max(axis=1)
        feats["atr"] = tr.rolling(ATR_PERIOD).mean() / c

        plus_dm = (h - h.shift(1)).where((h - h.shift(1)) > (l.shift(1) - l), 0)
        minus_dm = (l.shift(1) - l).where((l.shift(1) - l) > (h - h.shift(1)), 0)
        atr_adx = tr.ewm(span=ADX_PERIOD, adjust=False).mean()
        plus_di = 100 * plus_dm.ewm(span=ADX_PERIOD, adjust=False).mean() / atr_adx.replace(0, np.nan)
        minus_di = 100 * minus_dm.ewm(span=ADX_PERIOD, adjust=False).mean() / atr_adx.replace(0, np.nan)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        feats["adx"] = dx.ewm(span=ADX_PERIOD, adjust=False).mean()
        feats["plus_di"] = plus_di
        feats["minus_di"] = minus_di

        obv = (np.sign(c.diff()) * v).fillna(0).cumsum()
        feats["obv"] = obv
        feats["obv_slope_20"] = obv.diff(20)
        feats["sma_20_ratio"] = c / c.rolling(20).mean()
        feats["sma_200_ratio"] = c / c.rolling(200).mean()

        # ── Volatility (10) ──
        log_ret = np.log(c / c.shift(1))
        for w in VOL_WINDOWS:
            feats[f"realized_vol_{w}"] = log_ret.rolling(w).std()
            feats[f"vol_of_vol_{w}"] = log_ret.rolling(w).std().rolling(w).std()
        feats["vol_ratio_10_60"] = log_ret.rolling(10).std() / log_ret.rolling(60).std().replace(0, np.nan)
        feats["atr_ratio_5_20"] = tr.rolling(5).mean() / tr.rolling(20).mean().replace(0, np.nan)

        # ── Microstructure (8) ──
        feats["spread_pct"] = spread / c
        feats["spread_zscore_60"] = (spread - spread.rolling(60).mean()) / spread.rolling(60).std().replace(0, np.nan)
        feats["volume_zscore_60"] = (v - v.rolling(60).mean()) / v.rolling(60).std().replace(0, np.nan)
        feats["volume_ratio_5_20"] = v.rolling(5).mean() / v.rolling(20).mean().replace(0, np.nan)
        body = (c - o).abs()
        full_range = (h - l).replace(0, np.nan)
        feats["body_ratio"] = body / full_range
        feats["upper_wick_ratio"] = (h - np.maximum(o, c)) / full_range
        feats["lower_wick_ratio"] = (np.minimum(o, c) - l) / full_range
        feats["body_dir"] = (c - o) / full_range

        # ── Time (9) ──
        ts = df.index
        hour = ts.hour + ts.minute / 60.0
        feats["hour_sin"] = np.sin(2 * np.pi * hour / 24)
        feats["hour_cos"] = np.cos(2 * np.pi * hour / 24)
        dow = ts.dayofweek
        feats["dow_sin"] = np.sin(2 * np.pi * dow / 7)
        feats["dow_cos"] = np.cos(2 * np.pi * dow / 7)
        feats["asia_session"] = ((hour >= 0) & (hour < 8)).astype(int)
        feats["eu_session"] = ((hour >= 7) & (hour < 16)).astype(int)
        feats["us_session"] = ((hour >= 13) & (hour < 22)).astype(int)
        month = ts.month
        feats["month_sin"] = np.sin(2 * np.pi * month / 12)
        feats["month_cos"] = np.cos(2 * np.pi * month / 12)

        # ── Lag (7) ──
        for hz in LAG_HORIZONS:
            feats[f"ret_lag_{hz}"] = c.pct_change(hz).shift(1)

        # Reorder to match FEATURE_NAMES exactly
        feats = feats[FEATURE_NAMES]
        return feats

    # ─── Public API ─────────────────────────────────────────────────────

    def latest_features(self) -> pd.DataFrame:
        """Return the full feature DataFrame (history). For debugging."""
        return self._compute_features()

    def latest_vector(self, source: str = "canonical",
                      symbol: str = "XAUUSD") -> FeatureVector:
        """
        Compute the latest (most recent) feature vector.

        Args:
            source: "canonical" (offline parquet) | "mt5" (live)
            symbol: MT5 symbol (only for source="mt5")
        """
        try:
            if source == "canonical":
                if not self._canonical_loaded:
                    self.load_canonical()
            elif source == "mt5":
                self.load_from_mt5(symbol=symbol, n_bars=self.window)
            else:
                raise ValueError(f"Unknown source: {source}")

            # Preserve n_brokers if canonical had it
            if source == "canonical" and self._canonical_loaded:
                try:
                    full_df = pd.read_parquet(self._canonical_path)
                    if "n_brokers" in full_df.columns:
                        self._last_n_brokers = int(full_df["n_brokers"].iloc[-1])
                except Exception:
                    pass

            feats = self._compute_features()
            last_row = feats.iloc[-1]
            # Replace any remaining NaN/inf with 0
            vec = np.nan_to_num(last_row.values.astype(np.float64), nan=0.0,
                                posinf=0.0, neginf=0.0)
            ts = feats.index[-1]
            return FeatureVector(
                timestamp=ts,
                features=vec,
                feature_names=FEATURE_NAMES.copy(),
                n_bars_used=len(self._bars),
                source=source,
                is_valid=True,
            )
        except Exception as e:
            logger.error(f"Feature computation failed: {e}")
            return FeatureVector(
                timestamp=pd.Timestamp.utcnow(),
                features=np.zeros(N_FEATURES, dtype=np.float64),
                feature_names=FEATURE_NAMES.copy(),
                n_bars_used=len(self._bars),
                source=source,
                is_valid=False,
                error=str(e),
            )
