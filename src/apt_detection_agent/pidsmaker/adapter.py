"""Validated argv construction and PIDSMaker subprocess execution.

Requirements: REQ-TOOL-001..005, REQ-PIDS-004..005,
REQ-ARTIFACT-001..003, REQ-WANDB-001, REQ-RESOURCE-002.
"""

from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

from pydantic import Field, field_validator, model_validator

from apt_detection_agent.schemas import (
    ApprovedConfig,
    ArtifactManifest,
    ArtifactRecord,
    CommandManifest,
    DataSplit,
    PIDSRef,
    RunStatus,
    ToolName,
    ToolResult,
)
from apt_detection_agent.schemas.common import StrictModel

from .discovery import PIDSMakerDiscovery


FORBIDDEN_OVERRIDE_PARTS = frozenset(
    {
        "artifact_dir",
        "database_host",
        "database_password",
        "database_port",
        "database_user",
        "device",
        "gpu",
        "project",
        "sweep_id",
        "tags",
        "tuning_mode",
        "wandb",
    }
)


class PIDSDetectionRequest(StrictModel):
    request_id: str
    tool_call_id: str
    case_id: str
    scenario_id: str
    episode_id: str
    window_id: str
    split: DataSplit
    run_id: str
    pids: PIDSRef
    source_config_id: str
    dataset_id: str
    approved_config: ApprovedConfig
    timeout_seconds: int = Field(default=3600, ge=1, le=86400)
    cpu_only: bool = False

    @field_validator("run_id", "source_config_id", "dataset_id")
    @classmethod
    def safe_token(cls, value: str) -> str:
        if not value or not all(char.isalnum() or char in "_.-" for char in value):
            raise ValueError("identifier contains unsafe characters")
        return value

    @model_validator(mode="after")
    def approved_config_matches_request(self) -> "PIDSDetectionRequest":
        if self.approved_config.pids != self.pids:
            raise ValueError("ApprovedConfig PIDS does not match request")
        if self.approved_config.source_config_id != self.source_config_id:
            raise ValueError("ApprovedConfig source config does not match request")
        if self.approved_config.dataset_id != self.dataset_id:
            raise ValueError("ApprovedConfig dataset does not match request")
        if self.split not in self.approved_config.approved_splits:
            raise ValueError("ApprovedConfig is not frozen for the requested split")
        return self


@dataclass(frozen=True)
class ExecutionOutcome:
    tool_result: ToolResult
    artifact_manifest: ArtifactManifest
    run_directory: Path


ProcessRunner = Callable[..., subprocess.CompletedProcess[str]]


