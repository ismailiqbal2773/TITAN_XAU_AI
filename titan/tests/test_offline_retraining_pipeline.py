"""TITAN XAU AI - Sprint 9.9.3.37 Offline Retraining Pipeline Tests"""
from __future__ import annotations
import inspect, json, sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from titan.production.offline_retraining_pipeline import (
    OfflineRetrainingPipeline, RetrainingJobSpec, RetrainingJobResult,
    RetrainingTrigger, RetrainingJobStatus,
)


class TestEnums:
    def test_01_all_triggers_present(self):
        triggers = [t.value for t in RetrainingTrigger]
        for t in ["SCHEDULED", "PERFORMANCE_DECAY", "CALIBRATION_DRIFT",
                  "REGIME_SHIFT", "BROKER_DEGRADATION", "MANUAL_OPERATOR_REQUEST"]:
            assert t in triggers

    def test_02_all_statuses_present(self):
        statuses = [s.value for s in RetrainingJobStatus]
        for s in ["PLANNED", "BLOCKED", "READY_FOR_OFFLINE_TRAINING",
                  "TRAINING_DISABLED", "CANDIDATE_REGISTERED",
                  "FAILED_VALIDATION", "NEEDS_REVIEW"]:
            assert s in statuses


class TestJobSpecDefaults:
    def test_03_dry_run_defaults_true(self):
        spec = RetrainingJobSpec(
            job_id="j1",
            trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
            symbol="XAUUSD",
            timeframe="H1",
            dataset_manifest_path="/data/manifest.json",
            feature_set_id="fs_v1",
            label_policy_id="lp_v1",
            champion_model_id="champ_v1",
            requested_by="operator",
        )
        assert spec.dry_run is True

    def test_04_training_enabled_defaults_false(self):
        spec = RetrainingJobSpec(
            job_id="j1",
            trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
            symbol="XAUUSD",
            timeframe="H1",
            dataset_manifest_path="/data/manifest.json",
            feature_set_id="fs_v1",
            label_policy_id="lp_v1",
            champion_model_id="champ_v1",
            requested_by="operator",
        )
        assert spec.training_enabled is False

    def test_05_dry_run_forced_true_even_if_set_false(self):
        spec = RetrainingJobSpec(
            job_id="j1",
            trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
            symbol="XAUUSD",
            timeframe="H1",
            dataset_manifest_path="/data/manifest.json",
            feature_set_id="fs_v1",
            label_policy_id="lp_v1",
            champion_model_id="champ_v1",
            requested_by="operator",
            dry_run=False,  # try to override
        )
        # __post_init__ forces True
        assert spec.dry_run is True

    def test_06_training_enabled_forced_false_even_if_set_true(self):
        spec = RetrainingJobSpec(
            job_id="j1",
            trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
            symbol="XAUUSD",
            timeframe="H1",
            dataset_manifest_path="/data/manifest.json",
            feature_set_id="fs_v1",
            label_policy_id="lp_v1",
            champion_model_id="champ_v1",
            requested_by="operator",
            training_enabled=True,  # try to override
        )
        # __post_init__ forces False
        assert spec.training_enabled is False


class TestJobResultInvariants:
    def test_07_champion_replaced_always_false(self):
        result = RetrainingJobResult(
            job_id="j1",
            status=RetrainingJobStatus.CANDIDATE_REGISTERED,
            champion_replaced=True,  # try to override
        )
        # __post_init__ forces False
        assert result.champion_replaced is False

    def test_08_training_executed_always_false(self):
        result = RetrainingJobResult(
            job_id="j1",
            status=RetrainingJobStatus.CANDIDATE_REGISTERED,
            training_executed=True,  # try to override
        )
        # __post_init__ forces False
        assert result.training_executed is False


