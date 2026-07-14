#!/usr/bin/env python3
"""Validate public evidence for inference on a new window with frozen assets."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"expected object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    run = args.run_dir.resolve()
    pipeline = run / "pids_artifacts" / "pipeline"
    stage = load(pipeline / "stage_summary.json")
    inference = load(pipeline / "inference_stage_summary.json")
    resolved = load(pipeline / "resolved_config.yaml")
    bundle = load(args.bundle.resolve() / "bundle_manifest.json")

    completed = stage.get("completed_stages", [])
    stage_names = [item.get("stage") for item in completed]
    if stage_names != ["construction", "transformation", "featurization", "feat_inference"]:
        raise ValueError("frozen prefix did not complete the required ordered stages")
    featurization = completed[2]
    if (
        featurization.get("execution") != "skipped_loaded_frozen_asset"
        or featurization.get("featurizer_hash") != bundle.get("featurizer_hash")
        or resolved.get("featurizer_fit_on_current_window") is not False
        or inference.get("featurizer_fit_on_inference_window") is not False
        or inference.get("frozen_bundle_used") is not True
        or inference.get("test_labels_loaded") is not False
        or inference.get("checkpoint_hash") != bundle.get("checkpoint_hash")
    ):
        raise ValueError("frozen inference provenance is not causal")

    forbidden = {"y", "label", "ground_truth", "campaign_id", "tp", "fp", "fn"}
    score_rows = 0
    for relative in inference.get("raw_score_artifacts", []):
        score = pipeline / str(relative)
        with score.open(newline="") as stream:
            reader = csv.reader(stream)
            columns = set(next(reader))
            score_rows += sum(1 for _ in reader)
        if columns & forbidden or "loss" not in columns:
            raise ValueError("raw score schema violates deployment-visible boundary")
    if score_rows <= 0:
        raise ValueError("new-window inference produced no scores")

    metrics = {
        "schema_version": "frozen-new-window-smoke-v1",
        "evidence_class": "frozen_new_window_pids_smoke",
        "checkpoint_hash": bundle["checkpoint_hash"],
        "featurizer_hash": bundle["featurizer_hash"],
        "test_window": resolved["split_windows"]["test"],
        "score_rows": score_rows,
        "test_labels_loaded": False,
        "featurizer_fit_on_current_window": False,
        "formal_performance_claim": False,
    }
    (run / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
