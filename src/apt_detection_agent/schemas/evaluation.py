"""Privileged campaign truth and hidden-evaluation contracts.

These models belong to the evaluator boundary and are never nested in Observation.
Requirements: REQ-LABEL-001..004, REQ-EVAL-001..006, REQ-SFT-001..002.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import DataSplit, Identifier, StrictModel, Timestamp


class CampaignManifest(StrictModel):
    manifest_version: Identifier
    campaign_id: Identifier
    dataset_id: Identifier
    attack_date_range: tuple[Timestamp, Timestamp]
    included_window_ids: tuple[Identifier, ...]
    malicious_entity_ids: tuple[Identifier, ...]
    ground_truth_sources: tuple[str, ...]
    manual_corrections: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    exclusion_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def manifest_is_coherent(self) -> "CampaignManifest":
        start, end = self.attack_date_range
        if end <= start:
            raise ValueError("campaign date range must be increasing")
        if not self.included_window_ids or not self.malicious_entity_ids:
            raise ValueError("campaign requires windows and malicious entities")
        if len(self.exclusions) != len(self.exclusion_reasons):
            raise ValueError("every exclusion requires a reason")
        return self


class HiddenGroundTruth(StrictModel):
    scenario_id: Identifier
    campaign_manifests: tuple[CampaignManifest, ...]
    malicious_edges: tuple[tuple[Identifier, Identifier], ...] = ()
    evaluator_notes: tuple[str, ...] = ()


class EvaluationRecord(StrictModel):
    evaluation_id: Identifier
    split: DataSplit
    scenario_id: Identifier
    episode_id: Identifier
    campaign_manifest_version: Identifier
    campaign_coverage: float = Field(ge=0.0, le=1.0)
    unique_malicious_node_tp: int = Field(ge=0)
    unique_malicious_node_fp: int = Field(ge=0)
    unique_malicious_node_fn: int = Field(ge=0)
    p_at_c_100: float | None = Field(default=None, ge=0.0, le=1.0)
    mcc: float = Field(ge=-1.0, le=1.0)
    adp: float
    node_window_metrics: dict[str, float] = Field(default_factory=dict)
    edge_metrics: dict[str, float] = Field(default_factory=dict)
    evidence_metrics: dict[str, float] = Field(default_factory=dict)
    efficiency_metrics: dict[str, float] = Field(default_factory=dict)
    computed_at: Timestamp


class TrainingStepFeedback(StrictModel):
    split: DataSplit
    step_id: Identifier
    sanitized_reward: float
    signal_id: Identifier

    @model_validator(mode="after")
    def training_only(self) -> "TrainingStepFeedback":
        if self.split != DataSplit.AGENT_TRAINING:
            raise ValueError("step feedback is allowed only during agent training")
        return self


class EpisodeMetricsFeedback(StrictModel):
    split: DataSplit
    episode_id: Identifier
    metrics_artifact_id: Identifier
    emitted_at: Timestamp

    @model_validator(mode="after")
    def heldout_or_validation_only(self) -> "EpisodeMetricsFeedback":
        if self.split not in {DataSplit.VALIDATION, DataSplit.HELD_OUT}:
            raise ValueError("episode metrics feedback is for validation/held-out")
        return self


PRIVILEGED_FIELD_NAMES = frozenset(
    {
        "ground_truth",
        "test_labels",
        "labels",
        "campaign_mapping",
        "malicious_entity_ids",
        "counterfactual_best_action",
        "attack_identity",
        "attack_time",
        "campaign_id",
        "dataset_identity",
        "evaluator_notes",
        "hidden_metrics",
        "teacher_rationale",
        "tp",
        "fp",
        "fn",
        "unique_malicious_node_tp",
        "unique_malicious_node_fp",
        "unique_malicious_node_fn",
    }
)


def assert_deployable_payload(value: object, path: str = "payload") -> None:
    """Fail closed if a student/Agent payload contains privileged field names."""

    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in PRIVILEGED_FIELD_NAMES:
                raise ValueError(f"privileged field rejected at {path}.{key}")
            assert_deployable_payload(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_deployable_payload(child, f"{path}[{index}]")
