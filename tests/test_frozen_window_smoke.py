"""Frozen new-window runner must never refit or expose privileged labels."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FrozenWindowSmokeContractTests(unittest.TestCase):
    def test_shell_runner_uses_bundle_and_never_runs_training_or_featurization_fit(self) -> None:
        text = (ROOT / "scripts" / "run_frozen_pidsmaker_smoke.sh").read_text()
        self.assertIn("--frozen-bundle", text)
        self.assertIn("--stop-after feat_inference", text)
        self.assertNotIn("pidsmaker_causal_runner.py\" train", text)
        self.assertNotIn("--stop-after featurization", text)
        self.assertIn("CUDA_VISIBLE_DEVICES=1", text)
        self.assertIn("WANDB_MODE=disabled", text)

    def test_finalizer_requires_label_free_frozen_provenance(self) -> None:
        text = (ROOT / "scripts" / "finalize_frozen_window_smoke.py").read_text()
        self.assertIn("skipped_loaded_frozen_asset", text)
        self.assertIn("featurizer_fit_on_current_window", text)
        self.assertIn("test_labels_loaded", text)
        self.assertIn("formal_performance_claim", text)


if __name__ == "__main__":
    unittest.main()
