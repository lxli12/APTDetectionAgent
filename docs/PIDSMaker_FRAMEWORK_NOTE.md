# PIDSMaker Framework Research Note

Requirements: REQ-GOV-003, REQ-PIDS-001..005, REQ-CAUSAL-001..004,
REQ-LABEL-001..004, REQ-TOOL-001..005, REQ-ARTIFACT-001..003,
REQ-RESOURCE-001..003, REQ-ENV-001..004, REQ-WANDB-001,
REQ-REPRO-001..003.

Status: Phase 1 research note. This document describes the PIDSMaker framework and
the repository pinned at commit `32602734bc9f896be5fc0f03f0a185c967cd6624`.
It does not modify PIDSMaker, define an SFT schema, or authorize a real run.

## Evidence order and scope

When sources disagree, this note uses the following order:

1. the pinned PIDSMaker source and configuration actually present in this repository;
2. the maintained [official documentation](https://ubc-provenance.github.io/PIDSMaker/)
   and [official GitHub repository](https://github.com/ubc-provenance/PIDSMaker);
3. Bilot et al., [*Sometimes Simpler is Better: A Comprehensive Analysis of
   State-of-the-Art Provenance-Based Intrusion Detection Systems*](https://www.usenix.org/system/files/usenixsecurity25-bilot.pdf),
   USENIX Security 2025;
4. Bilot, Jiang, and Pasquier, [*PIDSMaker: Building and Evaluating
   Provenance-based Intrusion Detection Systems*](https://arxiv.org/pdf/2601.22983),
   arXiv:2601.22983.

The 2026 framework paper and current website describe a maintained framework that
may be newer than the pinned commit. Their claims are therefore explanatory
evidence, not automatic proof of behavior in the pinned checkout.

## PIDSMaker overall architecture

PIDSMaker is a configurable experiment framework for building and comparing
machine-learning PIDSs over whole-system provenance. Its central contribution is
not one detector algorithm, but a common execution substrate:

- dataset-specific provenance and split configuration;
- a staged, cached preprocessing/training/evaluation pipeline;
- reusable graph transformations, featurizers, encoders, decoders, and objectives;
- one YAML configuration per detector or variant;
- shared inference, thresholding, ground-truth mapping, metrics, visualization,
  tuning, and repeated-run utilities.

The public architecture emphasizes modularity, configurability, cache efficiency,
and extensibility. The pinned implementation realizes these properties through
`pidsmaker/main.py`, `pidsmaker/config/{config,pipeline}.py`, task modules,
component factories, and top-level YAML files in `config/`.

The framework is implemented with Python, PyTorch, PyTorch Geometric, NetworkX,
Gensim/scikit-learn utilities, PostgreSQL-backed input data, filesystem artifacts,
and W&B-integrated experiment logging. In this project W&B remains prohibited;
upstream use is an observed compatibility constraint, not an approved dependency.

## Unified pipeline

### Public seven-stage model versus pinned eight-task implementation

The official paper and documentation describe seven stages. The pinned executable
entrypoint actually schedules eight tasks because it separates feature-model fitting
from applying features to every split:

| Public stage | Pinned task and source | Actual responsibility | Principal output |
|---|---|---|---|
| 1. Construction | `tasks/construction.py` | Read configured provenance, create time-window graphs, attach selected entity/event attributes | Serialized NetworkX graphs and node/index maps |
| 2. Transformation | `tasks/transformation.py` | Copy unchanged graphs or apply undirected, DAG, R-CAID pseudo-graph, or synthetic-attack transformations | Transformed serialized graphs |
| 3. Featurization | `tasks/featurization.py` | Fit Word2Vec, Doc2Vec, FastText, ALaCarte, temporal-RW, or FLASH feature models; deterministic methods do no fitting here | Feature model/corpus artifacts |
| internal 3b | `tasks/feat_inference.py` | Apply the selected feature method and convert graph edges to `CollatableTemporalData` | Per-window `*.TemporalData.simple` files |
| 4. Batching | `tasks/batching.py` | Load and optionally persist train/val/test batches; apply global/intra/inter-graph and TGN preprocessing in data utilities | In-memory or serialized batched graph tensors |
| 5. Training | `tasks/training.py` and `detection/training_methods/training_loop.py` | Build encoder/objectives, optimize self-supervised losses, optionally few-shot tune, and run periodic inference | Model state in memory, per-epoch loss/score artifacts, runtime/resource logs |
| 6. Evaluation | `tasks/evaluation.py` and `detection/evaluation_methods/` | Load inference CSVs, apply threshold/post-processing, join hidden truth, compute metrics and plots, pick an epoch | Node/edge results, score files, metrics and visualizations |
| 7. Triage | `tasks/triage.py` | Optional DepImpact-style tracing over detections | Attack-tracing artifacts |

This distinction matters for Agent control. `feat_inference` is a real cached task
and must appear in provenance/stage traces, but it should not become an Agent tool
unless an actual validated decision exists (REQ-PIDS-004).

### Configuration and cache semantics

Each system YAML selects components and parameters. Configuration inheritance uses
`_include_yml`; CLI dot-notation overrides YAML. `pipeline.py` derives a task path
hash from the task's arguments and upstream task hash. Existing task directories are
treated as completed cache entries; a downstream parameter change reuses earlier
stages, while a change to an upstream parameter changes every dependent path.

This is an experiment cache, not by itself an artifact-integrity contract. The
APT-Agent adapter must additionally record code commit, exact arguments, hashes,
checkpoint identity, producing stage, timing, failure state, and standardized
outputs. Directory existence and exit code alone do not establish correctness.

### Execution modes

`main.py` supports a standard pipeline, repeated/uncertainty experiments, and
hyperparameter tuning. The standard entrypoint always proceeds through evaluation
and triage when their task paths require execution. It is therefore unsuitable as a
deployment-visible detection command: upstream evaluation directly loads ground
truth and emits label-dependent data. The project adapter must invoke approved
boundaries rather than expose the all-stage entrypoint.

## Dataset processing

### Registered datasets and split configuration

The pinned `DATASET_DEFAULT_CONFIG` registers DARPA TC E3/E5 hosts, three OpTC
hosts, and newer ATLASv2/CARBANAKv2 entries. Each dataset record contains database
names, node/relationship counts, `train_dates`, `val_dates`, `test_dates`, ground
truth paths, and `attack_to_time_window` mappings.

The website and repository disagree about the OS of FiveDirections; the project
inventory preserves that as an upstream documentation conflict. The 2026 framework
paper describes 13 DARPA TC/OpTC datasets, whereas the maintained repository and
pinned config additionally contain ATLASv2 and CARBANAKv2 registrations. Static
registration does not prove that a detector/dataset pair is runnable.

### Storage and preprocessing

DARPA/OpTC data is normalized into PostgreSQL tables. Construction queries events
for configured dates, creates entity identifiers and type/label maps, and emits
time-window graphs. The default configuration commonly uses 15-minute construction
windows. The pinned test-mode path still fetches a complete day before truncating
saved edges; it is not a bounded `[start,end)` query and cannot support a formal
minimal-window causal claim without an approved compatibility change.

Dataset splits serve two purposes that must remain distinct:

- PIDS train/validation/test dates are detector-internal partitions;
- APT-Agent training/validation/held-out scenarios are the controller-level split.

Some upstream configurations fit feature representations on `all` or otherwise
consult test data. Such configurations are compatibility baselines, not causal-main
configurations (REQ-CAUSAL-002..004).

## Graph construction

The default builder creates directed temporal provenance graphs whose nodes are
primarily `subject`, `file`, and `netflow` entities and whose edges are timestamped
system events. Selected attributes are detector-specific: type, executable/path,
command line, IP address, and port. Configurations can fuse redundant edges and
select the graph window size.

The graph path is approximately:

`PostgreSQL events → NetworkX MultiDiGraph → optional transformation →
CollatableTemporalData → PyG-ready batches`.

During `feat_inference`, each transformed edge yields source/destination IDs,
timestamp, event label/type encoding, node-type encodings, optional node embeddings,
and an edge `y` value if present. These are serialized as temporal tensors. This raw
representation includes fields used by upstream training/evaluation; it is not an
Agent-visible observation contract and must be sanitized before crossing the label
boundary.

Transformations are material algorithm choices:

- `none` copies construction graphs;
- `undirected` adds reverse edges with the same timestamp;
- `dag` creates a DAG-oriented representation;
- `rcaid_pseudo_graph` identifies roots, adds pseudo-root-to-descendant edges,
  optionally prunes high-fanout pseudo-roots, relabels them, and assigns timestamps;
- the MAGIC-specific graph builder exists, but the pinned `magic.yml` selects
  default construction and no transformation.

## Feature extraction

PIDSMaker separates feature-model fitting from graph vectorization.

| Family | Pinned behavior |
|---|---|
| Learned text features | Word2Vec, Doc2Vec, FastText, ALaCarte, temporal random-walk Word2Vec, and FLASH's node-document Word2Vec fit a feature model on configured splits |
| Deterministic features | Hierarchical feature hashing, node type only, and all-ones require no feature-training task |
| Applied representation | `feat_inference` maps persistent node IDs to vectors, combines node type/embedding and edge type into temporal messages, and processes train/val/test files |

Feature scope is detector-specific and can be non-causal. Examples in the pinned
configs include ORTHRUS Word2Vec on `all`, R-CAID Doc2Vec on `all`, and FLASH's
feature inference constructing node documents from train, validation, and test even
though its Word2Vec vocabulary is trained on train. A formal Agent run must audit
both the fitting split and the application/aggregation time boundary; a
`training_split: train` flag alone is insufficient proof of causality.

## Training and inference interface

### Model composition

`factory.py` builds one shared `Model` from:

- an encoder selected from linear, GraphSAGE, GAT, GIN, sum aggregation,
  graph attention, TGN wrapper, MAGIC GAT, R-CAID GAT, and other components;
- one or more objectives/decoders such as edge-type prediction, node-type
  prediction, node-feature reconstruction, masked feature/structure reconstruction,
  contrastive edge prediction, or optional few-shot classification;
- an optimizer and loss selected from configuration.

`Model.forward` embeds a batch, invokes every configured objective, and returns a
scalar summed loss in training or per-element anomaly losses/scores in inference.
For TGN configurations, the wrapper manages temporal neighbor state and optional
node memory; state is reset before each epoch.

### Actual training loop boundary

The pinned training loop is not a clean `fit(train,val) → frozen checkpoint →
infer(test)` interface:

- it loads train, validation, and test batches together;
- it trains on configured training batches and periodically runs inference on both
  validation and test during epochs;
- the normal `save_model` call is commented out, so successful completion does not
  create the declared checkpoint bundle;
- epoch selection/evaluation uses downstream label-dependent metrics in the normal
  all-stage workflow;
- W&B calls/imports remain in training and evaluation paths.

Therefore PIDSMaker currently provides reusable training/inference *functions*, but
not an accepted causal checkpoint lifecycle for APT-Agent. Missing checkpoints must
remain unavailable and cannot be fabricated (REQ-ARTIFACT-002).

### Inference artifacts

Inference writes one CSV per time interval under validation/test and epoch
directories. Edge-level paths record loss, source, destination, timestamp, and edge
type. Node-level configurations can instead record node loss plus specialized
scores/flags for ThreaTrace, FLASH, or MAGIC. These CSVs are intermediate raw
artifacts; they require a versioned, label-blind parser before becoming Agent tool
results.

## Detector abstraction

PIDSMaker does not define eight independent detector classes with one stable
`fit/predict` protocol. The effective detector abstraction is:

`dataset config + system YAML + shared task pipeline + component factory +
system-specific feature/encoder/evaluation branches`.

This abstraction is powerful for ablations because components can be swapped, but
it has consequences:

- the same system name can describe substantially different behavior after a YAML
  override;
- original-paper behavior may be only partially represented;
- detector output granularity is determined jointly by the objective, inference
  branch, aggregation, evaluation method, and threshold/post-processing;
- comparison requires preserving `source_config_id`, variant, full resolved config,
  upstream commit, dataset, and artifact provenance.

The pinned top-level configurations represent eight canonical PIDS identities:
VELOX, ORTHRUS, MAGIC, FLASH, KAIROS, NODLINK, ThreatRace, and R-CAID. ORTHRUS
`fixed` and `non_snooped` are variants, not additional PIDSs.

## Evaluation

The evaluation task loads raw inference outputs, directly loads ground truth and
campaign/time-window mappings, aggregates edge losses when required, thresholds or
clusters scores, computes predictions, and reports metrics.

Implemented threshold modes include:

- maximum or mean validation loss;
- fixed ThreaTrace threshold `1.5`;
- fixed FLASH threshold `0.53`;
- NODLINK's validation 90th percentile;
- MAGIC's mean score computed from the **test** inference directory;
- optional K-Means over high-scoring nodes for ORTHRUS.

The framework computes confusion-matrix metrics, precision/recall/F1, balanced
accuracy, ROC-AUC, average precision, MCC-related values, ADP, discrimination,
per-attack detections, and precision/recall at full attack coverage. It saves raw
result dictionaries, score pickles, plots, and W&B metrics. `best_adp` can select an
epoch using test-label-dependent evaluation in the upstream workflow.

These outputs are useful for an isolated hidden evaluator or offline teacher, but
are forbidden as deployment-visible Agent observations. In particular, raw
`results.pth`, per-attack TP logs, ADP, confusion counts, ground-truth paths, and
attack-window mappings must not cross the public boundary (REQ-LABEL-001..004).

## Framework strengths

- One resolved configuration captures most detector design decisions.
- Shared preprocessing and evaluation reduce accidental baseline differences.
- Stage hashes enable efficient ablation and reuse.
- Component factories expose meaningful architecture choices.
- Common datasets, labels, metrics, tuning, and repeated runs improve comparative
  research and reveal instability.
- Raw per-window losses provide a useful basis for a future standardized,
  label-blind detection result.

## Framework limitations for APT-Agent integration

- The public seven-stage narrative and pinned eight-task implementation differ.
- The all-stage entrypoint combines detection with hidden-label evaluation/triage.
- Several canonical configs are transductive or otherwise non-causal.
- Training consults test batches during epochs and does not save the expected model
  bundle in the normal path.
- Upstream W&B imports/calls are not optional throughout training/evaluation.
- Real output schemas are Python/Torch/pickle/CSV artifacts rather than stable Agent
  contracts.
- Construction test mode is not an interval-bounded database query.
- Dataset registration and a zero exit code do not establish checkpoint,
  compatibility, causality, resource, or artifact correctness.
- Published hardware/cost results were obtained on configurations and hardware that
  do not automatically transfer to the project's 2×24 GiB RTX 4090 profile.

Accordingly, PIDSMaker should be treated as an executor-owned staged research
backend. The LLM may select only approved high-level requests; it must not construct
CLI commands, choose CUDA devices, read raw evaluation artifacts, or bypass the
frozen config/checkpoint catalog.

## Source map

- Official framework overview: <https://ubc-provenance.github.io/PIDSMaker/>
- Official pipeline documentation: <https://ubc-provenance.github.io/PIDSMaker/pipeline/>
- Official dataset documentation: <https://ubc-provenance.github.io/PIDSMaker/datasets/>
- Official batching documentation: <https://ubc-provenance.github.io/PIDSMaker/features/batching/>
- Official repository: <https://github.com/ubc-provenance/PIDSMaker>
- USENIX Security 2025 study: <https://www.usenix.org/system/files/usenixsecurity25-bilot.pdf>
- PIDSMaker framework paper: <https://arxiv.org/pdf/2601.22983>
- Pinned local implementation: `PIDSMaker/` at
  `32602734bc9f896be5fc0f03f0a185c967cd6624`
