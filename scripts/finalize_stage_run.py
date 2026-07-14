#!/usr/bin/env python3
"""Hash a stage-orchestrator run and write terminal manifests once.

Requirements: REQ-ARTIFACT-001..003, REQ-REPRO-001..003.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--status", choices=("succeeded", "blocked", "failed"), required=True)
    parser.add_argument("--reason", default="")
    parser.add_argument("--evidence-class", required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    artifact_path = run_dir / "artifact_manifest.json"
    status_path = run_dir / "run_status.json"
    if artifact_path.exists() or status_path.exists():
        raise FileExistsError("terminal run manifests are append-only")
    artifacts = []
    for path in sorted(item for item in run_dir.iterdir() if item.is_file()):
        content = path.read_bytes()
        artifacts.append(
            {
                "relative_path": path.name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "stage-run-artifacts-v1",
                "run_id": run_dir.name,
                "artifacts": artifacts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    status_path.write_text(
        json.dumps(
            {
                "run_id": run_dir.name,
                "status": args.status,
                "reason": args.reason or None,
                "evidence_class": args.evidence_class,
                "ended_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
