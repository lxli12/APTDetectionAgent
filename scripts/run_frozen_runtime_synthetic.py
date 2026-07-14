#!/usr/bin/env python3
"""Run a two-window frozen-runtime protocol smoke without formal claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apt_detection_agent.controller import (
    CanonicalObservationInputs,
    CommittedExecutionBundle,
    CommittedResultLedger,
    DeterministicCanonicalObservationBuilder,
    DeterministicPromptBuilder,
    DeterministicTriggerPolicy,
    FrozenMemoryProtocol,
    FrozenRuntimeConfig,
    FrozenRuntimeController,
    FrozenTransactionLogger,
    FrozenTriggerProfile,
    PromptBuilderConfig,
    prepare_case_for_window,
)
from apt_detection_agent.schemas import (
    AvailabilityStatus,
    CacheReuseClass,
    CapabilityOption,
    CommittedDetectionState,
    CommittedFastPathResult,
    DataSplit,
    DetectionAlert,
    DetectionSignalSummary,
    DetectionUnit,
    EnvironmentSummary,
    ExecutionRole,
    ExecutionSummary,
    FrozenActionType,
    FrozenCaseState,
    MemoryActionResponse,
    MemoryReadRequest,
    MemoryRetrievalResult,
    PIDSRef,
    ProposedAction,
    RawExecutionState,
    RecomputationScope,
    RunStatus,
    RuntimeBudgetSummary,
    RuntimeMemorySummary,
    ScoreSummary,
    TimeWindow,
)
from apt_detection_agent.schemas.common import assert_deployable_payload


ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _window(sequence: int) -> TimeWindow:
    start = ORIGIN + timedelta(minutes=15 * sequence)
    return TimeWindow(
        window_id=f"synthetic-window-{sequence}",
        sequence_number=sequence,
        origin_time=ORIGIN,
        timezone="UTC",
        window_size_seconds=900,
        start=start,
        end=start + timedelta(minutes=15),
    )


def _raw_hash(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _committed_executor(request) -> CommittedExecutionBundle:
    sequence = request.window.sequence_number
    alerted = sequence == 1
    scores = (
        ScoreSummary(count=1, minimum=0.9, maximum=0.9, mean=0.9)
        if alerted
        else ScoreSummary(count=0)
    )
    alerts = (
        DetectionAlert(
            alert_id="synthetic-alert-1",
            entity_id="synthetic-entity-1",
            detection_unit=DetectionUnit.NODE_TIME_WINDOW,
            score=0.9,
            threshold_id=request.committed_state.threshold_id,
            evidence_artifact_ids=("synthetic-visible-evidence-1",),
        ),
    ) if alerted else ()
    result = CommittedFastPathResult(
        result_id=f"synthetic-committed-result-{sequence}",
        case_id=request.case_id,
        scenario_id=request.scenario_id,
        episode_id=request.episode_id,
        split=request.split,
        window=request.window,
        committed_state_id=request.committed_state.state_id,
        detector=request.committed_state.detector,
        config_id=request.committed_state.config_id,
        checkpoint_id=request.committed_state.checkpoint_id,
        threshold_id=request.committed_state.threshold_id,
        resource_preset_id=request.committed_state.resource_preset_id,
        status=RunStatus.SUCCEEDED,
        score_summary=scores,
        alerts=alerts,
        artifact_manifest_id=f"synthetic-artifact-manifest-{sequence}",
        provenance_id=f"synthetic-provenance-{sequence}",
        started_at=request.window.end,
        ended_at=request.window.end,
    )
    raw_payload: dict[str, object] = {
        "builder_version": "synthetic-raw-builder-v1",
        "raw_state_id": f"synthetic-raw-state-{sequence}",
        "execution_role": ExecutionRole.COMMITTED_FAST_PATH,
        "case_id": request.case_id,
        "window_id": request.window.window_id,
        "result_id": result.result_id,
        "command_manifest_id": f"synthetic-command-{sequence}",
        "artifact_ids": (f"synthetic-artifact-{sequence}",),
        "stage_status_ids": (f"synthetic-stage-{sequence}",),
        "resource_lease_id": f"synthetic-lease-{sequence}",
        "parser_id": "synthetic-parser-v1",
        "attempt_count": 1,
        "started_at": request.window.end,
        "ended_at": request.window.end,
    }
    provisional = RawExecutionState.model_construct(
        **raw_payload, content_hash="0" * 64
    ).model_dump(mode="json", exclude={"content_hash"})
    raw_payload["content_hash"] = _raw_hash(provisional)
    return CommittedExecutionBundle(
        result=result,
        raw_state=RawExecutionState.model_validate(raw_payload),
    )


def _canonical_inputs(bundle, case) -> CanonicalObservationInputs:
    alerts = bundle.result.alerts
    return CanonicalObservationInputs(
        builder_version="synthetic-canonical-builder-v1",
        observation_id=f"synthetic-observation-{bundle.result.window.sequence_number}",
        observed_at=bundle.result.ended_at,
        environment=EnvironmentSummary(
            environment_profile_id="synthetic-autodl-quota-profile",
            platform_class="synthetic-linux-provenance",
            provenance_schema_id="synthetic-schema-v1",
            node_count=1,
            edge_count=1,
            entity_type_distribution={"process": 1},
            relation_type_distribution={"event": 1},
            event_rate=1,
            graph_density=1,
            normal_reference_status="synthetic-frozen",
        ),
        detection_signal=DetectionSignalSummary(
            score_summary=bundle.result.score_summary,
            tail_mass=1 if alerts else 0,
            alert_count=len(alerts),
            alert_ratio=1 if alerts else 0,
            alert_entity_ids=tuple(item.entity_id for item in alerts),
            alert_score_bands={"high": len(alerts)} if alerts else {},
        ),
        execution=ExecutionSummary(
            status=RunStatus.SUCCEEDED,
            elapsed_seconds=0,
            cpu_time_seconds=0,
            peak_memory_class="synthetic-low",
            gpu_time_seconds=0,
            gpu_memory_pressure_class="synthetic-none",
            timeout_indicator=False,
            oom_indicator=False,
            sanitized_failure_code=None,
            cache_reuse_class=CacheReuseClass.FULL,
            recomputation_scope=RecomputationScope.INFERENCE_ONLY,
            provenance_id=bundle.result.provenance_id,
        ),
        capability_options=(
            CapabilityOption(
                detector=PIDSRef(pids_id="velox"),
                capability_type="event-surprise",
                available_status=AvailabilityStatus.UNVERIFIED,
                availability_reason_code="synthetic-protocol-only",
                cost_class="unprofiled",
                limitation_codes=("not-admitted-eight-gate",),
                approved_candidate_ids=(),
            ),
        ),
        budget=RuntimeBudgetSummary(
            remaining_slow_path_calls=1,
            remaining_retraining_calls=0,
            remaining_wall_time_class="synthetic-bounded",
            token_usage_so_far=0,
        ),
        memory=RuntimeMemorySummary(),
        capability_type="event-surprise",
        score_semantics="higher-is-more-anomalous",
        detection_unit=DetectionUnit.NODE_TIME_WINDOW,
    )


def _memory_protocol() -> FrozenMemoryProtocol:
    def read(prompt, case):
        return MemoryReadRequest(
            request_id=f"synthetic-memory-read-{prompt.prompt_id}",
            prompt_id=prompt.prompt_id,
            case_id=case.case_id,
            needed=False,
            reason_code="synthetic-no-memory-needed",
            visible_evidence_ids=(prompt.canonical_observation_id,),
        )

    def retrieve(request, case):
        return MemoryRetrievalResult(
            result_id=f"synthetic-memory-result-{request.prompt_id}",
            request_id=request.request_id,
            needed=False,
            status=RunStatus.SUCCEEDED,
            candidate_count=0,
            estimated_tokens=0,
            truncated=False,
            policy_validation_status="unvalidated-engineering-default",
        )

    def decide(prompt, result, case):
        action = ProposedAction(
            proposal_id=f"synthetic-finish-{prompt.prompt_id}",
            action_type=FrozenActionType.FINISH_DIAGNOSIS,
            based_on_observation_id=prompt.canonical_observation_id,
            diagnosis_code="synthetic-visible-alert-volume",
            visible_evidence_ids=prompt.visible_evidence_ids,
            expected_effect="preserve-current-admitted-state",
            confidence=0.5,
            fallback_policy=FrozenActionType.KEEP_CURRENT_CONFIG,
        )
        return MemoryActionResponse(
            response_id=f"synthetic-memory-response-{prompt.prompt_id}",
            prompt_id=prompt.prompt_id,
            retrieval_result_id=result.result_id,
            use_decisions=(),
            diagnosis_code="synthetic-visible-alert-volume",
            action=action,
        )

    return FrozenMemoryProtocol(read_policy=read, retrieval_tool=retrieve, action_policy=decide)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args()
    run_dir = (args.run_root.resolve() / args.run_id).resolve()
    if run_dir.parent != args.run_root.resolve() or run_dir.exists():
        raise FileExistsError("synthetic run directory must be new and contained")
    run_dir.mkdir(parents=True)
    (run_dir / "command.txt").write_text(" ".join(sys.argv) + "\n")
    (run_dir / "git_commit.txt").write_text(args.code_commit + "\n")
    (run_dir / "environment.json").write_text(
        json.dumps(
            {"python": sys.version, "platform": platform.platform(), "synthetic_only": True},
            sort_keys=True,
            indent=2,
        ) + "\n"
    )
    (run_dir / "resolved_config.yaml").write_text(
        "schema_version: synthetic-frozen-runtime-v1\n"
        "formal_performance_claim: false\n"
        "trigger_source_split: validation\n"
        "memory_policy_status: unvalidated_engineering_default\n"
    )
    state = CommittedDetectionState(
        state_id="synthetic-state-0",
        detector=PIDSRef(pids_id="velox"),
        approved_candidate_id="synthetic-nonadmitted-candidate",
        config_id="synthetic-config-0",
        checkpoint_id="synthetic-checkpoint-0",
        threshold_id="synthetic-threshold-0",
        resource_preset_id="synthetic-resource-0",
        state_token="synthetic-state-token-0",
        state_health="synthetic-healthy",
        effective_sequence_number=0,
    )
    case = FrozenCaseState(
        case_id="synthetic-case",
        scenario_id="synthetic-scenario",
        episode_id="synthetic-episode",
        split=DataSplit.AGENT_TRAINING,
        current_window_sequence=0,
        committed_state=state,
        memory_namespace="runtime:agent-training:synthetic-scenario:synthetic-episode",
        updated_at=ORIGIN,
    )
    controller = FrozenRuntimeController(
        config=FrozenRuntimeConfig(
            trigger_profile_id="synthetic-validation-trigger-v1",
            trigger_source_split=DataSplit.VALIDATION,
            max_additional_detector_cycles=1,
            require_frozen_memory_protocol=True,
        ),
        committed_executor=_committed_executor,
        canonical_builder=DeterministicCanonicalObservationBuilder(_canonical_inputs),
        trigger_policy=DeterministicTriggerPolicy(
            FrozenTriggerProfile(
                profile_id="synthetic-validation-trigger-v1",
                source_split=DataSplit.VALIDATION,
                alert_count_threshold=1,
                alert_count_calibration_artifact_id="synthetic-trigger-fixture-only",
            ),
            clock=lambda: ORIGIN + timedelta(minutes=30),
        ),
        prompt_builder=DeterministicPromptBuilder(
            PromptBuilderConfig(
                builder_version="synthetic-prompt-builder-v1",
                tokenizer_id="synthetic-byte-estimator-v1",
                token_budget=20000,
            ),
            token_counter=lambda text: (len(text.encode()) + 3) // 4,
        ),
        policy=_memory_protocol(),
        action_executor=lambda action, case: (_ for _ in ()).throw(
            AssertionError("synthetic terminal action must not call runtime tool")
        ),
        committed_ledger=CommittedResultLedger(run_dir / "committed_results.jsonl"),
        transaction_logger=FrozenTransactionLogger(run_dir / "trajectory.jsonl"),
    )
    first = controller.run_window(
        case=case,
        window=_window(0),
        started_at=_window(0).end,
        ended_at=_window(0).end,
    )
    case = prepare_case_for_window(
        first.next_case, sequence_number=1, activated_at=_window(1).start
    )
    second = controller.run_window(
        case=case,
        window=_window(1),
        started_at=_window(1).end,
        ended_at=ORIGIN + timedelta(minutes=30),
    )
    summary = {
        "schema_version": "synthetic-frozen-runtime-summary-v1",
        "formal_performance_claim": False,
        "committed_result_count": len(
            (run_dir / "committed_results.jsonl").read_text().splitlines()
        ),
        "first_window_prompt_count": len(first.record.model_prompt_observations),
        "second_window_prompt_count": len(second.record.model_prompt_observations),
        "second_window_memory_exchange_count": len(second.record.memory_exchange_ids),
        "pids_admitted_for_formal_trajectory": False,
        "checks": {
            "untriggered_has_no_assistant_turn": not first.record.model_prompt_observations,
            "triggered_has_frozen_memory_exchange": len(second.record.memory_exchange_ids) == 1,
            "exactly_one_commit_per_window": len(
                (run_dir / "committed_results.jsonl").read_text().splitlines()
            ) == 2,
        },
    }
    assert_deployable_payload(summary, "synthetic_frozen_runtime_summary")
    if not all(summary["checks"].values()):
        raise RuntimeError("synthetic frozen runtime checks failed")
    (run_dir / "metrics.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    (run_dir / "run_status.json").write_text(
        json.dumps({"status": "succeeded", **summary}, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
