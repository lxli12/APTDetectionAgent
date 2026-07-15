import ast
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from apt_detection_agent.schemas import (
    Action, ActionType, AgentSplit, Alert, BudgetState, CacheEntry, CacheReuseLevel,
    CacheState, CommitMode, CommitPolicy, CommittedDetection, ConstructionGraph,
    DeployableDataLeakageError, DetectionCommitStatus, Diagnosis, DiagnosisCategory,
    DiagnosisCode, EntityScore, EnvironmentProfile, ExecutionTrace, ExpectedCacheReuse,
    FallbackPolicy, MemoryContext, MemoryQuery, MemoryReadRequest, MemoryUseDecision,
    MemoryUseDisposition, MemoryUseItem, MemoryWriteRequest, Observation, OperationStatus,
    EnvironmentSignature, Experience, MemoryLayer, MemoryRecord, NamedCount,
    NumericFeature, ObservableBehaviorProfile, PathDecision, PIDSCapabilityProfile,
    PIDSResult, PipelineStage, PipelineState, ResourceProfile,
    ScoreQuantiles, StageInvalidation, StageState, ToolResult, ToolStatus,
    UnlabeledDetectionSignals, UsageAccounting, VisibleEvidence, assert_deployable,
    sanitize_deployable,
)


NOW = datetime(2026, 7, 15, 2, 0, tzinfo=timezone.utc)


def observation() -> Observation:
    environment = EnvironmentProfile(
        scenario_id="cadets-e3", dataset="darpa_tc_cadets", agent_split=AgentSplit.HELD_OUT,
        os_family="FreeBSD", platform="amd64", provenance_schema="CDM18",
        node_types=("process", "file"), edge_types=("read", "write"),
        normal_node_count_mean=100.0, normal_edge_count_mean=210.0,
        normal_event_rate_mean=14.0,
        resource_profile=ResourceProfile(32, 257_698_037_760, 2, 25_752_027_136),
    )
    graph = ConstructionGraph(
        "g-1", "w-1", 1, NOW, NOW + timedelta(minutes=15), 3, 2,
        node_type_counts=(NamedCount("process", 1), NamedCount("file", 2)),
        edge_type_counts=(NamedCount("read", 1), NamedCount("write", 1)),
        density=1 / 3, event_rate=2 / 900,
    )
    pipeline = PipelineState(
        "ORTHRUS", "orthrus-cadets-v1", "threshold-q99", "checkpoint-a",
        tuple(StageState(stage, OperationStatus.SUCCEEDED, f"hash-{stage.value}", f"artifact-{stage.value}") for stage in PipelineStage),
        OperationStatus.SUCCEEDED, OperationStatus.SUCCEEDED,
    )
    signals = UnlabeledDetectionSignals(
        ScoreQuantiles(0.01, 0.1, 0.4, 0.6, 0.9, 1.1), 0.02, 1, 1 / 3,
        0.1, 0.15, 0.05, False, 0.08,
    )
    entries = tuple(CacheEntry(stage, f"hash-{stage.value}", True) for stage in PipelineStage)
    return Observation(
        "obs-1", NOW + timedelta(minutes=15), environment, graph, pipeline, signals,
        CacheState(entries, tuple(PipelineStage)), BudgetState(4, 8000, 2000, 3600, 1, 0),
        (MemoryContext("memory-1", "Stable score tail under the same schema", 0.8, ("CDM18",), ("resource pressure",)),),
    )


