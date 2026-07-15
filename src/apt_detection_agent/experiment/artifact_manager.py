"""Manage Agent run outputs only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


class ArtifactManager:
    def __init__(self, run_root: Path) -> None:
        self.run_root = run_root.resolve()

    def create_run(self, run_id: str) -> Path:
        if not run_id or not all(char.isalnum() or char in "_-" for char in run_id):
            raise ValueError("unsafe run_id")
        self.run_root.mkdir(parents=True, exist_ok=True)
        run_dir = (self.run_root / run_id).resolve()
        if run_dir.parent != self.run_root:
            raise ValueError("run path escaped root")
        run_dir.mkdir(exist_ok=False)
        for name in ("logs", "execution_traces", "metrics", "reports"):
            (run_dir / name).mkdir()
        return run_dir

    @staticmethod
    def write_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
