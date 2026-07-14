"""Sanitized evaluation outputs allowed to cross into public processes.

Requirements: REQ-LABEL-001..004, REQ-EVAL-002, REQ-EVAL-006.
"""

from pydantic import model_validator

from apt_detection_agent.schemas.common import DataSplit, Identifier, StrictModel, Timestamp


class TrainingStepFeedback(StrictModel):
    split: DataSplit
    step_id: Identifier
    sanitized_reward: float
    signal_id: Identifier

    @model_validator(mode="after")
    def training_only(self) -> "TrainingStepFeedback":
        if self.split != DataSplit.AGENT_TRAINING:
            raise ValueError("step feedback is allowed only during agent training")
        return self


class EpisodeMetricsFeedback(StrictModel):
    split: DataSplit
    episode_id: Identifier
    metrics_artifact_id: Identifier
    emitted_at: Timestamp

    @model_validator(mode="after")
    def heldout_or_validation_only(self) -> "EpisodeMetricsFeedback":
        if self.split not in {DataSplit.VALIDATION, DataSplit.HELD_OUT}:
            raise ValueError("episode metrics feedback is for validation/held-out")
        return self
