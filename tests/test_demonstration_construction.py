"""Pre-SFT demonstration construction, isolation, and export tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from pydantic import ValidationError

from apt_detection_agent.evaluator import StrictTeacherSelectionParser
from apt_detection_agent.schemas import (
    AvailabilityStatus,
    DataSplit,
    DetectionUnit,
    PIDSRef,
)
from apt_detection_agent.sft import (
    CoverageClass,
    DemonstrationCorpusValidator,
    DemonstrationExchange,
    DemonstrationExporter,
    DemonstrationSanitizer,
    ExecutionDisposition,
    build_coverage_report,
    build_dataset_manifest,
    build_offline_run_record,
    build_trajectory,
)
from apt_detection_agent.sft.demonstration import (
    DemonstrationTrainingUse,
    GraphConstructionManifest,
    HistoricalEvidenceContext,
    LabelAvailability,
    ObservableBehavior,
    OpaqueConfigurationSummary,
    PIDSDataPartitions,
    TemporalContext,
    VisibleCostSummary,
    VisibleEvidenceGrounding,
    VisibleFailureCondition,
)
from apt_detection_agent.tooling.runtime_tools import DetectorCapabilityView
from tests.test_agent_runtime_contract import NOW
from tests.test_frozen_sft import frozen_teacher


SHA = "a" * 64
GIT_SHA = "b" * 40
ROOT = Path(__file__).resolve().parents[1]


def capability(pids_id: str = "velox") -> DetectorCapabilityView:
    return DetectorCapabilityView(
        pids=PIDSRef(pids_id=pids_id),
        purpose="Inspect deployment-visible provenance behavior.",
        capability_type="event-surprise",
        detection_unit=DetectionUnit.NODE_TIME_WINDOW,
        cost_class="medium",
        required_state_status="frozen-reference",
        limitation_codes=("not-real-admitted",),
        available_status=AvailabilityStatus.BLOCKED,
        availability_reason_codes=("missing-real-smoke",),
        approved_candidate_ids=(),
    )


def offline_record(pids_id: str = "velox"):
    detector = PIDSRef(pids_id=pids_id)
    behavior = ObservableBehavior(
        behavior_id="behavior-1",
        summary="A deployment-visible score shift was observed.",
        evidence_ids=("observation-1",),
    )
    temporal = TemporalContext(
        window_id="window-1",
        sequence_number=1,
        start=NOW,
        end=NOW + timedelta(minutes=15),
        past_range_window_ids=("window-0",),
        state_continuity_code="continuous",
    )
    return build_offline_run_record(
        run_record_id=f"offline-{pids_id}",
        dataset_manifest_id="manifest-1",
        episode_id="episode-1",
        split=DataSplit.AGENT_TRAINING,
        environment_profile_id="autodl-baseline",
        observable_behavior=behavior,
        historical_evidence_context=HistoricalEvidenceContext(
            past_window_ids=("window-0",),
            prior_result_ids=(),
            prior_action_ids=(),
            prior_failure_codes=(),
            prior_state_change_ids=(),
            memory_record_ids=(),
        ),
        temporal_context=temporal,
        pids_capability=capability(pids_id),
        detector=detector,
        configuration=OpaqueConfigurationSummary(
            approved_config_id="config-unavailable",
            checkpoint_id="checkpoint-unavailable",
            threshold_id="threshold-unavailable",
            resource_preset_id="resource-unavailable",
        ),
        admitted_use="capability-awareness-only",
        execution_disposition=ExecutionDisposition.CAPABILITY_ONLY,
        standardized_result_id=None,
        deployment_visible_outcome_code="not-executed",
        cost=VisibleCostSummary(
            wall_time_seconds=0,
            cpu_time_seconds=0,
            gpu_time_seconds=0,
            memory_pressure_class="none",
            gpu_pressure_class="none",
            cache_reuse_class="none",
            tool_call_count=0,
            llm_call_count=0,
            token_count=0,
        ),
        failure_condition=VisibleFailureCondition(
            failure_code="missing-real-admission",
            applicability_codes=("agent-training",),
            avoid_condition_codes=("do-not-claim-success",),
        ),
        execution_role="capability-candidate",
        public_runtime_trace_id="trace-1",
        admission_id=None,
        provenance_id="provenance-1",
    )


def trajectory(*, leaked: bool = False):
    teacher = frozen_teacher("demo", "group-a")
    grounding = VisibleEvidenceGrounding(
        observable_symptom="Visible score behavior needs bounded diagnosis.",
        graph_evidence_ids=(teacher.canonical_observation.observation_id,),
        observed_fact_codes=("window-closed",),
        bounded_inference_codes=("no-change-supported",),
        unknown_codes=("private-cause-unknown",),
        uncertainty_code="bounded",
        action_justification=(
            "Teacher rationale chooses this answer."
            if leaked
            else "No visible evidence supports a state change."
        ),
    )
    exchange = DemonstrationExchange(
        exchange_id="exchange-demo",
        memory_exchange=teacher.public_memory_exchange,
        grounding=grounding,
    )
    return build_trajectory(
        trajectory_id="trajectory-demo",
        partition_group_id="group-a",
        source_run_record_ids=("offline-velox",),
        source_admission_ids=(),
        initial_prompt=teacher.model_prompt,
        exchanges=(exchange,),
        pids_coverage=(PIDSRef(pids_id="velox"),),
        coverage_classes=(CoverageClass.CAPABILITY_AWARENESS,),
        sanitizer_version=DemonstrationSanitizer.VERSION,
    )


class DemonstrationConstructionTests(unittest.TestCase):
    def test_public_manifest_is_hashed_and_rejects_private_fields(self) -> None:
        manifest = build_dataset_manifest(
            dataset_manifest_id="manifest-1",
            dataset_id="public-dataset-alias",
            source_family="provenance-corpus",
            source_release="release-1",
            source_format="normalized-events",
            source_content_hashes=(SHA,),
            access_and_license_status="local-approved",
            normalized_storage_schema_id="normalized-v1",
            provenance_schema_id="provenance-v1",
            platform_class="linux",
            graph_construction=GraphConstructionManifest(
                builder_id="fixed-window-v1",
                origin=NOW,
                timezone="UTC",
                window_size_seconds=900,
                half_open_alignment=True,
                entity_types=("process",),
                relation_types=("exec",),
                transformation_policy_ids=("causal-v1",),
            ),
            pids_data_partitions=PIDSDataPartitions(
                train_partition_ref="pids-train",
                validation_partition_ref="pids-validation",
                demonstration_partition_ref="agent-training",
            ),
            registered_pids=(PIDSRef(pids_id="velox"),),
            pids_admission_ids=(),
            label_availability=LabelAvailability.PRIVATE_AVAILABLE,
            training_use=DemonstrationTrainingUse(
                pids_fit_allowed=False,
                threshold_calibration_allowed=False,
                sft_demonstration_allowed=True,
            ),
            private_companion_manifest_id="private-manifest-1",
            code_commit=GIT_SHA,
            builder_version="builder-v1",
            created_at=NOW,
        )
        self.assertEqual(manifest.content_hash, manifest.expected_hash())
        payload = manifest.model_dump()
        payload["ground_truth"] = {"campaign_id": "private"}
        with self.assertRaises(ValidationError):
            type(manifest).model_validate(payload)

    def test_unadmitted_record_is_capability_only_and_grouped_deterministically(self) -> None:
        one = offline_record()
        two = offline_record()
        self.assertEqual(one.counterfactual_group_id, two.counterfactual_group_id)
        self.assertEqual(one.content_hash, one.expected_hash())
        payload = one.model_dump()
        payload["failure_condition"] = None
        with self.assertRaises(ValidationError):
            type(one).model_validate(payload)

    def test_trajectory_closes_visible_evidence_and_exports_assistant_only_loss(self) -> None:
        canonical = trajectory()
        DemonstrationSanitizer.validate_trajectory(canonical)
        DemonstrationCorpusValidator.validate(
            trajectories=(canonical,),
            offline_records=(offline_record(),),
            admissions=(),
        )
        exported = DemonstrationExporter.export(canonical)
        self.assertEqual([message.loss for message in exported.messages], [False, False, True])
        encoded = DemonstrationExporter.canonical_jsonl((exported,))
        self.assertEqual(DemonstrationExporter.parse_canonical_jsonl(encoded), (exported,))

    def test_semantic_privilege_and_uncited_evidence_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "teacher rationale"):
            DemonstrationSanitizer.validate_trajectory(trajectory(leaked=True))
        teacher = frozen_teacher("bad-evidence", "group-a")
        exchange = DemonstrationExchange(
            exchange_id="exchange-bad",
            memory_exchange=teacher.public_memory_exchange,
            grounding=VisibleEvidenceGrounding(
                observable_symptom="Visible symptom.",
                graph_evidence_ids=("not-visible-yet",),
                observed_fact_codes=("visible-only",),
                bounded_inference_codes=("bounded",),
                unknown_codes=("unknown",),
                uncertainty_code="high",
                action_justification="Use only cited public evidence.",
            ),
        )
        with self.assertRaises(ValidationError):
            build_trajectory(
                trajectory_id="trajectory-bad",
                partition_group_id="group-a",
                source_run_record_ids=("offline-velox",),
                source_admission_ids=(),
                initial_prompt=teacher.model_prompt,
                exchanges=(exchange,),
                pids_coverage=(PIDSRef(pids_id="velox"),),
                coverage_classes=(CoverageClass.CAPABILITY_AWARENESS,),
                sanitizer_version=DemonstrationSanitizer.VERSION,
            )

    def test_private_teacher_parser_rejects_rationale_and_ambiguity(self) -> None:
        selected = StrictTeacherSelectionParser.parse(
            selection_id="selection-1",
            candidate_trajectory_ids=("trajectory-a", "trajectory-b"),
            response_text=json.dumps(
                {"selected_trajectory_id": "trajectory-a", "ambiguous_public_choice": False}
            ),
            private_reason_codes=("private-metric-rank",),
        )
        self.assertEqual(selected.selected_trajectory_id, "trajectory-a")
        with self.assertRaisesRegex(ValueError, "undeclared"):
            StrictTeacherSelectionParser.parse(
                selection_id="selection-2",
                candidate_trajectory_ids=("trajectory-a",),
                response_text=json.dumps(
                    {
                        "selected_trajectory_id": "trajectory-a",
                        "ambiguous_public_choice": False,
                        "rationale": "private answer",
                    }
                ),
                private_reason_codes=(),
            )

    def test_coverage_report_does_not_claim_unadmitted_success(self) -> None:
        report = build_coverage_report(
            report_id="coverage-1", trajectories=(trajectory(),), rejections=()
        )
        self.assertEqual(report.admitted_success_count, 0)
        self.assertEqual(report.capability_or_rejection_only_pids, ("velox:default",))

    def test_synthetic_builder_uses_dynamic_inventory_and_never_overwrites(self) -> None:
        environment = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT / "src")}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runtime = subprocess.run(
                (
                    sys.executable,
                    str(ROOT / "scripts" / "run_frozen_runtime_synthetic.py"),
                    "--run-id",
                    "runtime-source",
                    "--run-root",
                    str(root),
                    "--code-commit",
                    GIT_SHA,
                ),
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            command = (
                sys.executable,
                str(ROOT / "scripts" / "build_synthetic_demonstrations.py"),
                "--run-id",
                "demonstration-build",
                "--run-root",
                str(root),
                "--project-root",
                str(ROOT),
                "--source-runtime-run",
                str(root / "runtime-source"),
                "--code-commit",
                GIT_SHA,
            )
            first = subprocess.run(
                command, env=environment, capture_output=True, text=True, check=False
            )
            second = subprocess.run(
                command, env=environment, capture_output=True, text=True, check=False
            )
            summary = json.loads((root / "demonstration-build" / "metrics.json").read_text())
        self.assertEqual(runtime.returncode, 0, runtime.stderr)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertNotEqual(second.returncode, 0)
        self.assertGreaterEqual(summary["dynamic_source_config_count"], 8)
        self.assertEqual(
            summary["execution_matrix_row_count"], summary["dynamic_source_config_count"]
        )
        self.assertEqual(summary["successful_tool_use_count"], 0)
        self.assertTrue(all(summary["checks"].values()))


if __name__ == "__main__":
    unittest.main()
