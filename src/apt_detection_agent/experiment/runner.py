"""Deployment-visible side of the synthetic multi-window integration scenario.

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001..004,
REQ-WINDOW-001..004, REQ-CONFIG-001..003, REQ-MEMORY-001..007,
REQ-TOOL-001..005, REQ-ARTIFACT-001..003, REQ-REPRO-001..002.

This module deliberately never imports ``apt_detection_agent.evaluation``. Hidden
fixture construction and metric computation belong to a separate process and root.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shlex
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import field_validator

from apt_detection_agent.runtime import TrajectoryLogger
from .legacy_controller import Controller, ControllerConfig
from apt_detection_agent.data import CausalWindowStream, VisibleEvent
from apt_detection_agent.memory import (
    CaseMemoryStore,
    MemoryNamespace,
    MemoryQuery,
    normalized_content_hash,
)
from apt_detection_agent.schemas import (
    ActionType,
    AgentAction,
    ArtifactManifest,
    ArtifactRecord,
    CaseState,
    DataSplit,
    DetectionAlert,
    DetectionUnit,
    MemoryLayer,
    MemoryRecord,
    Observation,
    PIDSRef,
    Prediction,
    RunStatus,
    ScoreSummary,
    TimeWindow,
    ToolName,
    ToolRequest,
    ToolResult,
)
from apt_detection_agent.schemas.common import StrictModel


ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)
WINDOW_SECONDS = 15 * 60
ARTIFACT_MANIFEST_ID = "synthetic-agent-artifacts-v1"
PINNED_PIDS_SHA = "32602734bc9f896be5fc0f03f0a185c967cd6624"


class SyntheticScenarioConfig(StrictModel):
    run_id: str
    run_root: Path
    project_root: Path
    scenario_id: str = "synthetic-scenario-1"
    episode_id: str = "synthetic-episode-1"
    initial_config_id: str = "synthetic-config-a"
    next_config_id: str = "synthetic-config-b"

    @field_validator("run_id")
    @classmethod
    def safe_run_id(cls, value: str) -> str:
        if not value or not all(char.isalnum() or char in "_.-" for char in value):
            raise ValueError("run_id contains unsafe characters")
        return value


@dataclass
class SyntheticScenarioRunner:
    config: SyntheticScenarioConfig

    @property
    def run_directory(self) -> Path:
        root = self.config.run_root.resolve()
        candidate = (root / self.config.run_id).resolve()
        if candidate.parent != root:
            raise ValueError("run directory escaped approved root")
        return candidate

    def run(self) -> Path:
        run_dir = self.run_directory
        if not self.config.run_root.resolve().is_dir():
            raise ValueError("run root must already exist")
        run_dir.mkdir(parents=False, exist_ok=False)
        self._write_initial_manifests(run_dir)

        namespace = MemoryNamespace(
            split=DataSplit.HELD_OUT,
            scenario_id=self.config.scenario_id,
            episode_id=self.config.episode_id,
        )
        case = CaseState(
            case_id="synthetic-case-1",
            scenario_id=self.config.scenario_id,
            episode_id=self.config.episode_id,
            split=DataSplit.HELD_OUT,
            current_window_sequence=0,
            committed_config_id=self.config.initial_config_id,
            memory_namespace=namespace.key,
            updated_at=ORIGIN,
        )
        stream = CausalWindowStream(
            scenario_id=self.config.scenario_id,
            episode_id=self.config.episode_id,
            split=DataSplit.HELD_OUT,
        )
        tool_calls_path = run_dir / "tool_calls.jsonl"
        trajectory_path = run_dir / "trajectory.jsonl"
        controller = Controller(
            config=ControllerConfig(
                max_tool_attempts=2,
                slow_path_alert_count=1,
                periodic_check_window_count=99,
                trigger_profile_id="synthetic-validation-derived-trigger-v1",
                trigger_source_split=DataSplit.VALIDATION,
            ),
            fast_path=self._fast_path,
            policy=self._policy,
            tool_executor=lambda request: self._tool_executor(request, tool_calls_path),
            trajectory_logger=TrajectoryLogger(trajectory_path),
        )

        observations: list[Observation] = []
        tool_results: list[ToolResult] = []
        retrieved_memory_ids: tuple[str, ...] = ()
        with CaseMemoryStore(run_dir / "case_memory.sqlite3") as store:
            store.create_case(case)
            for sequence in range(4):
                case = store.get_case(case.case_id)
                current_window = self._window(sequence)
                events = (self._event(sequence, current_window),)
                stream.open_next(
                    window=current_window,
                    events=events,
                    committed_config_id=case.committed_config_id,
                    observed_at=current_window.end,
                )
                if sequence == 2:
                    retrieved = store.retrieve(
                        MemoryQuery(
                            query="capability inspection",
                            namespace=namespace,
                            environment="synthetic-autodl-profile",
                            pids_id="velox",
                        )
                    )
                    retrieved_memory_ids = tuple(item.memory_id for item in retrieved.records)
                observation = self._observation(
                    sequence,
                    current_window,
                    case,
                    retrieved_memory_ids if sequence == 2 else (),
                )
                observations.append(observation)
                result = controller.run_step(
                    observation,
                    case,
                    step_number=sequence,
                    started_at=current_window.end,
                    ended_at=current_window.end + timedelta(seconds=1),
                )
                stream.commit_prediction(result.prediction)
                tool_results.extend(result.tool_results)
                if result.next_case != case:
                    store.update_case(result.next_case)
                    case = result.next_case
                if sequence == 1:
                    memory = self._memory_record(current_window.end + timedelta(seconds=1))
                    store.write_runtime(memory, namespace)
                if sequence < 3:
                    case = store.advance_case(
                        case.case_id,
                        next_sequence=sequence + 1,
                        updated_at=current_window.end + timedelta(seconds=2),
                    )

            final_case = store.get_case(case.case_id)
            (run_dir / "case_final.json").write_text(final_case.model_dump_json(indent=2) + "\n")
            reset_memories, reset_cases = store.reset_episode(namespace)
            lifecycle = {
                "namespace": namespace.key,
                "reset_memories": reset_memories,
                "reset_cases": reset_cases,
                "remaining_runtime_or_static_records": store.count(),
            }
            (run_dir / "lifecycle.json").write_text(
                json.dumps(lifecycle, indent=2, sort_keys=True) + "\n"
            )

        predictions = stream.predictions
        with (run_dir / "predictions.jsonl").open("w") as handle:
            for prediction in predictions:
                handle.write(prediction.model_dump_json() + "\n")
        summary = self._validate_invariants(
            observations=tuple(observations),
            predictions=predictions,
            tool_results=tuple(tool_results),
            retrieved_memory_ids=retrieved_memory_ids,
            lifecycle=lifecycle,
        )
        (run_dir / "agent_summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
        (run_dir / "summary.md").write_text(self._summary_markdown(summary))
        (run_dir / "agent_status.json").write_text(
            json.dumps(
                {
                    "run_id": self.config.run_id,
                    "status": "awaiting_hidden_evaluator",
                    "evidence_class": "synthetic_integration_only",
                    "formal_performance_claim": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        return run_dir

    @staticmethod
    def _window(sequence: int) -> TimeWindow:
        start = ORIGIN + timedelta(seconds=sequence * WINDOW_SECONDS)
        return TimeWindow(
            window_id=f"synthetic-window-{sequence}",
            sequence_number=sequence,
            origin_time=ORIGIN,
            timezone="UTC",
            window_size_seconds=WINDOW_SECONDS,
            start=start,
            end=start + timedelta(seconds=WINDOW_SECONDS),
        )

    def _event(self, sequence: int, window: TimeWindow) -> VisibleEvent:
        entities = ("node-d", "node-a", "node-c", "node-b")
        return VisibleEvent(
            event_id=f"synthetic-event-{sequence}",
            scenario_id=self.config.scenario_id,
            occurred_at=window.start + timedelta(minutes=1),
            event_type="process-activity",
            entity_ids=(entities[sequence],),
            attributes={"observable_operation": "exec", "event_count": sequence + 1},
        )

    def _observation(
        self,
        sequence: int,
        window: TimeWindow,
        case: CaseState,
        memory_ids: tuple[str, ...],
    ) -> Observation:
        alert_entities = {1: "node-a", 2: "node-c", 3: "node-b"}
        alerts: tuple[DetectionAlert, ...] = ()
        if sequence in alert_entities:
            alerts = (
                DetectionAlert(
                    alert_id=f"synthetic-alert-{sequence}",
                    entity_id=alert_entities[sequence],
                    detection_unit=DetectionUnit.NODE,
                    score=(0.9, 0.8, 0.7)[sequence - 1],
                    threshold_id="synthetic-frozen-threshold-v1",
                    evidence_artifact_ids=(f"visible-evidence-{sequence}",),
                ),
            )
        scores = [alert.score for alert in alerts]
        return Observation(
            observation_id=f"synthetic-observation-{sequence}",
            scenario_id=self.config.scenario_id,
            episode_id=self.config.episode_id,
            split=DataSplit.HELD_OUT,
            observed_at=window.end,
            window=window,
            environment_profile_id="synthetic-autodl-profile",
            committed_config_id=case.committed_config_id,
            active_pids=(PIDSRef(pids_id="velox"),),
            score_summary=ScoreSummary(
                count=len(scores),
                minimum=min(scores) if scores else None,
                maximum=max(scores) if scores else None,
                mean=sum(scores) / len(scores) if scores else None,
            ),
            alerts=alerts,
            observable_failures=("observable-output-degenerate",) if sequence == 2 else (),
            case_summary="Synthetic case state contains deployment-visible evidence only.",
            memory_record_ids=memory_ids,
        )

    @staticmethod
    def _fast_path(observation: Observation, case: CaseState) -> Prediction:
        return Prediction(
            prediction_id=f"synthetic-prediction-{observation.window.sequence_number}",
            case_id=case.case_id,
            scenario_id=case.scenario_id,
            episode_id=case.episode_id,
            split=case.split,
            window_id=observation.window.window_id,
            window_sequence_number=observation.window.sequence_number,
            committed_config_id=case.committed_config_id,
            pids=observation.active_pids,
            alert_entity_ids=tuple(alert.entity_id for alert in observation.alerts),
            created_at=observation.observed_at,
            artifact_manifest_id=ARTIFACT_MANIFEST_ID,
        )

    def _policy(self, observation: Observation, case: CaseState, trigger: object) -> AgentAction:
        sequence = observation.window.sequence_number
        common = {
            "case_id": case.case_id,
            "window_id": observation.window.window_id,
            "based_on_observation_id": observation.observation_id,
            "deployment_evidence_ids": (observation.observation_id,),
        }
        if sequence == 1:
            request = ToolRequest(
                tool_call_id="synthetic-tool-call-1",
                tool_name=ToolName.INSPECT_PIDS_AVAILABILITY,
                case_id=case.case_id,
                scenario_id=case.scenario_id,
                episode_id=case.episode_id,
                window_id=observation.window.window_id,
                arguments={"pids_id": "velox", "variant_id": "default"},
                requested_at=observation.observed_at,
            )
            return AgentAction(
                action_id="synthetic-action-tool-1",
                action_type=ActionType.RUN_TOOL,
                rationale="Observable alert volume triggers a capability inspection.",
                tool_request=request,
                **common,
            )
        if sequence == 2:
            return AgentAction(
                action_id="synthetic-action-reconfigure-2",
                action_type=ActionType.SCHEDULE_RECONFIGURATION,
                rationale="Observable output failure schedules a frozen alternative next window.",
                pending_config_id=self.config.next_config_id,
                effective_sequence_number=3,
                **common,
            )
        return AgentAction(
            action_id=f"synthetic-action-no-change-{sequence}",
            action_type=ActionType.NO_CHANGE,
            rationale="Committed fast-path output remains the formal current-window prediction.",
            **common,
        )

    @staticmethod
    def _tool_executor(request: ToolRequest, path: Path) -> ToolResult:
        result = ToolResult(
            tool_call_id=request.tool_call_id,
            tool_name=request.tool_name,
            status=RunStatus.SUCCEEDED,
            validated_arguments=request.arguments,
            started_at=request.requested_at,
            ended_at=request.requested_at + timedelta(milliseconds=10),
            exit_code=0,
            artifact_ids=("synthetic-capability-artifact-1",),
            standardized_observation={
                "pids_id": "velox",
                "availability": "unavailable",
                "reason_code": "checkpoint_missing",
            },
        )
        with path.open("a") as handle:
            handle.write(result.model_dump_json() + "\n")
        return result

    def _memory_record(self, created_at: datetime) -> MemoryRecord:
        content = "Capability inspection found a missing checkpoint; keep the committed fast path."
        return MemoryRecord(
            memory_id="synthetic-episode-memory-1",
            layer=MemoryLayer.EPISODE,
            split=DataSplit.HELD_OUT,
            scenario_id=self.config.scenario_id,
            episode_id=self.config.episode_id,
            environment="synthetic-autodl-profile",
            observable_behavior="capability inspection returned checkpoint missing",
            pids=PIDSRef(pids_id="velox"),
            action="retain committed configuration",
            content=content,
            normalized_content_hash=normalized_content_hash(content),
            evidence_artifact_ids=("synthetic-capability-artifact-1",),
            created_at=created_at,
        )

    def _validate_invariants(
        self,
        *,
        observations: tuple[Observation, ...],
        predictions: tuple[Prediction, ...],
        tool_results: tuple[ToolResult, ...],
        retrieved_memory_ids: tuple[str, ...],
        lifecycle: dict[str, object],
    ) -> dict[str, object]:
        sequences = [item.window_sequence_number for item in predictions]
        configs = [item.committed_config_id for item in predictions]
        checks = {
            "chronological_contiguous_windows": sequences == [0, 1, 2, 3],
            "append_only_prediction_count": len(predictions) == 4,
            "current_window_config_not_rewritten": configs[:3]
            == [self.config.initial_config_id] * 3,
            "next_window_config_effective": configs[3] == self.config.next_config_id,
            "slow_path_tool_is_structured": len(tool_results) == 1
            and tool_results[0].tool_name == ToolName.INSPECT_PIDS_AVAILABILITY,
            "episode_memory_retrieved": retrieved_memory_ids == ("synthetic-episode-memory-1",),
            "memory_visible_only_in_later_window": observations[2].memory_record_ids
            == retrieved_memory_ids,
            "episode_state_reset": lifecycle["reset_memories"] == 1
            and lifecycle["reset_cases"] == 1,
            "synthetic_not_formal_performance": True,
        }
        if not all(checks.values()):
            failed = sorted(name for name, passed in checks.items() if not passed)
            raise RuntimeError(f"synthetic invariants failed: {failed}")
        return {
            "schema_version": "synthetic-e2e-v1",
            "run_id": self.config.run_id,
            "scenario_id": self.config.scenario_id,
            "episode_id": self.config.episode_id,
            "prediction_count": len(predictions),
            "tool_call_count": len(tool_results),
            "committed_config_history": configs,
            "retrieved_memory_ids": list(retrieved_memory_ids),
            "checks": checks,
            "evidence_class": "synthetic_integration_only",
            "formal_performance_claim": False,
        }

    @staticmethod
    def _summary_markdown(summary: dict[str, object]) -> str:
        checks = summary["checks"]
        lines = [
            "# Synthetic end-to-end validation summary",
            "",
            "This run is integration evidence only; it is not formal model performance.",
            "",
        ]
        lines.extend(f"- {name}: {'PASS' if passed else 'FAIL'}" for name, passed in checks.items())
        return "\n".join(lines) + "\n"

    def _write_initial_manifests(self, run_dir: Path) -> None:
        root = self.config.project_root.resolve()
        commit = self._git(root, "rev-parse", "HEAD")
        diff = self._git(root, "diff", "--binary")
        (run_dir / "command.txt").write_text(shlex.join(sys.argv) + "\n")
        (run_dir / "git_commit.txt").write_text(commit + "\n")
        (run_dir / "git_diff.patch").write_text(diff)
        (run_dir / "environment.json").write_text(
            json.dumps(
                {
                    "python": platform.python_version(),
                    "platform": platform.platform(),
                    "controller_runtime": "current_python",
                    "pids_runtime_imported": False,
                    "vllm_runtime_imported": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        profile = root / "configs" / "resource_profiles" / "autodl.yaml"
        (run_dir / "resource_profile.yaml").write_text(profile.read_text())
        (run_dir / "config_resolved.yaml").write_text(
            json.dumps(self.config.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
        )
        (run_dir / "data_manifest.json").write_text(
            json.dumps(
                {
                    "dataset_id": "synthetic-visible-fixture-v1",
                    "window_count": 4,
                    "origin_time": ORIGIN.isoformat(),
                    "timezone": "UTC",
                    "window_size_seconds": WINDOW_SECONDS,
                    "boundary": "[start,end)",
                    "contains_private_labels": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        (run_dir / "stdout.log").write_text("")
        (run_dir / "stderr.log").write_text("")

    @staticmethod
    def _git(root: Path, *arguments: str) -> str:
        return subprocess.run(
            ("git", "-C", str(root), *arguments),
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()


def write_synthetic_artifact_manifest(
    *, run_dir: Path, project_root: Path, run_id: str
) -> ArtifactManifest:
    """Finalize the manifest only after sanitized evaluator feedback/reporting."""

    manifest_path = run_dir / "artifact_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(manifest_path)
    created_at = ORIGIN + timedelta(seconds=4 * WINDOW_SECONDS + 3)
    artifacts = []
    for path in sorted(item for item in run_dir.iterdir() if item.is_file()):
        if path.name in {"artifact_manifest.json", "run_status.json"}:
            continue
        content = path.read_bytes()
        artifacts.append(
            ArtifactRecord(
                artifact_id=f"synthetic-{hashlib.sha256(path.name.encode()).hexdigest()[:16]}",
                artifact_type="synthetic_integration_artifact",
                relative_path=path.name,
                content_hash=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
                producing_stage="synthetic_end_to_end_validation",
                created_at=created_at,
            )
        )
    commit = SyntheticScenarioRunner._git(project_root.resolve(), "rev-parse", "HEAD")
    manifest = ArtifactManifest(
        manifest_id=ARTIFACT_MANIFEST_ID,
        run_id=run_id,
        code_commit=commit,
        pidsmaker_commit=PINNED_PIDS_SHA,
        artifacts=tuple(artifacts),
        created_at=created_at,
    )
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n")
    return manifest
