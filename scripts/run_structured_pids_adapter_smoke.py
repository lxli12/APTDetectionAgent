#!/usr/bin/env python3
"""Run one real structured adapter call against a frozen validation bundle.

Requirements: REQ-TOOL-001..005, REQ-ARTIFACT-001..003,
REQ-CAUSAL-001..004, REQ-LABEL-001..004, REQ-RESOURCE-001..003.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from apt_detection_agent.pidsmaker import (
    PIDSDetectionRequest,
    PIDSMakerAdapter,
)
from apt_detection_agent.tools.pids import ApprovedConfigCatalog
from apt_detection_agent.schemas import DataSplit, PIDSRef, TimeWindow


DATABASE_KEYS = ("PIDS_DB_HOST", "PIDS_DB_USER", "PIDS_DB_PORT")


def database_environment() -> dict[str, str]:
    missing = [key for key in DATABASE_KEYS if not os.environ.get(key)]
    if missing:
        raise ValueError("PIDS worker database environment is incomplete")
    secret_text = os.environ.get("APT_PIDS_DB_SECRET_FILE")
    if not secret_text:
        raise ValueError("executor-owned PIDS database secret file is required")
    secret = Path(secret_text).resolve()
    stat = secret.stat()
    if stat.st_mode & 0o007 or not secret.is_file() or secret.is_symlink():
        raise ValueError("PIDS database secret file permissions are unsafe")
    password = ""
    for line in secret.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator and key == "PIDS_WORKER_PASSWORD":
            password = value
    if len(password) != 64 or any(char not in "0123456789abcdef" for char in password):
        raise ValueError("PIDS worker database secret is malformed")
    return {
        **{key: os.environ[key] for key in DATABASE_KEYS},
        "PIDS_DB_PASSWORD": password,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--compatibility-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--nltk-data-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--window-start-ns", type=int, required=True)
    parser.add_argument("--window-end-ns", type=int, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9a-f]{40}", args.code_commit):
        raise ValueError("code commit must be an exact Git SHA")

    database = database_environment()
    bundle = args.bundle.resolve()
    availability = json.loads((bundle / "availability_manifest.json").read_text())
    catalog = ApprovedConfigCatalog.from_json(bundle / "approved_config_catalog.json")
    config_id = json.loads((bundle / "approved_config_catalog.json").read_text())[0][
        "config_id"
    ]
    pids = PIDSRef(
        pids_id=availability["pids_id"],
        variant_id=availability["variant_id"],
    )
    config = catalog.select(
        config_id=config_id,
        pids=pids,
        dataset_id=availability["dataset_id"],
        split=DataSplit.VALIDATION,
    )
    zone = ZoneInfo("America/New_York")
    start = datetime.fromtimestamp(args.window_start_ns / 1_000_000_000, zone)
    end = datetime.fromtimestamp(args.window_end_ns / 1_000_000_000, zone)
    origin = start.replace(hour=0, minute=0, second=0, microsecond=0)
    size = int((end - start).total_seconds())
    sequence = int((start - origin).total_seconds()) // size
    window_id = f"{availability['dataset_id'].lower()}-{args.window_start_ns}"
    window = TimeWindow(
        window_id=window_id,
        sequence_number=sequence,
        origin_time=origin,
        timezone="America/New_York",
        window_size_seconds=size,
        start=start,
        end=end,
    )
    request = PIDSDetectionRequest(
        request_id=f"request-{args.run_id}",
        tool_call_id=f"tool-{args.run_id}",
        case_id=f"case-{args.run_id}",
        scenario_id="cadets-e3-validation",
        episode_id=f"episode-{args.run_id}",
        window_id=window_id,
        window=window,
        split=DataSplit.VALIDATION,
        run_id=args.run_id,
        pids=pids,
        source_config_id=availability["source_config_id"],
        dataset_id=availability["dataset_id"],
        approved_config=config,
        timeout_seconds=1800,
    )
    adapter = PIDSMakerAdapter(
        args.project_root,
        args.artifact_root,
        Path(sys.executable),
        cuda_visible_devices="1",
        cpu_thread_limit=16,
        execution_enabled=True,
        compatibility_root=args.compatibility_root,
        frozen_bundle_root=bundle.parent,
        approved_bundles={config.config_id: bundle},
        database_environment=database,
        nltk_data_root=args.nltk_data_root,
        code_commit=args.code_commit,
    )
    outcome = adapter.execute(request)
    print(
        json.dumps(
            {
                "run_id": args.run_id,
                "status": outcome.tool_result.status.value,
                "tool_call_id": outcome.tool_result.tool_call_id,
                "approved_config_id": outcome.tool_result.approved_config_id,
                "checkpoint_hash": outcome.tool_result.checkpoint_hash,
                "standardized_observation": outcome.tool_result.standardized_observation,
                "stage_count": len(outcome.tool_result.stage_trace),
            },
            sort_keys=True,
        )
    )
    return 0 if outcome.tool_result.status.value == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
