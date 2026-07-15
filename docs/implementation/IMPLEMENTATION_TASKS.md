# APTDetectionAgent Implementation Tasks

Status: planned

Last updated: 2026-07-15

Design input: `docs/design/APT_Detection_Agent_Design_v0.4.md`

Architecture boundary: `docs/architecture/PROJECT_ARCHITECTURE_DESIGN_v1.2.md`

## 1. Objective

Implement the v0.4 APTDetectionAgent as a frozen-policy, label-blind,
construction-graph-level PIDSMaker controller. The first complete research
system must provide:

- persistent per-scenario PIDS configuration;
- per-construction-graph fast-path detection and committed alerts;
- event-triggered, budgeted LLM slow-path diagnosis and reconfiguration;
- a fixed Working/Episode/Long-Term Memory harness;
- constrained, stage-aware PIDSMaker tools with explicit cache behavior;
- privileged-to-deployable SFT data construction;
- frozen-agent held-out evaluation under the attack-coverage constraint; and
- reproducible baselines, ablations, cost accounting, and experiment artifacts.

This plan implements the design in dependency order. A later task must not
bypass an unfinished contract or safety boundary from an earlier task.

## 2. Non-negotiable boundaries

1. `PIDSMaker/` remains an unchanged pinned submodule. All compatibility work
   belongs in Agent-owned configuration, adapters, parsers, and tools.
2. The Mac M1 is for code, documentation, static checks, and lightweight unit
   tests only. Data processing, PIDSMaker execution, model serving, training,
   and experiments run on AutoDL.
3. Remote code lives at `/root/APTDetectionAgent`. Large files and generated
   artifacts live under `/root/autodl-tmp` according to `AGENTS.md`.
4. Held-out online observations and deployable memory must never contain attack
   identity, malicious nodes, attack time, TP/FP/FN, coverage, ADP, MCC, or
   another label-derived field.
5. The LLM cannot emit arbitrary shell commands, paths, PIDSMaker CLI arguments,
   numeric hyperparameters, or unregistered tools. Every executable choice comes
   from an admitted, versioned candidate set.
6. Every task ends with proportional verification, one or more focused commits,
   and a push to GitHub. Generated data, credentials, checkpoints, and run
   outputs are never committed.

## 3. Dependency sequence

```text
T0 Remote bootstrap
  |
  v
T1 Contracts and leakage boundary
  |
  v
T2 PIDSMaker capability audit and adapter
  |
  +-------------------+
  v                   v
T3 Observation/Fast   T4 Fixed Memory Harness
  |                   |
  +---------+---------+
            v
T5 Slow Path and Controller
            |
            v
T6 Evaluation, Experiments, Baselines
            |
            v
T7 Offline Run Table and SFT Data
            |
            v
T8 SFT, Held-Out Runs, and Ablations
```

T3 and T4 can be developed independently after T2 contracts are stable, but the
first end-to-end controller in T5 requires both.

## 4. Task definitions

### T0. Remote repository and runtime bootstrap

Purpose: make the live AutoDL machine a reproducible execution target without
placing generated artifacts on the system disk.

Deliverables:

- clone the repository to `/root/APTDetectionAgent` and checkout the pinned
  PIDSMaker submodule;
- create the approved `/root/autodl-tmp/pidsmaker` and
  `/root/autodl-tmp/apt-detection-agent` directory layout;
- replace the stale PIDSMaker editable install with an install from
  `/root/APTDetectionAgent/PIDSMaker` in the `pids` Conda environment;
- create an uncommitted remote `.env` from a committed secret-free template;
- route PostgreSQL, Hugging Face cache, PIDSMaker intermediates/checkpoints, and
  Agent runs to their data-disk paths;
- start and verify PostgreSQL only when the following task needs dataset access;
- record a machine-readable environment snapshot without credentials; and
- add a thin remote smoke-check script owned by this repository.

Acceptance criteria:

