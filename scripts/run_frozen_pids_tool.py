#!/usr/bin/env python3
"""Execute one structured, frozen PIDSMaker detection request.

Requirements: REQ-CAUSAL-001..004, REQ-CONFIG-002..003,
REQ-TOOL-001..005, REQ-ARTIFACT-001..003, REQ-LABEL-001..004.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pidsmaker_causal_runner as causal
import pidsmaker_stage_runner as stage


def load_object(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"expected object: {path}")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_config_id")
    parser.add_argument("dataset_id")
    parser.add_argument("--pidsmaker-root", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--frozen-bundle", required=True)
    parser.add_argument("--checkpoint-hash", required=True)
    parser.add_argument("--test-window-start-ns", type=int, required=True)
    parser.add_argument("--test-window-end-ns", type=int, required=True)
    parser.add_argument("--window-size-seconds", type=int, required=True)
    parser.add_argument("--override", action="append", default=[])
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args()


def namespace(args: argparse.Namespace) -> Namespace:
    bundle = Path(args.frozen_bundle).resolve()
    availability = load_object(bundle / "availability_manifest.json")
    references = availability.get("reference_windows")
    if not isinstance(references, dict):
        raise ValueError("bundle lacks frozen train/validation reference windows")
    train = references.get("train")
    val = references.get("val")
    if not isinstance(train, dict) or not isinstance(val, dict):
        raise ValueError("bundle reference windows are malformed")
    zone = ZoneInfo("America/New_York")
    test_date = datetime.fromtimestamp(args.test_window_start_ns / 1_000_000_000, zone)
    return Namespace(
        phase="infer",
        source_config_id=args.source_config_id,
        dataset_id=args.dataset_id,
        pidsmaker_root=args.pidsmaker_root,
        artifact_dir=args.artifact_dir,
        frozen_bundle=args.frozen_bundle,
        checkpoint_hash=args.checkpoint_hash,
        override=args.override,
        cpu=args.cpu,
        window_size_seconds=args.window_size_seconds,
        train_date=str(train["date"]),
        train_window_start_ns=int(train["start_ns"]),
        train_window_end_ns=int(train["end_ns"]),
        val_date=str(val["date"]),
        val_window_start_ns=int(val["start_ns"]),
        val_window_end_ns=int(val["end_ns"]),
        test_date=test_date.date().isoformat(),
        test_window_start_ns=args.test_window_start_ns,
        test_window_end_ns=args.test_window_end_ns,
        stop_after="feat_inference",
    )


def main() -> int:
    args = parse_args()
    request = namespace(args)
    environment = dict(os.environ)
    stage.run(request, environment)
    frozen = stage.validate_frozen_bundle(
        Path(args.frozen_bundle),
        environment,
        expected_source_config_id=args.source_config_id,
        expected_dataset_id=args.dataset_id,
        expected_overrides=args.override,
    )
    availability = frozen["availability"]
    checkpoint_manifest = {
        "schema_version": "apt-pids-checkpoint-v1",
        "source_config_id": args.source_config_id,
        "dataset_id": args.dataset_id,
        "selection_split": "frozen_validation_bundle",
        "checkpoint_hash": availability["checkpoint_hash"],
        "external_bundle_id": Path(args.frozen_bundle).resolve().name,
    }
    artifact = Path(args.artifact_dir).resolve()
    (artifact / "checkpoint_manifest.json").write_text(
        json.dumps(checkpoint_manifest, indent=2, sort_keys=True) + "\n"
    )
    summary = causal.run(request, environment)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
