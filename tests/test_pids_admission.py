"""Fail-closed PIDS formal-trajectory admission tests."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from pydantic import ValidationError

from apt_detection_agent.schemas import (
    AdmittedUse,
    AdmissionGate,
    AdmissionGateResult,
    DataSplit,
    ExperimentClass,
    PIDSAdmissionRecord,
    PIDSRef,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def passed_gate(gate: AdmissionGate) -> AdmissionGateResult:
    return AdmissionGateResult(
        gate=gate,
        passed=True,
        verified=True,
        evidence_artifact_ids=(f"evidence-{gate.value}",),
        evidence_class=(
            "real-non-synthetic-smoke"
            if gate == AdmissionGate.REAL_SMOKE
            else "reviewed-real-artifact"
        ),
        is_synthetic=False,
        label_blind=True,
    )


def record(**updates: object) -> dict[str, object]:
    gates = tuple(passed_gate(gate) for gate in AdmissionGate)
    values: dict[str, object] = {
        "admission_id": "admission-1",
        "pids": PIDSRef(pids_id="velox"),
        "dataset_or_scenario_id": "cadets-scenario-1",
        "split": DataSplit.AGENT_TRAINING,
        "experiment_class": ExperimentClass.CAUSAL_MAIN,
        "gate_version": "eight-gate-v1",
        "gate_results": gates,
        "admitted_for_formal_trajectory": True,
        "admitted_uses": (AdmittedUse.ADDITIONAL_INVESTIGATION,),
        "evidence_artifact_ids": tuple(
            artifact for gate in gates for artifact in gate.evidence_artifact_ids
        ),
        "reviewed_at": NOW,
        "reviewer_identity": "human-reviewer-1",
    }
    values.update(updates)
    return values


class PIDSAdmissionTests(unittest.TestCase):
    def test_all_eight_real_gates_are_required(self) -> None:
        admitted = PIDSAdmissionRecord.model_validate(record())
        self.assertTrue(admitted.admitted_for_formal_trajectory)
        with self.assertRaises(ValidationError):
            PIDSAdmissionRecord.model_validate(
                record(gate_results=tuple(passed_gate(gate) for gate in list(AdmissionGate)[:-1]))
            )

    def test_single_failed_gate_forces_not_admitted_and_no_uses(self) -> None:
        results = list(record()["gate_results"])
        results[1] = AdmissionGateResult(
            gate=AdmissionGate.CHECKPOINT,
            passed=False,
            verified=True,
            failure_reason_code="checkpoint-unloadable",
        )
        with self.assertRaises(ValidationError):
            PIDSAdmissionRecord.model_validate(record(gate_results=tuple(results)))
        rejected = PIDSAdmissionRecord.model_validate(
            record(
                gate_results=tuple(results),
                admitted_for_formal_trajectory=False,
                admitted_uses=(),
                evidence_artifact_ids=(),
            )
        )
        self.assertFalse(rejected.admitted_for_formal_trajectory)

    def test_synthetic_smoke_cannot_pass_real_smoke_gate(self) -> None:
        with self.assertRaises(ValidationError):
            AdmissionGateResult(
                gate=AdmissionGate.REAL_SMOKE,
                passed=True,
                verified=True,
                evidence_artifact_ids=("synthetic-smoke-1",),
                evidence_class="synthetic-smoke",
                is_synthetic=True,
                label_blind=True,
            )

    def test_passed_gate_requires_label_blind_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            AdmissionGateResult(
                gate=AdmissionGate.PARSER,
                passed=True,
                verified=True,
                evidence_artifact_ids=("parser-evidence-1",),
                evidence_class="reviewed-real-artifact",
                label_blind=False,
            )


if __name__ == "__main__":
    unittest.main()
