"""Phase 1 schema and negative-boundary tests.

Requirements: REQ-LABEL-001..004, REQ-TOOL-001..005,
REQ-CONFIG-001..003, REQ-WINDOW-001..003, REQ-MEMORY-001..006,
REQ-EVAL-001..004, REQ-ARTIFACT-001..003, REQ-CAUSAL-001..004.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone

from pydantic import ValidationError

from apt_detection_agent.schemas import (
    ActionType,
    AgentAction,
    ApprovedConfig,
    ArtifactManifest,
    ArtifactRecord,
    AvailabilityStatus,
    CalibrationMethod,
    CaseState,
    CheckpointDescriptor,
    CommandManifest,
    DataSplit,
    DetectionUnit,
    ExperimentClass,
    MemoryLayer,
    MemoryRecord,
    Observation,
    PIDSCapability,
    PIDSRef,
    PendingConfiguration,
    PipelineStage,
    RunManifest,
    RunStatus,
    ScoreSummary,
    StaticLTMSnapshot,
    ThresholdProvenance,
    ThresholdSourceSplit,
    TimeWindow,
    ToolName,
    ToolRequest,
    ToolResult,
    TransductiveStatus,
    assert_deployable_payload,
)
from apt_detection_agent.evaluation.private import CampaignManifest
from apt_detection_agent.evaluation.public import EpisodeMetricsFeedback, TrainingStepFeedback
import apt_detection_agent.schemas as public_schemas


NOW = datetime(2026, 1, 1, 1, tzinfo=timezone.utc)
ORIGIN = datetime(2026, 1, 1, 0, tzinfo=timezone.utc)
SHA = "a" * 64
GIT_SHA = "b" * 40


def valid_window(**updates: object) -> TimeWindow:
    values: dict[str, object] = {
        "window_id": "window-4",
        "sequence_number": 4,
        "origin_time": ORIGIN,
        "timezone": "UTC",
        "window_size_seconds": 900,
        "start": ORIGIN + timedelta(hours=1),
        "end": ORIGIN + timedelta(hours=1, minutes=15),
    }
    values.update(updates)
    return TimeWindow.model_validate(values)


def valid_memory(**updates: object) -> MemoryRecord:
    values: dict[str, object] = {
        "memory_id": "memory-1",
        "layer": MemoryLayer.EPISODE,
        "split": DataSplit.HELD_OUT,
        "scenario_id": "scenario-1",
        "episode_id": "episode-1",
        "environment": "freebsd-cdm18",
        "observable_behavior": "rare-process-edge",
        "pids": {"pids_id": "orthrus", "variant_id": "fixed"},
        "action": "run_slow_path",
        "content": "Observable score shift justified an additional detector.",
        "normalized_content_hash": SHA,
        "evidence_artifact_ids": ("artifact-1",),
        "created_at": NOW,
    }
    values.update(updates)
    return MemoryRecord.model_validate(values)


class WindowAndObservationTests(unittest.TestCase):
    def test_window_is_aligned_and_half_open(self) -> None:
        window = valid_window()
        self.assertEqual(window.end - window.start, timedelta(minutes=15))
        self.assertEqual(window.sequence_number, 4)

    def test_window_rejects_wrong_sequence(self) -> None:
        with self.assertRaises(ValidationError):
            valid_window(sequence_number=3)

    def test_window_rejects_unaligned_start(self) -> None:
        with self.assertRaises(ValidationError):
            valid_window(start=ORIGIN + timedelta(minutes=61), end=ORIGIN + timedelta(minutes=76))

    def test_window_rejects_naive_time(self) -> None:
        with self.assertRaises(ValidationError):
            valid_window(start=datetime(2026, 1, 1, 1), end=datetime(2026, 1, 1, 1, 15))

    def test_observation_round_trip_and_no_privileged_schema(self) -> None:
        observation = Observation(
            observation_id="obs-1",
            scenario_id="scenario-1",
            episode_id="episode-1",
            split=DataSplit.HELD_OUT,
            observed_at=NOW + timedelta(minutes=15),
            window=valid_window(),
            environment_profile_id="autodl-initial",
            committed_config_id="config-1",
            active_pids=(PIDSRef(pids_id="velox"),),
            score_summary=ScoreSummary(count=0),
        )
        restored = Observation.model_validate_json(observation.model_dump_json())
        self.assertEqual(restored, observation)
        schema = json.dumps(Observation.model_json_schema()).lower()
        self.assertNotIn("ground_truth", schema)
        self.assertNotIn("malicious_entity", schema)

    def test_observation_rejects_hidden_label(self) -> None:
        payload = {
            "observation_id": "obs-1",
            "scenario_id": "scenario-1",
            "episode_id": "episode-1",
            "split": "held_out",
            "observed_at": NOW + timedelta(minutes=15),
            "window": valid_window().model_dump(),
            "environment_profile_id": "autodl-initial",
            "committed_config_id": "config-1",
            "active_pids": [{"pids_id": "velox"}],
            "score_summary": {"count": 0},
            "ground_truth": {"malicious_entity_ids": ["node-1"]},
        }
        with self.assertRaises(ValidationError):
            Observation.model_validate(payload)

    def test_observation_cannot_precede_window_close(self) -> None:
        with self.assertRaises(ValidationError):
            Observation(
                observation_id="obs-1",
                scenario_id="scenario-1",
                episode_id="episode-1",
                split=DataSplit.DEPLOYMENT,
                observed_at=valid_window().start,
                window=valid_window(),
                environment_profile_id="env-1",
                committed_config_id="config-1",
                active_pids=(PIDSRef(pids_id="velox"),),
                score_summary=ScoreSummary(count=0),
            )

    def test_case_reconfiguration_is_next_window(self) -> None:
        case = CaseState(
            case_id="case-1",
            scenario_id="scenario-1",
            episode_id="episode-1",
            split=DataSplit.HELD_OUT,
            current_window_sequence=4,
            committed_config_id="config-old",
            pending_configuration=PendingConfiguration(
                config_id="config-new",
                effective_sequence_number=5,
                requested_by_tool_call_id="call-1",
            ),
            memory_namespace="heldout-scenario-1-episode-1",
            updated_at=NOW,
        )
        self.assertEqual(case.committed_config_id, "config-old")

    def test_case_rejects_same_window_reconfiguration(self) -> None:
        with self.assertRaises(ValidationError):
            CaseState(
                case_id="case-1",
                scenario_id="scenario-1",
                episode_id="episode-1",
                split=DataSplit.HELD_OUT,
                current_window_sequence=4,
                committed_config_id="config-old",
                pending_configuration={
                    "config_id": "config-new",
                    "effective_sequence_number": 4,
                    "requested_by_tool_call_id": "call-1",
                },
                memory_namespace="namespace-1",
                updated_at=NOW,
            )


class PIDSAndConfigurationTests(unittest.TestCase):
    def test_orthrus_variant_identity(self) -> None:
        ref = PIDSRef(pids_id="ORTHRUS", variant_id="fixed")
        self.assertEqual((ref.pids_id, ref.variant_id), ("orthrus", "fixed"))

    def test_orthrus_variant_cannot_be_method(self) -> None:
        with self.assertRaises(ValidationError):
            PIDSRef(pids_id="orthrus_fixed")

    def test_unavailable_checkpoint_requires_reason(self) -> None:
        with self.assertRaises(ValidationError):
            CheckpointDescriptor(format="torch", availability=AvailabilityStatus.UNAVAILABLE)

    def test_available_checkpoint_requires_hash_and_path(self) -> None:
        with self.assertRaises(ValidationError):
            CheckpointDescriptor(format="torch", availability=AvailabilityStatus.AVAILABLE)

    def test_checkpoint_rejects_path_escape(self) -> None:
        with self.assertRaises(ValidationError):
            CheckpointDescriptor(
                format="torch",
                availability=AvailabilityStatus.AVAILABLE,
                checkpoint_hash=SHA,
                relative_path="../private/model.pt",
            )

    def test_unavailable_pids_stays_in_registry_with_reason(self) -> None:
        capability = PIDSCapability(
            pids=PIDSRef(pids_id="orthrus", variant_id="fixed"),
            implementation_path="PIDSMaker/pidsmaker",
            source_config_id="orthrus_fixed",
            source_path="PIDSMaker/config/orthrus_fixed.yml",
            source_semantics="upstream variant",
            supported_datasets=("cadets_e3",),
            required_pipeline_stages=(PipelineStage.CONSTRUCTION, PipelineStage.INFERENCE),
            detection_unit=DetectionUnit.NODE_TIME_WINDOW,
            training_support=True,
            inference_support=True,
            checkpoint=CheckpointDescriptor(
                format="torch",
                availability=AvailabilityStatus.UNAVAILABLE,
                unavailable_reason="checkpoint not discovered",
            ),
            threshold_semantics="validation score threshold",
            cpu_supported=False,
            gpu_required=True,
            expected_outputs=("scores",),
            transductive_status=TransductiveStatus.UNKNOWN,
            compatibility_status="unverified",
            current_availability_status=AvailabilityStatus.UNAVAILABLE,
            unavailable_reason="checkpoint not discovered",
            pidsmaker_commit="32602734bc9f896be5fc0f03f0a185c967cd6624",
        )
        self.assertEqual(capability.current_availability_status, AvailabilityStatus.UNAVAILABLE)

    def test_causal_main_rejects_transductive_config(self) -> None:
        with self.assertRaises(ValidationError):
            ApprovedConfig(
                config_id="config-1",
                pids=PIDSRef(pids_id="velox"),
                source_config_id="velox",
                dataset_id="cadets_e3",
                parameters={},
                required_pipeline_stages=(PipelineStage.INFERENCE,),
                experiment_class=ExperimentClass.CAUSAL_MAIN,
                transductive_status=TransductiveStatus.TRANSDUCTIVE,
                frozen_at=NOW,
                code_commit=GIT_SHA,
                approved_splits=frozenset({DataSplit.HELD_OUT}),
            )

    def test_transductive_config_is_explicit_compatibility_baseline(self) -> None:
        config = ApprovedConfig(
            config_id="config-compat",
            pids=PIDSRef(pids_id="velox"),
            source_config_id="velox",
            dataset_id="cadets_e3",
            parameters={},
            required_pipeline_stages=(PipelineStage.INFERENCE,),
            experiment_class=ExperimentClass.COMPATIBILITY_BASELINE,
            transductive_status=TransductiveStatus.TRANSDUCTIVE,
            frozen_at=NOW,
            code_commit=GIT_SHA,
            approved_splits=frozenset({DataSplit.VALIDATION}),
        )
        self.assertEqual(config.experiment_class, ExperimentClass.COMPATIBILITY_BASELINE)

    def test_validation_threshold_requires_validation_source(self) -> None:
        with self.assertRaises(ValidationError):
            ThresholdProvenance(
                threshold_id="threshold-1",
                value=0.5,
                calibration_method=CalibrationMethod.VALIDATION_QUANTILE,
                source_dataset="cadets_e3",
                source_split=ThresholdSourceSplit.TRAINING,
                checkpoint_hash=SHA,
                target_metric="benign-score-quantile",
                created_at=NOW,
                code_commit=GIT_SHA,
            )

    def test_threshold_has_complete_provenance(self) -> None:
        threshold = ThresholdProvenance(
            threshold_id="threshold-1",
            value=0.5,
            calibration_method=CalibrationMethod.VALIDATION_COVERAGE,
            source_dataset="cadets_e3",
            source_split=ThresholdSourceSplit.VALIDATION,
            checkpoint_hash=SHA,
            target_metric="campaign-coverage",
            created_at=NOW,
            code_commit=GIT_SHA,
        )
        self.assertEqual(threshold.source_split, ThresholdSourceSplit.VALIDATION)


class ToolBoundaryTests(unittest.TestCase):
    def valid_request(self, **updates: object) -> ToolRequest:
        values: dict[str, object] = {
            "tool_call_id": "call-1",
            "tool_name": ToolName.RUN_PIDS_DETECTION,
            "case_id": "case-1",
            "scenario_id": "scenario-1",
            "episode_id": "episode-1",
            "window_id": "window-4",
            "approved_config_id": "config-1",
            "arguments": {"pids_id": "velox", "variant_id": "default"},
            "requested_at": NOW,
        }
        values.update(updates)
        return ToolRequest.model_validate(values)

    def test_typed_tool_request(self) -> None:
        request = self.valid_request()
        self.assertEqual(request.tool_name, ToolName.RUN_PIDS_DETECTION)

    def test_request_rejects_shell_command(self) -> None:
        with self.assertRaises(ValidationError):
            self.valid_request(arguments={"command": "python pidsmaker/main.py"})

    def test_request_rejects_nested_cuda_device(self) -> None:
        with self.assertRaises(ValidationError):
            self.valid_request(arguments={"resource": {"cuda_visible_devices": "0,1"}})

    def test_request_rejects_hidden_label_argument(self) -> None:
        with self.assertRaises(ValidationError):
            self.valid_request(arguments={"filter": {"labels": ["malicious"]}})

    def test_request_rejects_unknown_top_level_field(self) -> None:
        payload = self.valid_request().model_dump()
        payload["shell"] = "bash"
        with self.assertRaises(ValidationError):
            ToolRequest.model_validate(payload)

    def test_action_requires_typed_tool_request(self) -> None:
        with self.assertRaises(ValidationError):
            AgentAction(
                action_id="action-1",
                action_type=ActionType.RUN_TOOL,
                case_id="case-1",
                window_id="window-4",
                rationale="Observable score distribution shifted.",
                based_on_observation_id="obs-1",
                deployment_evidence_ids=("artifact-1",),
            )

    def test_reconfiguration_action_requires_effective_window(self) -> None:
        with self.assertRaises(ValidationError):
            AgentAction(
                action_id="action-1",
                action_type=ActionType.SCHEDULE_RECONFIGURATION,
                case_id="case-1",
                window_id="window-4",
                rationale="Schedule a frozen configuration for the next window.",
                based_on_observation_id="obs-1",
                deployment_evidence_ids=("artifact-1",),
                pending_config_id="config-2",
            )

    def test_command_manifest_rejects_secret_environment_name(self) -> None:
        with self.assertRaises(ValidationError):
            CommandManifest(
                manifest_id="command-1",
                executable_id="pidsmaker-cli",
                argv=("python", "main.py"),
                working_directory="/root/APTDetectionAgent/PIDSMaker",
                injected_environment_keys=("DB_PASSWORD",),
            )

    def test_failed_result_requires_sanitized_error(self) -> None:
        with self.assertRaises(ValidationError):
            ToolResult(
                tool_call_id="call-1",
                tool_name=ToolName.RUN_PIDS_DETECTION,
                status=RunStatus.FAILED,
                validated_arguments={},
                started_at=NOW,
                ended_at=NOW,
                exit_code=2,
            )

    def test_standardized_result_rejects_hidden_metrics(self) -> None:
        with self.assertRaises(ValidationError):
            ToolResult(
                tool_call_id="call-1",
                tool_name=ToolName.INSPECT_DETECTION_RESULT,
                status=RunStatus.SUCCEEDED,
                validated_arguments={},
                started_at=NOW,
                ended_at=NOW,
                exit_code=0,
                standardized_observation={"hidden_metrics": {"mcc": 1.0}},
            )


class MemoryAndEvaluatorBoundaryTests(unittest.TestCase):
    def test_privileged_models_are_not_public_agent_exports(self) -> None:
        self.assertFalse(hasattr(public_schemas, "CampaignManifest"))
        self.assertFalse(hasattr(public_schemas, "HiddenGroundTruth"))
        self.assertFalse(hasattr(public_schemas, "EvaluationRecord"))
        self.assertFalse(hasattr(public_schemas, "EpisodeMetricsFeedback"))
        self.assertFalse(hasattr(public_schemas, "TrainingStepFeedback"))

    def test_episode_memory_requires_episode_scope(self) -> None:
        with self.assertRaises(ValidationError):
            valid_memory(episode_id=None)

    def test_static_ltm_rejects_runtime_identity(self) -> None:
        with self.assertRaises(ValidationError):
            valid_memory(layer=MemoryLayer.STATIC_LTM)

    def test_static_ltm_must_come_from_agent_training(self) -> None:
        with self.assertRaises(ValidationError):
            valid_memory(
                layer=MemoryLayer.STATIC_LTM,
                split=DataSplit.VALIDATION,
                scenario_id=None,
                episode_id=None,
            )

    def test_released_ltm_requires_signature_and_human_sampling(self) -> None:
        static_record = valid_memory(
            layer=MemoryLayer.STATIC_LTM,
            split=DataSplit.AGENT_TRAINING,
            scenario_id=None,
            episode_id=None,
        )
        with self.assertRaises(ValidationError):
            StaticLTMSnapshot(
                snapshot_id="ltm-1",
                records=(static_record,),
                source_training_manifest_id="training-1",
                sanitizer_version="sanitizer-1",
                provenance_hash=SHA,
                hidden_evaluator_signature="",
                human_sample_reviewed=False,
                frozen_at=NOW,
            )

    def test_deployable_payload_rejects_nested_teacher_rationale(self) -> None:
        with self.assertRaises(ValueError):
            assert_deployable_payload({"memory": [{"teacher_rationale": "secret"}]})

    def test_deployable_payload_accepts_observable_evidence(self) -> None:
        assert_deployable_payload({"trace": {"observable_edges": ["edge-1"]}})

    def test_step_reward_is_training_only(self) -> None:
        with self.assertRaises(ValidationError):
            TrainingStepFeedback(
                split=DataSplit.HELD_OUT,
                step_id="step-1",
                sanitized_reward=0.1,
                signal_id="bounded-reward-v1",
            )

    def test_heldout_feedback_is_episode_level(self) -> None:
        feedback = EpisodeMetricsFeedback(
            split=DataSplit.HELD_OUT,
            episode_id="episode-1",
            metrics_artifact_id="metrics-1",
            emitted_at=NOW,
        )
        self.assertFalse(hasattr(feedback, "step_reward"))

    def test_campaign_manifest_requires_exclusion_reasons(self) -> None:
        with self.assertRaises(ValidationError):
            CampaignManifest(
                manifest_version="campaign-v1",
                campaign_id="campaign-1",
                dataset_id="cadets_e3",
                attack_date_range=(ORIGIN, NOW),
                included_window_ids=("window-1",),
                malicious_entity_ids=("node-1",),
                ground_truth_sources=("source-1",),
                exclusions=("node-2",),
                exclusion_reasons=(),
            )


class ArtifactAndRunTests(unittest.TestCase):
    def test_artifact_path_rejects_escape(self) -> None:
        with self.assertRaises(ValidationError):
            ArtifactRecord(
                artifact_id="artifact-1",
                artifact_type="metrics",
                relative_path="../metrics.json",
                content_hash=SHA,
                size_bytes=10,
                producing_stage="evaluation",
                created_at=NOW,
            )

    def test_manifest_rejects_duplicate_artifact_ids(self) -> None:
        artifact = ArtifactRecord(
            artifact_id="artifact-1",
            artifact_type="metrics",
            relative_path="metrics.json",
            content_hash=SHA,
            size_bytes=10,
            producing_stage="evaluation",
            created_at=NOW,
        )
        with self.assertRaises(ValidationError):
            ArtifactManifest(
                manifest_id="manifest-1",
                run_id="run-1",
                code_commit=GIT_SHA,
                pidsmaker_commit="32602734bc9f896be5fc0f03f0a185c967cd6624",
                artifacts=(artifact, artifact),
                created_at=NOW,
            )

    def test_pids_artifact_requires_config_and_checkpoint(self) -> None:
        with self.assertRaises(ValidationError):
            ArtifactRecord(
                artifact_id="artifact-1",
                artifact_type="detection-scores",
                relative_path="scores.json",
                content_hash=SHA,
                size_bytes=10,
                producing_stage="detection",
                pids_related=True,
                created_at=NOW,
            )

    def test_failed_run_requires_failure_provenance(self) -> None:
        with self.assertRaises(ValidationError):
            RunManifest(
                run_id="run-1",
                status=RunStatus.FAILED,
                code_commit=GIT_SHA,
                pidsmaker_commit="32602734bc9f896be5fc0f03f0a185c967cd6624",
                environment_manifest_id="env-1",
                resource_profile_id="resource-1",
                data_manifest_id="data-1",
                exact_command_artifact_id="command-1",
                resolved_config_artifact_id="config-1",
                random_seeds=(1,),
                started_at=NOW,
                ended_at=NOW,
            )

    def test_successful_run_requires_artifact_manifest(self) -> None:
        with self.assertRaises(ValidationError):
            RunManifest(
                run_id="run-1",
                status=RunStatus.SUCCEEDED,
                code_commit=GIT_SHA,
                pidsmaker_commit="32602734bc9f896be5fc0f03f0a185c967cd6624",
                environment_manifest_id="env-1",
                resource_profile_id="resource-1",
                data_manifest_id="data-1",
                exact_command_artifact_id="command-1",
                resolved_config_artifact_id="config-1",
                random_seeds=(1,),
                started_at=NOW,
                ended_at=NOW,
            )


if __name__ == "__main__":
    unittest.main()