- remote `main` and the local/GitHub `main` resolve to the same commit;
- PIDSMaker resolves to the submodule commit recorded by the parent repository;
- `import pidsmaker` succeeds in the `pids` environment;
- both GPUs are visible to PyTorch;
- no newly generated large file appears on the 30 GB system disk; and
- a smoke check reports paths, dependency versions, disk space, cgroup limits,
  GPU visibility, and PostgreSQL readiness without printing secrets.

### T1. Core contracts and data-leakage boundary

Purpose: replace the current generic skeleton contracts with the explicit v0.4
protocol before implementing behavior.

Deliverables:

- typed environment, construction-graph, pipeline, unlabeled detection signal,
  cache, budget, and observation contracts;
- explicit `FAST_PATH` and `SLOW_PATH` decisions;
- explicit Agent actions: `KEEP_AND_INFER`, `INVOKE_SLOW_DIAGNOSIS`,
  `ADJUST_THRESHOLD`, `LOAD_TUNED_CONFIG`, `SWITCH_PIDS`,
  `RETRAIN_CURRENT_PIDS`, `ADJUST_RESOURCE_CONFIG`, and `FALLBACK_OR_STOP`;
- diagnosis, visible evidence, stage invalidation, expected cache reuse,
  confidence, commit policy, and fallback contracts;
- memory read/use/write request contracts;
- per-window committed detection and expanded execution-trace contracts;
- stable serialization/deserialization and schema versioning; and
- a centralized deployable-field sanitizer/validator.

Acceptance criteria:

- contracts depend only on the Python standard library;
- invalid combinations and unknown enum values are rejected;
- hidden/privileged fields cannot enter an online observation or deployable
  memory record;
- round-trip serialization is deterministic; and
- architecture, contract, and adversarial leakage tests pass locally.

### T2. PIDSMaker capability audit and production adapter

Purpose: learn the actual backend interface on AutoDL and expose only admitted,
label-safe operations to the Agent.

Deliverables:

- a versioned audit of actual PIDSMaker CLI, configuration, task hashes, cache
  layout, checkpoint layout, score/alert output, and failure modes;
- a feasibility result for construction-graph-level inference, including an
  Agent-side compatibility strategy if PIDSMaker is batch-oriented;
- a detector/config/dataset capability catalog based on verified backend names;
- admitted threshold, tuned-config, PIDS, seed, and resource candidates;
- a fixed argv builder and subprocess runner with no `shell=True`;
- timeout, cancellation, OOM, non-zero-exit, partial-output, and log handling;
- a result parser that separates online score/alert output from offline
  label-derived evaluation; and
- stage invalidation and expected cache-reuse metadata for each action.

Acceptance criteria:

- arbitrary detector/config/dataset/parameter requests are rejected;
- the exact command, resolved config, stage boundary, duration, and artifact
  paths are recorded without secrets;
- repeated identical smoke runs demonstrate expected cache reuse;
- online normalized results contain no ground truth; and
- at least one real AutoDL scenario completes through the adapter.

### T3. Observation pipeline and deterministic fast path

Purpose: provide correct per-construction-graph detection without requiring the
main LLM on every graph.

Deliverables:

- graph/window ingestion and deterministic ordering;
- graph scale, density, type distribution, time span, and event-rate summaries;
- score quantiles, tail mass, alert volume, trend, degeneracy, and shift signals;
- a persistent committed configuration and last-known-stable fallback;
- `run_current_pids` and per-window committed alerts;
- rolling working state;
- fixed trigger rules for distribution shift, alert anomalies, state changes,
  timeout/OOM, degenerate output, and periodic checkpoints; and
- trigger reason and cost recording.

Acceptance criteria:

- every accepted graph produces exactly one committed detection result;
- an untriggered graph performs no main-LLM call;
- configuration persists across graph boundaries;
- trigger decisions use only deployable signals; and
- a fake-backend multi-window replay provides the first rule-only baseline.

### T4. Fixed Memory Harness

Purpose: implement deterministic storage and retrieval while leaving only
read/query/use/write decisions to the future SFT policy.

Deliverables:

