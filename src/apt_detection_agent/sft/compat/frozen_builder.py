"""Build frozen-runtime SFT datasets with group-disjoint partitions."""

from __future__ import annotations

import hashlib
from datetime import datetime

from apt_detection_agent.schemas import DataSplit, PIDSAdmissionRecord

from .frozen_contracts import (
    FrozenSFTDataset,
    FrozenSFTDatasetManifest,
    FrozenSFTDatasetValidator,
)
from .frozen_sanitizer import FrozenSFTSanitizer
from .frozen_teacher import FrozenHiddenTeacherRecord


def build_frozen_dataset(
    *,
    records: tuple[FrozenHiddenTeacherRecord, ...],
    admissions: tuple[PIDSAdmissionRecord, ...],
    validation_group_ids: frozenset[str],
    dataset_id: str,
    dataset_version: str,
    code_commit: str,
    created_at: datetime,
    synthetic_only: bool,
    formal_training_approved: bool,
) -> FrozenSFTDataset:
    if not records or not admissions:
        raise ValueError("frozen SFT dataset requires records and admissions")
    all_groups = {record.partition_group_id for record in records}
    if not validation_group_ids.issubset(all_groups):
        raise ValueError("validation partition references unknown group")
    examples = tuple(FrozenSFTSanitizer.sanitize(record) for record in records)
    admission_ids = tuple(item.admission_id for item in admissions)
    digest = hashlib.sha256()
    for admission in admissions:
        digest.update(admission.model_dump_json().encode())
        digest.update(b"\n")
    for example in examples:
        digest.update(example.model_dump_json().encode())
        digest.update(b"\n")
    train_groups = tuple(sorted(all_groups - validation_group_ids))
    validation_groups = tuple(sorted(validation_group_ids))
    manifest = FrozenSFTDatasetManifest(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        source_split=DataSplit.AGENT_TRAINING,
        sanitizer_version=FrozenSFTSanitizer.VERSION,
        example_ids=tuple(item.example_id for item in examples),
        example_group_ids={item.example_id: item.partition_group_id for item in examples},
        train_group_ids=train_groups,
        validation_group_ids=validation_groups,
        source_admission_ids=admission_ids,
        dataset_hash=digest.hexdigest(),
        code_commit=code_commit,
        created_at=created_at,
        synthetic_only=synthetic_only,
        formal_training_approved=formal_training_approved,
    )
    dataset = FrozenSFTDataset(manifest=manifest, admissions=admissions, examples=examples)
    FrozenSFTDatasetValidator.validate(dataset)
    return dataset
