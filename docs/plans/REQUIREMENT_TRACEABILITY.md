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
| REQ-CAUSAL-001 | No future window or event may enter current computation | 3 | `data/stream.py`; `data/causal.py` | future/boundary/ordering negative tests | implemented |
| REQ-CAUSAL-002 | Vocabulary, normalization, IDF, statistics, embeddings, model, and threshold freeze before held-out | 1/3 | `data/causal.py:FittedStateArtifact` | split/refit/freeze-cutoff tests | implemented |
| REQ-CAUSAL-003 | Current-graph parameter-free features are allowed only after that window arrives | 3 | `data/causal.py:CausalFeatureBoundary` | arrival and current-event timestamp tests | implemented |
| REQ-CAUSAL-004 | Transductive runs are labeled compatibility baselines and excluded from main results | 1/2/3/7 | config/result schemas; fitted-state causal-main gate | transductive state rejection; evaluator result-mixing test deferred | partial |
| REQ-LABEL-001 | Agent-visible processes cannot access hidden labels or private mappings | 1/3/7 | strict public schemas; `VisibleEvent`; separate evaluator namespace | nested event/feature leakage tests; later permission tests | partial |
| REQ-LABEL-002 | Hidden teacher data is sanitized before student input, rationale, or deployable memory | 1/4/10 | recursive deployable-payload guard | privileged-field negative tests | partial |
| REQ-LABEL-003 | Held-out evaluator returns no online step reward; only episode metrics | 1/7 | split-constrained feedback schemas; evaluator IPC | subprocess/public-payload tests | implemented |
| REQ-LABEL-004 | Trace routing uses deployment-visible evidence only | 1/2/5/7 | AgentAction evidence IDs; strict trace/controller guards | hidden annotation/rationale rejection tests | implemented |
| REQ-WINDOW-001 | Windows record origin, timezone, size, and `[start,end)` bounds | 1/3 | `schemas/runtime.py:TimeWindow` | alignment/timezone/boundary tests | implemented |
| REQ-WINDOW-002 | Scenario processing is chronological and predictions are append-only | 3/5 | `data/stream.py:CausalWindowStream` | multi-window, skip, advance, replay/rewrite tests | implemented |
| REQ-WINDOW-003 | Current window uses committed fast-path configuration | 1/3/5 | `CaseState`; `PendingConfiguration`; causal stream | prediction/config mismatch test | implemented |
| REQ-WINDOW-004 | Rolling-range constants are validation candidates, not hard-coded truths | 3/5 | `data/causal.py:RollingRangeCandidate` | non-validation source rejection | implemented |
| REQ-CONFIG-001 | Persistent reconfiguration takes effect at the next window | 1/5 | effective-window validators | same-window rejection tests | implemented |
| REQ-CONFIG-002 | Held-out selects only frozen ApprovedConfig and thresholds | 1/2/5 | `schemas/pids.py`; `pidsmaker/tools.py:ApprovedConfigCatalog` | schema and frozen-catalog rejection tests | implemented |
| REQ-CONFIG-003 | Threshold records carry method, split, checkpoint, metric, time, and commit provenance | 1 | `ThresholdProvenance` | source/missing-field tests | implemented |
| REQ-PIDS-001 | Registry covers every PIDS/variant at the pinned commit | 2 | `pidsmaker/discovery.py`; `docs/pidsmaker/MODEL_INVENTORY.md` | dynamic config/dataset/variant parity tests | implemented |
| REQ-PIDS-002 | Unavailable PIDS remain registered with explicit reasons | 1/2 | `PIDSCapability`; discovery checkpoint inventory | missing-root retains all entries test | implemented |
| REQ-PIDS-003 | ORTHRUS fixed/non-snooped are variants, not new methods | 1/2 | normalized `PIDSRef` | identity negative tests | implemented |
| REQ-PIDS-004 | `feat_inference` is traced internally unless a real Agent decision justifies a tool | 2 | `docs/pidsmaker/PIPELINE_MAP.md`; discovery stage map | internal-stage registry test | implemented |
| REQ-PIDS-005 | PIDSMaker submodule is never directly modified | all | adapter boundary | submodule diff check | implemented |
| REQ-TOOL-001 | LLM emits typed requests and never constructs shell commands | 1/2/5 | `AgentAction`; `ToolRequest` recursive guard | executor-field/unknown-field tests | implemented |
| REQ-TOOL-002 | Executor validates parameter/path/resource allowlists and builds argv | 2 | `pidsmaker/adapter.py` | override, path, checkpoint, shell-boundary tests | implemented |
| REQ-TOOL-003 | Every tool call records validated args, config/checkpoint, command manifest, timing, output, and artifacts | 1/2/8 | `ToolResult`; `CommandManifest`; Phase 2 adapter; safe stage summary | synthetic runtime artifacts and stage-runner contract tests; real PIDS trace deferred | partial |
| REQ-TOOL-004 | Parallel PIDS selection is scheduled by executor, never CUDA-selected by LLM | 2/5 | PIDSMaker tool scheduler; `controller/scheduler.py` | GPU assignment/serialization and hidden CUDA tests | implemented |
| REQ-TOOL-005 | Timeout, nonzero exit, malformed output, and missing artifact fail closed | 2/8 | `pidsmaker/adapter.py`; `scripts/pidsmaker_stage_runner.py` | adapter failure tests; stage path/override/env/overwrite negative tests; real typed parser deferred | partial |
| REQ-MEMORY-001 | Working, episode memory, and case state reset at split/scenario boundaries | 1/4 | `memory/store.py:CaseMemoryStore`; scoped schemas | exact episode reset tests | implemented |
| REQ-MEMORY-002 | Train memory cannot enter validation; validation cannot enter held-out | 1/4 | `MemoryNamespace`; runtime write scope gate | cross-split/scenario negative tests | implemented |
| REQ-MEMORY-003 | Frozen deployable static LTM may cross splits only as a sanitized training artifact | 1/4 | `StaticLTMSnapshot`; `StaticLTMSanitizer` | signature/review/schema/leakage tests | implemented |
| REQ-MEMORY-004 | Runtime held-out memory cannot update static LTM | 1/4 | static snapshot loader; runtime write rejection | static immutability/reset survival tests | implemented |
| REQ-MEMORY-005 | Initial backend is SQLite FTS5 with normalized-hash exact dedup | 4 | `memory/store.py:MemoryStore` | FTS retrieval and normalized dedup tests | implemented |
| REQ-MEMORY-006 | Conflicts coexist with environment, time, and evidence provenance | 4 | semantic key plus explicit conflict/evidence fields | conflict coexistence/unknown-target tests | implemented |
| REQ-MEMORY-007 | Retrieval budget and candidate cap are validation-tuned engineering defaults | 4/9 | `RetrievalPolicy` with unvalidated status | cap/budget/false-optimal-claim tests; sensitivity experiment deferred | partial |
| REQ-EVAL-001 | Main evaluation uses campaign coverage and unique malicious-node TP/FP/FN | 1/7 | `evaluator/engine.py` privileged engine | exact synthetic metric fixture | implemented |
| REQ-EVAL-002 | Node-window, edge, chain, phase, provenance, latency, GPU, and tool-call metrics have separate denominators | 1/7 | distinct private metric maps | denominator-isolation tests | implemented |
| REQ-EVAL-003 | P@C=100%, MCC, and ADP definitions are versioned | 1/7 | `agent-eval-v1`; metric protocol | numeric fixtures and tie-safe ranking | implemented |
| REQ-EVAL-004 | Campaign identity comes from a versioned manifest, not a ground-truth filename | 1/7 | privileged `CampaignManifest` | manifest validation tests | implemented |
| REQ-EVAL-005 | Validation calibrates coverage constraints using agent-level hidden campaigns | 7 | nonempty versioned campaign input gate | benign-only rejection; calibration workflow deferred | partial |
| REQ-EVAL-006 | Evaluation cannot feed hidden config search during held-out | 5/7 | private evaluator process and artifact-reference feedback | subprocess leakage/overwrite tests | implemented |
| REQ-ARTIFACT-001 | Every artifact records source config, checkpoint hash, code commit, and producing stage | 1/2 | artifact and run manifests | hash/path/provenance tests | implemented |
| REQ-ARTIFACT-002 | Missing checkpoints produce unavailable status, never fabricated artifacts | 1/2/8 | checkpoint schema; discovery availability | missing-checkpoint retention tests | implemented |
| REQ-ARTIFACT-003 | Raw PIDSMaker artifacts are mapped and validated before becoming Agent contracts | 2/8 | artifact map; compatibility report; stage runner | missing-artifact/stage-boundary tests; real per-PIDS parsers deferred | partial |
| REQ-RESOURCE-001 | Scheduler uses explicit 32 vCPU/240 GiB/2×24 GiB profile | 0/5 | AutoDL YAML; `controller/scheduler.py` | profile load and quota rejection tests | implemented |
| REQ-RESOURCE-002 | Initial profile uses GPU 0 for vLLM and one GPU PIDS on GPU 1 | 0/5/8 | explicit executor assignments | separate-device lease test | implemented |
| REQ-RESOURCE-003 | Same-GPU concurrency waits for per-PIDS smoke profiles | 5/8 | one-unknown-workload admission gate | second same-GPU PIDS rejection | implemented |
| REQ-ENV-001 | `pids` and `vllm` environments remain separate and pinned | 0/6 | ADR and resource profile | environment manifest | implemented |
| REQ-ENV-002 | Controller communicates through subprocess and localhost HTTP, not cross-imports | 1/2/6 | PIDSMaker subprocess adapter; `llm/vllm_client.py` | transport/import-boundary tests | implemented |
| REQ-ENV-003 | vLLM host, port, base URL, and model path are environment-driven | 6 | `VLLMConfig.from_environment` | alternate-port, localhost, URL validation tests | implemented |
| REQ-ENV-004 | Controller environment stays minimal and excludes PyTorch/PyG/vLLM | 1/6 | ADR 0005; stdlib HTTP client | dependency and runtime-import tests | implemented |
| REQ-DB-001 | Admin, PIDS worker, hidden evaluator, and controller have distinct DB privileges | 0/7 | security ADR; `DatabaseRolePolicy` | policy separation tests; live roles not created | partial |
| REQ-DB-002 | Controller has no private-label database access | 7 | evaluator filesystem IPC; role policy | path/public-payload tests; live permission test deferred | partial |
| REQ-DB-003 | PostgreSQL 17 data is never auto-migrated, rebuilt, or modified by runtime | 0/2 | AGENTS and ADR | command allowlist test | implemented |
| REQ-WANDB-001 | W&B is disabled, makes no network request, and is not a project dependency | 0/2/8 | AGENTS; W&B audit; disabled adapter environment; preprocessing runner bypasses eager W&B imports | dependency/source/argv/stage allowlist tests; upstream training compatibility remains | partial |
| REQ-REPRO-001 | Runs record exact code, environment, data, config, checkpoint, threshold, command, seed, timing, resources, metrics, and failures | 0/1/5 | experiment protocol; planned manifests | completeness tests | partial |
| REQ-REPRO-002 | Every run has a unique non-overwriting run ID and required local files | 5/8 | stage runner direct-child/non-overwrite gate; remote scripts planned | stage-runner collision tests; complete run-directory tests deferred | partial |
| REQ-REPRO-003 | Long runs use owned tmux sessions and leave status/tail/recovery instructions | 5/8 | planned remote scripts | remote smoke | planned |
| REQ-SFT-001 | SFT student data contains no privileged label/rationale leakage | 10 | planned sanitizer | dataset negative tests | planned |
| REQ-SFT-002 | Hidden teacher inputs and student-visible outputs use separate schemas | 1/10 | evaluator namespace and deployable payload guard | boundary tests | partial |
| REQ-SFT-003 | Synthetic fixtures are never reported as formal training evidence | 10 | experiment protocol | report validator | partial |
| REQ-SFT-004 | Missing formal trajectories yields `BLOCKED_BY_SFT_DATASET` | 0/10 | plan | stage status test | partial |
