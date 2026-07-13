"""Split-scoped case memory and deployable static-LTM contracts.

Requirements: REQ-MEMORY-001..006, REQ-LABEL-002, REQ-REPRO-001.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from .common import DataSplit, Identifier, Sha256, StrictModel, Timestamp
from .pids import PIDSRef


class MemoryLayer(str, Enum):
    WORKING = "working"
    EPISODE = "episode"
    STATIC_LTM = "static_ltm"


class MemoryRecord(StrictModel):
    memory_id: Identifier
    layer: MemoryLayer
    split: DataSplit
    scenario_id: Identifier | None
    episode_id: Identifier | None
    environment: str
    observable_behavior: str
    pids: PIDSRef
    action: str
    content: str = Field(min_length=1)
    normalized_content_hash: Sha256
    evidence_artifact_ids: tuple[Identifier, ...]
    applicability_conditions: tuple[str, ...] = ()
    conflicts_with: tuple[Identifier, ...] = ()
    created_at: Timestamp

    @model_validator(mode="after")
    def lifecycle_scope_is_explicit(self) -> "MemoryRecord":
        if self.layer in {MemoryLayer.WORKING, MemoryLayer.EPISODE}:
            if not self.scenario_id or not self.episode_id:
                raise ValueError("runtime memory requires scenario and episode scope")
        if self.layer == MemoryLayer.STATIC_LTM and (self.scenario_id or self.episode_id):
            raise ValueError("static LTM cannot carry runtime scenario/episode identity")
        if self.layer == MemoryLayer.STATIC_LTM and self.split != DataSplit.AGENT_TRAINING:
            raise ValueError("static LTM must be a frozen agent-training artifact")
        return self


class StaticLTMSnapshot(StrictModel):
    snapshot_id: Identifier
    records: tuple[MemoryRecord, ...] = Field(min_length=1)
    source_training_manifest_id: Identifier
    sanitizer_version: Identifier
    provenance_hash: Sha256
    hidden_evaluator_signature: str
    human_sample_reviewed: bool
    frozen_at: Timestamp

    @model_validator(mode="after")
    def only_deployable_static_records(self) -> "StaticLTMSnapshot":
        if not self.human_sample_reviewed:
            raise ValueError("released static LTM requires human sample review")
        if not self.hidden_evaluator_signature.strip():
            raise ValueError("released static LTM requires evaluator signature")
        if any(record.layer != MemoryLayer.STATIC_LTM for record in self.records):
            raise ValueError("static LTM snapshot can contain only static records")
        return self
