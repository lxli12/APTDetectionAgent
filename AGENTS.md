# APTDetectionAgent Engineering Rules

This repository implements a research system whose correctness includes causality,
label isolation, lifecycle semantics, provenance, and reproducibility. A successful
process exit is never sufficient evidence of correctness.

## Sources of truth

1. GitHub is the only source of versioned code and design documents.
2. Tracked source is edited only in the Mac repository.
3. `docs/design/APT_Detection_Agent_Design_v0.4.md`, accepted decisions in
   `docs/decisions/`, and `docs/plans/REQUIREMENT_TRACEABILITY.md` define behavior.
4. PIDSMaker is pinned at commit
   `32602734bc9f896be5fc0f03f0a185c967cd6624`; do not edit the submodule.
5. Historical `setup_server.sh` and `run_agent_server.sh` files outside this
   repository are evidence only. Never execute them, copy their installation or
   database-migration commands, or reproduce credentials found in them.

## Requirement traceability

- Every module, test, protocol, and acceptance item must cite at least one `REQ-*`
  identifier from `docs/plans/REQUIREMENT_TRACEABILITY.md`.
- Update the matrix when an implementation path, test, or status changes.
- Negative tests are mandatory for causality, hidden-label isolation, configuration
  timing, memory reset, and unsafe tool parameters.

## Security and data boundaries

- Agent-visible processes must never read test labels, private ground truth, hidden
  campaign mappings, teacher-only rationale, counterfactual best actions, or
  unsanitized TP/FP/FN details.
- The hidden evaluator runs as a separate process with separate filesystem and
  PostgreSQL permissions. It returns only versioned metrics, bounded training
  rewards, or sanitized feedback permitted by the active split.
- Never read or print `.env`, passwords, tokens, private keys, or database
  credentials. Connections are injected through environment or untracked local
  configuration.
- The LLM emits typed tool requests only. It never constructs shell commands,
  selects CUDA devices, or chooses arbitrary filesystem paths.
- W&B is prohibited: do not install it, log in, emit network requests, or make it a
  reproducibility dependency.

## Causality and evaluation

- Windows are aligned `[start, end)` buckets with recorded origin, timezone, and
  size. Never read a future window or rewrite a committed prediction.
- Fit vocabulary, normalization, IDF, feature statistics, embeddings, models, and
  thresholds only on allowed training/validation inputs; freeze them before
  held-out evaluation.
- Persistent reconfiguration becomes effective at the next window. A current
  window may run additional slow-path investigation without changing its committed
  fast-path prediction.
- Transductive PIDSMaker configurations are compatibility baselines and must never
  be mixed into causal main results.

## Runtime and resources

- Allocation comes from an explicit resource profile, not host-visible capacity.
- AutoDL baseline: 32 vCPU, 240 GiB RAM, two RTX 4090 GPUs, at most 24 GiB per GPU.
- Initial profile reserves GPU 0 for vLLM and permits one PIDSMaker GPU process on
  GPU 1. The executor, not the LLM, queues work.
- PIDSMaker runs in the `pids` Conda environment. vLLM runs in the separate `vllm`
  environment. Do not cross-import their packages or merge/upgrade environments.
- PostgreSQL 17 data is under `/root/autodl-tmp/postgresql/17/main`. Never use old
  binaries on it, modify it automatically, or commit database files.

## Git and remote workflow

1. Work in a phase-specific `codex/` feature branch and make small commits.
2. Before a remote pull, run `git status --short` in `/root/APTDetectionAgent`.
3. Stop if the remote tree is dirty. Never reset, checkout over, or delete user work.
4. Push local commits, then use only `git pull --ff-only` on the server.
5. Record the exact main-project and PIDSMaker SHAs for every remote run.
6. Never directly edit tracked files on the server.

If GitHub access from AutoDL fails, the official academic acceleration service may
be enabled only inside the SSH shell that performs the pull with
`source /etc/network_turbo`. Clear lowercase and uppercase HTTP(S) proxy variables
immediately afterward. Do not persist the proxy or propagate it to tests,
PIDSMaker, vLLM, PostgreSQL, W&B, or experiments. The service is an optional,
non-guaranteed Git transport aid, not part of the reproducibility environment.

The first SSH connection in a task must run the approved read-only identity check
(`hostname`, `whoami`, `pwd`, GPU query, and `df -h`). Installation, service changes,
database writes, stopping unrelated processes, destructive commands, and unapproved
high-cost experiments require explicit user approval.

Long tasks use tmux, a unique run ID, and a new directory below
`/root/autodl-tmp/apt-agent/experiments/runs/`. Immediately verify the session,
process, logs, resource use, and common failure signatures. Never overwrite a run.

## Completion discipline

For each phase: design mapping, minimal implementation, unit tests, synthetic
integration test where applicable, remote smoke where applicable, acceptance
report, commit, and push. Preserve complete command, configuration, environment,
artifact, prediction, metric, and failure provenance.
