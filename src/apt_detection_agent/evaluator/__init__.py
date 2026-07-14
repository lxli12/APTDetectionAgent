"""Deprecated private-evaluator compatibility namespace.

Use explicit modules under :mod:`apt_detection_agent.evaluation`.
Requirements: REQ-LABEL-001..004, REQ-EVAL-001..007.
"""
from apt_detection_agent.evaluation.private import CampaignManifest, EvaluationRecord, HiddenGroundTruth
from apt_detection_agent.evaluation.calibration import (
    CALIBRATION_DEFINITION_VERSION, PrivateCoverageCalibrationResult,
    ValidationCoverageCalibrationInput, ValidationCoverageCalibrator, ValidationEntityScore,
)
from apt_detection_agent.evaluation.metrics import (
    METRIC_DEFINITION_VERSION, HiddenEvaluationInput, HiddenEvaluationOutput,
    HiddenEvaluator, ScoredEntity,
)
from apt_detection_agent.evaluation.ipc import DatabaseRolePolicy, EvaluatorIPCPaths
from apt_detection_agent.evaluation.teacher import (
    HiddenOfflineRunEvaluationLink, PrivateDatasetCompanionManifest,
    PrivateTeacherSelectionRecord, StrictTeacherSelectionParser,
)
__all__ = [name for name in globals() if not name.startswith("_")]