- bounded Working Memory;
- scenario-scoped Episode Memory and summaries;
- static Long-Term Experience Memory;
- structured environment, observable behavior, PIDS capability, experience,
  applicability/failure condition, confidence, and support fields;
- privileged and deployable record views;
- schema validation, sanitization, deduplication, capacity, archive, and reset;
- held-out namespace isolation and prevention of held-out LTM consolidation;
- retrieval pipeline: metadata compatibility gate, normalized numeric
  similarity, semantic reranking, confidence reranking, and fixed top-k; and
- provenance IDs and inspectable retrieval scores.

Acceptance criteria:

- incompatible environments are filtered or explicitly downweighted;
- privileged fields cannot survive sanitization;
- independent held-out scenarios cannot read one another's episode memory;
- deterministic inputs produce deterministic retrieval; and
- no-memory, no-episode-memory, and semantic-only modes are configurable for
  later ablations.

### T5. LLM providers, slow path, tools, and complete controller

Purpose: connect policy reasoning to bounded memory and PIDSMaker actions with a
safe terminating state machine.

Deliverables:

- provider-neutral chat/completion interface and normalized usage result;
- default local Llama-3.1-8B vLLM client;
- configurable Hugging Face/open-model and closed-API adapters described in
  `AGENTS.md`, without requiring all providers for the default run;
- retry, timeout, structured-output parsing, token accounting, and no-silent-
  fallback behavior;
- registered observation, memory, inference, and reconfiguration tools;
- two-stage memory read/result/use policy transcript;
- diagnosis and action selection using only visible evidence;
- action validation against candidate, stage, cache, and budget constraints;
- commit/rollback behavior and last-known-stable fallback; and
- full Observe -> Infer -> Commit -> Trigger -> Retrieve -> Diagnose -> Act ->
  Reflect -> Trace controller lifecycle.

Acceptance criteria:

- malformed model output cannot execute a tool;
- no model output is interpreted as a shell command or arbitrary path;
- stage/cache expectations are checked before execution;
- tool/model failures and exhausted budgets terminate safely;
- every adopted memory is referenced by ID; and
- fake LLM plus fake backend tests cover multi-window success and failure flows.

### T6. Offline evaluation, experiment lifecycle, and baselines

Purpose: make controller behavior measurable and reproducible without leaking
ground truth into deployment.

Deliverables:

- TP/FP/FN/TN, precision, recall, MCC, attack coverage, P@C=100%, ADP,
  evidence recovery, per-campaign detection, delay, alert volume, and stability;
- token/context/LLM-call, runtime, memory, PIDSMaker-call, stage-rerun,
  reconfiguration, and cache-reuse cost metrics;
- strict post-hoc evaluator boundary;
- run creation, resolved-config snapshot, command snapshot, status tracking,
  logs, traces, metrics, reports, and failure manifests;
- reproducible CLI entry points; and
- static tuned PIDS, validation-selected config, rule-only controller, and
  always-slow-path baselines.

Acceptance criteria:

- the same trace and truth inputs produce the same report;
- episodes below 100% attack coverage are marked infeasible while retaining all
  diagnostic metrics;
- evaluator-only fields cannot flow back into controller inputs;
- interrupted/failed runs remain inspectable and cannot be marked completed;
  and
- a complete AutoDL rule-only baseline run is reproducible from saved metadata.

### T7. Offline Run Table and SFT dataset pipeline

Purpose: construct auditable privileged teacher data and sanitized deployable
training examples from controlled Agent-training scenarios.

Architecture gate:

The frozen v1.2 architecture intentionally reserves `sft/` without Python
implementation, and the current architecture test enforces that state. Before
adding SFT source files, publish an architecture v1.3 that activates the agreed
SFT modules while retaining the PIDSMaker and data-ownership boundaries. Update
the architecture test explicitly; do not silently bypass it.

Deliverables:

- agent-level training/validation/held-out split manifests;
- offline-run schema, manifest, storage, and provenance;
- representative PIDS/config/threshold/seed coverage plan;
- controlled counterfactual groups that change one factor at a time;
- weak diagnosis rules, ambiguous-label handling, and review sampling;
- privileged attack-chain analysis and deployable experience distillation;
- static LTM construction;
- trace/manifest loaders, example builder, sanitizer, validator, and exporter;
  and
