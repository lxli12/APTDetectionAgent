"""Stable SFT trainer request and result contracts.

Requirements: REQ-SFT-005..010, REQ-ARTIFACT-001..003, REQ-REPRO-001..003.
"""

from pathlib import PurePosixPath

from pydantic import Field, field_validator, model_validator

from apt_detection_agent.schemas.common import GitSha, Identifier, Sha256, StrictModel, Timestamp

BLOCKED_BY_SFT_DATASET = "BLOCKED_BY_SFT_DATASET"


class SFTTrainingConfig(StrictModel):
    config_id: Identifier
    base_model_id: Identifier
    base_model_hash: Sha256
    dataset_id: Identifier
    dataset_hash: Sha256
    adapter_format: Identifier = "lora"
    seed: int = Field(ge=0)
    learning_rate: float = Field(gt=0)
    epochs: int = Field(ge=1)
    max_sequence_length: int = Field(ge=128)
    dry_run: bool = False


class SFTCheckpointManifest(StrictModel):
    checkpoint_id: Identifier
    base_model_id: Identifier
    base_model_hash: Sha256
    adapter_format: Identifier
    adapter_relative_path: str
    adapter_hash: Sha256
    dataset_hash: Sha256
    training_config_hash: Sha256
    code_commit: GitSha
    produced_at: Timestamp

    @field_validator("adapter_relative_path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("adapter path must be relative and traversal-free")
        return value


class SFTTrainingResult(StrictModel):
    status: Identifier
    dataset_id: Identifier | None = None
    config_id: Identifier | None = None
    checkpoint_manifest: SFTCheckpointManifest | None = None
    reason: str | None = None
    dry_run: bool = False

    @model_validator(mode="after")
    def status_does_not_fabricate_checkpoint(self) -> "SFTTrainingResult":
        if self.status == BLOCKED_BY_SFT_DATASET:
            if self.checkpoint_manifest is not None or not self.reason:
                raise ValueError("blocked SFT result requires reason and no checkpoint")
        if self.dry_run and self.checkpoint_manifest is not None:
            raise ValueError("dry-run validation cannot produce a checkpoint")
        return self
