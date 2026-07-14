"""Privileged teacher envelope around an immutable public frozen runtime trace."""

from __future__ import annotations

from pydantic import Field, model_validator

from apt_detection_agent.schemas import (
    CanonicalAgentVisibleObservation,
    DataSplit,
    FrozenActionDecision,
    FrozenMemoryExchange,
    ModelPromptObservation,
)
from apt_detection_agent.schemas.common import Identifier, StrictModel


class FrozenHiddenTeacherRecord(StrictModel):
    teacher_record_id: Identifier
    source_split: DataSplit
    source_trajectory_id: Identifier
    partition_group_id: Identifier
    source_admission_ids: tuple[Identifier, ...] = Field(min_length=1)
    canonical_observation: CanonicalAgentVisibleObservation
    model_prompt: ModelPromptObservation
    public_memory_exchange: FrozenMemoryExchange
    target_action: FrozenActionDecision
    teacher_only_rationale: str = Field(min_length=1)
    privileged_labels: dict[str, str | int | float | bool]
    counterfactual_best_action: str | None = None

    @model_validator(mode="after")
    def privileged_teacher_wraps_but_cannot_rewrite_public_trace(
        self,
    ) -> "FrozenHiddenTeacherRecord":
        if self.source_split != DataSplit.AGENT_TRAINING:
            raise ValueError("frozen SFT teacher must use agent-training source")
        if self.canonical_observation.split != DataSplit.AGENT_TRAINING:
            raise ValueError("public observation must be agent-training scoped")
        if (
            self.model_prompt.canonical_observation_id
            != self.canonical_observation.observation_id
            or self.model_prompt.canonical_observation_hash
            != self.canonical_observation.content_hash
            or self.public_memory_exchange.prompt != self.model_prompt
            or self.public_memory_exchange.response.action != self.target_action
        ):
            raise ValueError("teacher target/public trace diverges from frozen runtime")
        return self