def _default_runner(argv: Sequence[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, shell=False, check=False, text=True, capture_output=True, **kwargs)


class PIDSMakerAdapter:
    """Construct and execute allowlisted PIDSMaker argv without a shell."""

    def __init__(
        self,
        project_root: Path,
        artifact_root: Path,
        python_executable: Path,
        *,
        cuda_visible_devices: str | None = None,
        runner: ProcessRunner = _default_runner,
        execution_enabled: bool = False,
    ) -> None:
        self.project_root = project_root.resolve()
        self.pidsmaker_root = (self.project_root / "PIDSMaker").resolve()
        self.artifact_root = artifact_root.resolve()
        self.python_executable = python_executable.resolve()
        self.cuda_visible_devices = cuda_visible_devices
        self.runner = runner
        self.execution_enabled = execution_enabled
        self.discovery = PIDSMakerDiscovery(self.project_root)

    def validate_request(self, request: PIDSDetectionRequest) -> None:
        by_source = {item.source_config_id: item for item in self.discovery.capabilities()}
        capability = by_source.get(request.source_config_id)
        if capability is None:
            raise ValueError("source config is not registered at the pinned commit")
        if capability.pids != request.pids:
            raise ValueError("PIDS identity does not match discovered source config")
        if request.dataset_id not in self.discovery.dataset_ids():
            raise ValueError("dataset is not registered by PIDSMaker")
        if request.split in {DataSplit.HELD_OUT, DataSplit.DEPLOYMENT}:
            if request.approved_config.checkpoint_hash is None:
                raise ValueError("held-out/deployment detection requires a frozen checkpoint")

        allowed_parameters = {item.name for item in capability.configurable_parameters}
        for key, value in request.approved_config.parameters.items():
            lowered_parts = set(key.lower().split("."))
            if lowered_parts & FORBIDDEN_OVERRIDE_PARTS:
                raise ValueError(f"override {key} is executor-owned or prohibited")
            if key not in allowed_parameters:
                raise ValueError(f"override {key} is not present in resolved upstream config")
            if not isinstance(value, (str, int, float, bool)) or isinstance(value, (list, dict)):
                raise ValueError(f"override {key} must be a scalar")
            if isinstance(value, str) and ("\x00" in value or "\n" in value or "\r" in value):
                raise ValueError(f"override {key} contains control characters")

    def run_directory(self, request: PIDSDetectionRequest) -> Path:
        candidate = (self.artifact_root / request.run_id).resolve()
        if candidate.parent != self.artifact_root:
            raise ValueError("run directory escaped artifact root")
        return candidate

    def build_argv(self, request: PIDSDetectionRequest) -> tuple[str, ...]:
        self.validate_request(request)
        run_directory = self.run_directory(request)
        argv = [
            str(self.python_executable),
            "pidsmaker/main.py",
            request.source_config_id,
            request.dataset_id,
            "--artifact_dir",
            str(run_directory / "pidsmaker"),
        ]
        if request.cpu_only:
            argv.append("--cpu")
        for key in sorted(request.approved_config.parameters):
            value = request.approved_config.parameters[key]
            rendered = str(value) if not isinstance(value, bool) else ("True" if value else "False")
            argv.append(f"--{key}={rendered}")
        return tuple(argv)

    def execution_environment(self) -> dict[str, str]:
        environment = {"PATH": os.environ.get("PATH", "")}
        environment["WANDB_MODE"] = "disabled"
        environment["WANDB_SILENT"] = "true"
        if self.cuda_visible_devices is not None:
            environment["CUDA_VISIBLE_DEVICES"] = self.cuda_visible_devices
        return environment

    def execute(self, request: PIDSDetectionRequest) -> ExecutionOutcome:
        if not self.execution_enabled:
            raise RuntimeError(
                "PIDSMaker execution is disabled until database credentials use an approved injection mode"
            )
        argv = self.build_argv(request)
        run_directory = self.run_directory(request)
        run_directory.mkdir(parents=True, exist_ok=False)
        started_at = datetime.now(timezone.utc)
        command_path = run_directory / "command.txt"
        command_path.write_text(shlex.join(argv) + "\n")
        try:
            completed = self.runner(
                argv,
                cwd=str(self.pidsmaker_root),
                env=self.execution_environment(),
                timeout=request.timeout_seconds,
            )
            exit_code = completed.returncode
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            status = RunStatus.SUCCEEDED if exit_code == 0 else RunStatus.FAILED
            error = None if status == RunStatus.SUCCEEDED else f"PIDSMaker exited with code {exit_code}"
        except subprocess.TimeoutExpired as exc:
            exit_code = None
            stdout = self._text_output(exc.stdout)
            stderr = self._text_output(exc.stderr)
            status = RunStatus.FAILED
            error = f"PIDSMaker timed out after {request.timeout_seconds}s"
        except OSError as exc:
            exit_code = None
            stdout = ""
            stderr = ""
            status = RunStatus.FAILED
            error = f"PIDSMaker process could not start: {type(exc).__name__}"
        (run_directory / "stdout.log").write_text(stdout)
        (run_directory / "stderr.log").write_text(stderr)
        ended_at = datetime.now(timezone.utc)

        raw_pids_files = tuple(
            item for item in (run_directory / "pidsmaker").rglob("*") if item.is_file()
        ) if (run_directory / "pidsmaker").is_dir() else ()
        if status == RunStatus.SUCCEEDED and not raw_pids_files:
            status = RunStatus.FAILED
            error = "PIDSMaker exited successfully but produced no artifacts"

        artifacts: list[ArtifactRecord] = []
        for path in sorted(item for item in run_directory.rglob("*") if item.is_file()):
            relative = path.relative_to(run_directory).as_posix()
            content = path.read_bytes()
            pids_related = path.is_relative_to(run_directory / "pidsmaker")
            artifacts.append(
                ArtifactRecord(
                    artifact_id=f"{request.run_id}-{hashlib.sha256(relative.encode()).hexdigest()[:16]}",
                    artifact_type="execution_log" if path.suffix in {".log", ".txt"} else "raw_pidsmaker",
                    relative_path=relative,
                    content_hash=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                    producing_stage="adapter_execution",
                    pids_related=pids_related,
                    source_config_id=request.source_config_id,
                    checkpoint_hash=request.approved_config.checkpoint_hash,
                    created_at=ended_at,
                )
            )
        manifest_id = f"artifacts-{request.run_id}"
        manifest = ArtifactManifest(
            manifest_id=manifest_id,
            run_id=request.run_id,
            code_commit=self._git_commit(self.project_root),
            pidsmaker_commit=self.discovery.verify_commit(),
            artifacts=tuple(artifacts),
            created_at=ended_at,
        )
        manifest_path = run_directory / "artifact_manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n")
        command_manifest = CommandManifest(
            manifest_id=f"command-{request.run_id}",
            executable_id="pidsmaker-python",
            argv=argv,
            working_directory=str(self.pidsmaker_root),
            injected_environment_keys=tuple(sorted(self.execution_environment())),
        )
        result = ToolResult(
            tool_call_id=request.tool_call_id,
            tool_name=ToolName.RUN_PIDS_DETECTION,
            status=status,
            validated_arguments={
                "pids_id": request.pids.pids_id,
                "variant_id": request.pids.variant_id,
                "dataset_id": request.dataset_id,
                "run_id": request.run_id,
                "cpu_only": request.cpu_only,
            },
            approved_config_id=request.approved_config.config_id,
            checkpoint_hash=request.approved_config.checkpoint_hash,
            command_manifest=command_manifest,
            started_at=started_at,
            ended_at=ended_at,
            exit_code=exit_code,
            artifact_ids=tuple(item.artifact_id for item in artifacts),
            standardized_observation={"artifact_manifest_id": manifest_id, "exit_code": exit_code},
            sanitized_error=error,
        )
        (run_directory / "tool_result.json").write_text(result.model_dump_json(indent=2) + "\n")
        return ExecutionOutcome(result, manifest, run_directory)

    @staticmethod
    def _git_commit(root: Path) -> str:
        return subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    @staticmethod
    def _text_output(value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode(errors="replace")
        return value