class TestDatasetManifestValidation:
    def test_09_missing_dataset_manifest_blocks(self, tmp_path):
        pipeline = OfflineRetrainingPipeline()
        spec = RetrainingJobSpec(
            job_id="j1",
            trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
            symbol="XAUUSD",
            timeframe="H1",
            dataset_manifest_path=str(tmp_path / "nonexistent.json"),
            feature_set_id="fs_v1",
            label_policy_id="lp_v1",
            champion_model_id="champ_v1",
            requested_by="operator",
        )
        ok, blockers, warnings = pipeline.validate_job_spec(spec)
        assert ok is False
        assert any("manifest" in b.lower() for b in blockers)

    def test_10_valid_dataset_manifest_passes(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "dataset_id": "ds_1",
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "rows": 10000,
            "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "train_test_split": {
                "train_start": "2024-01-01",
                "train_end": "2024-09-30",
                "test_start": "2024-10-01",
                "test_end": "2024-12-31",
            },
            "leakage_check_status": "PASS",
        }))
        pipeline = OfflineRetrainingPipeline()
        ok, blockers = pipeline.validate_dataset_manifest(str(manifest_path))
        assert ok is True
        assert len(blockers) == 0

    def test_11_manifest_missing_train_test_split_blocks(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "dataset_id": "ds_1",
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "rows": 10000,
            "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "leakage_check_status": "PASS",
            # missing train_test_split
        }))
        pipeline = OfflineRetrainingPipeline()
        ok, blockers = pipeline.validate_dataset_manifest(str(manifest_path))
        assert ok is False
        assert any("train_test_split" in b for b in blockers)

    def test_12_manifest_leakage_check_fail_blocks(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "dataset_id": "ds_1",
            "symbol": "XAUUSD",
            "timeframe": "H1",
            "rows": 10000,
            "date_range": {"start": "2024-01-01", "end": "2024-12-31"},
            "train_test_split": {"train_start": "x", "train_end": "y", "test_start": "z", "test_end": "w"},
            "leakage_check_status": "FAIL",
        }))
        pipeline = OfflineRetrainingPipeline()
        ok, blockers = pipeline.validate_dataset_manifest(str(manifest_path))
        assert ok is False
        assert any("leakage_check_status" in b for b in blockers)


class TestChampionReferenceValidation:
    def test_13_missing_champion_warns_in_non_strict(self):
        pipeline = OfflineRetrainingPipeline(strict_mode=False)
        ok, warnings, blockers = pipeline.validate_champion_reference("")
        assert ok is True
        assert any("champion_model_id" in w for w in warnings)

    def test_14_missing_champion_blocks_in_strict(self):
        pipeline = OfflineRetrainingPipeline(strict_mode=True)
        ok, warnings, blockers = pipeline.validate_champion_reference("")
        assert ok is False
        assert any("champion_model_id" in b for b in blockers)


class TestCandidateRegistration:
    def test_15_candidate_registers_as_candidate(self):
        pipeline = OfflineRetrainingPipeline()
        spec = RetrainingJobSpec(
            job_id="j1",
            trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
            symbol="XAUUSD",
            timeframe="H1",
            dataset_manifest_path="/data/manifest.json",
            feature_set_id="fs_v1",
            label_policy_id="lp_v1",
            champion_model_id="champ_v1",
            requested_by="operator",
        )
        stage, warnings, blockers = pipeline.register_candidate_metadata(
            spec, candidate_model_id="cand_v1"
        )
        assert stage == "CANDIDATE"
        assert len(blockers) == 0

    def test_16_submit_to_registry_registers_as_candidate(self):
        from titan.production.model_registry import ModelRegistry
        pipeline = OfflineRetrainingPipeline()
        spec = RetrainingJobSpec(
            job_id="j1",
            trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
            symbol="XAUUSD",
            timeframe="H1",
            dataset_manifest_path="/data/manifest.json",
            feature_set_id="fs_v1",
            label_policy_id="lp_v1",
            champion_model_id="champ_v1",
            requested_by="operator",
        )
        registry = ModelRegistry()
        ok, warnings, blockers = pipeline.submit_to_registry(
            registry, spec, candidate_model_id="cand_v1"
        )
        assert ok is True
        assert len(blockers) == 0
        m = registry.get_model("cand_v1")
        assert m is not None
        assert m.stage.value == "CANDIDATE"


