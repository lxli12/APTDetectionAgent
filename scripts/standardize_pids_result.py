#!/usr/bin/env python3
"""Freeze a validation threshold and emit a deployment-visible PIDS result."""

from __future__ import annotations

import argparse
from pathlib import Path

from apt_detection_agent.pidsmaker.results import (
    calibrate_validation_quantile,
    standardize_frozen_test_scores,
)
from apt_detection_agent.schemas import assert_deployable_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pids-run", type=Path, required=True)
    parser.add_argument("--threshold-output", type=Path, required=True)
    parser.add_argument("--observation-output", type=Path, required=True)
    parser.add_argument("--validation-quantile", type=float, default=0.999)
    args = parser.parse_args()
    if args.threshold_output.exists() or args.observation_output.exists():
        raise FileExistsError("standardized outputs are append-only")
    if args.threshold_output.parent != args.observation_output.parent:
        raise ValueError("threshold and observation must share an executor-owned output root")
    threshold = calibrate_validation_quantile(
        args.pids_run, quantile=args.validation_quantile
    )
    result = standardize_frozen_test_scores(args.pids_run, threshold)
    threshold_payload = threshold.model_dump(mode="json")
    result_payload = result.model_dump(mode="json")
    assert_deployable_payload(threshold_payload)
    assert_deployable_payload(result_payload)
    args.threshold_output.write_text(threshold.model_dump_json(indent=2) + "\n")
    args.observation_output.write_text(result.model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