- targets for trigger, memory read/query/use/write, diagnosis, action,
  stage/cache expectation, confidence, and fallback.

Acceptance criteria:

- every training row is traceable to source run(s), teacher evidence, and split;
- no dataset/scenario crosses an agent-level split;
- privileged fields are absent from model input and deployable rationale;
- counterfactual groups are internally consistent; and
- exported rows pass schema, tool, action, and leakage validation.

### T8. SFT training, frozen held-out deployment, and ablations

Purpose: determine whether an SFT-first Agent improves constrained detection and
whether any remaining limitation justifies a later RL project.

Deliverables:

- versioned base-model, tokenizer, training, checkpoint, and inference configs;
- SFT trainer/backend integration and resume behavior;
- single-step schema, trigger, diagnosis, action, and memory-policy evaluation;
- frozen-weight held-out scenario runner;
- full baseline comparison;
- ablations for memory, Episode Memory, environment gate, semantic-only
  retrieval, privileged distillation, PIDS capability, diagnosis, and trigger;
- multi-seed stability and resource/cost reports; and
- a documented SFT bottleneck analysis and explicit RL go/no-go decision.

Acceptance criteria:

- training and held-out scenarios remain isolated;
- held-out deployment performs no weight update and sees no labels;
- all primary results report coverage feasibility, P@C=100%, evidence recovery,
  false alerts, delay, runtime, cache behavior, and token usage;
- every published result maps to a versioned commit, config, data manifest,
  model revision/checksum, and run directory; and
- RL is not introduced unless a measured SFT limitation requires long-horizon
  optimization that imitation data cannot resolve.

## 5. Milestones

### M1. Safe rule-only controller

Complete T0-T3. Outcome: a real PIDSMaker-backed, label-safe,
construction-graph-level controller that commits alerts and invokes no main LLM.

### M2. Full untrained Agent harness

Complete T4-T6. Outcome: fixed memory, optional LLM slow path, constrained tools,
fallback behavior, evaluation, baselines, and reproducible experiment lifecycle.

### M3. SFT research system

Complete T7-T8. Outcome: auditable SFT data, trained frozen Agent, held-out
evaluation, baselines, ablations, and evidence for or against a later RL stage.

## 6. Verification matrix

| Check | Local Mac | AutoDL |
|---|---:|---:|
| Documentation and config validation | Yes | Optional |
| Pure schema/unit/property tests | Yes | Yes |
| Fake LLM/backend controller tests | Yes | Yes |
| PIDSMaker import and adapter tests | No | Yes |
| PostgreSQL and dataset checks | No | Yes |
| CUDA/vLLM/model smoke tests | No | Yes |
| Data generation, training, evaluation | No | Yes |
| Baselines and ablations | No | Yes |

Local success never substitutes for a required AutoDL result. Conversely, an
unversioned remote patch is not an acceptable implementation; source changes
must return through Git and pass the relevant checks.

## 7. Per-task completion checklist

A task is complete only when all applicable items are satisfied:

- design assumptions and unresolved decisions are recorded;
- implementation respects module ownership and dependency direction;
- public contracts and configs are documented;
- positive, invalid-input, leakage, and failure-path tests exist;
- local lightweight checks pass where applicable;
- required AutoDL smoke/integration/experiment checks pass;
- generated outputs are on `/root/autodl-tmp` and absent from Git;
- `git diff --check` and repository status are reviewed;
- focused commits are pushed to GitHub; and
- this document is updated if scope, ordering, or acceptance criteria change.

## 8. Immediate next action

Finish T0 without running an experiment: complete the pinned submodule checkout,
create the data-disk directory layout, reinstall PIDSMaker from the canonical
checkout, add the secret-free environment template and smoke-check script, and
verify the resulting runtime. Then begin T1 contracts before implementing any
LLM policy or backend action behavior.
