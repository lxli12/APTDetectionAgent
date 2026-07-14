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
process/import boundary between the controller and PIDSMaker.

## Remote smoke evidence

AutoDL was synchronized from GitHub with a clean-tree `git pull --ff-only` using
AutoDL's shell-scoped academic network acceleration. Proxy variables were unset in
the same shell after synchronization. At commit
`d94a9352ff2cec78af04ae15bab57903e59a9651`, the existing `pids` environment
(Python 3.10.20, Pydantic 2.12.5) passed:

- governance validation with 66 requirement IDs;
- `compileall` for `src` and `tests`;
- all 50 unit and negative tests.

The first remote attempt exposed a Python 3.10 compatibility issue in test code
(`datetime.UTC`, introduced in Python 3.11). Commit `d94a935` replaced it with
`timezone.utc`; the full remote rerun then passed. The server working tree remained
clean and PIDSMaker stayed at the pinned commit.

Result: Phase 1 acceptance criteria are satisfied locally and on AutoDL. Runtime
process/filesystem/database isolation remains correctly assigned to Phase 7; Phase 1
establishes the serialization boundary without claiming that later boundary is complete.
