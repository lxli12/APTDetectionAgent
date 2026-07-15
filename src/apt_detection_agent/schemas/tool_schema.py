"""Tool request and result contracts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping


class ToolStatus(str, Enum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ToolRequest:
    request_id: str
    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolResult:
    request_id: str
    tool_name: str
    status: ToolStatus
    output: Mapping[str, Any] = field(default_factory=dict)
    error_code: str | None = None

    def __post_init__(self) -> None:
        if self.status is ToolStatus.SUCCEEDED and self.error_code:
            raise ValueError("successful tool result cannot carry error_code")
        if self.status is not ToolStatus.SUCCEEDED and not self.error_code:
            raise ValueError("non-successful tool result requires error_code")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value
