"""Label-free PIDSMaker stage-runner contract tests.

Requirements: REQ-LABEL-001..004, REQ-PIDS-004..005, REQ-TOOL-001..005,
REQ-WANDB-001, REQ-REPRO-001..002.
"""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pidsmaker_stage_runner.py"
SPEC = importlib.util.spec_from_file_location("pidsmaker_stage_runner", SCRIPT)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def request(root: Path, artifact: Path, **updates: object) -> Namespace:
    values: dict[str, object] = {
        "source_config_id": "velox",
        "dataset_id": "CADETS_E3",
        "pidsmaker_root": str(root),
        "artifact_dir": str(artifact),
        "stop_after": "construction",
        "override": [],
        "cpu": True,
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
    }
    values.update(updates)
    return values


class StageRunnerContractTests(unittest.TestCase):
    def test_upstream_password_is_internal_not_runner_argv(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            artifact_root = Path(temp)
            args = request(ROOT / "PIDSMaker", artifact_root / "run-1")
            argv = runner.upstream_argv(args, Path(args.artifact_dir), environment(artifact_root))
        self.assertIn("unit-test-secret", argv)
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
        rendered = runner.sanitized_resolved_config(args, "a" * 40)
        text = repr(rendered)
        self.assertNotIn("password", text.lower())
        self.assertNotIn("unit-test-secret", text)
        self.assertEqual(
            rendered["excluded_privileged_fields"],
            ["ground_truth_relative_path", "attack_to_time_window"],
        )

    def test_safe_stage_list_stops_before_training_evaluation_and_triage(self) -> None:
        self.assertEqual(
            runner.SAFE_STAGES,
            ("construction", "transformation", "featurization", "feat_inference"),
        )
        self.assertFalse({"training", "evaluation", "triage"} & set(runner.SAFE_STAGES))

    def test_pinned_submodule_commit_is_verified_without_git_command(self) -> None:
        self.assertEqual(runner.pinned_commit(ROOT / "PIDSMaker"), runner.PINNED_PIDSMaker_COMMIT)


if __name__ == "__main__":
    unittest.main()
