"""Formal train/test entrypoint and owned-run workflow tests.

Requirements: REQ-GIT-001..003, REQ-LABEL-001..004, REQ-SFT-004,
REQ-REPRO-001..003.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class FormalEntrypointTests(unittest.TestCase):
    def environment(self) -> dict[str, str]:
        return {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(ROOT / "src"),
            "APT_AGENT_PYTHON": sys.executable,
        }

    def test_train_all_reports_explicit_gates_and_complete_stage_list(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_root = Path(temp) / "runs"
            completed = subprocess.run(
                (
                    str(ROOT / "scripts" / "train_agent.sh"),
                    "--run-id",
                    "train-entrypoint-test",
                    "--run-root",
                    str(run_root),
                    "--stage",
                    "all",
                ),
                env=self.environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            run_dir = run_root / "train-entrypoint-test"
            stages = [json.loads(line) for line in (run_dir / "stages.jsonl").read_text().splitlines()]
            status = json.loads((run_dir / "run_status.json").read_text())
            artifact_manifest_exists = (run_dir / "artifact_manifest.json").is_file()
        self.assertEqual(completed.returncode, 3)
        self.assertEqual(len(stages), 11)
        self.assertEqual(stages[0]["status"], "succeeded")
        self.assertTrue(any(item["reason"] == "BLOCKED_BY_SFT_DATASET" for item in stages))
        self.assertEqual(status["status"], "blocked")
        self.assertTrue(artifact_manifest_exists)

    def test_train_single_safe_stage_succeeds_and_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_root = Path(temp)
            command = (
                str(ROOT / "scripts" / "train_agent.sh"),
                "--run-id",
                "single-stage",
                "--run-root",
                str(run_root),
                "--stage",
                "validate_environment",
            )
            first = subprocess.run(
                command, env=self.environment(), capture_output=True, text=True, check=False
            )
            second = subprocess.run(
                command, env=self.environment(), capture_output=True, text=True, check=False
            )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertNotEqual(second.returncode, 0)

    def test_test_entrypoint_runs_full_synthetic_protocol(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_root = root / "runs"
            private_root = root / "private"
            completed = subprocess.run(
                (
                    str(ROOT / "scripts" / "test_agent.sh"),
                    "--run-id",
                    "test-entrypoint-synthetic",
                    "--run-root",
                    str(run_root),
                    "--private-root",
                    str(private_root),
                    "--mode",
                    "synthetic",
                ),
                env=self.environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            run_dir = run_root / "test-entrypoint-synthetic"
            status = json.loads((run_dir / "run_status.json").read_text())
            public_metrics = (run_dir / "metrics.json").read_text()
            stages_exist = (run_dir / "stages.jsonl").is_file()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(status["status"], "succeeded")
        self.assertNotIn("campaign_coverage", public_metrics)
        self.assertTrue(stages_exist)

    def test_real_test_mode_blocks_before_data_or_model_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_root = Path(temp) / "runs"
            completed = subprocess.run(
                (
                    str(ROOT / "scripts" / "test_agent.sh"),
                    "--run-id",
                    "real-preflight",
                    "--run-root",
                    str(run_root),
                    "--private-root",
                    str(Path(temp) / "private"),
                    "--mode",
                    "real",
                ),
                env=self.environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            status = json.loads((run_root / "real-preflight" / "run_status.json").read_text())
        self.assertEqual(completed.returncode, 3)
        self.assertEqual(status["reason"], "BLOCKED_BY_PHASE8_REAL_PIDS_GATES")

    def test_remote_scripts_have_owned_session_guard_and_no_destructive_git(self) -> None:
        remote_root = ROOT / "scripts" / "remote"
        start = (remote_root / "start_run.sh").read_text()
        stop = (remote_root / "stop_owned_run.sh").read_text()
        combined = "\n".join(path.read_text() for path in remote_root.glob("*.sh"))
        self.assertIn("BLOCKED_BY_MISSING_TMUX", start)
        self.assertIn("owned_session.txt", stop)
        self.assertNotIn("git reset", combined)
        self.assertNotIn("rm -rf", combined)

    def test_remote_sync_stops_on_dirty_tree_before_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repository = Path(temp) / "repository"
            repository.mkdir()
            subprocess.run(
                ("git", "init", "-q", str(repository)),
                check=True,
                capture_output=True,
                text=True,
            )
            (repository / "untracked-user-work.txt").write_text("preserve me\n")
            environment = self.environment()
            environment["APT_AGENT_PROJECT_ROOT"] = str(repository)
            environment["APT_USE_NETWORK_TURBO"] = "0"
            completed = subprocess.run(
                (
                    str(ROOT / "scripts" / "remote" / "sync_code.sh"),
                    "codex/test-ref",
                ),
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(completed.returncode, 3)
        self.assertIn("REMOTE_TREE_DIRTY", completed.stderr)
        self.assertNotIn("PIDSMaker", completed.stderr)


if __name__ == "__main__":
    unittest.main()
