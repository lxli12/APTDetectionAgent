"""Validation-only retrieval sensitivity harness tests.

Requirements: REQ-MEMORY-003..007, REQ-LABEL-001..004, REQ-REPRO-001..002.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from apt_detection_agent.memory import normalized_content_hash
from apt_detection_agent.schemas import DataSplit, MemoryLayer, MemoryRecord, PIDSRef


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "memory_sensitivity", ROOT / "scripts" / "run_memory_retrieval_sensitivity.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)
NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
SHA = "a" * 64


def memory(memory_id: str, content: str) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        layer=MemoryLayer.STATIC_LTM,
        split=DataSplit.AGENT_TRAINING,
        scenario_id=None,
        episode_id=None,
        environment="freebsd-cdm18",
        observable_behavior="rare process persistence",
        pids=PIDSRef(pids_id="velox"),
        action="run slow path",
        content=content,
        normalized_content_hash=normalized_content_hash(content),
        evidence_artifact_ids=("artifact-visible",),
        created_at=NOW,
    )


def manifest(evidence_class: str = "synthetic_smoke") -> dict[str, object]:
    records = (
        memory("memory-relevant", "Rare process persistence justified investigation."),
        memory("memory-other", "Rare process persistence was transient noise."),
    )
    return {
        "schema_version": "memory-retrieval-sensitivity-v1",
        "manifest_id": "sensitivity-fixture",
        "evidence_class": evidence_class,
        "source_split": "validation",
        "snapshot": {
            "snapshot_id": "ltm-fixture",
            "records": [record.model_dump(mode="json") for record in records],
            "source_training_manifest_id": "agent-training-fixture",
            "sanitizer_version": "sanitizer-v1",
            "provenance_hash": SHA,
            "hidden_evaluator_signature": "fixture-review-signature",
            "human_sample_reviewed": True,
            "frozen_at": NOW.isoformat(),
        },
        "queries": [
            {
                "query_id": "query-1",
                "query": "rare process persistence",
                "environment": "freebsd-cdm18",
                "pids_id": "velox",
                "relevant_memory_ids": ["memory-relevant"],
            }
        ],
    }


class MemorySensitivityTests(unittest.TestCase):
    def test_synthetic_smoke_never_selects_or_claims_optimality(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / "private"
            public = root / "results"
            private.mkdir()
            public.mkdir()
            source = private / "fixture.json"
            output = public / "result.json"
            source.write_text(json.dumps(manifest()))
            environment = {
                "HIDDEN_EVALUATOR_PRIVATE_ROOT": str(private),
                "APT_MEMORY_SENSITIVITY_ROOT": str(public),
            }
            argv = [
                "sensitivity",
                "--manifest",
                str(source),
                "--output",
                str(output),
                "--code-commit",
                SHA[:40],
                "--policies",
                "64:1,256:2",
            ]
            with patch.dict(os.environ, environment), patch("sys.argv", argv):
                self.assertEqual(module.main(), 0)
            result = json.loads(output.read_text())
        self.assertEqual(result["selection_status"], "synthetic_smoke_no_selection")
        self.assertIsNone(result["selected_engineering_default"])
        self.assertFalse(result["optimality_claim"])
        self.assertEqual(len(result["results"]), 2)

    def test_non_validation_and_unknown_relevance_fail_closed(self) -> None:
        invalid_split = manifest()
        invalid_split["source_split"] = "held_out"
        with self.assertRaises(ValueError):
            module.SensitivityManifest.model_validate(invalid_split)
        invalid_reference = manifest()
        invalid_reference["queries"][0]["relevant_memory_ids"] = ["missing"]
        with self.assertRaises(ValueError):
            module.SensitivityManifest.model_validate(invalid_reference)

    def test_policy_parser_rejects_duplicates_and_shell_text(self) -> None:
        with self.assertRaises(ValueError):
            module.parse_policies("2048:20,2048:20")
        with self.assertRaises(ValueError):
            module.parse_policies("2048:20;touch")


if __name__ == "__main__":
    unittest.main()
