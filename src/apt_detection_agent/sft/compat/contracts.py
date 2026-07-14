"""Compatibility contracts for pre-demonstration SFT artifacts.

Requirements: REQ-SFT-001..004, REQ-LABEL-002..004,
REQ-ARTIFACT-001..002, REQ-REPRO-001..003.
"""

from __future__ import annotations

import hashlib
from pydantic import model_validator

from apt_detection_agent.schemas import AgentAction, DataSplit, Observation
from apt_detection_agent.schemas.common import GitSha, Identifier, Sha256, StrictModel, Timestamp
from apt_detection_agent.schemas.common import assert_deployable_payload


class StudentSFTExample(StrictModel):
    example_id: Identifier
    source_trajectory_id: Identifier
    observation: Observation
    target_action: AgentAction
    sanitizer_version: Identifier
    payload_hash: Sha256

    @model_validator(mode="after")
    def deployment_visible_and_aligned(self) -> "StudentSFTExample":
        if self.observation.split != DataSplit.AGENT_TRAINING:
            raise ValueError("student examples must come only from agent-training data")
        if self.target_action.based_on_observation_id != self.observation.observation_id:
            raise ValueError("student target must cite its observation")
        if self.target_action.window_id != self.observation.window.window_id:
            raise ValueError("student target window does not match observation")
        payload = {
            "observation": self.observation.model_dump(mode="json"),
            "target_action": self.target_action.model_dump(mode="json"),
        }
        assert_deployable_payload(payload, "student_example")
        expected = hashlib.sha256(
            self.__class__.canonical_payload(self.observation, self.target_action).encode()
        ).hexdigest()
        if self.payload_hash != expected:
            raise ValueError("student payload hash does not match sanitized content")
        return self

    @staticmethod
    def canonical_payload(observation: Observation, action: AgentAction) -> str:
        return observation.model_dump_json() + "\n" + action.model_dump_json()


class SFTDatasetManifest(StrictModel):
    dataset_id: Identifier
    dataset_version: Identifier
    source_split: DataSplit
    sanitizer_version: Identifier
    example_ids: tuple[Identifier, ...]
    train_example_ids: tuple[Identifier, ...]
    validation_example_ids: tuple[Identifier, ...]
    dataset_hash: Sha256
    code_commit: GitSha
    created_at: Timestamp
    synthetic_only: bool
    formal_training_approved: bool

    @model_validator(mode="after")
    def split_and_approval_are_safe(self) -> "SFTDatasetManifest":
        if self.source_split != DataSplit.AGENT_TRAINING:
            raise ValueError("SFT dataset may only derive from agent-training split")
        all_ids = tuple(self.example_ids)
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("SFT example IDs must be unique")
        train = set(self.train_example_ids)
        validation = set(self.validation_example_ids)
        if train & validation:
            raise ValueError("SFT train and validation partitions must not overlap")
        if train | validation != set(all_ids):
            raise ValueError("SFT partitions must cover every example exactly once")
        if self.synthetic_only and self.formal_training_approved:
            raise ValueError("synthetic fixtures cannot be approved as formal SFT data")
        return self


class SFTDataset(StrictModel):
    manifest: SFTDatasetManifest
    examples: tuple[StudentSFTExample, ...]


class SFTDatasetValidator:
    @staticmethod
    def validate(dataset: SFTDataset) -> None:
        ids = tuple(example.example_id for example in dataset.examples)
        if ids != dataset.manifest.example_ids:
            raise ValueError("dataset example order/IDs differ from manifest")
        digest = hashlib.sha256()
        for example in dataset.examples:
            digest.update(example.model_dump_json().encode())
            digest.update(b"\n")
        if digest.hexdigest() != dataset.manifest.dataset_hash:
            raise ValueError("SFT dataset hash does not match examples")
        for example in dataset.examples:
            assert_deployable_payload(example.model_dump(mode="json"), "sft_dataset")
