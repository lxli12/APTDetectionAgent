"""Trainer-neutral SFT boundary; no RL implementation.

Requirements: REQ-SFT-005..010, REQ-REPRO-001..003.
"""

from .interface import (
    BLOCKED_BY_SFT_DATASET, SFTCheckpointManifest, SFTTrainingConfig,
    SFTTrainingResult,
)
from .sft import validate_sft_inputs

__all__ = [
    "BLOCKED_BY_SFT_DATASET", "SFTCheckpointManifest", "SFTTrainingConfig",
    "SFTTrainingResult", "validate_sft_inputs",
]
