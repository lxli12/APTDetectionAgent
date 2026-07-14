"""Generate a deployment-visible report from sanitized episode feedback only.

Requirements: REQ-LABEL-001..004, REQ-EVAL-002, REQ-EVAL-006,
REQ-ARTIFACT-001..003, REQ-REPRO-001..002.
"""

from __future__ import annotations

import json
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path

from apt_detection_agent.evaluation.public import EpisodeMetricsFeedback
from apt_detection_agent.schemas import ArtifactManifest, ArtifactRecord

PINNED_PIDS_SHA = "32602734bc9f896be5fc0f03f0a185c967cd6624"


def _write_artifact_manifest(
    *, run_dir: Path, project_root: Path, run_id: str, created_at: datetime
) -> ArtifactManifest:
    manifest_path = run_dir / "artifact_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(manifest_path)
    artifacts = []
    for path in sorted(item for item in run_dir.iterdir() if item.is_file()):
        if path.name in {"artifact_manifest.json", "run_status.json"}:
            continue
        content = path.read_bytes()
        artifacts.append(
            ArtifactRecord(
                artifact_id=f"synthetic-{hashlib.sha256(path.name.encode()).hexdigest()[:16]}",
                artifact_type="synthetic_integration_artifact",
                relative_path=path.name,
                content_hash=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
                producing_stage="synthetic_end_to_end_validation",
                created_at=created_at,
            )
        )
    commit = subprocess.run(
        ("git", "-C", str(project_root.resolve()), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    manifest = ArtifactManifest(
        manifest_id="synthetic-agent-artifacts-v1",
        run_id=run_id,
        code_commit=commit,
        pidsmaker_commit=PINNED_PIDS_SHA,
        artifacts=tuple(artifacts),
        created_at=created_at,
    )
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n")
    return manifest


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

    manifest = _write_artifact_manifest(
        run_dir=run_dir,
        project_root=project_root,
        run_id=summary["run_id"],
        created_at=feedback.emitted_at,
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
