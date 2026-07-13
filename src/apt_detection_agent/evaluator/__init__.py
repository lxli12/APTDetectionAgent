"""Privileged hidden-evaluator schema surface.

This namespace must not be imported by the Agent controller process.
Requirements: REQ-LABEL-001..004, REQ-EVAL-001..006.
"""

from apt_detection_agent.schemas.evaluation import (
    CampaignManifest,
    EvaluationRecord,
    HiddenGroundTruth,
)

__all__ = ["CampaignManifest", "EvaluationRecord", "HiddenGroundTruth"]
