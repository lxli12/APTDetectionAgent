"""Causal threshold and standardized PIDSMaker result tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from apt_detection_agent.pidsmaker.results import (
    calibrate_validation_quantile,
    standardize_frozen_test_scores,
)
from apt_detection_agent.schemas import (
    DataSplit,
    ExperimentClass,
    ThresholdSourceSplit,
    TransductiveStatus,
)


class PIDSMakerResultTests(unittest.TestCase):
    def fixture(self, root: Path, *, label_column: bool = False) -> Path:
        run = root / "pids-run"
        pipeline = run / "pids_artifacts" / "pipeline"
        val = pipeline / "training" / "training" / "hash" / "CADETS_E3" / "edge_losses" / "val" / "model_epoch_0"
        test = pipeline / "training" / "training" / "hash" / "CADETS_E3" / "edge_losses" / "test" / "model_epoch_frozen"
        val.mkdir(parents=True)
        test.mkdir(parents=True)
        header = "loss,srcnode,dstnode,time,edge_type" + (",label" if label_column else "")
        suffix = ",0" if label_column else ""
        (val / "scores.csv").write_text(
            header + "\n1.0,1,2,1522809000000000001,3" + suffix + "\n3.0,2,3,1522809000000000002,4" + suffix + "\n"
        )
        (test / "scores.csv").write_text(
            header + "\n4.0,2,4,1523030400000000001,3" + suffix + "\n2.0,4,5,1523030400000000002,4" + suffix + "\n"
        )
        (pipeline / "checkpoint_manifest.json").write_text(
            json.dumps(
                {
                    "checkpoint_hash": "a" * 64,
                    "dataset_id": "CADETS_E3",
                    "source_config_id": "velox",
                }
            )
        )
        (pipeline / "inference_stage_summary.json").write_text(
            json.dumps({"elapsed_seconds": 0.5})
        )
        (pipeline / "resolved_config.yaml").write_text(
            json.dumps(
                {
                    "timezone": "America/New_York",
                    "window_size_seconds": 900,
                    "split_windows": {
                        "test": {
                            "start_ns": 1523030400000000000,
                            "end_ns": 1523031300000000000,
                        }
                    },
                }
            )
        )
        (run / "git_commit.txt").write_text("b" * 40 + "\n")
        return run

    def test_validation_quantile_is_frozen_before_test_standardization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.fixture(Path(temp))
            created = datetime(2026, 1, 1, tzinfo=timezone.utc)
            threshold = calibrate_validation_quantile(run, quantile=0.5, created_at=created)
            result = standardize_frozen_test_scores(run, threshold, created_at=created)
        self.assertEqual(threshold.source_split, ThresholdSourceSplit.VALIDATION)
        self.assertEqual(threshold.value, 1.0)
        self.assertEqual(result.split, DataSplit.VALIDATION)
        self.assertEqual(result.experiment_class.value, "causal_main")
        self.assertEqual(result.transductive_status.value, "causal")
        self.assertEqual({item.entity_id for item in result.scored_entities}, {"2", "4", "5"})
        self.assertTrue(next(item for item in result.scored_entities if item.entity_id == "2").alerted)

    def test_privileged_label_column_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.fixture(Path(temp), label_column=True)
            with self.assertRaisesRegex(ValueError, "privileged"):
                calibrate_validation_quantile(run, quantile=0.5)

    def test_causal_result_rejects_transductive_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run = self.fixture(Path(temp))
            threshold = calibrate_validation_quantile(run, quantile=0.5)
            with self.assertRaisesRegex(ValueError, "causal main result"):
                standardize_frozen_test_scores(
                    run,
                    threshold,
                    experiment_class=ExperimentClass.CAUSAL_MAIN,
                    transductive_status=TransductiveStatus.TRANSDUCTIVE,
                )


if __name__ == "__main__":
    unittest.main()
