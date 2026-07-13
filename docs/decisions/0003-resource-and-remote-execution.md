# ADR 0003: Resource and remote execution baseline

Status: accepted
Requirements: REQ-RESOURCE-001..003, REQ-GIT-001..003,
REQ-REPRO-001..003.

The only allocatable AutoDL profile is 32 vCPU, 240 GiB RAM, two RTX 4090 GPUs, and
24 GiB per GPU. Host-visible resources are audit observations, not allocations.

The initial scheduler reserves GPU 0 for vLLM and permits one PIDSMaker GPU process
on GPU 1. CPU PIDS may run concurrently within explicit CPU/RAM admission limits.
Same-GPU model concurrency is prohibited until independent memory/latency profiles
justify it.

All tracked changes originate locally, are committed and pushed, then reach AutoDL
through a clean-tree `git pull --ff-only`. Remote experiments use owned tmux
sessions, unique run directories, and exact Git provenance.
