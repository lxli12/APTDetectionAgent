"""Safe PIDSMaker adapter and fake-runner integration tests.

Requirements: REQ-TOOL-001..005, REQ-ARTIFACT-001..003,
REQ-WANDB-001, REQ-RESOURCE-002, REQ-DB-003.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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
    zone = ZoneInfo("America/New_York")
    origin = datetime(2018, 4, 6, tzinfo=zone)
    start = origin + timedelta(hours=12)
    values: dict[str, object] = {
        "request_id": "request-1",
        "tool_call_id": "call-1",
        "case_id": "case-1",
        "scenario_id": "scenario-1",
        "episode_id": "episode-1",
        "window_id": "window-1",
        "window": {
            "window_id": "window-1",
            "sequence_number": 48,
            "origin_time": origin,
            "timezone": "America/New_York",
            "window_size_seconds": 900,
            "start": start,
            "end": start + timedelta(minutes=15),
        },
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
    def __init__(
        self,
        returncode: int = 0,
        *,
        write_artifact: bool = True,
        privileged_column: bool = False,
    ) -> None:
        self.returncode = returncode
        self.write_artifact = write_artifact
        self.privileged_column = privileged_column
        self.calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def __call__(self, argv: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append((tuple(argv), kwargs))
        artifact_index = argv.index("--artifact-dir") + 1
        artifact_dir = Path(argv[artifact_index])
        if self.write_artifact:
            artifact_dir.mkdir(parents=True)
            start_ns = int(argv[argv.index("--test-window-start-ns") + 1])
            end_ns = int(argv[argv.index("--test-window-end-ns") + 1])
            checkpoint_hash = argv[argv.index("--checkpoint-hash") + 1]
            score = (
                artifact_dir
                / "training"
                / "training"
                / "hash"
                / "CADETS_E3"
                / "edge_losses"
                / "test"
                / "model_epoch_frozen"
                / "scores.csv"
            )
            score.parent.mkdir(parents=True)
            header = "loss,srcnode,dstnode,time,edge_type"
            row = f"2.0,1,2,{start_ns + 1},3"
            if self.privileged_column:
                header += ",label"
                row += ",1"
            score.write_text(header + "\n" + row + "\n")
            (artifact_dir / "checkpoint_manifest.json").write_text(
                json.dumps(
                    {
                        "checkpoint_hash": checkpoint_hash,
                        "dataset_id": "CADETS_E3",
                        "source_config_id": "velox",
                    }
                )
            )
            (artifact_dir / "inference_stage_summary.json").write_text(
                json.dumps({"elapsed_seconds": 0.1})
            )
            (artifact_dir / "stage_summary.json").write_text(
                json.dumps(
                    {
                        "completed_stages": [
                            {"stage": "construction", "elapsed_seconds": 0.01},
                            {"stage": "transformation", "elapsed_seconds": 0.01},
                            {"stage": "featurization", "elapsed_seconds": 0.0},
                            {"stage": "feat_inference", "elapsed_seconds": 0.01},
                        ]
                    }
                )
            )
            (artifact_dir / "resolved_config.yaml").write_text(
                json.dumps(
                    {
                        "timezone": "America/New_York",
                        "window_size_seconds": 900,
                        "split_windows": {
                            "test": {"start_ns": start_ns, "end_ns": end_ns}
                        },
                    }
                )
            )
        return subprocess.CompletedProcess(
            argv,
            self.returncode,
            stdout="synthetic runner output\n",
            stderr="" if self.returncode == 0 else "synthetic failure\n",
        )


def configured_adapter(
    artifact_root: Path, runner: object, **kwargs: object
) -> PIDSMakerAdapter:
    compatibility = artifact_root / "compatibility"
    compatibility.mkdir(exist_ok=True)
    (compatibility / ".apt-pidsmaker-compat.json").write_text(
            json.dumps(
                {
                    "schema_version": "apt-pidsmaker-compat-v1",
                    "upstream_commit": "32602734bc9f896be5fc0f03f0a185c967cd6624",
                    "patch_series_hash": "c" * 64,
                    "source_submodule_modified": False,
                }
            )
    )
    bundle_root = artifact_root / "bundles"
    bundle = bundle_root / "bundle-1"
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / "bundle_manifest.json").write_text('{"status":"validation_candidate_frozen"}')
    (bundle / "approved_config_catalog.json").write_text(
        json.dumps([approved_config().model_dump(mode="json")])
    )
    (bundle / "threshold_catalog.json").write_text(
            json.dumps(
                [
                    {
                        "threshold_id": "threshold-1",
                        "value": 1.5,
                        "calibration_method": "validation_quantile",
                        "source_dataset": "CADETS_E3",
                        "source_split": "validation",
                        "checkpoint_hash": CHECKPOINT_SHA,
                        "target_metric": "edge_loss_quantile_0p99",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "code_commit": GIT_SHA,
                    }
                ]
            )
    )
    return PIDSMakerAdapter(
        ROOT,
        artifact_root,
        Path(sys.executable),
        runner=runner,
        execution_enabled=True,
        compatibility_root=compatibility,
        frozen_bundle_root=bundle_root,
        approved_bundles={"velox-cadets-causal-v1": bundle},
        **kwargs,
    )


class PIDSMakerAdapterTests(unittest.TestCase):
    def adapter(self, artifact_root: Path, runner: object, **kwargs: object) -> PIDSMakerAdapter:
        return configured_adapter(artifact_root, runner, **kwargs)

    def test_builds_argv_without_shell_or_wandb(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = self.adapter(Path(temp_dir), FakeRunner())
            argv = adapter.build_argv(request())
        self.assertTrue(argv[1].endswith("scripts/run_frozen_pids_tool.py"))
        self.assertEqual(argv[2:4], ("velox", "CADETS_E3"))
        self.assertIn("training.lr=0.001", argv)
        self.assertIn("--frozen-bundle", argv)
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
        with self.assertRaises(ValidationError):
            request(frozen_bundle="/executor/owned")

    def test_execution_disabled_by_default_until_credential_patch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = PIDSMakerAdapter(ROOT, Path(temp_dir), Path(sys.executable))
            with self.assertRaises(RuntimeError):
                adapter.execute(request())

    def test_fake_execution_writes_standardized_audit_artifacts(self) -> None:
        runner = FakeRunner()
        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = self.adapter(
                Path(temp_dir),
                runner,
                cuda_visible_devices="1",
                database_environment={"PIDS_DB_PASSWORD": "unit-test-only"},
            )
            outcome = adapter.execute(request())
            files = {path.name for path in outcome.run_directory.iterdir()}
        self.assertEqual(outcome.tool_result.status, RunStatus.SUCCEEDED)
        self.assertIn("command.txt", files)
        self.assertIn("stdout.log", files)
        self.assertIn("stderr.log", files)
        self.assertIn("artifact_manifest.json", files)
        self.assertIn("tool_result.json", files)
        self.assertIn("detection_result.json", files)
        self.assertEqual(outcome.tool_result.standardized_observation["score_count"], 2)
        self.assertEqual(outcome.tool_result.standardized_observation["alert_count"], 2)
        self.assertEqual(len(outcome.tool_result.stage_trace), 5)
        self.assertEqual(outcome.tool_result.stage_trace[-1].stage, PipelineStage.INFERENCE)
        self.assertNotIn(
            "PIDS_DB_PASSWORD",
            outcome.tool_result.command_manifest.injected_environment_keys,
        )
        self.assertEqual(len(runner.calls), 1)
        called_argv, called_kwargs = runner.calls[0]
        self.assertIsInstance(called_argv, tuple)
        self.assertEqual(called_kwargs["env"]["WANDB_MODE"], "disabled")
        self.assertEqual(called_kwargs["env"]["CUDA_VISIBLE_DEVICES"], "1")
        self.assertEqual(called_kwargs["env"]["APT_PIDS_CPU_THREADS"], "16")
        self.assertEqual(called_kwargs["env"]["PIDS_DB_PASSWORD"], "unit-test-only")
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

    def test_privileged_raw_score_column_fails_typed_standardization(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outcome = self.adapter(
                Path(temp_dir), FakeRunner(privileged_column=True)
            ).execute(request())
        self.assertEqual(outcome.tool_result.status, RunStatus.FAILED)
        self.assertEqual(
            outcome.tool_result.sanitized_error,
            "PIDSMaker output standardization failed: ValueError",
        )

    def test_process_start_error_is_sanitized_and_recorded(self) -> None:
        def missing_process(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            raise FileNotFoundError("sensitive local path must not be returned")

        with tempfile.TemporaryDirectory() as temp_dir:
            adapter = self.adapter(Path(temp_dir), missing_process)
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
        adapter = configured_adapter(artifact_root, runner)
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

    def test_catalog_loads_frozen_json_without_runtime_search(self) -> None:
        config = approved_config(approved_splits=frozenset({DataSplit.VALIDATION}))
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "catalog.json"
            path.write_text(json.dumps([config.model_dump(mode="json")]))
            catalog = ApprovedConfigCatalog.from_json(path)
            selected = catalog.select(
                config_id=config.config_id,
                pids=config.pids,
                dataset_id=config.dataset_id,
                split=DataSplit.VALIDATION,
            )
        self.assertEqual(selected, config)

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
