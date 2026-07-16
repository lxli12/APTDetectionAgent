"""Checkpoint preparation pipeline from construction through frozen publication."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
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
from pidsmaker_adapter.resources import ResourceMonitor, historical_partial_resource_usage
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


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _environment_snapshot(output_root: Path) -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    visible_gpu_names = [
        torch.cuda.get_device_name(index)
        for index in range(torch.cuda.device_count())
    ]
    disk = shutil.disk_usage(output_root)
    return {
        "adapter_revision": revision,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "visible_gpu_names": visible_gpu_names,
        "cgroup": {
            "cpu_max": _read_text(Path("/sys/fs/cgroup/cpu.max")),
            "memory_max": _read_text(Path("/sys/fs/cgroup/memory.max")),
        },
        "output_disk": {
            "total_bytes": disk.total,
            "free_bytes": disk.free,
        },
    }


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


def _cache_reuse_frontier(cfg: Any, signatures: dict[str, dict[str, Any]]) -> str | None:
    """Find the deepest reusable preprocessing stage in the dependency chain."""
    frontier = None
    for stage in STAGES[:-1]:
        stage_path = Path(getattr(cfg, stage)._task_path)
        if stage_complete(stage_path, signatures[stage]):
            frontier = stage
    return frontier


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


def _published_checkpoint_manifest(
    checkpoint_dir: Path,
    *,
    checkpoint_id: str,
    legal: LegalConfiguration,
    space: ConfigurationSpace,
) -> dict[str, Any] | None:
    manifest_path = checkpoint_dir / "manifest.json"
    state_dict_path = checkpoint_dir / "model" / "state_dict.pkl"
    required = [
        manifest_path,
        state_dict_path,
        checkpoint_dir / "resolved_config.yaml",
        checkpoint_dir / "thresholds.json",
        *(checkpoint_dir / f"{split}_result.json" for split in ("train", "val", "test")),
    ]
    if not all(path.is_file() for path in required):
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        resolved = yaml.safe_load(
            (checkpoint_dir / "resolved_config.yaml").read_text(encoding="utf-8")
        )
        thresholds = json.loads(
            (checkpoint_dir / "thresholds.json").read_text(encoding="utf-8")
        )
        results = {
            split: json.loads(
                (checkpoint_dir / f"{split}_result.json").read_text(encoding="utf-8")
            )
            for split in ("train", "val", "test")
        }
    except (OSError, json.JSONDecodeError, yaml.YAMLError):
        return None
    if not (
        manifest.get("schema_version") == "checkpoint_manifest_v1"
        and manifest.get("checkpoint_id") == checkpoint_id
        and manifest.get("configuration_id") == legal.config_id
        and manifest.get("pids") == legal.pids
        and manifest.get("dataset") == space.dataset
        and manifest.get("configuration_space_version") == space.schema_version
        and manifest.get("checkpoint_hash") == file_sha256(state_dict_path)
        and isinstance(manifest.get("agent_initialization_artifacts"), list)
        and isinstance(resolved, dict)
        and "scoring" in resolved
        and isinstance(thresholds, dict)
        and "options" in thresholds
    ):
        return None
    expected_result_keys = set(results["train"])
    for split, result in results.items():
        if not (
            set(result) == expected_result_keys
            and result.get("schema_version") == "checkpoint_split_result_v1"
            and result.get("checkpoint_id") == checkpoint_id
            and result.get("split") == split
            and result.get("privileged_metrics") is None
            and result.get("visibility", {}).get("labels_used") is False
        ):
            return None
    return manifest


def _resource_usage_document(
    *,
    usage: dict[str, Any],
    checkpoint_id: str,
    legal: LegalConfiguration,
    space: ConfigurationSpace,
    cache_status: dict[str, str],
) -> dict[str, Any]:
    return {
        "schema_version": "checkpoint_resource_usage_v1",
        "dataset": space.dataset,
        "pids": legal.pids,
        "configuration_id": legal.config_id,
        "checkpoint_id": checkpoint_id,
        "stage_cache_status": cache_status,
        **usage,
    }


def _ensure_historical_resource_artifact(
    checkpoint_dir: Path,
    manifest: dict[str, Any],
    *,
    checkpoint_id: str,
    legal: LegalConfiguration,
    space: ConfigurationSpace,
) -> dict[str, Any]:
    resource_path = checkpoint_dir / "train_val_resource_usage.json"
    if not resource_path.is_file():
        results = {
            split: json.loads(
                (checkpoint_dir / f"{split}_result.json").read_text(encoding="utf-8")
            )
            for split in ("train", "val")
        }
        atomic_json(
            resource_path,
            _resource_usage_document(
                usage=historical_partial_resource_usage(results),
                checkpoint_id=checkpoint_id,
                legal=legal,
                space=space,
                cache_status=manifest.get("cache_status", {}),
            ),
        )
    resource_ref = str(resource_path)
    manifest["resource_usage_artifact"] = resource_ref
    initialization_artifacts = manifest.setdefault("agent_initialization_artifacts", [])
    if resource_ref not in initialization_artifacts:
        initialization_artifacts.append(resource_ref)
    atomic_json(checkpoint_dir / "manifest.json", manifest)
    return manifest


def prepare_checkpoint(
    *,
    legal: LegalConfiguration,
    space: ConfigurationSpace,
    output_root: Path,
    database: dict[str, str],
    command: list[str] | None = None,
) -> Path:
    output_root = output_root.resolve()
    required_root = Path(
        "/root/autodl-tmp/apt-detection-agent/pidsmaker-output"
    ).resolve()
    if output_root != required_root and required_root not in output_root.parents:
        raise ValueError(f"Checkpoint outputs must remain under {required_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    dataset_root = output_root / space.dataset
    slug = checkpoint_slug(legal)
    checkpoint_id = f"{legal.pids}_{slug.removeprefix('checkpoint_')}"
    checkpoint_dir = dataset_root / legal.pids / slug
    existing_manifest = _published_checkpoint_manifest(
        checkpoint_dir,
        checkpoint_id=checkpoint_id,
        legal=legal,
        space=space,
    )
    if existing_manifest is not None:
        existing_manifest = _ensure_historical_resource_artifact(
            checkpoint_dir,
            existing_manifest,
            checkpoint_id=checkpoint_id,
            legal=legal,
            space=space,
        )
        resolved = yaml.safe_load(
            (checkpoint_dir / "resolved_config.yaml").read_text(encoding="utf-8")
        )
        thresholds = json.loads(
            (checkpoint_dir / "thresholds.json").read_text(encoding="utf-8")
        )
        _update_registry(
            dataset_root,
            {
                "checkpoint_id": checkpoint_id,
                "dataset": space.dataset,
                "pids": legal.pids,
                "configuration_id": legal.config_id,
                "path": str(checkpoint_dir),
                "checkpoint_hash": existing_manifest["checkpoint_hash"],
                "scoring": resolved["scoring"],
                "threshold_options": thresholds["options"],
                "agent_initialization_artifacts": existing_manifest[
                    "agent_initialization_artifacts"
                ],
            },
        )
        return checkpoint_dir
    cache_root = output_root / "stage-cache"
    cfg = resolve_runtime_config(legal, space, cache_root, database)
    signatures = stage_signatures(cfg, legal.scoring)
    configure_stage_paths(cfg, cache_root, signatures)
    frontier = _cache_reuse_frontier(cfg, signatures)

    minimum_free_gib = int(os.environ.get("PIDS_MIN_FREE_GIB", "50"))
    low_write_reuse = frontier == "batching" or (
        frontier == "feat_inference" and not cfg.batching.save_on_disk
    )
    if low_write_reuse:
        minimum_free_gib = min(minimum_free_gib, 10)
    free_bytes = shutil.disk_usage(output_root).free
    if free_bytes < minimum_free_gib * 1024**3:
        raise RuntimeError(
            f"Refusing checkpoint preparation with less than {minimum_free_gib} GiB free "
            f"on {output_root}"
        )
    resource_monitor = ResourceMonitor()
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    cache_status: dict[str, str] = {}
    frontier_index = -1 if frontier is None else STAGES.index(frontier)

    def execute_stage(
        stage: str,
        run: Callable[[], None],
        artifact_paths: Callable[[], list[str]],
    ) -> str:
        if STAGES.index(stage) < frontier_index:
            return f"reused_by_{frontier}"
        return _run_cached_stage(
            stage=stage,
            cfg=cfg,
            signature=signatures[stage],
            run=run,
            artifact_paths=artifact_paths,
        )

    cache_status["construction"] = execute_stage(
        stage="construction",
        run=lambda: construction.main(cfg),
        artifact_paths=lambda: [cfg.construction._graphs_dir, cfg.construction._dicts_dir],
    )

    if cfg.transformation.used_methods.strip() == "none":
        cfg.transformation._graphs_dir = cfg.construction._graphs_dir
        cache_status["transformation"] = execute_stage(
            stage="transformation",
            run=lambda: None,
            artifact_paths=lambda: [cfg.transformation._graphs_dir],
        )
    else:
        cache_status["transformation"] = execute_stage(
            stage="transformation",
            run=lambda: transformation.main(cfg),
            artifact_paths=lambda: [cfg.transformation._graphs_dir],
        )

    cache_status["featurization"] = execute_stage(
        stage="featurization",
        run=lambda: featurization.main(cfg),
        artifact_paths=lambda: [cfg.featurization._task_path],
    )
    cache_status["feat_inference"] = execute_stage(
        stage="feat_inference",
        run=lambda: feat_inference.main(cfg),
        artifact_paths=lambda: [cfg.feat_inference._edge_embeds_dir],
    )
    cache_status["batching"] = execute_stage(
        stage="batching",
        run=lambda: batching.main(cfg),
        artifact_paths=lambda: (
            [str(Path(cfg.batching._preprocessed_graphs_dir) / "torch_graphs.pkl")]
            if cfg.batching.save_on_disk
            else [cfg.batching._task_path]
        ),
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
    resource_path = checkpoint_dir / "train_val_resource_usage.json"
    atomic_json(
        resource_path,
        _resource_usage_document(
            usage=resource_monitor.finish(),
            checkpoint_id=checkpoint_id,
            legal=legal,
            space=space,
            cache_status=cache_status,
        ),
    )
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
        "resource_usage_artifact": str(resource_path),
        "resolved_config": str(resolved_path),
        "command": command or sys.argv,
        "environment": _environment_snapshot(output_root),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "agent_initialization_artifacts": [
            str(checkpoint_dir / "train_result.json"),
            str(checkpoint_dir / "val_result.json"),
            str(thresholds_path),
            str(resource_path),
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
