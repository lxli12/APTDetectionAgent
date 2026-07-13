# APTDetectionAgent

APTDetectionAgent is a research controller for provenance-based intrusion detection
pipelines. It wraps the pinned PIDSMaker implementation with typed tools, causal
window processing, controlled configuration, case and memory state, isolated hidden
evaluation, and reproducible experiment manifests.

The objective is not merely to execute PIDSMaker. The implementation must preserve
the invariants in the [final design](docs/design/APT_Detection_Agent_Design_v0.4.md)
and the [requirement traceability matrix](docs/plans/REQUIREMENT_TRACEABILITY.md),
especially future-data exclusion, hidden-label isolation, next-window
reconfiguration, split-scoped memory, and campaign-aware evaluation.

## Current status

Implementation is staged according to
[IMPLEMENTATION_PLAN.md](docs/plans/IMPLEMENTATION_PLAN.md). Phase acceptance is
recorded in `docs/reports/`; unimplemented phases must not be represented as
complete. Formal SFT training remains `BLOCKED_BY_SFT_DATASET` until a valid,
sanitized trajectory dataset exists.

## Runtime boundaries

- PIDSMaker is an unchanged submodule pinned by commit SHA and runs in the AutoDL
  `pids` environment.
- vLLM runs independently in the `vllm` environment and is accessed over a local
  OpenAI-compatible HTTP endpoint.
- The controller uses typed requests and never imports PIDSMaker or vLLM across
  their environment boundary.
- PostgreSQL access is role-separated; the controller has no private-label access.
- W&B is disabled and is not a project dependency.

## Development

Governance checks use only the Python standard library:

```bash
python3 scripts/check_governance.py
python3 -m unittest discover -s tests -v
```

Python 3.10 is the minimum project runtime. The formal AutoDL allocation is 32 vCPU,
240 GiB RAM, and two 24 GiB RTX 4090 GPUs regardless of greater host-visible
capacity. See [AGENTS.md](AGENTS.md) for the complete local/remote workflow.
