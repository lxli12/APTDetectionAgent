"""Canonical pre-SFT demonstration construction contracts and validators.

Requirements: REQ-RUNTIME-001..006, REQ-PIDS-006, REQ-SFT-001..004,
REQ-LABEL-001..004, REQ-REPRO-001..003.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from pydantic import Field, model_validator

from apt_detection_agent.schemas import (
    AdditionalDetectorResult,
    DataSplit,
    DetectionUnit,
    FrozenActionType,
    FrozenMemoryExchange,
    HighLevelToolOutcome,
    ModelPromptObservation,
    PIDSRef,
    RunStatus,
)
from apt_detection_agent.schemas.common import GitSha, Identifier, Sha256, StrictModel, Timestamp
from apt_detection_agent.schemas.evaluation import assert_deployable_payload
from apt_detection_agent.tooling.runtime_tools import DetectorCapabilityView


class LabelAvailability(str, Enum):
    NONE = "none"
    PRIVATE_AVAILABLE = "private_available"
    UNVERIFIED = "unverified"


class GraphConstructionManifest(StrictModel):
    builder_id: Identifier
    origin: Timestamp
    timezone: str
    window_size_seconds: int = Field(gt=0)
    half_open_alignment: bool
    entity_types: tuple[Identifier, ...]
    relation_types: tuple[Identifier, ...]
    transformation_policy_ids: tuple[Identifier, ...]

    @model_validator(mode="after")
    def alignment_is_mandatory(self) -> "GraphConstructionManifest":
        if not self.half_open_alignment:
            raise ValueError("demonstration graph construction must use [start,end)")
        return self


class PIDSDataPartitions(StrictModel):
    train_partition_ref: Identifier
    validation_partition_ref: Identifier
    demonstration_partition_ref: Identifier


class DemonstrationTrainingUse(StrictModel):
    pids_fit_allowed: bool
    threshold_calibration_allowed: bool
    sft_demonstration_allowed: bool
    held_out_sft_forbidden: bool = True

    @model_validator(mode="after")
    def heldout_is_always_forbidden(self) -> "DemonstrationTrainingUse":
        if not self.held_out_sft_forbidden:
            raise ValueError("held-out windows cannot enter SFT construction")
        return self


class DemonstrationDatasetManifest(StrictModel):
    schema_version: str = "demonstration-dataset-manifest-v1"
    dataset_manifest_id: Identifier
    dataset_id: Identifier
    source_family: Identifier
    source_release: Identifier
    source_format: Identifier
    source_content_hashes: tuple[Sha256, ...] = Field(min_length=1)
    access_and_license_status: Identifier
    normalized_storage_schema_id: Identifier
    provenance_schema_id: Identifier
    platform_class: Identifier
    graph_construction: GraphConstructionManifest
    pids_data_partitions: PIDSDataPartitions
    registered_pids: tuple[PIDSRef, ...] = Field(min_length=1)
    pids_admission_ids: tuple[Identifier, ...] = ()
    label_availability: LabelAvailability
    training_use: DemonstrationTrainingUse
    private_companion_manifest_id: Identifier
    code_commit: GitSha
    builder_version: Identifier
    created_at: Timestamp
    content_hash: Sha256

    def expected_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        return _hash(payload)

    @model_validator(mode="after")
    def public_manifest_is_deployable_and_hashed(self) -> "DemonstrationDatasetManifest":
        if len(self.registered_pids) != len(set((x.pids_id, x.variant_id) for x in self.registered_pids)):
            raise ValueError("registered PIDS identities must be unique")
        if self.content_hash != self.expected_hash():
            raise ValueError("dataset manifest content hash mismatch")
        assert_deployable_payload(self.model_dump(mode="json"), "dataset_manifest")
        return self


class ExecutionDisposition(str, Enum):
    EXECUTED = "executed"
    CAPABILITY_ONLY = "capability_only"
    REJECTED = "rejected"


class ObservableBehavior(StrictModel):
    behavior_id: Identifier
    summary: str = Field(min_length=1)
    evidence_ids: tuple[Identifier, ...]
    unknown_codes: tuple[Identifier, ...] = ()


class HistoricalEvidenceContext(StrictModel):
    past_window_ids: tuple[Identifier, ...]
    prior_result_ids: tuple[Identifier, ...]
    prior_action_ids: tuple[Identifier, ...]
    prior_failure_codes: tuple[Identifier, ...]
    prior_state_change_ids: tuple[Identifier, ...]
    memory_record_ids: tuple[Identifier, ...]


class TemporalContext(StrictModel):
    window_id: Identifier
    sequence_number: int = Field(ge=0)
    start: Timestamp
    end: Timestamp
    past_range_window_ids: tuple[Identifier, ...]
    state_continuity_code: Identifier

    @model_validator(mode="after")
    def chronological_context(self) -> "TemporalContext":
        if self.end <= self.start:
            raise ValueError("temporal context interval must increase")
        if self.window_id in self.past_range_window_ids:
            raise ValueError("current window cannot appear in past range")
        return self


class OpaqueConfigurationSummary(StrictModel):
    approved_config_id: Identifier
    checkpoint_id: Identifier
    threshold_id: Identifier
    resource_preset_id: Identifier


class VisibleCostSummary(StrictModel):
    wall_time_seconds: float = Field(ge=0, allow_inf_nan=False)
    cpu_time_seconds: float = Field(ge=0, allow_inf_nan=False)
    gpu_time_seconds: float = Field(ge=0, allow_inf_nan=False)
    memory_pressure_class: Identifier
    gpu_pressure_class: Identifier
    cache_reuse_class: Identifier
    tool_call_count: int = Field(ge=0)
    llm_call_count: int = Field(ge=0)
    token_count: int = Field(ge=0)


class VisibleFailureCondition(StrictModel):
    failure_code: Identifier
    applicability_codes: tuple[Identifier, ...]
    avoid_condition_codes: tuple[Identifier, ...]


class PublicOfflineRunRecord(StrictModel):
    schema_version: str = "public-offline-run-record-v1"
    run_record_id: Identifier
    counterfactual_group_id: Identifier
    dataset_manifest_id: Identifier
    episode_id: Identifier
    split: DataSplit
    environment_profile_id: Identifier
    observable_behavior: ObservableBehavior
    historical_evidence_context: HistoricalEvidenceContext
    temporal_context: TemporalContext
    pids_capability: DetectorCapabilityView
    detector: PIDSRef
    configuration: OpaqueConfigurationSummary
    admitted_use: Identifier
    execution_disposition: ExecutionDisposition
    standardized_result_id: Identifier | None = None
    deployment_visible_outcome_code: Identifier
    cost: VisibleCostSummary
    failure_condition: VisibleFailureCondition | None = None
    execution_role: Identifier
    public_runtime_trace_id: Identifier
    admission_id: Identifier | None = None
    provenance_id: Identifier
    content_hash: Sha256

    def expected_hash(self) -> str:
        return _hash(self.model_dump(mode="json", exclude={"content_hash"}))

    @model_validator(mode="after")
    def disposition_and_admission_are_coherent(self) -> "PublicOfflineRunRecord":
        if self.split != DataSplit.AGENT_TRAINING:
            raise ValueError("SFT offline records are agent-training only")
        if self.execution_disposition == ExecutionDisposition.EXECUTED:
            if not self.admission_id or not self.standardized_result_id or self.failure_condition:
                raise ValueError("executed row requires admission/result and no rejection")
        elif not self.failure_condition:
            raise ValueError("non-executed row requires typed visible condition")
        if self.content_hash != self.expected_hash():
            raise ValueError("offline run record hash mismatch")
        assert_deployable_payload(self.model_dump(mode="json"), "offline_run")
        return self


class CoverageClass(str, Enum):
    CAPABILITY_AWARENESS = "capability_awareness"
    SUCCESSFUL_TOOL_USE = "successful_tool_use"
    FAILURE_OR_REJECTION = "failure_or_rejection"
    COUNTERFACTUAL_CHOICE = "counterfactual_choice"
    MEMORY_ADAPTATION = "memory_adaptation"


class VisibleEvidenceGrounding(StrictModel):
    observable_symptom: str = Field(min_length=1)
    graph_evidence_ids: tuple[Identifier, ...] = ()
    score_evidence_ids: tuple[Identifier, ...] = ()
    trend_evidence_ids: tuple[Identifier, ...] = ()
    resource_evidence_ids: tuple[Identifier, ...] = ()
    historical_evidence_ids: tuple[Identifier, ...] = ()
    observed_fact_codes: tuple[Identifier, ...]
    bounded_inference_codes: tuple[Identifier, ...]
    unknown_codes: tuple[Identifier, ...]
    uncertainty_code: Identifier
    action_justification: str = Field(min_length=1)

    @property
    def cited_ids(self) -> set[str]:
        return set(
            self.graph_evidence_ids
            + self.score_evidence_ids
            + self.trend_evidence_ids
            + self.resource_evidence_ids
            + self.historical_evidence_ids
        )


class DemonstrationExchange(StrictModel):
    exchange_id: Identifier
    memory_exchange: FrozenMemoryExchange
    grounding: VisibleEvidenceGrounding
    action_tool_outcome: HighLevelToolOutcome | None = None
    additional_detector_result: AdditionalDetectorResult | None = None
    supplemental_prompt: ModelPromptObservation | None = None

    @model_validator(mode="after")
    def tool_pairing_matches_action(self) -> "DemonstrationExchange":
        action = self.memory_exchange.response.action
        no_tool = {
            FrozenActionType.KEEP_CURRENT_CONFIG,
            FrozenActionType.FINISH_DIAGNOSIS,
        }
        if action.action_type in no_tool:
            if self.action_tool_outcome or self.additional_detector_result or self.supplemental_prompt:
                raise ValueError("terminal no-tool action cannot carry tool events")
            return self
        outcome = self.action_tool_outcome
        if outcome is None or outcome.action_id != action.action_id or outcome.tool_name != action.requested_tool:
            raise ValueError("tool action requires exact paired outcome")
        if action.action_type == FrozenActionType.RUN_ADDITIONAL_DETECTOR:
            if outcome.status == RunStatus.SUCCEEDED:
                if (
                    self.additional_detector_result is None
                    or self.additional_detector_result.result_id != outcome.result_id
                    or self.additional_detector_result.committed
                    or self.supplemental_prompt is None
                ):
                    raise ValueError("successful additional detector requires result and supplemental prompt")
            elif self.additional_detector_result or self.supplemental_prompt:
                raise ValueError("preflight rejection cannot fabricate detector output")
        elif self.additional_detector_result or self.supplemental_prompt:
            raise ValueError("non-additional tool cannot carry supplemental detector result")
        return self


class CanonicalDemonstrationTrajectory(StrictModel):
    schema_version: str = "canonical-demonstration-trajectory-v1"
    trajectory_id: Identifier
    partition_group_id: Identifier
    source_run_record_ids: tuple[Identifier, ...] = Field(min_length=1)
    source_admission_ids: tuple[Identifier, ...] = ()
    initial_prompt: ModelPromptObservation
    exchanges: tuple[DemonstrationExchange, ...] = Field(min_length=1)
    pids_coverage: tuple[PIDSRef, ...] = Field(min_length=1)
    coverage_classes: tuple[CoverageClass, ...] = Field(min_length=1)
    sanitizer_version: Identifier
    content_hash: Sha256

    def expected_hash(self) -> str:
        return _hash(self.model_dump(mode="json", exclude={"content_hash"}))

    @model_validator(mode="after")
    def ordering_evidence_and_admission_close(self) -> "CanonicalDemonstrationTrajectory":
        expected_prompt = self.initial_prompt
        visible_ids: set[str] = set(expected_prompt.visible_evidence_ids)
        visible_ids.add(expected_prompt.canonical_observation_id)
        available_choices = _visible_approved_choices(expected_prompt)
        for index, exchange in enumerate(self.exchanges):
            if exchange.memory_exchange.prompt != expected_prompt:
                raise ValueError("demonstration prompt sequence is not causal")
            retrieval = exchange.memory_exchange.retrieval_result
            visible_ids.update(record.memory_id for record in retrieval.records)
            if not exchange.grounding.cited_ids.issubset(visible_ids):
                raise ValueError("grounding cites evidence not yet visible")
            action = exchange.memory_exchange.response.action
            if action.approved_choice_id and action.approved_choice_id not in available_choices:
                raise ValueError("action choice is absent from visible approved candidates")
            outcome = exchange.action_tool_outcome
            if outcome:
                visible_ids.add(outcome.outcome_id)
                if outcome.result_id:
                    visible_ids.add(outcome.result_id)
            if exchange.supplemental_prompt:
                if index + 1 >= len(self.exchanges):
                    raise ValueError("supplemental prompt requires a following decision exchange")
                expected_prompt = exchange.supplemental_prompt
                visible_ids.update(expected_prompt.visible_evidence_ids)
                available_choices = _visible_approved_choices(expected_prompt)
            elif index + 1 < len(self.exchanges):
                raise ValueError("new exchange requires a prior supplemental prompt")
        if CoverageClass.SUCCESSFUL_TOOL_USE in self.coverage_classes and not self.source_admission_ids:
            raise ValueError("successful tool supervision requires admission evidence")
        if self.content_hash != self.expected_hash():
            raise ValueError("canonical demonstration trajectory hash mismatch")
        assert_deployable_payload(self.model_dump(mode="json"), "demonstration_trajectory")
        return self


class DemonstrationRejection(StrictModel):
    rejection_id: Identifier
    candidate_trajectory_id: Identifier
    reason_code: Identifier
    offending_field_paths: tuple[str, ...]
    private_ledger_only: bool = True

    @model_validator(mode="after")
    def never_publicly_exported(self) -> "DemonstrationRejection":
        if not self.private_ledger_only:
            raise ValueError("rejection detail ledger must remain private")
        return self


def _hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def _visible_approved_choices(prompt: ModelPromptObservation) -> set[str]:
    """Extract choices only from a canonical structured prompt; opaque text grants none."""

    try:
        payload = json.loads(prompt.rendered_text)
    except json.JSONDecodeError:
        return set()
    if not isinstance(payload, dict):
        return set()
    observation = payload.get("canonical_observation", {})
    if not isinstance(observation, dict):
        return set()
    choices: set[str] = set()
    options = observation.get("capability_options", [])
    if not isinstance(options, list):
        return set()
    for option in options:
        if not isinstance(option, dict):
            continue
        candidate_ids = option.get("approved_candidate_ids", [])
        if isinstance(candidate_ids, list):
            choices.update(item for item in candidate_ids if isinstance(item, str))
    return choices
