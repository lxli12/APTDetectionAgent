"""Agent-facing structured tools over PIDSMaker discovery and execution.

Requirements: REQ-TOOL-001..005, REQ-PIDS-001..004,
REQ-CONFIG-002, REQ-LABEL-004, REQ-RESOURCE-002..003.
"""

from __future__ import annotations

import json
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, model_validator

from apt_detection_agent.schemas import (
    ApprovedConfig,
    DataSplit,
    PIDSCapability,
    PIDSRef,
    ToolResult,
)
from apt_detection_agent.schemas.common import StrictModel

from .adapter import ExecutionOutcome, PIDSDetectionRequest, PIDSMakerAdapter
from .discovery import PIDSMakerDiscovery


class ApprovedConfigCatalog:
    """Frozen catalog that never consults evaluator metrics at selection time."""

    def __init__(self, entries: tuple[ApprovedConfig, ...]) -> None:
        by_id = {entry.config_id: entry for entry in entries}
        if len(by_id) != len(entries):
            raise ValueError("ApprovedConfig IDs must be unique")
        self._entries = by_id

    @classmethod
    def from_json(cls, path: Path) -> "ApprovedConfigCatalog":
        payload = json.loads(path.read_text())
        if not isinstance(payload, list) or not payload:
            raise ValueError("ApprovedConfig catalog must be a nonempty JSON list")
        return cls(tuple(ApprovedConfig.model_validate(item) for item in payload))

    def select(
        self,
        *,
        config_id: str,
        pids: PIDSRef,
        dataset_id: str,
        split: DataSplit,
    ) -> ApprovedConfig:
        try:
            entry = self._entries[config_id]
        except KeyError as exc:
            raise ValueError("config is not in the frozen ApprovedConfig catalog") from exc
        if entry.pids != pids or entry.dataset_id != dataset_id:
            raise ValueError("ApprovedConfig does not match PIDS and dataset")
        if split not in entry.approved_splits:
            raise ValueError("ApprovedConfig is not approved for this split")
        return entry


class VisibleTraceGraph(StrictModel):
    graph_id: str
    adjacency: dict[str, tuple[str, ...]]

    @model_validator(mode="after")
    def all_targets_are_declared(self) -> "VisibleTraceGraph":
        nodes = set(self.adjacency)
        unknown = {target for targets in self.adjacency.values() for target in targets} - nodes
        if unknown:
            raise ValueError(f"trace graph targets are undeclared: {sorted(unknown)}")
        return self


class TraceResult(StrictModel):
    graph_id: str
    direction: str
    start_entity_ids: tuple[str, ...]
    entity_ids: tuple[str, ...]
    edges: tuple[tuple[str, str], ...]
    max_depth: int


class ResultComparison(StrictModel):
    tool_call_ids: tuple[str, ...]
    successful_calls: int = Field(ge=0)
    failed_calls: int = Field(ge=0)
    artifact_counts: dict[str, int]


@dataclass(frozen=True)
class PIDSToolService:
    discovery: PIDSMakerDiscovery
    adapter: PIDSMakerAdapter
    catalog: ApprovedConfigCatalog
    max_cpu_parallel: int = 4

    def list_pids_capabilities(self) -> tuple[PIDSCapability, ...]:
        return self.discovery.capabilities()

    def inspect_pids_availability(self, pids: PIDSRef) -> tuple[PIDSCapability, ...]:
        matches = tuple(item for item in self.list_pids_capabilities() if item.pids == pids)
        if not matches:
            raise ValueError("PIDS identity is not registered")
        return matches

    def select_approved_config(
        self, config_id: str, pids: PIDSRef, dataset_id: str, split: DataSplit
    ) -> ApprovedConfig:
        return self.catalog.select(
            config_id=config_id,
            pids=pids,
            dataset_id=dataset_id,
            split=split,
        )

    def validate_pids_request(self, request: PIDSDetectionRequest) -> None:
        selected = self.select_approved_config(
            request.approved_config.config_id,
            request.pids,
            request.dataset_id,
            request.split,
        )
        if selected != request.approved_config:
            raise ValueError("request embeds a config that differs from the frozen catalog entry")
        self.adapter.validate_request(request)

    def run_pids_detection(self, request: PIDSDetectionRequest) -> ExecutionOutcome:
        self.validate_pids_request(request)
        return self.adapter.execute(request)

    def run_parallel_pids_detection(
        self, requests: tuple[PIDSDetectionRequest, ...]
    ) -> tuple[ExecutionOutcome, ...]:
        if not requests:
            return ()
        for request in requests:
            self.validate_pids_request(request)
        if any(not request.cpu_only for request in requests):
            return tuple(self.adapter.execute(request) for request in requests)
        workers = min(self.max_cpu_parallel, len(requests), 32)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return tuple(pool.map(self.adapter.execute, requests))

    @staticmethod
    def inspect_detection_result(outcome: ExecutionOutcome) -> ToolResult:
        return outcome.tool_result

    @staticmethod
    def compare_pids_results(results: tuple[ToolResult, ...]) -> ResultComparison:
        return ResultComparison(
            tool_call_ids=tuple(result.tool_call_id for result in results),
            successful_calls=sum(result.status.value == "succeeded" for result in results),
            failed_calls=sum(result.status.value == "failed" for result in results),
            artifact_counts={result.tool_call_id: len(result.artifact_ids) for result in results},
        )

    @staticmethod
    def forward_trace(
        graph: VisibleTraceGraph, start_entity_ids: tuple[str, ...], max_depth: int = 3
    ) -> TraceResult:
        return _trace(graph, start_entity_ids, max_depth, reverse=False)

    @staticmethod
    def backward_trace(
        graph: VisibleTraceGraph, start_entity_ids: tuple[str, ...], max_depth: int = 3
    ) -> TraceResult:
        return _trace(graph, start_entity_ids, max_depth, reverse=True)


def _trace(
    graph: VisibleTraceGraph,
    start_entity_ids: tuple[str, ...],
    max_depth: int,
    *,
    reverse: bool,
) -> TraceResult:
    if not 0 <= max_depth <= 20:
        raise ValueError("max_depth must be between 0 and 20")
    if not start_entity_ids or any(item not in graph.adjacency for item in start_entity_ids):
        raise ValueError("trace start entities must be declared graph nodes")
    adjacency = graph.adjacency
    if reverse:
        reversed_adjacency = {node: [] for node in adjacency}
        for source, targets in adjacency.items():
            for target in targets:
                reversed_adjacency[target].append(source)
        adjacency = {node: tuple(targets) for node, targets in reversed_adjacency.items()}
    visited = set(start_entity_ids)
    edges: list[tuple[str, str]] = []
    queue = deque((node, 0) for node in start_entity_ids)
    while queue:
        node, depth = queue.popleft()
        if depth >= max_depth:
            continue
        for target in adjacency[node]:
            edge = (target, node) if reverse else (node, target)
            edges.append(edge)
            if target not in visited:
                visited.add(target)
                queue.append((target, depth + 1))
    return TraceResult(
        graph_id=graph.graph_id,
        direction="backward" if reverse else "forward",
        start_entity_ids=start_entity_ids,
        entity_ids=tuple(sorted(visited)),
        edges=tuple(edges),
        max_depth=max_depth,
    )
