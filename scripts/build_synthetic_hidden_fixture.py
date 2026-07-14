#!/usr/bin/env python3
"""Create the private Phase 9 fixture under the evaluator-only root.

Requirements: REQ-LABEL-001..004, REQ-EVAL-001..006, REQ-SFT-003.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from apt_detection_agent.evaluation.fixtures import build_synthetic_hidden_input


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args()
    private_root_text = os.environ.get("HIDDEN_EVALUATOR_PRIVATE_ROOT")
    if not private_root_text:
        raise ValueError("HIDDEN_EVALUATOR_PRIVATE_ROOT is required")
    private_root = Path(private_root_text).resolve()
    output = args.private_output.resolve()
    if output.parent != private_root:
        raise ValueError("synthetic private fixture must be a direct child of the private root")
    if output.exists():
        raise FileExistsError(output)
    private_root.mkdir(parents=True, exist_ok=True)
    output.write_text(build_synthetic_hidden_input().model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
