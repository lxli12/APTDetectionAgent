"""Deterministic canonical, trigger, and prompt builder tests."""

from __future__ import annotations

import unittest
from datetime import timedelta

from pydantic import ValidationError

from apt_detection_agent.controller import (
    CanonicalObservationInputs,
    DeterministicCanonicalObservationBuilder,
    DeterministicPromptBuilder,
    DeterministicTriggerPolicy,
    FrozenTriggerProfile,
    PromptBuilderConfig,
)
from apt_detection_agent.schemas import DataSplit, DetectionSignalSummary, ScoreSummary
from tests.test_agent_runtime_contract import NOW, canonical_observation
from tests.test_frozen_runtime import case, committed_bundle


def inputs(*, alert_count: int = 0) -> CanonicalObservationInputs:
    sample = canonical_observation()
    return CanonicalObservationInputs(
        builder_version="canonical-builder-v1",
        observation_id="observation-built-1",
        observed_at=NOW,
        environment=sample.environment,
        detection_signal=DetectionSignalSummary(
            score_summary=ScoreSummary(count=0),
            tail_mass=0,
            alert_count=alert_count,
            alert_ratio=0 if alert_count == 0 else 0.1,
            alert_entity_ids=() if alert_count == 0 else ("entity-1",),
            alert_score_bands={} if alert_count == 0 else {"high": 1},
        ),
        execution=sample.execution,
        capability_options=sample.capability_options,
        budget=sample.budget,
        memory=sample.memory,
        capability_type=sample.active_detection.capability_type,
        score_semantics=sample.active_detection.score_semantics,
        detection_unit=sample.active_detection.detection_unit,
    )


class ObservationBuilderTests(unittest.TestCase):
    def test_canonical_builder_is_deterministic_and_binds_raw_and_committed_state(self) -> None:
        bundle = committed_bundle(object())
        builder = DeterministicCanonicalObservationBuilder(
            input_provider=lambda result, state: inputs()
        )
        first = builder(bundle, case())
        second = builder(bundle, case())
        self.assertEqual(first, second)
        self.assertEqual(first.source_raw_state_id, bundle.raw_state.raw_state_id)
        self.assertEqual(first.active_detection.committed_state_id, "state-1")
        self.assertEqual(first.content_hash, first.expected_content_hash())

    def test_empirical_trigger_constants_require_validation_evidence(self) -> None:
        with self.assertRaises(ValidationError):
            FrozenTriggerProfile(
                profile_id="trigger-v1",
                source_split=DataSplit.VALIDATION,
                alert_count_threshold=2,
            )

    def test_trigger_uses_only_canonical_visible_signal_and_frozen_profile(self) -> None:
        builder = DeterministicCanonicalObservationBuilder(
            input_provider=lambda result, state: inputs(alert_count=1)
        )
        observation = builder(committed_bundle(object()), case())
        policy = DeterministicTriggerPolicy(
            profile=FrozenTriggerProfile(
                profile_id="trigger-v1",
                source_split=DataSplit.VALIDATION,
                alert_count_threshold=1,
                alert_count_calibration_artifact_id="validation-trigger-study-1",
            ),
            clock=lambda: NOW,
        )
        decision = policy(observation)
        self.assertTrue(decision.triggered)
        self.assertEqual(decision.reason_codes, ("validation-frozen-alert-volume",))

    def test_prompt_builder_is_reproducible_and_fails_closed_without_truncation_policy(self) -> None:
        observation = DeterministicCanonicalObservationBuilder(
            input_provider=lambda result, state: inputs(alert_count=1)
        )(committed_bundle(object()), case())
        trigger = DeterministicTriggerPolicy(
            profile=FrozenTriggerProfile(
                profile_id="trigger-v1",
                source_split=DataSplit.VALIDATION,
                alert_count_threshold=1,
                alert_count_calibration_artifact_id="validation-trigger-study-1",
            ),
            clock=lambda: NOW,
        )(observation)
        builder = DeterministicPromptBuilder(
            config=PromptBuilderConfig(
                builder_version="prompt-builder-v1",
                tokenizer_id="test-tokenizer-v1",
                token_budget=100,
            ),
            token_counter=lambda text: 10,
        )
        first = builder(observation, trigger, ())
        second = builder(observation, trigger, ())
        self.assertEqual(first, second)
        self.assertEqual(first.canonical_observation_hash, observation.content_hash)
        self.assertEqual(first.truncation_policy_id, "unresolved-requires-experiment")
        too_large = DeterministicPromptBuilder(
            config=PromptBuilderConfig(
                builder_version="prompt-builder-v1",
                tokenizer_id="test-tokenizer-v1",
                token_budget=100,
            ),
            token_counter=lambda text: 101,
        )
        with self.assertRaisesRegex(ValueError, "UNRESOLVED_REQUIRES_EXPERIMENT"):
            too_large(observation, trigger, ())

    def test_trigger_clock_cannot_precede_observation(self) -> None:
        observation = DeterministicCanonicalObservationBuilder(
            input_provider=lambda result, state: inputs()
        )(committed_bundle(object()), case())
        policy = DeterministicTriggerPolicy(
            profile=FrozenTriggerProfile(
                profile_id="trigger-v1",
                source_split=DataSplit.VALIDATION,
            ),
            clock=lambda: NOW - timedelta(seconds=1),
        )
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            policy(observation)


if __name__ == "__main__":
    unittest.main()
