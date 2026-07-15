"""Checkpoint preparation pipeline from construction through frozen publication."""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
import yaml

from pidsmaker_adapter.artifacts import (
    STAGES,
    UPSTREAM_REVISION,
    atomic_json,
    configure_stage_paths,
    file_sha256,
    plain,
    stage_complete,
    stage_lock,
    stage_signatures,
    write_stage_manifest,
)
from pidsmaker_adapter.configuration import (
    ConfigurationSpace,
    LegalConfiguration,
    checkpoint_slug,
    resolve_runtime_config,
)
from pidsmaker_adapter.inference import (
    calibrate_thresholds,
    result_envelope,
    run_split_inference,
)
from pidsmaker_adapter.training import train_and_select
from pidsmaker_adapter.upstream.factory import build_model
from pidsmaker_adapter.upstream.tasks import (
    batching,
    construction,
    feat_inference,
    featurization,
    transformation,
)
from pidsmaker_adapter.upstream.tasks.batching import get_preprocessed_graphs
from pidsmaker_adapter.upstream.utils.data_utils import load_model
from pidsmaker_adapter.upstream.utils.utils import get_device


def _run_cached_stage(
    *,
    stage: str,
    cfg: Any,
    signature: dict[str, Any],
    run: Callable[[], None],
    artifact_paths: Callable[[], list[str]],
) -> str:
    stage_path = Path(getattr(cfg, stage)._task_path)
    with stage_lock(stage_path):
        if stage_complete(stage_path, signature):
            return "hit"
        stage_path.mkdir(parents=True, exist_ok=True)
        started_wall = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        try:
            run()
            outputs = artifact_paths()
            if not outputs or not all(Path(path).exists() for path in outputs):
                raise RuntimeError(f"{stage} did not produce its declared artifacts")
            write_stage_manifest(
                stage_path,
                signature,
                status="complete",
                started_at=started_wall,
                runtime_seconds=time.perf_counter() - started,
                artifact_paths=outputs,
            )
            return "miss"
        except Exception as exc:
            write_stage_manifest(
                stage_path,
                signature,
                status="failed",
                started_at=started_wall,
                runtime_seconds=time.perf_counter() - started,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise


def _threshold_summary(scores: list[float], thresholds: dict[str, float]) -> dict[str, Any]:
    array = np.asarray(scores, dtype=np.float64)
    return {
        key: {
            "resolved_threshold": float(value),
            "count": int((array >= value).sum()),
            "rate": 0.0 if array.size == 0 else float((array >= value).mean()),
        }
        for key, value in thresholds.items()
    }


def _resolved_semantics(cfg: Any, legal: LegalConfiguration, space: ConfigurationSpace):
    return {
        "schema_version": "resolved_detector_configuration_v1",
        "configuration_space_version": space.schema_version,
        "dataset": cfg.dataset.name,
        "pids": legal.pids,
        "configuration_id": legal.config_id,
        "construction": {
            "method": cfg.construction.used_method,
            "time_window_size_minutes": cfg.construction.time_window_size,
            "fuse_edge": cfg.construction.fuse_edge,
            "node_label_features": plain(cfg.construction.node_label_features),
        },
        "transformation": plain(cfg.transformation),
        "featurization": plain(cfg.featurization),
        "batching": plain(cfg.batching),
        "training": plain(cfg.training),
        "scoring": {
            "node_aggregation": legal.scoring,
            "scope": "per_15_minute_graph",
        },
        "temporal_state": {
            "initialization": "reset_at_split_start",
            "stream_order": "timestamp_ascending",
        },
        "threshold": {
            "method": "validation_quantile",
            "allowed_quantiles": list(space.threshold_quantiles),
        },
        "reproducibility": {"seed": space.seed},
    }


def _load_cached_model(cfg: Any):
    train_data, val_data, test_data, max_node_num = get_preprocessed_graphs(cfg)
    model = build_model(
        data_sample=train_data[0][0],
        device=get_device(cfg),
        cfg=cfg,
        max_node_num=max_node_num,
    )
    model = load_model(
        model,
        str(Path(cfg.training._trained_models_dir) / "final"),
        cfg,
        map_location=get_device(cfg),
    )
    summary = json.loads(
        (Path(cfg.training._task_path) / "training_summary.json").read_text(encoding="utf-8")
    )
    return model, summary, train_data, val_data, test_data


def _update_registry(dataset_root: Path, entry: dict[str, Any]) -> None:
    registry_path = dataset_root / "configuration_registry.json"
    lock_path = dataset_root / ".configuration_registry"
    with stage_lock(lock_path):
        if registry_path.exists():
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        else:
            registry = {
                "schema_version": "detector_configuration_registry_v1",
                "dataset": entry["dataset"],
                "configurations": [],
            }
        registry["configurations"] = [
            item
            for item in registry["configurations"]
            if item["checkpoint_id"] != entry["checkpoint_id"]
        ]
        registry["configurations"].append(entry)
        registry["configurations"].sort(key=lambda item: item["checkpoint_id"])
        atomic_json(registry_path, registry)


def prepare_checkpoint(
    *,
    legal: LegalConfiguration,
    space: ConfigurationSpace,
    output_root: Path,
    database: dict[str, str],
    command: list[str] | None = None,
) -> Path:
    output_root = output_root.resolve()
    dataset_root = output_root / space.dataset
    cache_root = output_root / "stage-cache"
    cfg = resolve_runtime_config(legal, space, cache_root, database)
    signatures = stage_signatures(cfg, legal.scoring)
    configure_stage_paths(cfg, cache_root, signatures)

    slug = checkpoint_slug(legal)
    checkpoint_id = f"{legal.pids}_{slug.removeprefix('checkpoint_')}"
    checkpoint_dir = dataset_root / legal.pids / slug
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    cache_status: dict[str, str] = {}

    cache_status["construction"] = _run_cached_stage(
        stage="construction",
        cfg=cfg,
        signature=signatures["construction"],
        run=lambda: construction.main(cfg),
        artifact_paths=lambda: [cfg.construction._graphs_dir, cfg.construction._dicts_dir],
    )

    if cfg.transformation.used_methods.strip() == "none":
        cfg.transformation._graphs_dir = cfg.construction._graphs_dir
        cache_status["transformation"] = _run_cached_stage(
            stage="transformation",
            cfg=cfg,
            signature=signatures["transformation"],
            run=lambda: None,
            artifact_paths=lambda: [cfg.transformation._graphs_dir],
        )
    else:
        cache_status["transformation"] = _run_cached_stage(
            stage="transformation",
            cfg=cfg,
            signature=signatures["transformation"],
            run=lambda: transformation.main(cfg),
            artifact_paths=lambda: [cfg.transformation._graphs_dir],
        )

    cache_status["featurization"] = _run_cached_stage(
        stage="featurization",
        cfg=cfg,
        signature=signatures["featurization"],
        run=lambda: featurization.main(cfg),
        artifact_paths=lambda: [cfg.featurization._task_path],
    )
    cache_status["feat_inference"] = _run_cached_stage(
        stage="feat_inference",
        cfg=cfg,
        signature=signatures["feat_inference"],
        run=lambda: feat_inference.main(cfg),
        artifact_paths=lambda: [cfg.feat_inference._edge_embeds_dir],
    )
    cache_status["batching"] = _run_cached_stage(
        stage="batching",
        cfg=cfg,
        signature=signatures["batching"],
        run=lambda: batching.main(cfg),
        artifact_paths=lambda: [
            str(Path(cfg.batching._preprocessed_graphs_dir) / "torch_graphs.pkl")
        ],
    )

    training_path = Path(cfg.training._task_path)
    with stage_lock(training_path):
        if stage_complete(training_path, signatures["training"]):
            cache_status["training"] = "hit"
            model, training_summary, train_data, val_data, test_data = _load_cached_model(cfg)
        else:
            cache_status["training"] = "miss"
            training_path.mkdir(parents=True, exist_ok=True)
            started_wall = datetime.now(timezone.utc).isoformat()
            started = time.perf_counter()
            try:
                (
                    model,
                    training_summary,
                    train_data,
                    val_data,
                    test_data,
                    _,
                ) = train_and_select(cfg)
                atomic_json(training_path / "training_summary.json", training_summary)
                write_stage_manifest(
                    training_path,
                    signatures["training"],
                    status="complete",
                    started_at=started_wall,
                    runtime_seconds=time.perf_counter() - started,
                    artifact_paths=[
                        str(Path(cfg.training._trained_models_dir) / "final" / "state_dict.pkl"),
                        str(training_path / "training_summary.json"),
                    ],
                )
            except Exception as exc:
                write_stage_manifest(
                    training_path,
                    signatures["training"],
                    status="failed",
                    started_at=started_wall,
                    runtime_seconds=time.perf_counter() - started,
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise

    inference_root = checkpoint_dir / "inference"
    val_metrics = run_split_inference(
        cfg=cfg,
        model=model,
        data_groups=val_data,
        split="val",
        scoring=legal.scoring,
        output_dir=inference_root / "val",
    )
    thresholds_path = checkpoint_dir / "thresholds.json"
    thresholds = calibrate_thresholds(
        val_metrics["_scores"],
        space.threshold_quantiles,
        thresholds_path,
        scoring=legal.scoring,
    )
    val_metrics["alerts_by_threshold"] = _threshold_summary(val_metrics["_scores"], thresholds)
    train_metrics = run_split_inference(
        cfg=cfg,
        model=model,
        data_groups=train_data,
        split="train",
        scoring=legal.scoring,
        output_dir=inference_root / "train",
        threshold_values=thresholds,
    )
    train_metrics["loss"]["training_history"] = training_summary["history"]
    test_metrics = run_split_inference(
        cfg=cfg,
        model=model,
        data_groups=test_data,
        split="test",
        scoring=legal.scoring,
        output_dir=inference_root / "test",
        threshold_values=thresholds,
    )

    resolved = _resolved_semantics(cfg, legal, space)
    resolved_path = checkpoint_dir / "resolved_config.yaml"
    resolved_path.write_text(
        yaml.safe_dump(resolved, sort_keys=True, allow_unicode=True),
        encoding="utf-8",
    )
    source_model_dir = Path(cfg.training._trained_models_dir) / "final"
    published_model_dir = checkpoint_dir / "model"
    published_model_dir.mkdir(parents=True, exist_ok=True)
    for source in source_model_dir.iterdir():
        if source.is_file():
            shutil.copy2(source, published_model_dir / source.name)
    state_dict_path = published_model_dir / "state_dict.pkl"

    for split, metrics in (
        ("train", train_metrics),
        ("val", val_metrics),
        ("test", test_metrics),
    ):
        atomic_json(
            checkpoint_dir / f"{split}_result.json",
            result_envelope(
                cfg=cfg,
                pids=legal.pids,
                checkpoint_id=checkpoint_id,
                split=split,
                metrics=metrics,
            ),
        )

    manifest = {
        "schema_version": "checkpoint_manifest_v1",
        "checkpoint_id": checkpoint_id,
        "pids": legal.pids,
        "dataset": cfg.dataset.name,
        "configuration_id": legal.config_id,
        "configuration_space_version": space.schema_version,
        "checkpoint_path": str(checkpoint_dir),
        "checkpoint_hash": file_sha256(state_dict_path),
        "trained_on": "train",
        "selected_on": "val",
        "selected_epoch": training_summary["selection"]["selected_epoch"],
        "seed": space.seed,
        "upstream": {
            "revision": UPSTREAM_REVISION,
            "source_path": "PIDSMaker/pidsmaker",
        },
        "stage_digests": {stage: signatures[stage]["digest"] for stage in STAGES},
        "cache_status": cache_status,
        "threshold_artifact": str(thresholds_path),
        "resolved_config": str(resolved_path),
        "command": command or sys.argv,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "agent_initialization_artifacts": [
            str(checkpoint_dir / "train_result.json"),
            str(checkpoint_dir / "val_result.json"),
            str(thresholds_path),
        ],
        "excluded_from_agent_initialization": [
            str(checkpoint_dir / "test_result.json"),
        ],
    }
    atomic_json(checkpoint_dir / "manifest.json", manifest)
    _update_registry(
        dataset_root,
        {
            "checkpoint_id": checkpoint_id,
            "dataset": cfg.dataset.name,
            "pids": legal.pids,
            "configuration_id": legal.config_id,
            "path": str(checkpoint_dir),
            "checkpoint_hash": manifest["checkpoint_hash"],
            "scoring": resolved["scoring"],
            "threshold_options": json.loads(thresholds_path.read_text(encoding="utf-8"))[
                "options"
            ],
            "agent_initialization_artifacts": manifest["agent_initialization_artifacts"],
        },
    )
    return checkpoint_dir
