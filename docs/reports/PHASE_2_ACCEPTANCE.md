# Phase 2 acceptance report

Requirements: REQ-CONFIG-002, REQ-PIDS-001..005, REQ-TOOL-001..005,
REQ-ARTIFACT-001..003, REQ-CAUSAL-004, REQ-LABEL-004,
REQ-RESOURCE-002..003, REQ-WANDB-001.

## Scope and decision

Phase 2 implements static PIDSMaker discovery, a complete source-config registry,
the frozen ApprovedConfig selection boundary, safe argv construction, an initial
resource scheduler, deployment-visible tracing, artifact collection, and a
synthetic subprocess runner contract. It does not claim real PIDSMaker inference,
checkpoint validity, dataset compatibility, or per-PIDS artifact parsing.

Real execution remains disabled by default in
`src/apt_detection_agent/pidsmaker/adapter.py`. The blocking upstream facts and
versioned patch route are recorded in
`docs/pidsmaker/COMPATIBILITY_REPORT.md`; in particular, database credentials must
not be supplied in argv or copied from historical scripts.

## Evidence

Local evidence on 2026-07-14:

- bundled Python 3.12.13, Pydantic 2.13.4;
- `PYTHONPATH=src .../python3 -m unittest discover -s tests -v`: 73/73 passed;
- `PYTHONPATH=src .../python3 -m compileall -q src tests`: passed;
- `python3 scripts/check_governance.py`: passed, 66 unique requirements and pinned
  PIDSMaker commit verified;
- `git diff --check`: passed;
- `git -C PIDSMaker status --short`: clean.

The macOS system Python 3.9 lacks Pydantic and is not an approved project runtime;
its collection failure was diagnostic environment evidence, not a code test result
and did not trigger dependency installation.

Remote evidence on 2026-07-14 at main-project commit
`46ece3485f4d1c25c58ffb22446b68f7aa7439eb` and PIDSMaker commit
`32602734bc9f896be5fc0f03f0a185c967cd6624`:

- the pre-pull remote main tree and submodule were clean;
- a temporary AutoDL academic proxy was used only for the fast-forward pull and
  proxy variables were cleared in the same SSH shell;
- existing `pids` environment: Python 3.10.20, Pydantic 2.12.5;
- governance check: passed with 66 requirements and the pinned submodule;
- `compileall`: passed;
- synthetic/unit suite: 73/73 passed in 1.490 seconds.

The smoke did not start PostgreSQL, vLLM, an experiment, or the real PIDSMaker
pipeline and did not install or modify dependencies.

## Acceptance matrix

| Item | Evidence | Status |
|---|---|---|
| all top-level PIDS configs retained | dynamic parity test against `PIDSMaker/config/*.yml` | accepted |
| ORTHRUS variants normalized | registry identity negative/positive tests | accepted |
| datasets discovered from upstream registration | AST literal discovery and parity assertions | accepted |
| causal/transductive distinction explicit | resolved inheritance and active-method tests | accepted as static classification only |
| missing checkpoints retained | unavailable registry test | accepted |
| LLM cannot construct shell/device/path | schema and adapter negative tests | accepted |
| frozen held-out config/checkpoint | catalog and adapter negative tests | accepted |
| synthetic subprocess lifecycle | success, nonzero, start failure, missing artifact, overwrite tests | accepted |
| GPU parallel safety | initial GPU request serialization test | accepted for Phase 2; full scheduler deferred |
| deployment-visible tracing | strict graph schema and hidden-field rejection | accepted |
| W&B disabled boundary | dependency, argv, environment, and source audit | accepted with upstream compatibility gap |
| real inference/checkpoint/data smoke | Phase 8 | deferred, no claim |

## Residual risks

Per-PIDS artifact validators, stage traces from a real run, timeout integration,
checkpoint save/load, PostgreSQL credential injection, label-free inference output,
and measured CPU/GPU profiles remain open. The requirement matrix intentionally
keeps the affected requirements partial rather than treating process success as
scientific acceptance.