def action() -> Action:
    return Action(
        action_id="action-1", path_decision=PathDecision.FAST_PATH,
        action_type=ActionType.KEEP_AND_INFER,
        diagnosis=Diagnosis(DiagnosisCategory.VIABLE, DiagnosisCode.VIABLE_CONFIGURATION, "Visible score and alert trends are stable."),
        visible_evidence=(VisibleEvidence("e-1", "current_graph", ("signals.score_shift", "signals.alert_count"), "Both visible shifts remain bounded."),),
        tool_name="run_current_pids", arguments={"window_id": "w-1", "candidate_id": "orthrus-cadets-v1"},
        expected_cache_reuse=ExpectedCacheReuse(CacheReuseLevel.FULL, tuple(PipelineStage), (), "No configuration field changes."),
        confidence=0.85,
        commit_policy=CommitPolicy(CommitMode.NO_CONFIG_CHANGE, "orthrus-cadets-v1", True, False),
        fallback=FallbackPolicy(ActionType.FALLBACK_OR_STOP, "orthrus-cadets-v1", "Retain the last known stable configuration."),
    )


def commitment() -> CommittedDetection:
    return CommittedDetection(
        "commit-1", "cadets-e3", "w-1", 1, "ORTHRUS", "orthrus-cadets-v1", "run-1",
        (Alert("entity-7", 1.1, "threshold-q99", "score_above_candidate"),),
        DetectionCommitStatus.COMMITTED, NOW + timedelta(minutes=16),
    )


def memory_record(memory_id="memory-1", namespace="case-a", created_at=NOW) -> MemoryRecord:
    return MemoryRecord(
        memory_id, namespace, MemoryLayer.EPISODE,
        EnvironmentSignature(
            "FreeBSD", "amd64", "CDM18", ("ORTHRUS", "VELOX"), ("dual_gpu",),
            (NumericFeature("graph_density", 0.3),),
        ),
        ObservableBehaviorProfile(("persistent_tail",), 0.7, 0.2, 0.4, 0.1, 0.15),
        PIDSCapabilityProfile("ORTHRUS", ("temporal",), "medium", "large", ("node_type",), "medium"),
        Experience(
            "Persistent score tail", "viable_configuration", "KEEP_AND_INFER", "evaluation",
            "Alert volume remained stable", ("CDM18",), ("resource pressure",),
        ),
        ("evidence-1",), 0.8, 2, created_at, f"provenance-{memory_id}",
    )


def test_observation_and_action_round_trip_are_deterministic():
    for contract, loader in ((observation(), Observation.from_dict), (action(), Action.from_dict)):
        encoded = contract.to_json()
        restored = loader(json.loads(encoded))
        assert restored == contract
        assert restored.to_json() == encoded
        assert json.loads(encoded)["schema_version"] == "1.0"


def test_expanded_trace_round_trip_and_fast_path_invariants():
    trace = ExecutionTrace(
        "trace-1", "cadets-e3", "w-1", observation(), PathDecision.FAST_PATH, (),
        None, None, action(),
        ToolResult("action-1", "run_current_pids", ToolStatus.SUCCEEDED, {"run_id": "run-1"}),
        None, commitment(), UsageAccounting(0, 0, 0, 1, 1.25), NOW + timedelta(minutes=16),
    )
    assert ExecutionTrace.from_dict(json.loads(trace.to_json())) == trace
    with pytest.raises(ValueError, match="main LLM"):
        ExecutionTrace(
            "trace-2", "cadets-e3", "w-1", observation(), PathDecision.FAST_PATH, (),
            None, None, action(), None, None, commitment(), UsageAccounting(10, 2, 1, 1, 1), NOW,
        )


def test_unknown_values_and_invalid_cross_field_combinations_are_rejected():
    payload = action().to_dict()
    payload["action_type"] = "ARBITRARY_COMMAND"
    with pytest.raises(ValueError):
        Action.from_dict(payload)

    with pytest.raises(ValueError, match="fast path"):
        Action(
            "a", PathDecision.FAST_PATH, ActionType.SWITCH_PIDS,
            Diagnosis(DiagnosisCategory.DETECTION_FAILURE, DiagnosisCode.MODEL_MISMATCH, "Visible score separation degraded."),
            (VisibleEvidence("e", "trend", ("signals.score_shift",), "Score shift increased."),),
            "switch_pids", {"candidate_id": "velox-1"},
            StageInvalidation(PipelineStage.FEATURIZATION, tuple(PipelineStage)[2:], "Detector features differ."),
            ExpectedCacheReuse(CacheReuseLevel.PARTIAL, tuple(PipelineStage)[:2], tuple(PipelineStage)[2:], "Construction artifacts remain reusable."),
            0.5, CommitPolicy(CommitMode.VALIDATE_THEN_COMMIT, "stable", True, True),
            FallbackPolicy(ActionType.FALLBACK_OR_STOP, "stable", "Rollback on failure."),
        )


