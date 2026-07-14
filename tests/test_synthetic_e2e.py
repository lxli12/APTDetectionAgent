"""Phase 9 multi-process synthetic end-to-end acceptance tests.

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001..004,
REQ-WINDOW-001..004, REQ-CONFIG-001..003, REQ-MEMORY-001..007,
REQ-TOOL-001..005, REQ-EVAL-001..006, REQ-REPRO-001..002.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from apt_detection_agent.evaluation.fixtures import build_synthetic_hidden_input


ROOT = Path(__file__).resolve().parents[1]
class SyntheticEndToEndTests(unittest.TestCase):
    def _public_environment(self) -> dict[str, str]:
        return {
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(ROOT / "src"),
        }

    def test_multi_window_agent_evaluator_and_public_report(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_root = root / "runs"
            private_root = root / "evaluator-private"
            run_root.mkdir()
            private_root.mkdir()
            run_id = "synthetic-e2e-test"
            run_dir = run_root / run_id
            agent = subprocess.run(
                (
                    sys.executable,
                    str(ROOT / "scripts" / "run_synthetic_agent_scenario.py"),
                    "--run-id",
                    run_id,
                    "--run-root",
                    str(run_root),
                    "--project-root",
                    str(ROOT),
                ),
                env=self._public_environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(agent.returncode, 0, agent.stderr)
            summary = json.loads((run_dir / "agent_summary.json").read_text())
            self.assertTrue(all(summary["checks"].values()))
            self.assertEqual(
                summary["committed_config_history"],
                ["synthetic-config-a"] * 3 + ["synthetic-config-b"],
            )

            request_path = private_root / "request.json"
            private_metrics_path = private_root / "metrics.json"
            feedback_path = run_dir / "evaluation_feedback.json"
            request_path.write_text(build_synthetic_hidden_input().model_dump_json())
            evaluator_environment = {
                **self._public_environment(),
                "HIDDEN_EVALUATOR_PRIVATE_ROOT": str(private_root),
                "AGENT_FEEDBACK_ROOT": str(run_dir),
            }
            evaluator = subprocess.run(
                (
                    sys.executable,
                    str(ROOT / "scripts" / "run_hidden_evaluator.py"),
                    "--private-input",
                    str(request_path),
                    "--private-output",
                    str(private_metrics_path),
                    "--public-feedback",
                    str(feedback_path),
                ),
                env=evaluator_environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(evaluator.returncode, 0, evaluator.stderr)

            finalizer = subprocess.run(
                (
                    sys.executable,
                    str(ROOT / "scripts" / "finalize_public_report.py"),
                    "--run-dir",
                    str(run_dir),
                    "--feedback",
                    str(feedback_path),
                    "--project-root",
                    str(ROOT),
                ),
                env=self._public_environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(finalizer.returncode, 0, finalizer.stderr)

            private_metrics = json.loads(private_metrics_path.read_text())
            self.assertEqual(private_metrics["record"]["campaign_coverage"], 1.0)
            self.assertEqual(private_metrics["record"]["unique_malicious_node_fp"], 1)
            public_metrics = (run_dir / "metrics.json").read_text().casefold()
            self.assertNotIn("campaign_coverage", public_metrics)
            self.assertNotIn("unique_malicious_node", public_metrics)
            self.assertNotIn("ground_truth", (run_dir / "trajectory.jsonl").read_text().casefold())
            status = json.loads((run_dir / "run_status.json").read_text())
            self.assertEqual(status["status"], "succeeded")
            self.assertFalse(status["formal_performance_claim"])
            self.assertTrue((run_dir / "artifact_manifest.json").is_file())

    def test_agent_module_has_no_hidden_evaluator_import(self) -> None:
        source = (ROOT / "src" / "apt_detection_agent" / "validation" / "synthetic.py").read_text()
        tree = ast.parse(source)
        imports = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        self.assertFalse(any(name.startswith("apt_detection_agent.evaluator") for name in imports))
        self.assertNotIn("apt_detection_agent.evaluation.private", imports)

    def test_synthetic_run_directory_is_never_overwritten(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_root = Path(temp)
            command = (
                sys.executable,
                str(ROOT / "scripts" / "run_synthetic_agent_scenario.py"),
                "--run-id",
                "collision-test",
                "--run-root",
                str(run_root),
                "--project-root",
                str(ROOT),
            )
            first = subprocess.run(
                command,
                env=self._public_environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            second = subprocess.run(
                command,
                env=self._public_environment(),
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertNotEqual(second.returncode, 0)


if __name__ == "__main__":
    unittest.main()
