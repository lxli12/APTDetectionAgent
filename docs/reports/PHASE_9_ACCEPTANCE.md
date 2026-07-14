# Phase 9 acceptance report — bounded validation integration accepted

Requirements: REQ-CAUSAL-001..004, REQ-LABEL-001..004,
REQ-WINDOW-001..004, REQ-CONFIG-001..003, REQ-MEMORY-001..007,
REQ-TOOL-001..005, REQ-EVAL-001..007, REQ-ARTIFACT-001..003,
REQ-REPRO-001..003.

The synthetic four-window scenario in
`src/apt_detection_agent/validation/synthetic.py` remains accepted only as
protocol evidence. It proves chronological committed predictions, next-window
reconfiguration, episode memory/reset, structured tools, and sanitized evaluator
feedback; it is never a formal performance result.

The bounded real validation run is
`/root/autodl-tmp/apt-agent/experiments/runs/phase9-real-e2e-20260714-002`.
It consumed the Phase 8 frozen score artifacts, calibrated validation quantile
threshold `velox-cadets-val-q0p999-9fd5b64fd65f`, standardized 485 node scores and
22 alerts, and exposed only an episode metric artifact reference to the controller.
The threshold is bound to the frozen checkpoint and cannot be recalibrated in
held-out/test.

Live process isolation is implemented by `scripts/provision_os_isolation.sh` and
`scripts/build_process_runtimes.py`: `apt_agent_controller`, `apt_pids_worker`, and
`apt_hidden_evaluator` are distinct non-login identities; evaluator input and full
metrics live below an evaluator-owned mode-700 root; the controller runtime excludes
the evaluator namespace and private request builder. Permission checks confirmed
that the controller cannot read raw PIDS scores, private requests/metrics, repository
source, or evaluator runtime, and the evaluator cannot modify root-owned runtime
code. PostgreSQL worker and evaluator roles are also distinct.

This is validation integration evidence with `formal_performance_claim=false`, not
held-out performance. Private campaign mappings and TP/FP/FN details remain outside
Agent-visible artifacts. Promotion to held-out/deployment still requires the full
agent-level validation campaign set, frozen routing/policy, and a held-out-approved
bundle.

## Runtime-freeze qualification

The real run above predates the later frozen action/observation/memory contract and
must not be relabeled as a formal frozen-runtime trajectory. The new path passed a
two-window synthetic protocol smoke at
`/root/autodl-tmp/apt-agent/frozen-runtime-runs/frozen-runtime-synthetic-20260714-001`.
It makes no formal or performance claim. A real replay becomes eligible only after
the exact detector/config/dataset/use passes the eight-gate admission record.
