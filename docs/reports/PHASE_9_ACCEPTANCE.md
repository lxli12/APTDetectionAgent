# Phase 9 acceptance report — synthetic complete, real-data pending

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001..004,
REQ-WINDOW-001..004, REQ-CONFIG-001..003, REQ-MEMORY-001..007,
REQ-TOOL-001..005, REQ-EVAL-001..006, REQ-ARTIFACT-001..003,
REQ-REPRO-001..003.

## Synthetic acceptance

The Agent-visible scenario in
`src/apt_detection_agent/validation/synthetic.py` processes four contiguous
15-minute `[start,end)` windows. It commits the fast-path prediction before slow
work, invokes one typed availability tool, writes and retrieves episode memory,
schedules a persistent configuration at window 2, applies it only at window 3,
and resets case/episode state at the scenario boundary.

Privileged fixture creation is isolated in
`src/apt_detection_agent/evaluator/synthetic_fixture.py`. The Agent runner never
imports the evaluator namespace. `scripts/run_hidden_evaluator.py` writes full
metrics only under the private root; `scripts/finalize_public_report.py` receives
only `EpisodeMetricsFeedback` and cannot read TP/FP/FN or campaign data.

AutoDL smoke evidence:

- main-project commit: `368d0a252d2afa6a3984df30010e28953243e6e7`;
- PIDSMaker commit: `32602734bc9f896be5fc0f03f0a185c967cd6624`;
- public run: `/root/autodl-tmp/apt-agent/experiments/runs/phase9_synthetic_e2e_20260714_001`;
- private evaluator root:
  `/root/autodl-tmp/apt-agent/evaluator-private/phase9_synthetic_e2e_20260714_001`;
- all invariant checks passed; config history was A, A, A, B;
- private aggregate metrics were campaign coverage 1.0 and unique-node counts
  TP=2, FP=1, FN=0; these values were not returned to the Agent artifacts;
- both GPUs remained at 0 MiB because this fixture does not claim PIDS performance;
- all 154 project tests passed in the existing AutoDL `pids` environment.

The run contains command, Git SHA/diff, environment, resource/config/data/artifact
manifests, stdout/stderr, tool calls, trajectory, predictions, case/memory lifecycle,
sanitized metrics reference, reports, and terminal status. It is explicitly marked
`synthetic_integration_only` and `formal_performance_claim=false`.

## Remaining real-data gate

Phase 9 is not fully complete because its real PIDSMaker scenario depends on the
unsatisfied Phase 8 gates recorded in `docs/reports/PHASE_8_ACCEPTANCE.md`: no
least-privilege `pids_worker`, no bounded `[start,end)` construction query, and no
causal checkpoint save/load path. Synthetic metrics cannot substitute for that
experiment. Live filesystem/database role enforcement also remains pending; path
separation alone is not a production permission boundary.
