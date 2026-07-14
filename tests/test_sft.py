"""Phase 10 SFT boundary, dataset, dry-run, and blocked-state tests.

Requirements: REQ-SFT-001..004, REQ-LABEL-002..004,
REQ-ARTIFACT-001..002, REQ-REPRO-001..003.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from apt_detection_agent.schemas import (
    ActionType,
    AgentAction,
    DataSplit,
    Observation,
    PIDSRef,
    ScoreSummary,
    TimeWindow,
)
from apt_detection_agent.sft import (
    HiddenTeacherRecord,
    SFTDatasetValidator,
    SFTSanitizer,
)
from apt_detection_agent.sft.compat.builder import build_dataset
from apt_detection_agent.training import (
    BLOCKED_BY_SFT_DATASET, SFTCheckpointManifest, SFTTrainingConfig,
)


ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SHA = "a" * 64
GIT_SHA = "b" * 40


def observation(record_id: str = "one") -> Observation:
    window = TimeWindow(
        window_id=f"sft-window-{record_id}",
        sequence_number=0,
        origin_time=NOW,
        timezone="UTC",
        window_size_seconds=900,
        start=NOW,
        end=NOW + timedelta(minutes=15),
    )
    return Observation(
        observation_id=f"sft-observation-{record_id}",
        scenario_id="sft-scenario",
        episode_id="sft-episode",
        split=DataSplit.AGENT_TRAINING,
        observed_at=window.end,
        window=window,
        environment_profile_id="sft-visible-environment",
        committed_config_id="sft-frozen-config",
        active_pids=(PIDSRef(pids_id="velox"),),
        score_summary=ScoreSummary(count=0),
    )


def action(obs: Observation, rationale: str = "Visible alert volume supports this action.") -> AgentAction:
    return AgentAction(
        action_id=f"sft-action-{obs.observation_id}",
        action_type=ActionType.NO_CHANGE,
        case_id="sft-case",
        window_id=obs.window.window_id,
        rationale=rationale,
        based_on_observation_id=obs.observation_id,
        deployment_evidence_ids=(obs.observation_id,),
    )


def teacher(record_id: str = "one", **updates: object) -> HiddenTeacherRecord:
    obs = observation(record_id)
    values: dict[str, object] = {
        "teacher_record_id": f"teacher-{record_id}",
        "source_split": DataSplit.AGENT_TRAINING,
        "student_observation": obs,
        "target_action": action(obs),
        "teacher_only_rationale": "Private synthetic explanation may use fixture truth.",
        "privileged_labels": {"synthetic_private_class": "positive"},
        "counterfactual_best_action": "private synthetic alternative",
        "source_trajectory_id": f"trajectory-{record_id}",
    }
    values.update(updates)
    return HiddenTeacherRecord.model_validate(values)


def dataset():
    return build_dataset(
        records=(teacher("one"), teacher("two")),
        validation_teacher_record_ids=frozenset({"teacher-two"}),
        dataset_id="synthetic-sft-v1",
        dataset_version="v1",
        code_commit=GIT_SHA,
        created_at=NOW,
        synthetic_only=True,
        formal_training_approved=False,
    )


class SFTBoundaryTests(unittest.TestCase):
    def test_teacher_privilege_is_removed_from_student_payload(self) -> None:
        student = SFTSanitizer.sanitize(teacher())
        text = student.model_dump_json().casefold()
        self.assertNotIn("teacher_only", text)
        self.assertNotIn("privileged_labels", text)
        self.assertNotIn("counterfactual_best_action", text)
        self.assertEqual(student.observation.split, DataSplit.AGENT_TRAINING)

    def test_student_rationale_cannot_expose_teacher_evidence(self) -> None:
        obs = observation()
        with self.assertRaises(ValueError):
            SFTSanitizer.sanitize(
                teacher(target_action=action(obs, "Ground truth says to take this action."))
            )

    def test_validation_or_heldout_teacher_record_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            teacher(source_split=DataSplit.HELD_OUT)

    def test_dataset_manifest_is_partitioned_hashed_and_synthetic(self) -> None:
        built = dataset()
        SFTDatasetValidator.validate(built)
        self.assertEqual(built.manifest.train_example_ids, ("student-teacher-one",))
        self.assertEqual(built.manifest.validation_example_ids, ("student-teacher-two",))
        self.assertFalse(built.manifest.formal_training_approved)

    def test_synthetic_dataset_cannot_claim_formal_approval(self) -> None:
        with self.assertRaises(ValidationError):
            build_dataset(
                records=(teacher(),),
                validation_teacher_record_ids=frozenset(),
                dataset_id="invalid-sft",
                dataset_version="v1",
                code_commit=GIT_SHA,
                created_at=NOW,
                synthetic_only=True,
                formal_training_approved=True,
            )

    def test_future_rl_is_not_exposed_as_a_current_sft_implementation(self) -> None:
        import apt_detection_agent.sft as public_sft

        self.assertFalse(hasattr(public_sft, "RLCandidate"))

    def test_checkpoint_manifest_rejects_unsafe_adapter_path(self) -> None:
        with self.assertRaises(ValidationError):
            SFTCheckpointManifest(
                checkpoint_id="checkpoint-1",
                base_model_id="llama-3.1-8b",
                base_model_hash=SHA,
                adapter_format="lora",
                adapter_relative_path="../escape",
                adapter_hash=SHA,
                dataset_hash=SHA,
                training_config_hash=SHA,
                code_commit=GIT_SHA,
                produced_at=NOW,
            )


class SFTCLITests(unittest.TestCase):
    def environment(self) -> dict[str, str]:
        return {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src")}

    def config(self, built, *, dry_run: bool) -> SFTTrainingConfig:
        return SFTTrainingConfig(
            config_id="sft-dry-run-v1",
            base_model_id="llama-3.1-8b",
            base_model_hash=SHA,
            dataset_id=built.manifest.dataset_id,
            dataset_hash=built.manifest.dataset_hash,
            seed=7,
            learning_rate=0.0001,
            epochs=1,
            max_sequence_length=512,
            dry_run=dry_run,
        )

    def test_missing_formal_dataset_reports_blocked_without_checkpoint(self) -> None:
        built = dataset()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config_path = root / "config.json"
            result_path = root / "result.json"
            config_path.write_text(self.config(built, dry_run=False).model_dump_json())
            completed = subprocess.run(
                (
                    sys.executable,
                    str(ROOT / "scripts" / "train_sft.py"),
                    "--dataset",
                    str(root / "missing.json"),
                    "--config",
                    str(config_path),
                    "--result",
                    str(result_path),
                ),
                env=self.environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            result = json.loads(result_path.read_text())
        self.assertEqual(completed.returncode, 3)
        self.assertEqual(result["status"], BLOCKED_BY_SFT_DATASET)
        self.assertIsNone(result["checkpoint_manifest"])

    def test_synthetic_dataset_dry_run_validates_without_weight_update(self) -> None:
        built = dataset()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset_path = root / "dataset.json"
            config_path = root / "config.json"
            result_path = root / "result.json"
            dataset_path.write_text(built.model_dump_json())
            config_path.write_text(self.config(built, dry_run=True).model_dump_json())
            completed = subprocess.run(
                (
                    sys.executable,
                    str(ROOT / "scripts" / "train_sft.py"),
                    "--dataset",
                    str(dataset_path),
                    "--config",
                    str(config_path),
                    "--result",
                    str(result_path),
                ),
                env=self.environment(),
                capture_output=True,
                text=True,
                check=False,
            )
            result = json.loads(result_path.read_text())
            files = tuple(path.name for path in root.iterdir())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["status"], "dry_run_validated")
        self.assertIsNone(result["checkpoint_manifest"])
        self.assertFalse(any("adapter" in name or "checkpoint" in name for name in files))


if __name__ == "__main__":
    unittest.main()
