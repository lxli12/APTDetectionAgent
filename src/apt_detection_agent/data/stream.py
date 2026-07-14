"""Strict chronological stream and append-only prediction ledger.

Requirements: REQ-CAUSAL-001, REQ-LABEL-001, REQ-WINDOW-001..003,
REQ-CONFIG-001.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from apt_detection_agent.schemas.common import DataSplit, Identifier, StrictModel, Timestamp
from apt_detection_agent.schemas.common import assert_deployable_payload
from apt_detection_agent.schemas.runtime import Prediction, TimeWindow


class VisibleEvent(StrictModel):
    event_id: Identifier
    scenario_id: Identifier
    occurred_at: Timestamp
    event_type: Identifier
    entity_ids: tuple[Identifier, ...]
    attributes: dict[str, str | int | float | bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def no_privileged_payload(self) -> "VisibleEvent":
        assert_deployable_payload(self.attributes, "event.attributes")
        return self


class WindowBatch(StrictModel):
    scenario_id: Identifier
    split: DataSplit
    window: TimeWindow
    committed_config_id: Identifier
    observed_at: Timestamp
    events: tuple[VisibleEvent, ...]

    @model_validator(mode="after")
    def current_window_only(self) -> "WindowBatch":
        if self.observed_at < self.window.end:
            raise ValueError("window cannot be observed before its end")
        for event in self.events:
            if event.scenario_id != self.scenario_id:
                raise ValueError("event scenario does not match stream scenario")
            if not self.window.start <= event.occurred_at < self.window.end:
                raise ValueError("batch contains a past or future-window event")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("event IDs must be unique within a window")
        if tuple(event.occurred_at for event in self.events) != tuple(
            sorted(event.occurred_at for event in self.events)
        ):
            raise ValueError("events must be ordered chronologically")
        return self


class CausalWindowStream:
    """Mutable orchestrator that cannot skip/replay windows or rewrite predictions."""

    def __init__(self, *, scenario_id: str, episode_id: str, split: DataSplit) -> None:
        self.scenario_id = scenario_id
        self.episode_id = episode_id
        self.split = split
        self._last_sequence: int | None = None
        self._last_window: TimeWindow | None = None
        self._open_batch: WindowBatch | None = None
        self._predictions: dict[int, Prediction] = {}

    @property
    def predictions(self) -> tuple[Prediction, ...]:
        return tuple(self._predictions[index] for index in sorted(self._predictions))

    def open_next(
        self,
        *,
        window: TimeWindow,
        events: tuple[VisibleEvent, ...],
        committed_config_id: str,
        observed_at: datetime,
    ) -> WindowBatch:
        if self._open_batch is not None:
            raise ValueError("current window requires a committed prediction before advancing")
        expected = (
            window.sequence_number if self._last_sequence is None else self._last_sequence + 1
        )
        if window.sequence_number != expected:
            raise ValueError("window sequence must be strictly contiguous")
        if self._last_window is not None:
            if window.start != self._last_window.end:
                raise ValueError("window boundaries must be contiguous")
            if (
                window.origin_time != self._last_window.origin_time
                or window.timezone != self._last_window.timezone
                or window.window_size_seconds != self._last_window.window_size_seconds
            ):
                raise ValueError("window alignment policy cannot change within a scenario")
        batch = WindowBatch(
            scenario_id=self.scenario_id,
            split=self.split,
            window=window,
            committed_config_id=committed_config_id,
            observed_at=observed_at,
            events=events,
        )
        self._open_batch = batch
        return batch

    def commit_prediction(self, prediction: Prediction) -> None:
        batch = self._open_batch
        if batch is None:
            raise ValueError("no open window exists for prediction")
        if (
            prediction.scenario_id != self.scenario_id
            or prediction.episode_id != self.episode_id
            or prediction.split != self.split
            or prediction.window_id != batch.window.window_id
            or prediction.window_sequence_number != batch.window.sequence_number
        ):
            raise ValueError("prediction identity does not match the open window")
        if prediction.committed_config_id != batch.committed_config_id:
            raise ValueError("prediction must use the current committed fast-path config")
        if prediction.created_at < batch.observed_at:
            raise ValueError("prediction cannot predate the deployment-visible observation")
        sequence = prediction.window_sequence_number
        if sequence in self._predictions:
            raise ValueError("formal prediction is append-only and cannot be rewritten")
        self._predictions[sequence] = prediction
        self._last_sequence = sequence
        self._last_window = batch.window
        self._open_batch = None
