#!/usr/bin/env python3
"""Validate and summarize a completed real causal PIDSMaker smoke."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path.name}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    pipeline = run_dir / "pids_artifacts" / "pipeline"
    stage = load(pipeline / "stage_summary.json")
    training = load(pipeline / "training_stage_summary.json")
    inference = load(pipeline / "inference_stage_summary.json")
    checkpoint = load(pipeline / "checkpoint_manifest.json")
    if [item["stage"] for item in stage["completed_stages"]] != [
        "construction",
        "transformation",
        "featurization",
        "feat_inference",
    ]:
        raise ValueError("prefix stages are incomplete or reordered")
    if training.get("test_data_used_for_selection") is not False:
        raise ValueError("test data entered checkpoint selection")
    if training.get("wandb_used") is not False:
        raise ValueError("W&B entered the causal training path")
    if inference.get("test_labels_loaded") is not False:
        raise ValueError("test labels entered frozen inference")
    if checkpoint.get("checkpoint_hash") != inference.get("checkpoint_hash"):
        raise ValueError("training and inference checkpoint identities differ")
    numeric = {
        "best_validation_score": float(training["best_validation_score"]),
        "anomaly_score_mean": float(inference["anomaly_score_mean"]),
        "peak_inference_cpu_memory_gib": float(inference["peak_inference_cpu_memory_gib"]),
        "peak_inference_gpu_memory_gib": float(inference["peak_inference_gpu_memory_gib"]),
        "time_per_batch_seconds": float(inference["time_per_batch_seconds"]),
    }
    if not all(math.isfinite(value) for value in numeric.values()):
        raise ValueError("smoke metrics contain non-finite values")
    metrics = {
        "schema_version": "real-causal-pids-smoke-v1",
        "evidence_class": "bounded_smoke_not_formal_benchmark",
        "pids_id": "velox",
        "dataset_id": "CADETS_E3",
        "pidsmaker_commit": stage["pidsmaker_commit"],
        "compatibility_patch_series_hash": stage["compatibility_patch_series_hash"],
        "checkpoint_hash": checkpoint["checkpoint_hash"],
        "window_boundary": "[start,end)",
        "test_labels_loaded": False,
        "wandb_used": False,
        **numeric,
    }
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n"
    )
    (run_dir / "summary.md").write_text(
        "# Real causal PIDSMaker smoke\n\n"
        "The bounded VELOX/CADETS smoke completed exact-window preprocessing, "
        "validation-only checkpoint selection, and frozen test inference. This is "
        "compatibility evidence, not a formal benchmark result.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
