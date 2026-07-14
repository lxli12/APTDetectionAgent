"""Private synthetic fixture for Phase 9 integration tests only.

Requirements: REQ-LABEL-001..004, REQ-EVAL-001..006, REQ-SFT-003.

This module belongs to the privileged evaluator namespace. It is never imported by
the Agent runner and its outputs are never formal dataset or model evidence.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from apt_detection_agent.schemas import DataSplit
from apt_detection_agent.schemas.evaluation import CampaignManifest

from .engine import HiddenEvaluationInput, ScoredEntity


def build_synthetic_hidden_input() -> HiddenEvaluationInput:
    now = datetime(2026, 1, 1, 1, 1, tzinfo=timezone.utc)
    campaigns = (
        CampaignManifest(
            manifest_version="synthetic-campaigns-v1",
            campaign_id="synthetic-campaign-a",
            dataset_id="synthetic-private-fixture",
            attack_date_range=(now - timedelta(hours=1), now),
            included_window_ids=("synthetic-window-1",),
            malicious_entity_ids=("node-a",),
            ground_truth_sources=("synthetic-private-source",),
        ),
        CampaignManifest(
            manifest_version="synthetic-campaigns-v1",
            campaign_id="synthetic-campaign-b",
            dataset_id="synthetic-private-fixture",
            attack_date_range=(now - timedelta(hours=1), now),
            included_window_ids=("synthetic-window-3",),
            malicious_entity_ids=("node-b",),
            ground_truth_sources=("synthetic-private-source",),
        ),
    )
    return HiddenEvaluationInput(
        evaluation_id="synthetic-evaluation-1",
        split=DataSplit.HELD_OUT,
        scenario_id="synthetic-scenario-1",
        episode_id="synthetic-episode-1",
        campaign_manifest_version="synthetic-campaigns-v1",
        campaigns=campaigns,
        scored_entities=(
            ScoredEntity(
                entity_id="node-a",
                score=0.9,
                alerted=True,
                window_ids=("synthetic-window-1",),
                evidence_artifact_ids=("visible-evidence-1",),
            ),
            ScoredEntity(
                entity_id="node-c",
                score=0.8,
                alerted=True,
                window_ids=("synthetic-window-2",),
            ),
            ScoredEntity(
                entity_id="node-b",
                score=0.7,
                alerted=True,
                window_ids=("synthetic-window-3",),
                evidence_artifact_ids=("visible-evidence-3",),
            ),
            ScoredEntity(entity_id="node-d", score=0.1, alerted=False),
        ),
        universe_entity_ids=("node-a", "node-b", "node-c", "node-d"),
        malicious_node_window_occurrences=(
            ("synthetic-window-1", "node-a"),
            ("synthetic-window-3", "node-b"),
        ),
        malicious_edges=(("node-a", "node-b"),),
        recovered_edges=(("node-a", "node-b"),),
        attack_chain_edges=(("node-a", "node-b"),),
        phase_to_malicious_entities={"execution": ("node-a",), "persistence": ("node-b",)},
        latency_seconds=1.0,
        gpu_seconds=0.0,
        tool_calls=1,
        computed_at=now,
    )
