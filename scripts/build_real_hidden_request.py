#!/usr/bin/env python3
"""Build a private campaign manifest and evaluation request from public PIDS scores.

This entrypoint belongs only to the hidden-evaluator OS identity.
Requirements: REQ-LABEL-001..004, REQ-EVAL-001..007.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from apt_detection_agent.evaluator import HiddenEvaluationInput, ScoredEntity
from apt_detection_agent.schemas import StandardizedDetectionResult
from apt_detection_agent.schemas.evaluation import CampaignManifest


def child(path: Path, root: Path, description: str) -> Path:
    resolved = path.resolve()
    if resolved.parent != root.resolve():
        raise ValueError(f"{description} must be a direct child of its permission root")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--private-request", type=Path, required=True)
    parser.add_argument("--private-campaign-manifest", type=Path, required=True)
    args = parser.parse_args()
    private_root_text = os.environ.get("HIDDEN_EVALUATOR_PRIVATE_ROOT")
    observation_root_text = os.environ.get("AGENT_OBSERVATION_ROOT")
    if not private_root_text or not observation_root_text:
        raise ValueError("explicit private and observation roots are required")
    private_root = Path(private_root_text).resolve()
    observation_root = Path(observation_root_text).resolve()
    observation_path = child(args.observation, observation_root, "observation")
    truth_path = child(args.ground_truth, private_root, "ground truth")
    request_path = child(args.private_request, private_root, "private request")
    manifest_path = child(
        args.private_campaign_manifest, private_root, "private campaign manifest"
    )
    if request_path.exists() or manifest_path.exists():
        raise FileExistsError("private evaluator artifacts are append-only")

    observation = StandardizedDetectionResult.model_validate_json(
        observation_path.read_text()
    )
    universe = {item.entity_id for item in observation.scored_entities}
    truth_entities: set[str] = set()
    with truth_path.open(newline="") as stream:
        for row in csv.reader(stream):
            if len(row) != 3:
                raise ValueError("private ground-truth row must contain three fields")
            truth_entities.add(str(int(row[2])))
    malicious = tuple(sorted(truth_entities & universe, key=int))
    excluded = tuple(sorted(truth_entities - universe, key=int))
    if not malicious:
        raise ValueError("selected campaign has no malicious entity in the observed window")
    zone = ZoneInfo("America/New_York")
    campaign = CampaignManifest(
        manifest_version="cadets-e3-campaign-manifest-v1",
        campaign_id="cadets-e3-nginx-backdoor-20180406",
        dataset_id=observation.dataset_id,
        attack_date_range=(
            datetime(2018, 4, 6, 11, 20, tzinfo=zone),
            datetime(2018, 4, 6, 12, 9, tzinfo=zone),
        ),
        included_window_ids=(observation.window.window_id,),
        malicious_entity_ids=malicious,
        ground_truth_sources=(
            f"private:{truth_path.name}#sha256={hashlib.sha256(truth_path.read_bytes()).hexdigest()}",
        ),
        exclusions=excluded,
        exclusion_reasons=tuple("entity not observed in bounded evaluation window" for _ in excluded),
    )
    scored = tuple(
        ScoredEntity(
            entity_id=item.entity_id,
            score=item.score,
            alerted=item.alerted,
            window_ids=(observation.window.window_id,),
            evidence_artifact_ids=item.evidence_artifact_ids,
        )
        for item in observation.scored_entities
    )
    alerted_count = sum(item.alerted for item in observation.scored_entities)
    mean_score = sum(item.score for item in observation.scored_entities) / len(
        observation.scored_entities
    )
    request = HiddenEvaluationInput(
        evaluation_id="phase9-real-bounded-evaluation",
        split=observation.split,
        scenario_id="cadets-e3-bounded-real-scenario",
        episode_id="cadets-e3-bounded-real-episode",
        campaign_manifest_version=campaign.manifest_version,
        campaigns=(campaign,),
        scored_entities=scored,
        universe_entity_ids=tuple(sorted(universe, key=int)),
        malicious_node_window_occurrences=tuple(
            (observation.window.window_id, entity_id) for entity_id in malicious
        ),
        latency_seconds=observation.inference_elapsed_seconds,
        gpu_seconds=observation.gpu_seconds,
        tool_calls=3,
        window_alert_counts={observation.window.window_id: alerted_count},
        window_score_means={observation.window.window_id: mean_score},
        retraining_count=0,
        computed_at=datetime.now(timezone.utc),
    )
    manifest_path.write_text(campaign.model_dump_json(indent=2) + "\n")
    request_path.write_text(request.model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
