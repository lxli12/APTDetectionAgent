"""Generate a deployment-visible report from sanitized episode feedback only.

Requirements: REQ-LABEL-001..004, REQ-EVAL-002, REQ-EVAL-006,
REQ-ARTIFACT-001..003, REQ-REPRO-001..002.
"""

from __future__ import annotations

import json
from pathlib import Path

from apt_detection_agent.evaluation.public import EpisodeMetricsFeedback


def finalize_public_report(*, run_dir: Path, feedback_path: Path, project_root: Path) -> None:
    run_dir = run_dir.resolve()
    feedback_path = feedback_path.resolve()
    if not feedback_path.is_relative_to(run_dir):
        raise ValueError("sanitized feedback must be under the Agent-visible run directory")
    summary_path = run_dir / "agent_summary.json"
    if not summary_path.is_file():
        raise ValueError("agent summary is missing")
    summary = json.loads(summary_path.read_text())
    if summary.get("formal_performance_claim") is not False:
        raise ValueError("synthetic report cannot claim formal performance")
    feedback = EpisodeMetricsFeedback.model_validate_json(feedback_path.read_text())
    if feedback.episode_id != summary["episode_id"]:
        raise ValueError("evaluator feedback episode does not match the Agent run")

    metrics_path = run_dir / "metrics.json"
    report_path = run_dir / "report.md"
    status_path = run_dir / "run_status.json"
    for path in (metrics_path, report_path, status_path):
        if path.exists():
            raise FileExistsError(path)
    metrics_path.write_text(feedback.model_dump_json(indent=2) + "\n")
    report_path.write_text(
        "# Synthetic Agent validation report\n\n"
        "This report contains deployment-visible integration evidence only. Full metrics "
        "remain in the hidden evaluator's private artifact.\n\n"
        f"- Episode: `{feedback.episode_id}`\n"
        f"- Private metrics artifact reference: `{feedback.metrics_artifact_id}`\n"
        f"- Predictions: {summary['prediction_count']}\n"
        f"- Structured tool calls: {summary['tool_call_count']}\n"
        "- Formal performance claim: false\n"
    )

    from .synthetic import write_synthetic_artifact_manifest

    manifest = write_synthetic_artifact_manifest(
        run_dir=run_dir,
        project_root=project_root,
        run_id=summary["run_id"],
    )
    status_path.write_text(
        json.dumps(
            {
                "run_id": summary["run_id"],
                "status": "succeeded",
                "artifact_manifest_id": manifest.manifest_id,
                "evaluation_feedback_level": "episode_artifact_reference_only",
                "evidence_class": "synthetic_integration_only",
                "formal_performance_claim": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
