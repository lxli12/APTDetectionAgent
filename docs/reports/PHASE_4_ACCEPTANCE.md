# Phase 4 acceptance report

Requirements: REQ-MEMORY-001..007, REQ-LABEL-002, REQ-REPRO-001,
REQ-CONFIG-001.

## Scope

Phase 4 implements persistent Case State and the fixed SQLite/FTS5 memory harness.
It includes lifecycle namespaces, exact deduplication, structured semantic keys,
lexical retrieval, static-LTM release gates, conflict retention, bounded retrieval,
next-window configuration application, and exact episode reset.

It does not read, migrate, or delete historical Chroma data. Dense embedding and
destructive capacity eviction remain disabled. Retrieval-limit optimality is not
claimed.

## Local evidence

Evidence on 2026-07-14 using bundled Python 3.12.13 and Pydantic 2.13.4:

- Phase 4 focused suite: 17/17 passed;
- full suite: 108/108 passed;
- `compileall`, governance, and `git diff --check`: passed;
- governance verified 66 requirement IDs and the pinned PIDSMaker commit;
- PIDSMaker submodule status: clean.

Focused tests cover:

- FTS5 retrieval and normalized-content deduplication;
- split/scenario/episode isolation and reset;
- static LTM visibility, immutability, and privileged-text rejection;
- conflict coexistence and evidence retention;
- token/candidate budgets without capacity eviction;
- Case State persistence and next-window-only configuration activation.

Remote evidence on 2026-07-14 at main-project commit
`f78af969cea752870fee08f18fee63d9f2b255c9` and pinned PIDSMaker commit:

- pre-pull remote tree was clean and synchronization was fast-forward only;
- the temporary AutoDL academic proxy was cleared in the same SSH shell;
- governance and `compileall` passed in the existing `pids` environment;
- full suite: 108/108 passed in 1.639 seconds.

No PostgreSQL service, PIDSMaker pipeline, vLLM service, or experiment was started;
no dependency or Conda environment was modified.

## Post-acceptance sensitivity harness

`scripts/run_memory_retrieval_sensitivity.py` later added the missing
evaluator-private grid harness and aggregate-only result contract. Its synthetic
fixture proves path, split, relevance-reference, candidate-grid, and no-optimality
guards, but it deliberately makes no 2048/20 selection. REQ-MEMORY-007 remains
partial until a formal validation relevance manifest and prespecified review rule
are available.
