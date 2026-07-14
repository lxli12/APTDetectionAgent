#!/usr/bin/env python3
"""Finalize a public real-data report without importing the evaluator namespace."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apt_detection_agent.schemas import (
    DataSplit,
    StandardizedDetectionResult,
    ThresholdProvenance,
    assert_deployable_payload,
)
from apt_detection_agent.evaluation.public import EpisodeMetricsFeedback


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    result = StandardizedDetectionResult.model_validate_json(
        (run_dir / "detection_result.json").read_text()
    )
    threshold = ThresholdProvenance.model_validate_json(
        (run_dir / "threshold.json").read_text()
    )
    feedback = EpisodeMetricsFeedback.model_validate_json(
        (run_dir / "evaluation_feedback.json").read_text()
    )
    if result.split != DataSplit.VALIDATION or feedback.split != DataSplit.VALIDATION:
        raise ValueError("bounded real E2E is validation evidence, never held-out evidence")
    if result.threshold != threshold:
        raise ValueError("public threshold and detection result disagree")
    if any(
        name.startswith("apt_detection_agent.evaluator")
        or name.startswith("apt_detection_agent.evaluation.private")
        for name in sys.modules
    ):
        raise RuntimeError("controller report process imported the hidden evaluator namespace")
    payload = {
        "schema_version": "real-bounded-public-report-v1",
        "evidence_class": "bounded_real_validation_integration",
        "formal_performance_claim": False,
        "split": feedback.split.value,
        "episode_id": feedback.episode_id,
        "metrics_artifact_id": feedback.metrics_artifact_id,
        "emitted_at": feedback.emitted_at.isoformat(),
        "checkpoint_hash": result.checkpoint_hash,
        "threshold_id": threshold.threshold_id,
        "alert_count": sum(item.alerted for item in result.scored_entities),
        "scored_entity_count": len(result.scored_entities),
    }
    assert_deployable_payload(payload)
    (run_dir / "metrics.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    (run_dir / "summary.md").write_text(
        "# Bounded real-data validation integration\n\n"
        "A frozen validation-quantile threshold was applied to frozen PIDSMaker "
        "inference scores. The hidden evaluator returned only an episode-level "
        "artifact reference. Full campaign metrics remain evaluator-private. This "
        "run is integration evidence and makes no formal performance claim.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
