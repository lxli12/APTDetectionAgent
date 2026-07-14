"""Pre-SFT validation entrypoint contracts."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PreSFTValidationTests(unittest.TestCase):
    def test_validator_keeps_validation_separate_from_heldout_and_sft(self) -> None:
        text = (ROOT / "scripts" / "validate_pre_sft_bundle.py").read_text()
        self.assertIn('config.get("approved_splits") != ["validation"]', text)
        self.assertIn('manifest.get("sft_dataset_included") is not False', text)
        self.assertIn('availability.get("held_out_approved") is not False', text)
        self.assertIn('availability.get("deployment_approved") is not False', text)
        self.assertIn('threshold.get("source_split") != "validation"', text)


if __name__ == "__main__":
    unittest.main()
