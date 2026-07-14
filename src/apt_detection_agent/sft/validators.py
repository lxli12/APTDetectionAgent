"""Fail-closed semantic sanitization for canonical student demonstrations."""

from __future__ import annotations

from apt_detection_agent.schemas.common import assert_deployable_payload

from .models import CanonicalDemonstrationTrajectory, PublicOfflineRunRecord


class DemonstrationSanitizer:
    VERSION = "demonstration-sanitizer-v1"
    FORBIDDEN_PHRASES = (
        "ground truth",
        "test label",
        "teacher rationale",
        "counterfactual best action",
        "campaign mapping",
        "hidden campaign",
        "malicious entity",
        "attack identity",
        "dataset identity shortcut",
        "evaluator note",
    )

    @classmethod
    def validate_trajectory(cls, trajectory: CanonicalDemonstrationTrajectory) -> None:
        if trajectory.sanitizer_version != cls.VERSION:
            raise ValueError("trajectory sanitizer version is not the active frozen version")
        cls._validate(trajectory.model_dump(mode="json"), "trajectory")

    @classmethod
    def validate_offline_record(cls, record: PublicOfflineRunRecord) -> None:
        cls._validate(record.model_dump(mode="json"), "offline_record")

    @classmethod
    def _validate(cls, payload: object, path: str) -> None:
        assert_deployable_payload(payload, path)
        searchable = str(payload).casefold()
        matched = [phrase for phrase in cls.FORBIDDEN_PHRASES if phrase in searchable]
        if matched:
            raise ValueError(f"{path} contains privileged phrase: {matched[0]}")
