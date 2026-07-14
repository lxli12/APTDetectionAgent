"""Frozen two-assistant-turn runtime memory protocol."""

from __future__ import annotations

from enum import Enum

from pydantic import Field, field_validator, model_validator

from .agent_runtime import FrozenActionDecision, ModelPromptObservation
from .common import Identifier, RunStatus, StrictModel
from .evaluation import assert_deployable_payload
from .memory import MemoryLayer, MemoryRecord


class MemoryDisposition(str, Enum):
    USE = "use"
    DOWNWEIGHT = "downweight"
    IGNORE = "ignore"


class MemoryReadRequest(StrictModel):
    request_id: Identifier
    prompt_id: Identifier
    case_id: Identifier
    needed: bool
    query: str | None = Field(default=None, min_length=1, max_length=2048)
    pids_id: Identifier | None = None
    reason_code: Identifier
    visible_evidence_ids: tuple[Identifier, ...]

    @field_validator("query")
    @classmethod
    def query_is_deployment_visible(cls, value: str | None) -> str | None:
        if value is not None:
            _reject_privileged_text(value, "memory query")
        return value

    @model_validator(mode="after")
    def needed_controls_query(self) -> "MemoryReadRequest":
        if self.needed != bool(self.query):
            raise ValueError("needed=true requires query; needed=false forbids query")
        if not self.needed and self.pids_id:
            raise ValueError("unneeded retrieval cannot apply a PIDS filter")
        return self


class MemoryRetrievalResult(StrictModel):
    result_id: Identifier
    request_id: Identifier
    needed: bool
    status: RunStatus
    records: tuple[MemoryRecord, ...] = ()
    candidate_count: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    truncated: bool
    policy_validation_status: Identifier
    sanitized_failure_code: Identifier | None = None

    @model_validator(mode="after")
    def result_is_deterministic_and_typed(self) -> "MemoryRetrievalResult":
        if not self.needed and (
            self.records or self.candidate_count or self.estimated_tokens or self.truncated
        ):
            raise ValueError("needed=false requires deterministic empty retrieval")
        if self.status == RunStatus.SUCCEEDED and self.sanitized_failure_code:
            raise ValueError("successful retrieval cannot carry failure")
        if self.status != RunStatus.SUCCEEDED:
            if not self.sanitized_failure_code or self.records:
                raise ValueError("failed retrieval requires typed failure and no records")
        for record in self.records:
            _reject_privileged_text(
                " ".join(
                    (
                        record.environment,
                        record.observable_behavior,
                        record.action,
                        record.content,
                        *record.applicability_conditions,
                    )
                ),
                "retrieved memory",
            )
        assert_deployable_payload(self.model_dump(mode="json"), "memory_retrieval")
        return self


class MemoryUseDecision(StrictModel):
    memory_id: Identifier
    disposition: MemoryDisposition
    reason_code: Identifier
    visible_evidence_ids: tuple[Identifier, ...]


class MemoryWriteCandidate(StrictModel):
    candidate_id: Identifier
    layer: MemoryLayer
    observable_behavior: str = Field(min_length=1, max_length=4000)
    pids_id: Identifier
    variant_id: Identifier = "default"
    intended_action: str = Field(min_length=1, max_length=4000)
    content: str = Field(min_length=1, max_length=8000)
    evidence_artifact_ids: tuple[Identifier, ...]
    applicability_conditions: tuple[str, ...] = ()
    conflicts_with: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def candidate_is_runtime_visible_and_pre_outcome(self) -> "MemoryWriteCandidate":
        if self.layer not in {MemoryLayer.WORKING, MemoryLayer.EPISODE}:
            raise ValueError("runtime write candidate cannot target static LTM")
        assert_deployable_payload(self.model_dump(mode="json"), "memory_write_candidate")
        return self

    @field_validator("observable_behavior", "intended_action", "content")
    @classmethod
    def no_privileged_or_unseen_outcome_claim(cls, value: str) -> str:
        forbidden = (
            "ground truth",
            "test label",
            "teacher rationale",
            "counterfactual best action",
            "campaign mapping",
            "tool succeeded",
            "detector succeeded",
        )
        matched = [item for item in forbidden if item in value.casefold()]
        if matched:
            raise ValueError(f"memory candidate contains forbidden phrase: {matched[0]}")
        return value


class MemoryActionResponse(StrictModel):
    response_id: Identifier
    prompt_id: Identifier
    retrieval_result_id: Identifier
    use_decisions: tuple[MemoryUseDecision, ...]
    diagnosis_code: Identifier
    action: FrozenActionDecision
    write_candidate: MemoryWriteCandidate | None = None


class FrozenMemoryExchange(StrictModel):
    schema_version: str = "frozen-memory-exchange-v1"
    exchange_id: Identifier
    prompt: ModelPromptObservation
    read_request: MemoryReadRequest
    retrieval_result: MemoryRetrievalResult
    response: MemoryActionResponse

    @model_validator(mode="after")
    def exact_two_turn_protocol(self) -> "FrozenMemoryExchange":
        if (
            self.read_request.prompt_id != self.prompt.prompt_id
            or self.retrieval_result.request_id != self.read_request.request_id
            or self.retrieval_result.needed != self.read_request.needed
            or self.response.prompt_id != self.prompt.prompt_id
            or self.response.retrieval_result_id != self.retrieval_result.result_id
        ):
            raise ValueError("memory exchange identity chain is broken")
        record_ids = [record.memory_id for record in self.retrieval_result.records]
        decided_ids = [item.memory_id for item in self.response.use_decisions]
        if len(decided_ids) != len(set(decided_ids)) or set(decided_ids) != set(record_ids):
            raise ValueError("every retrieved memory requires exactly one disposition")
        used = {
            item.memory_id
            for item in self.response.use_decisions
            if item.disposition == MemoryDisposition.USE
        }
        if not used.issubset(set(self.response.action.visible_evidence_ids)):
            raise ValueError("action must cite every memory it actually uses")
        if self.response.action.based_on_observation_id != self.prompt.canonical_observation_id:
            raise ValueError("memory-assisted action changed canonical observation")
        assert_deployable_payload(self.model_dump(mode="json"), "memory_exchange")
        return self


class MemoryDecisionEnvelope(StrictModel):
    action: FrozenActionDecision
    exchange: FrozenMemoryExchange

    @model_validator(mode="after")
    def action_matches_exchange(self) -> "MemoryDecisionEnvelope":
        if self.action != self.exchange.response.action:
            raise ValueError("decision envelope action differs from memory exchange")
        return self


def _reject_privileged_text(value: str, context: str) -> None:
    forbidden = (
        "ground truth",
        "test label",
        "teacher rationale",
        "counterfactual best action",
        "campaign mapping",
        "attack identity",
        "dataset identity",
        "malicious node",
    )
    matched = [item for item in forbidden if item in value.casefold()]
    if matched:
        raise ValueError(f"{context} contains privileged phrase: {matched[0]}")
