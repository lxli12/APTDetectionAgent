"""Bounded, stage-aware Agent diagnosis and action contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ._serialization import (
    deterministic_json, require_keys, require_nonempty, require_object,
    require_unit_interval, versioned_dict,
)
from .observation_schema import PipelineStage
from .sanitization import assert_deployable


class PathDecision(str, Enum):
    FAST_PATH = "FAST_PATH"
    SLOW_PATH = "SLOW_PATH"


class ActionType(str, Enum):
    KEEP_AND_INFER = "KEEP_AND_INFER"
    INVOKE_SLOW_DIAGNOSIS = "INVOKE_SLOW_DIAGNOSIS"
    ADJUST_THRESHOLD = "ADJUST_THRESHOLD"
    LOAD_TUNED_CONFIG = "LOAD_TUNED_CONFIG"
    SWITCH_PIDS = "SWITCH_PIDS"
    RETRAIN_CURRENT_PIDS = "RETRAIN_CURRENT_PIDS"
    ADJUST_RESOURCE_CONFIG = "ADJUST_RESOURCE_CONFIG"
    FALLBACK_OR_STOP = "FALLBACK_OR_STOP"


class DiagnosisCategory(str, Enum):
    VIABLE = "viable"
    THRESHOLD_FAILURE = "threshold_failure"
    DETECTION_FAILURE = "detection_failure"
    REPRESENTATION_RESOURCE = "representation_resource"
    INSTABILITY = "instability"
    ENGINEERING = "engineering"
    AMBIGUOUS = "ambiguous"


class DiagnosisCode(str, Enum):
    VIABLE_CONFIGURATION = "viable_configuration"
    THRESHOLD_TOO_TIGHT = "threshold_too_tight"
    THRESHOLD_TOO_LOOSE_OR_FLOOD = "threshold_too_loose_or_flood"
    NO_SCORE_SEPARATION = "no_score_separation"
    MODEL_MISMATCH = "model_mismatch"
    PARAMETER_MISMATCH = "parameter_mismatch"
    FEATURIZATION_OR_BATCHING_MISMATCH = "featurization_or_batching_mismatch"
    OOM = "oom"
    UNSTABLE_SCORES = "unstable_scores"
    UNDERTRAINED = "undertrained"
    TIMEOUT = "timeout"
    INVALID_CONFIG = "invalid_config"
    PIPELINE_FAILURE = "pipeline_failure"
    AMBIGUOUS_FAILURE = "ambiguous_failure"


DIAGNOSIS_CATEGORY_BY_CODE = {
    DiagnosisCode.VIABLE_CONFIGURATION: DiagnosisCategory.VIABLE,
    DiagnosisCode.THRESHOLD_TOO_TIGHT: DiagnosisCategory.THRESHOLD_FAILURE,
    DiagnosisCode.THRESHOLD_TOO_LOOSE_OR_FLOOD: DiagnosisCategory.THRESHOLD_FAILURE,
    DiagnosisCode.NO_SCORE_SEPARATION: DiagnosisCategory.DETECTION_FAILURE,
    DiagnosisCode.MODEL_MISMATCH: DiagnosisCategory.DETECTION_FAILURE,
    DiagnosisCode.PARAMETER_MISMATCH: DiagnosisCategory.DETECTION_FAILURE,
    DiagnosisCode.FEATURIZATION_OR_BATCHING_MISMATCH: DiagnosisCategory.REPRESENTATION_RESOURCE,
    DiagnosisCode.OOM: DiagnosisCategory.REPRESENTATION_RESOURCE,
    DiagnosisCode.UNSTABLE_SCORES: DiagnosisCategory.INSTABILITY,
    DiagnosisCode.UNDERTRAINED: DiagnosisCategory.INSTABILITY,
    DiagnosisCode.TIMEOUT: DiagnosisCategory.ENGINEERING,
    DiagnosisCode.INVALID_CONFIG: DiagnosisCategory.ENGINEERING,
    DiagnosisCode.PIPELINE_FAILURE: DiagnosisCategory.ENGINEERING,
    DiagnosisCode.AMBIGUOUS_FAILURE: DiagnosisCategory.AMBIGUOUS,
}


class CacheReuseLevel(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"


class CommitMode(str, Enum):
    NO_CONFIG_CHANGE = "no_config_change"
    COMMIT_ON_SUCCESS = "commit_on_success"
    VALIDATE_THEN_COMMIT = "validate_then_commit"
    ROLLBACK_TO_STABLE = "rollback_to_stable"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class Diagnosis:
    category: DiagnosisCategory
    code: DiagnosisCode
    explanation: str

    def __post_init__(self) -> None:
        require_nonempty(self.explanation, "diagnosis explanation")
        if DIAGNOSIS_CATEGORY_BY_CODE[self.code] is not self.category:
            raise ValueError("diagnosis category and code do not match")
        assert_deployable(self.explanation)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Diagnosis":
        require_keys(data, required=("category", "code", "explanation"), name="Diagnosis")
        return cls(
            DiagnosisCategory(data["category"]), DiagnosisCode(data["code"]),
            str(data["explanation"]),
        )


@dataclass(frozen=True, slots=True)
class VisibleEvidence:
    evidence_id: str
    source: str
    observation_fields: tuple[str, ...]
    summary: str

    def __post_init__(self) -> None:
        require_nonempty(self.evidence_id, "evidence_id")
        require_nonempty(self.source, "evidence source")
        require_nonempty(self.summary, "evidence summary")
        if not self.observation_fields:
            raise ValueError("visible evidence must reference observation fields")
        if any(not item.startswith(("environment.", "graph.", "pipeline.", "signals.", "cache.", "budget.", "memory_context")) for item in self.observation_fields):
            raise ValueError("evidence references a non-deployable observation field")
        assert_deployable(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "VisibleEvidence":
        required = ("evidence_id", "source", "observation_fields", "summary")
        require_keys(data, required=required, name="VisibleEvidence")
        return cls(
            str(data["evidence_id"]), str(data["source"]),
            tuple(str(item) for item in data["observation_fields"]), str(data["summary"]),
        )


@dataclass(frozen=True, slots=True)
class StageInvalidation:
    rerun_from: PipelineStage
    invalidated_stages: tuple[PipelineStage, ...]
    reason: str

    def __post_init__(self) -> None:
        require_nonempty(self.reason, "stage invalidation reason")
        ordered = tuple(PipelineStage)
        expected = ordered[ordered.index(self.rerun_from):]
        if self.invalidated_stages != expected:
            raise ValueError("invalidated stages must be the complete suffix from rerun_from")
        assert_deployable(self.reason)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StageInvalidation":
        require_keys(data, required=("rerun_from", "invalidated_stages", "reason"), name="StageInvalidation")
        return cls(
            PipelineStage(data["rerun_from"]),
            tuple(PipelineStage(item) for item in data["invalidated_stages"]),
            str(data["reason"]),
        )


@dataclass(frozen=True, slots=True)
class ExpectedCacheReuse:
    level: CacheReuseLevel
    reusable_stages: tuple[PipelineStage, ...]
    invalidated_stages: tuple[PipelineStage, ...]
    rationale: str

    def __post_init__(self) -> None:
        require_nonempty(self.rationale, "cache reuse rationale")
        if set(self.reusable_stages) & set(self.invalidated_stages):
            raise ValueError("a stage cannot be both reused and invalidated")
        if self.level is CacheReuseLevel.FULL and self.invalidated_stages:
            raise ValueError("full cache reuse cannot invalidate stages")
        if self.level is CacheReuseLevel.NONE and self.reusable_stages:
            raise ValueError("no cache reuse cannot name reusable stages")
        assert_deployable(self.rationale)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExpectedCacheReuse":
        required = ("level", "reusable_stages", "invalidated_stages", "rationale")
        require_keys(data, required=required, name="ExpectedCacheReuse")
        return cls(
            CacheReuseLevel(data["level"]),
            tuple(PipelineStage(item) for item in data["reusable_stages"]),
            tuple(PipelineStage(item) for item in data["invalidated_stages"]),
            str(data["rationale"]),
        )


@dataclass(frozen=True, slots=True)
class CommitPolicy:
    mode: CommitMode
    stable_config_id: str
    rollback_on_failure: bool
    require_validation: bool

    def __post_init__(self) -> None:
        require_nonempty(self.stable_config_id, "stable_config_id")
        if self.mode is CommitMode.VALIDATE_THEN_COMMIT and not self.require_validation:
            raise ValueError("validate_then_commit requires validation")
        if self.mode is CommitMode.STOP and self.rollback_on_failure:
            raise ValueError("stop cannot request rollback")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CommitPolicy":
        required = ("mode", "stable_config_id", "rollback_on_failure", "require_validation")
        require_keys(data, required=required, name="CommitPolicy")
        return cls(
            CommitMode(data["mode"]), str(data["stable_config_id"]),
            bool(data["rollback_on_failure"]), bool(data["require_validation"]),
        )


@dataclass(frozen=True, slots=True)
class FallbackPolicy:
    fallback_action: ActionType
    stable_config_id: str
    reason: str

    def __post_init__(self) -> None:
        if self.fallback_action is not ActionType.FALLBACK_OR_STOP:
            raise ValueError("fallback policy must use FALLBACK_OR_STOP")
        require_nonempty(self.stable_config_id, "fallback stable_config_id")
        require_nonempty(self.reason, "fallback reason")
        assert_deployable(self.reason)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FallbackPolicy":
        require_keys(data, required=("fallback_action", "stable_config_id", "reason"), name="FallbackPolicy")
        return cls(ActionType(data["fallback_action"]), str(data["stable_config_id"]), str(data["reason"]))


ACTION_TOOL = {
    ActionType.KEEP_AND_INFER: "run_current_pids",
    ActionType.ADJUST_THRESHOLD: "adjust_threshold",
    ActionType.LOAD_TUNED_CONFIG: "load_tuned_config",
    ActionType.SWITCH_PIDS: "switch_pids",
    ActionType.RETRAIN_CURRENT_PIDS: "retrain_current_pids",
    ActionType.ADJUST_RESOURCE_CONFIG: "adjust_resource_config",
}


@dataclass(frozen=True, slots=True)
class Action:
    action_id: str
    path_decision: PathDecision
    action_type: ActionType
    diagnosis: Diagnosis
    visible_evidence: tuple[VisibleEvidence, ...]
    tool_name: str | None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    stage_invalidation: StageInvalidation | None = None
    expected_cache_reuse: ExpectedCacheReuse | None = None
    confidence: float = 0.0
    commit_policy: CommitPolicy | None = None
    fallback: FallbackPolicy | None = None
    adopted_memory_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_nonempty(self.action_id, "action_id")
        require_unit_interval(self.confidence, "confidence")
        expected_tool = ACTION_TOOL.get(self.action_type)
        if expected_tool is not None and self.tool_name != expected_tool:
            raise ValueError(f"{self.action_type.value} requires tool {expected_tool}")
        if self.action_type in (ActionType.INVOKE_SLOW_DIAGNOSIS, ActionType.FALLBACK_OR_STOP):
            if self.tool_name is not None or self.arguments:
                raise ValueError("diagnosis/fallback actions cannot directly execute a tool")
        if self.path_decision is PathDecision.FAST_PATH and self.action_type not in (
            ActionType.KEEP_AND_INFER, ActionType.FALLBACK_OR_STOP
        ):
            raise ValueError("fast path supports only keep/infer or safe termination")
        if self.action_type is ActionType.KEEP_AND_INFER and self.stage_invalidation is not None:
            raise ValueError("KEEP_AND_INFER cannot invalidate pipeline stages")
        if self.action_type in ACTION_TOOL and self.action_type is not ActionType.KEEP_AND_INFER:
            if self.stage_invalidation is None or self.expected_cache_reuse is None:
                raise ValueError("reconfiguration actions require stage/cache metadata")
        if self.commit_policy is None or self.fallback is None:
            raise ValueError("every action requires commit and fallback policies")
        if len(set(self.adopted_memory_ids)) != len(self.adopted_memory_ids):
            raise ValueError("adopted memory IDs must be unique")
        assert_deployable(self)

    @property
    def rationale(self) -> str:
        return self.diagnosis.explanation

    def to_dict(self) -> dict[str, Any]:
        return versioned_dict(self)

    def to_json(self) -> str:
        return deterministic_json(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Action":
        data = require_object(raw, "Action")
        required = (
            "action_id", "path_decision", "action_type", "diagnosis", "visible_evidence",
            "tool_name", "arguments", "stage_invalidation", "expected_cache_reuse", "confidence",
            "commit_policy", "fallback", "adopted_memory_ids",
        )
        require_keys(data, required=required, name="Action", versioned=True)
        return cls(
            action_id=str(data["action_id"]), path_decision=PathDecision(data["path_decision"]),
            action_type=ActionType(data["action_type"]),
            diagnosis=Diagnosis.from_dict(require_object(data["diagnosis"], "diagnosis")),
            visible_evidence=tuple(VisibleEvidence.from_dict(require_object(item, "visible_evidence")) for item in data["visible_evidence"]),
            tool_name=None if data["tool_name"] is None else str(data["tool_name"]),
            arguments=dict(require_object(data["arguments"], "arguments")),
            stage_invalidation=None if data["stage_invalidation"] is None else StageInvalidation.from_dict(require_object(data["stage_invalidation"], "stage_invalidation")),
            expected_cache_reuse=None if data["expected_cache_reuse"] is None else ExpectedCacheReuse.from_dict(require_object(data["expected_cache_reuse"], "expected_cache_reuse")),
            confidence=float(data["confidence"]),
            commit_policy=CommitPolicy.from_dict(require_object(data["commit_policy"], "commit_policy")),
            fallback=FallbackPolicy.from_dict(require_object(data["fallback"], "fallback")),
            adopted_memory_ids=tuple(str(item) for item in data["adopted_memory_ids"]),
        )
