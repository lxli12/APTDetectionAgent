#!/usr/bin/env python3
"""Finalize a run from sanitized feedback without reading hidden metrics.

Requirements: REQ-LABEL-001..004, REQ-EVAL-006, REQ-REPRO-001..002.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from apt_detection_agent.evaluation.reporting import finalize_public_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    finalize_public_report(
        run_dir=args.run_dir,
        feedback_path=args.feedback,
        project_root=args.project_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
