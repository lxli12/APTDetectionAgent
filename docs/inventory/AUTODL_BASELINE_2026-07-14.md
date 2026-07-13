# AutoDL baseline inventory — 2026-07-14

Requirements: REQ-ENV-001..004, REQ-RESOURCE-001..003, REQ-DB-001..003,
REQ-REPRO-001.

Method: read-only inspection over `ssh apt_agent`. This inventory records measured
state without treating host-visible resources as allocatable capacity. No service
was started, no database connection was made, and no credential file was read.

## Measured environment

- Ubuntu 22.04.3 LTS.
- Two NVIDIA RTX 4090 devices, 24564 MiB reported per device.
- Driver 580.105.08; `/usr/local/cuda` resolves to CUDA Toolkit 12.1.
- Project allocation remains 32 vCPU, 240 GiB RAM, two GPUs, 24 GiB per GPU.
- `pids`: Python 3.10.20, PyTorch 2.3.0+cu121, scikit-learn 1.2.0,
  psycopg2-binary 2.9.11.
- `vllm`: Python 3.10.20, PyTorch 2.3.1+cu121, vLLM 0.5.3.post1.
- W&B 0.25.1 is present in the historical `pids` environment and absent from
  `vllm`; presence is not approval or a project dependency.

## Paths

| Path | Measured state |
|---|---|
| `/root/APTDetectionAgent` | directory, approximately 20 MiB |
| `/root/autodl-tmp` | directory, approximately 139 GiB used by contents |
| `/root/autodl-tmp/data` | directory, approximately 23 GiB |
| `/root/autodl-tmp/pids_artifacts` | absent; expected before first new run |
| `/root/autodl-tmp/llm-models/Llama-3.1-8B` | directory, approximately 30 GiB |
| `/root/autodl-tmp/postgresql/17/main` | directory, approximately 86 GiB, owner `postgres`, mode 0700 |
| `/root/miniconda3/envs/pids` | directory, approximately 6.1 GiB |
| `/root/miniconda3/envs/vllm` | directory, approximately 6.9 GiB |

PostgreSQL client version is 17.9. The data directory control file reports format
1700 and state `in production`, while no PostgreSQL process or listener on 5432 was
observed. This inconsistency must be handled under the separately approved safe-start
procedure; it is not authorization for repair. Port 8000 was also not listening.

The Llama model config identifies a BF16 Llama architecture with a declared maximum
position length of 131072. This does not approve any serving context length or GPU
utilization value; those require a conservative smoke profile.