@pytest.mark.parametrize("hidden_key", [
    "attack_identity", "malicious_nodes", "attack_time", "ground_truth",
    "tp", "false_positives", "coverage", "ADP", "MCC",
])
def test_adversarial_hidden_fields_are_rejected_and_removed(hidden_key):
    payload = {"visible": {"score_shift": 0.1}, "nested": [{hidden_key: "secret"}]}
    with pytest.raises(DeployableDataLeakageError):
        assert_deployable(payload)
    sanitized = sanitize_deployable(payload)
    assert hidden_key not in json.dumps(sanitized)
    assert sanitized["visible"]["score_shift"] == 0.1


def test_tainted_free_text_cannot_bypass_memory_or_action_boundary():
    with pytest.raises(DeployableDataLeakageError):
        MemoryContext("m", "ground truth says entity 7", 0.8, (), ())
    with pytest.raises(DeployableDataLeakageError):
        VisibleEvidence("e", "notes", ("signals.score_shift",), "TP=9 justifies this action")


def test_online_pids_result_has_no_label_or_metric_escape_hatch():
    result = PIDSResult(
        "ORTHRUS", "run-1", "w-1", "cfg-1", OperationStatus.SUCCEEDED,
        (EntityScore("entity-7", 1.1),),
        (Alert("entity-7", 1.1, "q99", "score_above_candidate"),), (), NOW, NOW, 0.0,
    )
    payload = result.to_dict()
    payload["ground_truth"] = ["entity-7"]
    with pytest.raises(ValueError, match="unknown fields"):
        PIDSResult.from_dict(payload)


def test_schema_package_uses_only_standard_library_and_internal_imports():
    schema_root = Path(__file__).resolve().parents[1] / "src" / "apt_detection_agent" / "schemas"
    forbidden = set()
    allowed_roots = {
        "__future__", "dataclasses", "datetime", "enum", "json", "math", "re", "typing",
    }
    for path in schema_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                forbidden.update(alias.name.split(".")[0] for alias in node.names if alias.name.split(".")[0] not in allowed_roots)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                root = node.module.split(".")[0]
                if root not in allowed_roots:
                    forbidden.add(root)
    assert not forbidden


def test_memory_read_request_rejects_inconsistent_decision():
    with pytest.raises(ValueError, match="must agree"):
        MemoryReadRequest("read-1", True, "find compatible experience", None)


def test_memory_read_use_write_contracts_round_trip():
    query = MemoryQuery("case-a", "FreeBSD", "CDM18", "ORTHRUS", ("persistent_tail",), (), 5)
    read = MemoryReadRequest("read-1", True, "find environment-compatible experience", query)
    use = MemoryUseDecision("read-1", (MemoryUseItem("memory-1", MemoryUseDisposition.USE, "Environment and visible behavior are compatible."),))
    write = MemoryWriteRequest("write-1", True, MemoryLayer.EPISODE, "Preserve a reusable visible outcome.", memory_record())

    for contract, loader in (
        (read, MemoryReadRequest.from_dict),
        (use, MemoryUseDecision.from_dict),
        (write, MemoryWriteRequest.from_dict),
    ):
        restored = loader(json.loads(json.dumps(contract.to_dict(), sort_keys=True)))
        assert restored == contract
