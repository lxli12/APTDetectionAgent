"""Eight-gate PIDS admission contracts for real formal trajectories.

Requirements: REQ-PIDS-001..005, REQ-CAUSAL-001..004,
REQ-LABEL-001..004, REQ-RESOURCE-001..003, REQ-REPRO-001..003.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from .common import DataSplit, ExperimentClass, Identifier, StrictModel, Timestamp
from .pids import PIDSRef


class AdmissionGate(str, Enum):
    CAUSAL_CONFIG = "causal_config"
    CHECKPOINT = "checkpoint"
    THRESHOLD = "threshold"
    PARSER = "parser"
    RESOURCE_PROFILE = "resource_profile"
    STATE_RESET = "state_reset"
    REAL_SMOKE = "real_smoke"
    PROVENANCE = "provenance"


class AdmittedUse(str, Enum):
    COMMITTED_FAST_PATH = "committed_fast_path"
    ADDITIONAL_INVESTIGATION = "additional_investigation"
    TRAINING_CANDIDATE_CREATION = "training_candidate_creation"
    RESOURCE_PROFILE = "resource_profile"


class AdmissionGateResult(StrictModel):
    gate: AdmissionGate
    passed: bool
    verified: bool
    evidence_artifact_ids: tuple[Identifier, ...] = ()
    evidence_class: Identifier | None = None
    is_synthetic: bool = False
    label_blind: bool = True
    failure_reason_code: Identifier | None = None

    @model_validator(mode="after")
    def passed_gate_has_real_reviewable_evidence(self) -> "AdmissionGateResult":
        if self.passed:
            if not self.verified or not self.evidence_artifact_ids or not self.evidence_class:
                raise ValueError("passed admission gate requires verified evidence")
            if self.failure_reason_code:
                raise ValueError("passed admission gate cannot carry failure reason")
            if not self.label_blind:
                raise ValueError("admission evidence must be label blind")
            if self.gate == AdmissionGate.REAL_SMOKE:
                if self.is_synthetic or self.evidence_class != "real-non-synthetic-smoke":
                    raise ValueError("synthetic or zero-exit evidence cannot pass real smoke")
        elif not self.failure_reason_code:
            raise ValueError("failed admission gate requires an explicit reason")
        return self


class PIDSAdmissionRecord(StrictModel):
    schema_version: str = "pids-admission-record-v1"
    admission_id: Identifier
    pids: PIDSRef
    dataset_or_scenario_id: Identifier
    split: DataSplit
    experiment_class: ExperimentClass
    gate_version: Identifier
    gate_results: tuple[AdmissionGateResult, ...] = Field(min_length=8, max_length=8)
    admitted_for_formal_trajectory: bool
    admitted_uses: tuple[AdmittedUse, ...] = ()
    evidence_artifact_ids: tuple[Identifier, ...] = ()
    reviewed_at: Timestamp
    reviewer_identity: Identifier

    @model_validator(mode="after")
    def admission_requires_every_gate(self) -> "PIDSAdmissionRecord":
        gates = [result.gate for result in self.gate_results]
        if len(set(gates)) != len(gates) or set(gates) != set(AdmissionGate):
            raise ValueError("admission record must contain each gate exactly once")
        all_passed = all(result.passed for result in self.gate_results)
        if self.admitted_for_formal_trajectory != all_passed:
            raise ValueError("formal trajectory admission must equal all-gates-passed")
        if all_passed:
            if not self.admitted_uses or not self.evidence_artifact_ids:
                raise ValueError("admitted record requires scoped uses and evidence")
            nested_evidence = {
                artifact
                for result in self.gate_results
                for artifact in result.evidence_artifact_ids
            }
            if not set(self.evidence_artifact_ids).issubset(nested_evidence):
                raise ValueError("admission evidence must be traceable to gate evidence")
        elif self.admitted_uses:
            raise ValueError("failed admission cannot declare admitted uses")
        return self
