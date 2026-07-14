"""Deployment-visible standardized PIDS result contracts.

Requirements: REQ-LABEL-001..004, REQ-ARTIFACT-001..003,
REQ-CONFIG-002..003, REQ-CAUSAL-002.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from .common import DataSplit, DetectionUnit, Identifier, Sha256, StrictModel, Timestamp
from .pids import PIDSRef, ThresholdProvenance
from .runtime import TimeWindow


class EntityAnomalyScore(StrictModel):
    entity_id: Identifier
    score: float
    alerted: bool
    detection_unit: DetectionUnit
    evidence_artifact_ids: tuple[Identifier, ...]


class StandardizedDetectionResult(StrictModel):
    schema_version: str = "deployment-detection-result-v1"
    result_id: Identifier
    split: DataSplit
    pids: PIDSRef
    dataset_id: Identifier
    source_config_id: Identifier
    checkpoint_hash: Sha256
    threshold: ThresholdProvenance
    window: TimeWindow
    score_semantics: Identifier
    scored_entities: tuple[EntityAnomalyScore, ...]
    raw_artifact_hashes: dict[Identifier, Sha256]
    inference_elapsed_seconds: float = Field(ge=0.0)
    gpu_seconds: float = Field(ge=0.0)
    created_at: Timestamp

    @model_validator(mode="after")
    def frozen_and_nonempty(self) -> "StandardizedDetectionResult":
        if self.threshold.checkpoint_hash != self.checkpoint_hash:
            raise ValueError("threshold and detection checkpoint identities differ")
        if not self.scored_entities or not self.raw_artifact_hashes:
            raise ValueError("standardized detection requires scores and raw artifact evidence")
        return self
