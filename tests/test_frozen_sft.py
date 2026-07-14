"""Frozen runtime v2 SFT dataset and trainer-interface tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from apt_detection_agent.schemas import (
    AdmissionGate,
    AdmissionGateResult,
    CanonicalAgentVisibleObservation,
    DataSplit,
    FrozenMemoryExchange,
    MemoryActionResponse,
    MemoryReadRequest,
    MemoryRetrievalResult,
    PIDSAdmissionRecord,
    RunStatus,
)
from apt_detection_agent.sft import (
    FrozenHiddenTeacherRecord,
    FrozenSFTDatasetValidator,
    FrozenSFTSanitizer,
)
from apt_detection_agent.sft.compat.frozen_builder import build_frozen_dataset
from apt_detection_agent.training import SFTTrainingConfig
from tests.test_agent_runtime_contract import NOW, canonical_payload, content_hash
from tests.test_frozen_runtime import action, prompt, trigger
from tests.test_pids_admission import record as admission_payload


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64
GIT_SHA = "b" * 40


def training_observation() -> CanonicalAgentVisibleObservation:
    payload = canonical_payload()
    payload["split"] = DataSplit.AGENT_TRAINING
    provisional = CanonicalAgentVisibleObservation.model_construct(
        **payload, content_hash="0" * 64
    )
    payload["content_hash"] = content_hash(
        provisional.model_dump(mode="json", exclude={"content_hash"})
    )
    return CanonicalAgentVisibleObservation.model_validate(payload)


def synthetic_unadmitted() -> PIDSAdmissionRecord:
    payload = admission_payload(
        admission_id="admission-sft-1",
        dataset_or_scenario_id="scenario-1",
        split=DataSplit.AGENT_TRAINING,
    )
    gates = list(payload["gate_results"])
    gates[1] = AdmissionGateResult(
        gate=AdmissionGate.CHECKPOINT,
        passed=False,
        verified=True,
        failure_reason_code="synthetic-fixture-has-no-real-checkpoint",
    )
    payload.update(
        {
            "gate_results": tuple(gates),
            "admitted_for_formal_trajectory": False,
            "admitted_uses": (),
            "evidence_artifact_ids": (),
        }
    )
    return PIDSAdmissionRecord.model_validate(payload)


def frozen_teacher(record_id: str, group_id: str) -> FrozenHiddenTeacherRecord:
    observation = training_observation()
    model_prompt = prompt(observation, trigger(True), ())
    target = action("finish_diagnosis")
    read = MemoryReadRequest(
        request_id=f"memory-read-{record_id}",
        prompt_id=model_prompt.prompt_id,
        case_id="case-1",
        needed=False,
        reason_code="no-memory-needed",
        visible_evidence_ids=(observation.observation_id,),
    )
    result = MemoryRetrievalResult(
        result_id=f"memory-result-{record_id}",
        request_id=read.request_id,
        needed=False,
        status=RunStatus.SUCCEEDED,
        candidate_count=0,
        estimated_tokens=0,
        truncated=False,
        policy_validation_status="unvalidated-engineering-default",
    )
    response = MemoryActionResponse(
        response_id=f"memory-response-{record_id}",
        prompt_id=model_prompt.prompt_id,
        retrieval_result_id=result.result_id,
        use_decisions=(),
        diagnosis_code="visible-no-change",
        action=target,
    )
    exchange = FrozenMemoryExchange(
        exchange_id=f"memory-exchange-{record_id}",
        prompt=model_prompt,
        read_request=read,
        retrieval_result=result,
        response=response,
    )
    return FrozenHiddenTeacherRecord(
        teacher_record_id=f"teacher-{record_id}",
        source_split=DataSplit.AGENT_TRAINING,
        source_trajectory_id=f"trajectory-{record_id}",
        partition_group_id=group_id,
        source_admission_ids=("admission-sft-1",),
        canonical_observation=observation,
        model_prompt=model_prompt,
        public_memory_exchange=exchange,
        target_action=target,
        teacher_only_rationale="Private labels may rank offline alternatives.",
        privileged_labels={"private_fixture_class": "positive"},
        counterfactual_best_action="private alternative",
    )


def dataset():
    return build_frozen_dataset(
        records=(frozen_teacher("one", "group-a"), frozen_teacher("two", "group-b")),
        admissions=(synthetic_unadmitted(),),
        validation_group_ids=frozenset({"group-b"}),
        dataset_id="synthetic-frozen-sft-v2",
        dataset_version="v2",
        code_commit=GIT_SHA,
        created_at=NOW,
        synthetic_only=True,
        formal_training_approved=False,
    )


class FrozenSFTTests(unittest.TestCase):
    def test_sanitizer_preserves_runtime_hashes_and_removes_teacher_privilege(self) -> None:
        teacher = frozen_teacher("one", "group-a")
        student = FrozenSFTSanitizer.sanitize(teacher)
        text = student.model_dump_json().casefold()
        self.assertEqual(
            student.model_prompt.canonical_observation_hash,
            student.canonical_observation.content_hash,
        )
        self.assertNotIn("teacher_only_rationale", text)
        self.assertNotIn("privileged_labels", text)
        self.assertNotIn("counterfactual_best_action", text)

    def test_synthetic_dataset_is_group_disjoint_but_claims_no_real_admission(self) -> None:
        built = dataset()
        FrozenSFTDatasetValidator.validate(built)
        self.assertEqual(built.manifest.train_group_ids, ("group-a",))
        self.assertEqual(built.manifest.validation_group_ids, ("group-b",))
        self.assertFalse(built.admissions[0].admitted_for_formal_trajectory)

    def test_formal_dataset_rejects_unadmitted_synthetic_fixture(self) -> None:
        with self.assertRaisesRegex(ValueError, "all-gates admission"):
            build_frozen_dataset(
                records=(frozen_teacher("one", "group-a"),),
                admissions=(synthetic_unadmitted(),),
                validation_group_ids=frozenset(),
                dataset_id="formal-invalid-sft",
                dataset_version="v2",
                code_commit=GIT_SHA,
                created_at=NOW,
                synthetic_only=False,
                formal_training_approved=True,
            )

    def test_teacher_cannot_substitute_prompt_or_target_after_runtime(self) -> None:
        teacher = frozen_teacher("one", "group-a")
        with self.assertRaises(ValidationError):
            FrozenHiddenTeacherRecord.model_validate(
                {
                    **teacher.model_dump(),
                    "model_prompt": {
                        **teacher.model_prompt.model_dump(),
                        "canonical_observation_hash": "f" * 64,
                    },
                }
            )

    def test_partition_is_by_group_not_individual_example(self) -> None:
        with self.assertRaises(ValueError):
            build_frozen_dataset(
                records=(frozen_teacher("one", "group-a"),),
                admissions=(synthetic_unadmitted(),),
                validation_group_ids=frozenset({"missing-group"}),
                dataset_id="bad-frozen-sft",
                dataset_version="v2",
                code_commit=GIT_SHA,
                created_at=NOW,
                synthetic_only=True,
                formal_training_approved=False,
            )

    def test_trainer_dry_run_accepts_frozen_v2_without_weight_update(self) -> None:
        built = dataset()
        config = SFTTrainingConfig(
            config_id="frozen-sft-dry-run-v2",
            base_model_id="llama-3.1-8b",
            base_model_hash=SHA,
            dataset_id=built.manifest.dataset_id,
            dataset_hash=built.manifest.dataset_hash,
            seed=7,
            learning_rate=0.0001,
            epochs=1,
            max_sequence_length=512,
            dry_run=True,
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            dataset_path = root / "dataset.json"
            config_path = root / "config.json"
            result_path = root / "result.json"
            dataset_path.write_text(built.model_dump_json())
            config_path.write_text(config.model_dump_json())
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
                env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src")},
                capture_output=True,
                text=True,
                check=False,
            )
            result = json.loads(result_path.read_text())
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["status"], "dry_run_validated")
        self.assertIsNone(result["checkpoint_manifest"])

    def test_frozen_runtime_synthetic_smoke_is_non_overwriting_and_nonformal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            command = (
                sys.executable,
                str(ROOT / "scripts" / "run_frozen_runtime_synthetic.py"),
                "--run-id",
                "frozen-runtime-fixture",
                "--run-root",
                str(root),
                "--code-commit",
                GIT_SHA,
            )
            environment = {
                "PATH": os.environ.get("PATH", ""),
                "PYTHONPATH": str(ROOT / "src"),
            }
            first = subprocess.run(
                command,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            second = subprocess.run(
                command,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            summary = json.loads(
                (root / "frozen-runtime-fixture" / "metrics.json").read_text()
            )
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertNotEqual(second.returncode, 0)
        self.assertFalse(summary["formal_performance_claim"])
        self.assertTrue(all(summary["checks"].values()))


if __name__ == "__main__":
    unittest.main()
