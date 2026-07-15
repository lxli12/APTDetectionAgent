"""Explicit label-blind observation contracts for the v0.4 protocol."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from ._serialization import (
    deterministic_json, parse_datetime, require_keys, require_nonempty,
    require_nonnegative, require_object, require_unit_interval, versioned_dict,
)
from .sanitization import assert_deployable


class AgentSplit(str, Enum):
    TRAINING = "training"
    VALIDATION = "validation"
    HELD_OUT = "held_out"


class PipelineStage(str, Enum):
    CONSTRUCTION = "construction"
    TRANSFORMATION = "transformation"
    FEATURIZATION = "featurization"
    BATCHING = "batching"
    TRAINING = "training"
    EVALUATION = "evaluation"


class OperationStatus(str, Enum):
    NOT_RUN = "not_run"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    OOM = "oom"


@dataclass(frozen=True, slots=True)
class NamedCount:
    name: str
    count: int

    def __post_init__(self) -> None:
        require_nonempty(self.name, "count name")
        require_nonnegative(self.count, "count")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NamedCount":
        require_keys(data, required=("name", "count"), name="NamedCount")
        return cls(str(data["name"]), int(data["count"]))


@dataclass(frozen=True, slots=True)
class ResourceProfile:
    cpu_limit: int
    memory_limit_bytes: int
    gpu_count: int
    gpu_memory_bytes: int

    def __post_init__(self) -> None:
        for name in ("cpu_limit", "memory_limit_bytes", "gpu_count", "gpu_memory_bytes"):
            require_nonnegative(getattr(self, name), name)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResourceProfile":
        required = ("cpu_limit", "memory_limit_bytes", "gpu_count", "gpu_memory_bytes")
        require_keys(data, required=required, name="ResourceProfile")
        return cls(*(int(data[name]) for name in required))


@dataclass(frozen=True, slots=True)
class EnvironmentProfile:
    scenario_id: str
    dataset: str
    agent_split: AgentSplit
    os_family: str
    platform: str
    provenance_schema: str
    node_types: tuple[str, ...]
    edge_types: tuple[str, ...]
    normal_node_count_mean: float
    normal_edge_count_mean: float
    normal_event_rate_mean: float
    resource_profile: ResourceProfile

    def __post_init__(self) -> None:
        for field_name in ("scenario_id", "dataset", "os_family", "platform", "provenance_schema"):
            require_nonempty(getattr(self, field_name), field_name)
        if not self.node_types or not self.edge_types:
            raise ValueError("environment node_types and edge_types cannot be empty")
        for field_name in (
            "normal_node_count_mean", "normal_edge_count_mean", "normal_event_rate_mean"
        ):
            require_nonnegative(getattr(self, field_name), field_name)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EnvironmentProfile":
        required = (
            "scenario_id", "dataset", "agent_split", "os_family", "platform",
            "provenance_schema", "node_types", "edge_types", "normal_node_count_mean",
            "normal_edge_count_mean", "normal_event_rate_mean", "resource_profile",
        )
        require_keys(data, required=required, name="EnvironmentProfile")
        return cls(
            scenario_id=str(data["scenario_id"]), dataset=str(data["dataset"]),
            agent_split=AgentSplit(data["agent_split"]), os_family=str(data["os_family"]),
            platform=str(data["platform"]), provenance_schema=str(data["provenance_schema"]),
            node_types=tuple(str(item) for item in data["node_types"]),
            edge_types=tuple(str(item) for item in data["edge_types"]),
            normal_node_count_mean=float(data["normal_node_count_mean"]),
            normal_edge_count_mean=float(data["normal_edge_count_mean"]),
            normal_event_rate_mean=float(data["normal_event_rate_mean"]),
            resource_profile=ResourceProfile.from_dict(require_object(data["resource_profile"], "resource_profile")),
        )


@dataclass(frozen=True, slots=True)
class ConstructionGraph:
    graph_id: str
    window_id: str
    sequence_number: int
    start_time: datetime
    end_time: datetime
    node_count: int
    edge_count: int
    node_type_counts: tuple[NamedCount, ...]
    edge_type_counts: tuple[NamedCount, ...]
    density: float
    event_rate: float

    def __post_init__(self) -> None:
        require_nonempty(self.graph_id, "graph_id")
        require_nonempty(self.window_id, "window_id")
        for field_name in ("sequence_number", "node_count", "edge_count"):
            require_nonnegative(getattr(self, field_name), field_name)
        require_nonnegative(self.density, "density")
        require_nonnegative(self.event_rate, "event_rate")
        if self.start_time.tzinfo is None or self.end_time.tzinfo is None:
            raise ValueError("graph timestamps must be timezone-aware")
        if self.end_time <= self.start_time:
            raise ValueError("graph end_time must follow start_time")
        if sum(item.count for item in self.node_type_counts) != self.node_count:
            raise ValueError("node type counts must sum to node_count")
        if sum(item.count for item in self.edge_type_counts) != self.edge_count:
            raise ValueError("edge type counts must sum to edge_count")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ConstructionGraph":
        required = (
            "graph_id", "window_id", "sequence_number", "start_time", "end_time",
            "node_count", "edge_count", "node_type_counts", "edge_type_counts", "density",
            "event_rate",
        )
        require_keys(data, required=required, name="ConstructionGraph")
        return cls(
            graph_id=str(data["graph_id"]), window_id=str(data["window_id"]),
            sequence_number=int(data["sequence_number"]),
            start_time=parse_datetime(data["start_time"], "start_time"),
            end_time=parse_datetime(data["end_time"], "end_time"),
            node_count=int(data["node_count"]), edge_count=int(data["edge_count"]),
            node_type_counts=tuple(NamedCount.from_dict(require_object(item, "node_type_count")) for item in data["node_type_counts"]),
            edge_type_counts=tuple(NamedCount.from_dict(require_object(item, "edge_type_count")) for item in data["edge_type_counts"]),
            density=float(data["density"]), event_rate=float(data["event_rate"]),
        )


@dataclass(frozen=True, slots=True)
class StageState:
    stage: PipelineStage
    status: OperationStatus
    task_hash: str | None = None
    artifact_id: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StageState":
        require_keys(data, required=("stage", "status", "task_hash", "artifact_id"), name="StageState")
        return cls(PipelineStage(data["stage"]), OperationStatus(data["status"]), data["task_hash"], data["artifact_id"])


@dataclass(frozen=True, slots=True)
class PipelineState:
    detector: str
    config_id: str
    threshold_candidate_id: str
    checkpoint_id: str | None
    stages: tuple[StageState, ...]
    last_training_status: OperationStatus
    last_inference_status: OperationStatus

    def __post_init__(self) -> None:
        for field_name in ("detector", "config_id", "threshold_candidate_id"):
            require_nonempty(getattr(self, field_name), field_name)
        if len({item.stage for item in self.stages}) != len(self.stages):
            raise ValueError("pipeline stages must be unique")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PipelineState":
        required = (
            "detector", "config_id", "threshold_candidate_id", "checkpoint_id", "stages",
            "last_training_status", "last_inference_status",
        )
        require_keys(data, required=required, name="PipelineState")
        return cls(
            str(data["detector"]), str(data["config_id"]), str(data["threshold_candidate_id"]),
            None if data["checkpoint_id"] is None else str(data["checkpoint_id"]),
            tuple(StageState.from_dict(require_object(item, "stage")) for item in data["stages"]),
            OperationStatus(data["last_training_status"]), OperationStatus(data["last_inference_status"]),
        )


@dataclass(frozen=True, slots=True)
class ScoreQuantiles:
    minimum: float
    p50: float
    p90: float
    p95: float
    p99: float
    maximum: float

    def __post_init__(self) -> None:
        values = (self.minimum, self.p50, self.p90, self.p95, self.p99, self.maximum)
        if any(not isinstance(value, (int, float)) for value in values) or tuple(sorted(values)) != values:
            raise ValueError("score quantiles must be finite nondecreasing numbers")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ScoreQuantiles":
        required = ("minimum", "p50", "p90", "p95", "p99", "maximum")
        require_keys(data, required=required, name="ScoreQuantiles")
        return cls(*(float(data[name]) for name in required))


@dataclass(frozen=True, slots=True)
class UnlabeledDetectionSignals:
    score_quantiles: ScoreQuantiles
    tail_mass: float
    alert_count: int
    alert_ratio: float
    score_shift: float
    graph_shift: float
    alert_volume_shift: float
    degenerate_output: bool
    instability_score: float

    def __post_init__(self) -> None:
        require_unit_interval(self.tail_mass, "tail_mass")
        require_nonnegative(self.alert_count, "alert_count")
        require_unit_interval(self.alert_ratio, "alert_ratio")
        for name in ("score_shift", "graph_shift", "alert_volume_shift", "instability_score"):
            require_nonnegative(getattr(self, name), name)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "UnlabeledDetectionSignals":
        required = (
            "score_quantiles", "tail_mass", "alert_count", "alert_ratio", "score_shift",
            "graph_shift", "alert_volume_shift", "degenerate_output", "instability_score",
        )
        require_keys(data, required=required, name="UnlabeledDetectionSignals")
        return cls(
            ScoreQuantiles.from_dict(require_object(data["score_quantiles"], "score_quantiles")),
            float(data["tail_mass"]), int(data["alert_count"]), float(data["alert_ratio"]),
            float(data["score_shift"]), float(data["graph_shift"]),
            float(data["alert_volume_shift"]), bool(data["degenerate_output"]),
            float(data["instability_score"]),
        )


@dataclass(frozen=True, slots=True)
class CacheEntry:
    stage: PipelineStage
    task_hash: str
    available: bool

    def __post_init__(self) -> None:
        require_nonempty(self.task_hash, "task_hash")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CacheEntry":
        require_keys(data, required=("stage", "task_hash", "available"), name="CacheEntry")
        return cls(PipelineStage(data["stage"]), str(data["task_hash"]), bool(data["available"]))


@dataclass(frozen=True, slots=True)
class CacheState:
    entries: tuple[CacheEntry, ...]
    reusable_stages: tuple[PipelineStage, ...]

    def __post_init__(self) -> None:
        if len({item.stage for item in self.entries}) != len(self.entries):
            raise ValueError("cache entries must have unique stages")
        if not set(self.reusable_stages).issubset({item.stage for item in self.entries if item.available}):
            raise ValueError("reusable stages must refer to available cache entries")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CacheState":
        require_keys(data, required=("entries", "reusable_stages"), name="CacheState")
        return cls(
            tuple(CacheEntry.from_dict(require_object(item, "cache_entry")) for item in data["entries"]),
            tuple(PipelineStage(item) for item in data["reusable_stages"]),
        )


@dataclass(frozen=True, slots=True)
class BudgetState:
    remaining_llm_calls: int
    remaining_input_tokens: int
    remaining_output_tokens: int
    remaining_runtime_seconds: float
    pidsmaker_calls_used: int
    slow_path_calls_used: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "remaining_runtime_seconds", float(self.remaining_runtime_seconds))
        for name in (
            "remaining_llm_calls", "remaining_input_tokens", "remaining_output_tokens",
            "remaining_runtime_seconds", "pidsmaker_calls_used", "slow_path_calls_used",
        ):
            require_nonnegative(getattr(self, name), name)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BudgetState":
        required = (
            "remaining_llm_calls", "remaining_input_tokens", "remaining_output_tokens",
            "remaining_runtime_seconds", "pidsmaker_calls_used", "slow_path_calls_used",
        )
        require_keys(data, required=required, name="BudgetState")
        return cls(
            int(data["remaining_llm_calls"]), int(data["remaining_input_tokens"]),
            int(data["remaining_output_tokens"]), float(data["remaining_runtime_seconds"]),
            int(data["pidsmaker_calls_used"]), int(data["slow_path_calls_used"]),
        )


@dataclass(frozen=True, slots=True)
class MemoryContext:
    memory_id: str
    summary: str
    confidence: float
    applicability_conditions: tuple[str, ...]
    failure_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        require_nonempty(self.memory_id, "memory_id")
        require_nonempty(self.summary, "memory summary")
        require_unit_interval(self.confidence, "memory confidence")
        assert_deployable(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryContext":
        required = ("memory_id", "summary", "confidence", "applicability_conditions", "failure_conditions")
        require_keys(data, required=required, name="MemoryContext")
        return cls(
            str(data["memory_id"]), str(data["summary"]), float(data["confidence"]),
            tuple(str(item) for item in data["applicability_conditions"]),
            tuple(str(item) for item in data["failure_conditions"]),
        )


@dataclass(frozen=True, slots=True)
class Observation:
    observation_id: str
    observed_at: datetime
    environment: EnvironmentProfile
    graph: ConstructionGraph
    pipeline: PipelineState
    signals: UnlabeledDetectionSignals
    cache: CacheState
    budget: BudgetState
    memory_context: tuple[MemoryContext, ...] = ()

    def __post_init__(self) -> None:
        require_nonempty(self.observation_id, "observation_id")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.graph.window_id != self.graph.window_id.strip():
            raise ValueError("window_id cannot contain surrounding whitespace")
        assert_deployable(self)

    @property
    def window_id(self) -> str:
        return self.graph.window_id

    def to_dict(self) -> dict[str, Any]:
        return versioned_dict(self)

    def to_json(self) -> str:
        return deterministic_json(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Observation":
        data = require_object(raw, "Observation")
        required = (
            "observation_id", "observed_at", "environment", "graph", "pipeline", "signals",
            "cache", "budget", "memory_context",
        )
        require_keys(data, required=required, name="Observation", versioned=True)
        return cls(
            observation_id=str(data["observation_id"]),
            observed_at=parse_datetime(data["observed_at"], "observed_at"),
            environment=EnvironmentProfile.from_dict(require_object(data["environment"], "environment")),
            graph=ConstructionGraph.from_dict(require_object(data["graph"], "graph")),
            pipeline=PipelineState.from_dict(require_object(data["pipeline"], "pipeline")),
            signals=UnlabeledDetectionSignals.from_dict(require_object(data["signals"], "signals")),
            cache=CacheState.from_dict(require_object(data["cache"], "cache")),
            budget=BudgetState.from_dict(require_object(data["budget"], "budget")),
            memory_context=tuple(MemoryContext.from_dict(require_object(item, "memory_context")) for item in data["memory_context"]),
        )
