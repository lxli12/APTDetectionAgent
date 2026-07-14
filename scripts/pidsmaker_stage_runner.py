#!/usr/bin/env python3
"""Run a label-free prefix of the pinned PIDSMaker pipeline.

Requirements: REQ-PIDS-004..005, REQ-LABEL-001..004, REQ-TOOL-001..005,
REQ-WANDB-001, REQ-REPRO-001..002.

This file is executed by the ``pids`` Conda environment.  It intentionally does
not import the controller package, PIDSMaker's all-stage ``main.py``, or the
``pidsmaker.tasks`` package initializer.  The latter imports evaluation/training
modules (and therefore W&B) even for preprocessing-only runs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path
from types import ModuleType


PINNED_PIDSMaker_COMMIT = "32602734bc9f896be5fc0f03f0a185c967cd6624"
SAFE_STAGES = ("construction", "transformation", "featurization", "feat_inference")
REQUIRED_DATABASE_ENV = (
    "PIDS_DB_HOST",
    "PIDS_DB_USER",
    "PIDS_DB_PASSWORD",
    "PIDS_DB_PORT",
)
SAFE_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
SAFE_OVERRIDE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]*=[^\x00\r\n]*$")
FORBIDDEN_OVERRIDE_PARTS = {
    "artifact_dir",
    "database",
    "device",
    "gpu",
    "project",
    "sweep_id",
    "tags",
    "tuning_mode",
    "wandb",
}


class StageRunnerError(RuntimeError):
    """A fail-closed validation or compatibility error."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_config_id")
    parser.add_argument("dataset_id")
    parser.add_argument("--pidsmaker-root", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--stop-after", choices=SAFE_STAGES, required=True)
    parser.add_argument("--override", action="append", default=[])
    parser.add_argument("--cpu", action="store_true")
    return parser.parse_args(argv)


def validate_inputs(args: argparse.Namespace, environ: dict[str, str]) -> tuple[Path, Path]:
    for value, name in (
        (args.source_config_id, "source_config_id"),
        (args.dataset_id, "dataset_id"),
    ):
        if not SAFE_TOKEN.fullmatch(value):
            raise StageRunnerError(f"{name} contains unsafe characters")

    root = Path(args.pidsmaker_root).resolve()
    artifact_dir = Path(args.artifact_dir).resolve()
    if not (root / "pidsmaker" / "config" / "pipeline.py").is_file():
        raise StageRunnerError("pidsmaker-root is not a PIDSMaker checkout")
    allowed_root_text = environ.get("APT_PIDS_ARTIFACT_ROOT")
    if not allowed_root_text:
        raise StageRunnerError("APT_PIDS_ARTIFACT_ROOT is required")
    allowed_root = Path(allowed_root_text).resolve()
    if not allowed_root.is_dir():
        raise StageRunnerError("approved artifact root does not exist")
    if artifact_dir.parent != allowed_root:
        raise StageRunnerError("artifact directory must be a direct child of the approved root")
    if artifact_dir.exists():
        raise StageRunnerError("artifact directory already exists")

    missing = [name for name in REQUIRED_DATABASE_ENV if not environ.get(name)]
    if missing:
        raise StageRunnerError("database connection environment is incomplete")
    if environ.get("WANDB_MODE") != "disabled":
        raise StageRunnerError("WANDB_MODE=disabled is mandatory")

    for override in args.override:
        if not SAFE_OVERRIDE.fullmatch(override):
            raise StageRunnerError("override has invalid syntax")
        key = override.split("=", 1)[0]
        if set(key.lower().split(".")) & FORBIDDEN_OVERRIDE_PARTS:
            raise StageRunnerError(f"override {key} is executor-owned or prohibited")
    return root, artifact_dir


def pinned_commit(root: Path) -> str:
    """Read the submodule commit without invoking a shell or Git executable."""

    git_marker = root / ".git"
    if git_marker.is_file():
        text = git_marker.read_text().strip()
        if not text.startswith("gitdir: "):
            raise StageRunnerError("unsupported PIDSMaker .git marker")
        git_dir = (root / text.removeprefix("gitdir: ")).resolve()
    else:
        git_dir = git_marker
    head = (git_dir / "HEAD").read_text().strip()
    if head.startswith("ref: "):
        head = (git_dir / head.removeprefix("ref: ")).read_text().strip()
    if head != PINNED_PIDSMaker_COMMIT:
        raise StageRunnerError(f"PIDSMaker commit mismatch: {head}")
    return head


def upstream_argv(args: argparse.Namespace, artifact_dir: Path, environ: dict[str, str]) -> list[str]:
    """Build upstream config arguments; the password never enters this process's argv."""

    values = [
        args.source_config_id,
        args.dataset_id,
        "--artifact_dir",
        str(artifact_dir),
        "--database_host",
        environ["PIDS_DB_HOST"],
        "--database_user",
        environ["PIDS_DB_USER"],
        "--database_password",
        environ["PIDS_DB_PASSWORD"],
        "--database_port",
        environ["PIDS_DB_PORT"],
    ]
    if args.cpu:
        values.append("--cpu")
    for override in args.override:
        values.append(f"--{override}")
    return values


def load_stage_module(root: Path, stage: str) -> ModuleType:
    """Load one task file without executing ``pidsmaker.tasks.__init__``."""

    path = root / "pidsmaker" / "tasks" / f"{stage}.py"
    spec = importlib.util.spec_from_file_location(f"_apt_pidsmaker_{stage}", path)
    if spec is None or spec.loader is None:
        raise StageRunnerError(f"cannot load PIDSMaker stage {stage}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sanitized_resolved_config(args: argparse.Namespace, commit: str) -> dict[str, object]:
    return {
        "source_config_id": args.source_config_id,
        "dataset_id": args.dataset_id,
        "stop_after": args.stop_after,
        "cpu": args.cpu,
        "overrides": sorted(args.override),
        "pidsmaker_commit": commit,
        "wandb_mode": "disabled",
        "database": {"injected_by_environment": True},
        "excluded_privileged_fields": ["ground_truth_relative_path", "attack_to_time_window"],
    }


def run(args: argparse.Namespace, environ: dict[str, str] | None = None) -> int:
    environ = dict(os.environ if environ is None else environ)
    root, artifact_dir = validate_inputs(args, environ)
    commit = pinned_commit(root)
    sys.path.insert(0, str(root))

    from pidsmaker.config import get_runtime_required_args, get_yml_cfg, set_task_to_done

    upstream_args = get_runtime_required_args(args=upstream_argv(args, artifact_dir, environ))
    cfg = get_yml_cfg(upstream_args)

    # These upstream literals are evaluation-only metadata.  No task in this
    # runner is allowed to observe them, and the runner never serializes them.
    cfg.dataset.ground_truth_relative_path = []
    cfg.dataset.attack_to_time_window = []

    # ``get_yml_cfg`` creates per-stage log directories below the previously
    # absent run root.  Its existence here is expected, but it must still be a
    # directory and must not have existed at validation time.
    if not artifact_dir.is_dir():
        raise StageRunnerError("PIDSMaker did not create the artifact directory")
    # JSON is a strict YAML subset; using it here avoids adding a new runtime
    # dependency while preserving the required resolved_config.yaml artifact.
    (artifact_dir / "resolved_config.yaml").write_text(
        json.dumps(sanitized_resolved_config(args, commit), indent=2, sort_keys=True) + "\n"
    )

    completed: list[dict[str, object]] = []
    stop_index = SAFE_STAGES.index(args.stop_after)
    for stage in SAFE_STAGES[: stop_index + 1]:
        module = load_stage_module(root, stage)
        started = time.monotonic()
        module.main(cfg)
        task_path = Path(getattr(cfg, stage)._task_path)
        set_task_to_done(str(task_path))
        completed.append(
            {
                "stage": stage,
                "elapsed_seconds": round(time.monotonic() - started, 6),
                "task_path_relative_to_artifact_dir": task_path.relative_to(artifact_dir).as_posix(),
            }
        )

    summary = {
        "schema_version": "pidsmaker-stage-smoke-v1",
        "pidsmaker_commit": commit,
        "completed_stages": completed,
        "artifact_tree_hash": artifact_tree_hash(artifact_dir),
    }
    (artifact_dir / "stage_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return 0


def artifact_tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name == "stage_summary.json":
            continue
        digest.update(path.relative_to(root).as_posix().encode())
        file_digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                file_digest.update(chunk)
        digest.update(file_digest.digest())
    return digest.hexdigest()


def main() -> None:
    try:
        raise SystemExit(run(parse_args()))
    except StageRunnerError as exc:
        print(f"stage runner rejected request: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
