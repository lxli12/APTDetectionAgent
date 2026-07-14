# Implementation Plan

Status: active
Design baseline: `docs/design/APT_Detection_Agent_Design_v0.4.md` plus accepted
decisions in `docs/decisions/`
PIDSMaker baseline: `32602734bc9f896be5fc0f03f0a185c967cd6624`

Implementation snapshot (2026-07-14): Phases 0–7 are accepted; Phase 8 has a safe
prefix runner/inventory but real execution remains gated; Phase 9 synthetic
end-to-end is accepted while real-data end-to-end inherits the Phase 8 gates;
Phase 10 interfaces and dry-run are accepted while formal training is
`BLOCKED_BY_SFT_DATASET`.

This plan is requirement-driven. A phase is complete only when its mapped
requirements have implementation and test evidence in
`REQUIREMENT_TRACEABILITY.md`; exit code zero alone is insufficient.

## Phase workflow

Every phase follows: design mapping → minimal implementation → unit tests →
synthetic integration → applicable remote smoke → acceptance report → commit/push.
Each phase uses a separate feature branch and preserves the pinned submodule.

## Phase 0 — Governance and executable plan

Requirements: REQ-GOV-001..004, REQ-GIT-001..003, REQ-REPRO-001,
REQ-ENV-001..003, REQ-WANDB-001.

Deliverables:

- `AGENTS.md`, `README.md`, `pyproject.toml`.
- Implementation plan and requirement traceability matrix.
- Data and experiment protocols; architecture/resource/security decisions.
- `src/`, `tests/`, `configs/`, and `scripts/` foundations.
- Standard-library governance checker and tests.

Acceptance:

- Every normative requirement has an owner phase and verification strategy.
- Governance checker and unit tests pass without installing dependencies.
- Final design is tracked and unchanged; PIDSMaker SHA and worktree are unchanged.
- Diff is reviewed, then the phase commit is pushed.

## Phase 1 — Core schemas and safety boundaries

Requirements: REQ-LABEL-001..004, REQ-TOOL-001, REQ-CONFIG-001..003,
REQ-WINDOW-001..003, REQ-MEMORY-001..004, REQ-EVAL-001..004,
REQ-ARTIFACT-001..003.

Deliverables:

- Versioned schemas for Observation, Action/ToolRequest, ToolResult, PIDS registry,
  ApprovedConfig, Threshold, Window, Case, MemoryRecord, CampaignManifest,
  Prediction, EvaluationRecord, ArtifactManifest, and RunManifest.
- Explicit privileged/deployment-visible views and serialization boundaries.
- Dependency audit and decision on a minimal controller environment.
- Positive, round-trip, boundary, and negative schema tests.

Acceptance:

- Unknown fields and privileged fields are rejected at Agent-visible boundaries.
- Threshold/config provenance and immutable IDs are mandatory.
- Invalid intervals, split transitions, paths, hashes, and tool parameters fail
  closed with typed errors.
- Tests run locally and in an approved remote smoke without cross-environment imports.

## Phase 2 — PIDSMaker discovery and adapter

Requirements: REQ-PIDS-001..005, REQ-TOOL-001..005, REQ-ARTIFACT-001..003,
REQ-WANDB-001.

Deliverables include the complete `docs/pidsmaker/` inventory set, dynamic registry,
ApprovedConfig selector, validated argv builder, subprocess executor, standardized
outputs, fake runner, and all required PIDS/trace tools. The submodule remains clean.

Acceptance includes full model/variant discovery, unavailable entries retained with
reasons, no shell-string API, stage trace provenance, timeout/error handling, and
synthetic adapter integration tests.

## Phase 3 — Causal data and windows

Requirements: REQ-CAUSAL-001..004, REQ-WINDOW-001..004, REQ-LABEL-001.

Implement aligned `[start,end)` windows, explicit origin/timezone, chronological
streaming, causal feature boundaries, frozen fitted state, and physical label
separation. Negative tests inject future events and forbidden refits.

## Phase 4 — Case and memory

Requirements: REQ-MEMORY-001..007, REQ-LABEL-002..004.

Implement working/episode state, SQLite FTS5, structured retrieval, normalized hash
deduplication, conflict coexistence, reset boundaries, and a signed static-LTM
interface. Release flow is deterministic sanitizer/provenance check, hidden-evaluator
signature, then human sampling; runtime needs no human approval.

## Phase 5 — Agent controller

Requirements: REQ-TOOL-001..005, REQ-CONFIG-001..003, REQ-RESOURCE-001..003,
REQ-REPRO-001..003.

Implement observe–think–act–reflect, fast/slow paths, committed configuration,
next-window persistent changes, trace-informed routing, bounded retries, scheduler,
failure recovery, and complete trajectory logging. Hidden evidence is excluded from
routing by construction.

## Phase 6 — vLLM interface

Requirements: REQ-ENV-001..004, REQ-RESOURCE-001..003, REQ-TOOL-001.

Implement an HTTP client driven by `VLLM_HOST`, `VLLM_PORT`, `VLLM_BASE_URL`, and
`VLLM_MODEL_PATH`; no hard-coded port or vLLM import. Complete mock tests before a
conservative, explicitly approved AutoDL smoke.

## Phase 7 — Hidden evaluator and metrics

Requirements: REQ-LABEL-001..004, REQ-EVAL-001..006, REQ-DB-001..003.

Implement isolated evaluator IPC, campaign manifests, unique-node and occurrence
metrics, edge/evidence metrics, P@C=100%, MCC, ADP, coverage, stability, efficiency,
and leakage tests. Held-out feedback is episode-level only.

## Phase 8 — Real PIDSMaker smoke and artifacts

Requirements: REQ-PIDS-001..005, REQ-ARTIFACT-001..003,
REQ-RESOURCE-001..003, REQ-REPRO-001..003.

Start with one dataset, one PIDS, and a minimal construction/feature/inference
interval. Validate artifact schema and checkpoint load/save before expanding.
Profile every PIDS independently; GPU 1 runs at most one unknown GPU workload.

## Phase 9 — End-to-end validation

Requirements: all runtime requirements.

First pass a synthetic multi-window scenario covering state, memory, routing,
slow-path, next-window config, evaluator isolation, metrics, and reports. Then run a
minimal real-data scenario. Validate invariants and provenance, not only completion.

## Phase 10 — SFT interfaces

Requirements: REQ-SFT-001..004, REQ-LABEL-002..004, REQ-REPRO-001..003.

Implement trajectory/teacher boundaries, sanitizer, dataset validator, split
manifest, dataset-builder and trainer interfaces, dry-run fixtures, and checkpoint
manifest. Formal dataset construction and training remain
`BLOCKED_BY_SFT_DATASET` until authorized data exists.

## Formal entrypoints and remote operations

Phase 10 delivers substantive `scripts/train_agent.sh` and `scripts/test_agent.sh`
stage orchestrators plus owned-run start/status/tail/stop/summary scripts. They
create non-overwriting run directories under
`/root/autodl-tmp/apt-agent/experiments/runs/<run_id>/` and preserve every artifact
listed by REQ-REPRO-001..003.

## Stop conditions

Stop for user direction only when continuation requires destructive/overwriting
data operations, database repair or writes, key environment installation/upgrades,
an irreconcilable design conflict, missing essential data/credentials/permissions,
or an unapproved high-cost full training run.
