"""Deterministic hidden-teacher to student-example sanitizer.

Requirements: REQ-SFT-001..002, REQ-LABEL-002..004.
"""

from __future__ import annotations

import hashlib

from apt_detection_agent.schemas.evaluation import assert_deployable_payload

from .contracts import StudentSFTExample
from .teacher import HiddenTeacherRecord


class SFTSanitizer:
    VERSION = "sft-sanitizer-v1"
    FORBIDDEN_RATIONALE_PHRASES = (
        "ground truth",
        "test label",
        "teacher rationale",
        "counterfactual best action",
        "campaign mapping",
        "attack identity",
        "dataset identity",
    )

    @classmethod
    def sanitize(cls, record: HiddenTeacherRecord) -> StudentSFTExample:
        rationale = record.target_action.rationale.casefold()
        matched = [phrase for phrase in cls.FORBIDDEN_RATIONALE_PHRASES if phrase in rationale]
        if matched:
            raise ValueError(f"student rationale contains privileged phrase: {matched[0]}")
        observation = record.student_observation
        action = record.target_action
        payload = {
            "observation": observation.model_dump(mode="json"),
            "target_action": action.model_dump(mode="json"),
        }
        assert_deployable_payload(payload, "sanitized_student_payload")
        content = StudentSFTExample.canonical_payload(observation, action)
        return StudentSFTExample(
            example_id=f"student-{record.teacher_record_id}",
            source_trajectory_id=record.source_trajectory_id,
            observation=observation,
            target_action=action,
            sanitizer_version=cls.VERSION,
            payload_hash=hashlib.sha256(content.encode()).hexdigest(),
        )
