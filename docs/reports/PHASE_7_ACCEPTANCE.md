# Phase 7 acceptance report

Requirements: REQ-LABEL-001..004, REQ-EVAL-001..007, REQ-DB-001..003.

## Scope

Phase 7 implements versioned hidden metrics, private/public filesystem IPC, strict
feedback contracts, and database-role policy validation. It does not create or
modify PostgreSQL roles, schemas, or data.

## Local evidence

Evidence on 2026-07-14:

- Phase 7 focused suite: 13/13 passed;
- full suite: 142/142 passed after the tie-safe metric adjustment;
- separate-process fixture emitted only an episode/artifact reference publicly;
- numeric fixtures verify campaign, unique-node, P@C=100%, MCC, ADP, occurrence,
  edge, chain, phase, evidence, and efficiency calculations;
- path escape, artifact overwrite, benign-only campaign calibration, role sharing,
  deployment dependency, and private-feedback leakage are rejected;
- governance and compile checks pass; PIDSMaker remains clean.

Local `compileall`, governance, and diff checks passed with 66 requirement IDs and
the pinned, clean PIDSMaker submodule.

Remote evidence on 2026-07-14 at commit
`5e7a520aaa50f7b40c6a8f4388bacfd66d70b3b6`:

- clean-tree fast-forward synchronization succeeded;
- governance and compile checks passed in the existing `pids` environment;
- full suite: 142/142 passed in 1.973 seconds;
- no PostgreSQL service, role, schema, or data was changed.

## Residual deployment gate

The filesystem users and PostgreSQL grants were subsequently provisioned and
verified on AutoDL with separate `apt_agent_controller`, `apt_pids_worker`, and
`apt_hidden_evaluator` identities and distinct database roles. The controller was
denied the PIDS secret, raw PIDS artifacts, evaluator runtime, and evaluator-private
files. Runtime code does not create roles or alter the PostgreSQL 17 cluster;
`scripts/postgres/provision_roles.sh` remains a separately authorized administrative
operation. REQ-DB-001/002 are therefore implemented, while future schema changes
still require explicit approval.

## Post-acceptance metric completion audit

The 2026-07-14 completion audit introduced `agent-eval-v2` in
`src/apt_detection_agent/evaluator/engine.py`. It retains all v1 primary metrics and
adds separately denominated campaign delay, alert-volume/score stability, LLM
efficiency, and control-behavior maps required by the final design. Negative tests
reject unknown campaign delay keys, incoherent window series, and impossible cache
counters. This schema evolution does not reinterpret or overwrite historical v1
artifacts.