class TestRunDryJob:
    def test_17_valid_job_becomes_ready_or_disabled_metadata_only(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "dataset_id": "ds_1", "symbol": "XAUUSD", "timeframe": "H1",
            "rows": 10000, "date_range": {"start": "x", "end": "y"},
            "train_test_split": {"train_start": "x", "train_end": "y", "test_start": "z", "test_end": "w"},
            "leakage_check_status": "PASS",
        }))
        pipeline = OfflineRetrainingPipeline()
        spec = pipeline.create_job_spec(
            job_id="j1",
            trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
            symbol="XAUUSD", timeframe="H1",
            dataset_manifest_path=str(manifest_path),
            feature_set_id="fs_v1", label_policy_id="lp_v1",
            champion_model_id="champ_v1", requested_by="operator",
        )
        result = pipeline.run_dry_job(spec)
        assert result.status in (
            RetrainingJobStatus.TRAINING_DISABLED,
            RetrainingJobStatus.READY_FOR_OFFLINE_TRAINING,
            RetrainingJobStatus.CANDIDATE_REGISTERED,
        )
        assert result.training_executed is False
        assert result.champion_replaced is False

    def test_18_dry_job_with_registry_registers_candidate(self, tmp_path):
        from titan.production.model_registry import ModelRegistry
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "dataset_id": "ds_1", "symbol": "XAUUSD", "timeframe": "H1",
            "rows": 10000, "date_range": {"start": "x", "end": "y"},
            "train_test_split": {"train_start": "x", "train_end": "y", "test_start": "z", "test_end": "w"},
            "leakage_check_status": "PASS",
        }))
        pipeline = OfflineRetrainingPipeline()
        spec = pipeline.create_job_spec(
            job_id="j1",
            trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
            symbol="XAUUSD", timeframe="H1",
            dataset_manifest_path=str(manifest_path),
            feature_set_id="fs_v1", label_policy_id="lp_v1",
            champion_model_id="champ_v1", requested_by="operator",
        )
        registry = ModelRegistry()
        result = pipeline.run_dry_job(spec, registry=registry, candidate_model_id="cand_v1")
        assert result.status == RetrainingJobStatus.CANDIDATE_REGISTERED
        assert result.registry_updated is True
        assert result.registered_stage == "CANDIDATE"
        assert result.champion_replaced is False
        assert result.training_executed is False
        # Verify the model is in the registry
        m = registry.get_model("cand_v1")
        assert m is not None

    def test_19_invalid_job_blocks(self):
        pipeline = OfflineRetrainingPipeline()
        spec = pipeline.create_job_spec(
            job_id="j1",
            trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
            symbol="XAUUSD", timeframe="H1",
            dataset_manifest_path="/nonexistent/manifest.json",  # missing
            feature_set_id="fs_v1", label_policy_id="lp_v1",
            champion_model_id="champ_v1", requested_by="operator",
        )
        result = pipeline.run_dry_job(spec)
        assert result.status == RetrainingJobStatus.BLOCKED
        assert len(result.blockers) >= 1
        assert result.training_executed is False
        assert result.champion_replaced is False


