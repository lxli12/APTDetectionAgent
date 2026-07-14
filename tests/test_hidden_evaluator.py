"""Phase 7 privileged metrics and feedback isolation tests.

Requirements: REQ-LABEL-001..004, REQ-EVAL-001..007, REQ-DB-001..003.
"""

from __future__ import annotations

import json
import math
import tempfile
import subprocess
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from apt_detection_agent.evaluator import (
    CampaignManifest,
    DatabaseRolePolicy,
    EvaluatorIPCPaths,
    HiddenEvaluationInput,
    HiddenEvaluator,
    ScoredEntity,
    ValidationCoverageCalibrationInput,
    ValidationCoverageCalibrator,
    ValidationEntityScore,
)
from apt_detection_agent.schemas import DataSplit


NOW = datetime(2026, 1, 2, tzinfo=timezone.utc)


def campaign(campaign_id: str, entity: str, window: str) -> CampaignManifest:
    return CampaignManifest(
        manifest_version="campaigns-v1",
        campaign_id=campaign_id,
        dataset_id="dataset-private",
        attack_date_range=(NOW - timedelta(hours=1), NOW),
        included_window_ids=(window,),
        malicious_entity_ids=(entity,),
        ground_truth_sources=("private-source",),
    )


def evaluation_input(**updates: object) -> HiddenEvaluationInput:
    values: dict[str, object] = {
        "evaluation_id": "evaluation-1",
        "split": DataSplit.HELD_OUT,
        "scenario_id": "scenario-1",
        "episode_id": "episode-1",
        "campaign_manifest_version": "campaigns-v1",
        "campaigns": (
            campaign("campaign-1", "node-a", "window-1"),
            campaign("campaign-2", "node-b", "window-2"),
        ),
        "scored_entities": (
            ScoredEntity(
                entity_id="node-a",
                score=0.9,
                alerted=True,
                window_ids=("window-1",),
                evidence_artifact_ids=("evidence-a",),
            ),
            ScoredEntity(
                entity_id="node-c",
                score=0.8,
                alerted=True,
                window_ids=("window-1",),
            ),
            ScoredEntity(
                entity_id="node-b",
                score=0.7,
                alerted=True,
                window_ids=("window-2",),
            ),
            ScoredEntity(entity_id="node-d", score=0.1, alerted=False),
        ),
        "universe_entity_ids": ("node-a", "node-b", "node-c", "node-d"),
        "malicious_node_window_occurrences": (
            ("window-1", "node-a"),
            ("window-2", "node-b"),
        ),
        "malicious_edges": (("node-a", "node-b"), ("node-b", "node-d")),
        "recovered_edges": (("node-a", "node-b"), ("node-c", "node-d")),
        "attack_chain_edges": (("node-a", "node-b"),),
        "phase_to_malicious_entities": {
            "initial-access": ("node-a",),
            "execution": ("node-b",),
        },
        "latency_seconds": 2.5,
        "gpu_seconds": 1.25,
        "tool_calls": 3,
        "campaign_detection_delay_seconds": {"campaign-1": 10.0, "campaign-2": 30.0},
        "window_alert_counts": {"window-1": 2, "window-2": 1},
        "window_score_means": {"window-1": 0.55, "window-2": 0.40},
        "llm_calls": 2,
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "max_context_tokens": 80,
        "slow_path_triggers": 1,
        "reconfigurations": 1,
        "model_switches": 1,
        "threshold_changes": 0,
        "retraining_count": 0,
        "cache_hits": 3,
        "cache_requests": 4,
        "computed_at": NOW,
    }
    values.update(updates)
    return HiddenEvaluationInput.model_validate(values)


