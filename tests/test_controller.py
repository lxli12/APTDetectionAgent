"""Phase 5 controller, scheduler, retry, and trajectory tests.

Requirements: REQ-TOOL-001..005, REQ-CONFIG-001,
REQ-RESOURCE-001..003, REQ-REPRO-001..002, REQ-LABEL-004.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apt_detection_agent.experiment.legacy_controller import (
    Controller,
    ControllerConfig,
)
from apt_detection_agent.runtime import (
    ResourceProfile, ResourceRequest, ResourceScheduler, TrajectoryLogger, WorkloadKind,
)
from apt_detection_agent.schemas import (
    ActionType,
    AgentAction,
    CaseState,
    DataSplit,
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


ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)


def observation(sequence: int = 4, failures: tuple[str, ...] = ()) -> Observation:
    start = ORIGIN + timedelta(minutes=15 * sequence)
    window = TimeWindow(
        window_id=f"window-{sequence}",
        sequence_number=sequence,
        origin_time=ORIGIN,
        timezone="UTC",
        window_size_seconds=900,
        start=start,
        end=start + timedelta(minutes=15),
    )
    return Observation(
        observation_id=f"observation-{sequence}",
        scenario_id="scenario-1",
        episode_id="episode-1",
        split=DataSplit.HELD_OUT,
        observed_at=window.end,
        window=window,
        environment_profile_id="autodl-profile",
        committed_config_id="config-old",
        active_pids=(PIDSRef(pids_id="velox"),),
        score_summary=ScoreSummary(count=0),
        observable_failures=failures,
    )


def case(sequence: int = 4) -> CaseState:
    return CaseState(
        case_id="case-1",
        scenario_id="scenario-1",
        episode_id="episode-1",
        split=DataSplit.HELD_OUT,
        current_window_sequence=sequence,
        committed_config_id="config-old",
        memory_namespace="runtime:held_out:scenario-1:episode-1",
        updated_at=ORIGIN,
    )


def fast_path(obs: Observation, state: CaseState) -> Prediction:
    return Prediction(
        prediction_id=f"prediction-{obs.window.sequence_number}",
        case_id=state.case_id,
        scenario_id=state.scenario_id,
        episode_id=state.episode_id,
        split=state.split,
        window_id=obs.window.window_id,
        window_sequence_number=obs.window.sequence_number,
        committed_config_id=state.committed_config_id,
        pids=obs.active_pids,
        alert_entity_ids=(),
        created_at=obs.observed_at,
        artifact_manifest_id=f"manifest-{obs.window.sequence_number}",
    )


def no_change_policy(obs: Observation, state: CaseState, trigger: object) -> AgentAction:
    return AgentAction(
        action_id=f"action-{obs.window.sequence_number}",
        action_type=ActionType.NO_CHANGE,
        case_id=state.case_id,
        window_id=obs.window.window_id,
        rationale="No deployment-visible trigger requires a slow path.",
        based_on_observation_id=obs.observation_id,
        deployment_evidence_ids=(obs.observation_id,),
    )


def tool_result(request: ToolRequest, status: RunStatus) -> ToolResult:
    return ToolResult(
        tool_call_id=request.tool_call_id,
        tool_name=request.tool_name,
        status=status,
        validated_arguments=request.arguments,
        approved_config_id=request.approved_config_id,
        started_at=ORIGIN,
        ended_at=ORIGIN,
        exit_code=0 if status == RunStatus.SUCCEEDED else 1,
        sanitized_error=None if status == RunStatus.SUCCEEDED else "synthetic failure",
    )


class ControllerTests(unittest.TestCase):
    def controller(self, path: Path, policy=no_change_policy, executor=None) -> Controller:
        return Controller(
            config=ControllerConfig(
                max_tool_attempts=2,
                slow_path_alert_count=1,
                periodic_check_window_count=5,
                trigger_profile_id="validated-trigger-v1",
                trigger_source_split=DataSplit.VALIDATION,
            ),
            fast_path=fast_path,
            policy=policy,
            tool_executor=executor or (lambda request: tool_result(request, RunStatus.SUCCEEDED)),
            trajectory_logger=TrajectoryLogger(path),
        )

    def test_fast_path_and_append_only_trajectory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "trajectory.jsonl"
            result = self.controller(path).run_step(
                observation(), case(), step_number=0, started_at=ORIGIN, ended_at=ORIGIN
            )
            self.assertEqual(result.prediction.committed_config_id, "config-old")
            self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_slow_action_without_visible_trigger_is_rejected(self) -> None:
        def invalid_policy(obs: Observation, state: CaseState, trigger: object) -> AgentAction:
            return AgentAction(
                action_id="action-invalid",
                action_type=ActionType.INVOKE_SLOW_DIAGNOSIS,
                case_id=state.case_id,
                window_id=obs.window.window_id,
                rationale="Untriggered slow path.",
                based_on_observation_id=obs.observation_id,
                deployment_evidence_ids=(obs.observation_id,),
            )

        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            self.controller(Path(temp) / "t.jsonl", invalid_policy).run_step(
                observation(), case(), step_number=0, started_at=ORIGIN, ended_at=ORIGIN
            )

    def test_observable_failure_allows_typed_tool_and_bounded_retry(self) -> None:
        calls = 0

        def policy(obs: Observation, state: CaseState, trigger: object) -> AgentAction:
            request = ToolRequest(
                tool_call_id="call-1",
                tool_name=ToolName.INSPECT_PIDS_AVAILABILITY,
                case_id=state.case_id,
                scenario_id=state.scenario_id,
                episode_id=state.episode_id,
                window_id=obs.window.window_id,
                arguments={"pids_id": "velox"},
                requested_at=obs.observed_at,
            )
            return AgentAction(
                action_id="action-tool",
                action_type=ActionType.RUN_TOOL,
                case_id=state.case_id,
                window_id=obs.window.window_id,
                rationale="Observable failure warrants capability inspection.",
                based_on_observation_id=obs.observation_id,
                deployment_evidence_ids=(obs.observation_id,),
                tool_request=request,
            )

        def executor(request: ToolRequest) -> ToolResult:
            nonlocal calls
            calls += 1
            return tool_result(request, RunStatus.FAILED if calls == 1 else RunStatus.SUCCEEDED)

        with tempfile.TemporaryDirectory() as temp:
            result = self.controller(Path(temp) / "t.jsonl", policy, executor).run_step(
                observation(failures=("timeout",)),
                case(),
                step_number=0,
                started_at=ORIGIN,
                ended_at=ORIGIN,
            )
        self.assertEqual(len(result.tool_results), 2)
        self.assertEqual(result.reflection, "tool_succeeded")

    def test_persistent_reconfiguration_is_next_window_only(self) -> None:
        def policy(obs: Observation, state: CaseState, trigger: object) -> AgentAction:
            return AgentAction(
                action_id="action-reconfigure",
                action_type=ActionType.SCHEDULE_RECONFIGURATION,
                case_id=state.case_id,
                window_id=obs.window.window_id,
                rationale="Observable failure supports a frozen alternative next window.",
                based_on_observation_id=obs.observation_id,
                deployment_evidence_ids=(obs.observation_id,),
                pending_config_id="config-new",
                effective_sequence_number=5,
            )

        with tempfile.TemporaryDirectory() as temp:
            result = self.controller(Path(temp) / "t.jsonl", policy).run_step(
                observation(failures=("degenerate-output",)),
                case(),
                step_number=0,
                started_at=ORIGIN,
                ended_at=ORIGIN,
            )
        self.assertEqual(result.prediction.committed_config_id, "config-old")
        self.assertEqual(result.next_case.committed_config_id, "config-old")
        self.assertEqual(result.next_case.pending_configuration.config_id, "config-new")

    def test_trajectory_rejects_noncontiguous_step(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            controller = self.controller(Path(temp) / "t.jsonl")
            controller.run_step(
                observation(), case(), step_number=0, started_at=ORIGIN, ended_at=ORIGIN
            )
            with self.assertRaises(ValueError):
                controller.run_step(
                    observation(), case(), step_number=2, started_at=ORIGIN, ended_at=ORIGIN
                )

    def test_hidden_evidence_phrase_is_rejected_from_routing_rationale(self) -> None:
        def leaked_policy(obs: Observation, state: CaseState, trigger: object) -> AgentAction:
            return AgentAction(
                action_id="action-leaked",
                action_type=ActionType.NO_CHANGE,
                case_id=state.case_id,
                window_id=obs.window.window_id,
                rationale="Teacher rationale says this is the best action.",
                based_on_observation_id=obs.observation_id,
                deployment_evidence_ids=(obs.observation_id,),
            )

        with tempfile.TemporaryDirectory() as temp, self.assertRaises(ValueError):
            self.controller(Path(temp) / "t.jsonl", leaked_policy).run_step(
                observation(), case(), step_number=0, started_at=ORIGIN, ended_at=ORIGIN
            )

    def test_trigger_profile_must_come_from_validation(self) -> None:
        with self.assertRaises(ValueError):
            ControllerConfig(
                max_tool_attempts=2,
                slow_path_alert_count=1,
                periodic_check_window_count=4,
                trigger_profile_id="test-tuned-trigger",
                trigger_source_split=DataSplit.HELD_OUT,
            )


class SchedulerTests(unittest.TestCase):
    def profile(self) -> ResourceProfile:
        return ResourceProfile(
            profile_id="autodl-initial",
            cpu_vcpus=32,
            memory_gib=240,
            reserved_memory_gib=24,
            gpu_count=2,
            gpu_memory_gib_per_device=24,
        )

    def test_executor_assigns_vllm_and_pids_to_separate_gpus(self) -> None:
        scheduler = ResourceScheduler(self.profile())
        vllm = scheduler.admit(
            ResourceRequest(
                request_id="vllm-1",
                workload=WorkloadKind.VLLM,
                cpu_vcpus=4,
                memory_gib=32,
                gpu_memory_gib=20,
            )
        )
        pids = scheduler.admit(
            ResourceRequest(
                request_id="pids-1",
                workload=WorkloadKind.PIDS_GPU,
                cpu_vcpus=8,
                memory_gib=64,
                gpu_memory_gib=20,
            )
        )
        self.assertEqual((vllm.gpu_index, pids.gpu_index), (0, 1))

    def test_same_gpu_unknown_pids_concurrency_is_rejected(self) -> None:
        scheduler = ResourceScheduler(self.profile())
        for request_id in ("pids-1", "pids-2"):
            request = ResourceRequest(
                request_id=request_id,
                workload=WorkloadKind.PIDS_GPU,
                cpu_vcpus=4,
                memory_gib=16,
                gpu_memory_gib=8,
            )
            if request_id == "pids-1":
                scheduler.admit(request)
            else:
                with self.assertRaises(ValueError):
                    scheduler.admit(request)

    def test_host_visible_capacity_cannot_raise_quota(self) -> None:
        scheduler = ResourceScheduler(self.profile())
        with self.assertRaises(ValueError):
            scheduler.admit(
                ResourceRequest(
                    request_id="too-large",
                    workload=WorkloadKind.PIDS_CPU,
                    cpu_vcpus=33,
                    memory_gib=16,
                )
            )

    def test_profile_loads_project_quota_not_host_observation(self) -> None:
        root = Path(__file__).resolve().parents[1]
        profile = ResourceProfile.from_yaml(root / "configs/resource_profiles/autodl.yaml")
        self.assertEqual((profile.cpu_vcpus, profile.memory_gib), (32, 240))
        self.assertEqual(profile.pids_worker_cpu_threads, 16)
        self.assertIn("OPENBLAS_NUM_THREADS", profile.numeric_thread_environment)
        self.assertEqual((profile.vllm_gpu_index, profile.pids_gpu_index), (0, 1))


if __name__ == "__main__":
    unittest.main()
