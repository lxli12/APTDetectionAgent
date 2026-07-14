#!/usr/bin/env python3
"""Validate the frozen validation assets consumed by pre-SFT stages."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def load(path: Path) -> object:
    return json.loads(path.read_text())


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        raise ValueError("frozen asset tree is empty")
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def child(bundle: Path, relative: object) -> Path:
    path = (bundle / str(relative)).resolve()
    path.relative_to(bundle)
    return path


def validate(bundle: Path) -> dict[str, object]:
    root_text = os.environ.get("APT_PRE_SFT_BUNDLE_ROOT")
    bundle = bundle.resolve()
    if not root_text or bundle.parent != Path(root_text).resolve():
        raise ValueError("bundle escaped APT_PRE_SFT_BUNDLE_ROOT")
    manifest = load(bundle / "bundle_manifest.json")
    availability = load(bundle / "availability_manifest.json")
    thresholds = load(bundle / "threshold_catalog.json")
    configs = load(bundle / "approved_config_catalog.json")
    if not all(isinstance(item, dict) for item in (manifest, availability)):
        raise ValueError("bundle manifests must be objects")
    if not isinstance(thresholds, list) or len(thresholds) != 1:
        raise ValueError("expected exactly one frozen validation threshold")
    if not isinstance(configs, list) or len(configs) != 1:
        raise ValueError("expected exactly one frozen validation config")
    threshold, config = thresholds[0], configs[0]
    checkpoint = child(bundle, availability["checkpoint_relative_path"])
    featurizer = child(bundle, availability["featurizer_relative_path"])
    checkpoint_hash = tree_hash(checkpoint)
    if (
        manifest.get("status") != "validation_candidate_frozen"
        or manifest.get("sft_dataset_included") is not False
        or manifest.get("static_ltm_included") is not False
        or manifest.get("formal_performance_claim") is not False
        or availability.get("status") != "available_for_validation"
        or availability.get("held_out_approved") is not False
        or availability.get("deployment_approved") is not False
        or checkpoint_hash != manifest.get("checkpoint_hash")
        or tree_hash(featurizer) != manifest.get("featurizer_hash")
        or threshold.get("checkpoint_hash") != checkpoint_hash
        or threshold.get("source_split") != "validation"
        or config.get("checkpoint_hash") != checkpoint_hash
        or config.get("approved_splits") != ["validation"]
        or config.get("experiment_class") != "causal_main"
        or config.get("transductive_status") != "causal"
        or config.get("source_config_id") != availability.get("source_config_id")
        or config.get("dataset_id") != availability.get("dataset_id")
    ):
        raise ValueError("pre-SFT bundle provenance is invalid")
    return {
        "schema_version": "pre-sft-validation-v1",
        "status": "succeeded",
        "bundle_id": bundle.name,
        "pids_id": availability["pids_id"],
        "source_config_id": availability["source_config_id"],
        "dataset_id": availability["dataset_id"],
        "checkpoint_hash": checkpoint_hash,
        "threshold_id": threshold["threshold_id"],
        "approved_splits": ["validation"],
        "held_out_approved": False,
        "deployment_approved": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(validate(args.bundle), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
