"""Monotonic Agent experiment status tracker."""

from __future__ import annotations

from pathlib import Path

from .artifact_manager import ArtifactManager


class ResultTracker:
    _allowed = {
        "created": {"running", "failed"},
        "running": {"completed", "failed"},
        "completed": set(),
        "failed": set(),
    }

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.status = "created"
        self._persist()

    def transition(self, status: str) -> None:
        if status not in self._allowed[self.status]:
            raise ValueError(f"invalid experiment transition: {self.status} -> {status}")
        self.status = status
        self._persist()

    def _persist(self) -> None:
        ArtifactManager.write_json(self.run_dir / "status.json", {"status": self.status})
