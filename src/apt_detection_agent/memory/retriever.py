"""Deterministic lexical retrieval for the fixed initial memory mechanism."""

from __future__ import annotations

import re
from collections.abc import Iterable

from apt_detection_agent.schemas import MemoryQuery, MemoryRecord


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[\w-]+", text.casefold()))


class MemoryRetriever:
    def retrieve(
        self, records: Iterable[MemoryRecord], query: MemoryQuery
    ) -> tuple[MemoryRecord, ...]:
        query_tokens = _tokens(query.text)
        ranked = sorted(
            records,
            key=lambda record: (
                -len(query_tokens & _tokens(record.content)),
                -record.created_at.timestamp(),
                record.memory_id,
            ),
        )
        return tuple(ranked[: query.limit])
