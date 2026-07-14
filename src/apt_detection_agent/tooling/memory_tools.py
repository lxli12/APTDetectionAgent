"""Structured memory, case, and visible-report tool executor.

Requirements: REQ-TOOL-001..005, REQ-MEMORY-001..007,
REQ-CONFIG-001, REQ-LABEL-002..004, REQ-REPRO-001..002.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from pydantic import Field, field_validator, model_validator

from apt_detection_agent.memory import (
    CaseMemoryStore,
    MemoryNamespace,
    MemoryQuery,
    normalized_content_hash,
)
from apt_detection_agent.schemas import (
    MemoryLayer,
    MemoryRecord,
    PIDSRef,
    PendingConfiguration,
    RunStatus,
    ToolName,
    ToolRequest,
    ToolResult,
)
from apt_detection_agent.schemas.common import Identifier, StrictModel
from apt_detection_agent.schemas.common import assert_deployable_payload


class RetrieveMemoryArguments(StrictModel):
    query: str = Field(min_length=1, max_length=2048)
    pids_id: Identifier | None = None
    top_k: int = Field(default=5, ge=1, le=20)


class WriteMemoryArguments(StrictModel):
    layer: MemoryLayer
    observable_behavior: str = Field(min_length=1, max_length=4000)
    pids_id: Identifier
    variant_id: Identifier = "default"
    action: str = Field(min_length=1, max_length=4000)
    content: str = Field(min_length=1, max_length=8000)
    evidence_artifact_ids: tuple[Identifier, ...]
    applicability_conditions: tuple[str, ...] = ()
    conflicts_with: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def runtime_layer_only(self) -> "WriteMemoryArguments":
        if self.layer not in {MemoryLayer.WORKING, MemoryLayer.EPISODE}:
            raise ValueError("runtime tool cannot write static LTM")
        return self


class UpdateCaseArguments(StrictModel):
    pending_config_id: Identifier
    effective_sequence_number: int = Field(ge=0)


class GenerateReportArguments(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=12000)
    visible_evidence_ids: tuple[Identifier, ...]

    @field_validator("title", "summary")
    @classmethod
    def no_privileged_prose(cls, value: str) -> str:
        forbidden = (
            "ground truth",
            "test label",
            "teacher rationale",
            "counterfactual best action",
            "campaign mapping",
            "hidden metric",
            "malicious node",
        )
        matched = [term for term in forbidden if term in value.casefold()]
        if matched:
            raise ValueError(f"report text contains privileged phrase: {matched[0]}")
        return value


Clock = Callable[[], datetime]


@dataclass
class MemoryCaseToolService:
    """Bind Agent requests to one executor-owned case/namespace/report root."""

    store: CaseMemoryStore
    namespace: MemoryNamespace
    case_id: str
    environment_profile: str
    report_root: Path
    audit_path: Path
    clock: Clock

    def __post_init__(self) -> None:
        if not self.environment_profile.strip():
            raise ValueError("executor-owned environment profile is required")
        self.report_root = self.report_root.resolve()
        self.audit_path = self.audit_path.resolve()
        self.report_root.mkdir(parents=True, exist_ok=True)
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)

    def execute(self, request: ToolRequest) -> ToolResult:
        started_at = self.clock()
        try:
            self._validate_identity(request)
            if request.tool_name == ToolName.RETRIEVE_MEMORY:
                arguments = RetrieveMemoryArguments.model_validate(request.arguments)
                observation, artifact_ids = self._retrieve(arguments)
            elif request.tool_name == ToolName.WRITE_MEMORY:
                arguments = WriteMemoryArguments.model_validate(request.arguments)
                observation, artifact_ids = self._write(request, arguments, started_at)
            elif request.tool_name == ToolName.UPDATE_CASE:
                arguments = UpdateCaseArguments.model_validate(request.arguments)
                observation, artifact_ids = self._update_case(request, arguments)
            elif request.tool_name == ToolName.GENERATE_REPORT:
                arguments = GenerateReportArguments.model_validate(request.arguments)
                observation, artifact_ids = self._report(request, arguments)
            else:
                raise ValueError("tool is not handled by the memory/case/report executor")
            assert_deployable_payload(observation, "standardized_observation")
            ended_at = self.clock()
            result = ToolResult(
                tool_call_id=request.tool_call_id,
                tool_name=request.tool_name,
                status=RunStatus.SUCCEEDED,
                validated_arguments=arguments.model_dump(mode="json"),
                started_at=started_at,
                ended_at=ended_at,
                exit_code=0,
                artifact_ids=artifact_ids,
                standardized_observation=observation,
            )
        except (ValueError, KeyError, FileExistsError) as exc:
            ended_at = self.clock()
            result = ToolResult(
                tool_call_id=request.tool_call_id,
                tool_name=request.tool_name,
                status=RunStatus.FAILED,
                validated_arguments={},
                started_at=started_at,
                ended_at=ended_at,
                exit_code=1,
                sanitized_error=f"{type(exc).__name__}: structured tool request rejected",
            )
        with self.audit_path.open("a") as handle:
            handle.write(result.model_dump_json() + "\n")
        return result

    def _validate_identity(self, request: ToolRequest) -> None:
        case = self.store.get_case(self.case_id)
        if (
            request.case_id != case.case_id
            or request.scenario_id != self.namespace.scenario_id
            or request.episode_id != self.namespace.episode_id
            or case.split != self.namespace.split
            or case.memory_namespace != self.namespace.key
        ):
            raise ValueError("tool request escaped its case lifecycle scope")

    def _retrieve(
        self, arguments: RetrieveMemoryArguments
    ) -> tuple[dict[str, object], tuple[str, ...]]:
        result = self.store.retrieve(
            MemoryQuery(
                query=arguments.query,
                namespace=self.namespace,
                environment=self.environment_profile,
                pids_id=arguments.pids_id,
                top_k=arguments.top_k,
            )
        )
        records = [record.model_dump(mode="json") for record in result.records]
        return (
            {
                "records": records,
                "candidate_count": result.candidate_count,
                "estimated_tokens": result.estimated_tokens,
                "truncated": result.truncated,
                "policy_validation_status": result.policy_validation_status,
            },
            tuple(record.memory_id for record in result.records),
        )

    def _write(
        self,
        request: ToolRequest,
        arguments: WriteMemoryArguments,
        created_at: datetime,
    ) -> tuple[dict[str, object], tuple[str, ...]]:
        call_digest = hashlib.sha256(request.tool_call_id.encode()).hexdigest()[:24]
        memory_id = f"memory-{call_digest}"
        record = MemoryRecord(
            memory_id=memory_id,
            layer=arguments.layer,
            split=self.namespace.split,
            scenario_id=self.namespace.scenario_id,
            episode_id=self.namespace.episode_id,
            environment=self.environment_profile,
            observable_behavior=arguments.observable_behavior,
            pids=PIDSRef(pids_id=arguments.pids_id, variant_id=arguments.variant_id),
            action=arguments.action,
            content=arguments.content,
            normalized_content_hash=normalized_content_hash(arguments.content),
            evidence_artifact_ids=arguments.evidence_artifact_ids,
            applicability_conditions=arguments.applicability_conditions,
            conflicts_with=arguments.conflicts_with,
            created_at=created_at,
        )
        outcome = self.store.write_runtime(record, self.namespace)
        return (
            {
                "memory_id": outcome.memory_id,
                "inserted": outcome.inserted,
                "duplicate_of": outcome.duplicate_of,
            },
            (memory_id,) if outcome.inserted else (),
        )

    def _update_case(
        self, request: ToolRequest, arguments: UpdateCaseArguments
    ) -> tuple[dict[str, object], tuple[str, ...]]:
        case = self.store.get_case(self.case_id)
        if arguments.effective_sequence_number != case.current_window_sequence + 1:
            raise ValueError("persistent config must take effect exactly next window")
        updated = case.model_copy(
            update={
                "pending_configuration": PendingConfiguration(
                    config_id=arguments.pending_config_id,
                    effective_sequence_number=arguments.effective_sequence_number,
                    requested_by_tool_call_id=request.tool_call_id,
                ),
                "updated_at": self.clock(),
            }
        )
        updated = type(case).model_validate(updated.model_dump())
        self.store.update_case(updated)
        return (
            {
                "case_id": case.case_id,
                "committed_config_id": case.committed_config_id,
                "pending_config_id": arguments.pending_config_id,
                "effective_sequence_number": arguments.effective_sequence_number,
            },
            (),
        )

    def _report(
        self, request: ToolRequest, arguments: GenerateReportArguments
    ) -> tuple[dict[str, object], tuple[str, ...]]:
        call_digest = hashlib.sha256(request.tool_call_id.encode()).hexdigest()[:24]
        path = (self.report_root / f"report-{call_digest}.md").resolve()
        if path.parent != self.report_root:
            raise ValueError("report path escaped executor-owned root")
        if path.exists():
            raise FileExistsError(path)
        body = (
            f"# {arguments.title}\n\n{arguments.summary}\n\n"
            "## Deployment-visible evidence\n\n"
            + "\n".join(f"- `{item}`" for item in arguments.visible_evidence_ids)
            + "\n"
        )
        path.write_text(body)
        digest = hashlib.sha256(body.encode()).hexdigest()
        artifact_id = f"report-{call_digest}"
        return (
            {
                "report_artifact_id": artifact_id,
                "content_hash": digest,
                "evidence_count": len(arguments.visible_evidence_ids),
            },
            (artifact_id,),
        )
