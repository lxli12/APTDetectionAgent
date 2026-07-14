"""Frozen Agent runtime, observation-layer, and action contracts.

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001..004,
REQ-WINDOW-001..004, REQ-CONFIG-001..003, REQ-TOOL-001..005,
REQ-ARTIFACT-001..003, REQ-RESOURCE-001..003, REQ-REPRO-001..003.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    AvailabilityStatus,
    DataSplit,
    DetectionUnit,
    Identifier,
    RunStatus,
    Sha256,
    StrictModel,
    Timestamp,
)
from .evaluation import assert_deployable_payload
from .pids import PIDSRef
from .runtime import DetectionAlert, ScoreSummary, TimeWindow
from .tools import ToolName


class ExecutionRole(str, Enum):
    COMMITTED_FAST_PATH = "committed_fast_path"
    ADDITIONAL_INVESTIGATION = "additional_investigation"


class FrozenActionType(str, Enum):
    KEEP_CURRENT_CONFIG = "keep_current_config"
    RUN_ADDITIONAL_DETECTOR = "run_additional_detector"
    SELECT_VALIDATED_THRESHOLD = "select_validated_threshold"
    LOAD_APPROVED_CONFIG = "load_approved_config"
    SWITCH_DETECTOR = "switch_detector"
    RETRAIN_DETECTOR = "retrain_detector"
    SELECT_RESOURCE_PRESET = "select_resource_preset"
    FINISH_DIAGNOSIS = "finish_diagnosis"


class DecisionSource(str, Enum):
    HARNESS_DEFAULT = "harness_default"
    LLM_AGENT = "llm_agent"


class CacheReuseClass(str, Enum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"
    UNKNOWN = "unknown"


class RecomputationScope(str, Enum):
    NONE = "none"
    INFERENCE_ONLY = "inference_only"
    CONFIGURATION_DEPENDENT = "configuration_dependent"
    TRAINING_REQUIRED = "training_required"


class CommittedDetectionState(StrictModel):
    state_id: Identifier
    detector: PIDSRef
    approved_candidate_id: Identifier
    config_id: Identifier
    checkpoint_id: Identifier
    threshold_id: Identifier
    resource_preset_id: Identifier
    state_token: Identifier
    state_health: Identifier
    effective_sequence_number: int = Field(ge=0)


class PendingDetectionState(StrictModel):
    pending_change_id: Identifier
    action_type: FrozenActionType
    approved_choice_id: Identifier
    requested_by_action_id: Identifier
    effective_sequence_number: int = Field(ge=0)
    target_detector: PIDSRef
    target_config_id: Identifier
    target_checkpoint_id: Identifier
    target_threshold_id: Identifier
    target_resource_preset_id: Identifier
    state_initialization_policy_id: Identifier
    target_state_token: Identifier
    target_state_health: Identifier
    rollback_state_id: Identifier

    @model_validator(mode="after")
    def only_persistent_actions_create_pending_state(self) -> "PendingDetectionState":
        allowed = {
            FrozenActionType.SELECT_VALIDATED_THRESHOLD,
            FrozenActionType.LOAD_APPROVED_CONFIG,
            FrozenActionType.SWITCH_DETECTOR,
            FrozenActionType.SELECT_RESOURCE_PRESET,
        }
        if self.action_type not in allowed:
            raise ValueError("action cannot create an activatable pending state")
        return self


class FrozenCaseState(StrictModel):
    case_id: Identifier
    scenario_id: Identifier
    episode_id: Identifier
    split: DataSplit
    current_window_sequence: int = Field(ge=0)
    committed_state: CommittedDetectionState
    pending_state: PendingDetectionState | None = None
    memory_namespace: Identifier
    updated_at: Timestamp

    @model_validator(mode="after")
    def state_effective_at_current_boundary(self) -> "FrozenCaseState":
        if self.committed_state.effective_sequence_number > self.current_window_sequence:
            raise ValueError("committed state is not yet effective")
        if self.pending_state and (
            self.pending_state.effective_sequence_number <= self.current_window_sequence
        ):
            raise ValueError("pending state cannot affect current or past window")
        return self


class CommittedFastPathResult(StrictModel):
    schema_version: str = "committed-fast-path-result-v1"
    result_id: Identifier
    execution_role: Literal[ExecutionRole.COMMITTED_FAST_PATH] = (
        ExecutionRole.COMMITTED_FAST_PATH
    )
    committed: Literal[True] = True
    case_id: Identifier
    scenario_id: Identifier
    episode_id: Identifier
    split: DataSplit
    window: TimeWindow
    committed_state_id: Identifier
    detector: PIDSRef
    config_id: Identifier
    checkpoint_id: Identifier
    threshold_id: Identifier
    resource_preset_id: Identifier
    status: RunStatus
    score_summary: ScoreSummary
    alerts: tuple[DetectionAlert, ...] = ()
    artifact_manifest_id: Identifier
    provenance_id: Identifier
    started_at: Timestamp
    ended_at: Timestamp
    sanitized_failure_code: Identifier | None = None

    @model_validator(mode="after")
    def committed_result_is_complete(self) -> "CommittedFastPathResult":
        if self.ended_at < self.started_at:
            raise ValueError("committed inference timing is invalid")
        if self.status == RunStatus.SUCCEEDED and self.sanitized_failure_code:
            raise ValueError("successful committed result cannot carry failure")
        if self.status != RunStatus.SUCCEEDED and not self.sanitized_failure_code:
            raise ValueError("non-success committed result requires typed failure")
        if self.status != RunStatus.SUCCEEDED and (
            self.score_summary.count or self.alerts
        ):
            raise ValueError("failed committed inference cannot become an empty benign result")
        return self


class AdditionalDetectorRequest(StrictModel):
    request_id: Identifier
    case_id: Identifier
    window_id: Identifier
    approved_candidate_id: Identifier
    investigation_reason_code: Identifier
    visible_evidence_ids: tuple[Identifier, ...] = Field(min_length=1)


class AdditionalDetectorResult(StrictModel):
    schema_version: str = "additional-detector-result-v1"
    investigation_id: Identifier
    result_id: Identifier
    execution_role: Literal[ExecutionRole.ADDITIONAL_INVESTIGATION] = (
        ExecutionRole.ADDITIONAL_INVESTIGATION
    )
    committed: Literal[False] = False
    eligible_to_replace_committed_result: Literal[False] = False
    case_id: Identifier
    window: TimeWindow
    approved_candidate_id: Identifier
    detector: PIDSRef
    config_id: Identifier
    checkpoint_id: Identifier
    threshold_id: Identifier
    status: RunStatus
    score_summary: ScoreSummary
    alerts: tuple[DetectionAlert, ...] = ()
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    resource_pressure_class: Identifier
    provenance_id: Identifier
    sanitized_failure_code: Identifier | None = None

    @model_validator(mode="after")
    def failure_is_typed(self) -> "AdditionalDetectorResult":
        if self.status == RunStatus.SUCCEEDED and self.sanitized_failure_code:
            raise ValueError("successful investigation cannot carry failure")
        if self.status != RunStatus.SUCCEEDED and not self.sanitized_failure_code:
            raise ValueError("failed investigation requires typed failure")
        if self.status != RunStatus.SUCCEEDED and (
            self.score_summary.count or self.alerts
        ):
            raise ValueError("failed investigation cannot carry detection output")
        return self


class RawExecutionState(StrictModel):
    schema_version: str = "raw-execution-state-v1"
    builder_version: Identifier
    raw_state_id: Identifier
    execution_role: ExecutionRole
    case_id: Identifier
    window_id: Identifier
    result_id: Identifier
    command_manifest_id: Identifier
    artifact_ids: tuple[Identifier, ...]
    stage_status_ids: tuple[Identifier, ...]
    resource_lease_id: Identifier
    parser_id: Identifier
    parser_diagnostic_codes: tuple[Identifier, ...] = ()
    attempt_count: int = Field(ge=1)
    started_at: Timestamp
    ended_at: Timestamp
    content_hash: Sha256

    def expected_content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        return _content_hash(payload)

    @model_validator(mode="after")
    def raw_state_is_complete(self) -> "RawExecutionState":
        if self.ended_at < self.started_at:
            raise ValueError("raw execution timing is invalid")
        if self.content_hash != self.expected_content_hash():
            raise ValueError("raw execution state content hash mismatch")
        return self


class EnvironmentSummary(StrictModel):
    environment_profile_id: Identifier
    platform_class: Identifier
    provenance_schema_id: Identifier
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    entity_type_distribution: dict[Identifier, int]
    relation_type_distribution: dict[Identifier, int]
    event_rate: float = Field(ge=0, allow_inf_nan=False)
    graph_density: float = Field(ge=0, allow_inf_nan=False)
    normal_reference_status: Identifier


class ActiveDetectionSummary(StrictModel):
    detector: PIDSRef
    capability_type: Identifier
    committed_state_id: Identifier
    committed_config_id: Identifier
    checkpoint_id: Identifier
    threshold_id: Identifier
    resource_preset_id: Identifier
    score_semantics: Identifier
    detection_unit: DetectionUnit
    state_health: Identifier
    pending_change_id: Identifier | None = None
    pending_effective_sequence: int | None = Field(default=None, ge=0)


class DetectionSignalSummary(StrictModel):
    score_summary: ScoreSummary
    tail_mass: float = Field(ge=0, allow_inf_nan=False)
    alert_count: int = Field(ge=0)
    alert_ratio: float = Field(ge=0, le=1, allow_inf_nan=False)
    alert_entity_ids: tuple[Identifier, ...]
    alert_score_bands: dict[Identifier, int]
    recent_score_shift: float | None = Field(default=None, allow_inf_nan=False)
    recent_alert_volume_shift: float | None = Field(default=None, allow_inf_nan=False)
    instability_indicators: tuple[Identifier, ...] = ()
    degeneracy_indicators: tuple[Identifier, ...] = ()


class ExecutionSummary(StrictModel):
    status: RunStatus
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    cpu_time_seconds: float = Field(ge=0, allow_inf_nan=False)
    peak_memory_class: Identifier
    gpu_time_seconds: float = Field(ge=0, allow_inf_nan=False)
    gpu_memory_pressure_class: Identifier
    timeout_indicator: bool
    oom_indicator: bool
    sanitized_failure_code: Identifier | None
    cache_reuse_class: CacheReuseClass
    recomputation_scope: RecomputationScope
    provenance_id: Identifier


class CapabilityOption(StrictModel):
    detector: PIDSRef
    capability_type: Identifier
    available_status: AvailabilityStatus
    availability_reason_code: Identifier
    cost_class: Identifier
    limitation_codes: tuple[Identifier, ...]
    approved_candidate_ids: tuple[Identifier, ...]


class RuntimeBudgetSummary(StrictModel):
    remaining_slow_path_calls: int = Field(ge=0)
    remaining_retraining_calls: int = Field(ge=0)
    remaining_wall_time_class: Identifier
    token_usage_so_far: int = Field(ge=0)


class RuntimeMemorySummary(StrictModel):
    retrieved_record_ids: tuple[Identifier, ...] = ()
    applicability_summaries: tuple[Identifier, ...] = ()
    conflict_indicators: tuple[Identifier, ...] = ()


def _content_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class CanonicalAgentVisibleObservation(StrictModel):
    schema_version: str = "canonical-agent-observation-v1"
    builder_version: Identifier
    observation_id: Identifier
    case_id: Identifier
    scenario_id: Identifier
    episode_id: Identifier
    split: DataSplit
    observed_at: Timestamp
    window: TimeWindow
    environment: EnvironmentSummary
    active_detection: ActiveDetectionSummary
    detection_signal: DetectionSignalSummary
    execution: ExecutionSummary
    capability_options: tuple[CapabilityOption, ...]
    budget: RuntimeBudgetSummary
    memory: RuntimeMemorySummary
    source_raw_state_id: Identifier
    content_hash: Sha256

    def expected_content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        return _content_hash(payload)

    @model_validator(mode="after")
    def complete_deployable_observation(self) -> "CanonicalAgentVisibleObservation":
        if self.observed_at < self.window.end:
            raise ValueError("canonical observation cannot precede window close")
        if self.content_hash != self.expected_content_hash():
            raise ValueError("canonical observation content hash mismatch")
        assert_deployable_payload(
            self.model_dump(mode="json"), "canonical_agent_observation"
        )
        return self


class TriggerRecord(StrictModel):
    trigger_profile_id: Identifier
    triggered: bool
    reason_codes: tuple[Identifier, ...]
    decided_at: Timestamp

    @model_validator(mode="after")
    def reasons_match_decision(self) -> "TriggerRecord":
        if self.triggered != bool(self.reason_codes):
            raise ValueError("trigger decision and reason codes disagree")
        return self


class ModelPromptObservation(StrictModel):
    schema_version: str = "model-prompt-observation-v1"
    builder_version: Identifier
    tokenizer_id: Identifier
    prompt_id: Identifier
    canonical_observation_id: Identifier
    canonical_observation_hash: Sha256
    trigger: TriggerRecord
    allowed_actions: tuple[FrozenActionType, ...] = Field(min_length=1)
    visible_evidence_ids: tuple[Identifier, ...]
    included_memory_record_ids: tuple[Identifier, ...] = ()
    additional_result_ids: tuple[Identifier, ...] = ()
    token_budget: int = Field(ge=1)
    estimated_tokens: int = Field(ge=0)
    truncation_policy_id: Identifier
    truncation_status: Identifier
    rendered_text: str = Field(min_length=1)
    content_hash: Sha256

    def expected_content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        return _content_hash(payload)

    @model_validator(mode="after")
    def prompt_is_triggered_and_bounded(self) -> "ModelPromptObservation":
        if not self.trigger.triggered:
            raise ValueError("untriggered fast path must not create an LLM prompt")
        if self.estimated_tokens > self.token_budget:
            raise ValueError("rendered prompt exceeds its explicit token budget")
        if self.content_hash != self.expected_content_hash():
            raise ValueError("prompt observation content hash mismatch")
        assert_deployable_payload(self.model_dump(mode="json"), "model_prompt")
        return self


ACTION_TO_TOOL: dict[FrozenActionType, ToolName] = {
    FrozenActionType.RUN_ADDITIONAL_DETECTOR: ToolName.RUN_ADDITIONAL_DETECTOR,
    FrozenActionType.SELECT_VALIDATED_THRESHOLD: ToolName.SELECT_VALIDATED_THRESHOLD,
    FrozenActionType.LOAD_APPROVED_CONFIG: ToolName.LOAD_APPROVED_CONFIG,
    FrozenActionType.SWITCH_DETECTOR: ToolName.SWITCH_DETECTOR,
    FrozenActionType.RETRAIN_DETECTOR: ToolName.RETRAIN_DETECTOR,
    FrozenActionType.SELECT_RESOURCE_PRESET: ToolName.SELECT_RESOURCE_PRESET,
}


class FrozenActionDecision(StrictModel):
    schema_version: str = "frozen-action-decision-v1"
    action_id: Identifier
    action_type: FrozenActionType
    decision_source: DecisionSource
    case_id: Identifier
    window_id: Identifier
    current_sequence_number: int = Field(ge=0)
    based_on_observation_id: Identifier
    diagnosis_code: Identifier
    visible_evidence_ids: tuple[Identifier, ...]
    requested_tool: ToolName | None = None
    approved_choice_id: Identifier | None = None
    expected_effect: Identifier
    recomputation_scope: RecomputationScope
    cache_reuse_class: CacheReuseClass
    effective_sequence_number: int | None = Field(default=None, ge=0)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    commit_policy: Identifier
    fallback_policy: FrozenActionType

    @model_validator(mode="after")
    def action_has_exact_authority_and_timing(self) -> "FrozenActionDecision":
        expected_tool = ACTION_TO_TOOL.get(self.action_type)
        if self.requested_tool != expected_tool:
            raise ValueError("action and high-level tool do not match")
        if self.decision_source == DecisionSource.HARNESS_DEFAULT:
            if self.action_type != FrozenActionType.KEEP_CURRENT_CONFIG:
                raise ValueError("harness default can only keep current config")
        persistent = {
            FrozenActionType.SELECT_VALIDATED_THRESHOLD,
            FrozenActionType.LOAD_APPROVED_CONFIG,
            FrozenActionType.SWITCH_DETECTOR,
            FrozenActionType.SELECT_RESOURCE_PRESET,
        }
        if self.action_type in persistent:
            if not self.approved_choice_id:
                raise ValueError("persistent action requires an approved opaque choice")
            if self.effective_sequence_number is None or (
                self.effective_sequence_number <= self.current_sequence_number
            ):
                raise ValueError("persistent action must begin at a future window")
        elif self.effective_sequence_number is not None:
            raise ValueError("non-persistent action cannot schedule activation")
        if self.action_type in ACTION_TO_TOOL and not self.approved_choice_id:
            raise ValueError("tool action requires an approved opaque choice")
        if self.action_type in {
            FrozenActionType.KEEP_CURRENT_CONFIG,
            FrozenActionType.FINISH_DIAGNOSIS,
        } and self.approved_choice_id:
            raise ValueError("terminal no-tool action cannot carry a choice")
        if self.fallback_policy not in {
            FrozenActionType.KEEP_CURRENT_CONFIG,
            FrozenActionType.FINISH_DIAGNOSIS,
        }:
            raise ValueError("fallback must be a terminal no-tool action")
        return self


class HighLevelToolOutcome(StrictModel):
    schema_version: str = "high-level-tool-outcome-v1"
    outcome_id: Identifier
    action_id: Identifier
    tool_name: ToolName
    status: RunStatus
    approved_choice_id: Identifier
    result_id: Identifier | None = None
    pending_change_id: Identifier | None = None
    sanitized_failure_code: Identifier | None = None
    provenance_id: Identifier

    @model_validator(mode="after")
    def outcome_is_atomic_and_typed(self) -> "HighLevelToolOutcome":
        if self.status == RunStatus.SUCCEEDED:
            if self.sanitized_failure_code:
                raise ValueError("successful high-level tool cannot carry failure")
            if not self.result_id and not self.pending_change_id:
                raise ValueError("successful high-level tool requires one durable outcome")
        elif not self.sanitized_failure_code:
            raise ValueError("non-success high-level tool requires typed failure")
        if self.result_id and self.pending_change_id:
            raise ValueError("tool outcome cannot be both evidence and pending transition")
        return self


class FrozenWindowTransactionRecord(StrictModel):
    schema_version: str = "frozen-window-transaction-v1"
    transaction_id: Identifier
    case_id: Identifier
    scenario_id: Identifier
    episode_id: Identifier
    split: DataSplit
    window_id: Identifier
    window_sequence_number: int = Field(ge=0)
    committed_fast_path_result: CommittedFastPathResult
    raw_execution_state: RawExecutionState
    canonical_observation: CanonicalAgentVisibleObservation
    trigger: TriggerRecord
    model_prompt_observations: tuple[ModelPromptObservation, ...] = ()
    memory_protocol_status: Identifier
    memory_exchange_ids: tuple[Identifier, ...] = ()
    action_decisions: tuple[FrozenActionDecision, ...] = Field(min_length=1)
    additional_detector_tool_calls: tuple[HighLevelToolOutcome, ...] = ()
    additional_detector_results: tuple[AdditionalDetectorResult, ...] = ()
    persistent_tool_outcomes: tuple[HighLevelToolOutcome, ...] = ()
    pending_state_before_window: PendingDetectionState | None = None
    pending_state_after_window: PendingDetectionState | None = None
    started_at: Timestamp
    ended_at: Timestamp

    @model_validator(mode="after")
    def transaction_preserves_commit_and_authorship(self) -> "FrozenWindowTransactionRecord":
        if self.ended_at < self.started_at:
            raise ValueError("transaction timing is invalid")
        identity = (
            self.case_id,
            self.scenario_id,
            self.episode_id,
            self.split,
            self.window_id,
            self.window_sequence_number,
        )
        committed = self.committed_fast_path_result
        committed_identity = (
            committed.case_id,
            committed.scenario_id,
            committed.episode_id,
            committed.split,
            committed.window.window_id,
            committed.window.sequence_number,
        )
        if identity != committed_identity:
            raise ValueError("transaction and committed result identities disagree")
        if self.raw_execution_state.result_id != committed.result_id:
            raise ValueError("raw state does not describe committed result")
        if self.canonical_observation.source_raw_state_id != self.raw_execution_state.raw_state_id:
            raise ValueError("canonical observation does not derive from raw state")
        if any(
            self.canonical_observation.observation_id != action.based_on_observation_id
            for action in self.action_decisions
        ):
            raise ValueError("action does not cite canonical observation")
        if not self.trigger.triggered:
            action = self.action_decisions[0]
            if self.model_prompt_observations or len(self.action_decisions) != 1:
                raise ValueError("untriggered window cannot contain an assistant turn")
            if self.additional_detector_tool_calls or self.additional_detector_results:
                raise ValueError("untriggered window cannot contain slow-path evidence")
            if self.persistent_tool_outcomes:
                raise ValueError("untriggered window cannot reconfigure state")
            if self.pending_state_after_window != self.pending_state_before_window:
                raise ValueError("untriggered window cannot change pending state")
            if (
                action.action_type != FrozenActionType.KEEP_CURRENT_CONFIG
                or action.decision_source != DecisionSource.HARNESS_DEFAULT
            ):
                raise ValueError("untriggered action must be harness-default keep")
        else:
            if not self.model_prompt_observations:
                raise ValueError("triggered window requires a prompt observation")
            if len(self.model_prompt_observations) != len(self.action_decisions):
                raise ValueError("each slow-path decision requires its own prompt projection")
            if any(
                action.decision_source != DecisionSource.LLM_AGENT
                for action in self.action_decisions
            ):
                raise ValueError("slow-path actions must be authored by the LLM Agent")
            if any(prompt.trigger != self.trigger for prompt in self.model_prompt_observations):
                raise ValueError("prompt trigger provenance changed within transaction")
            if self.memory_protocol_status == "frozen-two-turn":
                if len(self.memory_exchange_ids) != len(self.model_prompt_observations):
                    raise ValueError("each prompt requires one frozen memory exchange")
            elif self.memory_protocol_status == "legacy-no-memory-protocol":
                if self.memory_exchange_ids:
                    raise ValueError("legacy trace cannot claim memory exchanges")
            else:
                raise ValueError("unknown memory protocol status")
        result_ids = {item.result_id for item in self.additional_detector_results}
        outcome_result_ids = {
            item.result_id
            for item in self.additional_detector_tool_calls
            if item.result_id is not None
        }
        if result_ids != outcome_result_ids:
            raise ValueError("additional result IDs must match completed tool outcomes")
        if any(
            item.status == RunStatus.SUCCEEDED and item.result_id is None
            for item in self.additional_detector_tool_calls
        ):
            raise ValueError("successful additional call requires separate detector result")
        if any(result.committed for result in self.additional_detector_results):
            raise ValueError("additional detector result cannot replace committed result")
        return self
