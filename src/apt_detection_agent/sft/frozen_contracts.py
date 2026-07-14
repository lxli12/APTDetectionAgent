"""Formal SFT contracts aligned with the frozen runtime v2 trace."""

from __future__ import annotations

import hashlib
import json

from pydantic import Field, model_validator

from apt_detection_agent.schemas import (
    CanonicalAgentVisibleObservation,
    DataSplit,
    FrozenActionDecision,
    FrozenMemoryExchange,
    ModelPromptObservation,
    PIDSAdmissionRecord,
)
from apt_detection_agent.schemas.common import GitSha, Identifier, Sha256, StrictModel, Timestamp
from apt_detection_agent.schemas.evaluation import assert_deployable_payload


def frozen_example_payload(
    *,
    canonical: CanonicalAgentVisibleObservation,
    prompt: ModelPromptObservation,
    memory_exchange: FrozenMemoryExchange,
    target_action: FrozenActionDecision,
    source_admission_ids: tuple[str, ...],
) -> str:
    payload = {
        "canonical_observation": canonical.model_dump(mode="json"),
        "model_prompt": prompt.model_dump(mode="json"),
        "memory_exchange": memory_exchange.model_dump(mode="json"),
        "target_action": target_action.model_dump(mode="json"),
        "source_admission_ids": source_admission_ids,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class FrozenStudentSFTExample(StrictModel):
    schema_version: str = "frozen-student-sft-example-v2"
    example_id: Identifier
    source_trajectory_id: Identifier
    partition_group_id: Identifier
    canonical_observation: CanonicalAgentVisibleObservation
    model_prompt: ModelPromptObservation
    memory_exchange: FrozenMemoryExchange
    target_action: FrozenActionDecision
    source_admission_ids: tuple[Identifier, ...] = Field(min_length=1)
    sanitizer_version: Identifier
    payload_hash: Sha256

    @model_validator(mode="after")
    def same_deployable_runtime_contract(self) -> "FrozenStudentSFTExample":
        observation = self.canonical_observation
        if observation.split != DataSplit.AGENT_TRAINING:
            raise ValueError("formal student example must be agent-training scoped")
        if (
            self.model_prompt.canonical_observation_id != observation.observation_id
            or self.model_prompt.canonical_observation_hash != observation.content_hash
            or self.memory_exchange.prompt != self.model_prompt
            or self.memory_exchange.response.action != self.target_action
            or self.target_action.based_on_observation_id != observation.observation_id
            or self.target_action.window_id != observation.window.window_id
        ):
            raise ValueError("SFT example diverges from frozen runtime identity/hash")
        assert_deployable_payload(self.model_dump(mode="json"), "frozen_sft_example")
        expected = hashlib.sha256(
            frozen_example_payload(
                canonical=observation,
                prompt=self.model_prompt,
                memory_exchange=self.memory_exchange,
                target_action=self.target_action,
                source_admission_ids=self.source_admission_ids,
            ).encode()
        ).hexdigest()
        if self.payload_hash != expected:
            raise ValueError("frozen SFT payload hash mismatch")
        return self


class FrozenSFTDatasetManifest(StrictModel):
    schema_version: str = "frozen-sft-dataset-manifest-v2"
    dataset_id: Identifier
    dataset_version: Identifier
    source_split: DataSplit
    sanitizer_version: Identifier
    example_ids: tuple[Identifier, ...]
    example_group_ids: dict[Identifier, Identifier]
    train_group_ids: tuple[Identifier, ...]
    validation_group_ids: tuple[Identifier, ...]
    source_admission_ids: tuple[Identifier, ...] = Field(min_length=1)
    dataset_hash: Sha256
    code_commit: GitSha
    created_at: Timestamp
    synthetic_only: bool
    formal_training_approved: bool

    @model_validator(mode="after")
    def groups_are_disjoint_and_complete(self) -> "FrozenSFTDatasetManifest":
        if self.source_split != DataSplit.AGENT_TRAINING:
            raise ValueError("formal SFT source split must be agent training")
        if len(self.example_ids) != len(set(self.example_ids)):
            raise ValueError("SFT example IDs must be unique")
        if set(self.example_group_ids) != set(self.example_ids):
            raise ValueError("every example requires exactly one partition group")
        train, validation = set(self.train_group_ids), set(self.validation_group_ids)
        if train & validation:
            raise ValueError("SFT partition groups cannot cross train/validation")
        if train | validation != set(self.example_group_ids.values()):
            raise ValueError("partition groups must cover every example")
        if self.synthetic_only and self.formal_training_approved:
            raise ValueError("synthetic frozen traces cannot approve formal training")
        return self


class FrozenSFTDataset(StrictModel):
    manifest: FrozenSFTDatasetManifest
    admissions: tuple[PIDSAdmissionRecord, ...] = Field(min_length=1)
    examples: tuple[FrozenStudentSFTExample, ...] = Field(min_length=1)


class FrozenSFTDatasetValidator:
    @staticmethod
    def validate(dataset: FrozenSFTDataset) -> None:
        manifest = dataset.manifest
        if tuple(item.example_id for item in dataset.examples) != manifest.example_ids:
            raise ValueError("frozen SFT example order differs from manifest")
        admission_by_id = {item.admission_id: item for item in dataset.admissions}
        if len(admission_by_id) != len(dataset.admissions):
            raise ValueError("frozen SFT admissions must be unique")
        if set(admission_by_id) != set(manifest.source_admission_ids):
            raise ValueError("manifest admission identities differ from records")
        for admission in dataset.admissions:
            if admission.split != DataSplit.AGENT_TRAINING:
                raise ValueError("SFT admission records must be agent-training scoped")
            if not manifest.synthetic_only and not admission.admitted_for_formal_trajectory:
                raise ValueError("formal SFT requires all-gates admission")
        for example in dataset.examples:
            if not set(example.source_admission_ids).issubset(admission_by_id):
                raise ValueError("example cites missing admission")
            if manifest.example_group_ids[example.example_id] != example.partition_group_id:
                raise ValueError("example partition group differs from manifest")
            assert_deployable_payload(example.model_dump(mode="json"), "frozen_sft_dataset")
        digest = hashlib.sha256()
        for admission in dataset.admissions:
            digest.update(admission.model_dump_json().encode())
            digest.update(b"\n")
        for example in dataset.examples:
            digest.update(example.model_dump_json().encode())
            digest.update(b"\n")
        if digest.hexdigest() != manifest.dataset_hash:
            raise ValueError("frozen SFT dataset hash mismatch")
