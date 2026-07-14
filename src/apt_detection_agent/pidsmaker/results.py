"""Causal threshold calibration and raw PIDSMaker score standardization.

Requirements: REQ-CAUSAL-002, REQ-CONFIG-002..003, REQ-LABEL-001,
REQ-ARTIFACT-001..003.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from apt_detection_agent.schemas import (
    CalibrationMethod,
    DataSplit,
    DetectionUnit,
    EntityAnomalyScore,
    ExperimentClass,
    PIDSRef,
    StandardizedDetectionResult,
    ThresholdProvenance,
    ThresholdSourceSplit,
    TimeWindow,
    TransductiveStatus,
)


FORBIDDEN_SCORE_COLUMNS = frozenset(
    {"y", "label", "ground_truth", "campaign_id", "tp", "fp", "fn"}
)


def _json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, dict):
        raise ValueError(f"expected object in {path.name}")
    return payload


def _score_files(pipeline: Path, split: str) -> tuple[Path, ...]:
    files = tuple(sorted(pipeline.glob(f"training/training/*/*/edge_losses/{split}/*/*.csv")))
    if not files or any(f"/{split}/" not in path.as_posix() for path in files):
        raise ValueError(f"missing isolated {split} score artifacts")
    return files


def _rows(path: Path) -> tuple[dict[str, str], ...]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or ())
        required = {"loss", "srcnode", "dstnode", "time", "edge_type"}
        if not required.issubset(columns) or columns & FORBIDDEN_SCORE_COLUMNS:
            raise ValueError("raw score schema is missing fields or contains privileged labels")
        return tuple(reader)


def calibrate_validation_quantile(
    pids_run: Path, *, quantile: float, created_at: datetime | None = None
) -> ThresholdProvenance:
    if not 0.0 < quantile < 1.0 or not math.isfinite(quantile):
        raise ValueError("validation quantile must be finite and strictly between zero and one")
    run = pids_run.resolve()
    pipeline = run / "pids_artifacts" / "pipeline"
    checkpoint = _json(pipeline / "checkpoint_manifest.json")
    losses = sorted(float(row["loss"]) for path in _score_files(pipeline, "val") for row in _rows(path))
    if not losses or any(not math.isfinite(value) for value in losses):
        raise ValueError("validation scores must be nonempty and finite")
    rank = max(0, math.ceil(quantile * len(losses)) - 1)
    quantile_token = str(quantile).replace(".", "p")
    checkpoint_hash = str(checkpoint["checkpoint_hash"])
    return ThresholdProvenance(
        threshold_id=f"velox-cadets-val-q{quantile_token}-{checkpoint_hash[:12]}",
        value=losses[rank],
        calibration_method=CalibrationMethod.VALIDATION_QUANTILE,
        source_dataset=str(checkpoint["dataset_id"]),
        source_split=ThresholdSourceSplit.VALIDATION,
        checkpoint_hash=checkpoint_hash,
        target_metric=f"edge_loss_quantile_{quantile_token}",
        created_at=created_at or datetime.now(timezone.utc),
        code_commit=(run / "git_commit.txt").read_text().strip(),
    )


def standardize_frozen_test_scores(
    pids_run: Path,
    threshold: ThresholdProvenance,
    *,
    created_at: datetime | None = None,
    split: DataSplit = DataSplit.VALIDATION,
    pids: PIDSRef | None = None,
    window: TimeWindow | None = None,
    experiment_class: ExperimentClass = ExperimentClass.CAUSAL_MAIN,
    transductive_status: TransductiveStatus = TransductiveStatus.CAUSAL,
) -> StandardizedDetectionResult:
    run = pids_run.resolve()
    pipeline = run / "pids_artifacts" / "pipeline"
    checkpoint = _json(pipeline / "checkpoint_manifest.json")
    inference = _json(pipeline / "inference_stage_summary.json")
    resolved = _json(pipeline / "resolved_config.yaml")
    if threshold.checkpoint_hash != checkpoint.get("checkpoint_hash"):
        raise ValueError("frozen threshold does not match the inference checkpoint")
    test_window = resolved["split_windows"]["test"]
    start_ns = int(test_window["start_ns"])
    end_ns = int(test_window["end_ns"])
    zone = ZoneInfo(str(resolved["timezone"]))
    start = datetime.fromtimestamp(start_ns / 1_000_000_000, zone)
    end = datetime.fromtimestamp(end_ns / 1_000_000_000, zone)
    origin = start.replace(hour=0, minute=0, second=0, microsecond=0)
    sequence = int((start - origin).total_seconds()) // int(resolved["window_size_seconds"])
    if window is not None and (
        int(window.start.timestamp() * 1_000_000_000) != start_ns
        or int(window.end.timestamp() * 1_000_000_000) != end_ns
        or window.timezone != str(resolved["timezone"])
    ):
        raise ValueError("requested window does not match PIDSMaker score provenance")

    scores: dict[str, float] = {}
    evidence: dict[str, set[str]] = defaultdict(set)
    artifact_hashes: dict[str, str] = {}
    for path in _score_files(pipeline, "test"):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        artifact_id = f"raw-score-{digest[:16]}"
        artifact_hashes[artifact_id] = digest
        for row in _rows(path):
            score = float(row["loss"])
            event_time = int(row["time"])
            if not math.isfinite(score) or not start_ns <= event_time < end_ns:
                raise ValueError("test score is non-finite or outside the committed window")
            for column in ("srcnode", "dstnode"):
                entity_id = str(int(row[column]))
                scores[entity_id] = max(score, scores.get(entity_id, float("-inf")))
                evidence[entity_id].add(artifact_id)
    entities = tuple(
        EntityAnomalyScore(
            entity_id=entity_id,
            score=score,
            alerted=score >= threshold.value,
            detection_unit=DetectionUnit.NODE,
            evidence_artifact_ids=tuple(sorted(evidence[entity_id])),
        )
        for entity_id, score in sorted(scores.items(), key=lambda item: int(item[0]))
    )
    return StandardizedDetectionResult(
        result_id=f"{checkpoint['source_config_id']}-{checkpoint['checkpoint_hash'][:12]}",
        split=split,
        pids=pids or PIDSRef(pids_id="velox"),
        dataset_id=str(checkpoint["dataset_id"]),
        source_config_id=str(checkpoint["source_config_id"]),
        experiment_class=experiment_class,
        transductive_status=transductive_status,
        checkpoint_hash=str(checkpoint["checkpoint_hash"]),
        threshold=threshold,
        window=window
        or TimeWindow(
            window_id=f"{str(checkpoint['dataset_id']).lower()}-{start_ns}",
            sequence_number=sequence,
            origin_time=origin,
            timezone=str(resolved["timezone"]),
            window_size_seconds=int(resolved["window_size_seconds"]),
            start=start,
            end=end,
        ),
        score_semantics="maximum_incident_edge_reconstruction_loss",
        scored_entities=entities,
        raw_artifact_hashes=artifact_hashes,
        inference_elapsed_seconds=float(inference["elapsed_seconds"]),
        gpu_seconds=float(inference["elapsed_seconds"]),
        created_at=created_at or datetime.now(timezone.utc),
    )
