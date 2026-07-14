# Completion audit — 2026-07-14

Requirements: REQ-GOV-001..004, REQ-GIT-001..003, REQ-CAUSAL-001..004,
REQ-LABEL-001..004, REQ-TOOL-001..005, REQ-MEMORY-001..007,
REQ-EVAL-001..007, REQ-ARTIFACT-001..003, REQ-DB-001..003,
REQ-WANDB-001, REQ-REPRO-001..003, REQ-SFT-001..004.

## Audited result

The implementation-only work that does not require new infrastructure authority or
formal data is complete through Phase 10. The project is not yet eligible for the
global “implementation complete” claim because Phase 8 real PIDSMaker acceptance,
Phase 9 real-data end-to-end acceptance, live database/filesystem isolation, and
formal SFT remain gated. Synthetic evidence is never promoted to a formal
performance result.

The completion audit closed four previously under-specified surfaces:

1. `src/apt_detection_agent/tooling/memory_tools.py` now implements strict
   `retrieve_memory`, `write_memory`, `update_case`, and `generate_report` tools.
   Namespace, environment, time, IDs, storage paths, and audit paths are executor
   owned; static-LTM writes and privileged report text fail closed.
2. `src/apt_detection_agent/evaluator/calibration.py` now performs private,
   validation-only agent-campaign coverage threshold calibration and emits complete
   frozen threshold provenance. Held-out, benign-only, and unsatisfied calibration
   requests fail closed.
3. `src/apt_detection_agent/evaluator/engine.py` now emits versioned
   `agent-eval-v2` metrics with separate campaign-delay, alert-volume/score
   stability, LLM efficiency, and control-behavior maps. Historical v1 artifacts
   remain immutable.
4. `scripts/remote/sync_code.sh` now enforces the dirty-tree/submodule gate before
   network access, performs only `git pull --ff-only`, clears temporary academic
   proxy variables, and re-verifies the fixed PIDSMaker commit.

## Verification evidence

AutoDL at main-project commit
`f430010d5b504f16205089297df4b4704a0d2502` and PIDSMaker commit
`32602734bc9f896be5fc0f03f0a185c967cd6624` passed:

- focused hidden-evaluator plus synthetic end-to-end suite: 22/22;
- full project suite: 180/180 in 7.892 seconds;
- governance: 67 unique requirement IDs and correct PIDSMaker pin;
- `git diff --check`: passed;
- main and submodule working trees: clean;
- safe remote sync script: live fast-forward and SHA verification passed.

The short zero-GPU run
`/root/autodl-tmp/apt-agent/experiments/runs/completion_audit_synthetic_20260714_001`
completed successfully with `formal_performance_claim=false`. Its public
`metrics.json` contains only `split`, `episode_id`, `metrics_artifact_id`, and
`emitted_at`. The evaluator-private artifact records `agent-eval-v2`; campaign
coverage, malicious-node counts, and other private fields do not enter the public
run artifacts. Both GPUs were 0 MiB after the run.

## Phase disposition

| Phase | Audited disposition | Remaining condition |
|---|---|---|
| 0–7 | implementation and scoped acceptance complete | Phase 7 live OS/DB permission enforcement remains a deployment gate |
| 8 | partial | real bounded PIDSMaker run, causal checkpoint lifecycle, artifact parsers, and per-PIDS profiles |
| 9 | synthetic complete; real-data pending | inherits every Phase 8 gate |
| 10 | interfaces complete; formal training blocked | `BLOCKED_BY_SFT_DATASET` until an approved deployable trajectory dataset exists |

## Gates that cannot be bypassed

1. PostgreSQL currently lacks approved distinct `pids_worker` and
   `hidden_evaluator` roles/grants. Creating roles or changing grants is a database
   modification requiring explicit authorization. The superuser is not an
   acceptable runtime substitute.
2. The pinned upstream code fetches a full day before test truncation, consults test
   data during training, imports/calls W&B in training paths, and does not save the
   declared checkpoint. The exact source evidence and proposed isolated patch route
   are in `docs/pidsmaker/COMPATIBILITY_REPORT.md`. No patch may be created or
   applied to the submodule without the required compatibility-patch approval.
3. AutoDL has no `tmux`. Project policy requires it for long training/evaluation;
   installation is an environment change requiring explicit authorization.
4. No approved formal Agent trajectory dataset exists. Synthetic fixtures cannot
   be relabeled as SFT evidence.
5. No PIDS checkpoint has passed save/load, causal provenance, dataset compatibility,
   and independent resource profiling. Registry entries therefore remain visible
   but unverified/unavailable rather than being silently removed.

Accordingly the remaining partial requirements in
`docs/plans/REQUIREMENT_TRACEABILITY.md` are evidence-bearing deferred gates, not
silent omissions: real transductive comparison, live label permissions, real PIDS
tool/artifact traces, memory sensitivity validation, live DB roles, upstream W&B
training compatibility, and formal-run reproducibility/tmux operation.
