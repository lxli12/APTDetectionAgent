# Phase 1 acceptance report

Date: 2026-07-14
Branch: `codex/phase-1-core-schemas`
Requirements: REQ-LABEL-001..004, REQ-TOOL-001..005,
REQ-CONFIG-001..003, REQ-WINDOW-001..003, REQ-MEMORY-001..006,
REQ-EVAL-001..004, REQ-ARTIFACT-001..003, REQ-ENV-004.

## Implemented evidence

- Immutable, strict Pydantic contracts reject undeclared fields.
- Public controller types and privileged hidden-evaluator types use distinct export
  namespaces.
- Window validation enforces aware timestamps, IANA timezone offsets, alignment,
  exact size, increasing `[start,end)` bounds, and consistent sequence numbers.
- Persistent configuration cannot become effective in the current or a past window.
- PIDS identity normalizes ORTHRUS variants and unavailable entries require reasons.
- Causal main configs reject transductive status; thresholds require complete and
  method-consistent provenance.
- LLM-side requests reject command/shell/environment/CUDA fields recursively.
- Runtime memory requires split/scenario/episode scope; released static LTM requires
  sanitizer/provenance, evaluator signature, and human sampling evidence.
- Artifact paths are traversal-free and manifests validate hashes, uniqueness,
  terminal status, and failure provenance.

## Test evidence

The local bundled Python 3.12 runtime provides a compatible Pydantic release without changing the
host environment. The following command passes 50 tests:

```text
PYTHONPATH=src <bundled-python> -m unittest discover -s tests -v
```

Tests include negative cases for hidden labels, teacher rationale, step reward in
held-out, shell/CUDA input, future-effective configuration, malformed windows,
transductive main config, missing checkpoints, path traversal, memory lifecycle,
campaign exclusions, and incomplete failure provenance.

## Dependency and remote status

Read-only AutoDL audit confirms system Python lacks controller dependencies and the
`pids`/`vllm` environments carry different Pydantic versions. The user subsequently
prohibited creation of a new environment and authorized the existing `pids`
environment. ADR 0005 therefore pins its installed Pydantic 2.12.5 while retaining a
process/import boundary between the controller and PIDSMaker. Remote schema smoke is
recorded separately after synchronization.

Process-level evaluator filesystem/database isolation remains assigned to Phase 7;
Phase 1 establishes the enforceable serialization boundary but does not claim the
later runtime boundary is complete.
