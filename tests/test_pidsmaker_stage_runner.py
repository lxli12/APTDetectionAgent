"""Label-free PIDSMaker stage-runner contract tests.

Requirements: REQ-LABEL-001..004, REQ-PIDS-004..005, REQ-TOOL-001..005,
REQ-WANDB-001, REQ-REPRO-001..002.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pidsmaker_stage_runner.py"
SPEC = importlib.util.spec_from_file_location("pidsmaker_stage_runner", SCRIPT)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def window(date: str) -> tuple[int, int]:
    start = int(
        datetime.strptime(date, "%Y-%m-%d")
        .replace(tzinfo=ZoneInfo("America/New_York"))
        .timestamp()
        * 1_000_000_000
    )
    return start, start + 900 * 1_000_000_000


def request(root: Path, artifact: Path, **updates: object) -> Namespace:
    train_start, train_end = window("2018-04-02")
    val_start, val_end = window("2018-04-03")
    test_start, test_end = window("2018-04-06")
    values: dict[str, object] = {
        "source_config_id": "velox",
        "dataset_id": "CADETS_E3",
        "pidsmaker_root": str(root),
        "artifact_dir": str(artifact),
        "frozen_bundle": None,
        "stop_after": "construction",
        "override": [],
        "cpu": True,
        "window_size_seconds": 900,
        "train_date": "2018-04-02",
        "train_window_start_ns": train_start,
        "train_window_end_ns": train_end,
        "val_date": "2018-04-03",
        "val_window_start_ns": val_start,
        "val_window_end_ns": val_end,
        "test_date": "2018-04-06",
        "test_window_start_ns": test_start,
        "test_window_end_ns": test_end,
    }
    values.update(updates)
    return Namespace(**values)


def environment(artifact_root: Path, **updates: str) -> dict[str, str]:
    values = {
        "APT_PIDS_ARTIFACT_ROOT": str(artifact_root),
        "PIDS_DB_HOST": "localhost",
        "PIDS_DB_USER": "pids_worker",
        "PIDS_DB_PASSWORD": "unit-test-secret",
        "PIDS_DB_PORT": "5432",
        "WANDB_MODE": "disabled",
        "APT_PIDS_CPU_THREADS": "16",
    }
    values.update(updates)
    return values


class StageRunnerContractTests(unittest.TestCase):
    def frozen_bundle(self, root: Path) -> Path:
        bundle = root / "bundle-1"
        featurizer = bundle / "featurizers" / "velox" / "word2vec"
        checkpoint = bundle / "checkpoints" / "velox" / "frozen_validation_checkpoint"
        featurizer.mkdir(parents=True)
        checkpoint.mkdir(parents=True)
        (featurizer / "word2vec.model").write_bytes(b"frozen-featurizer")
        (checkpoint / "state_dict.pkl").write_bytes(b"frozen-checkpoint")
        manifest = {
            "status": "validation_candidate_frozen",
            "featurizer_hash": runner.asset_tree_hash(featurizer),
            "checkpoint_hash": runner.asset_tree_hash(checkpoint),
        }
        availability = {
            "pids_id": "velox",
            "source_config_id": "velox",
            "dataset_id": "CADETS_E3",
            "status": "available_for_validation",
            "held_out_approved": False,
            "deployment_approved": False,
            "featurizer_relative_path": featurizer.relative_to(bundle).as_posix(),
            "checkpoint_relative_path": checkpoint.relative_to(bundle).as_posix(),
            "checkpoint_hash": manifest["checkpoint_hash"],
        }
        approved_config = [{
            "source_config_id": "velox",
            "dataset_id": "CADETS_E3",
            "approved_splits": ["validation"],
            "parameters": {},
        }]
        (bundle / "bundle_manifest.json").write_text(json.dumps(manifest))
        (bundle / "availability_manifest.json").write_text(json.dumps(availability))
        (bundle / "approved_config_catalog.json").write_text(json.dumps(approved_config))
        return bundle

    def test_upstream_password_is_environment_only_and_never_in_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            artifact_root = Path(temp)
            args = request(ROOT / "PIDSMaker", artifact_root / "run-1")
            argv = runner.upstream_argv(args, Path(args.artifact_dir), environment(artifact_root))
        self.assertNotIn("unit-test-secret", argv)
        self.assertNotIn("--database_password", argv)
        self.assertNotIn("unit-test-secret", vars(args).values())

    def test_requires_disabled_wandb(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            artifact_root = Path(temp)
            args = request(ROOT / "PIDSMaker", artifact_root / "run-1")
            with self.assertRaisesRegex(runner.StageRunnerError, "WANDB_MODE"):
                runner.validate_inputs(args, environment(artifact_root, WANDB_MODE="offline"))

    def test_rejects_artifact_escape_and_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            artifact_root = Path(temp) / "approved"
            artifact_root.mkdir()
            outside = Path(temp) / "outside" / "run-1"
            with self.assertRaisesRegex(runner.StageRunnerError, "direct child"):
                runner.validate_inputs(
                    request(ROOT / "PIDSMaker", outside), environment(artifact_root)
                )
            existing = artifact_root / "run-1"
            existing.mkdir()
            with self.assertRaisesRegex(runner.StageRunnerError, "already exists"):
                runner.validate_inputs(
                    request(ROOT / "PIDSMaker", existing), environment(artifact_root)
                )

    def test_rejects_executor_owned_and_control_character_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            artifact_root = Path(temp)
            for override in (["database.password=x"], ["training.lr=1\n--wandb"]):
                with self.subTest(override=override):
                    with self.assertRaises(runner.StageRunnerError):
                        runner.validate_inputs(
                            request(
                                ROOT / "PIDSMaker",
                                artifact_root / "run-1",
                                override=override,
                            ),
                            environment(artifact_root),
                        )

    def test_resolved_config_excludes_credentials_and_label_metadata(self) -> None:
        args = request(ROOT / "PIDSMaker", Path("/tmp/run-1"))
        rendered = runner.sanitized_resolved_config(
            args,
            {
                "upstream_commit": "a" * 40,
                "patch_series_hash": "b" * 64,
            },
            16,
        )
        text = repr(rendered)
        self.assertNotIn("password", text.lower())
        self.assertNotIn("unit-test-secret", text)
        self.assertEqual(
            rendered["excluded_privileged_fields"],
            ["ground_truth_relative_path", "attack_to_time_window"],
        )
        self.assertEqual(rendered["split_windows"]["train"]["boundary"], "[start,end)")
        self.assertEqual(rendered["pids_cpu_threads"], 16)

    def test_rejects_host_visible_cpu_count_as_allocation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            artifact_root = Path(temp)
            args = request(ROOT / "PIDSMaker", artifact_root / "run-1")
            with self.assertRaisesRegex(runner.StageRunnerError, "project quota"):
                runner.validate_inputs(
                    args, environment(artifact_root, APT_PIDS_CPU_THREADS="128")
                )

    def test_windows_are_equal_aligned_chronological_and_date_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            artifact_root = Path(temp)
            valid = request(ROOT / "PIDSMaker", artifact_root / "valid")
            runner.validate_inputs(valid, environment(artifact_root))
            with self.assertRaisesRegex(runner.StageRunnerError, "chronological"):
                runner.validate_inputs(
                    request(
                        ROOT / "PIDSMaker",
                        artifact_root / "bad-order",
                        test_date=valid.train_date,
                        test_window_start_ns=valid.train_window_start_ns,
                        test_window_end_ns=valid.train_window_end_ns,
                    ),
                    environment(artifact_root),
                )
            with self.assertRaisesRegex(runner.StageRunnerError, "disagrees"):
                runner.validate_inputs(
                    request(
                        ROOT / "PIDSMaker",
                        artifact_root / "bad-date",
                        train_date="2018-04-03",
                    ),
                    environment(artifact_root),
                )

    def test_safe_stage_list_stops_before_training_evaluation_and_triage(self) -> None:
        self.assertEqual(
            runner.SAFE_STAGES,
            ("construction", "transformation", "featurization", "feat_inference"),
        )
        self.assertFalse({"training", "evaluation", "triage"} & set(runner.SAFE_STAGES))

    def test_pinned_submodule_commit_is_verified_without_git_command(self) -> None:
        self.assertEqual(runner.pinned_commit(ROOT / "PIDSMaker"), runner.PINNED_PIDSMaker_COMMIT)

    def test_isolated_compatibility_marker_is_accepted_without_git_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".apt-pidsmaker-compat.json").write_text(
                "{\"schema_version\":\"apt-pidsmaker-compat-v1\","
                f"\"upstream_commit\":\"{runner.PINNED_PIDSMaker_COMMIT}\","
                f"\"patch_series_hash\":\"{'a' * 64}\","
                "\"source_submodule_modified\":false}"
            )
            identity = runner.source_identity(root)
        self.assertEqual(identity["patch_series_hash"], "a" * 64)

    def test_frozen_bundle_is_bound_to_identity_hashes_and_validation_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            artifacts = base / "artifacts"
            bundles = base / "bundles"
            artifacts.mkdir()
            bundles.mkdir()
            bundle = self.frozen_bundle(bundles)
            args = request(
                ROOT / "PIDSMaker",
                artifacts / "run-1",
                frozen_bundle=str(bundle),
                stop_after="feat_inference",
            )
            env = environment(artifacts, APT_PRE_SFT_BUNDLE_ROOT=str(bundles))
            frozen = runner.validate_frozen_bundle(
                bundle,
                env,
                expected_source_config_id="velox",
                expected_dataset_id="CADETS_E3",
                expected_overrides=[],
            )
            self.assertEqual(frozen["manifest"]["status"], "validation_candidate_frozen")
            runner.validate_inputs(args, env)
            with self.assertRaisesRegex(runner.StageRunnerError, "ApprovedConfig"):
                runner.validate_frozen_bundle(
                    bundle,
                    env,
                    expected_source_config_id="velox",
                    expected_dataset_id="CADETS_E3",
                    expected_overrides=["training.num_epochs=2"],
                )
            (Path(frozen["featurizer"]) / "word2vec.model").write_bytes(b"tampered")
            with self.assertRaisesRegex(runner.StageRunnerError, "provenance"):
                runner.validate_frozen_bundle(bundle, env)


if __name__ == "__main__":
    unittest.main()
