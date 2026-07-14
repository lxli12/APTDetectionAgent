"""PIDS identity, capability, configuration, and threshold contracts.

Requirements: REQ-PIDS-001..004, REQ-CONFIG-002..003,
REQ-CAUSAL-002..004, REQ-ARTIFACT-002.
"""

from __future__ import annotations

from enum import Enum
from pathlib import PurePosixPath

from pydantic import JsonValue, field_validator, model_validator

from .common import (
    AvailabilityStatus,
    DataSplit,
    DetectionUnit,
    ExperimentClass,
    GitSha,
    Identifier,
    PipelineStage,
    Sha256,
    StrictModel,
    Timestamp,
    TransductiveStatus,
)


class PIDSRef(StrictModel):
    pids_id: Identifier
    variant_id: Identifier = "default"

    @field_validator("pids_id", "variant_id")
    @classmethod
    def normalize_identity(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def normalize_orthrus_variants(self) -> "PIDSRef":
        if self.pids_id in {"orthrus_fixed", "orthrus_non_snooped"}:
            raise ValueError("ORTHRUS variants must use pids_id='orthrus'")
        return self


class CheckpointDescriptor(StrictModel):
    format: Identifier
    availability: AvailabilityStatus
    checkpoint_hash: Sha256 | None = None
    relative_path: str | None = None
    unavailable_reason: str | None = None

    @field_validator("relative_path")
    @classmethod
    def relative_safe_path(cls, value: str | None) -> str | None:
        if value is None:
            return value
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("checkpoint path must be relative and traversal-free")
        return value

    @model_validator(mode="after")
    def availability_fields_agree(self) -> "CheckpointDescriptor":
        if self.availability == AvailabilityStatus.AVAILABLE:
            if not self.checkpoint_hash or not self.relative_path:
                raise ValueError("available checkpoint requires hash and relative path")
            if self.unavailable_reason:
                raise ValueError("available checkpoint cannot have unavailable_reason")
        elif self.availability in {
            AvailabilityStatus.UNAVAILABLE,
            AvailabilityStatus.BLOCKED,
        } and not self.unavailable_reason:
            raise ValueError("unavailable or blocked checkpoint requires unavailable_reason")
        return self


class ConfigParameter(StrictModel):
    name: Identifier
    value_type: Identifier
    allowed_values: tuple[JsonValue, ...] = ()
    configurable_by_agent: bool = False


class PIDSCapability(StrictModel):
    pids: PIDSRef
    implementation_path: str
    source_config_id: Identifier
    source_path: str
    source_semantics: str
    supported_datasets: tuple[Identifier, ...]
    required_pipeline_stages: tuple[PipelineStage, ...]
    detection_unit: DetectionUnit
    training_support: bool
    inference_support: bool
    checkpoint: CheckpointDescriptor
    configurable_modules: tuple[Identifier, ...] = ()
    configurable_parameters: tuple[ConfigParameter, ...] = ()
    threshold_semantics: str
    cpu_supported: bool
    gpu_required: bool
    expected_outputs: tuple[Identifier, ...]
    known_compatibility_limitations: tuple[str, ...] = ()
    transductive_status: TransductiveStatus
    compatibility_status: Identifier
    current_availability_status: AvailabilityStatus
    unavailable_reason: str | None = None
    pidsmaker_commit: GitSha

    @field_validator("implementation_path", "source_path")
    @classmethod
    def repository_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("source paths must be repository-relative")
        return value

    @model_validator(mode="after")
    def availability_has_reason(self) -> "PIDSCapability":
        if self.current_availability_status in {
            AvailabilityStatus.UNAVAILABLE,
            AvailabilityStatus.BLOCKED,
        }:
            if not self.unavailable_reason:
                raise ValueError("unavailable or blocked PIDS must remain registered with a reason")
        elif self.unavailable_reason:
            raise ValueError("only unavailable PIDS may carry unavailable_reason")
        return self


class ApprovedConfig(StrictModel):
    config_id: Identifier
    pids: PIDSRef
    source_config_id: Identifier
    dataset_id: Identifier
    parameters: dict[str, JsonValue]
    required_pipeline_stages: tuple[PipelineStage, ...]
    checkpoint_hash: Sha256 | None = None
    experiment_class: ExperimentClass
    transductive_status: TransductiveStatus
    frozen_at: Timestamp
    code_commit: GitSha
    approved_splits: frozenset[DataSplit]

    @model_validator(mode="after")
    def causal_main_is_causal(self) -> "ApprovedConfig":
        if self.experiment_class == ExperimentClass.CAUSAL_MAIN:
            if self.transductive_status != TransductiveStatus.CAUSAL:
                raise ValueError("causal main config cannot be transductive or unknown")
        if DataSplit.HELD_OUT in self.approved_splits and not self.frozen_at:
            raise ValueError("held-out config must be frozen")
        return self


class CalibrationMethod(str, Enum):
    MODEL_FIXED = "model_fixed"
    LITERATURE_FIXED = "literature_fixed"
    VALIDATION_QUANTILE = "validation_quantile"
    VALIDATION_COVERAGE = "validation_coverage"


class ThresholdSourceSplit(str, Enum):
    TRAINING = "training"
    VALIDATION = "validation"
    LITERATURE = "literature"


class ThresholdProvenance(StrictModel):
    threshold_id: Identifier
    value: float
    calibration_method: CalibrationMethod
    source_dataset: Identifier
    source_split: ThresholdSourceSplit
    checkpoint_hash: Sha256
    target_metric: Identifier
    created_at: Timestamp
    code_commit: GitSha

    @model_validator(mode="after")
    def method_matches_source(self) -> "ThresholdProvenance":
        validation_methods = {
            CalibrationMethod.VALIDATION_QUANTILE,
            CalibrationMethod.VALIDATION_COVERAGE,
        }
        if self.calibration_method in validation_methods:
            if self.source_split != ThresholdSourceSplit.VALIDATION:
                raise ValueError("validation calibration must use validation split")
        if self.calibration_method == CalibrationMethod.LITERATURE_FIXED:
            if self.source_split != ThresholdSourceSplit.LITERATURE:
                raise ValueError("literature threshold must identify literature source")
        return self
