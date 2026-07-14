# PIDSMaker pipeline map

Requirements: REQ-PIDS-004, REQ-TOOL-001..005, REQ-ARTIFACT-003.

`PIDSMaker/pidsmaker/main.py:7-9` declares the sequence construction →
transformation → featurization → feat_inference → batching → training → evaluation
→ triage. `get_task_to_module` at `PIDSMaker/pidsmaker/main.py:54-99` binds each
stage to its implementation and artifact path. Stage invalidation dependencies are
defined at `PIDSMaker/pidsmaker/config/config.py:515-522`.

| Stage | Upstream implementation | Agent exposure decision |
|---|---|---|
| construction | `PIDSMaker/pidsmaker/tasks/construction.py` | internal traced stage |
| transformation | `PIDSMaker/pidsmaker/tasks/transformation.py` | internal traced stage |
| featurization | `PIDSMaker/pidsmaker/tasks/featurization.py` | internal traced stage |
| feat_inference | `PIDSMaker/pidsmaker/tasks/feat_inference.py` | internal traced stage by default |
| batching | `PIDSMaker/pidsmaker/tasks/batching.py` | internal traced stage |
| training | `PIDSMaker/pidsmaker/tasks/training.py` | catalog preparation only; prohibited in deployment |
| evaluation/detection | `PIDSMaker/pidsmaker/tasks/evaluation.py` | `run_pids_detection` result boundary |
| triage/reconstruction | `PIDSMaker/pidsmaker/tasks/triage.py` | backward/forward trace tools after sanitization |

The Agent does not select arbitrary stages. The adapter records every stage and uses
PIDSMaker restart/cache semantics, but only promotes a stage when a validated Agent
decision exists. In particular, featurizer choice is not yet an Agent action.

Current upstream evaluation loads ground truth directly
(`PIDSMaker/pidsmaker/tasks/evaluation.py:27` via `compute_tw_labels`) and logs
label-dependent metrics. Therefore the upstream evaluation stage cannot be exposed
as a deployment-visible observation without an adapter output sanitizer and later
hidden-evaluator separation.
