#!/usr/bin/env python3
"""Validate Phase 0 governance artifacts.

Requirements: REQ-GOV-001, REQ-GOV-003, REQ-GIT-003.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PIDS_SHA = "32602734bc9f896be5fc0f03f0a185c967cd6624"
REQUIRED_FILES = (
    "AGENTS.md",
    "README.md",
    "pyproject.toml",
    "docs/design/APT_Detection_Agent_Design_v0.4.md",
    "docs/plans/IMPLEMENTATION_PLAN.md",
    "docs/plans/REQUIREMENT_TRACEABILITY.md",
    "docs/data_protocol.md",
    "docs/experiment_protocol.md",
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]
    if missing:
        fail(f"missing required files: {', '.join(missing)}")

    matrix = (ROOT / "docs/plans/REQUIREMENT_TRACEABILITY.md").read_text()
    plan = (ROOT / "docs/plans/IMPLEMENTATION_PLAN.md").read_text()
    ids = set(re.findall(r"REQ-[A-Z]+-\d{3}", matrix))
    if len(ids) < 25:
        fail(f"requirement matrix unexpectedly small: {len(ids)} IDs")
    if not set(re.findall(r"REQ-[A-Z]+-\d{3}", plan)).issubset(ids):
        fail("implementation plan references unknown requirement IDs")

    actual_sha = subprocess.run(
        ["git", "-C", str(ROOT / "PIDSMaker"), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual_sha != EXPECTED_PIDS_SHA:
        fail(f"PIDSMaker SHA is {actual_sha}, expected {EXPECTED_PIDS_SHA}")

    submodule_diff = subprocess.run(
        ["git", "-C", str(ROOT / "PIDSMaker"), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if submodule_diff:
        fail("PIDSMaker working tree is dirty")

    print(f"OK: {len(ids)} requirement IDs; PIDSMaker {actual_sha}")


if __name__ == "__main__":
    main()
