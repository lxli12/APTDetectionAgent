"""Unified high-level runtime catalog and tool tests."""

from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from apt_detection_agent.schemas import (
    AdmittedUse,
    AdditionalDetectorResult,
    AvailabilityStatus,
    CacheReuseClass,
    CalibrationMethod,
    DataSplit,
    DecisionSource,
    DetectionUnit,
    ExperimentClass,
    ExecutableAction,
    FrozenActionType,
    PIDSAdmissionRecord,
    PIDSRef,
    RecomputationScope,
    RunStatus,
    ScoreSummary,
    ThresholdProvenance,
    ThresholdSourceSplit,
    ToolName,
)
from apt_detection_agent.tools import (
    ApprovedDetectorCandidate,
    ApprovedResourcePreset,
    ApprovedThresholdCandidate,
    ApprovedTrainingRecipe,
    ComparableDetectionResult,
    CompareDetectorResultsRequest,
    FrozenRuntimeCatalog,
    InspectDetectorCapabilityRequest,
    IntendedUse,
    RuntimeToolService,
    TrainingExecutionResult,
    build_unadmitted_detector_candidates,
)
from apt_detection_agent.pidsmaker import PIDSMakerDiscovery
from tests.test_agent_runtime_contract import NOW, window
from tests.test_frozen_runtime import case
from tests.test_pids_admission import record as admission_payload


SHA = "a" * 64
GIT_SHA = "b" * 40


def admission(
    pids_id: str,
    *,
    admission_id: str,
    split: DataSplit = DataSplit.HELD_OUT,
    uses: tuple[AdmittedUse, ...] = (
        AdmittedUse.COMMITTED_FAST_PATH,
        AdmittedUse.ADDITIONAL_INVESTIGATION,
        AdmittedUse.RESOURCE_PROFILE,
    ),
) -> PIDSAdmissionRecord:
    return PIDSAdmissionRecord.model_validate(
        admission_payload(
            admission_id=admission_id,
        pids=PIDSRef(
            pids_id=pids_id,
            variant_id="fixed" if pids_id == "orthrus" else "default",
        ),
            dataset_or_scenario_id="scenario-1",
            split=split,
            admitted_uses=uses,
        )
    )


def detector_candidate(
    candidate_id: str,
    pids_id: str,
    use: IntendedUse,
    admission_id: str | None,
    *,
    status: AvailabilityStatus = AvailabilityStatus.AVAILABLE,
) -> ApprovedDetectorCandidate:
    return ApprovedDetectorCandidate(
        candidate_id=candidate_id,
        pids=PIDSRef(pids_id=pids_id, variant_id="fixed" if pids_id == "orthrus" else "default"),
        scenario_id="scenario-1",
        dataset_id="cadets",
        split=DataSplit.HELD_OUT,
        intended_use=use,
        admission_id=admission_id,
        availability_status=status,
        availability_reason_code="admitted" if status == AvailabilityStatus.AVAILABLE else "missing-real-smoke",
        purpose="Score deployment-visible provenance anomalies.",
        capability_type="event-surprise" if pids_id == "velox" else "node-role-surprise",
        detection_unit=DetectionUnit.NODE_TIME_WINDOW,
        score_semantics="higher-is-more-anomalous",
        cost_class="medium",
        required_state_status="frozen-reference",
        limitation_codes=() if status == AvailabilityStatus.AVAILABLE else ("not-real-admitted",),
        approved_config_id=f"approved-{candidate_id}",
        config_id=f"config-{candidate_id}",
        checkpoint_id=f"checkpoint-{candidate_id}",
        threshold_id=f"threshold-{candidate_id}",
        resource_preset_id=f"resource-{candidate_id}",
        state_initialization_policy_id="reset-v1",
        target_state_token=f"state-token-{candidate_id}",
        target_state_health="initialized",
    )


