"""Privileged hidden-teacher record; never a student or deployment schema.

Requirements: REQ-SFT-001..002, REQ-LABEL-002..004.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from apt_detection_agent.schemas import AgentAction, DataSplit, Observation
from apt_detection_agent.schemas.common import Identifier, StrictModel


class HiddenTeacherRecord(StrictModel):
    teacher_record_id: Identifier
    source_split: DataSplit
    student_observation: Observation
    target_action: AgentAction
    teacher_only_rationale: str = Field(min_length=1)
    privileged_labels: dict[str, str | int | float | bool]
    counterfactual_best_action: str | None = None
    source_trajectory_id: Identifier

    @model_validator(mode="after")
    def agent_training_only_and_aligned(self) -> "HiddenTeacherRecord":
        if self.source_split != DataSplit.AGENT_TRAINING:
            raise ValueError("SFT teacher records must come only from agent-training data")
        if self.student_observation.split != DataSplit.AGENT_TRAINING:
            raise ValueError("student observation must be agent-training scoped")
        if self.target_action.based_on_observation_id != self.student_observation.observation_id:
            raise ValueError("teacher target must cite the student observation")
        if self.target_action.window_id != self.student_observation.window.window_id:
            raise ValueError("teacher target window does not match student observation")
        return self
