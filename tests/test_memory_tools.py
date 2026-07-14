"""Structured memory/case/report tool executor tests.

Requirements: REQ-TOOL-001..005, REQ-MEMORY-001..007,
REQ-CONFIG-001, REQ-LABEL-002..004, REQ-REPRO-001..002.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from apt_detection_agent.memory import CaseMemoryStore, MemoryNamespace
from apt_detection_agent.schemas import (
    CaseState,
    DataSplit,
    RunStatus,
    ToolName,
    ToolRequest,
)
from apt_detection_agent.tools import MemoryCaseToolService


NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


class MemoryCaseToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.namespace = MemoryNamespace(
            split=DataSplit.HELD_OUT,
            scenario_id="scenario-tools",
            episode_id="episode-tools",
        )
        self.store = CaseMemoryStore(self.root / "memory.sqlite3")
        self.store.create_case(
            CaseState(
                case_id="case-tools",
                scenario_id=self.namespace.scenario_id,
                episode_id=self.namespace.episode_id,
                split=self.namespace.split,
                current_window_sequence=4,
                committed_config_id="config-old",
                memory_namespace=self.namespace.key,
                updated_at=NOW,
            )
        )
        self.service = MemoryCaseToolService(
            store=self.store,
            namespace=self.namespace,
            case_id="case-tools",
            environment_profile="autodl-visible-profile",
            report_root=self.root / "reports",
            audit_path=self.root / "tool_calls.jsonl",
            clock=lambda: NOW,
        )

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def request(self, name: ToolName, arguments: dict[str, object], **updates: object) -> ToolRequest:
        values: dict[str, object] = {
            "tool_call_id": f"call-{name.value}",
            "tool_name": name,
            "case_id": "case-tools",
            "scenario_id": self.namespace.scenario_id,
            "episode_id": self.namespace.episode_id,
            "window_id": "window-4",
            "arguments": arguments,
            "requested_at": NOW,
        }
        values.update(updates)
        return ToolRequest.model_validate(values)

    def write_arguments(self, **updates: object) -> dict[str, object]:
        values: dict[str, object] = {
            "layer": "episode",
            "observable_behavior": "capability inspection reported a missing checkpoint",
            "pids_id": "velox",
            "variant_id": "default",
            "action": "retain the committed fast path",
            "content": "Capability inspection suggests retaining the committed fast path.",
            "evidence_artifact_ids": ["visible-artifact-1"],
        }
        values.update(updates)
        return values

    def test_write_then_retrieve_uses_executor_namespace(self) -> None:
        write = self.service.execute(
            self.request(ToolName.WRITE_MEMORY, self.write_arguments())
        )
        retrieve = self.service.execute(
            self.request(
                ToolName.RETRIEVE_MEMORY,
                {
                    "query": "capability inspection",
                    "pids_id": "velox",
                    "top_k": 5,
                },
            )
        )
        self.assertEqual(write.status, RunStatus.SUCCEEDED)
        self.assertTrue(write.standardized_observation["inserted"])
        self.assertEqual(retrieve.status, RunStatus.SUCCEEDED)
        self.assertEqual(len(retrieve.standardized_observation["records"]), 1)
        self.assertNotIn("environment", write.validated_arguments)
        record = retrieve.standardized_observation["records"][0]
        self.assertEqual(record["scenario_id"], self.namespace.scenario_id)
        self.assertNotIn("database_path", retrieve.model_dump_json())

    def test_update_case_can_schedule_only_exact_next_window(self) -> None:
        success = self.service.execute(
            self.request(
                ToolName.UPDATE_CASE,
                {"pending_config_id": "config-new", "effective_sequence_number": 5},
            )
        )
        failure = self.service.execute(
            self.request(
                ToolName.UPDATE_CASE,
                {"pending_config_id": "config-other", "effective_sequence_number": 4},
                tool_call_id="call-update-invalid",
            )
        )
        case = self.store.get_case("case-tools")
        self.assertEqual(success.status, RunStatus.SUCCEEDED)
        self.assertEqual(case.committed_config_id, "config-old")
        self.assertEqual(case.pending_configuration.config_id, "config-new")
        self.assertEqual(failure.status, RunStatus.FAILED)

    def test_report_path_is_executor_owned_and_append_only(self) -> None:
        request = self.request(
            ToolName.GENERATE_REPORT,
            {
                "title": "Visible case report",
                "summary": "Observable alert volume increased in the current window.",
                "visible_evidence_ids": ["visible-artifact-1"],
            },
        )
        first = self.service.execute(request)
        second = self.service.execute(request)
        reports = tuple((self.root / "reports").glob("*.md"))
        self.assertEqual(first.status, RunStatus.SUCCEEDED)
        self.assertEqual(second.status, RunStatus.FAILED)
        self.assertEqual(len(reports), 1)
        self.assertNotIn("private", reports[0].read_text().casefold())

    def test_hidden_report_phrase_and_static_ltm_write_fail_closed(self) -> None:
        leaked = self.service.execute(
            self.request(
                ToolName.GENERATE_REPORT,
                {
                    "title": "Case report",
                    "summary": "Ground truth identifies the target.",
                    "visible_evidence_ids": [],
                },
            )
        )
        static_write = self.service.execute(
            self.request(
                ToolName.WRITE_MEMORY,
                self.write_arguments(layer="static_ltm"),
                tool_call_id="call-static-write",
            )
        )
        self.assertEqual(leaked.status, RunStatus.FAILED)
        self.assertEqual(static_write.status, RunStatus.FAILED)
        self.assertEqual(self.store.count(), 0)

    def test_identity_escape_and_unknown_arguments_are_audited_failures(self) -> None:
        escaped = self.service.execute(
            self.request(
                ToolName.RETRIEVE_MEMORY,
                {"query": "anything"},
                scenario_id="other-scenario",
            )
        )
        unknown = self.service.execute(
            self.request(
                ToolName.RETRIEVE_MEMORY,
                {"query": "anything", "database_path": "/private/db"},
                tool_call_id="call-unknown-argument",
            )
        )
        audit = [json.loads(line) for line in (self.root / "tool_calls.jsonl").read_text().splitlines()]
        self.assertEqual(escaped.status, RunStatus.FAILED)
        self.assertEqual(unknown.status, RunStatus.FAILED)
        self.assertEqual(len(audit), 2)
        self.assertNotIn("/private/db", json.dumps(audit))


if __name__ == "__main__":
    unittest.main()
