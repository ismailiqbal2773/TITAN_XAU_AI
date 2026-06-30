"""
TITAN XAU AI - Offline Retraining Pipeline (Sprint 9.9.3.37)
==============================================================

Offline auto-retraining candidate pipeline. Plans, validates, and registers
retraining candidates WITHOUT replacing the champion model and WITHOUT
touching live/demo execution.

NEVER imports MetaTrader5.
NEVER sends orders.
NEVER loads model binaries (no pickle/joblib/torch.load).
NEVER creates model artifacts (no .fit() / train_model() / retrain() / run_hpo()).
NEVER replaces the champion.
NEVER modifies live runtime config.
NEVER enables live trading.

This module produces retraining job specs and candidate metadata only.
The pipeline can register a CANDIDATE in the ModelRegistry, but every
champion transition must go through ModelRegistry.require_manual_champion_promotion()
with explicit operator approval.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class RetrainingTrigger(str, Enum):
    SCHEDULED = "SCHEDULED"
    PERFORMANCE_DECAY = "PERFORMANCE_DECAY"
    CALIBRATION_DRIFT = "CALIBRATION_DRIFT"
    REGIME_SHIFT = "REGIME_SHIFT"
    BROKER_DEGRADATION = "BROKER_DEGRADATION"
    MANUAL_OPERATOR_REQUEST = "MANUAL_OPERATOR_REQUEST"


class RetrainingJobStatus(str, Enum):
    PLANNED = "PLANNED"
    BLOCKED = "BLOCKED"
    READY_FOR_OFFLINE_TRAINING = "READY_FOR_OFFLINE_TRAINING"
    TRAINING_DISABLED = "TRAINING_DISABLED"
    CANDIDATE_REGISTERED = "CANDIDATE_REGISTERED"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    NEEDS_REVIEW = "NEEDS_REVIEW"


@dataclass
class RetrainingJobSpec:
    job_id: str
    trigger: RetrainingTrigger
    symbol: str
    timeframe: str
    dataset_manifest_path: str
    feature_set_id: str
    label_policy_id: str
    champion_model_id: str
    requested_by: str
    created_utc: str = ""
    dry_run: bool = True                # ALWAYS True by default
    training_enabled: bool = False       # ALWAYS False by default
    notes: str = ""

    def __post_init__(self):
        if not self.created_utc:
            self.created_utc = datetime.now(timezone.utc).isoformat()
        # Safety hard defaults
        self.dry_run = True
        self.training_enabled = False


@dataclass
class RetrainingJobResult:
    job_id: str
    status: RetrainingJobStatus
    candidate_model_id: str = ""
    registered_stage: str = ""
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validation_summary: dict = field(default_factory=dict)
    registry_updated: bool = False
    champion_replaced: bool = False       # ALWAYS False
    training_executed: bool = False       # ALWAYS False
    timestamp_utc: str = ""

    def __post_init__(self):
        if not self.timestamp_utc:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()
        # Hard safety invariants
        self.champion_replaced = False
        self.training_executed = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class OfflineRetrainingPipeline:
    """Offline retraining candidate pipeline.

    Plans, validates, and registers retraining candidates only.
    Never runs real training. Never replaces champion. Never imports MT5.
    """

    def __init__(self, strict_mode: bool = False):
        # strict_mode: missing champion reference blocks; otherwise warns
        self.strict_mode = strict_mode
        self._jobs: dict[str, RetrainingJobSpec] = {}
        self._results: dict[str, RetrainingJobResult] = {}

    # ──────────────────────────────────────────────────────────────────────
    # Job spec creation & validation
    # ──────────────────────────────────────────────────────────────────────

    def create_job_spec(
        self,
        job_id: str,
        trigger: RetrainingTrigger,
        symbol: str,
        timeframe: str,
        dataset_manifest_path: str,
        feature_set_id: str,
        label_policy_id: str,
        champion_model_id: str,
        requested_by: str,
        notes: str = "",
    ) -> RetrainingJobSpec:
        """Create a retraining job spec. dry_run=True, training_enabled=False by default."""
        if job_id in self._jobs:
            raise ValueError(f"Job already exists: {job_id}")
        spec = RetrainingJobSpec(
            job_id=job_id,
            trigger=trigger,
            symbol=symbol,
            timeframe=timeframe,
            dataset_manifest_path=dataset_manifest_path,
            feature_set_id=feature_set_id,
            label_policy_id=label_policy_id,
            champion_model_id=champion_model_id,
            requested_by=requested_by,
            notes=notes,
        )
        self._jobs[job_id] = spec
        return spec

    def get_job(self, job_id: str) -> Optional[RetrainingJobSpec]:
        return self._jobs.get(job_id)

    def get_result(self, job_id: str) -> Optional[RetrainingJobResult]:
        return self._results.get(job_id)

    def validate_job_spec(self, spec: RetrainingJobSpec) -> tuple[bool, list[str], list[str]]:
        """Validate a retraining job spec. Returns (ok, blockers, warnings)."""
        blockers: list[str] = []
        warnings: list[str] = []

        # 1) Dataset manifest
        ok_ds, ds_blockers = self.validate_dataset_manifest(spec.dataset_manifest_path)
        if not ok_ds:
            blockers.extend(ds_blockers)

        # 2) Feature set
        ok_fs, fs_blockers = self.validate_feature_set(spec.feature_set_id)
        if not ok_fs:
            blockers.extend(fs_blockers)

        # 3) Label policy
        ok_lp, lp_blockers = self.validate_label_policy(spec.label_policy_id)
        if not ok_lp:
            blockers.extend(lp_blockers)

        # 4) Champion reference
        ok_ch, ch_warnings, ch_blockers = self.validate_champion_reference(spec.champion_model_id)
        if not ok_ch:
            blockers.extend(ch_blockers)
        warnings.extend(ch_warnings)

        # 5) Required fields
        if not spec.job_id:
            blockers.append("Missing job_id")
        if not spec.symbol:
            blockers.append("Missing symbol")
        if not spec.timeframe:
            blockers.append("Missing timeframe")
        if not spec.requested_by:
            blockers.append("Missing requested_by")

        # 6) Training must be disabled by default
        if spec.training_enabled:
            blockers.append("training_enabled=True is forbidden - retraining is metadata-only in this sprint")

        # 7) dry_run must be True
        if not spec.dry_run:
            blockers.append("dry_run=False is forbidden - retraining is metadata-only in this sprint")

        return len(blockers) == 0, blockers, warnings

    def validate_dataset_manifest(self, manifest_path: str) -> tuple[bool, list[str]]:
        """Validate dataset manifest presence. Does NOT load data files."""
        blockers: list[str] = []
        if not manifest_path:
            blockers.append("Missing dataset_manifest_path")
            return False, blockers
        path = Path(manifest_path)
        if not path.exists():
            blockers.append(f"Dataset manifest not found: {manifest_path}")
            return False, blockers
        # Read manifest metadata only - do NOT load data files
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            # Verify required manifest fields
            required = ["dataset_id", "symbol", "timeframe", "rows", "date_range"]
            for k in required:
                if k not in manifest:
                    blockers.append(f"Dataset manifest missing field: {k}")
            # Anti-leakage check: manifest must declare train/test split
            if "train_test_split" not in manifest:
                blockers.append("Dataset manifest missing train_test_split (anti-leakage requirement)")
            if "leakage_check_status" not in manifest:
                blockers.append("Dataset manifest missing leakage_check_status")
            elif manifest["leakage_check_status"] != "PASS":
                blockers.append(
                    f"Dataset manifest leakage_check_status={manifest['leakage_check_status']} (must be PASS)"
                )
        except json.JSONDecodeError as e:
            blockers.append(f"Dataset manifest invalid JSON: {e}")
        except Exception as e:
            blockers.append(f"Dataset manifest read error: {e}")
        return len(blockers) == 0, blockers

    def validate_feature_set(self, feature_set_id: str) -> tuple[bool, list[str]]:
        """Validate feature set ID format. Does NOT load feature definitions."""
        blockers: list[str] = []
        if not feature_set_id:
            blockers.append("Missing feature_set_id")
        elif not isinstance(feature_set_id, str):
            blockers.append("feature_set_id must be a string")
        elif len(feature_set_id) < 3:
            blockers.append("feature_set_id too short (min 3 chars)")
        return len(blockers) == 0, blockers

    def validate_label_policy(self, label_policy_id: str) -> tuple[bool, list[str]]:
        """Validate label policy ID. Does NOT load label definitions."""
        blockers: list[str] = []
        if not label_policy_id:
            blockers.append("Missing label_policy_id")
        elif not isinstance(label_policy_id, str):
            blockers.append("label_policy_id must be a string")
        elif len(label_policy_id) < 3:
            blockers.append("label_policy_id too short (min 3 chars)")
        return len(blockers) == 0, blockers

    def validate_champion_reference(self, champion_model_id: str) -> tuple[bool, list[str], list[str]]:
        """Validate champion model reference.

        Returns (ok, warnings, blockers).
        In strict_mode: missing champion blocks. Otherwise warns.
        """
        warnings: list[str] = []
        blockers: list[str] = []
        if not champion_model_id:
            msg = "Missing champion_model_id - cannot compare candidate to champion"
            if self.strict_mode:
                blockers.append(msg)
            else:
                warnings.append(msg)
            return len(blockers) == 0, warnings, blockers
        return True, warnings, blockers

    def block_if_training_disabled(self, spec: RetrainingJobSpec) -> tuple[bool, list[str]]:
        """Always blocks training execution. Returns (False, reason)."""
        # Training is NEVER executed by this pipeline.
        return False, ["Training execution is disabled in this pipeline - metadata-only"]

    # ──────────────────────────────────────────────────────────────────────
    # Candidate registration
    # ──────────────────────────────────────────────────────────────────────

    def register_candidate_metadata(
        self,
        spec: RetrainingJobSpec,
        candidate_model_id: str,
        metrics: Optional[dict] = None,
    ) -> tuple[str, list[str], list[str]]:
        """Register candidate metadata only. Returns (registered_stage, warnings, blockers).

        Does NOT create a model artifact. Does NOT load model binaries.
        The candidate is registered as CANDIDATE in the metadata.
        """
        blockers: list[str] = []
        warnings: list[str] = []
        if not candidate_model_id:
            blockers.append("Missing candidate_model_id")
            return "", warnings, blockers
        registered_stage = "CANDIDATE"  # always CANDIDATE
        warnings.append(
            f"Candidate {candidate_model_id} registered as {registered_stage} - "
            "promotion requires manual operator approval via ModelRegistry"
        )
        return registered_stage, warnings, blockers

    def submit_to_registry(
        self,
        registry,
        spec: RetrainingJobSpec,
        candidate_model_id: str,
        artifact_path: str = "",
        metrics: Optional[dict] = None,
    ) -> tuple[bool, list[str], list[str]]:
        """Submit candidate metadata to a ModelRegistry instance.

        The registry stores metadata only - never loads binaries.
        Returns (ok, warnings, blockers).
        """
        blockers: list[str] = []
        warnings: list[str] = []
        try:
            model = registry.register_model(
                model_id=candidate_model_id,
                version="0.1.0",
                artifact_path=artifact_path or f"/data/models/{candidate_model_id}.pkl.meta",
                metrics=metrics or {},
                notes=f"Submitted by retraining job {spec.job_id} (trigger={spec.trigger.value})",
            )
            # Confirm stage is CANDIDATE
            if model.stage.value != "CANDIDATE":
                blockers.append(
                    f"Registry returned stage={model.stage.value} - expected CANDIDATE"
                )
            else:
                warnings.append(f"Candidate registered in registry as CANDIDATE: {candidate_model_id}")
        except ValueError as e:
            blockers.append(f"Registry registration failed: {e}")
        except Exception as e:
            blockers.append(f"Registry submission error: {e}")
        return len(blockers) == 0, warnings, blockers

    # ──────────────────────────────────────────────────────────────────────
    # Dry job execution (metadata-only)
    # ──────────────────────────────────────────────────────────────────────

    def run_dry_job(
        self,
        spec: RetrainingJobSpec,
        registry=None,
        candidate_model_id: Optional[str] = None,
    ) -> RetrainingJobResult:
        """Run a dry retraining job.

        Validates the spec, registers candidate metadata (if registry provided),
        and returns a RetrainingJobResult. Never executes training. Never
        replaces champion.
        """
        # Hard safety: training is always disabled
        ok_train_block, train_block_reason = self.block_if_training_disabled(spec)
        # ok_train_block is always False here

        # Validate the spec
        ok, blockers, warnings = self.validate_job_spec(spec)

        if not ok:
            result = RetrainingJobResult(
                job_id=spec.job_id,
                status=RetrainingJobStatus.BLOCKED,
                blockers=blockers,
                warnings=warnings,
                validation_summary={"ok": False, "blocker_count": len(blockers)},
                registry_updated=False,
                champion_replaced=False,
                training_executed=False,
            )
            self._results[spec.job_id] = result
            return result

        # If training is disabled, status is TRAINING_DISABLED unless registry is provided
        if not spec.training_enabled:
            # Register candidate metadata if registry provided
            registry_updated = False
            registered_stage = ""
            reg_warnings: list[str] = []
            reg_blockers: list[str] = []
            if registry is not None and candidate_model_id:
                registered_stage, reg_warnings, reg_blockers = self.register_candidate_metadata(
                    spec, candidate_model_id
                )
                warnings.extend(reg_warnings)
                blockers.extend(reg_blockers)
                if not reg_blockers:
                    ok_submit, submit_warnings, submit_blockers = self.submit_to_registry(
                        registry, spec, candidate_model_id
                    )
                    warnings.extend(submit_warnings)
                    blockers.extend(submit_blockers)
                    registry_updated = ok_submit and not submit_blockers

            if blockers:
                status = RetrainingJobStatus.FAILED_VALIDATION
            elif registry is not None and candidate_model_id and registry_updated:
                status = RetrainingJobStatus.CANDIDATE_REGISTERED
            else:
                status = RetrainingJobStatus.TRAINING_DISABLED

            result = RetrainingJobResult(
                job_id=spec.job_id,
                status=status,
                candidate_model_id=candidate_model_id or "",
                registered_stage=registered_stage,
                blockers=blockers,
                warnings=warnings,
                validation_summary={
                    "ok": True,
                    "training_enabled": False,
                    "dry_run": True,
                    "registry_updated": registry_updated,
                },
                registry_updated=registry_updated,
                champion_replaced=False,
                training_executed=False,
            )
            self._results[spec.job_id] = result
            return result

        # spec.training_enabled should never be True (validate_job_spec blocks it),
        # but defensive: never reach here.
        result = RetrainingJobResult(
            job_id=spec.job_id,
            status=RetrainingJobStatus.BLOCKED,
            blockers=["training_enabled=True reached execution path - blocked defensively"],
            warnings=warnings,
            validation_summary={"ok": False, "defensive_block": True},
            registry_updated=False,
            champion_replaced=False,
            training_executed=False,
        )
        self._results[spec.job_id] = result
        return result

    def produce_result(self, job_id: str) -> Optional[RetrainingJobResult]:
        """Return the result of a previously-run job."""
        return self._results.get(job_id)

    # ──────────────────────────────────────────────────────────────────────
    # Summary
    # ──────────────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        return {
            "total_jobs": len(self._jobs),
            "total_results": len(self._results),
            "training_enabled_default": False,
            "dry_run_default": True,
            "champion_replacement_allowed": False,
            "model_artifacts_created": 0,
            "training_executed": 0,
        }
