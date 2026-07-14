#!/usr/bin/env python3
"""Build a non-formal demonstration corpus from a frozen-runtime smoke trace."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

from apt_detection_agent.pidsmaker import PIDSMakerDiscovery
from apt_detection_agent.schemas import (
    AvailabilityStatus,
    DataSplit,
    FrozenMemoryExchange,
    FrozenWindowTransactionRecord,
    MemoryActionResponse,
    MemoryReadRequest,
    MemoryRetrievalResult,
    ModelPromptObservation,
    ProposedAction,
    RunStatus,
)
from apt_detection_agent.sft import (
    CoverageClass,
    DemonstrationCorpusValidator,
    DemonstrationExchange,
    DemonstrationExporter,
    DemonstrationSanitizer,
    ExecutionDisposition,
    build_coverage_report,
    build_dataset_manifest,
    build_execution_matrix,
    build_offline_run_record,
    build_trajectory,
    corpus_digest,
)
from apt_detection_agent.sft.models import (
    DemonstrationTrainingUse,
    GraphConstructionManifest,
    HistoricalEvidenceContext,
    LabelAvailability,
    ObservableBehavior,
    OpaqueConfigurationSummary,
    PIDSDataPartitions,
    TemporalContext,
    VisibleCostSummary,
    VisibleEvidenceGrounding,
    VisibleFailureCondition,
)
from apt_detection_agent.sft.models import DetectorCapabilitySnapshot


def _jsonl(values) -> str:
    return "".join(item.model_dump_json() + "\n" for item in values)


def _capability_view(capability) -> DetectorCapabilitySnapshot:
    return DetectorCapabilitySnapshot(
        pids=capability.pids,
        purpose="Inspect deployment-visible provenance anomaly behavior.",
        capability_type=f"registered-{capability.pids.pids_id}-capability",
        detection_unit=capability.detection_unit,
        cost_class="unprofiled",
        required_state_status="unverified-frozen-state",
        limitation_codes=("syntactic-support-unverified",),
        available_status=AvailabilityStatus.BLOCKED,
        availability_reason_codes=(
            "checkpoint-unavailable"
            if capability.current_availability_status == AvailabilityStatus.UNAVAILABLE
            else "not-admitted-eight-gate",
        ),
        approved_candidate_ids=(),
    )


def _capability_prompt(source: FrozenMemoryExchange, views) -> FrozenMemoryExchange:
    rendered = json.dumps(
        {
            "canonical_observation": {
                "observation_id": source.prompt.canonical_observation_id,
                "capability_options": [item.model_dump(mode="json") for item in views],
            },
            "synthetic_contract_only": True,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    prompt_values = {
        name: getattr(source.prompt, name)
        for name in type(source.prompt).model_fields
        if name != "content_hash"
    }
    prompt_values.update(
        {
            "builder_version": "synthetic-demonstration-builder-v1",
            "prompt_id": "synthetic-capability-prompt",
            "rendered_text": rendered,
            "estimated_tokens": (len(rendered.encode()) + 3) // 4,
        }
    )
    provisional = ModelPromptObservation.model_construct(
        **prompt_values, content_hash="0" * 64
    )
    prompt = ModelPromptObservation(
        **prompt_values, content_hash=provisional.expected_content_hash()
    )
    read = MemoryReadRequest(
        request_id="synthetic-capability-memory-read",
        prompt_id=prompt.prompt_id,
        case_id=source.read_request.case_id,
        needed=False,
        reason_code="synthetic-capability-awareness-no-memory",
        visible_evidence_ids=(prompt.canonical_observation_id,),
    )
    result = MemoryRetrievalResult(
        result_id="synthetic-capability-memory-result",
        request_id=read.request_id,
        needed=False,
        status=RunStatus.SUCCEEDED,
        candidate_count=0,
        estimated_tokens=0,
        truncated=False,
        policy_validation_status="unvalidated-engineering-default",
    )
    response = MemoryActionResponse(
        response_id="synthetic-capability-response",
        prompt_id=prompt.prompt_id,
        retrieval_result_id=result.result_id,
        use_decisions=(),
        diagnosis_code="registered-capabilities-unadmitted",
        action=ProposedAction.model_validate(
            {
                **source.response.action.model_dump(),
                "proposal_id": "synthetic-capability-finish",
                "based_on_observation_id": prompt.canonical_observation_id,
                "visible_evidence_ids": (prompt.canonical_observation_id,),
                "diagnosis_code": "registered-capabilities-unadmitted",
            }
        ),
    )
    return FrozenMemoryExchange(
        exchange_id="synthetic-capability-exchange",
        prompt=prompt,
        read_request=read,
        retrieval_result=result,
        response=response,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--source-runtime-run", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args()
    root = args.run_root.resolve()
    run_dir = (root / args.run_id).resolve()
    if run_dir.parent != root or run_dir.exists():
        raise FileExistsError("demonstration run directory must be new and contained")
    source = args.source_runtime_run.resolve()
    if not source.is_dir():
        raise ValueError("source frozen-runtime run is missing")
    run_dir.mkdir(parents=True)
    (run_dir / "command.txt").write_text(" ".join(sys.argv) + "\n")
    (run_dir / "git_commit.txt").write_text(args.code_commit + "\n")
    (run_dir / "environment.json").write_text(
        json.dumps(
            {"python": sys.version, "platform": platform.platform(), "synthetic_only": True},
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (run_dir / "resolved_config.yaml").write_text(
        "schema_version: synthetic-demonstration-build-v1\n"
        "formal_training_approved: false\n"
        "execution_disposition: capability_only\n"
        "successful_tool_use_count: 0\n"
    )

    exchanges = tuple(
        FrozenMemoryExchange.model_validate_json(line)
        for line in (source / "memory_exchanges.jsonl").read_text().splitlines()
        if line.strip()
    )
    if len(exchanges) != 1:
        raise ValueError("synthetic source must contain exactly one frozen memory exchange")
    transactions = tuple(
        FrozenWindowTransactionRecord.model_validate_json(line)
        for line in (source / "trajectory.jsonl").read_text().splitlines()
        if line.strip()
    )
    triggered_transaction = next(item for item in transactions if item.trigger.triggered)
    capabilities = PIDSMakerDiscovery(args.project_root).capabilities()
    views = tuple(_capability_view(item) for item in capabilities)
    refs = tuple(item.pids for item in capabilities)
    if len({(item.pids_id, item.variant_id) for item in refs}) != len(refs):
        raise ValueError("dynamic capability identities must be unique")
    exchange = _capability_prompt(exchanges[0], views)
    source_hashes = tuple(
        hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (source / "committed_results.jsonl", source / "trajectory.jsonl")
    )
    created_at = datetime.now(timezone.utc)
    manifest = build_dataset_manifest(
        dataset_manifest_id="synthetic-demonstration-manifest",
        dataset_id="synthetic-contract-dataset",
        source_family="synthetic-frozen-runtime",
        source_release="contract-smoke-v1",
        source_format="frozen-runtime-jsonl",
        source_content_hashes=source_hashes,
        access_and_license_status="synthetic-local-only",
        normalized_storage_schema_id="synthetic-runtime-schema-v1",
        provenance_schema_id="synthetic-provenance-v1",
        platform_class="synthetic-linux-provenance",
        graph_construction=GraphConstructionManifest(
            builder_id="synthetic-fixed-window-v1",
            origin=datetime(2026, 1, 1, tzinfo=timezone.utc),
            timezone="UTC",
            window_size_seconds=900,
            half_open_alignment=True,
            entity_types=("process",),
            relation_types=("event",),
            transformation_policy_ids=("synthetic-causal-only",),
        ),
        pids_data_partitions=PIDSDataPartitions(
            train_partition_ref="synthetic-not-used",
            validation_partition_ref="synthetic-not-used",
            demonstration_partition_ref="synthetic-agent-training",
        ),
        registered_pids=refs,
        pids_admission_ids=(),
        label_availability=LabelAvailability.NONE,
        training_use=DemonstrationTrainingUse(
            pids_fit_allowed=False,
            threshold_calibration_allowed=False,
            sft_demonstration_allowed=True,
        ),
        private_companion_manifest_id="synthetic-private-companion-none",
        code_commit=args.code_commit,
        builder_version="synthetic-demonstration-builder-v1",
        created_at=created_at,
    )
    behavior = ObservableBehavior(
        behavior_id="synthetic-visible-alert-behavior",
        summary="The current closed window contains a deployment-visible alert.",
        evidence_ids=(exchange.prompt.canonical_observation_id,),
        unknown_codes=("real-detector-effect-unknown",),
    )
    temporal = TemporalContext(
        window_id=triggered_transaction.window_id,
        sequence_number=triggered_transaction.window_sequence_number,
        start=triggered_transaction.canonical_observation.window.start,
        end=triggered_transaction.canonical_observation.window.end,
        past_range_window_ids=("synthetic-window-0",),
        state_continuity_code="synthetic-continuous",
    )
    offline_records = tuple(
        build_offline_run_record(
            run_record_id=f"synthetic-offline-{capability.source_config_id}",
            dataset_manifest_id=manifest.dataset_manifest_id,
            episode_id="synthetic-episode",
            split=DataSplit.AGENT_TRAINING,
            environment_profile_id="synthetic-autodl-quota-profile",
            observable_behavior=behavior,
            historical_evidence_context=HistoricalEvidenceContext(
                past_window_ids=("synthetic-window-0",),
                prior_result_ids=("synthetic-committed-result-0",),
                prior_action_ids=(),
                prior_failure_codes=(),
                prior_state_change_ids=(),
                memory_record_ids=(),
            ),
            temporal_context=temporal,
            pids_capability=view,
            detector=capability.pids,
            configuration=OpaqueConfigurationSummary(
                approved_config_id=f"synthetic-unavailable-{capability.source_config_id}",
                checkpoint_id=f"synthetic-unavailable-checkpoint-{capability.source_config_id}",
                threshold_id=f"synthetic-unavailable-threshold-{capability.source_config_id}",
                resource_preset_id="synthetic-unprofiled-resource",
            ),
            admitted_use="capability-awareness-only",
            execution_disposition=ExecutionDisposition.CAPABILITY_ONLY,
            standardized_result_id=None,
            deployment_visible_outcome_code="not-executed-no-admission",
            cost=VisibleCostSummary(
                wall_time_seconds=0,
                cpu_time_seconds=0,
                gpu_time_seconds=0,
                memory_pressure_class="none",
                gpu_pressure_class="none",
                cache_reuse_class="none",
                tool_call_count=0,
                llm_call_count=0,
                token_count=0,
            ),
            failure_condition=VisibleFailureCondition(
                failure_code="not-admitted-eight-gate",
                applicability_codes=("synthetic-contract-smoke",),
                avoid_condition_codes=("do-not-claim-detector-success",),
            ),
            execution_role="capability-candidate",
            public_runtime_trace_id="synthetic-frozen-runtime-source",
            admission_id=None,
            provenance_id=f"synthetic-provenance-{capability.source_config_id}",
        )
        for capability, view in zip(capabilities, views, strict=True)
    )
    matrix = build_execution_matrix(
        dataset_manifest_id=manifest.dataset_manifest_id,
        dataset_or_scenario_id=manifest.dataset_id,
        episode_id="synthetic-episode",
        temporal_context=temporal,
        capabilities=capabilities,
        admissions=(),
        configurations={},
    )
    trajectory = build_trajectory(
        trajectory_id="synthetic-capability-trajectory",
        partition_group_id="synthetic-contract-group",
        source_run_record_ids=tuple(item.run_record_id for item in offline_records),
        source_admission_ids=(),
        initial_prompt=exchange.prompt,
        exchanges=(
            DemonstrationExchange(
                exchange_id="synthetic-demonstration-exchange",
                memory_exchange=exchange,
                grounding=VisibleEvidenceGrounding(
                    observable_symptom="A closed-window alert is visible; detector execution remains unadmitted.",
                    graph_evidence_ids=(exchange.prompt.canonical_observation_id,),
                    observed_fact_codes=("all-source-configs-registered",),
                    bounded_inference_codes=("capability-inspection-only",),
                    unknown_codes=("real-detector-outcome-unknown",),
                    uncertainty_code="synthetic-contract-only",
                    action_justification="Finish without fabricating an unavailable detector result.",
                ),
            ),
        ),
        pids_coverage=refs,
        coverage_classes=(CoverageClass.CAPABILITY_AWARENESS,),
        sanitizer_version=DemonstrationSanitizer.VERSION,
    )
    DemonstrationSanitizer.validate_trajectory(trajectory)
    for record in offline_records:
        DemonstrationSanitizer.validate_offline_record(record)
    DemonstrationCorpusValidator.validate(
        trajectories=(trajectory,), offline_records=offline_records, admissions=()
    )
    exported = DemonstrationExporter.export(trajectory)
    export_jsonl = DemonstrationExporter.canonical_jsonl((exported,))
    DemonstrationExporter.parse_canonical_jsonl(export_jsonl)
    coverage = build_coverage_report(
        report_id="synthetic-demonstration-coverage", trajectories=(trajectory,), rejections=()
    )
    summary = {
        "schema_version": "synthetic-demonstration-summary-v1",
        "formal_training_approved": False,
        "synthetic_only": True,
        "dynamic_source_config_count": len(capabilities),
        "canonical_pids_ids": sorted({item.pids.pids_id for item in capabilities}),
        "variant_identity_count": len(refs),
        "offline_record_count": len(offline_records),
        "execution_matrix_row_count": len(matrix),
        "trajectory_count": 1,
        "successful_tool_use_count": 0,
        "source_admission_count": 0,
        "assistant_loss_message_count": sum(item.loss for item in exported.messages),
        "corpus_hash": corpus_digest((trajectory,), offline_records),
        "checks": {
            "dynamic_inventory_used": len(capabilities) >= 8,
            "all_rows_capability_only": all(
                item.execution_disposition == ExecutionDisposition.CAPABILITY_ONLY
                for item in offline_records
            ) and all(
                item.execution_disposition == ExecutionDisposition.CAPABILITY_ONLY
                for item in matrix
            ),
            "no_real_admission_claim": not trajectory.source_admission_ids,
            "assistant_only_loss": all(
                item.loss == (item.role.value == "assistant") for item in exported.messages
            ),
        },
    }
    if not all(summary["checks"].values()):
        raise RuntimeError("synthetic demonstration invariant failed")
    (run_dir / "dataset_manifest.json").write_text(manifest.model_dump_json(indent=2) + "\n")
    (run_dir / "offline_runs.jsonl").write_text(_jsonl(offline_records))
    (run_dir / "execution_matrix.jsonl").write_text(_jsonl(matrix))
    (run_dir / "trajectories.jsonl").write_text(trajectory.model_dump_json() + "\n")
    (run_dir / "openai_tool_trajectories.jsonl").write_text(export_jsonl)
    (run_dir / "coverage_report.json").write_text(coverage.model_dump_json(indent=2) + "\n")
    (run_dir / "rejections.jsonl").write_text("")
    (run_dir / "metrics.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (run_dir / "run_status.json").write_text(
        json.dumps({"status": "succeeded", **summary}, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
