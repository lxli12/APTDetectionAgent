"""Phase 3 causal stream, fitted-state, and leakage boundary tests.

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001,
REQ-WINDOW-001..004, REQ-CONFIG-001.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from apt_detection_agent.data import (
    CausalFeatureBoundary,
    CausalWindowStream,
    FittedStateArtifact,
    FittedStateBundle,
    FittedStateKind,
    RollingRangeCandidate,
    VisibleEvent,
)
from apt_detection_agent.schemas import DataSplit, PIDSRef, Prediction, TimeWindow
from apt_detection_agent.schemas.common import TransductiveStatus


ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)
SHA = "a" * 64
GIT_SHA = "b" * 40


def window(sequence: int) -> TimeWindow:
    start = ORIGIN + timedelta(minutes=15 * sequence)
    return TimeWindow(
        window_id=f"window-{sequence}",
        sequence_number=sequence,
        origin_time=ORIGIN,
        timezone="UTC",
        window_size_seconds=900,
        start=start,
        end=start + timedelta(minutes=15),
    )


def event(sequence: int, minute: int = 1, **updates: object) -> VisibleEvent:
    values: dict[str, object] = {
        "event_id": f"event-{sequence}-{minute}",
        "scenario_id": "scenario-1",
        "occurred_at": window(sequence).start + timedelta(minutes=minute),
        "event_type": "process-start",
        "entity_ids": ("node-1",),
        "attributes": {"executable": "visible-process"},
    }
    values.update(updates)
    return VisibleEvent.model_validate(values)


def prediction(sequence: int, config: str = "config-a") -> Prediction:
    current = window(sequence)
    return Prediction(
        prediction_id=f"prediction-{sequence}",
        case_id="case-1",
        scenario_id="scenario-1",
        episode_id="episode-1",
        split=DataSplit.HELD_OUT,
        window_id=current.window_id,
        window_sequence_number=sequence,
        committed_config_id=config,
        pids=(PIDSRef(pids_id="velox"),),
        alert_entity_ids=(),
        created_at=current.end,
        artifact_manifest_id=f"manifest-{sequence}",
    )


def fitted_artifact(**updates: object) -> FittedStateArtifact:
    values: dict[str, object] = {
        "artifact_id": "state-vocabulary",
        "kind": FittedStateKind.VOCABULARY,
        "source_dataset_id": "train-dataset",
        "source_split": DataSplit.AGENT_TRAINING,
        "fitted_through": ORIGIN - timedelta(days=2),
        "frozen_at": ORIGIN - timedelta(days=1),
        "content_hash": SHA,
        "code_commit": GIT_SHA,
        "transductive_status": TransductiveStatus.CAUSAL,
    }
    values.update(updates)
    return FittedStateArtifact.model_validate(values)


class ChronologicalStreamTests(unittest.TestCase):
    def stream(self) -> CausalWindowStream:
        return CausalWindowStream(
            scenario_id="scenario-1",
            episode_id="episode-1",
            split=DataSplit.HELD_OUT,
        )

    def test_multi_window_stream_commits_append_only_predictions(self) -> None:
        stream = self.stream()
        for sequence in (4, 5, 6):
            current = window(sequence)
            stream.open_next(
                window=current,
                events=(event(sequence),),
                committed_config_id="config-a",
                observed_at=current.end,
            )
            stream.commit_prediction(prediction(sequence))
        self.assertEqual(
            tuple(item.window_sequence_number for item in stream.predictions),
            (4, 5, 6),
        )

    def test_future_event_is_rejected_from_current_window(self) -> None:
        current = window(4)
        with self.assertRaises(ValidationError):
            self.stream().open_next(
                window=current,
                events=(event(5),),
                committed_config_id="config-a",
                observed_at=current.end,
            )

    def test_event_at_half_open_end_belongs_to_next_window(self) -> None:
        current = window(4)
        boundary_event = event(4, occurred_at=current.end)
        with self.assertRaises(ValidationError):
            self.stream().open_next(
                window=current,
                events=(boundary_event,),
                committed_config_id="config-a",
                observed_at=current.end,
            )

    def test_events_must_be_chronological(self) -> None:
        current = window(4)
        with self.assertRaises(ValidationError):
            self.stream().open_next(
                window=current,
                events=(event(4, 2), event(4, 1)),
                committed_config_id="config-a",
                observed_at=current.end,
            )

    def test_window_cannot_advance_without_prediction(self) -> None:
        stream = self.stream()
        current = window(4)
        stream.open_next(
            window=current,
            events=(),
            committed_config_id="config-a",
            observed_at=current.end,
        )
        with self.assertRaises(ValueError):
            stream.open_next(
                window=window(5),
                events=(),
                committed_config_id="config-a",
                observed_at=window(5).end,
            )

    def test_window_skip_is_rejected(self) -> None:
        stream = self.stream()
        current = window(4)
        stream.open_next(
            window=current,
            events=(),
            committed_config_id="config-a",
            observed_at=current.end,
        )
        stream.commit_prediction(prediction(4))
        with self.assertRaises(ValueError):
            stream.open_next(
                window=window(6),
                events=(),
                committed_config_id="config-a",
                observed_at=window(6).end,
            )

    def test_prediction_must_use_committed_fast_path_config(self) -> None:
        stream = self.stream()
        current = window(4)
        stream.open_next(
            window=current,
            events=(),
            committed_config_id="config-a",
            observed_at=current.end,
        )
        with self.assertRaises(ValueError):
            stream.commit_prediction(prediction(4, config="config-from-current-slow-path"))

    def test_prediction_cannot_predate_delayed_observation(self) -> None:
        stream = self.stream()
        current = window(4)
        stream.open_next(
            window=current,
            events=(),
            committed_config_id="config-a",
            observed_at=current.end + timedelta(seconds=1),
        )
        with self.assertRaises(ValueError):
            stream.commit_prediction(prediction(4))

    def test_prediction_rewrite_or_replay_is_rejected(self) -> None:
        stream = self.stream()
        current = window(4)
        stream.open_next(
            window=current,
            events=(),
            committed_config_id="config-a",
            observed_at=current.end,
        )
        stream.commit_prediction(prediction(4))
        with self.assertRaises(ValueError):
            stream.commit_prediction(prediction(4))

    def test_visible_event_rejects_hidden_label(self) -> None:
        with self.assertRaises(ValidationError):
            event(4, attributes={"ground_truth": "malicious"})


class FittedStateAndFeatureTests(unittest.TestCase):
    def test_heldout_fitted_state_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            fitted_artifact(source_split=DataSplit.HELD_OUT)

    def test_validation_cannot_refit_vocabulary(self) -> None:
        with self.assertRaises(ValidationError):
            fitted_artifact(source_split=DataSplit.VALIDATION)

    def test_validation_threshold_is_allowed_but_not_for_validation_use(self) -> None:
        threshold = fitted_artifact(
            artifact_id="state-threshold",
            kind=FittedStateKind.THRESHOLD,
            source_split=DataSplit.VALIDATION,
        )
        bundle = FittedStateBundle(bundle_id="bundle-1", artifacts=(threshold,))
        CausalFeatureBoundary.require_frozen_bundle(
            bundle,
            target_split=DataSplit.HELD_OUT,
            scenario_start=ORIGIN,
        )
        with self.assertRaises(ValueError):
            CausalFeatureBoundary.require_frozen_bundle(
                bundle,
                target_split=DataSplit.VALIDATION,
                scenario_start=ORIGIN,
            )

    def test_state_frozen_after_scenario_start_is_rejected(self) -> None:
        artifact = fitted_artifact(frozen_at=ORIGIN + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            CausalFeatureBoundary.require_frozen_bundle(
                FittedStateBundle(bundle_id="bundle-1", artifacts=(artifact,)),
                target_split=DataSplit.HELD_OUT,
                scenario_start=ORIGIN,
            )

    def test_transductive_state_is_compatibility_only(self) -> None:
        artifact = fitted_artifact(transductive_status=TransductiveStatus.TRANSDUCTIVE)
        bundle = FittedStateBundle(bundle_id="bundle-1", artifacts=(artifact,))
        with self.assertRaises(ValueError):
            CausalFeatureBoundary.require_frozen_bundle(
                bundle,
                target_split=DataSplit.HELD_OUT,
                scenario_start=ORIGIN,
            )
        CausalFeatureBoundary.require_frozen_bundle(
            bundle,
            target_split=DataSplit.HELD_OUT,
            scenario_start=ORIGIN,
            experiment_is_causal_main=False,
        )

    def test_parameter_free_feature_waits_for_window_and_uses_current_events(self) -> None:
        current = window(4)
        with self.assertRaises(ValueError):
            CausalFeatureBoundary.compute_parameter_free(
                window=current,
                event_ids=("event-1",),
                event_times=(current.start,),
                computed_at=current.start,
                feature_id="feature-1",
                compute=lambda ids: {"count": len(ids)},
            )
        result = CausalFeatureBoundary.compute_parameter_free(
            window=current,
            event_ids=("event-1",),
            event_times=(current.start,),
            computed_at=current.end,
            feature_id="feature-1",
            compute=lambda ids: {"count": len(ids)},
        )
        self.assertEqual(result.values, {"count": 1})

    def test_parameter_free_feature_rejects_future_event_and_hidden_output(self) -> None:
        current = window(4)
        with self.assertRaises(ValueError):
            CausalFeatureBoundary.compute_parameter_free(
                window=current,
                event_ids=("future-event",),
                event_times=(window(5).start,),
                computed_at=current.end,
                feature_id="feature-1",
                compute=lambda ids: {"count": len(ids)},
            )
        with self.assertRaises(ValidationError):
            CausalFeatureBoundary.compute_parameter_free(
                window=current,
                event_ids=(),
                event_times=(),
                computed_at=current.end,
                feature_id="feature-1",
                compute=lambda ids: {"labels": "hidden"},
            )

    def test_rolling_range_is_validation_candidate(self) -> None:
        candidate = RollingRangeCandidate(
            candidate_id="rolling-4",
            window_count=4,
            source_split=DataSplit.VALIDATION,
            calibrated_at=ORIGIN,
            code_commit=GIT_SHA,
        )
        self.assertEqual(candidate.window_count, 4)
        with self.assertRaises(ValidationError):
            RollingRangeCandidate(
                candidate_id="rolling-hardcoded",
                window_count=4,
                source_split=DataSplit.HELD_OUT,
                calibrated_at=ORIGIN,
                code_commit=GIT_SHA,
            )


if __name__ == "__main__":
    unittest.main()
