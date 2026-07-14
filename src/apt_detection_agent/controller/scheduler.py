"""Quota-based scheduler; host-visible capacity never changes admission.

Requirements: REQ-RESOURCE-001..003, REQ-TOOL-004.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import Field, model_validator

from apt_detection_agent.schemas.common import Identifier, StrictModel


class WorkloadKind(str, Enum):
    CONTROLLER = "controller"
    VLLM = "vllm"
    PIDS_CPU = "pids_cpu"
    PIDS_GPU = "pids_gpu"
    HIDDEN_EVALUATOR = "hidden_evaluator"


class ResourceProfile(StrictModel):
    profile_id: Identifier
    cpu_vcpus: int = Field(ge=1, le=32)
    memory_gib: int = Field(ge=1, le=240)
    reserved_memory_gib: int = Field(ge=1)
    gpu_count: int = Field(ge=0, le=2)
    gpu_memory_gib_per_device: int = Field(ge=1, le=24)
    vllm_gpu_index: int = 0
    pids_gpu_index: int = 1
    max_unknown_gpu_pids_per_device: int = 1
    pids_worker_cpu_threads: int = Field(default=16, ge=1, le=32)
    numeric_thread_environment: tuple[str, ...] = ()

    @model_validator(mode="after")
    def safe_initial_profile(self) -> "ResourceProfile":
        if self.reserved_memory_gib >= self.memory_gib:
            raise ValueError("reserved memory must leave allocatable memory")
        if self.gpu_count == 2 and self.vllm_gpu_index == self.pids_gpu_index:
            raise ValueError("initial vLLM and PIDS GPU assignments must differ")
        if self.max_unknown_gpu_pids_per_device != 1:
            raise ValueError("unknown GPU PIDS concurrency requires smoke profiles")
        if self.pids_worker_cpu_threads > self.cpu_vcpus:
            raise ValueError("PIDS worker threads exceed explicit CPU quota")
        return self

    @classmethod
    def from_yaml(cls, path: Path) -> "ResourceProfile":
        payload: dict[str, object] = {}
        assignments: dict[str, int] = {}
        section: str | None = None
        for raw_line in path.read_text().splitlines():
            if not raw_line.strip() or raw_line.lstrip().startswith("#"):
                continue
            indent = len(raw_line) - len(raw_line.lstrip())
            key, value = (part.strip() for part in raw_line.split(":", 1))
            if indent == 0 and not value:
                section = key
                continue
            parsed: object = int(value) if value.isdigit() else value
            if section == "gpu_assignments" and indent:
                assignments[key] = int(parsed)
            else:
                section = None
                payload[key] = parsed
        return cls(
            profile_id=payload["profile_id"],
            cpu_vcpus=payload["cpu_vcpus"],
            memory_gib=payload["memory_gib"],
            reserved_memory_gib=payload["reserved_memory_gib"],
            gpu_count=payload["gpu_count"],
            gpu_memory_gib_per_device=payload["gpu_memory_gib_per_device"],
            vllm_gpu_index=assignments["vllm"],
            pids_gpu_index=assignments["pids_gpu_worker"],
            max_unknown_gpu_pids_per_device=payload["max_unknown_gpu_pids_per_device"],
            pids_worker_cpu_threads=payload["pids_worker_cpu_threads"],
            numeric_thread_environment=tuple(
                str(payload["numeric_thread_environment"]).split(",")
            ),
        )


class ResourceRequest(StrictModel):
    request_id: Identifier
    workload: WorkloadKind
    cpu_vcpus: int = Field(ge=1)
    memory_gib: int = Field(ge=1)
    gpu_memory_gib: int = Field(default=0, ge=0)


class ResourceLease(StrictModel):
    request_id: Identifier
    workload: WorkloadKind
    cpu_vcpus: int
    memory_gib: int
    gpu_index: int | None = None


class ResourceScheduler:
    def __init__(self, profile: ResourceProfile) -> None:
        self.profile = profile
        self._leases: dict[str, ResourceLease] = {}

    def admit(self, request: ResourceRequest) -> ResourceLease:
        if request.request_id in self._leases:
            raise ValueError("resource request is already active")
        used_cpu = sum(lease.cpu_vcpus for lease in self._leases.values())
        used_memory = sum(lease.memory_gib for lease in self._leases.values())
        if used_cpu + request.cpu_vcpus > self.profile.cpu_vcpus:
            raise ValueError("request exceeds explicit CPU quota")
        allocatable_memory = self.profile.memory_gib - self.profile.reserved_memory_gib
        if used_memory + request.memory_gib > allocatable_memory:
            raise ValueError("request exceeds explicit memory quota")
        gpu_index: int | None = None
        if request.workload == WorkloadKind.VLLM:
            gpu_index = self.profile.vllm_gpu_index
        elif request.workload == WorkloadKind.PIDS_GPU:
            gpu_index = self.profile.pids_gpu_index
        if gpu_index is not None:
            if request.gpu_memory_gib > self.profile.gpu_memory_gib_per_device:
                raise ValueError("request exceeds per-device GPU memory quota")
            if any(lease.gpu_index == gpu_index for lease in self._leases.values()):
                raise ValueError("initial profile permits only one workload per assigned GPU")
        elif request.gpu_memory_gib:
            raise ValueError("CPU workload cannot request GPU memory")
        lease = ResourceLease(
            request_id=request.request_id,
            workload=request.workload,
            cpu_vcpus=request.cpu_vcpus,
            memory_gib=request.memory_gib,
            gpu_index=gpu_index,
        )
        self._leases[request.request_id] = lease
        return lease

    def release(self, request_id: str) -> None:
        if self._leases.pop(request_id, None) is None:
            raise KeyError(request_id)
