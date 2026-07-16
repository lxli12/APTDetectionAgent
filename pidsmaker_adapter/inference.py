"""Label-free, graph-local inference and validation threshold calibration."""

from __future__ import annotations

import json
import math
import os
import resource
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import torch

from pidsmaker_adapter.artifacts import atomic_json
from pidsmaker_adapter.upstream.utils.utils import get_device


def _iter_batches(data_groups: Iterable[Iterable[Any]]):
    for group in data_groups:
        for batch in group:
            yield batch


def _graph_id(batch: Any, window_minutes: int) -> str:
    window_ns = int(window_minutes * 60_000_000_000)
    start_ns = int(batch.t.min().item())
    return str(start_ns // window_ns)


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "std": None,
            "min": None,
            "max": None,
            "quantiles": {},
        }
    array = np.asarray(values, dtype=np.float64)
    quantiles = (0.5, 0.9, 0.95, 0.99)
    return {
        "count": int(array.size),
        "mean": float(array.mean()),
        "std": float(array.std()),
        "min": float(array.min()),
        "max": float(array.max()),
        "quantiles": {
            f"q{q:g}": float(np.quantile(array, q))
            for q in quantiles
        },
    }


def _resource_snapshot(device: torch.device) -> dict[str, Any]:
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB; macOS reports bytes. Remote experiments run on Linux.
    rss_gib = max_rss / (1024**2) if os.uname().sysname == "Linux" else max_rss / (1024**3)
    gpu_gib = None
    if device.type == "cuda":
        gpu_gib = torch.cuda.max_memory_allocated(device=device) / (1024**3)
    return {
        "peak_process_rss_gib": round(float(rss_gib), 6),
        "peak_cuda_allocated_gib": None if gpu_gib is None else round(float(gpu_gib), 6),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
    }


def _pids_node_scores(
    *,
    result: dict[str, Any],
    batch: Any,
    objective_loss: torch.Tensor,
    score_channel: str,
) -> torch.Tensor:
    """Return the fixed PIDS score channel, independently of its threshold."""
    if score_channel == "objective_loss":
        return objective_loss
    if score_channel not in {"flash_confidence", "threatrace_ratio"}:
        raise ValueError(f"Unsupported score channel {score_channel!r}")

    out = result.get("out")
    if out is None or out.ndim != 2:
        raise ValueError(f"{score_channel} requires node classifier outputs")
    detached = out.detach()
    probabilities = torch.softmax(detached, dim=1)
    predicted = probabilities.argmax(dim=1)
    expected = batch.node_type.argmax(dim=1)
    correct = predicted.eq(expected)

    if score_channel == "threatrace_ratio":
        top_two = probabilities.topk(k=2, dim=1).values
        score = torch.log(top_two[:, 0] / top_two[:, 1].clamp_min(1e-5) + 1e-12)
    else:
        # PIDSMaker's FLASH branch applies the confidence formula directly to
        # log-softmax outputs, which makes the intended positive confidence
        # negative. Use probabilities while retaining its normalization rule.
        top_two = probabilities.topk(k=2, dim=1).values
        confidence = (top_two[:, 0] - top_two[:, 1]) / (top_two[:, 0] + 1e-6)
        maximum = confidence.max()
        score = (confidence - confidence.min()) / maximum if maximum > 0 else confidence
    return torch.where(correct, score.clamp_min(0), torch.zeros_like(score))


@torch.no_grad()
def run_split_inference(
    *,
    cfg: Any,
    model: Any,
    data_groups: Iterable[Iterable[Any]],
    split: str,
    scoring: str,
    score_channel: str,
    output_dir: Path,
    threshold_values: dict[str, float] | None = None,
) -> dict[str, Any]:
    if split not in {"train", "val", "test"}:
        raise ValueError(f"Invalid split {split!r}")
    if scoring not in {"direct_node_loss", "max_incident_edge_loss"}:
        raise ValueError(f"Invalid scoring rule {scoring!r}")

    device = get_device(cfg)
    model.to_device(device)
    model.reset_state()
    model.eval()

    graph_scores: dict[str, dict[int, float]] = defaultdict(dict)
    losses: list[float] = []
    edge_count = 0
    started = time.perf_counter()

    for batch in _iter_batches(data_groups):
        batch.to(device=device)
        result = model(batch, inference=True, validation=(split == "val"))
        loss = result["loss"].detach().reshape(-1).float().cpu()
        score_tensor = _pids_node_scores(
            result=result,
            batch=batch,
            objective_loss=loss,
            score_channel=score_channel,
        ).detach().reshape(-1).float().cpu()
        batch_losses = score_tensor.tolist()
        losses.extend(float(value) for value in loss.tolist())
        graph_id = _graph_id(batch, int(cfg.construction.time_window_size))

        if scoring == "max_incident_edge_loss":
            if loss.numel() != batch.original_edge_index.shape[1]:
                raise ValueError("Edge scoring requires one loss per original edge")
            edge_index = batch.original_edge_index.detach().cpu()
            for index, score in enumerate(batch_losses):
                src = int(edge_index[0, index].item())
                dst = int(edge_index[1, index].item())
                graph_scores[graph_id][src] = max(graph_scores[graph_id].get(src, -math.inf), score)
                graph_scores[graph_id][dst] = max(graph_scores[graph_id].get(dst, -math.inf), score)
            edge_count += int(edge_index.shape[1])
        else:
            node_ids = getattr(batch, "original_n_id_tgn", None)
            if node_ids is None:
                node_ids = getattr(batch, "original_n_id", None)
            if node_ids is None or loss.numel() != node_ids.numel():
                raise ValueError("Node scoring requires one loss per original node")
            for node_id, score in zip(node_ids.detach().cpu().tolist(), batch_losses):
                node_id = int(node_id)
                graph_scores[graph_id][node_id] = max(
                    graph_scores[graph_id].get(node_id, -math.inf),
                    score,
                )
            edge_count += int(batch.edge_index.shape[1])

        batch.to("cpu")
        if device.type == "cuda":
            torch.cuda.empty_cache()

    runtime_seconds = time.perf_counter() - started
    output_dir.mkdir(parents=True, exist_ok=True)
    scores_path = output_dir / "node_scores.jsonl"
    all_scores: list[float] = []
    alert_counts = {key: 0 for key in (threshold_values or {})}
    node_observations = 0
    with scores_path.open("w", encoding="utf-8") as handle:
        for graph_id in sorted(graph_scores, key=int):
            for node_id, score in sorted(graph_scores[graph_id].items()):
                record = {
                    "scenario_id": cfg.dataset.name,
                    "graph_id": graph_id,
                    "node_id": node_id,
                    "node_score": float(score),
                    "score_channel": score_channel,
                }
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                all_scores.append(float(score))
                node_observations += 1
                for key, threshold in (threshold_values or {}).items():
                    alert_counts[key] += int(score >= threshold)

    return {
        "loss": {
            "definition": "mean detector objective loss over inference outputs",
            "value": None if not losses else float(np.mean(losses)),
            "training_history": None,
        },
        "score_distribution": _distribution(all_scores),
        "alerts_by_threshold": {
            key: {
                "resolved_threshold": float((threshold_values or {})[key]),
                "count": int(count),
                "rate": 0.0 if node_observations == 0 else float(count / node_observations),
            }
            for key, count in alert_counts.items()
        },
        "workload": {
            "graph_count": len(graph_scores),
            "node_observation_count": node_observations,
            "edge_count": edge_count,
        },
        "runtime": {
            "seconds": round(runtime_seconds, 6),
            "seconds_per_graph": None
            if not graph_scores
            else round(runtime_seconds / len(graph_scores), 6),
        },
        "resource": _resource_snapshot(device),
        "artifact_refs": {
            "node_scores": str(scores_path),
        },
        "_scores": all_scores,
    }


