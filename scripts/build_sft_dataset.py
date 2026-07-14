#!/usr/bin/env python3
"""Sanitize private teacher JSONL into a versioned student SFT dataset.

Requirements: REQ-SFT-001..004, REQ-LABEL-002..004, REQ-REPRO-001..002.
"""

from __future__ import annotations

import argparse
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from apt_detection_agent.sft.builder import build_dataset
from apt_detection_agent.sft.teacher import HiddenTeacherRecord


def _under(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--teacher-jsonl", type=Path, required=True)
    parser.add_argument("--student-dataset", type=Path, required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--validation-teacher-id", action="append", default=[])
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--synthetic-only", action="store_true")
    parser.add_argument("--formal-training-approved", action="store_true")
    args = parser.parse_args()

    teacher_root_text = os.environ.get("HIDDEN_TEACHER_INPUT_ROOT")
    student_root_text = os.environ.get("SFT_STUDENT_OUTPUT_ROOT")
    if not teacher_root_text or not student_root_text:
        raise ValueError("teacher and student roots require explicit environment injection")
    teacher_root = Path(teacher_root_text).resolve()
    student_root = Path(student_root_text).resolve()
    if teacher_root == student_root or teacher_root.is_relative_to(student_root):
        raise ValueError("private teacher root cannot be inside student output root")
    if not _under(args.teacher_jsonl, teacher_root):
        raise ValueError("teacher input escaped private root")
    if not _under(args.student_dataset, student_root):
        raise ValueError("student dataset escaped output root")
    if args.student_dataset.exists():
        raise FileExistsError(args.student_dataset)

    records = tuple(
        HiddenTeacherRecord.model_validate_json(line)
        for line in args.teacher_jsonl.read_text().splitlines()
        if line.strip()
    )
    commit = subprocess.run(
        ("git", "-C", str(args.project_root.resolve()), "rev-parse", "HEAD"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dataset = build_dataset(
        records=records,
        validation_teacher_record_ids=frozenset(args.validation_teacher_id),
        dataset_id=args.dataset_id,
        dataset_version=args.dataset_version,
        code_commit=commit,
        created_at=datetime.now(timezone.utc),
        synthetic_only=args.synthetic_only,
        formal_training_approved=args.formal_training_approved,
    )
    args.student_dataset.parent.mkdir(parents=True, exist_ok=True)
    args.student_dataset.write_text(dataset.model_dump_json(indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