class HiddenMetricTests(unittest.TestCase):
    def test_primary_campaign_and_unique_node_metrics(self) -> None:
        output = HiddenEvaluator().evaluate(evaluation_input())
        record = output.record
        self.assertEqual(output.metric_definition_version, "agent-eval-v2")
        self.assertEqual(record.campaign_coverage, 1.0)
        self.assertEqual(
            (
                record.unique_malicious_node_tp,
                record.unique_malicious_node_fp,
                record.unique_malicious_node_fn,
            ),
            (2, 1, 0),
        )
        self.assertAlmostEqual(record.p_at_c_100 or 0.0, 2 / 3)
        self.assertAlmostEqual(record.mcc, 2 / math.sqrt(12))
        self.assertAlmostEqual(record.adp, 2 / 3)

    def test_occurrence_edge_phase_evidence_and_efficiency_denominators_are_separate(self) -> None:
        record = HiddenEvaluator().evaluate(evaluation_input()).record
        self.assertEqual(record.node_window_metrics["truth_denominator"], 2)
        self.assertEqual(record.node_window_metrics["tp"], 2)
        self.assertEqual(record.node_window_metrics["fp"], 1)
        self.assertEqual(record.edge_metrics["malicious_edge_denominator"], 2)
        self.assertEqual(record.edge_metrics["attack_chain_edge_denominator"], 1)
        self.assertEqual(record.edge_metrics["phase_denominator"], 2)
        self.assertEqual(record.evidence_metrics["unique_tp_denominator"], 2)
        self.assertEqual(record.evidence_metrics["provenance_completeness"], 0.5)
        self.assertEqual(record.efficiency_metrics["tool_calls"], 3)

    def test_delay_stability_and_control_metrics_are_separate(self) -> None:
        record = HiddenEvaluator().evaluate(evaluation_input()).record
        self.assertEqual(record.delay_metrics["all_campaign_denominator"], 2)
        self.assertEqual(record.delay_metrics["detected_campaign_denominator"], 2)
        self.assertEqual(record.delay_metrics["mean_detection_delay_seconds"], 20.0)
        self.assertEqual(record.stability_metrics["window_denominator"], 2)
        self.assertEqual(record.stability_metrics["total_alert_volume"], 3)
        self.assertAlmostEqual(record.stability_metrics["window_alert_count_mean"], 1.5)
        self.assertEqual(record.control_metrics["reconfigurations"], 1)
        self.assertEqual(record.control_metrics["cache_hit_rate"], 0.75)
        self.assertEqual(record.efficiency_metrics["prompt_tokens"], 100)

    def test_unknown_delay_campaign_or_incoherent_stability_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            evaluation_input(campaign_detection_delay_seconds={"unknown-campaign": 1.0})
        with self.assertRaises(ValidationError):
            evaluation_input(window_score_means={"window-1": 0.5})
        with self.assertRaises(ValidationError):
            evaluation_input(window_alert_counts={"window-1": 1, "window-2": 1})
        with self.assertRaises(ValidationError):
            evaluation_input(cache_hits=2, cache_requests=1)

    def test_campaign_manifest_version_mismatch_is_rejected(self) -> None:
        mismatched = campaign("campaign-x", "node-a", "window-1").model_copy(
            update={"manifest_version": "other-version"}
        )
        with self.assertRaises(ValidationError):
            evaluation_input(campaigns=(mismatched,))

    def test_malicious_entity_outside_universe_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            evaluation_input(universe_entity_ids=("node-c", "node-d"))

    def test_equal_scores_enter_p_at_full_coverage_as_one_threshold_group(self) -> None:
        request = evaluation_input(
            campaigns=(campaign("campaign-1", "node-a", "window-1"),),
            scored_entities=(
                ScoredEntity(entity_id="node-a", score=0.9, alerted=True),
                ScoredEntity(entity_id="node-c", score=0.9, alerted=True),
            ),
            universe_entity_ids=("node-a", "node-c"),
            malicious_node_window_occurrences=(),
        )
        record = HiddenEvaluator().evaluate(request).record
        self.assertEqual(record.p_at_c_100, 0.5)

    def test_deployment_is_not_a_hidden_evaluator_dependency(self) -> None:
        with self.assertRaises(ValidationError):
            evaluation_input(split=DataSplit.DEPLOYMENT)


