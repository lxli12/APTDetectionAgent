#!/usr/bin/env python3
"""Freeze causal PIDSMaker validation assets before formal SFT data arrives.

Requirements: REQ-CAUSAL-002, REQ-CONFIG-002..003, REQ-ARTIFACT-001..003,
REQ-SFT-003..004, REQ-REPRO-001..002.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from apt_detection_agent.schemas import (
    ApprovedConfig,
    DataSplit,
    ExperimentClass,
    PIDSRef,
    PipelineStage,
    ThresholdProvenance,
    TransductiveStatus,
    assert_deployable_payload,
)


def load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"expected object: {path}")
    return payload


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ValueError("frozen asset tree is empty")
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def scalar(value: str) -> str | int | float | bool:
    if value in {"True", "False"}:
        return value == "True"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pids-run", type=Path, required=True)
    parser.add_argument("--validation-run", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    approved_text = os.environ.get("APT_PRE_SFT_BUNDLE_ROOT")
    output = args.output_root.resolve()
    if not approved_text or output.parent != Path(approved_text).resolve():
        raise ValueError("bundle must be a direct child of the approved pre-SFT root")
    if output.exists():
        raise FileExistsError("pre-SFT bundles are append-only")
    pids_run = args.pids_run.resolve()
    validation_run = args.validation_run.resolve()
    pids_status = load(pids_run / "run_status.json")
    validation_status = load(validation_run / "run_status.json")
    public_metrics = load(validation_run / "metrics.json")
    if pids_status.get("status") != "succeeded" or pids_status.get(
        "evidence_class"
    ) != "real_causal_pids_smoke":
        raise ValueError("source PIDS run is not accepted causal smoke evidence")
    if validation_status.get("status") != "succeeded" or validation_status.get(
        "evidence_class"
    ) != "bounded_real_validation_integration":
        raise ValueError("source validation run is not accepted bounded real evidence")
    if public_metrics.get("formal_performance_claim") is not False:
        raise ValueError("bounded validation cannot become a formal performance claim")

    pipeline = pids_run / "pids_artifacts" / "pipeline"
    checkpoint_manifest = load(pipeline / "checkpoint_manifest.json")
    checkpoint_source = pipeline / str(checkpoint_manifest["checkpoint_relative_path"])
    if tree_hash(checkpoint_source) != checkpoint_manifest.get("checkpoint_hash"):
        raise ValueError("source checkpoint content hash mismatch")
    featurizer_models = tuple(sorted(pipeline.glob("featurization/*/featurization/*/stored_models")))
    if len(featurizer_models) != 1 or not (featurizer_models[0] / "word2vec.model").is_file():
        raise ValueError("expected exactly one frozen word2vec featurizer")
    threshold = ThresholdProvenance.model_validate_json(
        (validation_run / "threshold.json").read_text()
    )
    if threshold.checkpoint_hash != checkpoint_manifest.get("checkpoint_hash"):
        raise ValueError("threshold and checkpoint identity mismatch")
    resolved = load(pipeline / "resolved_config.yaml")
    parameters = {
        key: scalar(value)
        for key, value in (
            str(item).split("=", 1) for item in resolved.get("overrides", [])
        )
    }
    frozen_at = datetime.now(timezone.utc)
    config = ApprovedConfig(
        config_id=f"velox-cadets-validation-{threshold.checkpoint_hash[:12]}",
        pids=PIDSRef(pids_id="velox"),
        source_config_id="velox",
        dataset_id="CADETS_E3",
        parameters=parameters,
        required_pipeline_stages=(
            PipelineStage.CONSTRUCTION,
            PipelineStage.TRANSFORMATION,
            PipelineStage.FEAT_INFERENCE,
            PipelineStage.INFERENCE,
            PipelineStage.DETECTION,
        ),
        checkpoint_hash=threshold.checkpoint_hash,
        experiment_class=ExperimentClass.CAUSAL_MAIN,
        transductive_status=TransductiveStatus.CAUSAL,
        frozen_at=frozen_at,
        code_commit=(validation_run / "git_commit.txt").read_text().strip(),
        approved_splits=frozenset({DataSplit.VALIDATION}),
    )
    assert_deployable_payload(threshold.model_dump(mode="json"))
    assert_deployable_payload(config.model_dump(mode="json"))

    output.mkdir()
    checkpoint_out = output / "checkpoints" / "velox" / "frozen_validation_checkpoint"
    checkpoint_out.parent.mkdir(parents=True)
    shutil.copytree(checkpoint_source, checkpoint_out)
    featurizer_out = output / "featurizers" / "velox" / "word2vec"
    featurizer_out.parent.mkdir(parents=True)
    shutil.copytree(featurizer_models[0], featurizer_out)
    (output / "threshold_catalog.json").write_text(
        json.dumps([threshold.model_dump(mode="json")], indent=2, sort_keys=True) + "\n"
    )
    (output / "approved_config_catalog.json").write_text(
        json.dumps([config.model_dump(mode="json")], indent=2, sort_keys=True) + "\n"
    )
    availability = {
        "schema_version": "pids-availability-v1",
        "pids_id": "velox",
        "variant_id": "default",
        "source_config_id": config.source_config_id,
        "dataset_id": "CADETS_E3",
        "status": "available_for_validation",
        "checkpoint_hash": threshold.checkpoint_hash,
        "checkpoint_relative_path": checkpoint_out.relative_to(output).as_posix(),
        "featurizer_relative_path": featurizer_out.relative_to(output).as_posix(),
        "threshold_id": threshold.threshold_id,
        "held_out_approved": False,
        "deployment_approved": False,
        "unavailable_reason_for_held_out": "full agent-level validation campaign set is not yet complete",
    }
    assert_deployable_payload(availability)
    (output / "availability_manifest.json").write_text(
        json.dumps(availability, indent=2, sort_keys=True) + "\n"
    )
    manifest = {
        "schema_version": "pre-sft-freeze-v1",
        "status": "validation_candidate_frozen",
        "created_at": frozen_at.isoformat(),
        "source_pids_run_id": pids_run.name,
        "source_validation_run_id": validation_run.name,
        "checkpoint_hash": tree_hash(checkpoint_out),
        "featurizer_hash": tree_hash(featurizer_out),
        "threshold_id": threshold.threshold_id,
        "sft_dataset_included": False,
        "sft_status": "BLOCKED_BY_SFT_DATASET",
        "static_ltm_included": False,
        "formal_performance_claim": False,
    }
    assert_deployable_payload(manifest)
    (output / "bundle_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
