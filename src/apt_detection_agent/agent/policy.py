"""Typed Agent policy interface.

Requirements: REQ-RUNTIME-003, REQ-TOOL-001..005, REQ-MEMORY-001..007.
"""

from typing import Protocol, TypeAlias

from apt_detection_agent.schemas import (
    FrozenCaseState,
    MemoryDecisionEnvelope,
    ModelPromptObservation,
    ProposedAction,
)

PolicyOutput: TypeAlias = ProposedAction | MemoryDecisionEnvelope


class AgentPolicy(Protocol):
    def __call__(
        self, prompt: ModelPromptObservation, case: FrozenCaseState
    ) -> PolicyOutput: ...