class FeedbackIsolationTests(unittest.TestCase):
    def test_heldout_returns_only_episode_artifact_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            private_path = Path(temp) / "private" / "metrics-1.json"
            feedback = HiddenEvaluator().evaluate_to_private_artifact(
                evaluation_input(), private_path
            )
            public_payload = json.loads(feedback.model_dump_json())
            private_payload = json.loads(private_path.read_text())
        self.assertEqual(set(public_payload), {"split", "episode_id", "metrics_artifact_id", "emitted_at"})
        self.assertNotIn("tp", feedback.model_dump_json().lower())
        self.assertIn("unique_malicious_node_tp", json.dumps(private_payload))

    def test_private_metric_artifact_is_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            private_path = Path(temp) / "metrics.json"
            evaluator = HiddenEvaluator()
            evaluator.evaluate_to_private_artifact(evaluation_input(), private_path)
            with self.assertRaises(FileExistsError):
                evaluator.evaluate_to_private_artifact(evaluation_input(), private_path)

    def test_step_reward_is_agent_training_only(self) -> None:
        feedback = HiddenEvaluator.training_step_feedback(
            step_id="step-1", sanitized_reward=0.25, signal_id="bounded-signal-v1"
        )
        self.assertEqual(feedback.split, DataSplit.AGENT_TRAINING)

    def test_benign_only_validation_cannot_claim_campaign_coverage_calibration(self) -> None:
        with self.assertRaises(ValidationError):
            evaluation_input(split=DataSplit.VALIDATION, campaigns=())

    def test_database_roles_are_distinct_and_controller_has_no_private_access(self) -> None:
        policy = DatabaseRolePolicy(
            admin_role="db-admin",
            pids_worker_role="pids-worker",
            hidden_evaluator_role="hidden-evaluator",
            agent_controller_role="agent-controller",
        )
        self.assertFalse(policy.agent_private_schema_access)
        with self.assertRaises(ValidationError):
            DatabaseRolePolicy(
                admin_role="shared",
                pids_worker_role="shared",
                hidden_evaluator_role="hidden-evaluator",
                agent_controller_role="agent-controller",
            )

    def test_ipc_rejects_private_path_under_public_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(ValidationError):
                EvaluatorIPCPaths(
                    private_input=root / "private" / "input.json",
                    private_output=root / "private" / "metrics.json",
                    public_feedback=root / "feedback.json",
                    private_root=root / "private",
                    public_root=root,
                )

    def test_separate_process_emits_only_sanitized_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            private_root = root / "evaluator-private"
            public_root = root / "agent-visible"
            private_root.mkdir()
            public_root.mkdir()
            request_path = private_root / "request.json"
            metrics_path = private_root / "metrics.json"
            feedback_path = public_root / "feedback.json"
            request_path.write_text(evaluation_input().model_dump_json())
            project_root = Path(__file__).resolve().parents[1]
            environment = {
                "PYTHONPATH": str(project_root / "src"),
                "HIDDEN_EVALUATOR_PRIVATE_ROOT": str(private_root),
                "AGENT_FEEDBACK_ROOT": str(public_root),
            }
            completed = subprocess.run(
                (
                    sys.executable,
                    str(project_root / "scripts/run_hidden_evaluator.py"),
                    "--private-input",
                    str(request_path),
                    "--private-output",
                    str(metrics_path),
                    "--public-feedback",
                    str(feedback_path),
                ),
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            feedback_text = feedback_path.read_text()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("unique_malicious_node", feedback_text)
        self.assertNotIn("campaign_coverage", feedback_text)


class ValidationCoverageCalibrationTests(unittest.TestCase):
    def calibration_input(self, **updates: object) -> ValidationCoverageCalibrationInput:
        values: dict[str, object] = {
            "calibration_id": "coverage-calibration-1",
            "split": DataSplit.VALIDATION,
            "source_dataset": "dataset-private",
            "campaign_manifest_version": "campaigns-v1",
            "campaigns": (
                campaign("campaign-1", "node-a", "window-1"),
                campaign("campaign-2", "node-b", "window-2"),
            ),
            "scored_entities": (
                ValidationEntityScore(entity_id="node-a", score=0.9),
                ValidationEntityScore(entity_id="node-c", score=0.8),
                ValidationEntityScore(entity_id="node-b", score=0.7),
                ValidationEntityScore(entity_id="node-d", score=0.1),
            ),
            "universe_entity_ids": ("node-a", "node-b", "node-c", "node-d"),
            "target_coverage": 1.0,
            "target_metric": "campaign-coverage",
            "threshold_id": "threshold-validation-coverage-1",
            "checkpoint_hash": "1" * 64,
            "created_at": NOW,
            "code_commit": "2" * 40,
        }
        values.update(updates)
        return ValidationCoverageCalibrationInput.model_validate(values)

    def test_highest_threshold_meeting_agent_campaign_coverage_is_frozen(self) -> None:
        result = ValidationCoverageCalibrator().calibrate(self.calibration_input())
        self.assertEqual(result.threshold.value, 0.7)
        self.assertEqual(result.achieved_campaign_coverage, 1.0)
        self.assertAlmostEqual(result.precision_at_threshold, 2 / 3)
        self.assertEqual(result.threshold.calibration_method.value, "validation_coverage")
        self.assertEqual(result.threshold.source_split.value, "validation")
        self.assertEqual(result.threshold.checkpoint_hash, "1" * 64)

    def test_constraint_is_campaign_level_not_malicious_node_fraction(self) -> None:
        first = campaign("campaign-1", "node-a", "window-1").model_copy(
            update={"malicious_entity_ids": ("node-a", "node-x")}
        )
        request = self.calibration_input(
            campaigns=(first, campaign("campaign-2", "node-b", "window-2")),
            universe_entity_ids=("node-a", "node-b", "node-c", "node-d", "node-x"),
            target_coverage=0.5,
        )
        result = ValidationCoverageCalibrator().calibrate(request)
        self.assertEqual(result.threshold.value, 0.9)
        self.assertEqual(result.achieved_campaign_coverage, 0.5)

    def test_heldout_or_benign_only_calibration_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.calibration_input(split=DataSplit.HELD_OUT)
        with self.assertRaises(ValidationError):
            self.calibration_input(campaigns=())

    def test_unsatisfied_campaign_constraint_fails_closed(self) -> None:
        request = self.calibration_input(
            scored_entities=(ValidationEntityScore(entity_id="node-a", score=0.9),)
        )
        with self.assertRaises(ValueError):
            ValidationCoverageCalibrator().calibrate(request)


if __name__ == "__main__":
    unittest.main()
