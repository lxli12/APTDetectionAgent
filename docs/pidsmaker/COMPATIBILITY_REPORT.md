# PIDSMaker compatibility report

Requirements: REQ-PIDS-005, REQ-TOOL-002..005, REQ-ARTIFACT-002..003,
REQ-LABEL-001..004, REQ-WANDB-001, REQ-DB-003.

Baseline: PIDSMaker commit
`32602734bc9f896be5fc0f03f0a185c967cd6624`. This report describes adapter
boundaries; it does not authorize or apply a submodule modification.

| Gap | Source evidence | Current safe behavior | Proposed compatibility route |
|---|---|---|---|
| Database password is an upstream CLI argument with a literal default | `PIDSMaker/pidsmaker/config/pipeline.py:124-143` | real adapter execution defaults disabled; credentials are rejected as Agent overrides and never written to `command.txt` | versioned patch series in an isolated build copy: read a named environment variable or descriptor without placing the secret in argv |
| W&B imports are mandatory even when logging is disabled | `PIDSMaker/pidsmaker/main.py:20`; `PIDSMaker/pidsmaker/detection/training_methods/training_loop.py:18`; `PIDSMaker/pidsmaker/tasks/evaluation.py:3`; `PIDSMaker/pidsmaker/tasks/triage.py:5` | omit `--wandb`, force disabled mode, use local structured logs; no install/login/network action | versioned patch series making the logger optional; no fake package and no global import monkey patch |
| Normal training does not save the declared checkpoint bundle | `PIDSMaker/pidsmaker/detection/training_methods/training_loop.py:221-222`; bundle loader/saver at `PIDSMaker/pidsmaker/utils/data_utils.py:868-906` | registry remains `unverified`/`unavailable`; success exit never fabricates checkpoint availability | isolated patch adds explicit, tested save/load lifecycle and content hashing |
| Evaluation reads ground truth and produces label-dependent output | `PIDSMaker/pidsmaker/tasks/evaluation.py:23`; `PIDSMaker/pidsmaker/detection/evaluation_methods/node_evaluation.py:411-424` | raw evaluation output is not a deployment-visible observation | split detection-score production from hidden evaluation; evaluator receives raw score references through a private boundary |
| The upstream entrypoint always continues through evaluation and triage | `PIDSMaker/pidsmaker/main.py:91-128` | never use the all-stage entrypoint as a deployment detection command | `scripts/pidsmaker_stage_runner.py` permits only construction through `feat_inference` and imports individual task files without executing the task-package initializer |
| Upstream `--test_mode` still fetches a complete day before truncating saved edges | `PIDSMaker/pidsmaker/preprocessing/build_graph_methods/build_default_graphs.py:238-322,451-462` | do not describe test mode as a bounded interval query | versioned compatibility change must add parameterized `[start,end)` SQL bounds before a real minimal-window smoke |
| Training consults test data during epochs and has unconditional W&B calls | `PIDSMaker/pidsmaker/detection/training_methods/training_loop.py:224-264` | safe stage runner stops before training | versioned patch must create a train/validation-only checkpoint-producing path; hidden/test inference is a later frozen-model operation |
| Upstream windows/artifact caches encode compatibility semantics | `PIDSMaker/pidsmaker/config/config.py:515-522`; `PIDSMaker/pidsmaker/config/pipeline.py:240-320` | main experiment requires project-owned `[start,end)` window and provenance contracts | adapter maps a frozen ApprovedConfig and exact project window to upstream inputs; original semantics stay compatibility-only |
| OpTC config and restored database names disagree | `PIDSMaker/pidsmaker/config/config.py:196-249`; AutoDL has `optc_h201`, not requested `optc_201` | registry retains the dataset as unavailable with a reason | use an approved main-project database mapping; do not rename or recreate a database automatically |
| Dataset registration does not prove runnable support | `PIDSMaker/pidsmaker/config/config.py:3-500`; CLI validation at `PIDSMaker/pidsmaker/config/pipeline.py:375-379` | every PIDS/dataset pair begins unverified and remains visible | Phase 8 performs isolated checkpoint/data/resource smoke profiling before availability promotion |

## Patch decision gate

The preferred route is a main-project-maintained, versioned patch series applied
only to an isolated worktree or build artifact. A long-lived fork is considered
only if the patch becomes large or repeatedly conflicts with the pinned upstream.
Before any patch is created, its exact diff, affected requirements, rollback path,
and acceptance tests must be approved. The fixed submodule checkout remains clean.

The preprocessing prefix now has a credential-from-environment, W&B-disabled,
label-output-sanitized runner at `scripts/pidsmaker_stage_runner.py`. Real execution
still remains disabled because AutoDL has no `pids_worker` role, no approved worker
credential, no interval-bounded construction query, and no checkpoint. Activating
the `pids` Conda environment is permitted, but it does not relax those boundaries.
