"""SQLite FTS5 storage with strict split/scenario lifecycle boundaries.

Requirements: REQ-MEMORY-001..007, REQ-LABEL-002, REQ-REPRO-001.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import Field, model_validator

from apt_detection_agent.schemas import (
    CaseState,
    DataSplit,
    MemoryLayer,
    MemoryRecord,
    StaticLTMSnapshot,
)
from apt_detection_agent.schemas.common import Identifier, StrictModel
from apt_detection_agent.schemas.common import assert_deployable_payload


def normalized_content_hash(content: str) -> str:
    normalized = " ".join(content.casefold().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


class MemoryNamespace(StrictModel):
    split: DataSplit
    scenario_id: Identifier
    episode_id: Identifier

    @property
    def key(self) -> str:
        return f"runtime:{self.split.value}:{self.scenario_id}:{self.episode_id}"


class RetrievalPolicy(StrictModel):
    token_budget: int = Field(default=2048, ge=1)
    hard_candidate_cap: int = Field(default=20, ge=1)
    validation_status: str = "unvalidated_engineering_default"

    @model_validator(mode="after")
    def not_claimed_optimal(self) -> "RetrievalPolicy":
        if self.validation_status == "optimal":
            raise ValueError("retrieval limits require validation sensitivity evidence")
        return self


class MemoryQuery(StrictModel):
    query: str = Field(min_length=1, max_length=2048)
    namespace: MemoryNamespace
    environment: str | None = None
    pids_id: Identifier | None = None
    top_k: int = Field(default=5, ge=1)


class RetrievalResult(StrictModel):
    records: tuple[MemoryRecord, ...]
    candidate_count: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    truncated: bool
    policy_validation_status: str


class StaticLTMSanitizer:
    """Deterministic first-pass deployability check before signed release."""

    FORBIDDEN_TEXT = (
        "ground truth",
        "teacher rationale",
        "counterfactual best action",
        "malicious node",
        "attack identity",
        "attack time",
        "campaign mapping",
        "dataset identity",
        "test label",
    )

    @classmethod
    def validate_record(cls, record: MemoryRecord) -> None:
        assert_deployable_payload(record.model_dump(mode="json"), "memory")
        searchable = " ".join(
            (
                record.environment,
                record.observable_behavior,
                record.action,
                record.content,
                *record.applicability_conditions,
            )
        ).casefold()
        matched = [term for term in cls.FORBIDDEN_TEXT if term in searchable]
        if matched:
            raise ValueError(f"static LTM contains privileged phrase: {matched[0]}")
        if record.normalized_content_hash != normalized_content_hash(record.content):
            raise ValueError("memory normalized_content_hash does not match content")

    @classmethod
    def validate_snapshot(cls, snapshot: StaticLTMSnapshot) -> None:
        ids = [record.memory_id for record in snapshot.records]
        if len(ids) != len(set(ids)):
            raise ValueError("static LTM record IDs must be unique")
        for record in snapshot.records:
            cls.validate_record(record)


@dataclass(frozen=True)
class WriteResult:
    memory_id: str
    inserted: bool
    duplicate_of: str | None = None


class MemoryStore:
    """Fixed harness; no dense embeddings, online LTM writes, or capacity eviction."""

    def __init__(self, path: Path, policy: RetrievalPolicy | None = None) -> None:
        self.path = path
        self.policy = policy or RetrievalPolicy()
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                namespace TEXT NOT NULL,
                layer TEXT NOT NULL,
                split TEXT NOT NULL,
                scenario_id TEXT,
                episode_id TEXT,
                normalized_hash TEXT NOT NULL,
                semantic_key TEXT NOT NULL,
                environment TEXT NOT NULL,
                pids_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                record_json TEXT NOT NULL,
                is_static INTEGER NOT NULL CHECK (is_static IN (0, 1)),
                UNIQUE(namespace, normalized_hash)
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                memory_id UNINDEXED, content, environment, observable_behavior, action
            );
            CREATE TABLE IF NOT EXISTS cases (
                case_id TEXT PRIMARY KEY,
                split TEXT NOT NULL,
                scenario_id TEXT NOT NULL,
                episode_id TEXT NOT NULL,
                state_json TEXT NOT NULL
            );
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @staticmethod
    def _semantic_key(record: MemoryRecord) -> str:
        value = "|".join(
            (
                record.environment.casefold(),
                record.observable_behavior.casefold(),
                record.pids.pids_id,
                record.pids.variant_id,
                record.action.casefold(),
            )
        )
        return hashlib.sha256(value.encode()).hexdigest()

    @staticmethod
    def _validate_runtime_scope(record: MemoryRecord, namespace: MemoryNamespace) -> None:
        if record.layer == MemoryLayer.STATIC_LTM:
            raise ValueError("static LTM is immutable at runtime")
        if (
            record.split != namespace.split
            or record.scenario_id != namespace.scenario_id
            or record.episode_id != namespace.episode_id
        ):
            raise ValueError("memory record cannot cross split/scenario/episode namespace")

    def write_runtime(self, record: MemoryRecord, namespace: MemoryNamespace) -> WriteResult:
        self._validate_runtime_scope(record, namespace)
        StaticLTMSanitizer.validate_record(record)
        duplicate = self.connection.execute(
            "SELECT memory_id FROM memories WHERE namespace=? AND normalized_hash=?",
            (namespace.key, record.normalized_content_hash),
        ).fetchone()
        if duplicate:
            return WriteResult(record.memory_id, False, str(duplicate["memory_id"]))
        self._insert(record, namespace.key, is_static=False)
        return WriteResult(record.memory_id, True)

    def load_static_snapshot(self, snapshot: StaticLTMSnapshot) -> None:
        StaticLTMSanitizer.validate_snapshot(snapshot)
        namespace = f"static:{snapshot.snapshot_id}"
        snapshot_ids = {record.memory_id for record in snapshot.records}
        with self.connection:
            for record in snapshot.records:
                self._insert(
                    record,
                    namespace,
                    is_static=True,
                    commit=False,
                    allowed_conflicts=snapshot_ids,
                )

    def _insert(
        self,
        record: MemoryRecord,
        namespace: str,
        *,
        is_static: bool,
        commit: bool = True,
        allowed_conflicts: set[str] | None = None,
    ) -> None:
        for conflict_id in record.conflicts_with:
            exists = self.connection.execute(
                "SELECT 1 FROM memories WHERE memory_id=?", (conflict_id,)
            ).fetchone()
            if not exists and conflict_id not in (allowed_conflicts or set()):
                raise ValueError(f"conflict target does not exist: {conflict_id}")
        payload = record.model_dump_json()
        self.connection.execute(
            """INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                record.memory_id,
                namespace,
                record.layer.value,
                record.split.value,
                record.scenario_id,
                record.episode_id,
                record.normalized_content_hash,
                self._semantic_key(record),
                record.environment,
                record.pids.pids_id,
                record.created_at.isoformat(),
                payload,
                int(is_static),
            ),
        )
        self.connection.execute(
            "INSERT INTO memory_fts VALUES (?, ?, ?, ?, ?)",
            (
                record.memory_id,
                record.content,
                record.environment,
                record.observable_behavior,
                record.action,
            ),
        )
        if commit:
            self.connection.commit()

    @staticmethod
    def _fts_query(query: str) -> str:
        tokens = re.findall(r"[\w.-]+", query.casefold(), flags=re.UNICODE)
        if not tokens:
            raise ValueError("query must contain searchable tokens")
        return " AND ".join(f'"{token}"' for token in tokens)

    def retrieve(self, request: MemoryQuery) -> RetrievalResult:
        limit = min(request.top_k, self.policy.hard_candidate_cap)
        conditions = ["(m.namespace=? OR m.is_static=1)"]
        parameters: list[object] = [request.namespace.key]
        if request.environment is not None:
            conditions.append("m.environment=?")
            parameters.append(request.environment)
        if request.pids_id is not None:
            conditions.append("m.pids_id=?")
            parameters.append(request.pids_id)
        parameters.extend((self._fts_query(request.query), self.policy.hard_candidate_cap))
        rows = self.connection.execute(
            f"""
            SELECT m.record_json, bm25(memory_fts) AS rank
            FROM memory_fts JOIN memories m USING(memory_id)
            WHERE {' AND '.join(conditions)} AND memory_fts MATCH ?
            ORDER BY rank, m.created_at DESC LIMIT ?
            """,
            parameters,
        ).fetchall()
        selected: list[MemoryRecord] = []
        estimated_tokens = 0
        for row in rows:
            record = MemoryRecord.model_validate_json(row["record_json"])
            cost = max(1, len(record.content) // 4)
            if len(selected) >= limit or estimated_tokens + cost > self.policy.token_budget:
                break
            selected.append(record)
            estimated_tokens += cost
        return RetrievalResult(
            records=tuple(selected),
            candidate_count=len(rows),
            estimated_tokens=estimated_tokens,
            truncated=len(selected) < len(rows),
            policy_validation_status=self.policy.validation_status,
        )

    def reset_namespace(self, namespace: MemoryNamespace) -> int:
        rows = self.connection.execute(
            "SELECT memory_id FROM memories WHERE namespace=? AND is_static=0", (namespace.key,)
        ).fetchall()
        ids = [str(row["memory_id"]) for row in rows]
        with self.connection:
            for memory_id in ids:
                self.connection.execute("DELETE FROM memory_fts WHERE memory_id=?", (memory_id,))
            self.connection.execute(
                "DELETE FROM memories WHERE namespace=? AND is_static=0", (namespace.key,)
            )
        return len(ids)

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM memories").fetchone()[0])


class CaseMemoryStore(MemoryStore):
    """Atomically persist Case State beside its exact runtime memory namespace."""

    def create_case(self, state: CaseState) -> None:
        expected_namespace = MemoryNamespace(
            split=state.split,
            scenario_id=state.scenario_id,
            episode_id=state.episode_id,
        )
        if state.memory_namespace != expected_namespace.key:
            raise ValueError("case memory_namespace must equal the lifecycle namespace")
        with self.connection:
            self.connection.execute(
                "INSERT INTO cases VALUES (?, ?, ?, ?, ?)",
                (
                    state.case_id,
                    state.split.value,
                    state.scenario_id,
                    state.episode_id,
                    state.model_dump_json(),
                ),
            )

    def get_case(self, case_id: str) -> CaseState:
        row = self.connection.execute(
            "SELECT state_json FROM cases WHERE case_id=?", (case_id,)
        ).fetchone()
        if row is None:
            raise KeyError(case_id)
        return CaseState.model_validate_json(row["state_json"])

    def update_case(self, state: CaseState) -> None:
        """Persist same-window controller state without changing lifecycle identity."""

        current = self.get_case(state.case_id)
        immutable_identity = (
            "split",
            "scenario_id",
            "episode_id",
            "memory_namespace",
            "current_window_sequence",
        )
        if any(getattr(state, name) != getattr(current, name) for name in immutable_identity):
            raise ValueError("same-window case update cannot change lifecycle identity or sequence")
        if state.updated_at < current.updated_at:
            raise ValueError("case update time cannot move backward")
        with self.connection:
            self.connection.execute(
                "UPDATE cases SET state_json=? WHERE case_id=?",
                (state.model_dump_json(), state.case_id),
            )

    def advance_case(self, case_id: str, *, next_sequence: int, updated_at: datetime) -> CaseState:
        current = self.get_case(case_id)
        if next_sequence != current.current_window_sequence + 1:
            raise ValueError("case windows must advance exactly once")
        committed = current.committed_config_id
        pending = current.pending_configuration
        if pending and pending.effective_sequence_number == next_sequence:
            committed = pending.config_id
            pending = None
        advanced = current.model_copy(
            update={
                "current_window_sequence": next_sequence,
                "committed_config_id": committed,
                "pending_configuration": pending,
                "updated_at": updated_at,
            }
        )
        advanced = CaseState.model_validate(advanced.model_dump())
        with self.connection:
            self.connection.execute(
                "UPDATE cases SET state_json=? WHERE case_id=?",
                (advanced.model_dump_json(), case_id),
            )
        return advanced

    def reset_episode(self, namespace: MemoryNamespace) -> tuple[int, int]:
        memory_count = self.reset_namespace(namespace)
        with self.connection:
            cursor = self.connection.execute(
                """DELETE FROM cases
                WHERE split=? AND scenario_id=? AND episode_id=?""",
                (namespace.split.value, namespace.scenario_id, namespace.episode_id),
            )
        return memory_count, cursor.rowcount
