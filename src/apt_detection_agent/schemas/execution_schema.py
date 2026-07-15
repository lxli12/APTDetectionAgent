"""Expanded, replayable per-construction-graph execution trace contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping

from ._serialization import (
    deterministic_json, nested_versioned, parse_datetime, require_keys,
    require_nonempty, require_nonnegative, require_object, versioned_dict,
)
from .action_schema import Action, PathDecision
from .memory_schema import MemoryReadRequest, MemoryUseDecision, MemoryWriteRequest
from .observation_schema import Observation
from .pids_schema import CommittedDetection
from .sanitization import assert_deployable
from .tool_schema import ToolResult


class TriggerReason(str, Enum):
    SCORE_DISTRIBUTION_SHIFT = "score_distribution_shift"
    ALERT_VOLUME_ANOMALY = "alert_volume_anomaly"
    CONSECUTIVE_STATE_CHANGE = "consecutive_state_change"
    OOM = "oom"
    TIMEOUT = "timeout"
    DEGENERATE_OUTPUT = "degenerate_output"
    PERIODIC_CHECKPOINT = "periodic_checkpoint"
    MEMORY_RISK_CONDITION = "memory_risk_condition"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass(frozen=True, slots=True)
class UsageAccounting:
    input_tokens: int
    output_tokens: int
    llm_calls: int
    pidsmaker_calls: int
    runtime_seconds: float

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens", "llm_calls", "pidsmaker_calls", "runtime_seconds"):
            require_nonnegative(getattr(self, name), name)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "UsageAccounting":
        required = ("input_tokens", "output_tokens", "llm_calls", "pidsmaker_calls", "runtime_seconds")
        require_keys(data, required=required, name="UsageAccounting")
        return cls(int(data["input_tokens"]), int(data["output_tokens"]), int(data["llm_calls"]), int(data["pidsmaker_calls"]), float(data["runtime_seconds"]))


@dataclass(frozen=True, slots=True)
class ExecutionTrace:
    trace_id: str
    scenario_id: str
    window_id: str
    observation: Observation
    path_decision: PathDecision
    trigger_reasons: tuple[TriggerReason, ...]
    memory_read_request: MemoryReadRequest | None
    memory_use_decision: MemoryUseDecision | None
    action: Action
    tool_result: ToolResult | None
    memory_write_request: MemoryWriteRequest | None
    committed_detection: CommittedDetection
    usage: UsageAccounting
    recorded_at: datetime

    def __post_init__(self) -> None:
        for name in ("trace_id", "scenario_id", "window_id"):
            require_nonempty(getattr(self, name), name)
        if self.recorded_at.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware")
        if self.scenario_id != self.observation.environment.scenario_id:
            raise ValueError("trace scenario does not match observation")
        if self.window_id != self.observation.window_id or self.window_id != self.committed_detection.window_id:
            raise ValueError("trace window, observation, and commitment must match")
        if self.path_decision is not self.action.path_decision:
            raise ValueError("trace path decision must match action")
        if self.path_decision is PathDecision.FAST_PATH:
            if self.memory_read_request or self.memory_use_decision:
                raise ValueError("fast path cannot contain memory read/use decisions")
            if self.usage.llm_calls:
                raise ValueError("fast path cannot account for main LLM calls")
        if self.memory_use_decision and not self.memory_read_request:
            raise ValueError("memory use decision requires a read request")
        if self.memory_use_decision and self.memory_read_request:
            if self.memory_use_decision.request_id != self.memory_read_request.request_id:
                raise ValueError("memory read/use request IDs must match")
        adopted = {
            item.memory_id for item in (self.memory_use_decision.decisions if self.memory_use_decision else ())
            if item.disposition.value == "use"
        }
        if set(self.action.adopted_memory_ids) - adopted:
            raise ValueError("action adopted memory IDs must have explicit use decisions")
        assert_deployable(self)

    @property
    def memory_update_id(self) -> str | None:
        if self.memory_write_request and self.memory_write_request.record:
            return self.memory_write_request.record.memory_id
        return None

    def to_dict(self) -> dict[str, Any]:
        return versioned_dict(self)

    def to_json(self) -> str:
        return deterministic_json(self)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ExecutionTrace":
        data = require_object(raw, "ExecutionTrace")
        required = (
            "trace_id", "scenario_id", "window_id", "observation", "path_decision",
            "trigger_reasons", "memory_read_request", "memory_use_decision", "action",
            "tool_result", "memory_write_request", "committed_detection", "usage", "recorded_at",
        )
        require_keys(data, required=required, name="ExecutionTrace", versioned=True)
        return cls(
            trace_id=str(data["trace_id"]), scenario_id=str(data["scenario_id"]),
            window_id=str(data["window_id"]),
            observation=Observation.from_dict(nested_versioned(data["observation"], "observation")),
            path_decision=PathDecision(data["path_decision"]),
            trigger_reasons=tuple(TriggerReason(item) for item in data["trigger_reasons"]),
            memory_read_request=None if data["memory_read_request"] is None else MemoryReadRequest.from_dict(nested_versioned(data["memory_read_request"], "memory_read_request")),
            memory_use_decision=None if data["memory_use_decision"] is None else MemoryUseDecision.from_dict(nested_versioned(data["memory_use_decision"], "memory_use_decision")),
            action=Action.from_dict(nested_versioned(data["action"], "action")),
            tool_result=None if data["tool_result"] is None else ToolResult.from_dict(nested_versioned(data["tool_result"], "tool_result")),
            memory_write_request=None if data["memory_write_request"] is None else MemoryWriteRequest.from_dict(nested_versioned(data["memory_write_request"], "memory_write_request")),
            committed_detection=CommittedDetection.from_dict(nested_versioned(data["committed_detection"], "committed_detection")),
            usage=UsageAccounting.from_dict(require_object(data["usage"], "usage")),
            recorded_at=parse_datetime(data["recorded_at"], "recorded_at"),
        )
