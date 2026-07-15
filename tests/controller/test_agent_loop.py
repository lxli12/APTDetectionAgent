from datetime import timedelta
import json

from apt_detection_agent.controller.execution_trace_recorder import ExecutionTraceRecorder
from apt_detection_agent.schemas import ExecutionTrace, PathDecision, ToolResult, ToolStatus, UsageAccounting
from tests.test_contracts import NOW, action, commitment, observation


def test_execution_trace_recorder_writes_replayable_contract(tmp_path):
    trace = ExecutionTrace(
        "trace-1", "cadets-e3", "w-1", observation(), PathDecision.FAST_PATH, (),
        None, None, action(),
        ToolResult("action-1", "run_current_pids", ToolStatus.SUCCEEDED, {"run_id": "run-1"}),
        None, commitment(), UsageAccounting(0, 0, 0, 1, 1.0), NOW + timedelta(minutes=16),
    )
    trace_path = tmp_path / "execution_traces" / "trace.jsonl"
    ExecutionTraceRecorder(trace_path).append(trace)
    restored = ExecutionTrace.from_dict(json.loads(trace_path.read_text()))
    assert restored == trace
