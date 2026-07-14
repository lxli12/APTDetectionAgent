#!/usr/bin/env python3
"""Validate the future SFT trainer interface without fabricating training.

Requirements: REQ-SFT-001..004, REQ-ARTIFACT-002, REQ-REPRO-001..003.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apt_detection_agent.sft import (
    BLOCKED_BY_SFT_DATASET,
    SFTDataset,
    SFTDatasetValidator,
    SFTTrainingConfig,
    SFTTrainingResult,
    FrozenSFTDataset,
    FrozenSFTDatasetValidator,
)


def _write_once(path: Path, result: SFTTrainingResult) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(result.model_dump_json(indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    config = SFTTrainingConfig.model_validate_json(args.config.read_text())
    if not args.dataset.is_file():
        _write_once(
            args.result,
            SFTTrainingResult(
                status=BLOCKED_BY_SFT_DATASET,
                dataset_id=config.dataset_id,
                config_id=config.config_id,
                reason="No sanitized, versioned SFT trajectory dataset exists at the approved path.",
                dry_run=config.dry_run,
            ),
        )
        return 3

    raw_dataset = json.loads(args.dataset.read_text())
    manifest_version = raw_dataset.get("manifest", {}).get("schema_version")
    if manifest_version == "frozen-sft-dataset-manifest-v2":
        dataset = FrozenSFTDataset.model_validate(raw_dataset)
        FrozenSFTDatasetValidator.validate(dataset)
    else:
        dataset = SFTDataset.model_validate(raw_dataset)
        SFTDatasetValidator.validate(dataset)
    if (
        config.dataset_id != dataset.manifest.dataset_id
        or config.dataset_hash != dataset.manifest.dataset_hash
    ):
        raise ValueError("training config does not match the immutable dataset manifest")
    if config.dry_run:
        _write_once(
            args.result,
            SFTTrainingResult(
                status="dry_run_validated",
                dataset_id=config.dataset_id,
                config_id=config.config_id,
                reason="Schemas, hashes, split isolation, and trainer inputs validated; no weights updated.",
                dry_run=True,
            ),
        )
        return 0
    if dataset.manifest.synthetic_only or not dataset.manifest.formal_training_approved:
        _write_once(
            args.result,
            SFTTrainingResult(
                status=BLOCKED_BY_SFT_DATASET,
                dataset_id=config.dataset_id,
                config_id=config.config_id,
                reason="Dataset is synthetic or has not passed formal deployability approval.",
            ),
        )
        return 3

    _write_once(
        args.result,
        SFTTrainingResult(
            status="ready_for_versioned_trainer_backend",
            dataset_id=config.dataset_id,
            config_id=config.config_id,
            reason="Interface validation passed; a separately approved trainer backend is required.",
        ),
    )
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
