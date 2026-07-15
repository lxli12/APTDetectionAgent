"""Serializable Observe/Think/Act/Reflect trace contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Mapping

from .action_schema import Action
from .observation_schema import Observation
from .tool_schema import ToolResult


@dataclass(frozen=True, slots=True)
class ExecutionTrace:
    trace_id: str
    observation: Observation
    action: Action
    tool_result: ToolResult | None
    memory_update_id: str | None
    recorded_at: datetime

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = asdict(self)
        value["observation"] = self.observation.to_dict()
        value["action"] = self.action.to_dict()
        value["tool_result"] = self.tool_result.to_dict() if self.tool_result else None
        value["recorded_at"] = self.recorded_at.isoformat()
        return value
