# Script layout

Requirement mapping: REQ-REPRO-001..003, REQ-GIT-001..003.

Formal `train_agent.sh`, `test_agent.sh`, and `scripts/remote/` owned-run tools are
delivered in their mapped implementation phases.

`pidsmaker_stage_runner.py` is the Phase 8 subprocess boundary for a label-free
PIDSMaker preprocessing prefix. It is executed only in the `pids` environment by a
validated executor. It stops no later than `feat_inference`; it is not a replacement
for the hidden evaluator and must not be invoked as PIDSMaker's all-stage CLI.

`train_agent.sh` exposes all required training stages and records explicit blockers
instead of silently skipping them. `test_agent.sh` implements the complete synthetic
protocol and a fail-closed real-data preflight. `build_sft_dataset.py` and
`train_sft.py` enforce teacher/student roots, sanitization, hashes, partitions, and
dry-run/no-checkpoint semantics.

The `remote/` commands start, inspect, tail, summarize, or stop only owned tmux
sessions. The current AutoDL server has no tmux, so `start_run.sh` intentionally
returns `BLOCKED_BY_MISSING_TMUX` until installation is separately approved.
