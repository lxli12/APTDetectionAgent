#!/usr/bin/env python3
"""Run one private evaluation request and emit only sanitized public feedback.

Requirements: REQ-LABEL-001..004, REQ-EVAL-001..007, REQ-DB-001..003.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from apt_detection_agent.evaluation.ipc import EvaluatorIPCPaths
from apt_detection_agent.evaluation.metrics import HiddenEvaluationInput, HiddenEvaluator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-input", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--public-feedback", type=Path, required=True)
    arguments = parser.parse_args()
    paths = EvaluatorIPCPaths.from_environment(
        private_input=arguments.private_input,
        private_output=arguments.private_output,
        public_feedback=arguments.public_feedback,
    )
    if paths.public_feedback.exists():
        raise FileExistsError(paths.public_feedback)
    request = HiddenEvaluationInput.model_validate_json(paths.private_input.read_text())
    feedback = HiddenEvaluator().evaluate_to_private_artifact(request, paths.private_output)
    paths.public_feedback.parent.mkdir(parents=True, exist_ok=True)
    paths.public_feedback.write_text(feedback.model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
