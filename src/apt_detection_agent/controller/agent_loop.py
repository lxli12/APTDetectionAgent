"""Observe/Think/Act/Reflect orchestration loop."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from apt_detection_agent.memory import MemoryManager
from apt_detection_agent.schemas import (
    Action, ActionType, ExecutionTrace, MemoryRecord, Observation, ToolRequest,
)
from apt_detection_agent.tools import ToolExecutor, ToolRegistry

from .action_validator import ActionValidator
from .execution_trace_recorder import ExecutionTraceRecorder


class Policy(Protocol):
    def propose(self, observation: Observation, available_tools: tuple[str, ...]) -> Action: ...


class AgentLoop:
    def __init__(
        self,
        policy: Policy,
        tools: ToolRegistry,
        executor: ToolExecutor,
        memory: MemoryManager,
        recorder: ExecutionTraceRecorder,
        validator: ActionValidator | None = None,
    ) -> None:
        self.policy = policy
        self.tools = tools
        self.executor = executor
        self.memory = memory
        self.recorder = recorder
        self.validator = validator or ActionValidator()

    def step(self, observation: Observation, memory_namespace: str) -> ExecutionTrace:
        available = self.tools.names()
        action = self.policy.propose(observation, available)
        self.validator.validate(action, available)
        tool_result = None
        memory_update_id = None
        if action.action_type is ActionType.CALL_TOOL:
            tool_result = self.executor.execute(ToolRequest(
                request_id=action.action_id,
                tool_name=action.tool_name or "",
                arguments=action.arguments,
            ))
        elif action.action_type is ActionType.UPDATE_MEMORY:
            memory_update_id = str(uuid4())
            self.memory.remember(MemoryRecord(
                memory_id=memory_update_id,
                namespace=memory_namespace,
                content=action.memory_content or "",
                evidence_ids=(observation.observation_id,),
                created_at=datetime.now(timezone.utc),
            ))
        trace = ExecutionTrace(
            trace_id=str(uuid4()),
            observation=observation,
            action=action,
            tool_result=tool_result,
            memory_update_id=memory_update_id,
            recorded_at=datetime.now(timezone.utc),
        )
        self.recorder.append(trace)
        return trace
