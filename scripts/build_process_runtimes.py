#!/usr/bin/env python3
"""Build versioned least-privilege runtime trees for each process identity.

Requirements: REQ-LABEL-001, REQ-ENV-002..004, REQ-REPRO-001..002.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def copy_package(source: Path, destination: Path, components: tuple[str, ...]) -> None:
    destination.mkdir(parents=True)
    shutil.copy2(source / "__init__.py", destination / "__init__.py")
    for component in components:
        shutil.copytree(
            source / component,
            destination / component,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    project = args.project_root.resolve()
    output = args.output_root.resolve()
    allowed_text = os.environ.get("APT_PROCESS_RUNTIME_BUILD_ROOT")
    if not allowed_text or output.parent != Path(allowed_text).resolve():
        raise ValueError("runtime output must be a direct child of the approved build root")
    if output.exists():
        raise FileExistsError("runtime build is append-only")
    source = project / "src" / "apt_detection_agent"
    output.mkdir()
    copy_package(
        source,
        output / "controller" / "src" / "apt_detection_agent",
        ("schemas",),
    )
    copy_package(
        source,
        output / "pids" / "src" / "apt_detection_agent",
        ("schemas", "pidsmaker"),
    )
    copy_package(
        source,
        output / "evaluator" / "src" / "apt_detection_agent",
        ("schemas", "evaluator"),
    )
    scripts = project / "scripts"
    script_map = {
        "controller": ("finalize_real_public_report.py", "finalize_stage_run.py"),
        "pids": (
            "standardize_pids_result.py",
            "run_structured_pids_adapter_smoke.py",
            "run_frozen_pids_tool.py",
            "pidsmaker_stage_runner.py",
            "pidsmaker_causal_runner.py",
        ),
        "evaluator": (
            "build_real_hidden_request.py",
            "run_hidden_evaluator.py",
            "run_memory_retrieval_sensitivity.py",
        ),
    }
    for identity, names in script_map.items():
        destination = output / identity / "scripts"
        destination.mkdir()
        for name in names:
            shutil.copy2(scripts / name, destination / name)
    commit = subprocess.run(
        ("git", "-C", str(project), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    files = sorted(path for path in output.rglob("*") if path.is_file())
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(output).as_posix().encode())
        digest.update(path.read_bytes())
    marker = {
        "schema_version": "apt-process-runtimes-v1",
        "code_commit": commit,
        "tree_hash": digest.hexdigest(),
        "controller_excludes": ["apt_detection_agent.evaluator", "private campaign builder"],
        "identities": sorted(script_map),
    }
    (output / "runtime_manifest.json").write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(marker, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
