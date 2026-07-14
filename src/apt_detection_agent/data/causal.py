"""Frozen-state and current-window feature boundaries.

Requirements: REQ-CAUSAL-001..004, REQ-WINDOW-004, REQ-LABEL-001.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Callable

from pydantic import Field, model_validator

from apt_detection_agent.schemas.common import (
    DataSplit,
    GitSha,
    Identifier,
    Sha256,
    StrictModel,
    Timestamp,
    TransductiveStatus,
    require_utc_offset,
)
from apt_detection_agent.schemas.evaluation import assert_deployable_payload
from apt_detection_agent.schemas.runtime import TimeWindow


class FittedStateKind(str, Enum):
    VOCABULARY = "vocabulary"
    NORMALIZER = "normalizer"
    IDF = "idf"
    FEATURE_STATISTICS = "feature_statistics"
    FEATURIZER = "featurizer"
    EMBEDDING = "embedding"
    MODEL = "model"
    THRESHOLD = "threshold"


class FittedStateArtifact(StrictModel):
    artifact_id: Identifier
    kind: FittedStateKind
    source_dataset_id: Identifier
    source_split: DataSplit
    fitted_through: Timestamp
    frozen_at: Timestamp
    content_hash: Sha256
    code_commit: GitSha
    transductive_status: TransductiveStatus

    @model_validator(mode="after")
    def training_or_validation_only(self) -> "FittedStateArtifact":
        if self.source_split in {DataSplit.HELD_OUT, DataSplit.DEPLOYMENT}:
            raise ValueError("fitted state cannot be learned on held-out/deployment data")
        if self.kind == FittedStateKind.THRESHOLD:
            if self.source_split not in {DataSplit.AGENT_TRAINING, DataSplit.VALIDATION}:
                raise ValueError("threshold source must be training or validation")
        elif self.source_split != DataSplit.AGENT_TRAINING:
            raise ValueError(f"{self.kind.value} must be fitted on agent-training data")
        if self.frozen_at < self.fitted_through:
            raise ValueError("frozen_at cannot precede fitted_through")
        return self


class FittedStateBundle(StrictModel):
    bundle_id: Identifier
    artifacts: tuple[FittedStateArtifact, ...]

    @model_validator(mode="after")
    def unique_kinds(self) -> "FittedStateBundle":
        kinds = [artifact.kind for artifact in self.artifacts]
        if len(kinds) != len(set(kinds)):
            raise ValueError("fitted-state bundle cannot contain duplicate kinds")
        artifact_ids = [artifact.artifact_id for artifact in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("fitted-state artifact IDs must be unique")
        return self


class ParameterFreeFeatureResult(StrictModel):
    feature_id: Identifier
    window_id: Identifier
    computed_at: Timestamp
    event_ids: tuple[Identifier, ...]
    values: dict[str, int | float | str | bool]

    @model_validator(mode="after")
    def deployment_visible(self) -> "ParameterFreeFeatureResult":
        assert_deployable_payload(self.values, "parameter_free_features")
        return self


class RollingRangeCandidate(StrictModel):
    candidate_id: Identifier
    window_count: int = Field(ge=1)
    source_split: DataSplit
    calibrated_at: Timestamp
    code_commit: GitSha

    @model_validator(mode="after")
    def validation_derived(self) -> "RollingRangeCandidate":
        if self.source_split != DataSplit.VALIDATION:
            raise ValueError("rolling range must be a validation-derived candidate")
        return self


class CausalFeatureBoundary:
    """Validate frozen fitted state and isolate current-window parameter-free work."""

    @staticmethod
    def require_frozen_bundle(
        bundle: FittedStateBundle,
        *,
        target_split: DataSplit,
        scenario_start: datetime,
        experiment_is_causal_main: bool = True,
    ) -> None:
        require_utc_offset(scenario_start)
        if target_split not in {
            DataSplit.VALIDATION,
            DataSplit.HELD_OUT,
            DataSplit.DEPLOYMENT,
        }:
            raise ValueError("frozen bundle validation is for validation/deployment-like splits")
        if not bundle.artifacts:
            raise ValueError("fitted-state bundle cannot be empty")
        for artifact in bundle.artifacts:
            if artifact.frozen_at > scenario_start or artifact.fitted_through > scenario_start:
                raise ValueError("fitted state includes information at or after scenario start")
            if (
                target_split == DataSplit.VALIDATION
                and artifact.source_split != DataSplit.AGENT_TRAINING
            ):
                raise ValueError("validation cannot consume validation-fitted state")
            if (
                experiment_is_causal_main
                and artifact.transductive_status != TransductiveStatus.CAUSAL
            ):
                raise ValueError("causal main cannot consume transductive fitted state")

    @staticmethod
    def compute_parameter_free(
        *,
        window: TimeWindow,
        event_ids: tuple[str, ...],
        event_times: tuple[datetime, ...],
        computed_at: datetime,
        feature_id: str,
        compute: Callable[[tuple[str, ...]], dict[str, int | float | str | bool]],
    ) -> ParameterFreeFeatureResult:
        require_utc_offset(computed_at)
        for timestamp in event_times:
            require_utc_offset(timestamp)
        if computed_at < window.end:
            raise ValueError("current-graph features cannot be computed before window arrival")
        if len(event_ids) != len(event_times):
            raise ValueError("event IDs and timestamps must have equal length")
        if any(not window.start <= timestamp < window.end for timestamp in event_times):
            raise ValueError("parameter-free feature input must contain only current-window events")
        values = compute(event_ids)
        return ParameterFreeFeatureResult(
            feature_id=feature_id,
            window_id=window.window_id,
            computed_at=computed_at,
            event_ids=event_ids,
            values=values,
        )
