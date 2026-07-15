"""Validate and execute logical tools with sanitized failures."""

from __future__ import annotations

from apt_detection_agent.schemas import ToolRequest, ToolResult, ToolStatus

from .tool_registry import ToolRegistry


class ToolExecutor:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(self, request: ToolRequest) -> ToolResult:
        try:
            tool = self.registry.get(request.tool_name)
            tool.validate(request.arguments)
        except (KeyError, ValueError):
            return ToolResult(request.request_id, request.tool_name, ToolStatus.REJECTED, error_code="invalid_tool_request")
        try:
            output = tool.handler(request.arguments)
            return ToolResult(request.request_id, request.tool_name, ToolStatus.SUCCEEDED, output=dict(output))
        except Exception:
            return ToolResult(request.request_id, request.tool_name, ToolStatus.FAILED, error_code="tool_execution_failed")