def decision(
    action_type: FrozenActionType,
    choice_id: str,
    tool: ToolName,
    *,
    effective: int | None,
) -> ExecutableAction:
    return ExecutableAction(
        proposal_id="proposal-1",
        action_id="action-1",
        action_type=action_type,
        decision_source=DecisionSource.LLM_AGENT,
        case_id="case-1",
        window_id="window-1",
        current_sequence_number=1,
        based_on_observation_id="observation-1",
        diagnosis_code="visible-symptom",
        visible_evidence_ids=("evidence-1",),
        requested_tool=tool,
        approved_choice_id=choice_id,
        expected_effect="bounded-runtime-effect",
        recomputation_scope=(
            RecomputationScope.CONFIGURATION_DEPENDENT
            if effective is not None
            else RecomputationScope.TRAINING_REQUIRED
            if action_type == FrozenActionType.RETRAIN_DETECTOR
            else RecomputationScope.INFERENCE_ONLY
        ),
        cache_reuse_class=CacheReuseClass.NONE,
        effective_sequence_number=effective,
        confidence=0.8,
        commit_policy="no-current-window-rewrite",
        fallback_policy=FrozenActionType.KEEP_CURRENT_CONFIG,
    )


class RuntimeToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.velox_admission = admission("velox", admission_id="admission-velox")
        self.orthrus_admission = admission("orthrus", admission_id="admission-orthrus")
        self.training_admission = admission(
            "velox",
            admission_id="admission-training",
            split=DataSplit.AGENT_TRAINING,
            uses=(AdmittedUse.TRAINING_CANDIDATE_CREATION,),
        )
        self.additional = detector_candidate(
            "candidate-additional",
            "velox",
            IntendedUse.ADDITIONAL_INVESTIGATION,
            "admission-velox",
        )
        self.config_change = detector_candidate(
            "candidate-config",
            "velox",
            IntendedUse.CONFIGURATION_CHANGE,
            "admission-velox",
        )
        self.switch = detector_candidate(
            "candidate-switch",
            "orthrus",
            IntendedUse.DETECTOR_SWITCH,
            "admission-orthrus",
        )
        self.unverified = detector_candidate(
            "candidate-unverified",
            "magic",
            IntendedUse.ADDITIONAL_INVESTIGATION,
            None,
            status=AvailabilityStatus.UNVERIFIED,
        )
        threshold = ApprovedThresholdCandidate(
            candidate_id="candidate-threshold",
            pids=PIDSRef(pids_id="velox"),
            scenario_id="scenario-1",
            dataset_id="cadets",
            split=DataSplit.HELD_OUT,
            admission_id="admission-velox",
            availability_status=AvailabilityStatus.AVAILABLE,
            availability_reason_code="admitted",
            config_id="config-1",
            checkpoint_id="checkpoint-1",
            threshold=ThresholdProvenance(
                threshold_id="threshold-validated",
                value=0.5,
                calibration_method=CalibrationMethod.VALIDATION_QUANTILE,
                source_dataset="cadets",
                source_split=ThresholdSourceSplit.VALIDATION,
                checkpoint_hash=SHA,
                target_metric="benign-score-quantile",
                created_at=NOW,
                code_commit=GIT_SHA,
            ),
            resource_preset_id="resource-preset-1",
            expected_alert_volume_effect="lower-alert-volume",
        )
        resource = ApprovedResourcePreset(
            preset_id="candidate-resource",
            pids=PIDSRef(pids_id="velox"),
            scenario_id="scenario-1",
            split=DataSplit.HELD_OUT,
            admission_id="admission-velox",
            availability_status=AvailabilityStatus.AVAILABLE,
            availability_reason_code="admitted",
            cost_class="medium",
            retry_policy_id="no-automatic-retry",
            cpu_vcpus=8,
            memory_gib=32,
            gpu_memory_gib=20,
        )
        recipe = ApprovedTrainingRecipe(
            recipe_id="candidate-training",
            pids=PIDSRef(pids_id="velox"),
            scenario_id="scenario-1",
            admission_id="admission-training",
            availability_status=AvailabilityStatus.AVAILABLE,
            availability_reason_code="admitted",
            allowed_input_splits=frozenset({DataSplit.AGENT_TRAINING}),
            output_candidate_prefix="quarantined-velox",
            cost_class="high",
        )
        self.catalog = FrozenRuntimeCatalog(
            admissions=(
                self.velox_admission,
                self.orthrus_admission,
                self.training_admission,
            ),
            detector_candidates=(
                self.additional,
                self.config_change,
                self.switch,
                self.unverified,
            ),
            threshold_candidates=(threshold,),
            resource_presets=(resource,),
            training_recipes=(recipe,),
        )
        visible_results = {
            "result-a": ComparableDetectionResult(
                result_id="result-a",
                execution_role="committed-fast-path",
                window=window(),
                detection_unit=DetectionUnit.NODE_TIME_WINDOW,
                score_semantics="higher-is-more-anomalous",
                calibration_id="calibration-a",
                score_summary=ScoreSummary(count=0),
                alert_entity_ids=("entity-1", "entity-2"),
                elapsed_seconds=1,
                resource_pressure_class="low",
            ),
            "result-b": ComparableDetectionResult(
                result_id="result-b",
                execution_role="additional-investigation",
                window=window(),
                detection_unit=DetectionUnit.NODE_TIME_WINDOW,
                score_semantics="higher-is-more-anomalous",
                calibration_id="calibration-b",
                score_summary=ScoreSummary(count=0),
                alert_entity_ids=("entity-2", "entity-3"),
                elapsed_seconds=2,
                resource_pressure_class="medium",
            ),
        }

        def run_additional(request, candidate, state):
            return AdditionalDetectorResult(
                investigation_id="investigation-tool",
                result_id="result-additional-tool",
                case_id=state.case_id,
                window=window(),
                approved_candidate_id=candidate.candidate_id,
                detector=candidate.pids,
                config_id=candidate.config_id,
                checkpoint_id=candidate.checkpoint_id,
                threshold_id=candidate.threshold_id,
                status=RunStatus.SUCCEEDED,
                score_summary=ScoreSummary(count=0),
                elapsed_seconds=2,
                resource_pressure_class="medium",
                provenance_id="provenance-additional",
            )

        self.service = RuntimeToolService(
            catalog=self.catalog,
            cases={"case-1": case()},
            results=visible_results,
            additional_runner=run_additional,
            training_runner=lambda recipe, state: TrainingExecutionResult(
                status=RunStatus.SUCCEEDED,
                candidate_id="quarantined-velox-1",
                provenance_id="training-provenance-1",
            ),
            comparison_profile_ids=frozenset({"visible-comparison-v1"}),
        )

    def test_capability_view_hides_implementation_and_keeps_unverified_entry(self) -> None:
        view = self.service.inspect_detector_capability(
            InspectDetectorCapabilityRequest(
                pids=PIDSRef(pids_id="magic"),
                scenario_id="scenario-1",
                split=DataSplit.HELD_OUT,
                intended_use=IntendedUse.ADDITIONAL_INVESTIGATION,
            )
        )
        self.assertEqual(view.available_status, AvailabilityStatus.UNVERIFIED)
        self.assertEqual(view.approved_candidate_ids, ())
        serialized = json.dumps(view.model_dump(mode="json")).casefold()
        for forbidden in ("path", "cuda", "yaml", "checkpoint_path", "implementation"):
            self.assertNotIn(forbidden, serialized)

    def test_available_candidate_cannot_exceed_admission_scope(self) -> None:
        bad = detector_candidate(
            "candidate-bad",
            "magic",
            IntendedUse.ADDITIONAL_INVESTIGATION,
            "admission-velox",
        )
        with self.assertRaisesRegex(ValueError, "exceeds scoped admission"):
            FrozenRuntimeCatalog(
                admissions=(self.velox_admission,), detector_candidates=(bad,)
            )

    def test_unavailable_choice_returns_sanitized_blocked_outcome_at_boundary(self) -> None:
        blocked = self.service.execute_action(
            decision(
                FrozenActionType.RUN_ADDITIONAL_DETECTOR,
                "candidate-unverified",
                ToolName.RUN_ADDITIONAL_DETECTOR,
                effective=None,
            )
        )
        self.assertEqual(blocked.outcome.status, RunStatus.BLOCKED)
        self.assertEqual(
            blocked.outcome.sanitized_failure_code,
            "catalog-admission-or-state-rejected",
        )
        self.assertIsNone(blocked.additional_result)

    def test_additional_tool_accepts_only_opaque_candidate_and_never_commits(self) -> None:
        result = self.service.run_additional_detector(
            decision(
                FrozenActionType.RUN_ADDITIONAL_DETECTOR,
                "candidate-additional",
                ToolName.RUN_ADDITIONAL_DETECTOR,
                effective=None,
            )
        )
        self.assertFalse(result.additional_result.committed)
        with self.assertRaises(ValidationError):
            InspectDetectorCapabilityRequest.model_validate(
                {
                    "pids": {"pids_id": "velox"},
                    "scenario_id": "scenario-1",
                    "split": "held_out",
                    "intended_use": "additional_investigation",
                    "cuda_device": 1,
                }
            )

    def test_switch_and_threshold_create_future_pending_without_current_mutation(self) -> None:
        switch = self.service.switch_detector(
            decision(
                FrozenActionType.SWITCH_DETECTOR,
                "candidate-switch",
                ToolName.SWITCH_DETECTOR,
                effective=2,
            )
        )
        self.assertEqual(case().committed_state.detector.pids_id, "velox")
        self.assertEqual(switch.pending_state.target_detector.pids_id, "orthrus")
        self.assertEqual(switch.pending_state.effective_sequence_number, 2)
        threshold = self.service.select_validated_threshold(
            decision(
                FrozenActionType.SELECT_VALIDATED_THRESHOLD,
                "candidate-threshold",
                ToolName.SELECT_VALIDATED_THRESHOLD,
                effective=2,
            )
        )
        self.assertEqual(threshold.pending_state.target_threshold_id, "threshold-validated")

    def test_compare_is_label_free_and_marks_calibration_mismatch(self) -> None:
        comparison = self.service.compare_detector_results(
            CompareDetectorResultsRequest(
                result_ids=("result-a", "result-b"),
                comparison_profile_id="visible-comparison-v1",
            )
        )
        self.assertFalse(comparison.comparable_score_distribution)
        self.assertTrue(comparison.comparable_alert_overlap)
        payload = json.dumps(comparison.model_dump(mode="json")).casefold()
        for forbidden in ("accuracy", "precision", "recall", "ground_truth", "campaign"):
            self.assertNotIn(forbidden, payload)

    def test_retraining_returns_quarantined_candidate_without_pending_activation(self) -> None:
        result = self.service.retrain_detector(
            decision(
                FrozenActionType.RETRAIN_DETECTOR,
                "candidate-training",
                ToolName.RETRAIN_DETECTOR,
                effective=None,
            )
        )
        self.assertEqual(result.outcome.result_id, "quarantined-velox-1")
        self.assertIsNone(result.pending_state)

    def test_training_recipe_rejects_heldout_inputs(self) -> None:
        with self.assertRaises(ValidationError):
            ApprovedTrainingRecipe(
                recipe_id="bad-recipe",
                pids=PIDSRef(pids_id="velox"),
                scenario_id="scenario-1",
                availability_status=AvailabilityStatus.UNAVAILABLE,
                availability_reason_code="forbidden-input",
                allowed_input_splits=frozenset({DataSplit.HELD_OUT}),
                output_candidate_prefix="bad",
                cost_class="high",
            )

    def test_discovery_bridge_retains_every_source_config_but_admits_none(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        capabilities = PIDSMakerDiscovery(root).capabilities()
        candidates = build_unadmitted_detector_candidates(
            capabilities,
            scenario_id="scenario-inventory",
            dataset_id="cadets",
            split=DataSplit.HELD_OUT,
        )
        source_ids = {item.source_config_id for item in capabilities}
        projected_sources = {
            item.candidate_id.removesuffix(f"-{item.intended_use.value}")
            for item in candidates
        }
        self.assertEqual(projected_sources, source_ids)
        self.assertEqual(len(candidates), len(capabilities) * 4)
        self.assertTrue(
            all(item.availability_status != AvailabilityStatus.AVAILABLE for item in candidates)
        )
        self.assertTrue(all(item.admission_id is None for item in candidates))


if __name__ == "__main__":
    unittest.main()
