"""Private validation-only campaign coverage threshold calibration.

Requirements: REQ-CAUSAL-002, REQ-CONFIG-002..003, REQ-EVAL-004..006,
REQ-LABEL-001..004.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from apt_detection_agent.schemas.common import (
    DataSplit,
    GitSha,
    Identifier,
    Sha256,
    StrictModel,
    Timestamp,
)
from .contracts import CampaignManifest
from apt_detection_agent.schemas.pids import (
    CalibrationMethod,
    ThresholdProvenance,
    ThresholdSourceSplit,
)


CALIBRATION_DEFINITION_VERSION = "campaign-coverage-calibration-v1"


class ValidationEntityScore(StrictModel):
    entity_id: Identifier
    score: float = Field(allow_inf_nan=False)


class ValidationCoverageCalibrationInput(StrictModel):
    calibration_id: Identifier
    split: DataSplit
    source_dataset: Identifier
    campaign_manifest_version: Identifier
    campaigns: tuple[CampaignManifest, ...]
    scored_entities: tuple[ValidationEntityScore, ...]
    universe_entity_ids: tuple[Identifier, ...]
    target_coverage: float = Field(gt=0.0, le=1.0)
    target_metric: Literal["campaign-coverage"]
    threshold_id: Identifier
    checkpoint_hash: Sha256
    created_at: Timestamp
    code_commit: GitSha

    @model_validator(mode="after")
    def validation_campaigns_are_coherent(self) -> "ValidationCoverageCalibrationInput":
        if self.split != DataSplit.VALIDATION:
            raise ValueError("campaign coverage thresholds calibrate on validation only")
        campaign_ids = [campaign.campaign_id for campaign in self.campaigns]
        if not campaign_ids or len(campaign_ids) != len(set(campaign_ids)):
            raise ValueError("calibration requires unique agent-level validation campaigns")
        if any(
            campaign.manifest_version != self.campaign_manifest_version
            for campaign in self.campaigns
        ):
            raise ValueError("campaign manifest versions must match calibration input")
        if any(campaign.dataset_id != self.source_dataset for campaign in self.campaigns):
            raise ValueError("campaign dataset must match threshold source dataset")
        scored_ids = [item.entity_id for item in self.scored_entities]
        if not scored_ids or len(scored_ids) != len(set(scored_ids)):
            raise ValueError("validation entity scores must be nonempty and unique")
        universe = set(self.universe_entity_ids)
        if len(universe) != len(self.universe_entity_ids):
            raise ValueError("validation universe entity IDs must be unique")
        if not set(scored_ids).issubset(universe):
            raise ValueError("scored entities must belong to the validation universe")
        malicious = {
            entity
            for campaign in self.campaigns
            for entity in campaign.malicious_entity_ids
        }
        if not malicious.issubset(universe):
            raise ValueError("campaign entities must belong to the validation universe")
        return self


class PrivateCoverageCalibrationResult(StrictModel):
    calibration_definition_version: Identifier
    calibration_id: Identifier
    threshold: ThresholdProvenance
    target_coverage: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    achieved_campaign_coverage: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    precision_at_threshold: float = Field(ge=0.0, le=1.0, allow_inf_nan=False)
    alerted_entity_count: int = Field(ge=0)
    campaign_count: int = Field(gt=0)


@dataclass(frozen=True)
class ValidationCoverageCalibrator:
    """Choose the highest validation score threshold meeting campaign coverage."""

    calibration_definition_version: str = CALIBRATION_DEFINITION_VERSION

    def calibrate(
        self, request: ValidationCoverageCalibrationInput
    ) -> PrivateCoverageCalibrationResult:
        entity_to_campaigns: dict[str, set[str]] = {}
        malicious: set[str] = set()
        for campaign in request.campaigns:
            for entity in campaign.malicious_entity_ids:
                malicious.add(entity)
                entity_to_campaigns.setdefault(entity, set()).add(campaign.campaign_id)

        chosen: tuple[float, set[str], set[str]] | None = None
        for threshold in sorted({item.score for item in request.scored_entities}, reverse=True):
            alerted = {
                item.entity_id
                for item in request.scored_entities
                if item.score >= threshold
            }
            covered = {
                campaign_id
                for entity in alerted
                for campaign_id in entity_to_campaigns.get(entity, ())
            }
            if len(covered) / len(request.campaigns) >= request.target_coverage:
                chosen = (threshold, alerted, covered)
                break
        if chosen is None:
            raise ValueError("validation scores cannot satisfy campaign coverage constraint")

        threshold, alerted, covered = chosen
        true_alerts = len(alerted & malicious)
        precision = true_alerts / len(alerted) if alerted else 0.0
        provenance = ThresholdProvenance(
            threshold_id=request.threshold_id,
            value=threshold,
            calibration_method=CalibrationMethod.VALIDATION_COVERAGE,
            source_dataset=request.source_dataset,
            source_split=ThresholdSourceSplit.VALIDATION,
            checkpoint_hash=request.checkpoint_hash,
            target_metric=request.target_metric,
            created_at=request.created_at,
            code_commit=request.code_commit,
        )
        return PrivateCoverageCalibrationResult(
            calibration_definition_version=self.calibration_definition_version,
            calibration_id=request.calibration_id,
            threshold=provenance,
            target_coverage=request.target_coverage,
            achieved_campaign_coverage=len(covered) / len(request.campaigns),
            precision_at_threshold=precision,
            alerted_entity_count=len(alerted),
            campaign_count=len(request.campaigns),
        )
