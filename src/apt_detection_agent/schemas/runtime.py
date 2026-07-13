"""Deployment-visible window, observation, prediction, and case contracts.

Requirements: REQ-LABEL-001, REQ-WINDOW-001..003, REQ-CONFIG-001,
REQ-CAUSAL-001, REQ-EVAL-002.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator, model_validator

from .common import DataSplit, DetectionUnit, Identifier, StrictModel, Timestamp
from .pids import PIDSRef


class TimeWindow(StrictModel):
    window_id: Identifier
    sequence_number: int = Field(ge=0)
    origin_time: Timestamp
    timezone: str
    window_size_seconds: int = Field(gt=0)
    start: Timestamp
    end: Timestamp

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("timezone must be an IANA timezone") from exc
        return value

    @model_validator(mode="after")
    def validate_half_open_alignment(self) -> "TimeWindow":
        if self.end <= self.start:
            raise ValueError("window end must be after start")
        duration = int((self.end - self.start).total_seconds())
        if duration != self.window_size_seconds:
            raise ValueError("window duration must equal window_size_seconds")
        offset = int((self.start - self.origin_time).total_seconds())
        if offset < 0 or offset % self.window_size_seconds:
            raise ValueError("window start must align to origin and size")
        if offset // self.window_size_seconds != self.sequence_number:
            raise ValueError("sequence_number must match aligned window offset")
        zone = ZoneInfo(self.timezone)
        for name, value in (
            ("origin_time", self.origin_time),
            ("start", self.start),
            ("end", self.end),
        ):
            if value.utcoffset() != value.astimezone(zone).utcoffset():
                raise ValueError(f"{name} UTC offset does not match timezone")
        return self


class ScoreSummary(StrictModel):
    count: int = Field(ge=0)
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    quantiles: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def empty_summary_has_no_values(self) -> "ScoreSummary":
        values = (self.minimum, self.maximum, self.mean)
        if self.count == 0 and any(value is not None for value in values):
            raise ValueError("empty score summary cannot contain statistics")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise ValueError("minimum cannot exceed maximum")
        return self


class DetectionAlert(StrictModel):
    alert_id: Identifier
    entity_id: Identifier
    detection_unit: DetectionUnit
    score: float
    threshold_id: Identifier
    evidence_artifact_ids: tuple[Identifier, ...] = ()


class Observation(StrictModel):
    schema_version: str = "1.0"
    observation_id: Identifier
    scenario_id: Identifier
    episode_id: Identifier
    split: DataSplit
    observed_at: Timestamp
    window: TimeWindow
    environment_profile_id: Identifier
    committed_config_id: Identifier
    active_pids: tuple[PIDSRef, ...]
    score_summary: ScoreSummary
    alerts: tuple[DetectionAlert, ...] = ()
    observable_failures: tuple[str, ...] = ()
    case_summary: str | None = None
    memory_record_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def observation_is_current(self) -> "Observation":
        if self.observed_at < self.window.end:
            raise ValueError("observation cannot be emitted before its window closes")
        return self


class PendingConfiguration(StrictModel):
    config_id: Identifier
    effective_sequence_number: int = Field(ge=0)
    requested_by_tool_call_id: Identifier


class CaseState(StrictModel):
    case_id: Identifier
    scenario_id: Identifier
    episode_id: Identifier
    split: DataSplit
    current_window_sequence: int = Field(ge=0)
    committed_config_id: Identifier
    pending_configuration: PendingConfiguration | None = None
    memory_namespace: Identifier
    updated_at: Timestamp

    @model_validator(mode="after")
    def pending_config_is_next_window_or_later(self) -> "CaseState":
        pending = self.pending_configuration
        if pending and pending.effective_sequence_number <= self.current_window_sequence:
            raise ValueError("persistent configuration cannot affect current/past window")
        return self


class Prediction(StrictModel):
    prediction_id: Identifier
    case_id: Identifier
    scenario_id: Identifier
    episode_id: Identifier
    split: DataSplit
    window_id: Identifier
    window_sequence_number: int = Field(ge=0)
    committed_config_id: Identifier
    pids: tuple[PIDSRef, ...]
    alert_entity_ids: tuple[Identifier, ...]
    created_at: Timestamp
    artifact_manifest_id: Identifier
