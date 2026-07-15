"""Memory exchange contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id: str
    namespace: str
    content: str
    evidence_ids: tuple[str, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("memory content cannot be empty")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class MemoryQuery:
    namespace: str
    text: str
    limit: int = 5

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("memory query limit must be positive")
