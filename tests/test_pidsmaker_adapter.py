"""Safe PIDSMaker adapter and fake-runner integration tests.

Requirements: REQ-TOOL-001..005, REQ-ARTIFACT-001..003,
REQ-WANDB-001, REQ-RESOURCE-002, REQ-DB-003.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from apt_detection_agent.pidsmaker import (
    ApprovedConfigCatalog,
    PIDSDetectionRequest,
    PIDSMakerAdapter,
    PIDSMakerDiscovery,
    PIDSToolService,
    VisibleTraceGraph,
)
from apt_detection_agent.schemas import (
    ApprovedConfig,
    DataSplit,
    ExperimentClass,
    PIDSRef,
    PipelineStage,
    RunStatus,
    TransductiveStatus,
)


ROOT = Path(__file__).resolve().parents[1]
GIT_SHA = "b" * 40
CHECKPOINT_SHA = "a" * 64


def approved_config(**updates: object) -> ApprovedConfig:
    values: dict[str, object] = {
        "config_id": "velox-cadets-causal-v1",
        "pids": {"pids_id": "velox", "variant_id": "default"},
        "source_config_id": "velox",
        "dataset_id": "CADETS_E3",
        "parameters": {"training.lr": 0.001},
        "required_pipeline_stages": (PipelineStage.INFERENCE, PipelineStage.DETECTION),
        "checkpoint_hash": CHECKPOINT_SHA,
        "experiment_class": ExperimentClass.CAUSAL_MAIN,
        "transductive_status": TransductiveStatus.CAUSAL,
        "frozen_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "code_commit": GIT_SHA,
        "approved_splits": frozenset({DataSplit.HELD_OUT}),
    }
    values.update(updates)
    return ApprovedConfig.model_validate(values)


def request(**updates: object) -> PIDSDetectionRequest:
    values: dict[str, object] = {
        "request_id": "request-1",
        "tool_call_id": "call-1",
        "case_id": "case-1",
        "scenario_id": "scenario-1",
        "episode_id": "episode-1",
        "window_id": "window-1",
        "split": DataSplit.HELD_OUT,
        "run_id": "run-adapter-1",
        "pids": PIDSRef(pids_id="velox"),
        "source_config_id": "velox",
        "dataset_id": "CADETS_E3",
        "approved_config": approved_config(),
        "timeout_seconds": 30,
    }
    values.update(updates)
    return PIDSDetectionRequest.model_validate(values)


class FakeRunner:
    def __init__(self, returncode: int = 0, *, write_artifact: bool = True) -> None:
        self.returncode = returncode
        self.write_artifact = write_artifact
        self.calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def __call__(self, argv: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append((tuple(argv), kwargs))
        artifact_index = argv.index("--artifact_dir") + 1
        artifact_dir = Path(argv[artifact_index])
        if self.write_artifact:
            artifact_dir.mkdir(parents=True)
            (artifact_dir / "scores.json").write_text('{"score_count": 1}\n')
        return subprocess.CompletedProcess(
            argv,
            self.returncode,
            stdout="synthetic runner output\n",
            stderr="" if self.returncode == 0 else "synthetic failure\n",
        )


class PIDSMakerAdapterTests(unittest.TestCase):
    def adapter(self, artifact_root: Path, runner: FakeRunner, **kwargs: object) -> PIDSMakerAdapter:
        return PIDSMakerAdapter(
            ROOT,
            artifact_root,
            Path(sys.executable),
            runner=runner,
            execution_enabled=True,
            **kwargs,
        )

    def test_builds_argv_without_shell_or_wandb(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = self.adapter(Path(temp_dir), FakeRunner())
            argv = adapter.build_argv(request())
        self.assertEqual(argv[1:4], ("pidsmaker/main.py", "velox", "CADETS_E3"))
        self.assertIn("--training.lr=0.001", argv)
        self.assertNotIn("--wandb", argv)
        self.assertTrue(all(";" not in item for item in argv))

    def test_rejects_unregistered_override(self) -> None:
        config = approved_config(parameters={"database_password": "do-not-use"})
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = self.adapter(Path(temp_dir), FakeRunner())
            with self.assertRaises(ValueError):
                adapter.build_argv(request(approved_config=config))

    def test_rejects_heldout_without_checkpoint(self) -> None:
        config = approved_config(checkpoint_hash=None)
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = self.adapter(Path(temp_dir), FakeRunner())
            with self.assertRaises(ValueError):
                adapter.build_argv(request(approved_config=config))

    def test_llm_cannot_supply_run_path(self) -> None:
        with self.assertRaises(ValidationError):
            request(run_id="../escape")

    def test_execution_disabled_by_default_until_credential_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = PIDSMakerAdapter(ROOT, Path(temp_dir), Path(sys.executable))
            with self.assertRaises(RuntimeError):
                adapter.execute(request())

    def test_fake_execution_writes_standardized_audit_artifacts(self) -> None:
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = self.adapter(Path(temp_dir), runner, cuda_visible_devices="1")
            outcome = adapter.execute(request())
            files = {path.name for path in outcome.run_directory.iterdir()}
        self.assertEqual(outcome.tool_result.status, RunStatus.SUCCEEDED)
        self.assertIn("command.txt", files)
        self.assertIn("stdout.log", files)
        self.assertIn("stderr.log", files)
        self.assertIn("artifact_manifest.json", files)
        self.assertIn("tool_result.json", files)
        self.assertEqual(len(runner.calls), 1)
        called_argv, called_kwargs = runner.calls[0]
        self.assertIsInstance(called_argv, tuple)
        self.assertEqual(called_kwargs["env"]["WANDB_MODE"], "disabled")
        self.assertEqual(called_kwargs["env"]["CUDA_VISIBLE_DEVICES"], "1")
        self.assertEqual(called_kwargs["env"]["APT_PIDS_CPU_THREADS"], "16")
        self.assertTrue(
            all(
                called_kwargs["env"][name] == "16"
                for name in (
                    "OMP_NUM_THREADS",
                    "MKL_NUM_THREADS",
                    "OPENBLAS_NUM_THREADS",
                    "NUMEXPR_NUM_THREADS",
                    "VECLIB_MAXIMUM_THREADS",
                )
            )
        )

    def test_rejects_cpu_thread_limit_above_project_quota(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "project quota"):
                PIDSMakerAdapter(
                    ROOT,
                    Path(temp_dir),
                    Path(sys.executable),
                    cpu_thread_limit=33,
                )

    def test_nonzero_exit_is_typed_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outcome = self.adapter(Path(temp_dir), FakeRunner(returncode=7)).execute(request())
        self.assertEqual(outcome.tool_result.status, RunStatus.FAILED)
        self.assertEqual(outcome.tool_result.exit_code, 7)
        self.assertIn("code 7", outcome.tool_result.sanitized_error or "")

    def test_zero_exit_without_artifact_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outcome = self.adapter(
                Path(temp_dir), FakeRunner(write_artifact=False)
            ).execute(request())
        self.assertEqual(outcome.tool_result.status, RunStatus.FAILED)
        self.assertIn("produced no artifacts", outcome.tool_result.sanitized_error or "")

    def test_process_start_error_is_sanitized_and_recorded(self) -> None:
        def missing_process(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("sensitive local path must not be returned")

        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = PIDSMakerAdapter(
                ROOT,
                Path(temp_dir),
                Path(sys.executable),
                runner=missing_process,
                execution_enabled=True,
            )
            outcome = adapter.execute(request())
            stderr_exists = (outcome.run_directory / "stderr.log").exists()
        self.assertEqual(outcome.tool_result.status, RunStatus.FAILED)
        self.assertIn("FileNotFoundError", outcome.tool_result.sanitized_error or "")
        self.assertNotIn("sensitive local path", outcome.tool_result.sanitized_error or "")
        self.assertTrue(stderr_exists)

    def test_run_directory_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = self.adapter(Path(temp_dir), FakeRunner())
            adapter.execute(request())
            with self.assertRaises(FileExistsError):
                adapter.execute(request())


class PIDSToolServiceTests(unittest.TestCase):
    def service(self, artifact_root: Path, runner: FakeRunner) -> PIDSToolService:
        config = approved_config()
        adapter = PIDSMakerAdapter(
            ROOT,
            artifact_root,
            Path(sys.executable),
            runner=runner,
            execution_enabled=True,
        )
        return PIDSToolService(
            discovery=PIDSMakerDiscovery(ROOT),
            adapter=adapter,
            catalog=ApprovedConfigCatalog((config,)),
        )

    def test_lists_complete_registry_and_availability(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self.service(Path(temp_dir), FakeRunner())
            self.assertEqual(len(service.list_pids_capabilities()), 10)
            matches = service.inspect_pids_availability(PIDSRef(pids_id="orthrus", variant_id="fixed"))
        self.assertEqual(matches[0].source_config_id, "orthrus_fixed")

    def test_catalog_rejects_config_not_frozen_for_request(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self.service(Path(temp_dir), FakeRunner())
            with self.assertRaises(ValueError):
                service.select_approved_config(
                    "missing-config",
                    PIDSRef(pids_id="velox"),
                    "CADETS_E3",
                    DataSplit.HELD_OUT,
                )

    def test_gpu_requests_are_serialized_by_initial_profile(self) -> None:
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self.service(Path(temp_dir), runner)
            second = request(run_id="run-adapter-2", request_id="request-2", tool_call_id="call-2")
            outcomes = service.run_parallel_pids_detection((request(), second))
        self.assertEqual(len(outcomes), 2)
        self.assertEqual([call[0][2] for call in runner.calls], ["velox", "velox"])

    def test_comparison_uses_only_standardized_results(self) -> None:
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self.service(Path(temp_dir), runner)
            outcome = service.run_pids_detection(request())
            comparison = service.compare_pids_results((outcome.tool_result,))
        self.assertEqual(comparison.successful_calls, 1)
        self.assertEqual(comparison.failed_calls, 0)

    def test_forward_and_backward_trace_visible_graph_only(self) -> None:
        graph = VisibleTraceGraph(
            graph_id="graph-1",
            adjacency={"a": ("b",), "b": ("c",), "c": ()},
        )
        forward = PIDSToolService.forward_trace(graph, ("a",), max_depth=2)
        backward = PIDSToolService.backward_trace(graph, ("c",), max_depth=2)
        self.assertEqual(forward.entity_ids, ("a", "b", "c"))
        self.assertEqual(backward.entity_ids, ("a", "b", "c"))
        self.assertEqual(backward.edges, (("b", "c"), ("a", "b")))

    def test_trace_rejects_hidden_or_unknown_extra_fields(self) -> None:
        with self.assertRaises(ValidationError):
            VisibleTraceGraph.model_validate(
                {
                    "graph_id": "graph-1",
                    "adjacency": {"a": ()},
                    "ground_truth": {"a": "malicious"},
                }
            )


if __name__ == "__main__":
    unittest.main()
