"""
TITAN XAU AI — BrokerScoringEngine unit tests (Sprint 9.9.3.45.8.5)
=====================================================================

Pure-Python tests. No MT5 imports, no order_send calls. Verifies that
the broker scoring engine loads the YAML config, scores every broker
0-100 across 14 weighted dimensions, and produces the correct tri-state
verdict.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.broker_scoring_engine import (
    BrokerScoringEngine,
    BrokerScoreResult,
    SCORE_COMPONENTS,
    DEFAULT_WEIGHTS,
    SAFETY_FLAGS,
    BROKER_APPROVED,
    BROKER_CAUTION,
    BROKER_BLOCKED,
    APPROVED_THRESHOLD,
    CAUTION_THRESHOLD,
    BROKER_ID_TO_HISTORICAL_SOURCE,
)
from scripts.audit.broker_score_audit import (
    ALL_AUDIT_VERDICTS,
    BROKER_SCORING_READY,
    BROKER_SCORING_NEEDS_WORK,
    BROKER_SCORING_BLOCKED,
)


# ─── Test fixtures ─────────────────────────────────────────────────────────
BROKER_PROFILES_YAML = REPO_ROOT / "config" / "broker_profiles.yaml"
HISTORICAL_CSV = (
    REPO_ROOT
    / "data"
    / "audit"
    / "frozen_balanced_validation"
    / "broker_validation.csv"
)


@pytest.fixture
def engine() -> BrokerScoringEngine:
    return BrokerScoringEngine(
        profiles_path=BROKER_PROFILES_YAML,
        historical_csv=HISTORICAL_CSV if HISTORICAL_CSV.exists() else None,
    )


@pytest.fixture
def tmp_engine(tmp_path: Path) -> BrokerScoringEngine:
    """Engine backed by a small in-process YAML for deterministic tests."""
    yaml_doc = {
        "brokers": {
            "test_broker_a": {
                "broker_id": "test_broker_a",
                "name": "Test Broker A",
                "server": "Test-Server-A",
                "account_type": "live",
                "typical_spread_xauusd": 0.18,
                "max_spread_xauusd": 0.30,
                "commission_per_lot_round_turn": 3.0,
                "typical_slippage_xauusd": 0.01,
                "max_slippage_xauusd": 0.05,
                "swap_long_xauusd_per_lot_per_night": -2.0,
                "swap_short_xauusd_per_lot_per_night": -0.8,
                "contract_size_xauusd": 100,
                "stops_level_points_xauusd": 20,
                "freeze_level_points_xauusd": 0,
                "filling_mode": "ORDER_FILLING_IOC",
                "margin_currency": "USD",
                "min_lot": 0.01,
                "max_lot": 100.0,
                "lot_step": 0.01,
                "leverage_options": [100, 200, 500],
            },
            "test_broker_b": {
                "broker_id": "test_broker_b",
                "name": "Test Broker B (poor)",
                "server": "Test-Server-B",
                "account_type": "live",
                "typical_spread_xauusd": 2.5,
                "max_spread_xauusd": 4.0,
                "commission_per_lot_round_turn": 12.0,
                "typical_slippage_xauusd": 0.18,
                "max_slippage_xauusd": 0.30,
                "swap_long_xauusd_per_lot_per_night": -6.0,
                "swap_short_xauusd_per_lot_per_night": -3.0,
                "contract_size_xauusd": 100,
                "stops_level_points_xauusd": 90,
                "freeze_level_points_xauusd": 20,
                "filling_mode": "ORDER_FILLING_RETURN",
                "margin_currency": "USD",
                "min_lot": 0.10,
                "max_lot": 50.0,
                "lot_step": 0.10,
                "leverage_options": [30],
            },
        }
    }
    yaml_path = tmp_path / "broker_profiles.yaml"
    yaml_path.write_text(yaml.safe_dump(yaml_doc), encoding="utf-8")
    return BrokerScoringEngine(profiles_path=yaml_path, historical_csv=None)


# ════════════════════════════════════════════════════════════════════════════
# 1. Import / module structure
# ════════════════════════════════════════════════════════════════════════════
def _module_ast(filepath: Path):
    """Parse a Python module's source into an AST."""
    import ast
    src = filepath.read_text(encoding="utf-8")
    return ast.parse(src), src


def _ast_has_mt5_import(tree) -> bool:
    """True if AST contains `import MetaTrader5` or `from MetaTrader5`."""
    import ast
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "MetaTrader5":
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "MetaTrader5":
                return True
    return False


def _ast_has_order_send_call(tree) -> bool:
    """True if AST contains any attribute access ending in order_send()."""
    import ast
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "order_send":
            return True
    return False


