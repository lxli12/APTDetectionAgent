"""Observe-think-act-reflect controller with committed fast path.

Requirements: REQ-TOOL-001..005, REQ-CONFIG-001..002,
REQ-WINDOW-002..004, REQ-LABEL-004, REQ-REPRO-001.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from pydantic import Field

from apt_detection_agent.schemas import (
    ActionType,
    AgentAction,
    CaseState,
    DataSplit,
    Observation,
    PendingConfiguration,
    Prediction,
    RunStatus,
    ToolRequest,
    ToolResult,
)
from apt_detection_agent.schemas.common import StrictModel

from .trajectory import TrajectoryLogger, TrajectoryStep


class ControllerConfig(StrictModel):
    max_tool_attempts: int = Field(default=2, ge=1, le=3)
    slow_path_alert_count: int = Field(ge=1)
    periodic_check_window_count: int = Field(ge=1)
    trigger_profile_id: str
    trigger_source_split: DataSplit

    def model_post_init(self, __context: object) -> None:
        if self.trigger_source_split != DataSplit.VALIDATION:
            raise ValueError("slow-path trigger thresholds must be frozen from validation")


class TriggerDecision(StrictModel):
    triggered: bool
    reasons: tuple[str, ...]


class ControllerStepResult(StrictModel):
    prediction: Prediction
    action: AgentAction
    tool_results: tuple[ToolResult, ...]
    next_case: CaseState
    reflection: str


FastPath = Callable[[Observation, CaseState], Prediction]
Policy = Callable[[Observation, CaseState, TriggerDecision], AgentAction]
ToolExecutor = Callable[[ToolRequest], ToolResult]


@dataclass
class Controller:
    config: ControllerConfig
    fast_path: FastPath
    policy: Policy
    tool_executor: ToolExecutor
    trajectory_logger: TrajectoryLogger

    def _trigger(self, observation: Observation) -> TriggerDecision:
        reasons: list[str] = []
        if len(observation.alerts) >= self.config.slow_path_alert_count:
            reasons.append("validated_alert_volume_trigger")
        if observation.observable_failures:
            reasons.append("observable_failure_trigger")
        if observation.window.sequence_number % self.config.periodic_check_window_count == 0:
            reasons.append("validated_periodic_health_check")
        return TriggerDecision(triggered=bool(reasons), reasons=tuple(reasons))

    @staticmethod
    def _validate_identity(observation: Observation, case: CaseState) -> None:
        if (
            observation.scenario_id != case.scenario_id
            or observation.episode_id != case.episode_id
            or observation.split != case.split
            or observation.window.sequence_number != case.current_window_sequence
            or observation.committed_config_id != case.committed_config_id
        ):
            raise ValueError("observation and Case State identities/config do not match")

    def run_step(
        self,
        observation: Observation,
        case: CaseState,
        *,
        step_number: int,
        started_at: datetime,
        ended_at: datetime,
    ) -> ControllerStepResult:
        self._validate_identity(observation, case)
        prediction = self.fast_path(observation, case)
        if prediction.committed_config_id != case.committed_config_id:
            raise ValueError("fast path prediction did not use committed config")
        trigger = self._trigger(observation)
        action = self.policy(observation, case, trigger)
        forbidden_rationale = (
            "ground truth",
            "test label",
            "teacher rationale",
            "campaign mapping",
            "counterfactual best action",
        )
        if any(term in action.rationale.casefold() for term in forbidden_rationale):
            raise ValueError("policy rationale contains privileged evidence")
        if action.case_id != case.case_id or action.window_id != observation.window.window_id:
            raise ValueError("policy action identity does not match current step")
        if not trigger.triggered and action.action_type not in {
            ActionType.NO_CHANGE,
            ActionType.COMMIT_FAST_PATH,
        }:
            raise ValueError("slow-path action requires a deployment-visible trigger")
        tool_results: list[ToolResult] = []
        if action.action_type == ActionType.RUN_TOOL:
            request = action.tool_request
            assert request is not None
            if (
                request.case_id != case.case_id
                or request.scenario_id != case.scenario_id
                or request.episode_id != case.episode_id
                or request.window_id != observation.window.window_id
            ):
                raise ValueError("tool request identity does not match current step")
            for _ in range(self.config.max_tool_attempts):
                result = self.tool_executor(request)
                tool_results.append(result)
                if result.status == RunStatus.SUCCEEDED:
                    break
        next_case = case
        if action.action_type == ActionType.SCHEDULE_RECONFIGURATION:
            if action.effective_sequence_number != case.current_window_sequence + 1:
                raise ValueError("persistent reconfiguration must begin next window")
            next_case = case.model_copy(
                update={
                    "pending_configuration": PendingConfiguration(
                        config_id=action.pending_config_id,
                        effective_sequence_number=action.effective_sequence_number,
                        requested_by_tool_call_id=action.action_id,
                    ),
                    "updated_at": ended_at,
                }
            )
            next_case = CaseState.model_validate(next_case.model_dump())
        reflection = (
            "tool_succeeded"
            if tool_results and tool_results[-1].status == RunStatus.SUCCEEDED
            else "bounded_failure_fallback" if tool_results else "no_tool_executed"
        )
        step = TrajectoryStep(
            trajectory_id=f"trajectory-{case.episode_id}",
            step_number=step_number,
            observation=observation,
            prediction=prediction,
            action=action,
            tool_results=tuple(tool_results),
            reflection=reflection,
            started_at=started_at,
            ended_at=ended_at,
        )
        self.trajectory_logger.append(step)
        return ControllerStepResult(
            prediction=prediction,
            action=action,
            tool_results=tuple(tool_results),
            next_case=next_case,
            reflection=reflection,
        )