def calibrate_thresholds(
    validation_scores: list[float],
    threshold_options: tuple[dict[str, Any], ...],
    output_path: Path,
    *,
    pids: str,
    scoring: str,
    score_channel: str,
    threshold_space_version: str,
) -> dict[str, float]:
    if not validation_scores:
        raise ValueError("Cannot calibrate thresholds without validation scores")
    array = np.asarray(validation_scores, dtype=np.float64)
    resolved: dict[str, float] = {}
    artifact_options: list[dict[str, Any]] = []
    for option in threshold_options:
        method = option["method"]
        if method == "validation_quantile":
            quantile = float(option["value"])
            value = float(np.quantile(array, quantile))
            option_id = f"validation_quantile_q{quantile:g}"
            option_fields = {
                "value": quantile,
                "expected_benign_exceedance_rate": 1.0 - quantile,
            }
            resolution = "quantile of benign validation node scores"
        elif method in {"flash", "threatrace"}:
            value = float(option["value"])
            option_id = f"{method}_v{value:g}"
            option_fields = {
                "value": value,
                "expected_benign_exceedance_rate": float(np.mean(array >= value)),
            }
            resolution = f"{method} scalar applied to benign validation node scores"
        elif method == "max_val_loss":
            value = float(array.max())
            option_id = method
            option_fields = {"expected_benign_exceedance_rate": 0.0}
            resolution = "maximum benign validation node score"
        elif method == "mean_val_loss":
            value = float(array.mean())
            option_id = method
            option_fields = {
                "expected_benign_exceedance_rate": float(np.mean(array >= value))
            }
            resolution = "mean benign validation node score"
        else:
            raise ValueError(f"Unsupported threshold method {method!r}")
        resolved[option_id] = value
        artifact_options.append(
            {
                "id": option_id,
                "method": method,
                **option_fields,
                "resolution": resolution,
                "resolved_value": value,
            }
        )
    atomic_json(
        output_path,
        {
            "schema_version": "threshold_artifact_v1",
            "threshold_space_version": threshold_space_version,
            "pids": pids,
            "labels_used": False,
            "source_split": "val",
            "scoring": scoring,
            "score_channel": score_channel,
            "options": artifact_options,
        },
    )
    return resolved


def result_envelope(
    *,
    cfg: Any,
    pids: str,
    checkpoint_id: str,
    split: str,
    metrics: dict[str, Any],
    status: str = "success",
) -> dict[str, Any]:
    clean_metrics = {key: value for key, value in metrics.items() if not key.startswith("_")}
    return {
        "schema_version": "checkpoint_split_result_v1",
        "dataset": cfg.dataset.name,
        "pids": pids,
        "checkpoint_id": checkpoint_id,
        "split": split,
        "status": status,
        "visibility": {
            "labels_used": False,
            "agent_initialization": split in {"train", "val"},
            "posthoc_only": False,
        },
        "metric_definitions": {
            "loss": "PIDS-specific objective; compare only within the same PIDS/scoring semantics",
            "score_distribution": "graph-local node scores without labels",
            "alerts_by_threshold": "PIDS-specific threshold method applied without attack labels",
            "workload": "observed graph/node/edge counts",
        },
        "metrics": {
            "loss": clean_metrics["loss"],
            "score_distribution": clean_metrics["score_distribution"],
            "alerts_by_threshold": clean_metrics["alerts_by_threshold"],
            "workload": clean_metrics["workload"],
        },
        "runtime": clean_metrics["runtime"],
        "resource": clean_metrics["resource"],
        "artifact_refs": clean_metrics["artifact_refs"],
        "privileged_metrics": None,
    }
