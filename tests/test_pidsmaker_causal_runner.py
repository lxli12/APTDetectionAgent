"""Causal PIDSMaker training/frozen-inference runner contracts.

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001..004, REQ-PIDS-005,
REQ-ARTIFACT-001..003, REQ-WANDB-001, REQ-REPRO-001..002.
"""

from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "pidsmaker_causal_runner.py"
SPEC = importlib.util.spec_from_file_location("pidsmaker_causal_runner", SCRIPT)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def interval(date: str) -> tuple[int, int]:
    start = int(
        datetime.strptime(date, "%Y-%m-%d")
        .replace(tzinfo=ZoneInfo("America/New_York"))
        .timestamp()
        * 1_000_000_000
    )
    return start, start + 900 * 1_000_000_000


def arguments(root: Path, artifact: Path, **updates: object) -> Namespace:
    train = interval("2018-04-02")
    val = interval("2018-04-03")
    test = interval("2018-04-06")
    values: dict[str, object] = {
        "phase": "train",
        "source_config_id": "velox",
        "dataset_id": "CADETS_E3",
        "pidsmaker_root": str(root),
        "artifact_dir": str(artifact),
        "checkpoint_hash": None,
        "override": ["training.num_epochs=1"],
        "cpu": False,
        "window_size_seconds": 900,
        "train_date": "2018-04-02",
        "train_window_start_ns": train[0],
        "train_window_end_ns": train[1],
        "val_date": "2018-04-03",
        "val_window_start_ns": val[0],
        "val_window_end_ns": val[1],
        "test_date": "2018-04-06",
        "test_window_start_ns": test[0],
        "test_window_end_ns": test[1],
    }
    values.update(updates)
    return Namespace(**values)


def environment(artifact_root: Path, **updates: str) -> dict[str, str]:
    values = {
        "APT_PIDS_ARTIFACT_ROOT": str(artifact_root),
        "PIDS_DB_HOST": "127.0.0.1",
        "PIDS_DB_USER": "pids_worker",
        "PIDS_DB_PASSWORD": "secret",
        "PIDS_DB_PORT": "5432",
        "WANDB_MODE": "disabled",
        "APT_PIDS_CPU_THREADS": "16",
    }
    values.update(updates)
    return values


class CausalRunnerContractTests(unittest.TestCase):
    def fixture(self, root: Path, artifact: Path) -> None:
        training = root / "pidsmaker" / "detection" / "training_methods"
        training.mkdir(parents=True)
        (training / "training_loop.py").write_text("# local JSON logging only\n")
        (root / ".apt-pidsmaker-compat.json").write_text(
            json.dumps(
                {
                    "schema_version": "apt-pidsmaker-compat-v1",
                    "upstream_commit": runner.prefix.PINNED_PIDSMaker_COMMIT,
                    "patch_series_hash": "a" * 64,
                    "source_submodule_modified": False,
                }
            )
        )
        artifact.mkdir()
        (artifact / "stage_summary.json").write_text("{}\n")

    def test_requires_isolated_build_existing_prefix_and_disabled_wandb(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            approved = base / "artifacts"
            approved.mkdir()
            root = base / "compat"
            artifact = approved / "run"
            self.fixture(root, artifact)
            identity = runner.validate(arguments(root, artifact), environment(approved))[2]
            self.assertEqual(identity["patch_series_hash"], "a" * 64)
            with self.assertRaisesRegex(runner.CausalRunnerError, "WANDB_MODE"):
                runner.validate(
                    arguments(root, artifact), environment(approved, WANDB_MODE="offline")
                )

    def test_inference_requires_exact_hash_and_train_rejects_one(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            approved = base / "artifacts"
            approved.mkdir()
            root = base / "compat"
            artifact = approved / "run"
            self.fixture(root, artifact)
            with self.assertRaisesRegex(runner.CausalRunnerError, "requires a checkpoint"):
                runner.validate(
                    arguments(root, artifact, phase="infer"), environment(approved)
                )
            with self.assertRaisesRegex(runner.CausalRunnerError, "does not accept"):
                runner.validate(
                    arguments(root, artifact, checkpoint_hash="b" * 64),
                    environment(approved),
                )

    def test_training_source_with_wandb_import_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            approved = base / "artifacts"
            approved.mkdir()
            root = base / "compat"
            artifact = approved / "run"
            self.fixture(root, artifact)
            (
                root / "pidsmaker" / "detection" / "training_methods" / "training_loop.py"
            ).write_text("import wandb\n")
            with self.assertRaisesRegex(runner.CausalRunnerError, "imports W&B"):
                runner.validate(arguments(root, artifact), environment(approved))

    def test_tree_hash_is_content_and_path_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "one").write_text("same")
            first = runner.tree_hash(root)
            (root / "one").write_text("changed")
            second = runner.tree_hash(root)
        self.assertNotEqual(first, second)

    def test_runner_never_imports_hidden_evaluation_or_wandb(self) -> None:
        source = SCRIPT.read_text()
        self.assertNotIn("pidsmaker.tasks.evaluation", source)
        self.assertIn("cfg.dataset.ground_truth_relative_path = []", source)
        self.assertIsNone(re.search(r"(?m)^\s*(?:from|import)\s+wandb\b", source))
        self.assertIn('split="test"', source)
        self.assertIn("test_labels_loaded", source)


if __name__ == "__main__":
    unittest.main()
