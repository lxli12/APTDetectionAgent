"""Versioned typed envelopes for constrained tool execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from ._serialization import deterministic_json, require_keys, require_nonempty, require_object, versioned_dict
from .sanitization import assert_deployable


class ToolStatus(str, Enum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ToolRequest:
    request_id: str
    tool_name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    candidate_set_version: str = "1.0"

    def __post_init__(self) -> None:
        require_nonempty(self.request_id, "tool request_id")
        require_nonempty(self.tool_name, "tool_name")
        require_nonempty(self.candidate_set_version, "candidate_set_version")
        assert_deployable(self.arguments)

    def to_dict(self) -> dict[str, Any]:
        return versioned_dict(self)

    def to_json(self) -> str:
        return deterministic_json(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ToolRequest":
        data = require_object(raw, "ToolRequest")
        required = ("request_id", "tool_name", "arguments", "candidate_set_version")
        require_keys(data, required=required, name="ToolRequest", versioned=True)
        return cls(str(data["request_id"]), str(data["tool_name"]), dict(require_object(data["arguments"], "arguments")), str(data["candidate_set_version"]))


@dataclass(frozen=True, slots=True)
class ToolResult:
    request_id: str
    tool_name: str
    status: ToolStatus
    output: Mapping[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False

    def __post_init__(self) -> None:
        require_nonempty(self.request_id, "tool result request_id")
        require_nonempty(self.tool_name, "tool_name")
        if self.status is ToolStatus.SUCCEEDED and (self.error_code or self.error_message):
            raise ValueError("successful tool result cannot carry an error")
        if self.status is not ToolStatus.SUCCEEDED and not self.error_code:
            raise ValueError("non-successful tool result requires error_code")
        assert_deployable(self.output)
        if self.error_message:
            assert_deployable(self.error_message)

    def to_dict(self) -> dict[str, Any]:
        return versioned_dict(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ToolResult":
        data = require_object(raw, "ToolResult")
        required = (
            "request_id", "tool_name", "status", "output", "error_code",
            "error_message", "retryable",
        )
        require_keys(data, required=required, name="ToolResult", versioned=True)
        return cls(
            str(data["request_id"]), str(data["tool_name"]), ToolStatus(data["status"]),
            dict(require_object(data["output"], "output")),
            None if data["error_code"] is None else str(data["error_code"]),
            None if data["error_message"] is None else str(data["error_message"]),
            bool(data["retryable"]),
        )
