# APTDetectionAgent

APTDetectionAgent is a research controller for provenance-based intrusion detection
pipelines. It wraps the pinned PIDSMaker implementation with typed tools, causal
window processing, controlled configuration, case and memory state, isolated hidden
evaluation, and reproducible experiment manifests.

The objective is not merely to execute PIDSMaker. The implementation must preserve
the invariants in the [final design](docs/design/APT_Detection_Agent_Design_v0.4.md)
and the [requirement traceability matrix](docs/plans/REQUIREMENT_TRACEABILITY.md),
plus the [frozen repository architecture](docs/PROJECT_ARCHITECTURE_DESIGN_v1.1.md),
especially future-data exclusion, hidden-label isolation, next-window
reconfiguration, split-scoped memory, and campaign-aware evaluation.

## Current status

Implementation is staged according to
[IMPLEMENTATION_PLAN.md](docs/plans/IMPLEMENTATION_PLAN.md). Phase acceptance is
recorded in `docs/reports/`; unimplemented phases must not be represented as
complete. Formal SFT training remains `BLOCKED_BY_SFT_DATASET` until a valid,
sanitized trajectory dataset exists.

Repository implementation now uses the v1.1 owners: `agent`, `runtime`, `tools`,
`memory`, `evaluation`, `experiment`, `sft`, and `training`. The former
`controller`, `llm`, `tooling`, `evaluator`, and `validation` packages are thin
deprecated import shims only; they contain no authoritative implementation.

Phases 0–7 and the Phase 9 synthetic multi-window path have remote acceptance
evidence. Phase 8 real PIDSMaker and Phase 9 real-data acceptance remain gated by a
least-privilege database role, interval-bounded construction compatibility, and a
causal checkpoint path. See
[`PHASE_8_ACCEPTANCE.md`](docs/reports/PHASE_8_ACCEPTANCE.md) and
[`PHASE_9_ACCEPTANCE.md`](docs/reports/PHASE_9_ACCEPTANCE.md); synthetic success is
not reported as detector performance.

## Runtime boundaries

- PIDSMaker is an unchanged submodule pinned by commit SHA and runs in the AutoDL
  `pids` environment.
- vLLM runs independently in the `vllm` environment and is accessed over a local
  OpenAI-compatible HTTP endpoint.
- The controller uses typed requests and never imports PIDSMaker or vLLM across
  their environment boundary.
- The Agent emits only `ProposedAction`; the runtime resolves it into an
  `ExecutableAction` before any tool dispatch.
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

## Formal entrypoints

Run these in an environment containing the lightweight controller dependencies;
PIDSMaker execution itself remains in `pids`, while vLLM remains in `vllm`.

```bash
# Validates every training stage and reports explicit blocked gates.
scripts/train_agent.sh --run-id <unique-id> --stage all

# Executes the isolated, non-performance synthetic protocol.
scripts/test_agent.sh --run-id <unique-id> --mode synthetic

# Real mode fails closed until the Phase 8 gates are satisfied.
scripts/test_agent.sh --run-id <unique-id> --mode real
```

The SFT interface validates schemas/hashes in dry-run mode and never fabricates a
checkpoint. Missing or unapproved trajectory data produces
`BLOCKED_BY_SFT_DATASET`. Detailed reproduction and status/tail commands are in
[`docs/reproduction.md`](docs/reproduction.md).
