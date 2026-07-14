"""Frozen transaction ordering, authorship, and activation tests.

Requirements: REQ-WINDOW-001..004, REQ-CONFIG-001..003,
REQ-TOOL-001..005, REQ-LABEL-001..004, REQ-REPRO-001..003.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from apt_detection_agent.controller import (
    ActionExecutionEnvelope,
    CommittedExecutionBundle,
    CommittedResultLedger,
    FrozenRuntimeConfig,
    FrozenRuntimeController,
    FrozenTransactionLogger,
    prepare_case_for_window,
)
from apt_detection_agent.schemas import (
    AdditionalDetectorResult,
    CacheReuseClass,
    CommittedDetectionState,
    CommittedFastPathResult,
    DataSplit,
    DecisionSource,
    FrozenActionDecision,
    FrozenActionType,
    FrozenCaseState,
    HighLevelToolOutcome,
    ModelPromptObservation,
    PendingDetectionState,
    PIDSRef,
    RawExecutionState,
    RecomputationScope,
    RunStatus,
    ScoreSummary,
    ToolName,
    TriggerRecord,
)
from tests.test_agent_runtime_contract import (
    NOW,
    canonical_observation,
    content_hash,
    window,
)


def committed_state() -> CommittedDetectionState:
    return CommittedDetectionState(
        state_id="state-1",
        detector=PIDSRef(pids_id="velox"),
        approved_candidate_id="candidate-1",
        config_id="config-1",
        checkpoint_id="checkpoint-1",
        threshold_id="threshold-1",
        resource_preset_id="resource-preset-1",
        state_token="state-token-1",
        state_health="healthy",
        effective_sequence_number=1,
    )


def case() -> FrozenCaseState:
    return FrozenCaseState(
        case_id="case-1",
        scenario_id="scenario-1",
        episode_id="episode-1",
        split=DataSplit.HELD_OUT,
        current_window_sequence=1,
        committed_state=committed_state(),
        memory_namespace="runtime:held-out:scenario-1:episode-1",
        updated_at=NOW,
    )


def committed_bundle(request: object) -> CommittedExecutionBundle:
    result = CommittedFastPathResult(
        result_id="committed-result-1",
        case_id="case-1",
        scenario_id="scenario-1",
        episode_id="episode-1",
        split=DataSplit.HELD_OUT,
        window=window(),
        committed_state_id="state-1",
        detector=PIDSRef(pids_id="velox"),
        config_id="config-1",
        checkpoint_id="checkpoint-1",
        threshold_id="threshold-1",
        resource_preset_id="resource-preset-1",
        status=RunStatus.SUCCEEDED,
        score_summary=ScoreSummary(count=0),
        artifact_manifest_id="artifact-manifest-1",
        provenance_id="provenance-1",
        started_at=NOW,
        ended_at=NOW,
    )
    raw_payload: dict[str, object] = {
        "builder_version": "raw-builder-v1",
        "raw_state_id": "raw-state-1",
        "execution_role": "committed_fast_path",
        "case_id": "case-1",
        "window_id": "window-1",
        "result_id": result.result_id,
        "command_manifest_id": "command-1",
        "artifact_ids": ("artifact-1",),
        "stage_status_ids": ("stage-1",),
        "resource_lease_id": "lease-1",
        "parser_id": "parser-1",
        "attempt_count": 1,
        "started_at": NOW,
        "ended_at": NOW,
    }
    dumped = RawExecutionState.model_construct(
        **raw_payload, content_hash="0" * 64
    ).model_dump(mode="json", exclude={"content_hash"})
    raw_payload["content_hash"] = content_hash(dumped)
    return CommittedExecutionBundle(
        result=result,
        raw_state=RawExecutionState.model_validate(raw_payload),
    )


def trigger(triggered: bool) -> TriggerRecord:
    return TriggerRecord(
        trigger_profile_id="validated-trigger-v1",
        triggered=triggered,
        reason_codes=("score-shift",) if triggered else (),
        decided_at=NOW,
    )


def prompt(observation: object, decision: TriggerRecord, results: tuple[object, ...]) -> ModelPromptObservation:
    payload: dict[str, object] = {
        "builder_version": "prompt-builder-v1",
        "tokenizer_id": "tokenizer-1",
        "prompt_id": f"prompt-{len(results)}",
        "canonical_observation_id": observation.observation_id,
        "canonical_observation_hash": observation.content_hash,
        "trigger": decision,
        "allowed_actions": tuple(FrozenActionType),
        "visible_evidence_ids": ("evidence-1",),
        "additional_result_ids": tuple(item.result_id for item in results),
        "token_budget": 100,
        "estimated_tokens": 20,
        "truncation_policy_id": "unresolved-requires-experiment",
        "truncation_status": "not-truncated",
        "rendered_text": "A deployment-visible trigger opened bounded diagnosis.",
    }
    dumped = ModelPromptObservation.model_construct(
        **payload, content_hash="0" * 64
    ).model_dump(mode="json", exclude={"content_hash"})
    payload["content_hash"] = content_hash(dumped)
    return ModelPromptObservation.model_validate(payload)


def action(action_type: FrozenActionType, *, action_id: str = "action-1") -> FrozenActionDecision:
    tool = {
        FrozenActionType.RUN_ADDITIONAL_DETECTOR: ToolName.RUN_ADDITIONAL_DETECTOR,
        FrozenActionType.SWITCH_DETECTOR: ToolName.SWITCH_DETECTOR,
    }.get(action_type)
    persistent = action_type == FrozenActionType.SWITCH_DETECTOR
    return FrozenActionDecision(
        action_id=action_id,
        action_type=action_type,
        decision_source=DecisionSource.LLM_AGENT,
        case_id="case-1",
        window_id="window-1",
        current_sequence_number=1,
        based_on_observation_id="observation-1",
        diagnosis_code="visible-symptom",
        visible_evidence_ids=("evidence-1",),
        requested_tool=tool,
        approved_choice_id="candidate-2" if tool else None,
        expected_effect="different-deployment-visible-signal",
        recomputation_scope=(
            RecomputationScope.CONFIGURATION_DEPENDENT
            if persistent
            else RecomputationScope.INFERENCE_ONLY if tool else RecomputationScope.NONE
        ),
        cache_reuse_class=CacheReuseClass.NONE if tool else CacheReuseClass.FULL,
        effective_sequence_number=2 if persistent else None,
        confidence=0.8,
        commit_policy="no-current-window-rewrite",
        fallback_policy=FrozenActionType.KEEP_CURRENT_CONFIG,
    )


class FrozenRuntimeTests(unittest.TestCase):
    def controller(
        self,
        root: Path,
        *,
        triggered: bool,
        policy,
        executor,
        prompt_builder=prompt,
    ) -> FrozenRuntimeController:
        return FrozenRuntimeController(
            config=FrozenRuntimeConfig(
                trigger_profile_id="validated-trigger-v1",
                trigger_source_split=DataSplit.VALIDATION,
                max_additional_detector_cycles=1,
            ),
            committed_executor=committed_bundle,
            canonical_builder=lambda bundle, state: canonical_observation(),
            trigger_policy=lambda observation: trigger(triggered),
            prompt_builder=prompt_builder,
            policy=policy,
            action_executor=executor,
            committed_ledger=CommittedResultLedger(root / "committed.jsonl"),
            transaction_logger=FrozenTransactionLogger(root / "transactions.jsonl"),
        )

    def test_untriggered_window_has_no_prompt_policy_memory_or_tool_turn(self) -> None:
        calls = {"prompt": 0, "policy": 0, "tool": 0}

        def forbidden_prompt(*args: object) -> ModelPromptObservation:
            calls["prompt"] += 1
            raise AssertionError("untriggered window created a prompt")

        def forbidden_policy(*args: object) -> FrozenActionDecision:
            calls["policy"] += 1
            raise AssertionError("untriggered window called the policy")

        def forbidden_tool(*args: object) -> ActionExecutionEnvelope:
            calls["tool"] += 1
            raise AssertionError("untriggered window called a tool")

        with tempfile.TemporaryDirectory() as temp:
            result = self.controller(
                Path(temp),
                triggered=False,
                policy=forbidden_policy,
                executor=forbidden_tool,
                prompt_builder=forbidden_prompt,
            ).run_window(
                case=case(),
                window=window(),
                started_at=NOW,
                ended_at=NOW + timedelta(seconds=2),
            )
        self.assertEqual(calls, {"prompt": 0, "policy": 0, "tool": 0})
        self.assertEqual(result.record.model_prompt_observations, ())
        self.assertEqual(
            result.record.action_decisions[0].decision_source,
            DecisionSource.HARNESS_DEFAULT,
        )

    def test_committed_result_is_exactly_once_even_if_transaction_retried(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = self.controller(
                Path(temp),
                triggered=False,
                policy=lambda *args: action(FrozenActionType.KEEP_CURRENT_CONFIG),
                executor=lambda *args: None,
            )
            controller.run_window(
                case=case(), window=window(), started_at=NOW, ended_at=NOW
            )
            with self.assertRaisesRegex(ValueError, "exactly one committed result"):
                controller.run_window(
                    case=case(), window=window(), started_at=NOW, ended_at=NOW
                )

    def test_persistent_switch_is_pending_then_activates_next_window(self) -> None:
        switch = action(FrozenActionType.SWITCH_DETECTOR)
        pending = PendingDetectionState(
            pending_change_id="pending-1",
            action_type=FrozenActionType.SWITCH_DETECTOR,
            approved_choice_id="candidate-2",
            requested_by_action_id=switch.action_id,
            effective_sequence_number=2,
            target_detector=PIDSRef(pids_id="orthrus", variant_id="fixed"),
            target_config_id="config-2",
            target_checkpoint_id="checkpoint-2",
            target_threshold_id="threshold-2",
            target_resource_preset_id="resource-preset-2",
            state_initialization_policy_id="reset-v1",
            target_state_token="state-token-2",
            target_state_health="initialized",
            rollback_state_id="state-1",
        )
        outcome = HighLevelToolOutcome(
            outcome_id="outcome-1",
            action_id=switch.action_id,
            tool_name=ToolName.SWITCH_DETECTOR,
            status=RunStatus.SUCCEEDED,
            approved_choice_id="candidate-2",
            pending_change_id=pending.pending_change_id,
            provenance_id="provenance-2",
        )
        with tempfile.TemporaryDirectory() as temp:
            result = self.controller(
                Path(temp),
                triggered=True,
                policy=lambda *args: switch,
                executor=lambda *args: ActionExecutionEnvelope(
                    outcome=outcome, pending_state=pending
                ),
            ).run_window(
                case=case(), window=window(), started_at=NOW, ended_at=NOW
            )
        self.assertEqual(result.next_case.committed_state, committed_state())
        self.assertEqual(result.next_case.pending_state, pending)
        activated = prepare_case_for_window(
            result.next_case,
            sequence_number=2,
            activated_at=NOW + timedelta(minutes=15),
        )
        self.assertEqual(activated.committed_state.detector.pids_id, "orthrus")
        self.assertIsNone(activated.pending_state)

    def test_additional_result_is_separate_then_reprompts(self) -> None:
        decisions = [
            action(FrozenActionType.RUN_ADDITIONAL_DETECTOR, action_id="action-additional"),
            action(FrozenActionType.FINISH_DIAGNOSIS, action_id="action-finish"),
        ]
        additional = AdditionalDetectorResult(
            investigation_id="investigation-1",
            result_id="additional-result-1",
            case_id="case-1",
            window=window(),
            approved_candidate_id="candidate-2",
            detector=PIDSRef(pids_id="orthrus", variant_id="fixed"),
            config_id="config-2",
            checkpoint_id="checkpoint-2",
            threshold_id="threshold-2",
            status=RunStatus.SUCCEEDED,
            score_summary=ScoreSummary(count=0),
            elapsed_seconds=2,
            resource_pressure_class="medium",
            provenance_id="provenance-2",
        )
        outcome = HighLevelToolOutcome(
            outcome_id="outcome-additional",
            action_id="action-additional",
            tool_name=ToolName.RUN_ADDITIONAL_DETECTOR,
            status=RunStatus.SUCCEEDED,
            approved_choice_id="candidate-2",
            result_id=additional.result_id,
            provenance_id="provenance-2",
        )
        with tempfile.TemporaryDirectory() as temp:
            result = self.controller(
                Path(temp),
                triggered=True,
                policy=lambda *args: decisions.pop(0),
                executor=lambda *args: ActionExecutionEnvelope(
                    outcome=outcome, additional_result=additional
                ),
            ).run_window(
                case=case(), window=window(), started_at=NOW, ended_at=NOW
            )
        self.assertEqual(len(result.record.model_prompt_observations), 2)
        self.assertEqual(len(result.record.additional_detector_results), 1)
        self.assertEqual(
            result.record.committed_fast_path_result.result_id,
            "committed-result-1",
        )
        self.assertFalse(result.record.additional_detector_results[0].committed)


if __name__ == "__main__":
    unittest.main()
