# Requirement Traceability Matrix

Status values: `implemented`, `partial`, `planned`, `blocked`. Every implementation
and test path is updated when work lands.

| ID | Invariant | Phase | Implementation evidence | Verification | Status |
|---|---|---:|---|---|---|
| REQ-GOV-001 | Every module, test, and acceptance item cites a requirement ID | 0 | `AGENTS.md`; this matrix | `tests/test_governance.py` | implemented |
| REQ-GOV-002 | Phase completion requires invariant evidence, not only exit code zero | 0 | `IMPLEMENTATION_PLAN.md` | governance review | implemented |
| REQ-GOV-003 | Final design and accepted ADRs are behavioral sources of truth | 0 | `AGENTS.md` | governance checker | implemented |
| REQ-GOV-004 | SFT work is explicitly blocked when no valid dataset exists | 0/10 | plan; experiment protocol | SFT stage negative test | partial |
| REQ-GIT-001 | Tracked code changes locally and reaches server only through push + fast-forward pull | 0 | `AGENTS.md` | remote workflow review | implemented |
| REQ-GIT-002 | Dirty remote worktree stops synchronization; no destructive Git | 0 | `AGENTS.md` | remote script tests | partial |
| REQ-GIT-003 | PIDSMaker remains pinned and unmodified | all | `.gitmodules`; commit pin | submodule status check | implemented |
| REQ-CAUSAL-001 | No future window or event may enter current computation | 3 | planned causal stream | future-event negative tests | planned |
| REQ-CAUSAL-002 | Vocabulary, normalization, IDF, statistics, embeddings, model, and threshold freeze before held-out | 1/3 | planned provenance schemas | forbidden-refit tests | planned |
| REQ-CAUSAL-003 | Current-graph parameter-free features are allowed only after that window arrives | 3 | planned featurizer boundary | timestamp boundary tests | planned |
| REQ-CAUSAL-004 | Transductive runs are labeled compatibility baselines and excluded from main results | 1/2/7 | planned config/result schemas | result-mixing negative test | planned |
| REQ-LABEL-001 | Agent-visible processes cannot access hidden labels or private mappings | 1/3/7 | strict public schemas; separate evaluator namespace | field leakage tests; later permission tests | partial |
| REQ-LABEL-002 | Hidden teacher data is sanitized before student input, rationale, or deployable memory | 1/4/10 | recursive deployable-payload guard | privileged-field negative tests | partial |
| REQ-LABEL-003 | Held-out evaluator returns no online step reward; only episode metrics | 1/7 | split-constrained feedback schemas | feedback-contract tests | partial |
| REQ-LABEL-004 | Trace routing uses deployment-visible evidence only | 1/2/5 | AgentAction evidence IDs; payload guard | hidden-annotation rejection tests | partial |
| REQ-WINDOW-001 | Windows record origin, timezone, size, and `[start,end)` bounds | 1/3 | `schemas/runtime.py:TimeWindow` | alignment/timezone/boundary tests | implemented |
| REQ-WINDOW-002 | Scenario processing is chronological and predictions are append-only | 3/5 | planned stream/ledger | ordering and rewrite tests | planned |
| REQ-WINDOW-003 | Current window uses committed fast-path configuration | 1/5 | `CaseState`; `PendingConfiguration` | state-transition tests | partial |
| REQ-WINDOW-004 | Rolling-range constants are validation candidates, not hard-coded truths | 3/5 | planned trigger config | configuration tests | planned |
| REQ-CONFIG-001 | Persistent reconfiguration takes effect at the next window | 1/5 | effective-window validators | same-window rejection tests | implemented |
| REQ-CONFIG-002 | Held-out selects only frozen ApprovedConfig and thresholds | 1/2/5 | frozen `ApprovedConfig`/threshold schemas | catalog rejection tests in Phase 2 | partial |
| REQ-CONFIG-003 | Threshold records carry method, split, checkpoint, metric, time, and commit provenance | 1 | `ThresholdProvenance` | source/missing-field tests | implemented |
| REQ-PIDS-001 | Registry covers every PIDS/variant at the pinned commit | 2 | planned discovery registry | config/code/test parity | planned |
| REQ-PIDS-002 | Unavailable PIDS remain registered with explicit reasons | 1/2 | `PIDSCapability` availability fields | unavailable retention test | partial |
| REQ-PIDS-003 | ORTHRUS fixed/non-snooped are variants, not new methods | 1/2 | normalized `PIDSRef` | identity negative tests | implemented |
| REQ-PIDS-004 | `feat_inference` is traced internally unless a real Agent decision justifies a tool | 2 | planned pipeline map | stage trace tests | planned |
| REQ-PIDS-005 | PIDSMaker submodule is never directly modified | all | adapter boundary | submodule diff check | implemented |
| REQ-TOOL-001 | LLM emits typed requests and never constructs shell commands | 1/2/5 | `AgentAction`; `ToolRequest` recursive guard | executor-field/unknown-field tests | implemented |
| REQ-TOOL-002 | Executor validates parameter/path/resource allowlists and builds argv | 2 | planned adapter/executor | injection/path escape tests | planned |
| REQ-TOOL-003 | Every tool call records validated args, config/checkpoint, command manifest, timing, output, and artifacts | 1/2 | `ToolResult`; `CommandManifest`; `StageTrace` | schema completeness tests; Phase 2 runtime tests | partial |
| REQ-TOOL-004 | Parallel PIDS selection is scheduled by executor, never CUDA-selected by LLM | 2/5 | planned scheduler | resource admission tests | planned |
| REQ-TOOL-005 | Timeout, nonzero exit, malformed output, and missing artifact fail closed | 2 | planned executor | fake-runner failure tests | planned |
| REQ-MEMORY-001 | Working, episode memory, and case state reset at split/scenario boundaries | 1/4 | explicit split/scenario/episode scope | scope tests; Phase 4 reset tests | partial |
| REQ-MEMORY-002 | Train memory cannot enter validation; validation cannot enter held-out | 1/4 | planned namespace policy | cross-split negative tests | planned |
| REQ-MEMORY-003 | Frozen deployable static LTM may cross splits only as a sanitized training artifact | 1/4 | `StaticLTMSnapshot` release contract | signature/review tests | partial |
| REQ-MEMORY-004 | Runtime held-out memory cannot update static LTM | 1/4 | planned read-only snapshot | write rejection tests | planned |
| REQ-MEMORY-005 | Initial backend is SQLite FTS5 with normalized-hash exact dedup | 4 | planned memory store | retrieval/dedup tests | planned |
| REQ-MEMORY-006 | Conflicts coexist with environment, time, and evidence provenance | 4 | planned conflict records | conflict retention tests | planned |
| REQ-MEMORY-007 | Retrieval budget and candidate cap are validation-tuned engineering defaults | 4/9 | planned retrieval config | sensitivity protocol | planned |
| REQ-EVAL-001 | Main evaluation uses campaign coverage and unique malicious-node TP/FP/FN | 1/7 | privileged `EvaluationRecord` | Phase 7 metric fixtures | partial |
| REQ-EVAL-002 | Node-window, edge, chain, phase, provenance, latency, GPU, and tool-call metrics have separate denominators | 1/7 | distinct metric maps in evaluator schema | Phase 7 denominator tests | partial |
| REQ-EVAL-003 | P@C=100%, MCC, and ADP definitions are versioned | 1/7 | version-linked evaluator record | Phase 7 metric definitions/tests | partial |
| REQ-EVAL-004 | Campaign identity comes from a versioned manifest, not a ground-truth filename | 1/7 | privileged `CampaignManifest` | manifest validation tests | implemented |
| REQ-EVAL-005 | Validation calibrates coverage constraints using agent-level hidden campaigns | 7 | planned evaluator | benign-only rejection test | planned |
| REQ-EVAL-006 | Evaluation cannot feed hidden config search during held-out | 5/7 | planned IPC boundary | feedback leakage tests | planned |
| REQ-ARTIFACT-001 | Every artifact records source config, checkpoint hash, code commit, and producing stage | 1/2 | artifact and run manifests | hash/path/provenance tests | implemented |
| REQ-ARTIFACT-002 | Missing checkpoints produce unavailable status, never fabricated artifacts | 1/2/8 | checkpoint availability schema | missing-checkpoint tests | partial |
| REQ-ARTIFACT-003 | Raw PIDSMaker artifacts are mapped and validated before becoming Agent contracts | 2 | planned artifact map/adapter | malformed artifact tests | planned |
| REQ-RESOURCE-001 | Scheduler uses explicit 32 vCPU/240 GiB/2×24 GiB profile | 0/5 | AutoDL profile | profile validation | partial |
| REQ-RESOURCE-002 | Initial profile uses GPU 0 for vLLM and one GPU PIDS on GPU 1 | 0/5/8 | AutoDL profile | scheduling tests | partial |
| REQ-RESOURCE-003 | Same-GPU concurrency waits for per-PIDS smoke profiles | 5/8 | planned capability profiles | admission rejection test | planned |
| REQ-ENV-001 | `pids` and `vllm` environments remain separate and pinned | 0/6 | ADR and resource profile | environment manifest | implemented |
| REQ-ENV-002 | Controller communicates through subprocess and localhost HTTP, not cross-imports | 1/2/6 | planned adapters | import-boundary tests | planned |
| REQ-ENV-003 | vLLM host, port, base URL, and model path are environment-driven | 6 | planned client config | no-hardcoded-port test | planned |
| REQ-ENV-004 | Controller environment stays minimal and excludes PyTorch/PyG/vLLM | 1 | ADR 0005; Pydantic-only Phase 1 dependency | dependency audit | partial |
| REQ-DB-001 | Admin, PIDS worker, hidden evaluator, and controller have distinct DB privileges | 0/7 | security ADR | role/connection tests | partial |
| REQ-DB-002 | Controller has no private-label database access | 7 | planned evaluator topology | permission test | planned |
| REQ-DB-003 | PostgreSQL 17 data is never auto-migrated, rebuilt, or modified by runtime | 0/2 | AGENTS and ADR | command allowlist test | implemented |
| REQ-WANDB-001 | W&B is disabled, makes no network request, and is not a project dependency | 0/2 | AGENTS; planned compatibility audit | dependency/source tests | partial |
| REQ-REPRO-001 | Runs record exact code, environment, data, config, checkpoint, threshold, command, seed, timing, resources, metrics, and failures | 0/1/5 | experiment protocol; planned manifests | completeness tests | partial |
| REQ-REPRO-002 | Every run has a unique non-overwriting run ID and required local files | 5/8 | planned remote scripts | collision/manifest tests | planned |
| REQ-REPRO-003 | Long runs use owned tmux sessions and leave status/tail/recovery instructions | 5/8 | planned remote scripts | remote smoke | planned |
| REQ-SFT-001 | SFT student data contains no privileged label/rationale leakage | 10 | planned sanitizer | dataset negative tests | planned |
| REQ-SFT-002 | Hidden teacher inputs and student-visible outputs use separate schemas | 1/10 | evaluator namespace and deployable payload guard | boundary tests | partial |
| REQ-SFT-003 | Synthetic fixtures are never reported as formal training evidence | 10 | experiment protocol | report validator | partial |
| REQ-SFT-004 | Missing formal trajectories yields `BLOCKED_BY_SFT_DATASET` | 0/10 | plan | stage status test | partial |
