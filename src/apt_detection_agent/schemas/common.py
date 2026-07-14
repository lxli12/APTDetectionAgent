"""Shared strict types for all controller contracts.

Requirements: REQ-GOV-001, REQ-LABEL-001, REQ-REPRO-001.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, StringConstraints


Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.:-]*$",
    ),
]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
GitSha = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]


class StrictModel(BaseModel):
    """Immutable model that rejects undeclared input fields."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)


PRIVILEGED_FIELD_NAMES = frozenset(
    {
        "ground_truth", "test_labels", "labels", "campaign_mapping",
        "malicious_entity_ids", "counterfactual_best_action", "attack_identity",
        "attack_time", "campaign_id", "dataset_identity", "evaluator_notes",
        "hidden_metrics", "teacher_rationale", "tp", "fp", "fn",
        "unique_malicious_node_tp", "unique_malicious_node_fp",
        "unique_malicious_node_fn",
    }
)


def assert_deployable_payload(value: object, path: str = "payload") -> None:
    """Reject privileged evaluator fields at a public contract boundary.

    Requirements: REQ-LABEL-001..004.
    """

    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in PRIVILEGED_FIELD_NAMES:
                raise ValueError(f"privileged field rejected at {path}.{key}")
            assert_deployable_payload(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            assert_deployable_payload(child, f"{path}[{index}]")


class DataSplit(str, Enum):
    AGENT_TRAINING = "agent_training"
    VALIDATION = "validation"
    HELD_OUT = "held_out"
    DEPLOYMENT = "deployment"


class PipelineStage(str, Enum):
    CONSTRUCTION = "construction"
    TRANSFORMATION = "transformation"
    FEATURIZATION = "featurization"
    FEAT_INFERENCE = "feat_inference"
    BATCHING = "batching"
    TRAINING = "training"
    INFERENCE = "inference"
    DETECTION = "detection"
    EVALUATION = "evaluation"
    RECONSTRUCTION = "reconstruction"
    TRIAGE = "triage"


class AvailabilityStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNVERIFIED = "unverified"
    BLOCKED = "blocked"


class ExperimentClass(str, Enum):
    CAUSAL_MAIN = "causal_main"
    COMPATIBILITY_BASELINE = "compatibility_baseline"


class TransductiveStatus(str, Enum):
    CAUSAL = "causal"
    TRANSDUCTIVE = "transductive"
    UNKNOWN = "unknown"


class DetectionUnit(str, Enum):
    NODE = "node"
    EDGE = "edge"
    NODE_TIME_WINDOW = "node_time_window"


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"


def require_utc_offset(value: datetime) -> datetime:
    """Reject naive datetimes even when constructed outside Pydantic parsing."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must include an explicit UTC offset")
    return value


Timestamp = AwareDatetime
