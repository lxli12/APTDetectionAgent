# Script layout

Requirement mapping: REQ-REPRO-001..003, REQ-GIT-001..003.

Formal `train_agent.sh`, `test_agent.sh`, and `scripts/remote/` owned-run tools are
delivered in their mapped implementation phases.

`pidsmaker_stage_runner.py` is the Phase 8 subprocess boundary for a label-free
PIDSMaker preprocessing prefix. It is executed only in the `pids` environment by a
validated executor. It stops no later than `feat_inference`; it is not a replacement
for the hidden evaluator and must not be invoked as PIDSMaker's all-stage CLI.
