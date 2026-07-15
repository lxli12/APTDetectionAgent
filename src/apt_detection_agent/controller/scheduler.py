"""Detection-window scheduling policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class WindowScheduler:
    interval: timedelta

    def __post_init__(self) -> None:
        if self.interval.total_seconds() <= 0:
            raise ValueError("scheduler interval must be positive")

    def next_after(self, previous_start: datetime) -> datetime:
        if previous_start.tzinfo is None:
            raise ValueError("window time must be timezone-aware")
        return previous_start + self.interval
