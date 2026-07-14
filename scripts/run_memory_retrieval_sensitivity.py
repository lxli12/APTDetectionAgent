#!/usr/bin/env python3
"""Evaluate SQLite FTS5 retrieval limits on evaluator-private validation queries.

Requirements: REQ-MEMORY-003..007, REQ-LABEL-001..004, REQ-REPRO-001..002.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import Field, model_validator

from apt_detection_agent.memory import (
    MemoryNamespace,
    MemoryQuery,
    MemoryStore,
    RetrievalPolicy,
)
from apt_detection_agent.schemas import DataSplit, StaticLTMSnapshot
from apt_detection_agent.schemas.common import Identifier, StrictModel


class ValidationQuery(StrictModel):
    query_id: Identifier
    query: str = Field(min_length=1, max_length=2048)
    environment: str | None = None
    pids_id: Identifier | None = None
    relevant_memory_ids: frozenset[Identifier] = Field(min_length=1)


class SensitivityManifest(StrictModel):
    schema_version: str = "memory-retrieval-sensitivity-v1"
    manifest_id: Identifier
    evidence_class: str
    source_split: DataSplit
    snapshot: StaticLTMSnapshot
    queries: tuple[ValidationQuery, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validation_only_and_references_known_records(self) -> "SensitivityManifest":
        if self.source_split != DataSplit.VALIDATION:
            raise ValueError("retrieval sensitivity selection is validation-only")
        if self.evidence_class not in {"synthetic_smoke", "agent_validation"}:
            raise ValueError("unknown retrieval sensitivity evidence class")
        known = {record.memory_id for record in self.snapshot.records}
        for query in self.queries:
            if not query.relevant_memory_ids <= known:
                raise ValueError("relevance judgment references unknown memory")
        return self


def approved_path(path: Path, environment_name: str) -> Path:
    root_text = os.environ.get(environment_name)
    if not root_text:
        raise ValueError(f"{environment_name} is required")
    root = Path(root_text).resolve()
    resolved = path.resolve()
    if resolved.parent != root:
        raise ValueError("sensitivity path escaped its executor-owned root")
    return resolved


def parse_policies(text: str) -> tuple[RetrievalPolicy, ...]:
    policies: list[RetrievalPolicy] = []
    for item in text.split(","):
        if not re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*", item):
            raise ValueError("policies must be comma-separated TOKEN_BUDGET:CANDIDATE_CAP")
        budget, cap = (int(value) for value in item.split(":"))
        policies.append(
            RetrievalPolicy(
                token_budget=budget,
                hard_candidate_cap=cap,
                validation_status="sensitivity_candidate",
            )
        )
    if len({(item.token_budget, item.hard_candidate_cap) for item in policies}) != len(
        policies
    ):
        raise ValueError("retrieval sensitivity policies must be unique")
    return tuple(policies)


def evaluate(
    manifest: SensitivityManifest, policies: tuple[RetrievalPolicy, ...]
) -> list[dict[str, object]]:
    namespace = MemoryNamespace(
        split=DataSplit.VALIDATION,
        scenario_id="retrieval-sensitivity",
        episode_id=manifest.manifest_id,
    )
    results: list[dict[str, object]] = []
    for policy in policies:
        with tempfile.TemporaryDirectory() as temporary:
            with MemoryStore(Path(temporary) / "memory.sqlite3", policy) as store:
                store.load_static_snapshot(manifest.snapshot)
                recalls: list[float] = []
                precisions: list[float] = []
                reciprocal_ranks: list[float] = []
                tokens: list[int] = []
                truncated = 0
                for query in manifest.queries:
                    retrieved = store.retrieve(
                        MemoryQuery(
                            query=query.query,
                            namespace=namespace,
                            environment=query.environment,
                            pids_id=query.pids_id,
                            top_k=policy.hard_candidate_cap,
                        )
                    )
                    identifiers = [record.memory_id for record in retrieved.records]
                    hits = query.relevant_memory_ids.intersection(identifiers)
                    recalls.append(len(hits) / len(query.relevant_memory_ids))
                    precisions.append(len(hits) / len(identifiers) if identifiers else 0.0)
                    ranks = [
                        index + 1
                        for index, memory_id in enumerate(identifiers)
                        if memory_id in query.relevant_memory_ids
                    ]
                    reciprocal_ranks.append(1.0 / min(ranks) if ranks else 0.0)
                    tokens.append(retrieved.estimated_tokens)
                    truncated += int(retrieved.truncated)
        count = len(manifest.queries)
        results.append(
            {
                "token_budget": policy.token_budget,
                "hard_candidate_cap": policy.hard_candidate_cap,
                "mean_recall": sum(recalls) / count,
                "mean_precision": sum(precisions) / count,
                "mean_reciprocal_rank": sum(reciprocal_ranks) / count,
                "mean_estimated_tokens": sum(tokens) / count,
                "truncated_query_fraction": truncated / count,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument(
        "--policies", default="256:5,512:10,1024:20,2048:20,4096:40"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.code_commit):
        raise ValueError("code commit must be an exact Git SHA")
    manifest_path = approved_path(args.manifest, "HIDDEN_EVALUATOR_PRIVATE_ROOT")
    output_path = approved_path(args.output, "APT_MEMORY_SENSITIVITY_ROOT")
    if output_path.exists():
        raise FileExistsError("sensitivity outputs are append-only")
    manifest_bytes = manifest_path.read_bytes()
    manifest = SensitivityManifest.model_validate_json(manifest_bytes)
    policies = parse_policies(args.policies)
    results = evaluate(manifest, policies)
    payload = {
        "schema_version": "memory-retrieval-sensitivity-result-v1",
        "manifest_id": manifest.manifest_id,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "evidence_class": manifest.evidence_class,
        "source_split": manifest.source_split.value,
        "query_count": len(manifest.queries),
        "code_commit": args.code_commit,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "selected_engineering_default": None,
        "selection_status": (
            "synthetic_smoke_no_selection"
            if manifest.evidence_class == "synthetic_smoke"
            else "requires_prespecified_selection_rule_and_review"
        ),
        "optimality_claim": False,
    }
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
