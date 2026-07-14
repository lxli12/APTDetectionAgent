"""Real causal PIDSMaker smoke entrypoint/finalizer contracts."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PIDSMakerSmokeTests(unittest.TestCase):
    def test_shell_entrypoint_has_causal_resource_and_secret_boundaries(self) -> None:
        script = (ROOT / "scripts" / "run_pidsmaker_smoke.sh").read_text()
        self.assertIn("CUDA_VISIBLE_DEVICES=1", script)
        self.assertIn("APT_PIDS_CPU_THREADS=16", script)
        self.assertIn("WANDB_MODE=disabled", script)
        self.assertIn("PIDS_WORKER_PASSWORD", script)
        self.assertNotIn("--database_password", script)
        self.assertIn("pidsmaker_causal_runner.py\" train", script)
        self.assertIn("pidsmaker_causal_runner.py\" infer", script)
        self.assertLess(script.index(" train \"${COMMON_ARGS[@]}\""), script.index(" infer \"${COMMON_ARGS[@]}\""))

    def test_finalizer_accepts_only_causal_label_free_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp) / "run"
            pipeline = run_dir / "pids_artifacts" / "pipeline"
            pipeline.mkdir(parents=True)
            (pipeline / "stage_summary.json").write_text(
                json.dumps(
                    {
                        "pidsmaker_commit": "a" * 40,
                        "compatibility_patch_series_hash": "b" * 64,
                        "completed_stages": [
                            {"stage": name}
                            for name in (
                                "construction",
                                "transformation",
                                "featurization",
                                "feat_inference",
                            )
                        ],
                    }
                )
            )
            (pipeline / "training_stage_summary.json").write_text(
                json.dumps(
                    {
                        "best_validation_score": 0.5,
                        "checkpoint_hash": "c" * 64,
                        "test_data_used_for_selection": False,
                        "wandb_used": False,
                    }
                )
            )
            (pipeline / "inference_stage_summary.json").write_text(
                json.dumps(
                    {
                        "checkpoint_hash": "c" * 64,
                        "test_labels_loaded": False,
                        "anomaly_score_mean": 0.25,
                        "peak_inference_cpu_memory_gib": 1.0,
                        "peak_inference_gpu_memory_gib": 2.0,
                        "time_per_batch_seconds": 0.1,
                    }
                )
            )
            (pipeline / "checkpoint_manifest.json").write_text(
                json.dumps({"checkpoint_hash": "c" * 64})
            )
            completed = subprocess.run(
                (
                    sys.executable,
                    str(ROOT / "scripts" / "finalize_pidsmaker_smoke.py"),
                    "--run-dir",
                    str(run_dir),
                ),
                capture_output=True,
                text=True,
                check=False,
            )
            metrics = json.loads((run_dir / "metrics.json").read_text())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertFalse(metrics["test_labels_loaded"])
        self.assertFalse(metrics["wandb_used"])
        self.assertEqual(metrics["evidence_class"], "bounded_smoke_not_formal_benchmark")


if __name__ == "__main__":
    unittest.main()
