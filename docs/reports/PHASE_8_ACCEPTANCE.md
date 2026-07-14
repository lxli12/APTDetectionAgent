# Phase 8 acceptance report — partial

Requirements: REQ-PIDS-001..005, REQ-ARTIFACT-001..003,
REQ-RESOURCE-001..003, REQ-REPRO-001..003, REQ-LABEL-001..004,
REQ-WANDB-001, REQ-DB-001..003.

## Implemented evidence

- `scripts/pidsmaker_stage_runner.py` provides a typed, shell-free prefix runner
  for construction through `feat_inference`, verifies the pinned commit, obtains
  database values only from named environment variables, rejects artifact-root
  escape/overwrite, requires W&B disabled mode, strips evaluation-only dataset
  metadata, and never invokes training/evaluation/triage.
- `tests/test_pidsmaker_stage_runner.py` covers credential/argv separation,
  forbidden overrides, W&B mode, path containment, non-overwrite semantics,
  privileged-field exclusion, stage allowlisting, and the pinned submodule SHA.
- `docs/dataset_inventory.md` records all 15 upstream datasets and distinguishes
  dump presence, restored database presence, checkpoint state, and unresolved
  compatibility.
- Read-only AutoDL checks confirm PostgreSQL 17.9 is ready, five dataset databases
  exist, only the administrator login role exists, no PIDS checkpoint was found,
  both GPUs were idle during inventory, and `tmux` is absent.

## Acceptance gates not yet satisfied

Phase 8 is not complete and no real PIDS availability has been promoted:

1. `PIDSMaker/pidsmaker/preprocessing/build_graph_methods/build_default_graphs.py`
   fetches an entire day before test-mode truncation. A true minimal `[start,end)`
   smoke requires an isolated, versioned compatibility patch.
2. No `pids_worker` database role or approved credential exists. Using the
   PostgreSQL superuser would violate `docs/decisions/0001-process-and-environment-boundaries.md`.
3. `PIDSMaker/pidsmaker/detection/training_methods/training_loop.py` consults test
   data during training, calls W&B unconditionally, and comments out checkpoint
   saving. It cannot establish a causal frozen checkpoint as pinned.
4. Long PIDSMaker runs require `tmux` under `AGENTS.md`, but AutoDL has no `tmux`.
   Installing it requires explicit approval.

Consequently checkpoint save/load, raw-to-standard artifact validation, independent
per-PIDS resource profiles, and a real construction/feature/inference run remain
pending. A zero-exit upstream CLI invocation would not satisfy these gates.
