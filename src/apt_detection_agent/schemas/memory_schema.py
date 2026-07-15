"""Fixed-harness memory exchange contracts and deployable record boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from ._serialization import (
    deterministic_json, nested_versioned, parse_datetime, require_keys, require_nonempty,
    require_nonnegative, require_object, require_unit_interval, versioned_dict,
)
from .sanitization import assert_deployable


class MemoryLayer(str, Enum):
    WORKING = "working"
    EPISODE = "episode"
    LTM_CANDIDATE = "ltm_candidate"


class MemoryUseDisposition(str, Enum):
    USE = "use"
    DOWNWEIGHT = "downweight"
    IGNORE = "ignore"


@dataclass(frozen=True, slots=True)
class NumericFeature:
    name: str
    value: float

    def __post_init__(self) -> None:
        require_nonempty(self.name, "numeric feature name")
        require_nonnegative(self.value, "numeric feature value")
        assert_deployable(self.name)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NumericFeature":
        require_keys(data, required=("name", "value"), name="NumericFeature")
        return cls(str(data["name"]), float(data["value"]))


@dataclass(frozen=True, slots=True)
class EnvironmentSignature:
    os_family: str
    platform: str
    provenance_schema: str
    supported_detectors: tuple[str, ...]
    resource_tags: tuple[str, ...]
    numeric_profile: tuple[NumericFeature, ...]

    def __post_init__(self) -> None:
        for name in ("os_family", "platform", "provenance_schema"):
            require_nonempty(getattr(self, name), name)
        if not self.supported_detectors:
            raise ValueError("environment signature requires supported detectors")
        assert_deployable(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EnvironmentSignature":
        required = (
            "os_family", "platform", "provenance_schema", "supported_detectors",
            "resource_tags", "numeric_profile",
        )
        require_keys(data, required=required, name="EnvironmentSignature")
        return cls(
            str(data["os_family"]), str(data["platform"]), str(data["provenance_schema"]),
            tuple(str(item) for item in data["supported_detectors"]),
            tuple(str(item) for item in data["resource_tags"]),
            tuple(NumericFeature.from_dict(require_object(item, "numeric_feature")) for item in data["numeric_profile"]),
        )


@dataclass(frozen=True, slots=True)
class ObservableBehaviorProfile:
    symptom_tags: tuple[str, ...]
    temporal_persistence: float
    cross_window_change: float
    entity_dispersion: float
    score_tail_mass: float
    structural_shift: float

    def __post_init__(self) -> None:
        for name in (
            "temporal_persistence", "cross_window_change", "entity_dispersion",
            "score_tail_mass", "structural_shift",
        ):
            require_unit_interval(getattr(self, name), name)
        assert_deployable(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ObservableBehaviorProfile":
        required = (
            "symptom_tags", "temporal_persistence", "cross_window_change",
            "entity_dispersion", "score_tail_mass", "structural_shift",
        )
        require_keys(data, required=required, name="ObservableBehaviorProfile")
        return cls(
            tuple(str(item) for item in data["symptom_tags"]),
            *(float(data[name]) for name in required[1:]),
        )


@dataclass(frozen=True, slots=True)
class PIDSCapabilityProfile:
    detector: str
    capability_tags: tuple[str, ...]
    threshold_sensitivity: str
    scalability_class: str
    feature_dependencies: tuple[str, ...]
    latency_class: str

    def __post_init__(self) -> None:
        for name in ("detector", "threshold_sensitivity", "scalability_class", "latency_class"):
            require_nonempty(getattr(self, name), name)
        assert_deployable(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PIDSCapabilityProfile":
        required = (
            "detector", "capability_tags", "threshold_sensitivity", "scalability_class",
            "feature_dependencies", "latency_class",
        )
        require_keys(data, required=required, name="PIDSCapabilityProfile")
        return cls(
            str(data["detector"]), tuple(str(item) for item in data["capability_tags"]),
            str(data["threshold_sensitivity"]), str(data["scalability_class"]),
            tuple(str(item) for item in data["feature_dependencies"]), str(data["latency_class"]),
        )


@dataclass(frozen=True, slots=True)
class Experience:
    visible_symptom: str
    diagnosis_code: str
    recommended_action: str
    stage_invalidation: str
    deployable_outcome: str
    applicability_conditions: tuple[str, ...]
    failure_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "visible_symptom", "diagnosis_code", "recommended_action",
            "stage_invalidation", "deployable_outcome",
        ):
            require_nonempty(getattr(self, name), name)
        assert_deployable(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Experience":
        required = (
            "visible_symptom", "diagnosis_code", "recommended_action", "stage_invalidation",
            "deployable_outcome", "applicability_conditions", "failure_conditions",
        )
        require_keys(data, required=required, name="Experience")
        return cls(
            *(str(data[name]) for name in required[:5]),
            tuple(str(item) for item in data["applicability_conditions"]),
            tuple(str(item) for item in data["failure_conditions"]),
        )


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    namespace: str
    layer: MemoryLayer
    environment: EnvironmentSignature
    behavior: ObservableBehaviorProfile
    pids_capability: PIDSCapabilityProfile
    experience: Experience
    evidence_ids: tuple[str, ...]
    confidence: float
    support_count: int
    created_at: datetime
    provenance_id: str

    def __post_init__(self) -> None:
        for name in ("memory_id", "namespace", "provenance_id"):
            require_nonempty(getattr(self, name), name)
        require_unit_interval(self.confidence, "memory confidence")
        if self.support_count < 1:
            raise ValueError("memory support_count must be positive")
        if self.created_at.tzinfo is None:
            raise ValueError("memory created_at must be timezone-aware")
        assert_deployable(self)

    @property
    def content(self) -> str:
        return " ".join((
            self.experience.visible_symptom, self.experience.diagnosis_code,
            self.experience.recommended_action, self.experience.deployable_outcome,
        ))

    def to_dict(self) -> dict[str, Any]:
        return versioned_dict(self)

    def to_json(self) -> str:
        return deterministic_json(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MemoryRecord":
        data = require_object(raw, "MemoryRecord")
        required = (
            "memory_id", "namespace", "layer", "environment", "behavior", "pids_capability",
            "experience", "evidence_ids", "confidence", "support_count", "created_at", "provenance_id",
        )
        require_keys(data, required=required, name="MemoryRecord", versioned=True)
        return cls(
            str(data["memory_id"]), str(data["namespace"]), MemoryLayer(data["layer"]),
            EnvironmentSignature.from_dict(require_object(data["environment"], "environment")),
            ObservableBehaviorProfile.from_dict(require_object(data["behavior"], "behavior")),
            PIDSCapabilityProfile.from_dict(require_object(data["pids_capability"], "pids_capability")),
            Experience.from_dict(require_object(data["experience"], "experience")),
            tuple(str(item) for item in data["evidence_ids"]), float(data["confidence"]),
            int(data["support_count"]), parse_datetime(data["created_at"], "created_at"),
            str(data["provenance_id"]),
        )


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    namespace: str
    os_family: str
    provenance_schema: str
    current_detector: str
    symptom_tags: tuple[str, ...]
    numeric_profile: tuple[NumericFeature, ...]
    top_k: int = 5

    def __post_init__(self) -> None:
        for name in ("namespace", "os_family", "provenance_schema", "current_detector"):
            require_nonempty(getattr(self, name), name)
        if not 1 <= self.top_k <= 20:
            raise ValueError("memory top_k must be between 1 and 20")
        assert_deployable(self)

    @property
    def text(self) -> str:
        return " ".join((self.os_family, self.provenance_schema, self.current_detector, *self.symptom_tags))

    @property
    def limit(self) -> int:
        return self.top_k

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryQuery":
        required = (
            "namespace", "os_family", "provenance_schema", "current_detector",
            "symptom_tags", "numeric_profile", "top_k",
        )
        require_keys(data, required=required, name="MemoryQuery")
        return cls(
            str(data["namespace"]), str(data["os_family"]), str(data["provenance_schema"]),
            str(data["current_detector"]), tuple(str(item) for item in data["symptom_tags"]),
            tuple(NumericFeature.from_dict(require_object(item, "numeric_feature")) for item in data["numeric_profile"]),
            int(data["top_k"]),
        )


@dataclass(frozen=True, slots=True)
class MemoryReadRequest:
    request_id: str
    needed: bool
    query_intent: str | None
    query: MemoryQuery | None

    def __post_init__(self) -> None:
        require_nonempty(self.request_id, "memory read request_id")
        if self.needed != (self.query is not None):
            raise ValueError("needed and query presence must agree")
        if self.needed and (self.query_intent is None or not self.query_intent.strip()):
            raise ValueError("needed memory read requires query_intent")
        if not self.needed and self.query_intent is not None:
            raise ValueError("unneeded memory read cannot carry query_intent")
        assert_deployable(self)

    def to_dict(self) -> dict[str, Any]:
        return versioned_dict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MemoryReadRequest":
        data = require_object(raw, "MemoryReadRequest")
        require_keys(data, required=("request_id", "needed", "query_intent", "query"), name="MemoryReadRequest", versioned=True)
        return cls(
            str(data["request_id"]), bool(data["needed"]),
            None if data["query_intent"] is None else str(data["query_intent"]),
            None if data["query"] is None else MemoryQuery.from_dict(require_object(data["query"], "query")),
        )


@dataclass(frozen=True, slots=True)
class MemoryUseItem:
    memory_id: str
    disposition: MemoryUseDisposition
    reason: str

    def __post_init__(self) -> None:
        require_nonempty(self.memory_id, "memory use memory_id")
        require_nonempty(self.reason, "memory use reason")
        assert_deployable(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "MemoryUseItem":
        require_keys(data, required=("memory_id", "disposition", "reason"), name="MemoryUseItem")
        return cls(str(data["memory_id"]), MemoryUseDisposition(data["disposition"]), str(data["reason"]))


@dataclass(frozen=True, slots=True)
class MemoryUseDecision:
    request_id: str
    decisions: tuple[MemoryUseItem, ...]

    def __post_init__(self) -> None:
        require_nonempty(self.request_id, "memory use request_id")
        if len({item.memory_id for item in self.decisions}) != len(self.decisions):
            raise ValueError("memory use decisions must reference unique IDs")

    def to_dict(self) -> dict[str, Any]:
        return versioned_dict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MemoryUseDecision":
        data = require_object(raw, "MemoryUseDecision")
        require_keys(data, required=("request_id", "decisions"), name="MemoryUseDecision", versioned=True)
        return cls(str(data["request_id"]), tuple(MemoryUseItem.from_dict(require_object(item, "decision")) for item in data["decisions"]))


@dataclass(frozen=True, slots=True)
class MemoryWriteRequest:
    request_id: str
    should_write: bool
    target_layer: MemoryLayer | None
    write_reason: str | None
    record: MemoryRecord | None

    def __post_init__(self) -> None:
        require_nonempty(self.request_id, "memory write request_id")
        present = self.target_layer is not None and self.write_reason is not None and self.record is not None
        if self.should_write != present:
            raise ValueError("write decision and candidate fields must agree")
        if not self.should_write and any(item is not None for item in (self.target_layer, self.write_reason, self.record)):
            raise ValueError("rejected memory write cannot carry a candidate")
        if self.record is not None and self.record.layer is not self.target_layer:
            raise ValueError("memory record layer does not match target_layer")
        assert_deployable(self)

    def to_dict(self) -> dict[str, Any]:
        return versioned_dict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "MemoryWriteRequest":
        data = require_object(raw, "MemoryWriteRequest")
        required = ("request_id", "should_write", "target_layer", "write_reason", "record")
        require_keys(data, required=required, name="MemoryWriteRequest", versioned=True)
        return cls(
            str(data["request_id"]), bool(data["should_write"]),
            None if data["target_layer"] is None else MemoryLayer(data["target_layer"]),
            None if data["write_reason"] is None else str(data["write_reason"]),
            None if data["record"] is None else MemoryRecord.from_dict(nested_versioned(data["record"], "record")),
        )
