"""Resource accounting for checkpoint preparation through train/validation."""

from __future__ import annotations

import os
import platform
import resource
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch


def _effective_cpu_limit() -> float:
    try:
        quota, period = Path("/sys/fs/cgroup/cpu.max").read_text(encoding="utf-8").split()
        if quota != "max":
            return float(quota) / float(period)
    except (OSError, ValueError):
        pass
    return float(os.cpu_count() or 1)


def _peak_rss_gib() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024**2 if platform.system() == "Linux" else 1024**3
    return float(peak) / divisor


class ResourceMonitor:
    """Sample process CPU while retaining exact PyTorch CUDA peak counters."""

    def __init__(self, sample_interval_seconds: float = 0.25):
        self.sample_interval_seconds = sample_interval_seconds
        self.started_at = datetime.now(timezone.utc)
        self._started_perf = time.perf_counter()
        self._started_times = os.times()
        self._last_perf = self._started_perf
        self._last_cpu = self._started_times.user + self._started_times.system
        self._peak_cpu_percent = 0.0
        self._stop = threading.Event()
        self._cpu_limit = _effective_cpu_limit()
        self._gpu_indices: list[int] = []
        if torch.cuda.is_available():
            self._gpu_indices = list(range(torch.cuda.device_count()))
            for index in self._gpu_indices:
                torch.cuda.reset_peak_memory_stats(index)
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def _sample_cpu(self) -> None:
        now_perf = time.perf_counter()
        now_times = os.times()
        now_cpu = now_times.user + now_times.system
        elapsed = now_perf - self._last_perf
        if elapsed > 0:
            percent = 100.0 * (now_cpu - self._last_cpu) / elapsed
            self._peak_cpu_percent = max(self._peak_cpu_percent, percent)
        self._last_perf = now_perf
        self._last_cpu = now_cpu

    def _sample_loop(self) -> None:
        while not self._stop.wait(self.sample_interval_seconds):
            self._sample_cpu()

    def finish(self) -> dict[str, Any]:
        self._stop.set()
        self._thread.join(timeout=max(1.0, self.sample_interval_seconds * 4))
        self._sample_cpu()
        finished_at = datetime.now(timezone.utc)
        finished_perf = time.perf_counter()
        finished_times = os.times()
        user_seconds = finished_times.user - self._started_times.user
        system_seconds = finished_times.system - self._started_times.system
        cpu_seconds = user_seconds + system_seconds
        wall_seconds = finished_perf - self._started_perf
        gpu_devices = []
        for index in self._gpu_indices:
            properties = torch.cuda.get_device_properties(index)
            gpu_devices.append(
                {
                    "logical_index": index,
                    "name": properties.name,
                    "total_memory_gib": round(properties.total_memory / 1024**3, 6),
                    "peak_allocated_gib": round(
                        torch.cuda.max_memory_allocated(index) / 1024**3, 6
                    ),
                    "peak_reserved_gib": round(
                        torch.cuda.max_memory_reserved(index) / 1024**3, 6
                    ),
                }
            )
        average_cpu_percent = 0.0 if wall_seconds <= 0 else 100.0 * cpu_seconds / wall_seconds
        return {
            "collection_status": "complete",
            "scope": "construction_through_train_and_validation",
            "started_at": self.started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "wall_time_seconds": round(wall_seconds, 6),
            "cpu": {
                "user_seconds": round(user_seconds, 6),
                "system_seconds": round(system_seconds, 6),
                "total_seconds": round(cpu_seconds, 6),
                "average_process_percent": round(average_cpu_percent, 6),
                "peak_process_percent": round(self._peak_cpu_percent, 6),
                "effective_limit_cores": round(self._cpu_limit, 6),
                "peak_fraction_of_limit": round(
                    self._peak_cpu_percent / (100.0 * self._cpu_limit), 6
                ),
            },
            "memory": {"peak_process_rss_gib": round(_peak_rss_gib(), 6)},
            "gpu": {
                "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
                "devices": gpu_devices,
            },
        }


def historical_partial_resource_usage(
    results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Represent known historical observations without inventing missing peaks."""
    resources = [results[split].get("resource", {}) for split in ("train", "val")]
    rss_values = [item.get("peak_process_rss_gib") for item in resources]
    rss_values = [float(value) for value in rss_values if value is not None]
    gpu_values = [item.get("peak_cuda_allocated_gib") for item in resources]
    gpu_values = [float(value) for value in gpu_values if value is not None]
    return {
        "collection_status": "historical_partial",
        "scope": "construction_through_train_and_validation",
        "started_at": None,
        "finished_at": None,
        "wall_time_seconds": None,
        "cpu": {
            "user_seconds": None,
            "system_seconds": None,
            "total_seconds": None,
            "average_process_percent": None,
            "peak_process_percent": None,
            "effective_limit_cores": None,
            "peak_fraction_of_limit": None,
        },
        "memory": {
            "peak_process_rss_gib": max(rss_values) if rss_values else None,
        },
        "gpu": {
            "cuda_visible_devices": None,
            "devices": [],
            "observed_split_peak_allocated_gib": max(gpu_values) if gpu_values else None,
        },
        "missing_metrics": [
            "full_pipeline_wall_time_seconds",
            "cpu_peak_percent",
            "cpu_seconds",
            "training_gpu_peak_reserved_gib",
        ],
    }
