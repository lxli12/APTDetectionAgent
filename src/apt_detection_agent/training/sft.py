"""Trainer-neutral validation of exported SFT inputs.

Requirements: REQ-SFT-005..010, REQ-REPRO-001..003.
"""

from .interface import SFTTrainingConfig


def validate_sft_inputs(
    config: SFTTrainingConfig, *, dataset_id: str, dataset_hash: str
) -> None:
    if config.dataset_id != dataset_id or config.dataset_hash != dataset_hash:
        raise ValueError("training config is not bound to the exported dataset")