class TestBrokerScoringEngineImports:
    def test_01_engine_imports(self):
        """BrokerScoringEngine and BrokerScoreResult must import cleanly."""
        assert BrokerScoringEngine is not None
        assert BrokerScoreResult is not None

    def test_02_no_mt5_import_in_module(self):
        """The broker_scoring_engine module must never import MetaTrader5."""
        import titan.production.broker_scoring_engine as mod
        tree, _ = _module_ast(Path(mod.__file__))
        assert not _ast_has_mt5_import(tree), (
            "broker_scoring_engine.py imports MetaTrader5"
        )

    def test_03_no_order_send_call_in_module_source(self):
        """Source must not contain any order_send() call."""
        import titan.production.broker_scoring_engine as mod
        tree, _ = _module_ast(Path(mod.__file__))
        assert not _ast_has_order_send_call(tree), (
            "broker_scoring_engine.py calls order_send"
        )


# ════════════════════════════════════════════════════════════════════════════
# 2. Score components
# ════════════════════════════════════════════════════════════════════════════
class TestScoreComponents:
    def test_04_all_required_score_components_present(self):
        """All 14 required score components must be declared."""
        required = {
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
        }
        assert required.issubset(set(SCORE_COMPONENTS))
        assert len(SCORE_COMPONENTS) == 14

    def test_05_result_has_all_component_fields(self, engine: BrokerScoringEngine):
        """BrokerScoreResult must contain all 14 component scores."""
        result = engine.score_broker("metaquotes_demo")
        for comp in SCORE_COMPONENTS:
            assert comp in result.components, (
                f"missing component {comp} in result"
            )
            assert 0.0 <= result.components[comp] <= 100.0, (
                f"component {comp} out of range: {result.components[comp]}"
            )

    def test_06_weights_sum_to_one(self):
        """Component weights must sum to ~1.0."""
        total = sum(DEFAULT_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-6, f"weights sum to {total}, not 1.0"

    def test_07_result_has_all_top_level_fields(self, engine: BrokerScoringEngine):
        """BrokerScoreResult must have all required top-level fields."""
        result = engine.score_broker("metaquotes_demo")
        assert hasattr(result, "broker_id")
        assert hasattr(result, "broker_name")
        assert hasattr(result, "server")
        assert hasattr(result, "account_type")
        assert hasattr(result, "score")
        assert hasattr(result, "verdict")
        assert hasattr(result, "components")
        assert hasattr(result, "weights")
        assert hasattr(result, "prop_funded_compatible")
        assert hasattr(result, "historical_source")
        assert hasattr(result, "historical_verdict")
        assert hasattr(result, "notes")
        assert hasattr(result, "no_martingale")
        assert hasattr(result, "no_grid")
        assert hasattr(result, "no_averaging")


# ════════════════════════════════════════════════════════════════════════════
# 3. Scoring and verdicts
# ════════════════════════════════════════════════════════════════════════════
class TestScoring:
    def test_08_metaquotes_demo_scored(self, engine: BrokerScoringEngine):
        """metaquotes_demo must be present and produce a valid result."""
        result = engine.score_broker("metaquotes_demo")
        assert result.broker_id == "metaquotes_demo"
        assert result.broker_name == "MetaQuotes-Demo"
        assert result.server == "MetaQuotes-Demo"
        assert result.account_type == "demo"

    def test_09_score_range_0_to_100(self, engine: BrokerScoringEngine):
        """Every broker score must be in [0, 100]."""
        for bid in engine.list_brokers():
            result = engine.score_broker(bid)
            assert 0.0 <= result.score <= 100.0, (
                f"{bid} score {result.score} out of [0,100]"
            )

    def test_10_verdict_thresholds_approved(self, tmp_path: Path):
        """A broker scoring >= 85 must receive BROKER_APPROVED."""
        eng = _build_engine_with_score(tmp_path, target_score=90.0)
        # Force a high score by using a perfect profile.
        result = eng.score_broker("perfect_broker")
        assert result.score >= APPROVED_THRESHOLD
        assert result.verdict == BROKER_APPROVED

    def test_11_verdict_thresholds_caution(self, tmp_path: Path):
        """A broker scoring 70-84 must receive BROKER_CAUTION."""
        eng = _build_engine_with_score(tmp_path, target_score=75.0)
        result = eng.score_broker("mid_broker")
        assert CAUTION_THRESHOLD <= result.score < APPROVED_THRESHOLD
        assert result.verdict == BROKER_CAUTION

    def test_12_verdict_thresholds_blocked(self, tmp_engine: BrokerScoringEngine):
        """A broker scoring < 70 must receive BROKER_BLOCKED."""
        result = tmp_engine.score_broker("test_broker_b")
        assert result.score < CAUTION_THRESHOLD
        assert result.verdict == BROKER_BLOCKED

    def test_13_verdict_thresholds_boundary_values(self):
        """Verdict thresholds: approved=85, caution=70."""
        assert APPROVED_THRESHOLD == 85.0
        assert CAUTION_THRESHOLD == 70.0

    def test_14_score_all_brokers(self, engine: BrokerScoringEngine):
        """score_all_brokers must return a dict keyed by broker_id."""
        results = engine.score_all_brokers()
        assert isinstance(results, dict)
        assert len(results) >= 4  # YAML has at least 4 brokers
        for bid, result in results.items():
            assert isinstance(result, BrokerScoreResult)
            assert result.broker_id == bid


# ════════════════════════════════════════════════════════════════════════════
# 4. Prop-funded compatibility & net expectancy
# ════════════════════════════════════════════════════════════════════════════
class TestPropFundedAndNetExpectancy:
    def test_15_prop_funded_compatible_field_present(self, engine: BrokerScoringEngine):
        """prop_funded_compatible boolean must always be set."""
        for bid in engine.list_brokers():
            result = engine.score_broker(bid)
            assert isinstance(result.prop_funded_compatible, bool)

    def test_16_prop_funded_compatible_for_ic_markets(self, engine: BrokerScoringEngine):
        """IC Markets Standard has tight execution and should be prop-compatible."""
        result = engine.score_broker("ic_markets_standard")
        assert isinstance(result.prop_funded_compatible, bool)
        # IC Markets Standard has tight spread (0.25), commission 7.0,
        # stop level 50, IOC, lot_step 0.01 → should be compatible.
        assert result.prop_funded_compatible is True

    def test_17_net_expectancy_impact_computed(self, engine: BrokerScoringEngine):
        """net_expectancy_impact_score must be a number 0-100."""
        for bid in engine.list_brokers():
            result = engine.score_broker(bid)
            net = result.components.get("net_expectancy_impact_score")
            assert net is not None
            assert 0.0 <= net <= 100.0


# ════════════════════════════════════════════════════════════════════════════
# 5. Profile loading and error handling
# ════════════════════════════════════════════════════════════════════════════
class TestProfileLoading:
    def test_18_broker_profile_loading(self, engine: BrokerScoringEngine):
        """Engine must load all 4 brokers from the shipped YAML."""
        brokers = engine.list_brokers()
        assert "metaquotes_demo" in brokers
        assert "ic_markets_standard" in brokers
        assert "ftmo_prop" in brokers
        assert "institutional_ecn" in brokers
        assert len(brokers) == 4

    def test_19_missing_broker_raises_keyerror(self, engine: BrokerScoringEngine):
        """Scoring an unknown broker must raise KeyError."""
        with pytest.raises(KeyError):
            engine.score_broker("does_not_exist_xyz")

    def test_20_missing_yaml_raises_filenotfound(self, tmp_path: Path):
        """Loading a non-existent YAML must raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            BrokerScoringEngine(
                profiles_path=tmp_path / "nonexistent.yaml",
                historical_csv=None,
            )


# ════════════════════════════════════════════════════════════════════════════
# 6. Historical validation
# ════════════════════════════════════════════════════════════════════════════
class TestHistoricalValidation:
    def test_21_historical_validation_considered(self, engine: BrokerScoringEngine):
        """Historical validation CSV must be loaded (if present)."""
        if HISTORICAL_CSV.exists():
            assert len(engine._historical) >= 4  # at least 4 sources
            # canonical is the MetaQuotes-Demo historical source
            assert "canonical" in engine._historical
            assert "exness" in engine._historical
            assert "icmarkets" in engine._historical

    def test_22_historical_validation_score_for_metaquotes(
        self, engine: BrokerScoringEngine
    ):
        """metaquotes_demo maps to canonical which has PASS → score=100."""
        if HISTORICAL_CSV.exists():
            result = engine.score_broker("metaquotes_demo")
            hist_score = result.components.get(
                "historical_validation_score", 0.0
            )
            assert hist_score == 100.0

    def test_23_historical_source_mapping(self):
        """BROKER_ID_TO_HISTORICAL_SOURCE must map known YAML ids."""
        assert (
            BROKER_ID_TO_HISTORICAL_SOURCE["metaquotes_demo"] == "canonical"
        )
        assert (
            BROKER_ID_TO_HISTORICAL_SOURCE["ic_markets_standard"]
            == "icmarkets"
        )


# ════════════════════════════════════════════════════════════════════════════
# 7. Safety invariants
# ════════════════════════════════════════════════════════════════════════════
class TestSafetyInvariants:
    def test_24_safety_flags_all_true(self):
        """SAFETY_FLAGS must declare no_martingale/no_grid/no_averaging True."""
        assert SAFETY_FLAGS["no_martingale"] is True
        assert SAFETY_FLAGS["no_grid"] is True
        assert SAFETY_FLAGS["no_averaging"] is True

    def test_25_result_safety_fields_all_true(self, engine: BrokerScoringEngine):
        """Every BrokerScoreResult must carry no_martingale/no_grid/no_averaging True."""
        for bid in engine.list_brokers():
            result = engine.score_broker(bid)
            assert result.no_martingale is True, f"{bid} no_martingale=False"
            assert result.no_grid is True, f"{bid} no_grid=False"
            assert result.no_averaging is True, f"{bid} no_averaging=False"

    def test_26_no_martingale_grid_averaging_in_engine_source(self):
        """Engine source must declare no martingale/grid/averaging."""
        import titan.production.broker_scoring_engine as mod
        src = inspect.getsource(mod)
        # Safety flags must be declared in source.
        assert "no_martingale" in src
        assert "no_grid" in src
        assert "no_averaging" in src
        # Negative guards — these strategy primitives must NOT appear as
        # actual code constructs (only in docstrings/comments is OK).
        # We check via AST: no function or attribute named *_multiplier
        # / grid_spacing / averaging_step.
        import ast
        tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        forbidden_attrs = {
            "martingale_multiplier",
            "grid_spacing",
            "averaging_step",
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden_attrs, (
                    f"forbidden attribute {node.attr} found"
                )
            if isinstance(node, ast.FunctionDef):
                assert node.name not in forbidden_attrs, (
                    f"forbidden function {node.name} found"
                )


# ════════════════════════════════════════════════════════════════════════════
# 8. Audit verdicts (cross-namespace)
# ════════════════════════════════════════════════════════════════════════════
class TestAuditVerdicts:
    def test_27_audit_verdicts_supported(self):
        """All three audit verdicts must be declared."""
        assert BROKER_SCORING_READY in ALL_AUDIT_VERDICTS
        assert BROKER_SCORING_NEEDS_WORK in ALL_AUDIT_VERDICTS
        assert BROKER_SCORING_BLOCKED in ALL_AUDIT_VERDICTS
        assert len(ALL_AUDIT_VERDICTS) == 3


# ─── Helpers ────────────────────────────────────────────────────────────────
def _build_engine_with_score(
    tmp_path: Path,
    target_score: float,
) -> BrokerScoringEngine:
    """Build an engine with one broker tuned to roughly the target score."""
    if target_score >= 85.0:
        # Perfect broker → near-100 score.
        broker_doc = {
            "broker_id": "perfect_broker",
            "name": "Perfect Broker",
            "server": "Perfect-Server",
            "account_type": "live",
            "typical_spread_xauusd": 0.10,
            "max_spread_xauusd": 0.20,
            "commission_per_lot_round_turn": 0.0,
            "typical_slippage_xauusd": 0.0,
            "max_slippage_xauusd": 0.02,
            "swap_long_xauusd_per_lot_per_night": 0.0,
            "swap_short_xauusd_per_lot_per_night": 0.0,
            "contract_size_xauusd": 100,
            "stops_level_points_xauusd": 0,
            "freeze_level_points_xauusd": 0,
            "filling_mode": "ORDER_FILLING_IOC",
            "margin_currency": "USD",
            "min_lot": 0.01,
            "max_lot": 200.0,
            "lot_step": 0.01,
            "leverage_options": [100, 200, 500],
        }
    else:
        # Mid-tier broker → roughly 75.
        broker_doc = {
            "broker_id": "mid_broker",
            "name": "Mid Broker",
            "server": "Mid-Server",
            "account_type": "live",
            "typical_spread_xauusd": 0.40,
            "max_spread_xauusd": 0.60,
            "commission_per_lot_round_turn": 5.0,
            "typical_slippage_xauusd": 0.04,
            "max_slippage_xauusd": 0.10,
            "swap_long_xauusd_per_lot_per_night": -3.0,
            "swap_short_xauusd_per_lot_per_night": -1.0,
            "contract_size_xauusd": 100,
            "stops_level_points_xauusd": 50,
            "freeze_level_points_xauusd": 5,
            "filling_mode": "ORDER_FILLING_IOC",
            "margin_currency": "USD",
            "min_lot": 0.01,
            "max_lot": 100.0,
            "lot_step": 0.01,
            "leverage_options": [100, 200],
        }
    yaml_doc = {"brokers": {broker_doc["broker_id"]: broker_doc}}
    yaml_path = tmp_path / "broker_profiles.yaml"
    yaml_path.write_text(yaml.safe_dump(yaml_doc), encoding="utf-8")
    return BrokerScoringEngine(profiles_path=yaml_path, historical_csv=None)
