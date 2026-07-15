"""Readable publication paths backed by content-addressed stage caches."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

UPSTREAM_REVISION = "32602734bc9f896be5fc0f03f0a185c967cd6624"
STAGES = (
    "construction",
    "transformation",
    "featurization",
    "feat_inference",
    "batching",
    "training",
)
STAGE_CODE_VERSIONS = {
    "construction": "1",
    "transformation": "1",
    "featurization": "1",
    "feat_inference": "2",
    "batching": "2",
    "training": "3",
}


def plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): plain(item)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if hasattr(value, "items"):
        return plain(dict(value))
    if isinstance(value, Path):
        return str(value)
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def adapter_revision() -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


@contextmanager
def stage_lock(stage_path: Path) -> Iterator[None]:
    stage_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = stage_path.with_suffix(".lock")
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def stage_signatures(cfg: Any, scoring: str) -> dict[str, dict[str, Any]]:
    dataset = {
        "name": cfg.dataset.name,
        "database": cfg.dataset.database,
        "train_dates": list(cfg.dataset.train_dates),
        "val_dates": list(cfg.dataset.val_dates),
        "test_dates": list(cfg.dataset.test_dates),
    }
    sections = {
        "construction": plain(cfg.construction),
        "transformation": plain(cfg.transformation),
        "featurization": plain(cfg.featurization),
        "feat_inference": {
            "featurization": plain(cfg.featurization),
            "feat_inference": plain(cfg.feat_inference),
        },
        "batching": {
            "batching": plain(cfg.batching),
            "training_semantics": plain(cfg.training),
        },
        "training": {
            "training": plain(cfg.training),
            "scoring": scoring,
        },
    }
    result: dict[str, dict[str, Any]] = {}
    dependency_digest = ""
    code_revision = adapter_revision()
    for stage in STAGES:
        signature = {
            "schema_version": "stage_signature_v1",
            "stage": stage,
            "dataset": dataset,
            "configuration": sections[stage],
            "dependency_digest": dependency_digest,
            "upstream_revision": UPSTREAM_REVISION,
            "adapter_revision": code_revision,
            "stage_code_version": STAGE_CODE_VERSIONS[stage],
        }
        cache_identity = {
            key: value
            for key, value in signature.items()
            if key != "adapter_revision"
        }
        signature["digest"] = digest(cache_identity)
        result[stage] = signature
        dependency_digest = signature["digest"]
    return result


def configure_stage_paths(cfg: Any, cache_root: Path, signatures: dict[str, dict[str, Any]]) -> None:
    for stage in STAGES:
        stage_cfg = getattr(cfg, stage)
        stage_path = cache_root / stage / signatures[stage]["digest"][:20]
        stage_cfg._task_path = str(stage_path)
        stage_cfg._logs_dir = str(stage_path / "logs")

    construction = Path(cfg.construction._task_path)
    cfg.construction._graphs_dir = str(construction / "nx")
    cfg.construction._tw_labels = str(construction / "tw_labels")
    cfg.construction._node_id_to_path = str(construction / "node_id_to_path")
    cfg.construction._dicts_dir = str(construction / "indexid2msg")
    cfg.construction._magic_dir = str(construction / "magic")
    cfg.construction._magic_graphs_dir = str(construction / "magic" / "dgl_graphs")

    transformation = Path(cfg.transformation._task_path)
    cfg.transformation._graphs_dir = str(transformation / "nx")

    featurization = Path(cfg.featurization._task_path)
    cfg.featurization._model_dir = str(featurization / "stored_models")
    cfg.featurization.temporal_rw._random_walk_dir = str(featurization / "random_walks")
    cfg.featurization.temporal_rw._random_walk_corpus_dir = str(
        featurization / "random_walks" / "random_walk_corpus"
    )
    cfg.featurization.alacarte._random_walk_dir = str(featurization / "random_walks")
    cfg.featurization.alacarte._random_walk_corpus_dir = str(
        featurization / "random_walks" / "random_walk_corpus"
    )
    cfg.featurization.alacarte._vec_graphs_dir = str(featurization / "vectorized")

    feat_inference = Path(cfg.feat_inference._task_path)
    cfg.feat_inference._edge_embeds_dir = str(feat_inference / "edge_embeds")
    cfg.feat_inference._model_dir = str(feat_inference / "stored_models")

    batching = Path(cfg.batching._task_path)
    cfg.batching._preprocessed_graphs_dir = str(batching / "preprocessed_graphs")

    training = Path(cfg.training._task_path)
    cfg.training._trained_models_dir = str(training / "trained_models")
    cfg.training._edge_losses_dir = str(training / "node_scores")
    cfg.training._magic_dir = str(training / "magic")


def stage_complete(stage_path: Path, signature: dict[str, Any]) -> bool:
    manifest_path = stage_path / "stage_manifest.json"
    if not manifest_path.is_file():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    paths_exist = all(Path(path).exists() for path in manifest.get("artifact_paths", ()))
    return (
        manifest.get("status") == "complete"
        and manifest.get("signature", {}).get("digest") == signature["digest"]
        and paths_exist
    )


def write_stage_manifest(
    stage_path: Path,
    signature: dict[str, Any],
    *,
    status: str,
    started_at: str,
    runtime_seconds: float,
    error: str | None = None,
    artifact_paths: list[str] | None = None,
) -> None:
    atomic_json(
        stage_path / "stage_manifest.json",
        {
            "schema_version": "stage_manifest_v1",
            "status": status,
            "signature": signature,
            "started_at": started_at,
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "runtime_seconds": round(runtime_seconds, 6),
            "error": error,
            "artifact_paths": artifact_paths or [],
        },
    )
