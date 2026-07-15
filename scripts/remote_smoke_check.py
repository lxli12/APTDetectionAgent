#!/usr/bin/env python3
"""Record a secret-free snapshot of the authoritative AutoDL runtime.

Run this script inside the ``pids`` Conda environment. It performs read-only
runtime checks and writes JSON only when ``--output`` is supplied. Generated
snapshots must be stored outside the Git checkout.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from typing import Any, Sequence


DEFAULT_REPOSITORY_ROOT = Path("/root/APTDetectionAgent")
DEFAULT_DATA_ROOT = Path("/root/autodl-tmp")
REQUIRED_DATA_DIRECTORIES = (
    "data/raw_datasets",
    "data/sft_data",
    "huggingface",
    "llm-models",
    "pidsmaker/cache",
    "pidsmaker/intermediate",
    "pidsmaker/checkpoints",
    "pidsmaker/outputs",
    "apt-detection-agent/experiments",
    "apt-detection-agent/checkpoints",
    "apt-detection-agent/offline-run-table",
    "apt-detection-agent/environment-snapshots",
    "tmp",
    "cache",
)


def _run(argv: Sequence[str], *, timeout: int = 15) -> dict[str, Any]:
    """Run a fixed diagnostic command and normalize its result."""

    try:
        completed = subprocess.run(
            list(argv),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": type(exc).__name__}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _read_first(paths: Sequence[Path]) -> str | None:
    for path in paths:
        try:
            return path.read_text(encoding="utf-8").strip()
        except (FileNotFoundError, PermissionError, OSError):
            continue
    return None


def _git_value(repository_root: Path, *args: str) -> str | None:
    result = _run(("git", "-C", str(repository_root), *args))
    return result["stdout"] if result["ok"] else None


def _package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def build_snapshot(repository_root: Path, data_root: Path) -> dict[str, Any]:
    """Build a machine-readable snapshot without reading arbitrary env vars."""

    try:
        import pidsmaker
        pidsmaker_import = {
            "ok": True,
            "module_path": str(Path(pidsmaker.__file__).resolve()),
            "distribution_version": _package_version("pidsmaker"),
        }
    except Exception as exc:  # import failures are diagnostic output
        pidsmaker_import = {"ok": False, "error": type(exc).__name__}

    try:
        import torch
        gpu_count = torch.cuda.device_count()
        torch_info: dict[str, Any] = {
            "version": torch.__version__,
            "cuda_version": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "gpu_count": gpu_count,
            "gpu_names": [torch.cuda.get_device_name(index) for index in range(gpu_count)],
        }
    except Exception as exc:
        torch_info = {"ok": False, "error": type(exc).__name__}

    disk = shutil.disk_usage(data_root)
    cgroup_cpu = _read_first((
        Path("/sys/fs/cgroup/cpu.max"),
        Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"),
    ))
    cgroup_cpuset = _read_first((
        Path("/sys/fs/cgroup/cpuset.cpus.effective"),
        Path("/sys/fs/cgroup/cpuset/cpuset.cpus"),
    ))
    cgroup_memory = _read_first((
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ))
    postgres = _run(("pg_isready",))
    nvidia = _run((
        "nvidia-smi",
        "--query-gpu=index,name,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ))

    expected_submodule = _git_value(repository_root, "ls-tree", "HEAD", "PIDSMaker")
    actual_submodule = _git_value(repository_root / "PIDSMaker", "rev-parse", "HEAD")
    parent_commit = _git_value(repository_root, "rev-parse", "HEAD")
    remote_main = _git_value(repository_root, "rev-parse", "origin/main")

    return {
        "schema_version": "1.0",
        "repository": {
            "path": str(repository_root.resolve()),
            "commit": parent_commit,
            "origin_main_commit": remote_main,
            "clean": _git_value(repository_root, "status", "--porcelain") == "",
            "pidsmaker_expected_tree_entry": expected_submodule,
            "pidsmaker_commit": actual_submodule,
        },
        "runtime": {
            "platform": platform.platform(),
            "python": sys.version.splitlines()[0],
            "executable": sys.executable,
            "pidsmaker": pidsmaker_import,
            "torch": torch_info,
            "nvidia_smi": nvidia,
            "postgresql": {
                "ready": postgres["ok"],
                "status": postgres.get("stdout") or postgres.get("stderr"),
            },
        },
        "resources": {
            "logical_cpu_count": os.cpu_count(),
            "cgroup_cpu_max": cgroup_cpu,
            "cgroup_cpuset_effective": cgroup_cpuset,
            "cgroup_memory_max_bytes": cgroup_memory,
            "data_disk": {
                "path": str(data_root.resolve()),
                "total_bytes": disk.total,
                "used_bytes": disk.used,
                "free_bytes": disk.free,
            },
        },
        "storage": {
            "data_root": str(data_root.resolve()),
            "required_directories": {
                relative: (data_root / relative).is_dir()
                for relative in REQUIRED_DATA_DIRECTORIES
            },
        },
    }


def validate_snapshot(snapshot: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    repository = snapshot["repository"]
    if repository["commit"] != repository["origin_main_commit"]:
        failures.append("repository HEAD does not match origin/main")
    if not repository["clean"]:
        failures.append("remote repository has uncommitted changes")
    if repository["pidsmaker_commit"] not in (
        repository["pidsmaker_expected_tree_entry"] or ""
    ):
        failures.append("PIDSMaker checkout does not match the parent gitlink")
    if not snapshot["runtime"]["pidsmaker"]["ok"]:
        failures.append("pidsmaker import failed")
    torch_info = snapshot["runtime"]["torch"]
    if not torch_info.get("cuda_available") or torch_info.get("gpu_count", 0) < 1:
        failures.append("PyTorch cannot see a CUDA GPU")
    missing = [
        path
        for path, exists in snapshot["storage"]["required_directories"].items()
        if not exists
    ]
    if missing:
        failures.append("missing data-disk directories: " + ", ".join(missing))
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository-root",
        type=Path,
        default=Path(os.environ.get("APT_AGENT_REPOSITORY_ROOT", DEFAULT_REPOSITORY_ROOT)),
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("APT_AGENT_DATA_ROOT", DEFAULT_DATA_ROOT)),
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional external JSON path. Paths inside the repository are rejected.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot = build_snapshot(args.repository_root, args.data_root)
    failures = validate_snapshot(snapshot)
    snapshot["validation"] = {"ok": not failures, "failures": failures}
    rendered = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"

    if args.output is not None:
        output = args.output.resolve()
        repository_root = args.repository_root.resolve()
        if output == repository_root or repository_root in output.parents:
            raise SystemExit("snapshot output must be outside the Git checkout")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
