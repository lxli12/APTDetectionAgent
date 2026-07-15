"""Bounded Agent action contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


class ActionType(str, Enum):
    CALL_TOOL = "call_tool"
    UPDATE_MEMORY = "update_memory"
    FINISH = "finish"


@dataclass(frozen=True, slots=True)
class Action:
    action_id: str
    action_type: ActionType
    rationale: str
    tool_name: str | None = None
    arguments: Mapping[str, Any] = field(default_factory=dict)
    memory_content: str | None = None

    def __post_init__(self) -> None:
        if not self.action_id or not self.rationale.strip():
            raise ValueError("action_id and rationale are required")
        if self.action_type is ActionType.CALL_TOOL and not self.tool_name:
            raise ValueError("tool action requires tool_name")
        if self.action_type is not ActionType.CALL_TOOL and self.tool_name:
            raise ValueError("non-tool action cannot name a tool")
        if self.action_type is ActionType.UPDATE_MEMORY and not self.memory_content:
            raise ValueError("memory update requires content")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["action_type"] = self.action_type.value
        return value
