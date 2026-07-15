"""Storage interface and deterministic in-memory implementation."""

from __future__ import annotations

from typing import Protocol

from apt_detection_agent.schemas import MemoryRecord


class MemoryStore(Protocol):
    def put(self, record: MemoryRecord) -> None: ...
    def list(self, namespace: str) -> tuple[MemoryRecord, ...]: ...
    def clear(self, namespace: str) -> int: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, MemoryRecord]] = {}

    def put(self, record: MemoryRecord) -> None:
        self._records.setdefault(record.namespace, {})[record.memory_id] = record

    def list(self, namespace: str) -> tuple[MemoryRecord, ...]:
        records = self._records.get(namespace, {}).values()
        return tuple(sorted(records, key=lambda item: (item.created_at, item.memory_id)))

    def clear(self, namespace: str) -> int:
        return len(self._records.pop(namespace, {}))
