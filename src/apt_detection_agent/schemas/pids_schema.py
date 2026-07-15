"""Label-safe normalized PIDSMaker and per-window commitment contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from ._serialization import (
    deterministic_json, parse_datetime, require_keys, require_nonempty,
    require_nonnegative, require_object, versioned_dict,
)
from .observation_schema import OperationStatus, PipelineStage
from .sanitization import assert_deployable


class DetectionCommitStatus(str, Enum):
    COMMITTED = "committed"
    FALLBACK_COMMITTED = "fallback_committed"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class EntityScore:
    entity_id: str
    score: float

    def __post_init__(self) -> None:
        require_nonempty(self.entity_id, "entity_id")
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise ValueError("entity score must be numeric")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EntityScore":
        require_keys(data, required=("entity_id", "score"), name="EntityScore")
        return cls(str(data["entity_id"]), float(data["score"]))


@dataclass(frozen=True, slots=True)
class Alert:
    entity_id: str
    score: float
    threshold_candidate_id: str
    reason_code: str

    def __post_init__(self) -> None:
        for name in ("entity_id", "threshold_candidate_id", "reason_code"):
            require_nonempty(getattr(self, name), name)
        if isinstance(self.score, bool) or not isinstance(self.score, (int, float)):
            raise ValueError("alert score must be numeric")
        assert_deployable(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Alert":
        required = ("entity_id", "score", "threshold_candidate_id", "reason_code")
        require_keys(data, required=required, name="Alert")
        return cls(str(data["entity_id"]), float(data["score"]), str(data["threshold_candidate_id"]), str(data["reason_code"]))


@dataclass(frozen=True, slots=True)
class BackendArtifact:
    artifact_id: str
    stage: PipelineStage
    path: str
    task_hash: str
    cache_hit: bool

    def __post_init__(self) -> None:
        for name in ("artifact_id", "path", "task_hash"):
            require_nonempty(getattr(self, name), name)
        if not self.path.startswith("/"):
            raise ValueError("backend artifact paths must be absolute")
        assert_deployable(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BackendArtifact":
        required = ("artifact_id", "stage", "path", "task_hash", "cache_hit")
        require_keys(data, required=required, name="BackendArtifact")
        return cls(str(data["artifact_id"]), PipelineStage(data["stage"]), str(data["path"]), str(data["task_hash"]), bool(data["cache_hit"]))


@dataclass(frozen=True, slots=True)
class PIDSResult:
    detector: str
    run_id: str
    window_id: str
    config_id: str
    status: OperationStatus
    scores: tuple[EntityScore, ...]
    alerts: tuple[Alert, ...]
    artifacts: tuple[BackendArtifact, ...]
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    partial_output: bool = False

    def __post_init__(self) -> None:
        for name in ("detector", "run_id", "window_id", "config_id"):
            require_nonempty(getattr(self, name), name)
        if self.started_at.tzinfo is None or self.completed_at.tzinfo is None:
            raise ValueError("PIDS result timestamps must be timezone-aware")
        if self.completed_at < self.started_at:
            raise ValueError("PIDS completion cannot precede start")
        require_nonnegative(self.duration_seconds, "duration_seconds")
        if self.status is OperationStatus.SUCCEEDED and self.partial_output:
            raise ValueError("successful PIDS result cannot be partial")
        if len({item.entity_id for item in self.scores}) != len(self.scores):
            raise ValueError("PIDS entity scores must be unique")
        score_ids = {item.entity_id for item in self.scores}
        if not {item.entity_id for item in self.alerts}.issubset(score_ids):
            raise ValueError("every alert must reference an entity score")
        assert_deployable(self)

    def to_dict(self) -> dict[str, Any]:
        return versioned_dict(self)

    def to_json(self) -> str:
        return deterministic_json(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "PIDSResult":
        data = require_object(raw, "PIDSResult")
        required = (
            "detector", "run_id", "window_id", "config_id", "status", "scores", "alerts",
            "artifacts", "started_at", "completed_at", "duration_seconds", "partial_output",
        )
        require_keys(data, required=required, name="PIDSResult", versioned=True)
        return cls(
            str(data["detector"]), str(data["run_id"]), str(data["window_id"]),
            str(data["config_id"]), OperationStatus(data["status"]),
            tuple(EntityScore.from_dict(require_object(item, "score")) for item in data["scores"]),
            tuple(Alert.from_dict(require_object(item, "alert")) for item in data["alerts"]),
            tuple(BackendArtifact.from_dict(require_object(item, "artifact")) for item in data["artifacts"]),
            parse_datetime(data["started_at"], "started_at"),
            parse_datetime(data["completed_at"], "completed_at"),
            float(data["duration_seconds"]), bool(data["partial_output"]),
        )


@dataclass(frozen=True, slots=True)
class CommittedDetection:
    commitment_id: str
    scenario_id: str
    window_id: str
    graph_sequence_number: int
    detector: str
    config_id: str
    result_run_id: str | None
    alerts: tuple[Alert, ...]
    status: DetectionCommitStatus
    committed_at: datetime
    fallback_reason: str | None = None

    def __post_init__(self) -> None:
        for name in ("commitment_id", "scenario_id", "window_id", "detector", "config_id"):
            require_nonempty(getattr(self, name), name)
        require_nonnegative(self.graph_sequence_number, "graph_sequence_number")
        if self.committed_at.tzinfo is None:
            raise ValueError("committed_at must be timezone-aware")
        if self.status is DetectionCommitStatus.COMMITTED and self.result_run_id is None:
            raise ValueError("normal commitment requires result_run_id")
        if self.status is DetectionCommitStatus.FALLBACK_COMMITTED and not self.fallback_reason:
            raise ValueError("fallback commitment requires fallback_reason")
        if self.status is DetectionCommitStatus.STOPPED and self.alerts:
            raise ValueError("stopped commitment cannot contain alerts")
        assert_deployable(self)

    def to_dict(self) -> dict[str, Any]:
        return versioned_dict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "CommittedDetection":
        data = require_object(raw, "CommittedDetection")
        required = (
            "commitment_id", "scenario_id", "window_id", "graph_sequence_number", "detector",
            "config_id", "result_run_id", "alerts", "status", "committed_at", "fallback_reason",
        )
        require_keys(data, required=required, name="CommittedDetection", versioned=True)
        return cls(
            str(data["commitment_id"]), str(data["scenario_id"]), str(data["window_id"]),
            int(data["graph_sequence_number"]), str(data["detector"]), str(data["config_id"]),
            None if data["result_run_id"] is None else str(data["result_run_id"]),
            tuple(Alert.from_dict(require_object(item, "alert")) for item in data["alerts"]),
            DetectionCommitStatus(data["status"]), parse_datetime(data["committed_at"], "committed_at"),
            None if data["fallback_reason"] is None else str(data["fallback_reason"]),
        )
