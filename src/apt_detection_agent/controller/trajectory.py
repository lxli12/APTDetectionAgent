"""Append-only local trajectory JSONL.

Requirements: REQ-REPRO-001..002, REQ-LABEL-004.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field, model_validator

from apt_detection_agent.schemas import AgentAction, Observation, Prediction, ToolResult
from apt_detection_agent.schemas.common import Identifier, StrictModel, Timestamp


class TrajectoryStep(StrictModel):
    trajectory_id: Identifier
    step_number: int = Field(ge=0)
    observation: Observation
    prediction: Prediction
    action: AgentAction
    tool_results: tuple[ToolResult, ...]
    reflection: str
    started_at: Timestamp
    ended_at: Timestamp

    @model_validator(mode="after")
    def valid_timing(self) -> "TrajectoryStep":
        if self.ended_at < self.started_at:
            raise ValueError("trajectory step end cannot precede start")
        return self


class TrajectoryLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, step: TrajectoryStep) -> None:
        if self.path.exists():
            last_number = None
            with self.path.open() as handle:
                for line in handle:
                    if line.strip():
                        last_number = json.loads(line)["step_number"]
            if last_number is not None and step.step_number != last_number + 1:
                raise ValueError("trajectory steps must be append-only and contiguous")
        elif step.step_number != 0:
            raise ValueError("new trajectory must start at step zero")
        with self.path.open("a") as handle:
            handle.write(step.model_dump_json() + "\n")
