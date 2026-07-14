"""Pre-SFT freeze contract tests."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PreSFTBundleTests(unittest.TestCase):
    def test_bundle_is_validation_only_and_explicitly_excludes_sft(self) -> None:
        text = (ROOT / "scripts" / "freeze_pre_sft_bundle.py").read_text()
        self.assertIn("frozenset({DataSplit.VALIDATION})", text)
        self.assertIn('"held_out_approved": False', text)
        self.assertIn('"deployment_approved": False', text)
        self.assertIn('"sft_dataset_included": False', text)
        self.assertIn('"sft_status": "BLOCKED_BY_SFT_DATASET"', text)
        self.assertNotIn("DataSplit.HELD_OUT})", text)

    def test_bundle_copies_frozen_model_and_featurizer_without_private_metrics(self) -> None:
        text = (ROOT / "scripts" / "freeze_pre_sft_bundle.py").read_text()
        self.assertIn("frozen_validation_checkpoint", text)
        self.assertIn("word2vec.model", text)
        self.assertNotIn("campaign_manifest.json", text)
        self.assertNotIn("evaluator-private", text)


if __name__ == "__main__":
    unittest.main()
