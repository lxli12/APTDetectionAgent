"""Privileged hidden-evaluator schema surface.

This namespace must not be imported by the Agent controller process.
Requirements: REQ-LABEL-001..004, REQ-EVAL-001..006.
"""

from apt_detection_agent.schemas.evaluation import (
    CampaignManifest,
    EvaluationRecord,
    HiddenGroundTruth,
)
from .calibration import (
    CALIBRATION_DEFINITION_VERSION,
    PrivateCoverageCalibrationResult,
    ValidationCoverageCalibrationInput,
    ValidationCoverageCalibrator,
    ValidationEntityScore,
)
from .engine import (
    METRIC_DEFINITION_VERSION,
    HiddenEvaluationInput,
    HiddenEvaluationOutput,
    HiddenEvaluator,
    ScoredEntity,
)
from .ipc import DatabaseRolePolicy, EvaluatorIPCPaths

__all__ = [
    "CALIBRATION_DEFINITION_VERSION",
    "CampaignManifest",
    "EvaluationRecord",
    "DatabaseRolePolicy",
    "EvaluatorIPCPaths",
    "HiddenEvaluationInput",
    "HiddenEvaluationOutput",
    "HiddenEvaluator",
    "HiddenGroundTruth",
    "METRIC_DEFINITION_VERSION",
    "PrivateCoverageCalibrationResult",
    "ScoredEntity",
    "ValidationCoverageCalibrationInput",
    "ValidationCoverageCalibrator",
    "ValidationEntityScore",
]
