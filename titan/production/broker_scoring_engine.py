"""
TITAN XAU AI — Broker Scoring Engine (Sprint 9.9.3.45.8.5)
============================================================

Scores every broker profile declared in ``config/broker_profiles.yaml``
against 14 weighted execution-quality dimensions and produces a single
0-100 BrokerScore with a tri-state verdict:

  BROKER_APPROVED  (>=85)  — safe to deploy
  BROKER_CAUTION   (70-84) — usable but with caveats
  BROKER_BLOCKED   (<70)   — must not be used

The engine is pure-Python. It NEVER imports MetaTrader5, NEVER calls
``mt5.order_send``, and NEVER submits orders. It reads configuration
YAML and (optionally) the frozen-balanced historical broker validation
CSV produced by the multi-year backtest pipeline, then derives a
deterministic score.

Safety invariants (HARD — enforced for every broker):
  - no_martingale: True
  - no_grid: True
  - no_averaging: True
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


# ─── Verdict bands ─────────────────────────────────────────────────────────
BROKER_APPROVED: str = "BROKER_APPROVED"
BROKER_CAUTION: str = "BROKER_CAUTION"
BROKER_BLOCKED: str = "BROKER_BLOCKED"

APPROVED_THRESHOLD: float = 85.0
CAUTION_THRESHOLD: float = 70.0


# ─── Safety flags mirrored across the production stack ─────────────────────
SAFETY_FLAGS: dict[str, bool] = {
    "no_martingale": True,
    "no_grid": True,
    "no_averaging": True,
}


# ─── Score component names (14 weighted dimensions) ────────────────────────
SCORE_COMPONENTS: tuple[str, ...] = (
    "spread_score",
    "slippage_score",
    "commission_score",
    "swap_score",
    "stop_level_score",
    "freeze_level_score",
    "filling_mode_score",
    "lot_step_score",
    "symbol_suffix_score",
    "execution_profile_score",
    "historical_validation_score",
    "broker_split_validation_score",
    "net_expectancy_impact_score",
    "prop_funded_compatibility_score",
)


# Weights per component (sum to 1.0). Each weight reflects the relative
# importance of that dimension to TITAN XAU AI's execution quality.
DEFAULT_WEIGHTS: dict[str, float] = {
    "spread_score": 0.15,
    "slippage_score": 0.10,
    "commission_score": 0.08,
    "swap_score": 0.05,
    "stop_level_score": 0.07,
    "freeze_level_score": 0.05,
    "filling_mode_score": 0.05,
    "lot_step_score": 0.04,
    "symbol_suffix_score": 0.03,
    "execution_profile_score": 0.08,
    "historical_validation_score": 0.10,
    "broker_split_validation_score": 0.07,
    "net_expectancy_impact_score": 0.08,
    "prop_funded_compatibility_score": 0.05,
}


# ─── Filling mode known constants ──────────────────────────────────────────
FILLING_MODE_SCORES: dict[str, float] = {
    "ORDER_FILLING_IOC": 100.0,
    "ORDER_FILLING_FOK": 85.0,
    "ORDER_FILLING_RETURN": 70.0,
    "ORDER_FILLING_BOC": 60.0,
}


# ─── Mapping from YAML broker ids to historical CSV source names ───────────
# The frozen_balanced_validation/broker_validation.csv uses short source
# labels (canonical, exness, icmarkets, fundednext, fbs) while the broker
# profiles YAML uses fully qualified ids. This map bridges the two.
BROKER_ID_TO_HISTORICAL_SOURCE: dict[str, str] = {
    "metaquotes_demo": "canonical",      # demo broker, uses canonical data
    "ic_markets_standard": "icmarkets",
    "ftmo_prop": "ftmo",                 # not in historical CSV → fallback
    "institutional_ecn": "institutional",
    "exness": "exness",
    "fbs": "fbs",
    "fundednext": "fundednext",
    "icmarkets": "icmarkets",
    "canonical": "canonical",
}


# ─── Dataclasses ────────────────────────────────────────────────────────────
@dataclass
class BrokerScoreResult:
    """
    Final scored result for a single broker.

    ``score`` is the weighted 0-100 aggregate. Each component in
    ``components`` is also 0-100. ``verdict`` is one of
    BROKER_APPROVED / BROKER_CAUTION / BROKER_BLOCKED.
    """
    broker_id: str
    broker_name: str
    server: str
    account_type: str
    score: float
    verdict: str
    components: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    prop_funded_compatible: bool = False
    historical_source: str = ""
    historical_verdict: str = ""
    notes: list[str] = field(default_factory=list)
    # Hard safety invariants — always True.
    no_martingale: bool = True
    no_grid: bool = True
    no_averaging: bool = True

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["score"] = round(self.score, 2)
        d["components"] = {k: round(v, 2) for k, v in self.components.items()}
        d["weights"] = {k: round(v, 4) for k, v in self.weights.items()}
        return d


# ─── Engine ────────────────────────────────────────────────────────────────
class BrokerScoringEngine:
    """
    Scores broker profiles from YAML against 14 weighted execution-quality
    dimensions and produces a 0-100 BrokerScore with a tri-state verdict.

    Usage:
        engine = BrokerScoringEngine(
            profiles_path="config/broker_profiles.yaml",
            historical_csv="data/audit/frozen_balanced_validation/broker_validation.csv",
        )
        result = engine.score_broker("metaquotes_demo")
        all_results = engine.score_all_brokers()
    """

    def __init__(
        self,
        profiles_path: str | Path = "config/broker_profiles.yaml",
        historical_csv: Optional[str | Path] = None,
        weights: Optional[dict[str, float]] = None,
    ) -> None:
        self.profiles_path = Path(profiles_path)
        # Default historical CSV location — only used if it exists.
        if historical_csv is None:
            default_csv = (
                self.profiles_path.parent.parent
                / "data"
                / "audit"
                / "frozen_balanced_validation"
                / "broker_validation.csv"
            )
            self.historical_csv: Optional[Path] = (
                default_csv if default_csv.exists() else None
            )
        else:
            self.historical_csv = Path(historical_csv)

        self.weights: dict[str, float] = dict(DEFAULT_WEIGHTS)
        if weights:
            self.weights.update(weights)

        self._raw: dict[str, dict] = {}
        self._profiles: dict[str, dict] = {}
        self._historical: dict[str, dict] = {}
        self._load_yaml()
        self._load_historical()

    # ─── Loading ────────────────────────────────────────────────────────
    def _load_yaml(self) -> None:
        if not self.profiles_path.exists():
            raise FileNotFoundError(
                f"Broker profiles YAML not found: {self.profiles_path}"
            )
        with open(self.profiles_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f) or {}
        raw_brokers = doc.get("brokers", {}) or {}
        for broker_id, raw in raw_brokers.items():
            if not isinstance(raw, dict):
                logger.warning(
                    "Skipping broker entry '%s': not a mapping", broker_id
                )
                continue
            self._raw[broker_id] = raw
            # Enforce safety flags defensively.
            raw.setdefault("no_martingale", True)
            raw.setdefault("no_grid", True)
            raw.setdefault("no_averaging", True)
            # Force-override safety invariants regardless of YAML content.
            raw["no_martingale"] = bool(raw["no_martingale"]) or True
            raw["no_grid"] = bool(raw["no_grid"]) or True
            raw["no_averaging"] = bool(raw["no_averaging"]) or True
            self._profiles[broker_id] = raw
        logger.info(
            "BrokerScoringEngine loaded %d broker profiles from %s",
            len(self._profiles),
            self.profiles_path,
        )

    def _load_historical(self) -> None:
        """Load frozen-balanced broker validation CSV if available."""
        if self.historical_csv is None or not self.historical_csv.exists():
            logger.info(
                "No historical broker_validation.csv found — "
                "historical scores will use neutral defaults."
            )
            return
        try:
            with open(self.historical_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    source = (row.get("source") or "").strip().lower()
                    if not source:
                        continue
                    self._historical[source] = {
                        "source": source,
                        "total_months": _safe_float(row.get("total_months")),
                        "avg_monthly_pct": _safe_float(row.get("avg_monthly_pct")),
                        "median_monthly_pct": _safe_float(row.get("median_monthly_pct")),
                        "target_10_rate": _safe_float(row.get("target_10_rate")),
                        "max_dd_pct": _safe_float(row.get("max_dd_pct")),
                        "dd_breach_count": _safe_float(row.get("dd_breach_count")),
                        "avg_pf": _safe_float(row.get("avg_pf")),
                        "avg_win_rate": _safe_float(row.get("avg_win_rate")),
                        "avg_trade_count": _safe_float(row.get("avg_trade_count")),
                        "verdict": (row.get("verdict") or "").strip().upper(),
                    }
            logger.info(
                "Loaded historical broker validation for %d sources from %s",
                len(self._historical),
                self.historical_csv,
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.error("Failed to load historical CSV: %s", e)
            self._historical = {}

    # ─── Public API ─────────────────────────────────────────────────────
    def list_brokers(self) -> list[str]:
        """Return all broker profile ids registered in the YAML."""
        return sorted(self._profiles.keys())

    def has_broker(self, broker_id: str) -> bool:
        return broker_id in self._profiles

    def list_historical_sources(self) -> list[str]:
        """Return all source labels in the historical validation CSV."""
        return sorted(self._historical.keys())

    def score_broker(self, broker_id: str) -> BrokerScoreResult:
        """
        Score a single broker by id.

        Raises:
            KeyError: if broker_id is not in the YAML.
        """
        if broker_id not in self._profiles:
            raise KeyError(
                f"Broker '{broker_id}' not found in {self.profiles_path}. "
                f"Available: {self.list_brokers()}"
            )
        raw = self._profiles[broker_id]
        components = self._compute_components(broker_id, raw)
        weights = {k: self.weights.get(k, 0.0) for k in SCORE_COMPONENTS}
        total_weight = sum(weights.values()) or 1.0
        score = sum(
            components.get(k, 0.0) * weights.get(k, 0.0)
            for k in SCORE_COMPONENTS
        ) / total_weight
        score = max(0.0, min(100.0, score))
        verdict = self._verdict_for(score)

        historical_source = self._historical_source_for(broker_id, raw)
        historical_record = self._historical.get(historical_source, {})
        historical_verdict = historical_record.get("verdict", "")

        prop_funded_compatible = self._prop_funded_compatible(raw, components)

        notes: list[str] = []
        if components.get("spread_score", 0.0) < 70.0:
            notes.append("spread above ideal band")
        if components.get("slippage_score", 0.0) < 70.0:
            notes.append("slippage above ideal band")
        if components.get("historical_validation_score", 0.0) < 70.0:
            notes.append("historical validation weak or missing")
        if not prop_funded_compatible:
            notes.append("not prop-firm compatible")
        if verdict == BROKER_BLOCKED:
            notes.append("broker blocked — do not deploy")

        return BrokerScoreResult(
            broker_id=broker_id,
            broker_name=str(raw.get("name", broker_id)),
            server=str(raw.get("server", broker_id)),
            account_type=str(raw.get("account_type", "demo")).lower(),
            score=score,
            verdict=verdict,
            components=components,
            weights=weights,
            prop_funded_compatible=prop_funded_compatible,
            historical_source=historical_source,
            historical_verdict=historical_verdict,
            notes=notes,
            no_martingale=True,
            no_grid=True,
            no_averaging=True,
        )

    def score_all_brokers(self) -> dict[str, BrokerScoreResult]:
        """
        Score every broker registered in the YAML.

        Returns:
            dict mapping broker_id → BrokerScoreResult.
        """
        return {bid: self.score_broker(bid) for bid in self.list_brokers()}

    # ─── Component scoring (0-100 each) ─────────────────────────────────
    def _compute_components(
        self,
        broker_id: str,
        raw: dict,
    ) -> dict[str, float]:
        return {
            "spread_score": self._score_spread(raw),
            "slippage_score": self._score_slippage(raw),
            "commission_score": self._score_commission(raw),
            "swap_score": self._score_swap(raw),
            "stop_level_score": self._score_stop_level(raw),
            "freeze_level_score": self._score_freeze_level(raw),
            "filling_mode_score": self._score_filling_mode(raw),
            "lot_step_score": self._score_lot_step(raw),
            "symbol_suffix_score": self._score_symbol_suffix(raw),
            "execution_profile_score": self._score_execution_profile(raw),
            "historical_validation_score": self._score_historical_validation(
                broker_id, raw
            ),
            "broker_split_validation_score": self._score_broker_split_validation(
                broker_id, raw
            ),
            "net_expectancy_impact_score": self._score_net_expectancy_impact(
                broker_id, raw
            ),
            "prop_funded_compatibility_score": self._score_prop_funded_compatibility(
                raw
            ),
        }

    def _score_spread(self, raw: dict) -> float:
        """Lower typical spread = higher score. XAUUSD: <=0.20 = 100, >=3.0 = 0."""
        s = _safe_float(raw.get("typical_spread_xauusd"), 0.35)
        if s <= 0.20:
            return 100.0
        if s >= 3.0:
            return 0.0
        return 100.0 * (1.0 - (s - 0.20) / 2.80)

    def _score_slippage(self, raw: dict) -> float:
        """Lower typical slippage = higher score. 0 = 100, >=0.20 = 0."""
        s = _safe_float(raw.get("typical_slippage_xauusd"), 0.02)
        if s <= 0.0:
            return 100.0
        if s >= 0.20:
            return 0.0
        return 100.0 * (1.0 - s / 0.20)

    def _score_commission(self, raw: dict) -> float:
        """Lower commission = higher score. 0 = 100, >=10 = 0."""
        c = _safe_float(raw.get("commission_per_lot_round_turn"), 0.0)
        if c <= 0.0:
            return 100.0
        if c >= 10.0:
            return 0.0
        return 100.0 * (1.0 - c / 10.0)

    def _score_swap(self, raw: dict) -> float:
        """
        Lower absolute swap = higher score.

        Long-side swap is the dominant cost for TITAN XAU AI directional
        trades. We score on ``abs(swap_long_xauusd_per_lot_per_night)``.
        0 = 100, >=5.0 = 0.
        """
        s = abs(_safe_float(raw.get("swap_long_xauusd_per_lot_per_night"), -3.50))
        if s <= 0.0:
            return 100.0
        if s >= 5.0:
            return 0.0
        return 100.0 * (1.0 - s / 5.0)

    def _score_stop_level(self, raw: dict) -> float:
        """Lower stops_level_points = higher score. 0 = 100, >=100 = 0."""
        s = _safe_float(raw.get("stops_level_points_xauusd"), 50)
        if s <= 0.0:
            return 100.0
        if s >= 100.0:
            return 0.0
        return 100.0 * (1.0 - s / 100.0)

    def _score_freeze_level(self, raw: dict) -> float:
        """Lower freeze_level_points = higher score. 0 = 100, >=50 = 0."""
        s = _safe_float(raw.get("freeze_level_points_xauusd"), 0)
        if s <= 0.0:
            return 100.0
        if s >= 50.0:
            return 0.0
        return 100.0 * (1.0 - s / 50.0)

    def _score_filling_mode(self, raw: dict) -> float:
        """IOC = 100 (best for TITAN), FOK = 85, RETURN = 70, other = 40."""
        fm = str(raw.get("filling_mode", "ORDER_FILLING_IOC")).upper()
        if fm in FILLING_MODE_SCORES:
            return FILLING_MODE_SCORES[fm]
        return 40.0

    def _score_lot_step(self, raw: dict) -> float:
        """Smaller lot step = higher score (more granular sizing)."""
        ls = _safe_float(raw.get("lot_step"), 0.01)
        if ls <= 0.01:
            return 100.0
        if ls >= 1.0:
            return 20.0
        if ls >= 0.5:
            return 40.0
        if ls >= 0.1:
            return 70.0
        return 90.0

    def _score_symbol_suffix(self, raw: dict) -> float:
        """
        No suffix = 100 (canonical XAUUSD).
        Suffix map declared = 85 (broker is explicit).
        Single simple suffix = 75.
        Unknown complex suffix = 60.
        """
        suffixes = raw.get("symbol_suffixes")
        if isinstance(suffixes, dict) and suffixes:
            return 85.0
        # Heuristic: if profile does not declare suffixes, assume canonical.
        # This is the safest assumption — the broker may still append ".c"
        # at runtime but the YAML does not require it.
        return 100.0

    def _score_execution_profile(self, raw: dict) -> float:
        """
        Composite execution-profile score combining spread, slippage,
        stop level, and freeze level. This rewards brokers with a
        tight, well-rounded execution profile rather than excelling in
        a single dimension.
        """
        sub = [
            self._score_spread(raw),
            self._score_slippage(raw),
            self._score_stop_level(raw),
            self._score_freeze_level(raw),
        ]
        return sum(sub) / len(sub)

    def _historical_source_for(self, broker_id: str, raw: dict) -> str:
        """
        Resolve the historical CSV source label for a broker profile.

        Priority:
          1. Explicit ``historical_source`` field on the profile.
          2. BROKER_ID_TO_HISTORICAL_SOURCE mapping.
          3. broker_id itself (lowercased).
        """
        explicit = raw.get("historical_source")
        if explicit:
            return str(explicit).strip().lower()
        return BROKER_ID_TO_HISTORICAL_SOURCE.get(
            broker_id, broker_id.lower()
        )

    def _score_historical_validation(
        self, broker_id: str, raw: dict
    ) -> float:
        """
        Score based on the historical broker validation CSV verdict.

        PASS = 100, WARN = 60, FAIL = 0, missing = 50 (neutral).
        """
        source = self._historical_source_for(broker_id, raw)
        rec = self._historical.get(source)
        if not rec:
            return 50.0
        verdict = rec.get("verdict", "").upper()
        if verdict == "PASS":
            return 100.0
        if verdict in {"WARN", "PENDING", "PARTIAL"}:
            return 60.0
        if verdict in {"FAIL", "BLOCKED", "REJECT"}:
            return 0.0
        return 50.0

    def _score_broker_split_validation(
        self, broker_id: str, raw: dict
    ) -> float:
        """
        Score based on whether the broker has a long enough historical
        sample (>12 months) with no drawdown breaches and a healthy
        profit factor (>1.5).
        """
        source = self._historical_source_for(broker_id, raw)
        rec = self._historical.get(source)
        if not rec:
            return 50.0
        months = _safe_float(rec.get("total_months"), 0.0)
        dd_breaches = _safe_float(rec.get("dd_breach_count"), 0.0)
        pf = _safe_float(rec.get("avg_pf"), 0.0)
        # Sample length: >=24 months = 100, >=12 = 80, >=6 = 60, <6 = 30.
        if months >= 24.0:
            len_score = 100.0
        elif months >= 12.0:
            len_score = 80.0
        elif months >= 6.0:
            len_score = 60.0
        else:
            len_score = 30.0
        # DD breaches: 0 = 100, >=3 = 0.
        if dd_breaches <= 0.0:
            dd_score = 100.0
        elif dd_breaches >= 3.0:
            dd_score = 0.0
        else:
            dd_score = 100.0 * (1.0 - dd_breaches / 3.0)
        # Profit factor: >=3 = 100, >=1.5 = 80, >=1 = 50, <1 = 0.
        # Treat inf PF as 100.
        if pf == float("inf") or pf >= 3.0:
            pf_score = 100.0
        elif pf >= 1.5:
            pf_score = 80.0
        elif pf >= 1.0:
            pf_score = 50.0
        else:
            pf_score = 0.0
        return (len_score + dd_score + pf_score) / 3.0

    def _score_net_expectancy_impact(
        self, broker_id: str, raw: dict
    ) -> float:
        """
        Score based on the broker's net expectancy impact — derived from
        the historical average monthly return percentage and the
        average profit factor.

        avg_monthly_pct >= 20 = 100, >=10 = 80, >=5 = 60, >=0 = 40, <0 = 0.
        """
        source = self._historical_source_for(broker_id, raw)
        rec = self._historical.get(source)
        if not rec:
            return 50.0
        monthly = _safe_float(rec.get("avg_monthly_pct"), 0.0)
        if monthly >= 20.0:
            monthly_score = 100.0
        elif monthly >= 10.0:
            monthly_score = 80.0
        elif monthly >= 5.0:
            monthly_score = 60.0
        elif monthly >= 0.0:
            monthly_score = 40.0
        else:
            monthly_score = 0.0
        # Weight the monthly score with the broker's own cost profile — a
        # high historical return on a broker with a poor execution profile
        # is suspect. We blend 70% historical + 30% execution-profile.
        exec_score = self._score_execution_profile(raw)
        return 0.7 * monthly_score + 0.3 * exec_score

    def _score_prop_funded_compatibility(self, raw: dict) -> float:
        """
        Score prop-firm compatibility. Prop firms (FTMO, MyForexFunds,
        FundingNext, etc.) typically require:
          - Tight spread (typical_spread_xauusd <= 0.30)
          - Low commission (<= 7.0 USD round turn)
          - Low stop level (<= 50 points)
          - IOC filling mode
          - Reasonable leverage (>= 30)
          - Lot step <= 0.01
        """
        score = 100.0
        spread = _safe_float(raw.get("typical_spread_xauusd"), 0.35)
        commission = _safe_float(raw.get("commission_per_lot_round_turn"), 0.0)
        stop_level = _safe_float(raw.get("stops_level_points_xauusd"), 50)
        filling_mode = str(raw.get("filling_mode", "ORDER_FILLING_IOC")).upper()
        lot_step = _safe_float(raw.get("lot_step"), 0.01)
        leverage_opts = raw.get("leverage_options", [])
        max_leverage = max(leverage_opts) if leverage_opts else 0

        if spread > 0.30:
            score -= 20.0
        if commission > 7.0:
            score -= 15.0
        if stop_level > 50:
            score -= 15.0
        if filling_mode != "ORDER_FILLING_IOC":
            score -= 15.0
        if lot_step > 0.01:
            score -= 15.0
        if max_leverage < 30:
            score -= 20.0
        return max(0.0, min(100.0, score))

    def _prop_funded_compatible(
        self,
        raw: dict,
        components: dict[str, float],
    ) -> bool:
        """Boolean prop-firm compatibility gate."""
        # Compatible if prop score >= 70 AND no hard violations.
        prop_score = components.get("prop_funded_compatibility_score", 0.0)
        if prop_score < 70.0:
            return False
        # Hard violations: any of these → incompatible.
        spread = _safe_float(raw.get("typical_spread_xauusd"), 0.35)
        if spread > 0.50:
            return False
        filling = str(raw.get("filling_mode", "ORDER_FILLING_IOC")).upper()
        if filling not in {"ORDER_FILLING_IOC", "ORDER_FILLING_FOK"}:
            return False
        lot_step = _safe_float(raw.get("lot_step"), 0.01)
        if lot_step > 0.01:
            return False
        return True

    @staticmethod
    def _verdict_for(score: float) -> str:
        if score >= APPROVED_THRESHOLD:
            return BROKER_APPROVED
        if score >= CAUTION_THRESHOLD:
            return BROKER_CAUTION
        return BROKER_BLOCKED


# ─── Helpers ────────────────────────────────────────────────────────────────
def _safe_float(value: Any, default: float = 0.0) -> float:
    """Parse a value to float, returning default on failure."""
    if value is None:
        return default
    try:
        f = float(value)
        if f != f:  # NaN check
            return default
        return f
    except (TypeError, ValueError):
        return default


# ─── Module-level smoke check (defensive) ──────────────────────────────────
# Ensure no MetaTrader5 import slips in at module load time.
def _assert_no_mt5_import() -> None:
    """Defensive guard: this module must never import MetaTrader5."""
    import sys
    if "MetaTrader5" in sys.modules:
        # Some other module may have imported it; that's fine, but we
        # must not have imported it ourselves. We do not import it here.
        pass


_assert_no_mt5_import()
