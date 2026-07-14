"""Versioned isolated PIDSMaker compatibility build tests.

Requirements: REQ-GIT-003, REQ-PIDS-005, REQ-CAUSAL-001..004,
REQ-WANDB-001, REQ-REPRO-001..002.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_pidsmaker_compat.py"
SPEC = importlib.util.spec_from_file_location("build_pidsmaker_compat", SCRIPT)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PIDSMakerCompatibilityBuildTests(unittest.TestCase):
    def test_patch_contract_contains_required_causal_changes(self) -> None:
        patch_text = (
            ROOT
            / "compat"
            / "pidsmaker"
            / builder.PINNED_COMMIT
            / "0001-apt-causal-runtime.patch"
        ).read_text()
        self.assertIn("timestamp_rec >= %s and timestamp_rec < %s", patch_text)
        self.assertIn("cur.execute(sql, (start_ns_timestamp, end_ns_timestamp))", patch_text)
        self.assertIn("PIDS_DB_PASSWORD", patch_text)
        self.assertIn("load_train_validation_datasets", patch_text)
        self.assertIn("load_test_dataset", patch_text)
        self.assertIn("frozen_validation_checkpoint", patch_text)
        self.assertIn("test_data_used_for_selection", patch_text)
        self.assertIn("-import wandb", patch_text)
        self.assertNotIn("+import wandb", patch_text)
        self.assertIn('-nltk.download("punkt", quiet=True)', patch_text)
        self.assertIn('nltk.data.find("tokenizers/punkt")', patch_text)
        self.assertIn(
            "from pidsmaker.experiments.uncertainty import activate_dropout_inference",
            patch_text,
        )

    def test_build_applies_patch_outside_clean_submodule_and_never_overwrites(self) -> None:
        source = ROOT / "PIDSMaker"
        tracked = (
            source / "pidsmaker" / "config" / "pipeline.py",
            source
            / "pidsmaker"
            / "preprocessing"
            / "build_graph_methods"
            / "build_default_graphs.py",
            source / "pidsmaker" / "utils" / "data_utils.py",
            source
            / "pidsmaker"
            / "detection"
            / "training_methods"
            / "training_loop.py",
            source / "pidsmaker" / "model.py",
            source / "pidsmaker" / "utils" / "utils.py",
        )
        before = tuple(digest(path) for path in tracked)
        with tempfile.TemporaryDirectory() as temp:
            approved_root = Path(temp) / "approved"
            approved_root.mkdir()
            output = approved_root / "compat-v1"
            with patch.dict(os.environ, {"APT_PIDS_COMPAT_BUILD_ROOT": str(approved_root)}):
                marker = builder.build(ROOT, source, output)
                with self.assertRaisesRegex(builder.CompatibilityBuildError, "already exists"):
                    builder.build(ROOT, source, output)
            patched_training = (
                output
                / "pidsmaker"
                / "detection"
                / "training_methods"
                / "training_loop.py"
            ).read_text()
            patched_query = (
                output
                / "pidsmaker"
                / "preprocessing"
                / "build_graph_methods"
                / "build_default_graphs.py"
            ).read_text()
            patched_model = (output / "pidsmaker" / "model.py").read_text()
            patched_utils = (output / "pidsmaker" / "utils" / "utils.py").read_text()
            marker_exists = (output / ".apt-pidsmaker-compat.json").is_file()
            git_marker_exists = (output / ".git").exists()
        self.assertEqual(marker["upstream_commit"], builder.PINNED_COMMIT)
        self.assertTrue(marker_exists)
        self.assertFalse(git_marker_exists)
        self.assertNotIn("import wandb", patched_training)
        self.assertNotIn('split="all"', patched_training)
        self.assertNotIn('split="test"', patched_training)
        self.assertNotIn(
            "from pidsmaker.experiments.uncertainty import activate_dropout_inference\n\n\nclass",
            patched_model,
        )
        self.assertIn("if self.is_running_mc_dropout:", patched_model)
        self.assertNotIn("nltk.download", patched_utils)
        self.assertIn('nltk.data.find("tokenizers/punkt")', patched_utils)
        self.assertIn("cur.execute(sql, (start_ns_timestamp, end_ns_timestamp))", patched_query)
        self.assertEqual(before, tuple(digest(path) for path in tracked))


if __name__ == "__main__":
    unittest.main()
