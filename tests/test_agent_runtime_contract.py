"""Frozen runtime contract and privileged-boundary tests.

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001..004,
REQ-WINDOW-001..004, REQ-CONFIG-001..003, REQ-TOOL-001..005.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from apt_detection_agent.schemas import (
    ActiveDetectionSummary,
    AdditionalDetectorRequest,
    AdditionalDetectorResult,
    AvailabilityStatus,
    CacheReuseClass,
    CanonicalAgentVisibleObservation,
    CapabilityOption,
    CommittedFastPathResult,
    DataSplit,
    DecisionSource,
    DetectionSignalSummary,
    DetectionUnit,
    EnvironmentSummary,
    ExecutionRole,
    ExecutionSummary,
    FrozenActionDecision,
    FrozenActionType,
    ModelPromptObservation,
    PIDSRef,
    RawExecutionState,
    RecomputationScope,
    RunStatus,
    RuntimeBudgetSummary,
    RuntimeMemorySummary,
    ScoreSummary,
    TimeWindow,
    ToolName,
    TriggerRecord,
)


ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)
NOW = ORIGIN + timedelta(minutes=30)


def content_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def window() -> TimeWindow:
    return TimeWindow(
        window_id="window-1",
        sequence_number=1,
        origin_time=ORIGIN,
        timezone="UTC",
        window_size_seconds=900,
        start=ORIGIN + timedelta(minutes=15),
        end=NOW,
    )


def empty_scores() -> ScoreSummary:
    return ScoreSummary(count=0)


def canonical_payload() -> dict[str, object]:
    return {
        "builder_version": "canonical-builder-v1",
        "observation_id": "observation-1",
        "case_id": "case-1",
        "scenario_id": "scenario-1",
        "episode_id": "episode-1",
        "split": DataSplit.HELD_OUT,
        "observed_at": NOW,
        "window": window(),
        "environment": EnvironmentSummary(
            environment_profile_id="autodl-initial",
            platform_class="linux-cdm",
            provenance_schema_id="cdm-v18",
            node_count=10,
            edge_count=20,
            entity_type_distribution={"process": 10},
            relation_type_distribution={"event": 20},
            event_rate=1.0,
            graph_density=0.2,
            normal_reference_status="frozen",
        ),
        "active_detection": ActiveDetectionSummary(
            detector=PIDSRef(pids_id="velox"),
            capability_type="event_surprise",
            committed_state_id="state-1",
            committed_config_id="config-1",
            checkpoint_id="checkpoint-1",
            threshold_id="threshold-1",
            resource_preset_id="resource-preset-1",
            score_semantics="higher-is-more-anomalous",
            detection_unit=DetectionUnit.NODE_TIME_WINDOW,
            state_health="healthy",
        ),
        "detection_signal": DetectionSignalSummary(
            score_summary=empty_scores(),
            tail_mass=0,
            alert_count=0,
            alert_ratio=0,
            alert_entity_ids=(),
            alert_score_bands={},
        ),
        "execution": ExecutionSummary(
            status=RunStatus.SUCCEEDED,
            elapsed_seconds=1,
            cpu_time_seconds=1,
            peak_memory_class="low",
            gpu_time_seconds=0,
            gpu_memory_pressure_class="none",
            timeout_indicator=False,
            oom_indicator=False,
            sanitized_failure_code=None,
            cache_reuse_class=CacheReuseClass.FULL,
            recomputation_scope=RecomputationScope.INFERENCE_ONLY,
            provenance_id="provenance-1",
        ),
        "capability_options": (
            CapabilityOption(
                detector=PIDSRef(pids_id="velox"),
                capability_type="event_surprise",
                available_status=AvailabilityStatus.AVAILABLE,
                availability_reason_code="admitted",
                cost_class="medium",
                limitation_codes=(),
                approved_candidate_ids=("candidate-1",),
            ),
        ),
        "budget": RuntimeBudgetSummary(
            remaining_slow_path_calls=1,
            remaining_retraining_calls=0,
            remaining_wall_time_class="bounded",
            token_usage_so_far=0,
        ),
        "memory": RuntimeMemorySummary(),
        "source_raw_state_id": "raw-state-1",
    }


def canonical_observation() -> CanonicalAgentVisibleObservation:
    payload = canonical_payload()
    serializable = CanonicalAgentVisibleObservation.model_construct(
        **payload, content_hash="0" * 64
    ).model_dump(mode="json", exclude={"content_hash"})
    payload["content_hash"] = content_hash(serializable)
    return CanonicalAgentVisibleObservation.model_validate(payload)


class ResultBoundaryTests(unittest.TestCase):
    def test_additional_request_has_no_executor_authority(self) -> None:
        request = AdditionalDetectorRequest(
            request_id="request-1",
            case_id="case-1",
            window_id="window-1",
            approved_candidate_id="candidate-1",
            investigation_reason_code="score-shift",
            visible_evidence_ids=("evidence-1",),
        )
        self.assertNotIn("execution_role", request.model_dump())
        with self.assertRaises(ValidationError):
            AdditionalDetectorRequest.model_validate(
                {**request.model_dump(), "cuda_device": 1}
            )

    def test_additional_result_is_non_replacing(self) -> None:
        result = AdditionalDetectorResult(
            investigation_id="investigation-1",
            result_id="additional-result-1",
            case_id="case-1",
            window=window(),
            approved_candidate_id="candidate-1",
            detector=PIDSRef(pids_id="velox"),
            config_id="config-1",
            checkpoint_id="checkpoint-1",
            threshold_id="threshold-1",
            status=RunStatus.SUCCEEDED,
            score_summary=empty_scores(),
            elapsed_seconds=1,
            resource_pressure_class="low",
            provenance_id="provenance-1",
        )
        self.assertFalse(result.committed)
        self.assertFalse(result.eligible_to_replace_committed_result)
        with self.assertRaises(ValidationError):
            AdditionalDetectorResult.model_validate(
                {**result.model_dump(), "committed": True}
            )

    def test_failed_outputs_are_typed_and_cannot_carry_scores(self) -> None:
        base = {
            "result_id": "committed-result-1",
            "case_id": "case-1",
            "scenario_id": "scenario-1",
            "episode_id": "episode-1",
            "split": DataSplit.HELD_OUT,
            "window": window(),
            "committed_state_id": "state-1",
            "detector": PIDSRef(pids_id="velox"),
            "config_id": "config-1",
            "checkpoint_id": "checkpoint-1",
            "threshold_id": "threshold-1",
            "resource_preset_id": "resource-preset-1",
            "status": RunStatus.FAILED,
            "score_summary": ScoreSummary(count=1, minimum=1, maximum=1, mean=1),
            "artifact_manifest_id": "manifest-1",
            "provenance_id": "provenance-1",
            "started_at": NOW,
            "ended_at": NOW + timedelta(seconds=1),
            "sanitized_failure_code": "parser-failed",
        }
        with self.assertRaises(ValidationError):
            CommittedFastPathResult.model_validate(base)


class ObservationLayerTests(unittest.TestCase):
    def test_raw_state_hash_is_immutable(self) -> None:
        payload: dict[str, object] = {
            "builder_version": "raw-builder-v1",
            "raw_state_id": "raw-state-1",
            "execution_role": ExecutionRole.COMMITTED_FAST_PATH,
            "case_id": "case-1",
            "window_id": "window-1",
            "result_id": "result-1",
            "command_manifest_id": "command-1",
            "artifact_ids": ("artifact-1",),
            "stage_status_ids": ("stage-1",),
            "resource_lease_id": "lease-1",
            "parser_id": "parser-1",
            "attempt_count": 1,
            "started_at": NOW,
            "ended_at": NOW + timedelta(seconds=1),
        }
        dumped = RawExecutionState.model_construct(
            **payload, content_hash="0" * 64
        ).model_dump(mode="json", exclude={"content_hash"})
        payload["content_hash"] = content_hash(dumped)
        state = RawExecutionState.model_validate(payload)
        with self.assertRaises(ValidationError):
            RawExecutionState.model_validate(
                {**state.model_dump(), "attempt_count": 2}
            )

    def test_canonical_observation_is_complete_hashed_and_label_free(self) -> None:
        observation = canonical_observation()
        self.assertEqual(observation.content_hash, observation.expected_content_hash())
        with self.assertRaises(ValidationError):
            CanonicalAgentVisibleObservation.model_validate(
                {**observation.model_dump(), "ground_truth": {"node": "bad"}}
            )
        with self.assertRaises(ValidationError):
            CanonicalAgentVisibleObservation.model_validate(
                {**observation.model_dump(), "content_hash": "f" * 64}
            )

    def test_prompt_exists_only_for_triggered_bounded_slow_path(self) -> None:
        observation = canonical_observation()
        base: dict[str, object] = {
            "builder_version": "prompt-builder-v1",
            "tokenizer_id": "tokenizer-1",
            "prompt_id": "prompt-1",
            "canonical_observation_id": observation.observation_id,
            "canonical_observation_hash": observation.content_hash,
            "trigger": TriggerRecord(
                trigger_profile_id="trigger-profile-1",
                triggered=True,
                reason_codes=("score-shift",),
                decided_at=NOW,
            ),
            "allowed_actions": (FrozenActionType.KEEP_CURRENT_CONFIG,),
            "visible_evidence_ids": ("evidence-1",),
            "token_budget": 100,
            "estimated_tokens": 20,
            "truncation_policy_id": "unresolved-requires-experiment",
            "truncation_status": "not-truncated",
            "rendered_text": "A deployment-visible score shift occurred.",
        }
        dumped = ModelPromptObservation.model_construct(
            **base, content_hash="0" * 64
        ).model_dump(mode="json", exclude={"content_hash"})
        base["content_hash"] = content_hash(dumped)
        prompt = ModelPromptObservation.model_validate(base)
        self.assertLessEqual(prompt.estimated_tokens, prompt.token_budget)
        untriggered = {
            **prompt.model_dump(),
            "trigger": {
                "trigger_profile_id": "trigger-profile-1",
                "triggered": False,
                "reason_codes": (),
                "decided_at": NOW,
            },
        }
        untriggered["content_hash"] = "0" * 64
        with self.assertRaises(ValidationError):
            ModelPromptObservation.model_validate(untriggered)


class FrozenActionTests(unittest.TestCase):
    def action(self, **updates: object) -> dict[str, object]:
        values: dict[str, object] = {
            "action_id": "action-1",
            "action_type": FrozenActionType.KEEP_CURRENT_CONFIG,
            "decision_source": DecisionSource.HARNESS_DEFAULT,
            "case_id": "case-1",
            "window_id": "window-1",
            "current_sequence_number": 1,
            "based_on_observation_id": "observation-1",
            "diagnosis_code": "no-trigger",
            "visible_evidence_ids": (),
            "requested_tool": None,
            "approved_choice_id": None,
            "expected_effect": "preserve-current-state",
            "recomputation_scope": RecomputationScope.NONE,
            "cache_reuse_class": CacheReuseClass.FULL,
            "effective_sequence_number": None,
            "confidence": 1,
            "commit_policy": "no-new-commit",
            "fallback_policy": FrozenActionType.KEEP_CURRENT_CONFIG,
        }
        values.update(updates)
        return values

    def test_action_taxonomy_is_exact_and_has_no_legacy_keep_and_infer(self) -> None:
        self.assertEqual(len(FrozenActionType), 8)
        self.assertNotIn("keep_and_infer", {item.value for item in FrozenActionType})

    def test_harness_default_can_only_keep(self) -> None:
        FrozenActionDecision.model_validate(self.action())
        with self.assertRaises(ValidationError):
            FrozenActionDecision.model_validate(
                self.action(action_type=FrozenActionType.FINISH_DIAGNOSIS)
            )

    def test_persistent_action_uses_exact_tool_and_future_window(self) -> None:
        decision = FrozenActionDecision.model_validate(
            self.action(
                action_type=FrozenActionType.SWITCH_DETECTOR,
                decision_source=DecisionSource.LLM_AGENT,
                requested_tool=ToolName.SWITCH_DETECTOR,
                approved_choice_id="candidate-2",
                effective_sequence_number=2,
            )
        )
        self.assertEqual(decision.requested_tool, ToolName.SWITCH_DETECTOR)
        with self.assertRaises(ValidationError):
            FrozenActionDecision.model_validate(
                self.action(
                    action_type=FrozenActionType.SWITCH_DETECTOR,
                    decision_source=DecisionSource.LLM_AGENT,
                    requested_tool=ToolName.LOAD_APPROVED_CONFIG,
                    approved_choice_id="candidate-2",
                    effective_sequence_number=1,
                )
            )


if __name__ == "__main__":
    unittest.main()
