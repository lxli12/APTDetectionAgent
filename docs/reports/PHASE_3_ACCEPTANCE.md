# Phase 3 acceptance report

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001,
REQ-WINDOW-001..004, REQ-CONFIG-001.

## Scope and decision

Phase 3 provides a project-owned causal stream around PIDSMaker-compatible graph
windows. It validates event/window chronology, enforces one append-only formal
prediction per opened window, binds that prediction to the committed fast-path
configuration, records fitted-state provenance, blocks held-out refitting, and
admits current-graph parameter-free features only after the graph arrives.

This phase does not parse a real PIDSMaker graph, select dataset split dates, fit a
real featurizer, or claim that upstream approximate windows are causal. Those
operations require inventory-selected data and later real integration.

## Local evidence

Evidence on 2026-07-14:

- bundled Python 3.12.13, Pydantic 2.13.4;
- Phase 3 focused suite: 18/18 passed;
- full suite: 91/91 passed;
- `compileall`: passed;
- governance: passed with 66 requirement IDs and the pinned PIDSMaker SHA;
- `git diff --check`: passed;
- PIDSMaker submodule status: clean.

Remote evidence: pending commit, push, clean-tree fast-forward pull, and execution
inside the existing `pids` environment. No real pipeline, database, vLLM service,
or experiment is needed for this synthetic temporal acceptance.

## Invariants exercised

| Invariant | Negative/positive evidence | Status |
|---|---|---|
| half-open event membership | event at `end` and future-window event rejected | accepted |
| chronological scenario | unordered events, skipped window, and advance-before-prediction rejected | accepted |
| append-only prediction | replay/rewrite attempt rejected | accepted |
| committed fast path | different current-window config rejected | accepted |
| hidden-label isolation | privileged event attributes and feature output rejected | accepted at schema boundary |
| frozen training state | held-out refit and validation vocabulary fit rejected | accepted |
| validation threshold | usable in later held-out, not in the same validation split | accepted |
| causal main | transductive fitted state rejected; compatibility mode explicit | accepted at state boundary |
| current-graph features | pre-arrival and out-of-window inputs rejected | accepted |
| rolling trigger range | non-validation candidate rejected | accepted |

## Residual risks

Filesystem/database permission isolation remains Phase 7. Real PIDSMaker window
conversion and fitted-artifact smoke remain Phase 8. Compatibility-baseline result
separation still needs evaluator-level negative tests, so REQ-CAUSAL-004 remains
partial rather than overclaimed.
