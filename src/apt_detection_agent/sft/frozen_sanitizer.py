"""Remove privileged teacher fields while preserving public runtime hashes."""

from __future__ import annotations

import hashlib

from apt_detection_agent.schemas.common import assert_deployable_payload

from .frozen_contracts import FrozenStudentSFTExample, frozen_example_payload
from .frozen_teacher import FrozenHiddenTeacherRecord


class FrozenSFTSanitizer:
    VERSION = "frozen-sft-sanitizer-v2"
    FORBIDDEN_TEXT = (
        "ground truth",
        "test label",
        "teacher rationale",
        "counterfactual best action",
        "campaign mapping",
        "attack identity",
        "dataset identity",
    )

    @classmethod
    def sanitize(cls, record: FrozenHiddenTeacherRecord) -> FrozenStudentSFTExample:
        public = {
            "canonical_observation": record.canonical_observation.model_dump(mode="json"),
            "model_prompt": record.model_prompt.model_dump(mode="json"),
            "memory_exchange": record.public_memory_exchange.model_dump(mode="json"),
            "target_action": record.target_action.model_dump(mode="json"),
        }
        assert_deployable_payload(public, "frozen_student_payload")
        searchable = str(public).casefold()
        matched = [item for item in cls.FORBIDDEN_TEXT if item in searchable]
        if matched:
            raise ValueError(f"frozen student payload contains privileged phrase: {matched[0]}")
        content = frozen_example_payload(
            canonical=record.canonical_observation,
            prompt=record.model_prompt,
            memory_exchange=record.public_memory_exchange,
            target_action=record.target_action,
            source_admission_ids=record.source_admission_ids,
        )
        return FrozenStudentSFTExample(
            example_id=f"student-{record.teacher_record_id}",
            source_trajectory_id=record.source_trajectory_id,
            partition_group_id=record.partition_group_id,
            canonical_observation=record.canonical_observation,
            model_prompt=record.model_prompt,
            memory_exchange=record.public_memory_exchange,
            target_action=record.target_action,
            source_admission_ids=record.source_admission_ids,
            sanitizer_version=cls.VERSION,
            payload_hash=hashlib.sha256(content.encode()).hexdigest(),
        )
