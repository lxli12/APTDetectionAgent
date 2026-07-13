"""Typed Agent tool and executor audit contracts.

Requirements: REQ-TOOL-001..005, REQ-LABEL-004, REQ-REPRO-001.
"""

from __future__ import annotations

from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from pydantic import Field, JsonValue, field_validator, model_validator

from .common import Identifier, PipelineStage, RunStatus, Sha256, StrictModel, Timestamp
from .evaluation import assert_deployable_payload


class ToolName(str, Enum):
    LIST_PIDS_CAPABILITIES = "list_pids_capabilities"
    INSPECT_PIDS_AVAILABILITY = "inspect_pids_availability"
    VALIDATE_PIDS_REQUEST = "validate_pids_request"
    SELECT_APPROVED_CONFIG = "select_approved_config"
    RUN_PIDS_DETECTION = "run_pids_detection"
    RUN_PARALLEL_PIDS_DETECTION = "run_parallel_pids_detection"
    INSPECT_DETECTION_RESULT = "inspect_detection_result"
    COMPARE_PIDS_RESULTS = "compare_pids_results"
    BACKWARD_TRACE = "backward_trace"
    FORWARD_TRACE = "forward_trace"


class ActionType(str, Enum):
    COMMIT_FAST_PATH = "commit_fast_path"
    INVOKE_SLOW_DIAGNOSIS = "invoke_slow_diagnosis"
    RUN_TOOL = "run_tool"
    SCHEDULE_RECONFIGURATION = "schedule_reconfiguration"
    NO_CHANGE = "no_change"


FORBIDDEN_REQUEST_KEYS = frozenset(
    {
        "argv",
        "command",
        "cwd",
        "env",
        "environment",
        "shell",
        "subprocess",
        "cuda_visible_devices",
        "gpu_id",
        "device_id",
    }
)


def _reject_executor_fields(value: Any, path: str = "arguments") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_REQUEST_KEYS:
                raise ValueError(f"{path}.{key} is executor-owned")
            _reject_executor_fields(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_executor_fields(child, f"{path}[{index}]")


class ToolRequest(StrictModel):
    schema_version: str = "1.0"
    tool_call_id: Identifier
    tool_name: ToolName
    case_id: Identifier
    scenario_id: Identifier
    episode_id: Identifier
    window_id: Identifier
    approved_config_id: Identifier | None = None
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    requested_at: Timestamp

    @field_validator("arguments")
    @classmethod
    def llm_cannot_supply_executor_fields(
        cls, value: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        _reject_executor_fields(value)
        assert_deployable_payload(value, "arguments")
        return value


class AgentAction(StrictModel):
    action_id: Identifier
    action_type: ActionType
    case_id: Identifier
    window_id: Identifier
    rationale: str = Field(min_length=1, max_length=4000)
    based_on_observation_id: Identifier
    deployment_evidence_ids: tuple[Identifier, ...]
    tool_request: ToolRequest | None = None
    pending_config_id: Identifier | None = None
    effective_sequence_number: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def action_payload_matches_type(self) -> "AgentAction":
        if self.action_type == ActionType.RUN_TOOL and self.tool_request is None:
            raise ValueError("run_tool action requires a typed ToolRequest")
        if self.action_type != ActionType.RUN_TOOL and self.tool_request is not None:
            raise ValueError("only run_tool action may contain ToolRequest")
        if self.action_type == ActionType.SCHEDULE_RECONFIGURATION:
            if not self.pending_config_id or self.effective_sequence_number is None:
                raise ValueError("reconfiguration action requires config and effective window")
        elif self.pending_config_id or self.effective_sequence_number is not None:
            raise ValueError("config scheduling fields belong only to reconfiguration action")
        return self


class CommandManifest(StrictModel):
    manifest_id: Identifier
    executable_id: Identifier
    argv: tuple[str, ...]
    working_directory: str
    injected_environment_keys: tuple[Identifier, ...] = ()

    @field_validator("working_directory")
    @classmethod
    def absolute_working_directory(cls, value: str) -> str:
        if not PurePosixPath(value).is_absolute():
            raise ValueError("executor working directory must be absolute")
        return value

    @field_validator("injected_environment_keys")
    @classmethod
    def no_secret_environment_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        forbidden_fragments = ("PASSWORD", "TOKEN", "SECRET", "PRIVATE", "API_KEY")
        if any(any(fragment in key.upper() for fragment in forbidden_fragments) for key in value):
            raise ValueError("command manifest cannot expose secret environment keys")
        return value


class StageTrace(StrictModel):
    stage: PipelineStage
    status: RunStatus
    started_at: Timestamp
    ended_at: Timestamp | None = None
    artifact_ids: tuple[Identifier, ...] = ()
    sanitized_error: str | None = None

    @model_validator(mode="after")
    def terminal_stage_has_end(self) -> "StageTrace":
        if self.status in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.BLOCKED}:
            if self.ended_at is None:
                raise ValueError("terminal stage requires ended_at")
        if self.ended_at and self.ended_at < self.started_at:
            raise ValueError("stage ended_at cannot precede started_at")
        return self


class ToolResult(StrictModel):
    schema_version: str = "1.0"
    tool_call_id: Identifier
    tool_name: ToolName
    status: RunStatus
    validated_arguments: dict[str, JsonValue]
    approved_config_id: Identifier | None = None
    checkpoint_hash: Sha256 | None = None
    command_manifest: CommandManifest | None = None
    started_at: Timestamp
    ended_at: Timestamp
    exit_code: int | None = None
    stdout_artifact_id: Identifier | None = None
    stderr_artifact_id: Identifier | None = None
    artifact_ids: tuple[Identifier, ...] = ()
    stage_trace: tuple[StageTrace, ...] = ()
    standardized_observation: dict[str, JsonValue] = Field(default_factory=dict)
    sanitized_error: str | None = None

    @field_validator("standardized_observation")
    @classmethod
    def standardized_output_is_deployable(
        cls, value: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        assert_deployable_payload(value, "standardized_observation")
        return value

    @model_validator(mode="after")
    def result_fields_are_consistent(self) -> "ToolResult":
        if self.ended_at < self.started_at:
            raise ValueError("tool ended_at cannot precede started_at")
        if self.status == RunStatus.SUCCEEDED:
            if self.exit_code not in (None, 0):
                raise ValueError("successful tool cannot have nonzero exit code")
            if self.sanitized_error:
                raise ValueError("successful tool cannot have an error")
        if self.status == RunStatus.FAILED and not self.sanitized_error:
            raise ValueError("failed tool requires sanitized_error")
        return self
