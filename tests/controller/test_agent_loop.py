from datetime import datetime, timezone

from apt_detection_agent.controller import AgentLoop
from apt_detection_agent.controller.execution_trace_recorder import ExecutionTraceRecorder
from apt_detection_agent.memory import InMemoryStore, MemoryManager
from apt_detection_agent.schemas import Action, ActionType, Observation, ToolStatus
from apt_detection_agent.tools import Tool, ToolExecutor, ToolRegistry


class ToolPolicy:
    def propose(self, observation, available_tools):
        return Action("a1", ActionType.CALL_TOOL, "inspect", "inspect", {"id": "e1"})


def test_agent_loop_records_typed_trace(tmp_path):
    registry = ToolRegistry()
    registry.register(Tool("inspect", "inspect", frozenset({"id"}), lambda args: args))
    trace_path = tmp_path / "execution_traces" / "trace.jsonl"
    loop = AgentLoop(
        ToolPolicy(), registry, ToolExecutor(registry),
        MemoryManager(InMemoryStore()), ExecutionTraceRecorder(trace_path),
    )
    observation = Observation("o1", "w1", datetime.now(timezone.utc))
    trace = loop.step(observation, "case-a")
    assert trace.tool_result.status is ToolStatus.SUCCEEDED
    assert trace_path.read_text().count("\n") == 1
