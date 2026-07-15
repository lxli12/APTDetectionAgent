from apt_detection_agent.schemas import ToolRequest, ToolStatus
from apt_detection_agent.tools import Tool, ToolExecutor, ToolRegistry


def test_tool_executor_validates_before_dispatch():
    registry = ToolRegistry()
    registry.register(Tool("inspect", "inspect evidence", frozenset({"id"}), lambda args: {"id": args["id"]}))
    executor = ToolExecutor(registry)
    rejected = executor.execute(ToolRequest("r1", "inspect", {}))
    assert rejected.status is ToolStatus.REJECTED
    success = executor.execute(ToolRequest("r2", "inspect", {"id": "e1"}))
    assert success.output == {"id": "e1"}
