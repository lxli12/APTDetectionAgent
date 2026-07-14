"""Unified high-level Agent tools backed by frozen runtime catalogs.

Public requests accept only case/window identities and opaque approved catalog IDs.
Paths, CLI fragments, CUDA devices, raw configs, and free numeric overrides remain
executor-owned.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable

from pydantic import Field, model_validator

from apt_detection_agent.schemas import (
    ActionExecutionEnvelope,
    AdmittedUse,
    AdditionalDetectorRequest,
    AdditionalDetectorResult,
    AvailabilityStatus,
    CacheReuseClass,
    DataSplit,
    DetectionUnit,
    ExecutableAction,
    FrozenActionType,
    FrozenCaseState,
    HighLevelToolOutcome,
    PIDSAdmissionRecord,
    PIDSCapability,
    PIDSRef,
    PendingDetectionState,
    RecomputationScope,
    RunStatus,
    ScoreSummary,
    ThresholdProvenance,
    TimeWindow,
    ToolName,
)
from apt_detection_agent.schemas.common import Identifier, StrictModel
from apt_detection_agent.pidsmaker.admission import PIDSAdmissionRegistry


class IntendedUse(str, Enum):
    COMMITTED_FAST_PATH = "committed_fast_path"
    ADDITIONAL_INVESTIGATION = "additional_investigation"
    CONFIGURATION_CHANGE = "configuration_change"
    DETECTOR_SWITCH = "detector_switch"
    TRAINING_CANDIDATE_CREATION = "training_candidate_creation"
    RESOURCE_PROFILE = "resource_profile"


INTENDED_TO_ADMITTED_USE = {
    IntendedUse.COMMITTED_FAST_PATH: AdmittedUse.COMMITTED_FAST_PATH,
    IntendedUse.ADDITIONAL_INVESTIGATION: AdmittedUse.ADDITIONAL_INVESTIGATION,
    IntendedUse.CONFIGURATION_CHANGE: AdmittedUse.COMMITTED_FAST_PATH,
    IntendedUse.DETECTOR_SWITCH: AdmittedUse.COMMITTED_FAST_PATH,
    IntendedUse.TRAINING_CANDIDATE_CREATION: AdmittedUse.TRAINING_CANDIDATE_CREATION,
    IntendedUse.RESOURCE_PROFILE: AdmittedUse.RESOURCE_PROFILE,
}


class ApprovedDetectorCandidate(StrictModel):
    candidate_id: Identifier
    pids: PIDSRef
    scenario_id: Identifier
    dataset_id: Identifier
    split: DataSplit
    intended_use: IntendedUse
    admission_id: Identifier | None = None
    availability_status: AvailabilityStatus
    availability_reason_code: Identifier
    purpose: str = Field(min_length=1)
    capability_type: Identifier
    detection_unit: DetectionUnit
    score_semantics: Identifier
    cost_class: Identifier
    required_state_status: Identifier
    limitation_codes: tuple[Identifier, ...] = ()
    approved_config_id: Identifier
    config_id: Identifier
    checkpoint_id: Identifier
    threshold_id: Identifier
    resource_preset_id: Identifier
    state_initialization_policy_id: Identifier
    target_state_token: Identifier
    target_state_health: Identifier

    @model_validator(mode="after")
    def available_has_admission(self) -> "ApprovedDetectorCandidate":
        if self.availability_status == AvailabilityStatus.AVAILABLE and not self.admission_id:
            raise ValueError("available detector candidate requires admission record")
        return self


class ApprovedThresholdCandidate(StrictModel):
    candidate_id: Identifier
    pids: PIDSRef
    scenario_id: Identifier
    dataset_id: Identifier
    split: DataSplit
    admission_id: Identifier | None = None
    availability_status: AvailabilityStatus
    availability_reason_code: Identifier
    config_id: Identifier
    checkpoint_id: Identifier
    threshold: ThresholdProvenance
    resource_preset_id: Identifier
    expected_alert_volume_effect: Identifier


class ApprovedResourcePreset(StrictModel):
    preset_id: Identifier
    pids: PIDSRef
    scenario_id: Identifier
    split: DataSplit
    admission_id: Identifier | None = None
    availability_status: AvailabilityStatus
    availability_reason_code: Identifier
    cost_class: Identifier
    retry_policy_id: Identifier
    cpu_vcpus: int = Field(ge=1, le=32)
    memory_gib: int = Field(ge=1, le=240)
    gpu_memory_gib: int = Field(ge=0, le=24)


class ApprovedTrainingRecipe(StrictModel):
    recipe_id: Identifier
    pids: PIDSRef
    scenario_id: Identifier
    admission_id: Identifier | None = None
    availability_status: AvailabilityStatus
    availability_reason_code: Identifier
    allowed_input_splits: frozenset[DataSplit]
    output_candidate_prefix: Identifier
    cost_class: Identifier

    @model_validator(mode="after")
    def train_validation_only(self) -> "ApprovedTrainingRecipe":
        if not self.allowed_input_splits:
            raise ValueError("training recipe requires allowed inputs")
        if self.allowed_input_splits & {DataSplit.HELD_OUT, DataSplit.DEPLOYMENT}:
            raise ValueError("training cannot consume held-out/deployment inputs")
        return self


class InspectDetectorCapabilityRequest(StrictModel):
    pids: PIDSRef
    scenario_id: Identifier
    split: DataSplit
    intended_use: IntendedUse


class DetectorCapabilityView(StrictModel):
    pids: PIDSRef
    purpose: str
    capability_type: Identifier
    detection_unit: DetectionUnit
    cost_class: Identifier
    required_state_status: Identifier
    limitation_codes: tuple[Identifier, ...]
    available_status: AvailabilityStatus
    availability_reason_codes: tuple[Identifier, ...]
    approved_candidate_ids: tuple[Identifier, ...]


class ActiveDetectionStateView(StrictModel):
    case_id: Identifier
    detector: PIDSRef
    committed_state_id: Identifier
    approved_candidate_id: Identifier
    config_id: Identifier
    checkpoint_id: Identifier
    threshold_id: Identifier
    resource_preset_id: Identifier
    state_health: Identifier
    pending_change_id: Identifier | None = None
    pending_effective_sequence: int | None = None
    cache_reuse_class: CacheReuseClass
    recomputation_scope: RecomputationScope


class CompareDetectorResultsRequest(StrictModel):
    result_ids: tuple[Identifier, ...] = Field(min_length=2)
    comparison_profile_id: Identifier


class ComparableDetectionResult(StrictModel):
    result_id: Identifier
    execution_role: Identifier
    window: TimeWindow
    detection_unit: DetectionUnit
    score_semantics: Identifier
    calibration_id: Identifier
    score_summary: ScoreSummary
    alert_entity_ids: tuple[Identifier, ...]
    elapsed_seconds: float = Field(ge=0, allow_inf_nan=False)
    resource_pressure_class: Identifier


class DetectorResultComparison(StrictModel):
    comparison_profile_id: Identifier
    result_ids: tuple[Identifier, ...]
    same_window: bool
    comparable_score_distribution: bool
    comparable_alert_overlap: bool
    alert_intersection_count: int = Field(ge=0)
    alert_union_count: int = Field(ge=0)
    alert_counts: dict[Identifier, int]
    elapsed_seconds: dict[Identifier, float]
    resource_pressure_classes: dict[Identifier, Identifier]
    cautions: tuple[Identifier, ...]


class TrainingExecutionResult(StrictModel):
    status: RunStatus
    candidate_id: Identifier | None = None
    provenance_id: Identifier
    sanitized_failure_code: Identifier | None = None

    @model_validator(mode="after")
    def typed_result(self) -> "TrainingExecutionResult":
        if self.status == RunStatus.SUCCEEDED:
            if not self.candidate_id or self.sanitized_failure_code:
                raise ValueError("successful training requires quarantined candidate")
        elif not self.sanitized_failure_code or self.candidate_id:
            raise ValueError("failed training requires only sanitized failure")
        return self


AdditionalRunner = Callable[
    [AdditionalDetectorRequest, ApprovedDetectorCandidate, FrozenCaseState],
    AdditionalDetectorResult,
]
TrainingRunner = Callable[[ApprovedTrainingRecipe, FrozenCaseState], TrainingExecutionResult]


class FrozenRuntimeCatalog:
    """Frozen catalog where unavailable entries remain inspectable."""

    def __init__(
        self,
        *,
        admissions: tuple[PIDSAdmissionRecord, ...],
        detector_candidates: tuple[ApprovedDetectorCandidate, ...],
        threshold_candidates: tuple[ApprovedThresholdCandidate, ...] = (),
        resource_presets: tuple[ApprovedResourcePreset, ...] = (),
        training_recipes: tuple[ApprovedTrainingRecipe, ...] = (),
    ) -> None:
        self.admissions = self._unique(admissions, "admission_id")
        self.admission_registry = PIDSAdmissionRegistry(admissions)
        self.detector_candidates = self._unique(detector_candidates, "candidate_id")
        self.threshold_candidates = self._unique(threshold_candidates, "candidate_id")
        self.resource_presets = self._unique(resource_presets, "preset_id")
        self.training_recipes = self._unique(training_recipes, "recipe_id")
        groups = (
            self.detector_candidates,
            self.threshold_candidates,
            self.resource_presets,
            self.training_recipes,
        )
        if len(set().union(*(set(group) for group in groups))) != sum(map(len, groups)):
            raise ValueError("approved choice IDs must be globally unique")
        for item in self.detector_candidates.values():
            assert isinstance(item, ApprovedDetectorCandidate)
            self._validate_link(
                item.admission_id,
                item.availability_status,
                item.pids,
                item.scenario_id,
                item.split,
                INTENDED_TO_ADMITTED_USE[item.intended_use],
            )
        for item in self.threshold_candidates.values():
            assert isinstance(item, ApprovedThresholdCandidate)
            self._validate_link(
                item.admission_id,
                item.availability_status,
                item.pids,
                item.scenario_id,
                item.split,
                AdmittedUse.COMMITTED_FAST_PATH,
            )
        for item in self.resource_presets.values():
            assert isinstance(item, ApprovedResourcePreset)
            self._validate_link(
                item.admission_id,
                item.availability_status,
                item.pids,
                item.scenario_id,
                item.split,
                AdmittedUse.RESOURCE_PROFILE,
            )
        for item in self.training_recipes.values():
            assert isinstance(item, ApprovedTrainingRecipe)
            if item.availability_status == AvailabilityStatus.AVAILABLE:
                admission = self.admissions.get(str(item.admission_id))
                if not isinstance(admission, PIDSAdmissionRecord) or (
                    not admission.admitted_for_formal_trajectory
                    or admission.pids != item.pids
                    or admission.dataset_or_scenario_id != item.scenario_id
                    or admission.split not in item.allowed_input_splits
                    or AdmittedUse.TRAINING_CANDIDATE_CREATION not in admission.admitted_uses
                ):
                    raise ValueError("training recipe availability exceeds scoped admission")

    @staticmethod
    def _unique(items: tuple[object, ...], field: str) -> dict[str, object]:
        indexed = {str(getattr(item, field)): item for item in items}
        if len(indexed) != len(items):
            raise ValueError(f"duplicate frozen catalog identity: {field}")
        return indexed

    def _validate_link(
        self,
        admission_id: str | None,
        status: AvailabilityStatus,
        pids: PIDSRef,
        scenario_id: str,
        split: DataSplit,
        admitted_use: AdmittedUse,
    ) -> None:
        if status != AvailabilityStatus.AVAILABLE:
            return
        self.admission_registry.require_exact(
            admission_id=admission_id,
            pids=pids,
            scenario_id=scenario_id,
            split=split,
            admitted_use=admitted_use,
        )

    @staticmethod
    def require_available(item: object) -> None:
        if getattr(item, "availability_status") != AvailabilityStatus.AVAILABLE:
            raise ValueError(
                "approved choice is not available: "
                + str(getattr(item, "availability_reason_code"))
            )


CAPABILITY_TYPE_BY_PIDS = {
    "velox": "event-surprise",
    "orthrus": "temporal-event-model",
    "kairos": "temporal-event-model",
    "magic": "embedding-outlier",
    "flash": "node-role-surprise",
    "nodlink": "feature-reconstruction",
    "threatrace": "node-role-surprise",
    "rcaid": "root-context-anomaly",
}


def build_unadmitted_detector_candidates(
    capabilities: tuple[PIDSCapability, ...],
    *,
    scenario_id: str,
    dataset_id: str,
    split: DataSplit,
) -> tuple[ApprovedDetectorCandidate, ...]:
    """Project every discovered source config into inspectable, non-executable choices."""

    candidates: list[ApprovedDetectorCandidate] = []
    for capability in capabilities:
        status = (
            AvailabilityStatus.UNAVAILABLE
            if capability.current_availability_status == AvailabilityStatus.UNAVAILABLE
            else AvailabilityStatus.UNVERIFIED
        )
        reason = (
            "upstream-or-artifact-unavailable"
            if status == AvailabilityStatus.UNAVAILABLE
            else "not-admitted-eight-gate"
        )
        capability_type = CAPABILITY_TYPE_BY_PIDS.get(
            capability.pids.pids_id, "registered-provenance-anomaly"
        )
        for intended_use in (
            IntendedUse.COMMITTED_FAST_PATH,
            IntendedUse.ADDITIONAL_INVESTIGATION,
            IntendedUse.CONFIGURATION_CHANGE,
            IntendedUse.DETECTOR_SWITCH,
        ):
            identity = f"{capability.source_config_id}-{intended_use.value}"
            candidates.append(
                ApprovedDetectorCandidate(
                    candidate_id=identity,
                    pids=capability.pids,
                    scenario_id=scenario_id,
                    dataset_id=dataset_id,
                    split=split,
                    intended_use=intended_use,
                    availability_status=status,
                    availability_reason_code=reason,
                    purpose="Score deployment-visible provenance anomalies.",
                    capability_type=capability_type,
                    detection_unit=capability.detection_unit,
                    score_semantics="upstream-defined-unverified",
                    cost_class="unprofiled",
                    required_state_status="unverified",
                    limitation_codes=(
                        "not-admitted-eight-gate",
                        "no-formal-trajectory-use",
                    ),
                    approved_config_id=f"unavailable-{capability.source_config_id}",
                    config_id=f"unavailable-{capability.source_config_id}",
                    checkpoint_id="unavailable-checkpoint",
                    threshold_id="unavailable-threshold",
                    resource_preset_id="unavailable-resource-profile",
                    state_initialization_policy_id="unverified-state-reset",
                    target_state_token="unavailable-state-token",
                    target_state_health="unverified",
                )
            )
    return tuple(candidates)


@dataclass
class RuntimeToolService:
    catalog: FrozenRuntimeCatalog
    cases: dict[str, FrozenCaseState]
    results: dict[str, ComparableDetectionResult]
    additional_runner: AdditionalRunner
    training_runner: TrainingRunner
    comparison_profile_ids: frozenset[str]

    def inspect_detector_capability(
        self, request: InspectDetectorCapabilityRequest
    ) -> DetectorCapabilityView:
        matches = [
            item
            for item in self.catalog.detector_candidates.values()
            if isinstance(item, ApprovedDetectorCandidate)
            and item.pids == request.pids
            and item.scenario_id == request.scenario_id
            and item.split == request.split
            and item.intended_use == request.intended_use
        ]
        if not matches:
            raise ValueError("detector capability is not registered for context")
        first = matches[0]
        if len(
            {
                (item.purpose, item.capability_type, item.detection_unit, item.required_state_status)
                for item in matches
            }
        ) != 1:
            raise ValueError("detector capability catalog is inconsistent")
        statuses = {item.availability_status for item in matches}
        status = next(
            item
            for item in (
                AvailabilityStatus.AVAILABLE,
                AvailabilityStatus.BLOCKED,
                AvailabilityStatus.UNVERIFIED,
                AvailabilityStatus.UNAVAILABLE,
            )
            if item in statuses
        )
        return DetectorCapabilityView(
            pids=first.pids,
            purpose=first.purpose,
            capability_type=first.capability_type,
            detection_unit=first.detection_unit,
            cost_class=first.cost_class,
            required_state_status=first.required_state_status,
            limitation_codes=tuple(sorted({x for item in matches for x in item.limitation_codes})),
            available_status=status,
            availability_reason_codes=tuple(sorted({item.availability_reason_code for item in matches})),
            approved_candidate_ids=tuple(
                sorted(
                    item.candidate_id
                    for item in matches
                    if item.availability_status == AvailabilityStatus.AVAILABLE
                )
            ),
        )

    def inspect_active_detection_state(self, case_id: str) -> ActiveDetectionStateView:
        case = self._case(case_id)
        state, pending = case.committed_state, case.pending_state
        return ActiveDetectionStateView(
            case_id=case.case_id,
            detector=state.detector,
            committed_state_id=state.state_id,
            approved_candidate_id=state.approved_candidate_id,
            config_id=state.config_id,
            checkpoint_id=state.checkpoint_id,
            threshold_id=state.threshold_id,
            resource_preset_id=state.resource_preset_id,
            state_health=state.state_health,
            pending_change_id=pending.pending_change_id if pending else None,
            pending_effective_sequence=pending.effective_sequence_number if pending else None,
            cache_reuse_class=CacheReuseClass.UNKNOWN,
            recomputation_scope=RecomputationScope.NONE,
        )

    def run_additional_detector(self, action: ExecutableAction) -> ActionExecutionEnvelope:
        case = self._action_case(action, FrozenActionType.RUN_ADDITIONAL_DETECTOR)
        candidate = self._detector_candidate(action.approved_choice_id, case)
        if candidate.intended_use != IntendedUse.ADDITIONAL_INVESTIGATION:
            raise ValueError("candidate is not admitted for additional investigation")
        self.catalog.require_available(candidate)
        request = AdditionalDetectorRequest(
            request_id=f"additional-request-{action.action_id}",
            case_id=case.case_id,
            window_id=action.window_id,
            approved_candidate_id=candidate.candidate_id,
            investigation_reason_code=action.diagnosis_code,
            visible_evidence_ids=action.visible_evidence_ids,
        )
        result = self.additional_runner(request, candidate, case)
        return ActionExecutionEnvelope(
            outcome=HighLevelToolOutcome(
                outcome_id=f"outcome-{action.action_id}",
                action_id=action.action_id,
                tool_name=ToolName.RUN_ADDITIONAL_DETECTOR,
                status=result.status,
                approved_choice_id=candidate.candidate_id,
                result_id=result.result_id,
                sanitized_failure_code=result.sanitized_failure_code,
                provenance_id=result.provenance_id,
            ),
            additional_result=result,
        )

    def compare_detector_results(
        self, request: CompareDetectorResultsRequest
    ) -> DetectorResultComparison:
        if request.comparison_profile_id not in self.comparison_profile_ids:
            raise ValueError("comparison profile is not frozen")
        if len(set(request.result_ids)) != len(request.result_ids):
            raise ValueError("comparison result IDs must be unique")
        try:
            results = tuple(self.results[item] for item in request.result_ids)
        except KeyError as exc:
            raise ValueError("result is not in visible result store") from exc
        same_window = len({item.window.window_id for item in results}) == 1
        score_comparable = same_window and len(
            {(item.detection_unit, item.score_semantics, item.calibration_id) for item in results}
        ) == 1
        alert_comparable = same_window and len({item.detection_unit for item in results}) == 1
        sets = [set(item.alert_entity_ids) for item in results]
        intersection, union = set.intersection(*sets), set.union(*sets)
        cautions: list[str] = []
        if not same_window:
            cautions.append("different-window")
        if not score_comparable:
            cautions.append("score-not-comparable")
        if not alert_comparable:
            cautions.append("detection-unit-not-comparable")
        return DetectorResultComparison(
            comparison_profile_id=request.comparison_profile_id,
            result_ids=request.result_ids,
            same_window=same_window,
            comparable_score_distribution=score_comparable,
            comparable_alert_overlap=alert_comparable,
            alert_intersection_count=len(intersection) if alert_comparable else 0,
            alert_union_count=len(union) if alert_comparable else 0,
            alert_counts={item.result_id: len(item.alert_entity_ids) for item in results},
            elapsed_seconds={item.result_id: item.elapsed_seconds for item in results},
            resource_pressure_classes={
                item.result_id: item.resource_pressure_class for item in results
            },
            cautions=tuple(cautions),
        )

    def select_validated_threshold(self, action: ExecutableAction) -> ActionExecutionEnvelope:
        case = self._action_case(action, FrozenActionType.SELECT_VALIDATED_THRESHOLD)
        candidate = self.catalog.threshold_candidates.get(str(action.approved_choice_id))
        if not isinstance(candidate, ApprovedThresholdCandidate):
            raise ValueError("threshold candidate is not frozen")
        self.catalog.require_available(candidate)
        state = case.committed_state
        if (
            candidate.scenario_id != case.scenario_id
            or candidate.split != case.split
            or candidate.pids != state.detector
            or candidate.config_id != state.config_id
            or candidate.checkpoint_id != state.checkpoint_id
        ):
            raise ValueError("threshold candidate is not bound to active state")
        return self._pending_envelope(
            action,
            case,
            state.detector,
            state.approved_candidate_id,
            state.config_id,
            state.checkpoint_id,
            candidate.threshold.threshold_id,
            state.resource_preset_id,
            "preserve-compatible-state",
        )

    def load_approved_config(self, action: ExecutableAction) -> ActionExecutionEnvelope:
        case = self._action_case(action, FrozenActionType.LOAD_APPROVED_CONFIG)
        candidate = self._detector_candidate(action.approved_choice_id, case)
        self.catalog.require_available(candidate)
        if candidate.intended_use != IntendedUse.CONFIGURATION_CHANGE:
            raise ValueError("candidate is not an approved config change")
        if candidate.pids != case.committed_state.detector:
            raise ValueError("config load cannot silently switch detector")
        return self._candidate_pending(action, case, candidate)

    def switch_detector(self, action: ExecutableAction) -> ActionExecutionEnvelope:
        case = self._action_case(action, FrozenActionType.SWITCH_DETECTOR)
        candidate = self._detector_candidate(action.approved_choice_id, case)
        self.catalog.require_available(candidate)
        if candidate.intended_use != IntendedUse.DETECTOR_SWITCH:
            raise ValueError("candidate is not admitted for detector switching")
        if candidate.pids == case.committed_state.detector:
            raise ValueError("switch requires a different detector")
        return self._candidate_pending(action, case, candidate)

    def retrain_detector(self, action: ExecutableAction) -> ActionExecutionEnvelope:
        case = self._action_case(action, FrozenActionType.RETRAIN_DETECTOR)
        recipe = self.catalog.training_recipes.get(str(action.approved_choice_id))
        if not isinstance(recipe, ApprovedTrainingRecipe):
            raise ValueError("training recipe is not frozen")
        self.catalog.require_available(recipe)
        if recipe.pids != case.committed_state.detector or recipe.scenario_id != case.scenario_id:
            raise ValueError("training recipe does not match active state")
        result = self.training_runner(recipe, case)
        return ActionExecutionEnvelope(
            outcome=HighLevelToolOutcome(
                outcome_id=f"outcome-{action.action_id}",
                action_id=action.action_id,
                tool_name=ToolName.RETRAIN_DETECTOR,
                status=result.status,
                approved_choice_id=recipe.recipe_id,
                result_id=result.candidate_id if result.status == RunStatus.SUCCEEDED else None,
                sanitized_failure_code=result.sanitized_failure_code,
                provenance_id=result.provenance_id,
            )
        )

    def select_resource_preset(self, action: ExecutableAction) -> ActionExecutionEnvelope:
        case = self._action_case(action, FrozenActionType.SELECT_RESOURCE_PRESET)
        preset = self.catalog.resource_presets.get(str(action.approved_choice_id))
        if not isinstance(preset, ApprovedResourcePreset):
            raise ValueError("resource preset is not frozen")
        self.catalog.require_available(preset)
        state = case.committed_state
        if (
            preset.scenario_id != case.scenario_id
            or preset.split != case.split
            or preset.pids != state.detector
        ):
            raise ValueError("resource preset does not match active state")
        return self._pending_envelope(
            action,
            case,
            state.detector,
            state.approved_candidate_id,
            state.config_id,
            state.checkpoint_id,
            state.threshold_id,
            preset.preset_id,
            "preserve-compatible-state",
        )

    def execute_action(self, action: ExecutableAction) -> ActionExecutionEnvelope:
        handlers = {
            FrozenActionType.RUN_ADDITIONAL_DETECTOR: self.run_additional_detector,
            FrozenActionType.SELECT_VALIDATED_THRESHOLD: self.select_validated_threshold,
            FrozenActionType.LOAD_APPROVED_CONFIG: self.load_approved_config,
            FrozenActionType.SWITCH_DETECTOR: self.switch_detector,
            FrozenActionType.RETRAIN_DETECTOR: self.retrain_detector,
            FrozenActionType.SELECT_RESOURCE_PRESET: self.select_resource_preset,
        }
        try:
            handler = handlers[action.action_type]
        except KeyError as exc:
            raise ValueError("terminal action has no high-level tool") from exc
        try:
            return handler(action)
        except (ValueError, KeyError):
            return ActionExecutionEnvelope(
                outcome=HighLevelToolOutcome(
                    outcome_id=f"outcome-{action.action_id}",
                    action_id=action.action_id,
                    tool_name=action.requested_tool,
                    status=RunStatus.BLOCKED,
                    approved_choice_id=str(action.approved_choice_id),
                    sanitized_failure_code="catalog-admission-or-state-rejected",
                    provenance_id=f"tool-rejection-{action.action_id}",
                )
            )

    def _case(self, case_id: str) -> FrozenCaseState:
        try:
            return self.cases[case_id]
        except KeyError as exc:
            raise ValueError("case is not in runtime state store") from exc

    def _action_case(
        self, action: ExecutableAction, expected: FrozenActionType
    ) -> FrozenCaseState:
        if action.action_type != expected:
            raise ValueError("action was sent to wrong high-level tool")
        case = self._case(action.case_id)
        if action.current_sequence_number != case.current_window_sequence:
            raise ValueError("action timing does not match current case")
        return case

    def _detector_candidate(
        self, candidate_id: str | None, case: FrozenCaseState
    ) -> ApprovedDetectorCandidate:
        candidate = self.catalog.detector_candidates.get(str(candidate_id))
        if not isinstance(candidate, ApprovedDetectorCandidate):
            raise ValueError("detector candidate is not frozen")
        if candidate.scenario_id != case.scenario_id or candidate.split != case.split:
            raise ValueError("detector candidate context does not match case")
        return candidate

    def _candidate_pending(
        self,
        action: ExecutableAction,
        case: FrozenCaseState,
        candidate: ApprovedDetectorCandidate,
    ) -> ActionExecutionEnvelope:
        return self._pending_envelope(
            action,
            case,
            candidate.pids,
            candidate.candidate_id,
            candidate.config_id,
            candidate.checkpoint_id,
            candidate.threshold_id,
            candidate.resource_preset_id,
            candidate.state_initialization_policy_id,
            candidate.target_state_token,
            candidate.target_state_health,
        )

    @staticmethod
    def _pending_envelope(
        action: ExecutableAction,
        case: FrozenCaseState,
        detector: PIDSRef,
        approved_candidate_id: str,
        config_id: str,
        checkpoint_id: str,
        threshold_id: str,
        resource_preset_id: str,
        initialization_policy_id: str,
        target_state_token: str | None = None,
        target_state_health: str | None = None,
    ) -> ActionExecutionEnvelope:
        if action.effective_sequence_number is None:
            raise ValueError("persistent action requires future effective sequence")
        pending = PendingDetectionState(
            pending_change_id=f"pending-{action.action_id}",
            action_type=action.action_type,
            approved_choice_id=str(action.approved_choice_id),
            requested_by_action_id=action.action_id,
            effective_sequence_number=action.effective_sequence_number,
            target_detector=detector,
            target_config_id=config_id,
            target_checkpoint_id=checkpoint_id,
            target_threshold_id=threshold_id,
            target_resource_preset_id=resource_preset_id,
            state_initialization_policy_id=initialization_policy_id,
            target_state_token=target_state_token or case.committed_state.state_token,
            target_state_health=target_state_health or case.committed_state.state_health,
            rollback_state_id=case.committed_state.state_id,
        )
        return ActionExecutionEnvelope(
            outcome=HighLevelToolOutcome(
                outcome_id=f"outcome-{action.action_id}",
                action_id=action.action_id,
                tool_name=action.requested_tool,
                status=RunStatus.SUCCEEDED,
                approved_choice_id=str(action.approved_choice_id),
                pending_change_id=pending.pending_change_id,
                provenance_id=f"provenance-{action.action_id}",
            ),
            pending_state=pending,
        )
