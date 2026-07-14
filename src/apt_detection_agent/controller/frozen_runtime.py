"""Frozen current-window transaction harness.

The committed fast path is an internal harness operation.  Only a triggered slow
path may create a prompt or call the Agent policy.

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001..004,
REQ-WINDOW-001..004, REQ-CONFIG-001..003, REQ-TOOL-001..005,
REQ-REPRO-001..003.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from pydantic import Field, model_validator

from apt_detection_agent.schemas import (
    AdditionalDetectorResult,
    CacheReuseClass,
    CanonicalAgentVisibleObservation,
    CommittedDetectionState,
    CommittedFastPathResult,
    DataSplit,
    DecisionSource,
    ExecutionRole,
    FrozenActionDecision,
    FrozenActionType,
    FrozenCaseState,
    FrozenMemoryExchange,
    FrozenWindowTransactionRecord,
    HighLevelToolOutcome,
    MemoryDecisionEnvelope,
    ModelPromptObservation,
    PendingDetectionState,
    RawExecutionState,
    RecomputationScope,
    RunStatus,
    TimeWindow,
    TriggerRecord,
)
from apt_detection_agent.schemas.common import Identifier, StrictModel, Timestamp


class FrozenRuntimeConfig(StrictModel):
    trigger_profile_id: Identifier
    trigger_source_split: DataSplit
    additional_cycle_budget_policy_id: Identifier = "unresolved-requires-experiment"
    max_additional_detector_cycles: int = Field(default=1, ge=0, le=8)
    require_frozen_memory_protocol: bool = True

    @model_validator(mode="after")
    def trigger_is_validation_frozen(self) -> "FrozenRuntimeConfig":
        if self.trigger_source_split != DataSplit.VALIDATION:
            raise ValueError("runtime trigger profile must be frozen from validation")
        return self


class CommittedFastPathInferenceRequest(StrictModel):
    """Internal-only request created from the immutable state snapshot."""

    request_id: Identifier
    case_id: Identifier
    scenario_id: Identifier
    episode_id: Identifier
    split: DataSplit
    window: TimeWindow
    committed_state: CommittedDetectionState
    requested_at: Timestamp


@dataclass(frozen=True)
class CommittedExecutionBundle:
    result: CommittedFastPathResult
    raw_state: RawExecutionState


@dataclass(frozen=True)
class ActionExecutionEnvelope:
    outcome: HighLevelToolOutcome
    additional_result: AdditionalDetectorResult | None = None
    pending_state: PendingDetectionState | None = None


@dataclass(frozen=True)
class FrozenWindowStepResult:
    record: FrozenWindowTransactionRecord
    next_case: FrozenCaseState


CommittedExecutor = Callable[[CommittedFastPathInferenceRequest], CommittedExecutionBundle]
CanonicalBuilder = Callable[
    [CommittedExecutionBundle, FrozenCaseState], CanonicalAgentVisibleObservation
]
TriggerPolicy = Callable[[CanonicalAgentVisibleObservation], TriggerRecord]
PromptBuilder = Callable[
    [
        CanonicalAgentVisibleObservation,
        TriggerRecord,
        tuple[AdditionalDetectorResult, ...],
    ],
    ModelPromptObservation,
]
SlowPathPolicy = Callable[
    [ModelPromptObservation, FrozenCaseState],
    FrozenActionDecision | MemoryDecisionEnvelope,
]
ActionExecutor = Callable[[FrozenActionDecision, FrozenCaseState], ActionExecutionEnvelope]


class CommittedResultLedger:
    """Append-only, exactly-once ledger keyed by scenario/episode/window."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _existing_keys(self) -> set[tuple[str, str, str]]:
        if not self.path.exists():
            return set()
        keys: set[tuple[str, str, str]] = set()
        for line_number, line in enumerate(self.path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = CommittedFastPathResult.model_validate_json(line)
            except Exception as exc:
                raise ValueError(
                    f"invalid committed ledger record at line {line_number}"
                ) from exc
            key = (item.scenario_id, item.episode_id, item.window.window_id)
            if key in keys:
                raise ValueError("committed ledger already contains a duplicate key")
            keys.add(key)
        return keys

    def append(self, result: CommittedFastPathResult) -> None:
        key = (result.scenario_id, result.episode_id, result.window.window_id)
        if key in self._existing_keys():
            raise ValueError("exactly one committed result is allowed per window")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(result.model_dump_json() + "\n")
            handle.flush()


class FrozenTransactionLogger:
    """Append-only full transaction audit log."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, record: FrozenWindowTransactionRecord) -> None:
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if not line.strip():
                    continue
                existing = json.loads(line)
                if existing.get("transaction_id") == record.transaction_id:
                    raise ValueError("transaction identity is append-only")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")
            handle.flush()

    def append_memory_exchange(self, exchange: FrozenMemoryExchange) -> None:
        path = self.path.with_name("memory_exchanges.jsonl")
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip() and json.loads(line).get("exchange_id") == exchange.exchange_id:
                    raise ValueError("memory exchange identity is append-only")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(exchange.model_dump_json() + "\n")
            handle.flush()


def prepare_case_for_window(
    case: FrozenCaseState,
    *,
    sequence_number: int,
    activated_at: datetime,
) -> FrozenCaseState:
    """Advance exactly one window and atomically activate an admitted pending state."""

    if sequence_number != case.current_window_sequence + 1:
        raise ValueError("case windows must advance exactly once in sequence")
    pending = case.pending_state
    if pending and pending.effective_sequence_number < sequence_number:
        raise ValueError("pending activation boundary was missed")
    committed = case.committed_state
    remaining_pending = pending
    if pending and pending.effective_sequence_number == sequence_number:
        committed = CommittedDetectionState(
            state_id=f"activated-{pending.pending_change_id}",
            detector=pending.target_detector,
            approved_candidate_id=pending.approved_choice_id,
            config_id=pending.target_config_id,
            checkpoint_id=pending.target_checkpoint_id,
            threshold_id=pending.target_threshold_id,
            resource_preset_id=pending.target_resource_preset_id,
            state_token=pending.target_state_token,
            state_health=pending.target_state_health,
            effective_sequence_number=sequence_number,
        )
        remaining_pending = None
    return FrozenCaseState(
        case_id=case.case_id,
        scenario_id=case.scenario_id,
        episode_id=case.episode_id,
        split=case.split,
        current_window_sequence=sequence_number,
        committed_state=committed,
        pending_state=remaining_pending,
        memory_namespace=case.memory_namespace,
        updated_at=activated_at,
    )


@dataclass
class FrozenRuntimeController:
    config: FrozenRuntimeConfig
    committed_executor: CommittedExecutor
    canonical_builder: CanonicalBuilder
    trigger_policy: TriggerPolicy
    prompt_builder: PromptBuilder
    policy: SlowPathPolicy
    action_executor: ActionExecutor
    committed_ledger: CommittedResultLedger
    transaction_logger: FrozenTransactionLogger

    @staticmethod
    def _validate_case_window(case: FrozenCaseState, window: TimeWindow) -> None:
        if window.sequence_number != case.current_window_sequence:
            raise ValueError("case state does not belong to current window")
        if case.committed_state.effective_sequence_number > window.sequence_number:
            raise ValueError("committed state is not effective for current window")

    @staticmethod
    def _validate_committed_bundle(
        request: CommittedFastPathInferenceRequest,
        bundle: CommittedExecutionBundle,
    ) -> None:
        result = bundle.result
        state = request.committed_state
        if (
            result.case_id != request.case_id
            or result.scenario_id != request.scenario_id
            or result.episode_id != request.episode_id
            or result.split != request.split
            or result.window != request.window
            or result.detector != state.detector
            or result.committed_state_id != state.state_id
            or result.config_id != state.config_id
            or result.checkpoint_id != state.checkpoint_id
            or result.threshold_id != state.threshold_id
            or result.resource_preset_id != state.resource_preset_id
        ):
            raise ValueError("committed executor did not use the bound state snapshot")
        raw = bundle.raw_state
        if (
            raw.execution_role != ExecutionRole.COMMITTED_FAST_PATH
            or raw.case_id != request.case_id
            or raw.window_id != request.window.window_id
            or raw.result_id != result.result_id
        ):
            raise ValueError("raw execution state does not match committed execution")

    @staticmethod
    def _validate_canonical(
        canonical: CanonicalAgentVisibleObservation,
        case: FrozenCaseState,
        bundle: CommittedExecutionBundle,
    ) -> None:
        state = case.committed_state
        if (
            canonical.case_id != case.case_id
            or canonical.scenario_id != case.scenario_id
            or canonical.episode_id != case.episode_id
            or canonical.split != case.split
            or canonical.window != bundle.result.window
            or canonical.source_raw_state_id != bundle.raw_state.raw_state_id
            or canonical.active_detection.committed_state_id != state.state_id
            or canonical.active_detection.committed_config_id != state.config_id
            or canonical.active_detection.checkpoint_id != state.checkpoint_id
            or canonical.active_detection.threshold_id != state.threshold_id
            or canonical.active_detection.resource_preset_id != state.resource_preset_id
        ):
            raise ValueError("canonical builder changed immutable runtime identity")

    @staticmethod
    def _default_keep(
        canonical: CanonicalAgentVisibleObservation,
    ) -> FrozenActionDecision:
        return FrozenActionDecision(
            action_id=f"harness-keep-{canonical.window.window_id}",
            action_type=FrozenActionType.KEEP_CURRENT_CONFIG,
            decision_source=DecisionSource.HARNESS_DEFAULT,
            case_id=canonical.case_id,
            window_id=canonical.window.window_id,
            current_sequence_number=canonical.window.sequence_number,
            based_on_observation_id=canonical.observation_id,
            diagnosis_code="no-trigger",
            visible_evidence_ids=(),
            expected_effect="preserve-current-admitted-state",
            recomputation_scope=RecomputationScope.NONE,
            cache_reuse_class=CacheReuseClass.FULL,
            confidence=1.0,
            commit_policy="no-current-window-rewrite",
            fallback_policy=FrozenActionType.KEEP_CURRENT_CONFIG,
        )

    @staticmethod
    def _validate_agent_action(
        action: FrozenActionDecision,
        canonical: CanonicalAgentVisibleObservation,
        case: FrozenCaseState,
    ) -> None:
        if (
            action.decision_source != DecisionSource.LLM_AGENT
            or action.case_id != case.case_id
            or action.window_id != canonical.window.window_id
            or action.current_sequence_number != canonical.window.sequence_number
            or action.based_on_observation_id != canonical.observation_id
        ):
            raise ValueError("slow-path action does not match the visible transaction")

    def run_window(
        self,
        *,
        case: FrozenCaseState,
        window: TimeWindow,
        started_at: datetime,
        ended_at: datetime,
    ) -> FrozenWindowStepResult:
        self._validate_case_window(case, window)
        request = CommittedFastPathInferenceRequest(
            request_id=f"committed-request-{window.window_id}",
            case_id=case.case_id,
            scenario_id=case.scenario_id,
            episode_id=case.episode_id,
            split=case.split,
            window=window,
            committed_state=case.committed_state,
            requested_at=window.end,
        )
        bundle = self.committed_executor(request)
        self._validate_committed_bundle(request, bundle)

        # The current-window result becomes immutable before observation or diagnosis.
        self.committed_ledger.append(bundle.result)
        canonical = self.canonical_builder(bundle, case)
        self._validate_canonical(canonical, case, bundle)
        trigger = self.trigger_policy(canonical)
        if trigger.trigger_profile_id != self.config.trigger_profile_id:
            raise ValueError("trigger policy identity is not the frozen runtime profile")

        prompts: list[ModelPromptObservation] = []
        actions: list[FrozenActionDecision] = []
        additional_outcomes: list[HighLevelToolOutcome] = []
        additional_results: list[AdditionalDetectorResult] = []
        persistent_outcomes: list[HighLevelToolOutcome] = []
        memory_exchanges: list[FrozenMemoryExchange] = []
        pending_after = case.pending_state

        if not trigger.triggered:
            actions.append(self._default_keep(canonical))
        else:
            while True:
                prompt = self.prompt_builder(canonical, trigger, tuple(additional_results))
                if (
                    prompt.canonical_observation_id != canonical.observation_id
                    or prompt.canonical_observation_hash != canonical.content_hash
                    or not prompt.trigger.triggered
                ):
                    raise ValueError("prompt projection changed canonical/trigger identity")
                prompts.append(prompt)
                policy_output = self.policy(prompt, case)
                if isinstance(policy_output, MemoryDecisionEnvelope):
                    action = policy_output.action
                    memory_exchanges.append(policy_output.exchange)
                else:
                    if self.config.require_frozen_memory_protocol:
                        raise ValueError("slow path requires frozen two-turn memory protocol")
                    action = policy_output
                self._validate_agent_action(action, canonical, case)
                actions.append(action)
                if action.action_type in {
                    FrozenActionType.KEEP_CURRENT_CONFIG,
                    FrozenActionType.FINISH_DIAGNOSIS,
                }:
                    break
                if action.action_type == FrozenActionType.RUN_ADDITIONAL_DETECTOR and (
                    len(additional_results) >= self.config.max_additional_detector_cycles
                ):
                    raise ValueError("additional detector cycle budget exhausted")
                envelope = self.action_executor(action, case)
                outcome = envelope.outcome
                if (
                    outcome.action_id != action.action_id
                    or outcome.tool_name != action.requested_tool
                    or outcome.approved_choice_id != action.approved_choice_id
                ):
                    raise ValueError("executor outcome does not match approved action")
                if action.action_type == FrozenActionType.RUN_ADDITIONAL_DETECTOR:
                    if envelope.pending_state:
                        raise ValueError("additional detector cannot create pending state")
                    additional_outcomes.append(outcome)
                    if envelope.additional_result is None:
                        if outcome.status == RunStatus.SUCCEEDED:
                            raise ValueError("successful additional call requires evidence result")
                        break
                    result = envelope.additional_result
                    if (
                        result.result_id != outcome.result_id
                        or result.case_id != case.case_id
                        or result.window != window
                        or result.approved_candidate_id != action.approved_choice_id
                        or result.status != outcome.status
                    ):
                        raise ValueError("additional detector result identity/status mismatch")
                    additional_results.append(result)
                    if outcome.status != RunStatus.SUCCEEDED:
                        break
                    continue
                if envelope.additional_result:
                    raise ValueError("persistent/training tool cannot return detector evidence")
                persistent_outcomes.append(outcome)
                if outcome.status == RunStatus.SUCCEEDED and action.action_type in {
                    FrozenActionType.SELECT_VALIDATED_THRESHOLD,
                    FrozenActionType.LOAD_APPROVED_CONFIG,
                    FrozenActionType.SWITCH_DETECTOR,
                    FrozenActionType.SELECT_RESOURCE_PRESET,
                }:
                    pending = envelope.pending_state
                    if (
                        pending is None
                        or pending.pending_change_id != outcome.pending_change_id
                        or pending.requested_by_action_id != action.action_id
                        or pending.approved_choice_id != action.approved_choice_id
                        or pending.effective_sequence_number
                        != action.effective_sequence_number
                    ):
                        raise ValueError("persistent action did not produce exact pending state")
                    if case.pending_state and case.pending_state != pending:
                        raise ValueError("an existing pending transition cannot be overwritten")
                    pending_after = pending
                elif envelope.pending_state:
                    raise ValueError("failed or non-persistent tool cannot schedule activation")
                break

        next_case = case.model_copy(
            update={"pending_state": pending_after, "updated_at": ended_at}
        )
        next_case = FrozenCaseState.model_validate(next_case.model_dump())
        record = FrozenWindowTransactionRecord(
            transaction_id=f"transaction-{case.episode_id}-{window.window_id}",
            case_id=case.case_id,
            scenario_id=case.scenario_id,
            episode_id=case.episode_id,
            split=case.split,
            window_id=window.window_id,
            window_sequence_number=window.sequence_number,
            committed_fast_path_result=bundle.result,
            raw_execution_state=bundle.raw_state,
            canonical_observation=canonical,
            trigger=trigger,
            model_prompt_observations=tuple(prompts),
            memory_protocol_status=(
                "frozen-two-turn"
                if self.config.require_frozen_memory_protocol
                else "legacy-no-memory-protocol"
            ),
            memory_exchange_ids=tuple(exchange.exchange_id for exchange in memory_exchanges),
            action_decisions=tuple(actions),
            additional_detector_tool_calls=tuple(additional_outcomes),
            additional_detector_results=tuple(additional_results),
            persistent_tool_outcomes=tuple(persistent_outcomes),
            pending_state_before_window=case.pending_state,
            pending_state_after_window=pending_after,
            started_at=started_at,
            ended_at=ended_at,
        )
        for exchange in memory_exchanges:
            self.transaction_logger.append_memory_exchange(exchange)
        self.transaction_logger.append(record)
        return FrozenWindowStepResult(record=record, next_case=next_case)
