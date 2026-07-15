"""Memory lifecycle facade used by the controller."""

from __future__ import annotations

from apt_detection_agent.schemas import MemoryQuery, MemoryRecord

from .memory_retriever import MemoryRetriever
from .memory_store import MemoryStore


class MemoryManager:
    def __init__(self, store: MemoryStore, retriever: MemoryRetriever | None = None) -> None:
        self.store = store
        self.retriever = retriever or MemoryRetriever()

    def remember(self, record: MemoryRecord) -> None:
        self.store.put(record)

    def recall(self, query: MemoryQuery) -> tuple[MemoryRecord, ...]:
        return self.retriever.retrieve(self.store.list(query.namespace), query)

    def reset(self, namespace: str) -> int:
        return self.store.clear(namespace)
