"""Loss-aware deterministic exports for canonical demonstration trajectories."""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from pydantic import Field, model_validator

from apt_detection_agent.schemas.common import Identifier, Sha256, StrictModel
from apt_detection_agent.schemas.evaluation import assert_deployable_payload

from .demonstration import CanonicalDemonstrationTrajectory


class ChatRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ExportedToolCall(StrictModel):
    id: Identifier
    type: str = "function"
    function: dict[str, str]


class LossAwareMessage(StrictModel):
    role: ChatRole
    content: str
    loss: bool
    tool_calls: tuple[ExportedToolCall, ...] = ()
    tool_call_id: Identifier | None = None

    @model_validator(mode="after")
    def assistant_only_loss_and_tool_shape(self) -> "LossAwareMessage":
        if self.loss != (self.role == ChatRole.ASSISTANT):
            raise ValueError("only assistant messages may contribute training loss")
        if self.tool_calls and self.role != ChatRole.ASSISTANT:
            raise ValueError("tool calls belong to assistant messages")
        if self.tool_call_id and self.role != ChatRole.TOOL:
            raise ValueError("tool_call_id belongs to a tool result")
        if self.role == ChatRole.TOOL and not self.tool_call_id:
            raise ValueError("tool result requires paired call identity")
        return self


class OpenAICompatibleTrajectory(StrictModel):
    schema_version: str = "openai-tool-trajectory-v1"
    trajectory_id: Identifier
    partition_group_id: Identifier
    messages: tuple[LossAwareMessage, ...] = Field(min_length=3)
    source_admission_ids: tuple[Identifier, ...]
    payload_hash: Sha256

    def expected_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"payload_hash"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()

    @model_validator(mode="after")
    def sequence_is_paired_and_hashed(self) -> "OpenAICompatibleTrajectory":
        if self.messages[0].role != ChatRole.SYSTEM:
            raise ValueError("chat trajectory must begin with system contract")
        open_calls: set[str] = set()
        for message in self.messages:
            for call in message.tool_calls:
                if call.id in open_calls:
                    raise ValueError("duplicate tool call identity")
                open_calls.add(call.id)
            if message.tool_call_id:
                if message.tool_call_id not in open_calls:
                    raise ValueError("tool result precedes its assistant call")
                open_calls.remove(message.tool_call_id)
        if open_calls:
            raise ValueError("assistant tool call has no result")
        if self.payload_hash != self.expected_hash():
            raise ValueError("export payload hash mismatch")
        assert_deployable_payload(self.model_dump(mode="json"), "openai_export")
        return self


class DemonstrationExporter:
    VERSION = "demonstration-exporter-v1"
    SYSTEM_CONTRACT = (
        "Use only the deployment-visible observation and retrieved public memory. "
        "Choose one frozen action and emit schema-valid arguments."
    )

    @classmethod
    def export(cls, trajectory: CanonicalDemonstrationTrajectory) -> OpenAICompatibleTrajectory:
        messages: list[LossAwareMessage] = [
            LossAwareMessage(role=ChatRole.SYSTEM, content=cls.SYSTEM_CONTRACT, loss=False)
        ]
        for exchange in trajectory.exchanges:
            user_payload = {
                "prompt": exchange.memory_exchange.prompt.model_dump(mode="json"),
                "memory_retrieval": exchange.memory_exchange.retrieval_result.model_dump(mode="json"),
            }
            messages.append(
                LossAwareMessage(
                    role=ChatRole.USER,
                    content=_json(user_payload),
                    loss=False,
                )
            )
            action = exchange.memory_exchange.response.action
            calls: tuple[ExportedToolCall, ...] = ()
            if action.requested_tool:
                calls = (
                    ExportedToolCall(
                        id=action.action_id,
                        function={
                            "name": action.requested_tool.value,
                            "arguments": _json(action.model_dump(mode="json")),
                        },
                    ),
                )
            messages.append(
                LossAwareMessage(
                    role=ChatRole.ASSISTANT,
                    content=_json(
                        {
                            "diagnosis_code": exchange.memory_exchange.response.diagnosis_code,
                            "grounding": exchange.grounding.model_dump(mode="json"),
                            "action": action.model_dump(mode="json"),
                        }
                    ),
                    loss=True,
                    tool_calls=calls,
                )
            )
            if exchange.action_tool_outcome:
                outcome_payload: dict[str, object] = {
                    "outcome": exchange.action_tool_outcome.model_dump(mode="json")
                }
                if exchange.additional_detector_result:
                    outcome_payload["additional_detector_result"] = (
                        exchange.additional_detector_result.model_dump(mode="json")
                    )
                messages.append(
                    LossAwareMessage(
                        role=ChatRole.TOOL,
                        content=_json(outcome_payload),
                        loss=False,
                        tool_call_id=action.action_id,
                    )
                )
        values = {
            "trajectory_id": trajectory.trajectory_id,
            "partition_group_id": trajectory.partition_group_id,
            "messages": tuple(messages),
            "source_admission_ids": trajectory.source_admission_ids,
        }
        provisional = OpenAICompatibleTrajectory.model_construct(**values, payload_hash="0" * 64)
        return OpenAICompatibleTrajectory(**values, payload_hash=provisional.expected_hash())

    @staticmethod
    def canonical_jsonl(exports: tuple[OpenAICompatibleTrajectory, ...]) -> str:
        ids = [item.trajectory_id for item in exports]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate trajectory identity in export")
        return "".join(_json(item.model_dump(mode="json")) + "\n" for item in exports)

    @staticmethod
    def parse_canonical_jsonl(value: str) -> tuple[OpenAICompatibleTrajectory, ...]:
        records = tuple(
            OpenAICompatibleTrajectory.model_validate_json(line)
            for line in value.splitlines()
            if line.strip()
        )
        if DemonstrationExporter.canonical_jsonl(records) != value:
            raise ValueError("JSONL is not in canonical deterministic form")
        return records


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
