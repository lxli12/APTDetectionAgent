"""Privileged metric engine; never imported into the controller process.

Requirements: REQ-LABEL-001..004, REQ-EVAL-001..007.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path

from pydantic import Field, model_validator

from apt_detection_agent.schemas.common import DataSplit, Identifier, StrictModel, Timestamp
from .private import (
    CampaignManifest,
    EvaluationRecord,
)
from apt_detection_agent.evaluation.public import EpisodeMetricsFeedback, TrainingStepFeedback


METRIC_DEFINITION_VERSION = "agent-eval-v2"


class ScoredEntity(StrictModel):
    entity_id: Identifier
    score: float
    alerted: bool
    window_ids: tuple[Identifier, ...] = ()
    evidence_artifact_ids: tuple[Identifier, ...] = ()


class HiddenEvaluationInput(StrictModel):
    evaluation_id: Identifier
    split: DataSplit
    scenario_id: Identifier
    episode_id: Identifier
    campaign_manifest_version: Identifier
    campaigns: tuple[CampaignManifest, ...]
    scored_entities: tuple[ScoredEntity, ...]
    universe_entity_ids: tuple[Identifier, ...]
    malicious_node_window_occurrences: tuple[tuple[Identifier, Identifier], ...] = ()
    malicious_edges: tuple[tuple[Identifier, Identifier], ...] = ()
    recovered_edges: tuple[tuple[Identifier, Identifier], ...] = ()
    attack_chain_edges: tuple[tuple[Identifier, Identifier], ...] = ()
    phase_to_malicious_entities: dict[Identifier, tuple[Identifier, ...]] = Field(
        default_factory=dict
    )
    latency_seconds: float = Field(default=0.0, ge=0.0)
    gpu_seconds: float = Field(default=0.0, ge=0.0)
    tool_calls: int = Field(default=0, ge=0)
    campaign_detection_delay_seconds: dict[Identifier, float] = Field(default_factory=dict)
    window_alert_counts: dict[Identifier, int] = Field(default_factory=dict)
    window_score_means: dict[Identifier, float] = Field(default_factory=dict)
    llm_calls: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    max_context_tokens: int = Field(default=0, ge=0)
    slow_path_triggers: int = Field(default=0, ge=0)
    reconfigurations: int = Field(default=0, ge=0)
    model_switches: int = Field(default=0, ge=0)
    threshold_changes: int = Field(default=0, ge=0)
    retraining_count: int = Field(default=0, ge=0)
    cache_hits: int = Field(default=0, ge=0)
    cache_requests: int = Field(default=0, ge=0)
    computed_at: Timestamp

    @model_validator(mode="after")
    def coherent_private_input(self) -> "HiddenEvaluationInput":
        if self.split not in {DataSplit.AGENT_TRAINING, DataSplit.VALIDATION, DataSplit.HELD_OUT}:
            raise ValueError("hidden evaluation input is not a deployment dependency")
        campaign_ids = [campaign.campaign_id for campaign in self.campaigns]
        if not campaign_ids or len(campaign_ids) != len(set(campaign_ids)):
            raise ValueError("campaign IDs must be nonempty and unique")
        if any(
            campaign.manifest_version != self.campaign_manifest_version
            for campaign in self.campaigns
        ):
            raise ValueError("campaign manifest versions must match evaluation input")
        entity_ids = [item.entity_id for item in self.scored_entities]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("scored entity IDs must be unique")
        if not set(entity_ids).issubset(self.universe_entity_ids):
            raise ValueError("scored entities must belong to the evaluation universe")
        malicious = {
            entity
            for campaign in self.campaigns
            for entity in campaign.malicious_entity_ids
        }
        if not malicious.issubset(self.universe_entity_ids):
            raise ValueError("malicious entities must belong to the evaluation universe")
        campaign_id_set = set(campaign_ids)
        if not set(self.campaign_detection_delay_seconds).issubset(campaign_id_set):
            raise ValueError("delay metrics reference an unknown campaign")
        if any(
            value < 0.0 or not math.isfinite(value)
            for value in self.campaign_detection_delay_seconds.values()
        ):
            raise ValueError("campaign detection delays must be finite and nonnegative")
        campaign_by_id = {campaign.campaign_id: campaign for campaign in self.campaigns}
        alerted_ids = {item.entity_id for item in self.scored_entities if item.alerted}
        if any(
            not (alerted_ids & set(campaign_by_id[campaign_id].malicious_entity_ids))
            for campaign_id in self.campaign_detection_delay_seconds
        ):
            raise ValueError("delay metrics require a detected campaign")
        if any(value < 0 for value in self.window_alert_counts.values()):
            raise ValueError("window alert counts must be nonnegative")
        if any(not math.isfinite(value) for value in self.window_score_means.values()):
            raise ValueError("window score means must be finite")
        if set(self.window_alert_counts) != set(self.window_score_means):
            raise ValueError("stability inputs must describe the same windows")
        derived_alert_counts: dict[str, int] = {}
        for item in self.scored_entities:
            if item.alerted:
                for window_id in item.window_ids:
                    derived_alert_counts[window_id] = derived_alert_counts.get(window_id, 0) + 1
        if self.window_alert_counts and self.window_alert_counts != derived_alert_counts:
            raise ValueError("window alert counts disagree with alerted entity occurrences")
        if self.cache_hits > self.cache_requests:
            raise ValueError("cache hits cannot exceed cache requests")
        return self


class HiddenEvaluationOutput(StrictModel):
    metric_definition_version: Identifier
    record: EvaluationRecord


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _mcc(tp: int, fp: int, fn: int, tn: int) -> float:
    denominator = math.sqrt((tp + fp) * (tp + fn) * (tn + fp) * (tn + fn))
    return ((tp * tn - fp * fn) / denominator) if denominator else 0.0


def _distribution_metrics(values: tuple[float, ...], prefix: str) -> dict[str, float]:
    if not values:
        return {
            f"{prefix}_mean": 0.0,
            f"{prefix}_stddev": 0.0,
            f"{prefix}_coefficient_of_variation": 0.0,
        }
    mean = statistics.fmean(values)
    stddev = statistics.pstdev(values)
    return {
        f"{prefix}_mean": mean,
        f"{prefix}_stddev": stddev,
        f"{prefix}_coefficient_of_variation": stddev / abs(mean) if mean else 0.0,
    }


def _campaign_curve(
    scored: tuple[ScoredEntity, ...], campaigns: tuple[CampaignManifest, ...]
) -> tuple[float, float | None]:
    entity_to_campaigns: dict[str, set[str]] = {}
    for campaign in campaigns:
        for entity in campaign.malicious_entity_ids:
            entity_to_campaigns.setdefault(entity, set()).add(campaign.campaign_id)
    total = len(campaigns)
    detected: set[str] = set()
    tp = 0
    fp = 0
    precision_to_coverage: dict[float, float] = {0.0: 0.0}
    precision_at_full: float | None = None
    ordered = sorted(scored, key=lambda value: (-value.score, value.entity_id))
    for _, tied_items in groupby(ordered, key=lambda value: value.score):
        for item in tied_items:
            if item.entity_id in entity_to_campaigns:
                tp += 1
                detected.update(entity_to_campaigns[item.entity_id])
            else:
                fp += 1
        precision = tp / (tp + fp)
        coverage = len(detected) / total
        precision_to_coverage[precision] = max(
            coverage, precision_to_coverage.get(precision, 0.0)
        )
        if coverage == 1.0 and precision_at_full is None:
            precision_at_full = precision
    points = sorted(precision_to_coverage.items())
    area = sum(
        (right_x - left_x) * (left_y + right_y) / 2
        for (left_x, left_y), (right_x, right_y) in zip(points, points[1:])
    )
    return area, precision_at_full


@dataclass(frozen=True)
class HiddenEvaluator:
    metric_definition_version: str = METRIC_DEFINITION_VERSION

    def evaluate(self, request: HiddenEvaluationInput) -> HiddenEvaluationOutput:
        malicious = {
            entity
            for campaign in request.campaigns
            for entity in campaign.malicious_entity_ids
        }
        alerted = {item.entity_id for item in request.scored_entities if item.alerted}
        universe = set(request.universe_entity_ids)
        tp_set = alerted & malicious
        fp_set = alerted - malicious
        fn_set = malicious - alerted
        tn_set = universe - malicious - alerted
        covered = sum(bool(alerted & set(campaign.malicious_entity_ids)) for campaign in request.campaigns)
        adp, p_at_c_100 = _campaign_curve(request.scored_entities, request.campaigns)

        truth_occurrences = set(request.malicious_node_window_occurrences)
        predicted_occurrences = {
            (window_id, item.entity_id)
            for item in request.scored_entities
            if item.alerted
            for window_id in item.window_ids
        }
        occurrence_tp = len(truth_occurrences & predicted_occurrences)
        occurrence_fp = len(predicted_occurrences - truth_occurrences)
        occurrence_fn = len(truth_occurrences - predicted_occurrences)

        malicious_edges = set(request.malicious_edges)
        recovered_edges = set(request.recovered_edges)
        chain_edges = set(request.attack_chain_edges)
        phase_hits = sum(
            bool(alerted & set(entities))
            for entities in request.phase_to_malicious_entities.values()
        )
        tp_with_evidence = sum(
            bool(item.evidence_artifact_ids)
            for item in request.scored_entities
            if item.entity_id in tp_set
        )
        delay_values = tuple(request.campaign_detection_delay_seconds.values())
        stability_metrics = {
            "window_denominator": float(len(request.window_alert_counts)),
            "total_alert_volume": float(sum(request.window_alert_counts.values())),
            **_distribution_metrics(
                tuple(float(value) for value in request.window_alert_counts.values()),
                "window_alert_count",
            ),
            **_distribution_metrics(
                tuple(request.window_score_means.values()), "window_score_mean"
            ),
        }
        record = EvaluationRecord(
            evaluation_id=request.evaluation_id,
            split=request.split,
            scenario_id=request.scenario_id,
            episode_id=request.episode_id,
            campaign_manifest_version=request.campaign_manifest_version,
            campaign_coverage=_ratio(covered, len(request.campaigns)),
            unique_malicious_node_tp=len(tp_set),
            unique_malicious_node_fp=len(fp_set),
            unique_malicious_node_fn=len(fn_set),
            p_at_c_100=p_at_c_100,
            mcc=_mcc(len(tp_set), len(fp_set), len(fn_set), len(tn_set)),
            adp=adp,
            node_window_metrics={
                "tp": occurrence_tp,
                "fp": occurrence_fp,
                "fn": occurrence_fn,
                "truth_denominator": len(truth_occurrences),
            },
            edge_metrics={
                "malicious_edge_recovered": len(malicious_edges & recovered_edges),
                "malicious_edge_denominator": len(malicious_edges),
                "attack_chain_edge_recovered": len(chain_edges & recovered_edges),
                "attack_chain_edge_denominator": len(chain_edges),
                "phase_recovered": phase_hits,
                "phase_denominator": len(request.phase_to_malicious_entities),
            },
            evidence_metrics={
                "tp_with_evidence": tp_with_evidence,
                "unique_tp_denominator": len(tp_set),
                "provenance_completeness": _ratio(tp_with_evidence, len(tp_set)),
            },
            efficiency_metrics={
                "latency_seconds": request.latency_seconds,
                "gpu_seconds": request.gpu_seconds,
                "tool_calls": float(request.tool_calls),
                "llm_calls": float(request.llm_calls),
                "prompt_tokens": float(request.prompt_tokens),
                "completion_tokens": float(request.completion_tokens),
                "max_context_tokens": float(request.max_context_tokens),
            },
            delay_metrics={
                "detected_campaign_denominator": float(len(delay_values)),
                "all_campaign_denominator": float(len(request.campaigns)),
                "mean_detection_delay_seconds": statistics.fmean(delay_values)
                if delay_values
                else 0.0,
                "maximum_detection_delay_seconds": max(delay_values) if delay_values else 0.0,
            },
            stability_metrics=stability_metrics,
            control_metrics={
                "slow_path_triggers": float(request.slow_path_triggers),
                "reconfigurations": float(request.reconfigurations),
                "model_switches": float(request.model_switches),
                "threshold_changes": float(request.threshold_changes),
                "retraining_count": float(request.retraining_count),
                "cache_hits": float(request.cache_hits),
                "cache_requests": float(request.cache_requests),
                "cache_hit_rate": _ratio(request.cache_hits, request.cache_requests),
            },
            computed_at=request.computed_at,
        )
        return HiddenEvaluationOutput(
            metric_definition_version=self.metric_definition_version,
            record=record,
        )
    def evaluate_to_private_artifact(
        self, request: HiddenEvaluationInput, private_path: Path
    ) -> EpisodeMetricsFeedback:
        if request.split not in {DataSplit.VALIDATION, DataSplit.HELD_OUT}:
            raise ValueError("episode-only feedback is for validation/held-out")
        if private_path.exists():
            raise FileExistsError(private_path)
        output = self.evaluate(request)
        private_path.parent.mkdir(parents=True, exist_ok=True)
        private_path.write_text(output.model_dump_json(indent=2) + "\n")
        return EpisodeMetricsFeedback(
            split=request.split,
            episode_id=request.episode_id,
            metrics_artifact_id=private_path.stem,
            emitted_at=request.computed_at,
        )

    @staticmethod
    def training_step_feedback(
        *, step_id: str, sanitized_reward: float, signal_id: str
    ) -> TrainingStepFeedback:
        return TrainingStepFeedback(
            split=DataSplit.AGENT_TRAINING,
            step_id=step_id,
            sanitized_reward=sanitized_reward,
            signal_id=signal_id,
        )
