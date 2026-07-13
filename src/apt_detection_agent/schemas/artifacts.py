"""Artifact and reproducibility manifests.

Requirements: REQ-ARTIFACT-001..003, REQ-REPRO-001..002.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from pydantic import Field, field_validator, model_validator

from .common import GitSha, Identifier, RunStatus, Sha256, StrictModel, Timestamp


class ArtifactRecord(StrictModel):
    artifact_id: Identifier
    artifact_type: Identifier
    relative_path: str
    content_hash: Sha256
    size_bytes: int = Field(ge=0)
    producing_stage: Identifier
    pids_related: bool = False
    source_config_id: Identifier | None = None
    checkpoint_hash: Sha256 | None = None
    created_at: Timestamp

    @field_validator("relative_path")
    @classmethod
    def safe_relative_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("artifact path must be relative and traversal-free")
        return value

    @model_validator(mode="after")
    def pids_artifact_has_execution_provenance(self) -> "ArtifactRecord":
        if self.pids_related and not (self.source_config_id and self.checkpoint_hash):
            raise ValueError("PIDS artifact requires source config and checkpoint hash")
        return self


class ArtifactManifest(StrictModel):
    manifest_id: Identifier
    run_id: Identifier
    code_commit: GitSha
    pidsmaker_commit: GitSha
    artifacts: tuple[ArtifactRecord, ...]
    created_at: Timestamp

    @model_validator(mode="after")
    def artifact_ids_are_unique(self) -> "ArtifactManifest":
        ids = [artifact.artifact_id for artifact in self.artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError("artifact IDs must be unique")
        return self


class RunManifest(StrictModel):
    run_id: Identifier
    status: RunStatus
    code_commit: GitSha
    pidsmaker_commit: GitSha
    environment_manifest_id: Identifier
    resource_profile_id: Identifier
    data_manifest_id: Identifier
    artifact_manifest_id: Identifier | None = None
    exact_command_artifact_id: Identifier
    resolved_config_artifact_id: Identifier
    random_seeds: tuple[int, ...]
    started_at: Timestamp
    ended_at: Timestamp | None = None
    failure_type: Identifier | None = None
    failure_message: str | None = None

    @model_validator(mode="after")
    def terminal_run_is_complete(self) -> "RunManifest":
        terminal = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.BLOCKED}
        if self.status in terminal and self.ended_at is None:
            raise ValueError("terminal run requires ended_at")
        if self.ended_at and self.ended_at < self.started_at:
            raise ValueError("run ended_at cannot precede started_at")
        if self.status == RunStatus.FAILED and not (self.failure_type and self.failure_message):
            raise ValueError("failed run requires typed failure provenance")
        if self.status == RunStatus.SUCCEEDED and (self.failure_type or self.failure_message):
            raise ValueError("successful run cannot carry failure provenance")
        if self.status == RunStatus.SUCCEEDED and not self.artifact_manifest_id:
            raise ValueError("successful run requires artifact manifest")
        return self
