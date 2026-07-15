"""Create and run a complete Agent experiment lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Mapping

import yaml

from .artifact_manager import ArtifactManager
from .result_tracker import ResultTracker


class ExperimentRunner:
    def __init__(self, run_root: Path) -> None:
        self.artifacts = ArtifactManager(run_root)

    def run(
        self,
        run_id: str,
        resolved_config: Mapping[str, Any],
        workload: Callable[[Path], Mapping[str, Any]],
    ) -> Path:
        run_dir = self.artifacts.create_run(run_id)
        (run_dir / "config.yaml").write_text(
            yaml.safe_dump(dict(resolved_config), sort_keys=True), encoding="utf-8"
        )
        tracker = ResultTracker(run_dir)
        tracker.transition("running")
        try:
            result = workload(run_dir)
            self.artifacts.write_json(run_dir / "metrics" / "result.json", result)
        except Exception:
            tracker.transition("failed")
            raise
        tracker.transition("completed")
        return run_dir