class TestSafetyInvariants:
    def _strip_docstrings(self, src: str) -> str:
        """Remove docstrings AND string literals to check actual code only."""
        import re
        # Remove triple-quoted strings (both """ and ''')
        src = re.sub(r'"""[\s\S]*?"""', '""', src)
        src = re.sub(r"'''[\s\S]*?'''", "''", src)
        # Remove single-line double-quoted strings
        src = re.sub(r'"(?:[^"\\]|\\.)*"', '""', src)
        # Remove single-line single-quoted strings
        src = re.sub(r"'(?:[^'\\]|\\.)*'", "''", src)
        # Remove single-line comments
        lines = []
        for line in src.splitlines():
            in_str = False
            quote_char = None
            result = []
            i = 0
            while i < len(line):
                c = line[i]
                if in_str:
                    if c == quote_char and (i == 0 or line[i-1] != '\\'):
                        in_str = False
                        quote_char = None
                    result.append(c)
                else:
                    if c in ('"', "'"):
                        in_str = True
                        quote_char = c
                        result.append(c)
                    elif c == '#':
                        break  # rest of line is comment
                    else:
                        result.append(c)
                i += 1
            lines.append(''.join(result))
        return '\n'.join(lines)

    def test_20_no_metatrader5_import(self):
        from titan.production import offline_retraining_pipeline
        src = inspect.getsource(offline_retraining_pipeline)
        assert "import MetaTrader5" not in src
        assert "from MetaTrader5" not in src

    def test_21_no_order_send_calls(self):
        import re
        from titan.production import offline_retraining_pipeline
        src = self._strip_docstrings(inspect.getsource(offline_retraining_pipeline))
        call_pattern = r"\b(mt5\.order_send|adapter\.send_open_order|adapter\.send_order|send_close_order)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found execution calls: {matches}"

    def test_22_no_model_training_execution(self):
        import re
        from titan.production import offline_retraining_pipeline
        src = self._strip_docstrings(inspect.getsource(offline_retraining_pipeline))
        # Check for actual code calls only (docstrings stripped)
        call_pattern = r"\b(\w+\.fit|train_model|retrain|run_hpo)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found training calls: {matches}"

    def test_23_no_pickle_joblib_torch_load(self):
        import re
        from titan.production import offline_retraining_pipeline
        src = self._strip_docstrings(inspect.getsource(offline_retraining_pipeline))
        assert "import pickle" not in src
        assert "import joblib" not in src
        assert "import torch" not in src
        call_pattern = r"\b(pickle\.(load|dump)|joblib\.(load|dump)|torch\.(load|save))\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found pickle/joblib/torch calls: {matches}"

    def test_24_no_champion_replacement(self):
        import re
        from titan.production import offline_retraining_pipeline
        src = self._strip_docstrings(inspect.getsource(offline_retraining_pipeline))
        # Check for actual method calls only (docstrings stripped)
        call_pattern = r"\b(require_manual_champion_promotion|promote_to_challenger)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found champion promotion calls: {matches}"
        # No artifact manipulation
        assert "shutil.copy" not in src
        assert "shutil.move" not in src
        assert "os.replace" not in src

    def test_25_no_runtime_config_modification(self):
        from titan.production import offline_retraining_pipeline
        src = self._strip_docstrings(inspect.getsource(offline_retraining_pipeline))
        assert "runtime.yaml" not in src
        assert "config/runtime" not in src

    def test_26_no_demo_micro_execute(self):
        import re
        from titan.production import offline_retraining_pipeline
        src = self._strip_docstrings(inspect.getsource(offline_retraining_pipeline))
        assert "import demo_micro_execute" not in src
        assert "from demo_micro_execute" not in src
        call_pattern = r"\b(DEMO_MICRO_EXECUTE|run_demo_micro)\s*\("
        matches = re.findall(call_pattern, src)
        assert len(matches) == 0, f"Found demo micro execute calls: {matches}"

    def test_27_block_if_training_disabled_always_blocks(self):
        pipeline = OfflineRetrainingPipeline()
        spec = RetrainingJobSpec(
            job_id="j1", trigger=RetrainingTrigger.MANUAL_OPERATOR_REQUEST,
            symbol="XAUUSD", timeframe="H1",
            dataset_manifest_path="/data/m.json",
            feature_set_id="fs", label_policy_id="lp",
            champion_model_id="ch", requested_by="op",
        )
        ok, reason = pipeline.block_if_training_disabled(spec)
        assert ok is False
        assert len(reason) >= 1
