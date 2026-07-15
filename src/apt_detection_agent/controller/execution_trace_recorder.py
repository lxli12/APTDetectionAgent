"""Append-only JSONL execution trace recorder."""

from __future__ import annotations

import json
from pathlib import Path

from apt_detection_agent.schemas import ExecutionTrace


class ExecutionTraceRecorder:
    def __init__(self, path: Path) -> None:
        self.path = path

    def append(self, trace: ExecutionTrace) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(trace.to_dict(), sort_keys=True) + "\n")
