"""Deterministic SFT dataset builder with explicit partitions.

Requirements: REQ-SFT-001..004, REQ-REPRO-001..002.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from apt_detection_agent.schemas import DataSplit

from .contracts import SFTDataset, SFTDatasetManifest
from .sanitizer import SFTSanitizer
from .teacher import HiddenTeacherRecord


def build_dataset(
    *,
    records: tuple[HiddenTeacherRecord, ...],
    validation_teacher_record_ids: frozenset[str],
    dataset_id: str,
    dataset_version: str,
    code_commit: str,
    created_at: datetime,
    synthetic_only: bool,
    formal_training_approved: bool,
) -> SFTDataset:
    if not records:
        raise ValueError("SFT dataset requires at least one teacher record")
    teacher_ids = {record.teacher_record_id for record in records}
    if not validation_teacher_record_ids.issubset(teacher_ids):
        raise ValueError("validation partition references unknown teacher records")
    examples = tuple(SFTSanitizer.sanitize(record) for record in records)
    digest = hashlib.sha256()
    for example in examples:
        digest.update(example.model_dump_json().encode())
        digest.update(b"\n")
    train_ids = tuple(
        example.example_id
        for record, example in zip(records, examples)
        if record.teacher_record_id not in validation_teacher_record_ids
    )
    validation_ids = tuple(
        example.example_id
        for record, example in zip(records, examples)
        if record.teacher_record_id in validation_teacher_record_ids
    )
    manifest = SFTDatasetManifest(
        dataset_id=dataset_id,
        dataset_version=dataset_version,
        source_split=DataSplit.AGENT_TRAINING,
        sanitizer_version=SFTSanitizer.VERSION,
        example_ids=tuple(example.example_id for example in examples),
        train_example_ids=train_ids,
        validation_example_ids=validation_ids,
        dataset_hash=digest.hexdigest(),
        code_commit=code_commit,
        created_at=created_at,
        synthetic_only=synthetic_only,
        formal_training_approved=formal_training_approved,
    )
    return SFTDataset(manifest=manifest, examples=examples)
