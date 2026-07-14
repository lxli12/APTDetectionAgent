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

Remote evidence on 2026-07-14 at main-project commit
`9f21535abce42b959d7f76571e7da11c7056ad1d` and PIDSMaker commit
`32602734bc9f896be5fc0f03f0a185c967cd6624`:

- pre-pull main tree and PIDSMaker submodule were clean;
- GitHub synchronization was a fast-forward pull; the temporary AutoDL academic
  proxy was cleared in the same SSH shell;
- governance and `compileall` passed in the existing `pids` environment;
- full suite: 91/91 passed in 1.618 seconds.

The smoke did not start a real pipeline, PostgreSQL, vLLM, or an experiment and did
not install or modify any dependency.

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
