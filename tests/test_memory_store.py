"""Phase 4 SQLite/FTS5 memory lifecycle and isolation tests.

Requirements: REQ-MEMORY-001..007, REQ-LABEL-002, REQ-REPRO-001.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from apt_detection_agent.memory import (
    CaseMemoryStore,
    MemoryNamespace,
    MemoryQuery,
    MemoryStore,
    RetrievalPolicy,
    normalized_content_hash,
)
from apt_detection_agent.schemas import (
    CaseState,
    DataSplit,
    MemoryLayer,
    MemoryRecord,
    PIDSRef,
    PendingConfiguration,
    StaticLTMSnapshot,
)


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SHA = "a" * 64


def namespace(
    split: DataSplit = DataSplit.HELD_OUT,
    scenario: str = "scenario-1",
    episode: str = "episode-1",
) -> MemoryNamespace:
    return MemoryNamespace(split=split, scenario_id=scenario, episode_id=episode)


def record(content: str, **updates: object) -> MemoryRecord:
    values: dict[str, object] = {
        "memory_id": f"memory-{normalized_content_hash(content)[:12]}",
        "layer": MemoryLayer.EPISODE,
        "split": DataSplit.HELD_OUT,
        "scenario_id": "scenario-1",
        "episode_id": "episode-1",
        "environment": "freebsd-cdm18",
        "observable_behavior": "rare process persistence",
        "pids": PIDSRef(pids_id="velox"),
        "action": "run slow path",
        "content": content,
        "normalized_content_hash": normalized_content_hash(content),
        "evidence_artifact_ids": ("artifact-1",),
        "created_at": NOW,
    }
    values.update(updates)
    return MemoryRecord.model_validate(values)


def static_record(content: str, **updates: object) -> MemoryRecord:
    values: dict[str, object] = {
        "layer": MemoryLayer.STATIC_LTM,
        "split": DataSplit.AGENT_TRAINING,
        "scenario_id": None,
        "episode_id": None,
    }
    values.update(updates)
    return record(content, **values)


def snapshot(records: tuple[MemoryRecord, ...]) -> StaticLTMSnapshot:
    return StaticLTMSnapshot(
        snapshot_id="ltm-v1",
        records=records,
        source_training_manifest_id="training-manifest-1",
        sanitizer_version="sanitizer-v1",
        provenance_hash=SHA,
        hidden_evaluator_signature="signature-placeholder-for-contract",
        human_sample_reviewed=True,
        frozen_at=NOW,
    )


class MemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = MemoryStore(Path(self.temp.name) / "memory.sqlite3")

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_sqlite_fts5_lexical_retrieval(self) -> None:
        item = record("Rare process persistence justified a slow path investigation.")
        self.store.write_runtime(item, namespace())
        result = self.store.retrieve(
            MemoryQuery(query="rare process", namespace=namespace(), top_k=5)
        )
        self.assertEqual(tuple(row.memory_id for row in result.records), (item.memory_id,))
        self.assertEqual(result.policy_validation_status, "unvalidated_engineering_default")

    def test_exact_normalized_dedup_within_episode(self) -> None:
        first = record("Observable score shift")
        second = record("  observable   SCORE shift  ", memory_id="memory-second")
        self.assertTrue(self.store.write_runtime(first, namespace()).inserted)
        duplicate = self.store.write_runtime(second, namespace())
        self.assertFalse(duplicate.inserted)
        self.assertEqual(duplicate.duplicate_of, first.memory_id)
        self.assertEqual(self.store.count(), 1)

    def test_same_content_is_isolated_across_scenarios(self) -> None:
        content = "Current episode evidence only"
        self.store.write_runtime(record(content), namespace())
        other = namespace(scenario="scenario-2", episode="episode-2")
        other_record = record(
            content,
            memory_id="memory-other",
            scenario_id="scenario-2",
            episode_id="episode-2",
        )
        self.assertTrue(self.store.write_runtime(other_record, other).inserted)
        result = self.store.retrieve(MemoryQuery(query="episode evidence", namespace=other))
        self.assertEqual(tuple(item.memory_id for item in result.records), ("memory-other",))

    def test_cross_split_or_scenario_write_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.write_runtime(record("isolated"), namespace(split=DataSplit.VALIDATION))
        with self.assertRaises(ValueError):
            self.store.write_runtime(record("isolated"), namespace(scenario="scenario-2"))

    def test_reset_removes_only_exact_runtime_namespace(self) -> None:
        self.store.write_runtime(record("first runtime memory"), namespace())
        other = namespace(scenario="scenario-2", episode="episode-2")
        self.store.write_runtime(
            record(
                "second runtime memory",
                scenario_id="scenario-2",
                episode_id="episode-2",
            ),
            other,
        )
        self.assertEqual(self.store.reset_namespace(namespace()), 1)
        self.assertEqual(self.store.count(), 1)

    def test_static_ltm_is_retrievable_but_runtime_immutable(self) -> None:
        static = static_record("Portable rare-process response experience")
        self.store.load_static_snapshot(snapshot((static,)))
        result = self.store.retrieve(
            MemoryQuery(query="portable experience", namespace=namespace())
        )
        self.assertEqual(result.records[0].layer, MemoryLayer.STATIC_LTM)
        with self.assertRaises(ValueError):
            self.store.write_runtime(static, namespace())
        self.assertEqual(self.store.reset_namespace(namespace()), 0)
        self.assertEqual(self.store.count(), 1)

    def test_privileged_static_ltm_text_is_rejected(self) -> None:
        leaked = static_record("Teacher rationale identifies a malicious node.")
        with self.assertRaises(ValueError):
            self.store.load_static_snapshot(snapshot((leaked,)))

    def test_hash_mismatch_is_rejected(self) -> None:
        mismatch = record("observable text", normalized_content_hash=SHA)
        with self.assertRaises(ValueError):
            self.store.write_runtime(mismatch, namespace())

    def test_conflicting_records_coexist_with_explicit_provenance(self) -> None:
        first = record("Slow path helped in this environment.")
        self.store.write_runtime(first, namespace())
        second = record(
            "Slow path exhausted the latency budget.",
            conflicts_with=(first.memory_id,),
            applicability_conditions=("high event rate",),
        )
        self.store.write_runtime(second, namespace())
        self.assertEqual(self.store.count(), 2)
        result = self.store.retrieve(
            MemoryQuery(query="slow path", namespace=namespace(), top_k=20)
        )
        self.assertEqual(len(result.records), 2)

    def test_unknown_conflict_target_is_rejected(self) -> None:
        item = record("conflicting evidence", conflicts_with=("missing-memory",))
        with self.assertRaises(ValueError):
            self.store.write_runtime(item, namespace())

    def test_candidate_cap_and_token_budget_are_enforced(self) -> None:
        self.store.close()
        self.store = MemoryStore(
            Path(self.temp.name) / "bounded.sqlite3",
            RetrievalPolicy(token_budget=5, hard_candidate_cap=2),
        )
        for index in range(3):
            content = f"common evidence record number {index} with extra text"
            self.store.write_runtime(record(content), namespace())
        result = self.store.retrieve(
            MemoryQuery(query="common evidence", namespace=namespace(), top_k=20)
        )
        self.assertLessEqual(len(result.records), 2)
        self.assertLessEqual(result.estimated_tokens, 5)
        self.assertTrue(result.truncated)

    def test_optimal_claim_without_validation_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            RetrievalPolicy(validation_status="optimal")

    def test_no_capacity_eviction_within_episode(self) -> None:
        for index in range(25):
            self.store.write_runtime(record(f"persistent item {index}"), namespace())
        self.assertEqual(self.store.count(), 25)


class CaseMemoryStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.store = CaseMemoryStore(Path(self.temp.name) / "case-memory.sqlite3")
        self.ns = namespace()

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def case(self, **updates: object) -> CaseState:
        values: dict[str, object] = {
            "case_id": "case-1",
            "scenario_id": self.ns.scenario_id,
            "episode_id": self.ns.episode_id,
            "split": self.ns.split,
            "current_window_sequence": 4,
            "committed_config_id": "config-old",
            "pending_configuration": PendingConfiguration(
                config_id="config-new",
                effective_sequence_number=5,
                requested_by_tool_call_id="call-1",
            ),
            "memory_namespace": self.ns.key,
            "updated_at": NOW,
        }
        values.update(updates)
        return CaseState.model_validate(values)

    def test_pending_config_applies_only_on_next_window(self) -> None:
        initial = self.case()
        self.store.create_case(initial)
        self.assertEqual(self.store.get_case("case-1").committed_config_id, "config-old")
        advanced = self.store.advance_case(
            "case-1",
            next_sequence=5,
            updated_at=NOW,
        )
        self.assertEqual(advanced.committed_config_id, "config-new")
        self.assertIsNone(advanced.pending_configuration)

    def test_case_cannot_skip_or_rewind_window(self) -> None:
        self.store.create_case(self.case(pending_configuration=None))
        with self.assertRaises(ValueError):
            self.store.advance_case("case-1", next_sequence=6, updated_at=NOW)
        with self.assertRaises(ValueError):
            self.store.advance_case("case-1", next_sequence=4, updated_at=NOW)

    def test_case_namespace_must_match_scope(self) -> None:
        with self.assertRaises(ValueError):
            self.store.create_case(self.case(memory_namespace="heldout-wrong"))

    def test_episode_reset_removes_case_and_runtime_memory_but_not_static_ltm(self) -> None:
        self.store.create_case(self.case(pending_configuration=None))
        self.store.write_runtime(record("runtime state"), self.ns)
        static = static_record("portable response experience")
        self.store.load_static_snapshot(snapshot((static,)))
        self.assertEqual(self.store.reset_episode(self.ns), (1, 1))
        with self.assertRaises(KeyError):
            self.store.get_case("case-1")
        self.assertEqual(self.store.count(), 1)


if __name__ == "__main__":
    unittest.main()
