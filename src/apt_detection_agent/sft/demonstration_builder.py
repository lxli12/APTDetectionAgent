"""Deterministic builders and corpus validation for pre-SFT demonstrations."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime

from pydantic import Field, model_validator

from apt_detection_agent.schemas import AdmittedUse, PIDSCapability, PIDSAdmissionRecord, PIDSRef
from apt_detection_agent.schemas.common import GitSha, Identifier, Sha256, StrictModel, Timestamp
from apt_detection_agent.schemas.evaluation import assert_deployable_payload

from .demonstration import (
    CanonicalDemonstrationTrajectory,
    CoverageClass,
    DemonstrationDatasetManifest,
    DemonstrationExecutionMatrixRow,
    DemonstrationExchange,
    DemonstrationRejection,
    DemonstrationTrainingUse,
    ExecutionDisposition,
    GraphConstructionManifest,
    HistoricalEvidenceContext,
    LabelAvailability,
    ObservableBehavior,
    OpaqueConfigurationSummary,
    PIDSDataPartitions,
    PublicOfflineRunRecord,
    TemporalContext,
    VisibleCostSummary,
    VisibleFailureCondition,
)
from apt_detection_agent.tooling.runtime_tools import DetectorCapabilityView


def stable_identifier(prefix: str, payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{prefix}-{hashlib.sha256(encoded.encode()).hexdigest()[:24]}"


def build_dataset_manifest(
    *,
    dataset_manifest_id: str,
    dataset_id: str,
    source_family: str,
    source_release: str,
    source_format: str,
    source_content_hashes: tuple[str, ...],
    access_and_license_status: str,
    normalized_storage_schema_id: str,
    provenance_schema_id: str,
    platform_class: str,
    graph_construction: GraphConstructionManifest,
    pids_data_partitions: PIDSDataPartitions,
    registered_pids: tuple[PIDSRef, ...],
    pids_admission_ids: tuple[str, ...],
    label_availability: LabelAvailability,
    training_use: DemonstrationTrainingUse,
    private_companion_manifest_id: str,
    code_commit: str,
    builder_version: str,
    created_at: datetime,
) -> DemonstrationDatasetManifest:
    values = locals()
    provisional = DemonstrationDatasetManifest.model_construct(**values, content_hash="0" * 64)
    return DemonstrationDatasetManifest(**values, content_hash=provisional.expected_hash())


def counterfactual_group_id(
    *,
    dataset_manifest_id: str,
    episode_id: str,
    temporal_context: TemporalContext,
    environment_profile_id: str,
    observable_behavior: ObservableBehavior,
) -> str:
    return stable_identifier(
        "counterfactual",
        {
            "dataset_manifest_id": dataset_manifest_id,
            "episode_id": episode_id,
            "window_id": temporal_context.window_id,
            "environment_profile_id": environment_profile_id,
            "observable_behavior_id": observable_behavior.behavior_id,
        },
    )


def build_offline_run_record(
    *,
    run_record_id: str,
    dataset_manifest_id: str,
    episode_id: str,
    split,
    environment_profile_id: str,
    observable_behavior: ObservableBehavior,
    historical_evidence_context: HistoricalEvidenceContext,
    temporal_context: TemporalContext,
    pids_capability: DetectorCapabilityView,
    detector: PIDSRef,
    configuration: OpaqueConfigurationSummary,
    admitted_use: str,
    execution_disposition: ExecutionDisposition,
    standardized_result_id: str | None,
    deployment_visible_outcome_code: str,
    cost: VisibleCostSummary,
    failure_condition: VisibleFailureCondition | None,
    execution_role: str,
    public_runtime_trace_id: str,
    admission_id: str | None,
    provenance_id: str,
) -> PublicOfflineRunRecord:
    values = locals()
    values["counterfactual_group_id"] = counterfactual_group_id(
        dataset_manifest_id=dataset_manifest_id,
        episode_id=episode_id,
        temporal_context=temporal_context,
        environment_profile_id=environment_profile_id,
        observable_behavior=observable_behavior,
    )
    provisional = PublicOfflineRunRecord.model_construct(**values, content_hash="0" * 64)
    return PublicOfflineRunRecord(**values, content_hash=provisional.expected_hash())


def build_execution_matrix(
    *,
    dataset_manifest_id: str,
    dataset_or_scenario_id: str,
    episode_id: str,
    temporal_context: TemporalContext,
    capabilities: tuple[PIDSCapability, ...],
    admissions: tuple[PIDSAdmissionRecord, ...],
    configurations: dict[tuple[str, str], OpaqueConfigurationSummary],
    admitted_use: AdmittedUse = AdmittedUse.TRAINING_CANDIDATE_CREATION,
    controlled_seed: int = 0,
    repetition_index: int = 0,
) -> tuple[DemonstrationExecutionMatrixRow, ...]:
    """Join dynamic capabilities to exact admission/config records without executing."""

    relevant_admissions = tuple(
        item for item in admissions if item.dataset_or_scenario_id == dataset_or_scenario_id
    )
    admission_by_identity = {
        (item.pids.pids_id, item.pids.variant_id): item
        for item in relevant_admissions
    }
    if len(admission_by_identity) != len(relevant_admissions):
        raise ValueError("duplicate admission identity")
    rows: list[DemonstrationExecutionMatrixRow] = []
    for capability in capabilities:
        identity = (capability.pids.pids_id, capability.pids.variant_id)
        admission = admission_by_identity.get(identity)
        configuration = configurations.get(identity)
        executable = bool(
            admission
            and admission.admitted_for_formal_trajectory
            and admitted_use in admission.admitted_uses
            and configuration
        )
        if executable:
            reason = None
        elif admission is None:
            reason = "missing-exact-admission"
        elif not admission.admitted_for_formal_trajectory:
            reason = "admission-gate-failed"
        elif admitted_use not in admission.admitted_uses:
            reason = "admitted-use-not-authorized"
        else:
            reason = "missing-frozen-configuration"
        rows.append(
            DemonstrationExecutionMatrixRow(
                matrix_row_id=stable_identifier(
                    "matrix",
                    {
                        "dataset_manifest_id": dataset_manifest_id,
                        "episode_id": episode_id,
                        "window_id": temporal_context.window_id,
                        "pids": identity,
                        "seed": controlled_seed,
                        "repetition": repetition_index,
                    },
                ),
                dataset_manifest_id=dataset_manifest_id,
                episode_id=episode_id,
                temporal_context=temporal_context,
                detector=capability.pids,
                source_config_id=capability.source_config_id,
                admitted_use=admitted_use,
                controlled_seed=controlled_seed,
                repetition_index=repetition_index,
                configuration=configuration,
                admission_id=admission.admission_id if executable and admission else None,
                execution_disposition=(
                    ExecutionDisposition.EXECUTED
                    if executable
                    else ExecutionDisposition.CAPABILITY_ONLY
                ),
                visible_reason_code=reason,
            )
        )
    return tuple(rows)


def build_trajectory(
    *,
    trajectory_id: str,
    partition_group_id: str,
    source_run_record_ids: tuple[str, ...],
    source_admission_ids: tuple[str, ...],
    initial_prompt,
    exchanges: tuple[DemonstrationExchange, ...],
    pids_coverage: tuple[PIDSRef, ...],
    coverage_classes: tuple[CoverageClass, ...],
    sanitizer_version: str,
) -> CanonicalDemonstrationTrajectory:
    values = locals()
    provisional = CanonicalDemonstrationTrajectory.model_construct(
        **values, content_hash="0" * 64
    )
    return CanonicalDemonstrationTrajectory(**values, content_hash=provisional.expected_hash())


class DemonstrationCoverageReport(StrictModel):
    schema_version: str = "demonstration-coverage-report-v1"
    report_id: Identifier
    trajectory_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    pids_counts: dict[Identifier, int]
    coverage_class_counts: dict[CoverageClass, int]
    rejection_reason_counts: dict[Identifier, int]
    admitted_success_count: int = Field(ge=0)
    capability_or_rejection_only_pids: tuple[Identifier, ...]
    content_hash: Sha256

    def expected_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    @model_validator(mode="after")
    def hash_is_stable(self) -> "DemonstrationCoverageReport":
        if self.content_hash != self.expected_hash():
            raise ValueError("coverage report hash mismatch")
        return self


class DemonstrationCorpusManifest(StrictModel):
    schema_version: str = "demonstration-corpus-manifest-v1"
    corpus_id: Identifier
    trajectory_ids: tuple[Identifier, ...]
    trajectory_group_ids: dict[Identifier, Identifier]
    train_group_ids: tuple[Identifier, ...]
    validation_group_ids: tuple[Identifier, ...]
    source_admission_ids: tuple[Identifier, ...]
    sanitizer_version: Identifier
    exporter_version: Identifier
    code_commit: GitSha
    created_at: Timestamp
    synthetic_only: bool
    formal_training_approved: bool
    corpus_hash: Sha256

    @model_validator(mode="after")
    def partitions_are_disjoint(self) -> "DemonstrationCorpusManifest":
        if len(self.trajectory_ids) != len(set(self.trajectory_ids)):
            raise ValueError("trajectory IDs must be unique")
        if set(self.trajectory_group_ids) != set(self.trajectory_ids):
            raise ValueError("each trajectory requires one group")
        train, validation = set(self.train_group_ids), set(self.validation_group_ids)
        if train & validation:
            raise ValueError("trajectory groups cannot cross train/validation")
        if train | validation != set(self.trajectory_group_ids.values()):
            raise ValueError("partitions must cover all trajectory groups")
        if self.synthetic_only and self.formal_training_approved:
            raise ValueError("synthetic corpus cannot approve formal training")
        return self


class DemonstrationCorpusValidator:
    @staticmethod
    def validate(
        *,
        trajectories: tuple[CanonicalDemonstrationTrajectory, ...],
        offline_records: tuple[PublicOfflineRunRecord, ...],
        admissions: tuple[PIDSAdmissionRecord, ...],
    ) -> None:
        trajectory_ids = [item.trajectory_id for item in trajectories]
        if len(trajectory_ids) != len(set(trajectory_ids)):
            raise ValueError("duplicate trajectory identity")
        record_by_id = {item.run_record_id: item for item in offline_records}
        admission_by_id = {item.admission_id: item for item in admissions}
        if len(record_by_id) != len(offline_records) or len(admission_by_id) != len(admissions):
            raise ValueError("source identities must be unique")
        for trajectory in trajectories:
            if not set(trajectory.source_run_record_ids).issubset(record_by_id):
                raise ValueError("trajectory cites missing offline run")
            if not set(trajectory.source_admission_ids).issubset(admission_by_id):
                raise ValueError("trajectory cites missing admission")
            if CoverageClass.SUCCESSFUL_TOOL_USE in trajectory.coverage_classes:
                for admission_id in trajectory.source_admission_ids:
                    admission = admission_by_id[admission_id]
                    if not admission.admitted_for_formal_trajectory:
                        raise ValueError("successful supervision cites failed admission")
                if not any(
                    record_by_id[item].execution_disposition == ExecutionDisposition.EXECUTED
                    for item in trajectory.source_run_record_ids
                ):
                    raise ValueError("successful supervision lacks executed source record")
            assert_deployable_payload(trajectory.model_dump(mode="json"), "demonstration_corpus")


def build_coverage_report(
    *,
    report_id: str,
    trajectories: tuple[CanonicalDemonstrationTrajectory, ...],
    rejections: tuple[DemonstrationRejection, ...],
) -> DemonstrationCoverageReport:
    pids = Counter(
        f"{ref.pids_id}:{ref.variant_id}" for trajectory in trajectories for ref in trajectory.pids_coverage
    )
    classes = Counter(cls for trajectory in trajectories for cls in trajectory.coverage_classes)
    reasons = Counter(item.reason_code for item in rejections)
    successful = {
        f"{ref.pids_id}:{ref.variant_id}"
        for trajectory in trajectories
        if CoverageClass.SUCCESSFUL_TOOL_USE in trajectory.coverage_classes
        for ref in trajectory.pids_coverage
    }
    values = {
        "report_id": report_id,
        "trajectory_count": len(trajectories),
        "rejected_count": len(rejections),
        "pids_counts": dict(sorted(pids.items())),
        "coverage_class_counts": dict(classes),
        "rejection_reason_counts": dict(sorted(reasons.items())),
        "admitted_success_count": sum(
            CoverageClass.SUCCESSFUL_TOOL_USE in item.coverage_classes for item in trajectories
        ),
        "capability_or_rejection_only_pids": tuple(sorted(set(pids) - successful)),
    }
    provisional = DemonstrationCoverageReport.model_construct(**values, content_hash="0" * 64)
    return DemonstrationCoverageReport(**values, content_hash=provisional.expected_hash())


def corpus_digest(
    trajectories: tuple[CanonicalDemonstrationTrajectory, ...],
    offline_records: tuple[PublicOfflineRunRecord, ...],
) -> str:
    digest = hashlib.sha256()
    for record in offline_records:
        digest.update(record.model_dump_json().encode())
        digest.update(b"\n")
    for trajectory in trajectories:
        digest.update(trajectory.model_dump_json().encode())
        digest.update(b"\n")
    return digest.hexdigest()
