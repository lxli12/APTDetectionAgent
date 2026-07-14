"""Deterministic canonical observation, trigger, and prompt builders.

Token compression is deliberately not guessed: an over-budget prompt fails closed
until a validation-approved truncation policy exists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from pydantic import Field, model_validator

from apt_detection_agent.schemas import (
    AdditionalDetectorResult,
    CanonicalAgentVisibleObservation,
    CapabilityOption,
    DataSplit,
    DetectionUnit,
    DetectionSignalSummary,
    EnvironmentSummary,
    ExecutionSummary,
    FrozenActionType,
    FrozenCaseState,
    ModelPromptObservation,
    RuntimeBudgetSummary,
    RuntimeMemorySummary,
    TriggerRecord,
)
from apt_detection_agent.schemas.agent_runtime import ActiveDetectionSummary
from apt_detection_agent.schemas.common import Identifier, StrictModel

from .controller import CommittedExecutionBundle


class CanonicalObservationInputs(StrictModel):
    builder_version: Identifier
    observation_id: Identifier
    observed_at: datetime
    environment: EnvironmentSummary
    detection_signal: DetectionSignalSummary
    execution: ExecutionSummary
    capability_options: tuple[CapabilityOption, ...]
    budget: RuntimeBudgetSummary
    memory: RuntimeMemorySummary
    capability_type: Identifier
    score_semantics: Identifier
    detection_unit: DetectionUnit


CanonicalInputProvider = Callable[
    [CommittedExecutionBundle, FrozenCaseState], CanonicalObservationInputs
]


@dataclass(frozen=True)
class DeterministicCanonicalObservationBuilder:
    input_provider: CanonicalInputProvider

    def __call__(
        self,
        bundle: CommittedExecutionBundle,
        case: FrozenCaseState,
    ) -> CanonicalAgentVisibleObservation:
        inputs = self.input_provider(bundle, case)
        state = case.committed_state
        pending = case.pending_state
        payload: dict[str, object] = {
            "builder_version": inputs.builder_version,
            "observation_id": inputs.observation_id,
            "case_id": case.case_id,
            "scenario_id": case.scenario_id,
            "episode_id": case.episode_id,
            "split": case.split,
            "observed_at": inputs.observed_at,
            "window": bundle.result.window,
            "environment": inputs.environment,
            "active_detection": ActiveDetectionSummary(
                detector=state.detector,
                capability_type=inputs.capability_type,
                committed_state_id=state.state_id,
                committed_config_id=state.config_id,
                checkpoint_id=state.checkpoint_id,
                threshold_id=state.threshold_id,
                resource_preset_id=state.resource_preset_id,
                score_semantics=inputs.score_semantics,
                detection_unit=inputs.detection_unit,
                state_health=state.state_health,
                pending_change_id=pending.pending_change_id if pending else None,
                pending_effective_sequence=(
                    pending.effective_sequence_number if pending else None
                ),
            ),
            "detection_signal": inputs.detection_signal,
            "execution": inputs.execution,
            "capability_options": inputs.capability_options,
            "budget": inputs.budget,
            "memory": inputs.memory,
            "source_raw_state_id": bundle.raw_state.raw_state_id,
        }
        provisional = CanonicalAgentVisibleObservation.model_construct(
            **payload, content_hash="0" * 64
        )
        payload["content_hash"] = provisional.expected_content_hash()
        return CanonicalAgentVisibleObservation.model_validate(payload)


class FrozenTriggerProfile(StrictModel):
    profile_id: Identifier
    source_split: DataSplit
    failure_trigger_enabled: bool = True
    alert_count_threshold: int | None = Field(default=None, ge=1)
    alert_count_calibration_artifact_id: Identifier | None = None
    periodic_window_count: int | None = Field(default=None, ge=1)
    periodic_calibration_artifact_id: Identifier | None = None

    @model_validator(mode="after")
    def empirical_triggers_are_validation_frozen(self) -> "FrozenTriggerProfile":
        if self.source_split != DataSplit.VALIDATION:
            raise ValueError("trigger profile must be frozen from validation")
        if bool(self.alert_count_threshold) != bool(self.alert_count_calibration_artifact_id):
            raise ValueError("alert trigger requires threshold and validation evidence")
        if bool(self.periodic_window_count) != bool(self.periodic_calibration_artifact_id):
            raise ValueError("periodic trigger requires interval and validation evidence")
        return self


@dataclass(frozen=True)
class DeterministicTriggerPolicy:
    profile: FrozenTriggerProfile
    clock: Callable[[], datetime]

    def __call__(self, observation: CanonicalAgentVisibleObservation) -> TriggerRecord:
        reasons: list[str] = []
        if self.profile.failure_trigger_enabled and observation.execution.status.value != "succeeded":
            reasons.append("observable-execution-failure")
        if (
            self.profile.alert_count_threshold is not None
            and observation.detection_signal.alert_count
            >= self.profile.alert_count_threshold
        ):
            reasons.append("validation-frozen-alert-volume")
        if (
            self.profile.periodic_window_count is not None
            and observation.window.sequence_number % self.profile.periodic_window_count == 0
        ):
            reasons.append("validation-frozen-periodic-check")
        decided_at = self.clock()
        if decided_at < observation.observed_at:
            raise ValueError("trigger decision cannot precede canonical observation")
        return TriggerRecord(
            trigger_profile_id=self.profile.profile_id,
            triggered=bool(reasons),
            reason_codes=tuple(reasons),
            decided_at=decided_at,
        )


TokenCounter = Callable[[str], int]


class PromptBuilderConfig(StrictModel):
    builder_version: Identifier
    tokenizer_id: Identifier
    token_budget: int = Field(ge=1)
    truncation_policy_id: Identifier = "unresolved-requires-experiment"


@dataclass(frozen=True)
class DeterministicPromptBuilder:
    config: PromptBuilderConfig
    token_counter: TokenCounter

    def __call__(
        self,
        canonical: CanonicalAgentVisibleObservation,
        trigger: TriggerRecord,
        additional_results: tuple[AdditionalDetectorResult, ...],
    ) -> ModelPromptObservation:
        if not trigger.triggered:
            raise ValueError("untriggered window has no model prompt")
        prompt_id = f"prompt-{canonical.window.window_id}-{len(additional_results)}"
        body = {
            "canonical_observation": canonical.model_dump(mode="json"),
            "trigger": trigger.model_dump(mode="json"),
            "allowed_actions": [item.value for item in FrozenActionType],
            "additional_detector_results": [
                {
                    "result_id": item.result_id,
                    "approved_candidate_id": item.approved_candidate_id,
                    "detector": item.detector.model_dump(mode="json"),
                    "status": item.status.value,
                    "score_summary": item.score_summary.model_dump(mode="json"),
                    "alert_entity_ids": [alert.entity_id for alert in item.alerts],
                    "elapsed_seconds": item.elapsed_seconds,
                    "resource_pressure_class": item.resource_pressure_class,
                    "provenance_id": item.provenance_id,
                    "sanitized_failure_code": item.sanitized_failure_code,
                }
                for item in additional_results
            ],
        }
        rendered = json.dumps(body, sort_keys=True, separators=(",", ":"))
        estimated_tokens = self.token_counter(rendered)
        if estimated_tokens > self.config.token_budget:
            raise ValueError(
                "prompt exceeds budget; truncation is UNRESOLVED_REQUIRES_EXPERIMENT"
            )
        payload: dict[str, object] = {
            "builder_version": self.config.builder_version,
            "tokenizer_id": self.config.tokenizer_id,
            "prompt_id": prompt_id,
            "canonical_observation_id": canonical.observation_id,
            "canonical_observation_hash": canonical.content_hash,
            "trigger": trigger,
            "allowed_actions": tuple(FrozenActionType),
            "visible_evidence_ids": (
                canonical.observation_id,
                canonical.execution.provenance_id,
            ),
            "included_memory_record_ids": canonical.memory.retrieved_record_ids,
            "additional_result_ids": tuple(item.result_id for item in additional_results),
            "token_budget": self.config.token_budget,
            "estimated_tokens": estimated_tokens,
            "truncation_policy_id": self.config.truncation_policy_id,
            "truncation_status": "not-truncated",
            "rendered_text": rendered,
        }
        provisional = ModelPromptObservation.model_construct(
            **payload, content_hash="0" * 64
        )
        payload["content_hash"] = provisional.expected_content_hash()
        return ModelPromptObservation.model_validate(payload)
