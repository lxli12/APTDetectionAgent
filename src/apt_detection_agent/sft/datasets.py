"""Deterministic loading of canonical demonstration datasets.

Requirements: REQ-SFT-001..004, REQ-REPRO-001..003.
"""

from pathlib import Path

from .models import CanonicalDemonstrationTrajectory


def load_trajectory_jsonl(path: Path) -> tuple[CanonicalDemonstrationTrajectory, ...]:
    """Load an ordered canonical JSONL corpus and reject empty inputs."""

    records = tuple(
        CanonicalDemonstrationTrajectory.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    )
    if not records:
        raise ValueError("canonical demonstration dataset is empty")
    return records
