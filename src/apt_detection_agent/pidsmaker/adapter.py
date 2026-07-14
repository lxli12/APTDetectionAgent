"""Validated argv construction and PIDSMaker subprocess execution.

Requirements: REQ-TOOL-001..005, REQ-PIDS-004..005,
REQ-ARTIFACT-001..003, REQ-WANDB-001, REQ-RESOURCE-002.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

from pydantic import Field, field_validator, model_validator

from apt_detection_agent.schemas import (
    ApprovedConfig,
    ArtifactManifest,
    ArtifactRecord,
    CommandManifest,
    DataSplit,
    PIDSRef,
    PipelineStage,
    RunStatus,
    StageTrace,
    ThresholdProvenance,
    TimeWindow,
    ToolName,
    ToolResult,
)
from apt_detection_agent.schemas.common import StrictModel

from .discovery import PIDSMakerDiscovery
from .results import standardize_frozen_test_scores


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
MAX_PROJECT_CPU_VCPUS = 32
DEFAULT_PIDS_CPU_THREADS = 16
NUMERIC_THREAD_ENV = (
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


class PIDSDetectionRequest(StrictModel):
    request_id: str
    tool_call_id: str
    case_id: str
    scenario_id: str
    episode_id: str
    window_id: str
    window: TimeWindow
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
        if self.window.window_id != self.window_id:
            raise ValueError("request window identity does not match the typed window")
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
        cpu_thread_limit: int = DEFAULT_PIDS_CPU_THREADS,
        runner: ProcessRunner = _default_runner,
        execution_enabled: bool = False,
        compatibility_root: Path | None = None,
        frozen_bundle_root: Path | None = None,
        approved_bundles: Mapping[str, Path] | None = None,
        database_environment: Mapping[str, str] | None = None,
        nltk_data_root: Path | None = None,
        code_commit: str | None = None,
    ) -> None:
        self.project_root = project_root.resolve()
        self.pidsmaker_root = (self.project_root / "PIDSMaker").resolve()
        self.artifact_root = artifact_root.resolve()
        self.python_executable = python_executable.resolve()
        self.cuda_visible_devices = cuda_visible_devices
        if not 1 <= cpu_thread_limit <= MAX_PROJECT_CPU_VCPUS:
            raise ValueError("PIDSMaker CPU thread limit must be within the project quota")
        self.cpu_thread_limit = cpu_thread_limit
        self.runner = runner
        self.execution_enabled = execution_enabled
        self.compatibility_root = compatibility_root.resolve() if compatibility_root else None
        self.frozen_bundle_root = frozen_bundle_root.resolve() if frozen_bundle_root else None
        self.approved_bundles = {
            key: value.resolve() for key, value in (approved_bundles or {}).items()
        }
        self.database_environment = dict(database_environment or {})
        self.nltk_data_root = nltk_data_root.resolve() if nltk_data_root else None
        if self.nltk_data_root is not None and not self.nltk_data_root.is_dir():
            raise ValueError("executor-owned NLTK data root is unavailable")
        self.code_commit = code_commit
        self.discovery = PIDSMakerDiscovery(
            self.project_root,
            pidsmaker_root=self.compatibility_root,
        )

    def bundle_for(self, request: PIDSDetectionRequest) -> Path:
        try:
            bundle = self.approved_bundles[request.approved_config.config_id]
        except KeyError as exc:
            raise ValueError("ApprovedConfig has no executor-owned frozen bundle") from exc
        if self.frozen_bundle_root is None or bundle.parent != self.frozen_bundle_root:
            raise ValueError("frozen bundle escaped the executor-owned root")
        if not (bundle / "bundle_manifest.json").is_file():
            raise ValueError("frozen bundle manifest is missing")
        catalog_payload = json.loads((bundle / "approved_config_catalog.json").read_text())
        if not isinstance(catalog_payload, list):
            raise ValueError("frozen ApprovedConfig catalog is malformed")
        matches = [
            ApprovedConfig.model_validate(item)
            for item in catalog_payload
            if isinstance(item, dict) and item.get("config_id") == request.approved_config.config_id
        ]
        if len(matches) != 1 or matches[0] != request.approved_config:
            raise ValueError("request differs from the executor-owned frozen ApprovedConfig")
        return bundle

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
        if self.compatibility_root is None:
            raise ValueError("isolated PIDSMaker compatibility root is required")
        marker = self.compatibility_root / ".apt-pidsmaker-compat.json"
        if not marker.is_file():
            raise ValueError("PIDSMaker execution requires an isolated compatibility build")
        identity = json.loads(marker.read_text())
        if (
            identity.get("upstream_commit") != self.discovery.verify_commit()
            or identity.get("source_submodule_modified") is not False
        ):
            raise ValueError("PIDSMaker compatibility build identity is invalid")
        self.bundle_for(request)

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
        bundle = self.bundle_for(request)
        start_ns = int(request.window.start.timestamp() * 1_000_000_000)
        end_ns = int(request.window.end.timestamp() * 1_000_000_000)
        argv = [
            str(self.python_executable),
            str(self.project_root / "scripts" / "run_frozen_pids_tool.py"),
            request.source_config_id,
            request.dataset_id,
            "--pidsmaker-root",
            str(self.compatibility_root),
            "--artifact-dir",
            str(run_directory / "pids_artifacts" / "pipeline"),
            "--frozen-bundle",
            str(bundle),
            "--checkpoint-hash",
            str(request.approved_config.checkpoint_hash),
            "--test-window-start-ns",
            str(start_ns),
            "--test-window-end-ns",
            str(end_ns),
            "--window-size-seconds",
            str(request.window.window_size_seconds),
        ]
        if request.cpu_only:
            argv.append("--cpu")
        for key in sorted(request.approved_config.parameters):
            value = request.approved_config.parameters[key]
            rendered = str(value) if not isinstance(value, bool) else ("True" if value else "False")
            argv.extend(("--override", f"{key}={rendered}"))
        return tuple(argv)

    def execution_environment(self, run_directory: Path | None = None) -> dict[str, str]:
        environment = {"PATH": os.environ.get("PATH", "")}
        environment["WANDB_MODE"] = "disabled"
        environment["WANDB_SILENT"] = "true"
        environment["APT_PIDS_CPU_THREADS"] = str(self.cpu_thread_limit)
        for name in NUMERIC_THREAD_ENV:
            environment[name] = str(self.cpu_thread_limit)
        if self.cuda_visible_devices is not None:
            environment["CUDA_VISIBLE_DEVICES"] = self.cuda_visible_devices
        environment.update(self.database_environment)
        if self.nltk_data_root is not None:
            environment["NLTK_DATA"] = str(self.nltk_data_root)
        if self.frozen_bundle_root is not None:
            environment["APT_PRE_SFT_BUNDLE_ROOT"] = str(self.frozen_bundle_root)
        if run_directory is not None:
            environment["APT_PIDS_ARTIFACT_ROOT"] = str(
                run_directory / "pids_artifacts"
            )
        return environment

    def execute(self, request: PIDSDetectionRequest) -> ExecutionOutcome:
        if not self.execution_enabled:
            raise RuntimeError(
                "PIDSMaker execution is disabled until database credentials use an approved injection mode"
            )
        argv = self.build_argv(request)
        run_directory = self.run_directory(request)
        run_directory.mkdir(parents=True, exist_ok=False)
        (run_directory / "pids_artifacts").mkdir()
        started_at = datetime.now(timezone.utc)
        command_path = run_directory / "command.txt"
        command_path.write_text(shlex.join(argv) + "\n")
        execution_environment = self.execution_environment(run_directory)
        try:
            completed = self.runner(
                argv,
                cwd=str(self.project_root),
                env=execution_environment,
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
            item for item in (run_directory / "pids_artifacts").rglob("*") if item.is_file()
        ) if (run_directory / "pids_artifacts").is_dir() else ()
        if status == RunStatus.SUCCEEDED and not raw_pids_files:
            status = RunStatus.FAILED
            error = "PIDSMaker exited successfully but produced no artifacts"

        standardized_summary: dict[str, object] = {"exit_code": exit_code}
        if status == RunStatus.SUCCEEDED:
            try:
                threshold_payload = json.loads(
                    (self.bundle_for(request) / "threshold_catalog.json").read_text()
                )
                if not isinstance(threshold_payload, list) or len(threshold_payload) != 1:
                    raise ValueError("frozen threshold catalog must contain exactly one entry")
                threshold = ThresholdProvenance.model_validate(threshold_payload[0])
                detection = standardize_frozen_test_scores(
                    run_directory,
                    threshold,
                    split=request.split,
                    pids=request.pids,
                    window=request.window,
                )
                detection_path = run_directory / "detection_result.json"
                detection_path.write_text(detection.model_dump_json(indent=2) + "\n")
                standardized_summary = {
                    "result_id": detection.result_id,
                    "score_count": len(detection.scored_entities),
                    "alert_count": sum(item.alerted for item in detection.scored_entities),
                    "threshold_id": detection.threshold.threshold_id,
                    "window_id": detection.window.window_id,
                    "detection_result_relative_path": detection_path.relative_to(
                        run_directory
                    ).as_posix(),
                }
            except (ValueError, KeyError, FileNotFoundError, json.JSONDecodeError) as exc:
                status = RunStatus.FAILED
                error = f"PIDSMaker output standardization failed: {type(exc).__name__}"

        artifacts: list[ArtifactRecord] = []
        for path in sorted(item for item in run_directory.rglob("*") if item.is_file()):
            relative = path.relative_to(run_directory).as_posix()
            content = path.read_bytes()
            pids_related = path.is_relative_to(run_directory / "pids_artifacts")
            artifacts.append(
                ArtifactRecord(
                    artifact_id=f"{request.run_id}-{hashlib.sha256(relative.encode()).hexdigest()[:16]}",
                    artifact_type="execution_log" if path.suffix in {".log", ".txt"} else "raw_pidsmaker",
                    relative_path=relative,
                    content_hash=hashlib.sha256(content).hexdigest(),
                    size_bytes=len(content),
                    producing_stage=self._producing_stage(relative),
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
            code_commit=self.code_commit or self._git_commit(self.project_root),
            pidsmaker_commit=self.discovery.verify_commit(),
            artifacts=tuple(artifacts),
            created_at=ended_at,
        )
        manifest_path = run_directory / "artifact_manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n")
        artifact_ids_by_path = {item.relative_path: item.artifact_id for item in artifacts}
        stage_trace: tuple[StageTrace, ...] = ()
        if status == RunStatus.SUCCEEDED:
            try:
                stage_trace = self._stage_trace(
                    run_directory,
                    started_at,
                    ended_at,
                    artifact_ids_by_path,
                )
            except (ValueError, KeyError, FileNotFoundError, json.JSONDecodeError) as exc:
                status = RunStatus.FAILED
                error = f"PIDSMaker stage trace validation failed: {type(exc).__name__}"
        command_manifest = CommandManifest(
            manifest_id=f"command-{request.run_id}",
            executable_id="pidsmaker-python",
            argv=argv,
            working_directory=str(self.project_root),
            injected_environment_keys=tuple(
                sorted(
                    key
                    for key in execution_environment
                    if not any(token in key.upper() for token in ("PASSWORD", "SECRET", "TOKEN"))
                )
            ),
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
            stdout_artifact_id=artifact_ids_by_path.get("stdout.log"),
            stderr_artifact_id=artifact_ids_by_path.get("stderr.log"),
            artifact_ids=tuple(item.artifact_id for item in artifacts),
            stage_trace=stage_trace,
            standardized_observation={
                "artifact_manifest_id": manifest_id,
                **standardized_summary,
            },
            sanitized_error=error,
        )
        (run_directory / "tool_result.json").write_text(result.model_dump_json(indent=2) + "\n")
        (run_directory / "tool_calls.jsonl").write_text(result.model_dump_json() + "\n")
        return ExecutionOutcome(result, manifest, run_directory)

    @staticmethod
    def _producing_stage(relative_path: str) -> str:
        parts = Path(relative_path).parts
        for stage in (
            "construction",
            "transformation",
            "featurization",
            "feat_inference",
            "training",
        ):
            if stage in parts:
                return "inference" if stage == "training" else stage
        if relative_path == "detection_result.json":
            return "detection"
        return "adapter_execution"

    @staticmethod
    def _stage_trace(
        run_directory: Path,
        started_at: datetime,
        ended_at: datetime,
        artifact_ids_by_path: Mapping[str, str],
    ) -> tuple[StageTrace, ...]:
        pipeline = run_directory / "pids_artifacts" / "pipeline"
        stage_summary = json.loads((pipeline / "stage_summary.json").read_text())
        completed = stage_summary.get("completed_stages")
        if not isinstance(completed, list):
            raise ValueError("PIDSMaker stage summary is malformed")
        pending: list[tuple[PipelineStage, float, tuple[str, ...]]] = []
        for item in completed:
            if not isinstance(item, dict):
                raise ValueError("PIDSMaker stage trace entry is malformed")
            stage = PipelineStage(str(item["stage"]))
            elapsed = float(item.get("elapsed_seconds", 0.0))
            artifact_ids = tuple(
                artifact_id
                for path, artifact_id in artifact_ids_by_path.items()
                if stage.value in Path(path).parts
            )
            pending.append((stage, max(0.0, elapsed), artifact_ids))
        inference = json.loads((pipeline / "inference_stage_summary.json").read_text())
        pending.append(
            (
                PipelineStage.INFERENCE,
                max(0.0, float(inference["elapsed_seconds"])),
                tuple(
                    artifact_id
                    for path, artifact_id in artifact_ids_by_path.items()
                    if "training" in Path(path).parts
                ),
            )
        )
        total_weight = sum(weight for _stage, weight, _artifacts in pending)
        if total_weight <= 0.0:
            total_weight = float(len(pending))
            pending = [(stage, 1.0, artifacts) for stage, _weight, artifacts in pending]
        available_seconds = max(0.0, (ended_at - started_at).total_seconds())
        cursor = started_at
        cumulative_weight = 0.0
        traces: list[StageTrace] = []
        for index, (stage, weight, artifact_ids) in enumerate(pending):
            cumulative_weight += weight
            stage_end = (
                ended_at
                if index == len(pending) - 1
                else started_at
                + timedelta(seconds=available_seconds * cumulative_weight / total_weight)
            )
            traces.append(
                StageTrace(
                    stage=stage,
                    status=RunStatus.SUCCEEDED,
                    started_at=cursor,
                    ended_at=stage_end,
                    artifact_ids=artifact_ids,
                )
            )
            cursor = stage_end
        return tuple(traces)

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
