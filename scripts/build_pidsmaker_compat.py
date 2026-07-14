#!/usr/bin/env python3
"""Build an isolated, versioned PIDSMaker compatibility tree.

Requirements: REQ-GIT-003, REQ-PIDS-005, REQ-CAUSAL-001..004,
REQ-WANDB-001, REQ-REPRO-001..002.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


PINNED_COMMIT = "32602734bc9f896be5fc0f03f0a185c967cd6624"
PATCH_SET = Path("compat") / "pidsmaker" / PINNED_COMMIT


class CompatibilityBuildError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-root", required=True)
    return parser.parse_args()


def git_marker_commit(root: Path) -> str:
    marker = root / ".git"
    if marker.is_file():
        text = marker.read_text().strip()
        if not text.startswith("gitdir: "):
            raise CompatibilityBuildError("unsupported source Git marker")
        git_dir = (root / text.removeprefix("gitdir: ")).resolve()
    elif marker.is_dir():
        git_dir = marker.resolve()
    else:
        raise CompatibilityBuildError("source has no Git identity")
    head = (git_dir / "HEAD").read_text().strip()
    if head.startswith("ref: "):
        head = (git_dir / head.removeprefix("ref: ")).read_text().strip()
    return head


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(project_root: Path, source_root: Path, output_root: Path) -> dict[str, object]:
    project_root = project_root.resolve()
    source_root = source_root.resolve()
    output_root = output_root.resolve()
    allowed_text = os.environ.get("APT_PIDS_COMPAT_BUILD_ROOT")
    if not allowed_text:
        raise CompatibilityBuildError("APT_PIDS_COMPAT_BUILD_ROOT is required")
    allowed_root = Path(allowed_text).resolve()
    if not allowed_root.is_dir() or output_root.parent != allowed_root:
        raise CompatibilityBuildError("output must be a direct child of the approved build root")
    if output_root.exists():
        raise CompatibilityBuildError("compatibility output already exists")
    if git_marker_commit(source_root) != PINNED_COMMIT:
        raise CompatibilityBuildError("PIDSMaker source commit mismatch")

    patch_root = project_root / PATCH_SET
    series_path = patch_root / "series"
    patch_names = tuple(
        line.strip()
        for line in series_path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not patch_names or len(patch_names) != len(set(patch_names)):
        raise CompatibilityBuildError("patch series must be nonempty and unique")
    patch_paths = tuple((patch_root / name).resolve() for name in patch_names)
    if any(path.parent != patch_root.resolve() or not path.is_file() for path in patch_paths):
        raise CompatibilityBuildError("patch series path escaped or is missing")

    shutil.copytree(
        source_root,
        output_root,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".DS_Store"),
    )
    applied: list[dict[str, str]] = []
    for name, path in zip(patch_names, patch_paths):
        completed = subprocess.run(
            ("patch", "--batch", "--forward", "-p1", "-i", str(path)),
            cwd=output_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            (output_root / "BUILD_FAILED.txt").write_text(
                f"patch_failed={name}\nuse_a_new_output_id_after_review=true\n"
            )
            raise CompatibilityBuildError(f"patch failed: {name}")
        applied.append({"name": name, "sha256": sha256_file(path)})

    series_hash = hashlib.sha256(
        "".join(item["name"] + item["sha256"] for item in applied).encode()
    ).hexdigest()
    main_commit = subprocess.run(
        ("git", "-C", str(project_root), "rev-parse", "HEAD"),
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    marker = {
        "schema_version": "apt-pidsmaker-compat-v1",
        "upstream_commit": PINNED_COMMIT,
        "main_project_commit": main_commit,
        "patch_series_hash": series_hash,
        "patches": applied,
        "source_submodule_modified": False,
    }
    (output_root / ".apt-pidsmaker-compat.json").write_text(
        json.dumps(marker, indent=2, sort_keys=True) + "\n"
    )
    return marker


def main() -> None:
    args = parse_args()
    try:
        marker = build(
            Path(args.project_root), Path(args.source_root), Path(args.output_root)
        )
    except CompatibilityBuildError as exc:
        print(f"compatibility build rejected: {exc}")
        raise SystemExit(2) from None
    print(json.dumps(marker, sort_keys=True))


if __name__ == "__main__":
    main()
