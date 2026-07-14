"""Harness for the frozen two-turn memory diagnostic exchange."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from apt_detection_agent.schemas import (
    FrozenCaseState,
    FrozenMemoryExchange,
    MemoryActionResponse,
    MemoryDecisionEnvelope,
    MemoryReadRequest,
    MemoryRetrievalResult,
    ModelPromptObservation,
)


MemoryReadPolicy = Callable[
    [ModelPromptObservation, FrozenCaseState], MemoryReadRequest
]
MemoryRetrievalTool = Callable[
    [MemoryReadRequest, FrozenCaseState], MemoryRetrievalResult
]
MemoryActionPolicy = Callable[
    [ModelPromptObservation, MemoryRetrievalResult, FrozenCaseState],
    MemoryActionResponse,
]


@dataclass(frozen=True)
class FrozenMemoryProtocol:
    read_policy: MemoryReadPolicy
    retrieval_tool: MemoryRetrievalTool
    action_policy: MemoryActionPolicy

    def __call__(
        self,
        prompt: ModelPromptObservation,
        case: FrozenCaseState,
    ) -> MemoryDecisionEnvelope:
        read_request = self.read_policy(prompt, case)
        if read_request.case_id != case.case_id or read_request.prompt_id != prompt.prompt_id:
            raise ValueError("memory read request escaped prompt/case identity")
        # The tool is always called, including needed=false, to preserve turn shape.
        retrieval_result = self.retrieval_tool(read_request, case)
        response = self.action_policy(prompt, retrieval_result, case)
        exchange = FrozenMemoryExchange(
            exchange_id=f"memory-exchange-{read_request.request_id}",
            prompt=prompt,
            read_request=read_request,
            retrieval_result=retrieval_result,
            response=response,
        )
        return MemoryDecisionEnvelope(action=response.action, exchange=exchange)
