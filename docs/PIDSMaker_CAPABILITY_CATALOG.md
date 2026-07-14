# PIDSMaker PIDS Capability Catalog

Requirements: REQ-GOV-003, REQ-PIDS-001..005, REQ-CAUSAL-002..004,
REQ-LABEL-001..004, REQ-CONFIG-002..003, REQ-TOOL-001..005,
REQ-ARTIFACT-001..003, REQ-RESOURCE-001..003, REQ-REPRO-001.

Status: Phase 1 research catalog for PIDSMaker commit
`32602734bc9f896be5fc0f03f0a185c967cd6624`. Capability claims describe the
pinned implementation first and original papers second. No PIDS is currently
promoted to runnable/approved status by this document.

## How to read this catalog

The official repository lists eight PIDSs: VELOX, ORTHRUS, MAGIC, FLASH, KAIROS,
NODLINK, ThreatRace, and R-CAID. The pinned config directory contains those eight,
plus two ORTHRUS variants (`orthrus_fixed`, `orthrus_non_snooped`). The variants
remain ORTHRUS configurations rather than additional systems.

“Output” below means the actual PIDSMaker output path, not the broader output
promised by an original end-to-end system. In the pinned framework, most detectors
ultimately produce per-edge or per-node losses/scores, then the evaluation task
joins labels and produces metrics. Attack graphs, attribution reports, and root
causes from original papers are not assumed unless their implementation exists in
the pinned pipeline.

“Computational cost” separates architectural cost from measured cost. This project
has not completed independent per-PIDS profiling on its 2×24 GiB RTX 4090 resource
profile; published times on GA100 or other hardware are context, not a project
runtime guarantee.

## Capability summary

| PIDS | Pinned representation/model | Pinned detection output | Causality/status warning |
|---|---|---|---|
| VELOX | Train-only Word2Vec, linear encoder, edge-type prediction | Edge losses aggregated to node scores, max-validation threshold | Causal candidate only; checkpoint unavailable |
| ORTHRUS | Word2Vec, TGN without memory, graph attention, edge-type prediction | Node scores from edge losses; max-validation threshold and optional K-Means | Default fits Word2Vec on all splits; use explicit variant identity |
| MAGIC | Node types, MAGIC GAT encoder/decoder, masked feature and structure reconstruction | Per-node KNN-style `magic_score` and thresholded nodes | Threshold/statistics use test embeddings/data; compatibility baseline only |
| FLASH | FLASH Word2Vec/positional embedding, GraphSAGE, node-type prediction | Per-node confidence score and fixed threshold | Original embedding DB/XGBoost path absent; feature inference scans all splits |
| KAIROS | Hierarchical hashing, stateful TGN + graph attention, edge-type prediction | In current config, edge losses aggregated to node scores | Original queue detector/investigation not selected; compatibility baseline |
| NODLINK | Undirected graph, train-only FastText, sum aggregation, variational decoder, node-feature reconstruction | Node reconstruction scores, validation 90th-percentile threshold | Original online cache/STP attack graph absent |
| ThreatRace | Node type + edge distribution, GraphSAGE, node-type prediction | Per-node prediction ratio/flag and fixed threshold | Original multi-model/retraining/tracing behavior absent |
| R-CAID | Pseudo-root graph, Doc2Vec, R-CAID GAT, node-type prediction | Per-node loss aggregated with max-validation threshold | Doc2Vec fits all splits; original clustering/root-cause output absent |

## VELOX

### Original paper

VELOX is introduced in Bilot et al., [*Sometimes Simpler is Better: A
Comprehensive Analysis of State-of-the-Art Provenance-Based Intrusion Detection
Systems*](https://www.usenix.org/system/files/usenixsecurity25-bilot.pdf), USENIX
Security 2025. It is not a separate paper/system repository in the evidence used
here; it is the lightweight detector derived from the paper's ablation study.

### Purpose

VELOX tests whether a simple pairwise event model can outperform complex GNN PIDSs.
It is an anomaly detector: learn normal edge/event types from benign provenance,
then use edge-type prediction error as anomaly evidence. It is not an attack
reconstruction or root-cause-analysis system.

### PIDSMaker module location

- configuration: `PIDSMaker/config/velox.yml`, inheriting
  `orthrus_non_snooped.yml` and `orthrus.yml`;
- text features: `pidsmaker/featurization/featurization_methods/featurization_word2vec.py`
  and `feat_inference_methods/feat_inference_word2vec.py`;
- linear encoder: `pidsmaker/encoders/linear_encoder.py`, selected by
  `factory.py` when encoder method is `none`;
- objective/decoder: `objectives/predict_edge_type.py` and the configured edge MLP;
- inference/evaluation: `detection/training_methods/inference_loop.py` and
  `detection/evaluation_methods/node_evaluation.py`.

### Input

Default PIDSMaker construction graphs use process type/path/command line, file
type/path, netflow type/IP/port, event type, endpoint node types, and timestamps.
Word2Vec is inherited from the non-snooped ORTHRUS variant and fitted on the train
split. Intra-graph batching uses 1,024-edge batches; VELOX removes TGN neighbor
precomputation.

### Output

The model outputs a cross-entropy loss for each event's predicted edge type.
PIDSMaker writes edge loss CSVs, aggregates incident losses to node anomaly scores,
and applies the maximum validation loss as threshold. Standard evaluation produces
node IDs, scores/predictions, raw result files, metrics, and plots. Only a sanitized
score/alert summary is potentially Agent-visible; label-derived evaluation is not.

### Training requirement

It requires a train-only Word2Vec model and self-supervised edge-type prediction on
benign training graphs. The pinned loop does not create a usable checkpoint because
normal checkpoint saving is commented out.

### Inference behavior

For each event, endpoint embeddings pass through a linear encoder and an oriented
edge decoder. High edge-type prediction loss indicates an unusual interaction.
PIDSMaker then reduces edge evidence to node scores. No graph-message-passing state,
attack tracing, or online memory is used.

### Computational cost

Architecturally this is the lightest registered detector: Word2Vec plus linear/MLP
operations, without GNN neighborhood aggregation or TGN memory. The original study
reports roughly 2,400 edges/s and low average CPU use in its real-time experiment,
but those measurements are not a profile of the pinned project environment.

### Strengths

- Simple, comparatively interpretable pairwise anomaly signal.
- Low expected inference and GPU-memory cost.
- Train-only feature fitting in the inherited non-snooped configuration.
- Strong candidate for a fast-path baseline when an approved checkpoint exists.

### Limitations

- Limited structural/long-range temporal modeling; no reconstruction or attribution.
- Depends on text embeddings and OOV handling.
- Node alerts are post-hoc aggregation of edge losses rather than native node
  classification.
- Current project has no approved checkpoint or real parser/profile.

### Possible Agent tool usage

An Agent could consider an approved VELOX configuration for low-cost routine
detection, as a fast comparison against a heavier PIDS, or when resource pressure
rules out stateful GNNs. It should not select VELOX when the requested outcome is an
attack path/root cause, and it must not infer that a low-cost model is sufficient
without deployment-visible score, environment, and availability evidence.

## ORTHRUS

### Original paper

Jiang et al., [*ORTHRUS: Achieving High Quality of Attribution in
Provenance-based Intrusion Detection Systems*](https://www.usenix.org/system/files/conference/usenixsecurity25/sec25cycle1-prepub-103-jiang-baoxiang.pdf),
USENIX Security 2025.

### Purpose

ORTHRUS targets fine-grained node anomaly detection followed by dependency-based
attack reconstruction. Its original contribution is attribution quality: identify a
small set of anomalous seed nodes and reconstruct concise causal attack summaries.
PIDSMaker's detector portion is implemented more fully than its analyst-facing
reconstruction outcome.

### PIDSMaker module location

- configurations: `config/orthrus.yml`, `config/orthrus_non_snooped.yml`, and
  `config/orthrus_fixed.yml`;
- Word2Vec: `featurization_word2vec.py` and `feat_inference_word2vec.py`;
- temporal preprocessing: batching/TGN utilities in `utils/data_utils.py`;
- encoder: `encoders/tgn_encoder.py` wrapping `encoders/graph_attention.py`;
- objective: `objectives/predict_edge_type.py` with an edge MLP;
- node/edge evaluation: `evaluation_methods/node_evaluation.py` and
  `edge_evaluation.py`;
- optional shared tracing implementation: `triage/tracing_methods/depimpact.py`
  (not enabled in the shown canonical config).

### Input

Directed temporal construction graphs with process type/path/cmd, file type/path,
netflow type/IP/port, event type, and timestamps. The canonical config uses
Word2Vec, 1,024-edge batches, a last-neighbor graph (20 neighbors, one hop), and
node/edge type/message features.

### Output

The model produces per-edge edge-type prediction losses. Canonical node evaluation
aggregates source and destination incident losses, thresholds at maximum validation
loss, and optionally applies K-Means to the top 30 candidates. It emits scored node
results and label-dependent evaluation artifacts. `orthrus_fixed` switches to
edge-level evaluation. The pinned canonical pipeline does not automatically emit the
original paper's concise attack-summary graphs.

### Training requirement

Self-supervised edge-type prediction on training graphs, plus a fitted text
embedding. The default `orthrus.yml` fits Word2Vec on `all`, which is transductive.
`orthrus_non_snooped.yml` changes feature fitting to train and disables K-Means.
`orthrus_fixed.yml` inherits the non-snooped variant, uses node type only, fixes
specific graph/TGN reindexing behavior, and evaluates edges.

### Inference behavior

ORTHRUS uses a TGN wrapper with `use_memory: False`: projected source/destination
features and a last-neighbor graph feed a TransformerConv-based graph-attention
encoder. An edge MLP predicts event type. The standard path reduces edge losses to
node anomalies; default K-Means further filters/relabels high-scoring nodes.

### Computational cost

More expensive than VELOX because it builds temporal neighbor structures and runs
multi-head graph attention, but lighter than memory-updating KAIROS. The ORTHRUS
paper reports favorable training time and GPU memory against its baselines; actual
cost still scales with graph size, neighbor preprocessing, batch size, and variant.

### Strengths

- Fine-grained node/edge anomaly evidence.
- Models pairwise event semantics plus local temporal structure.
- Explicit non-snooped and fixed variants expose important causal/bug boundaries.
- Original system has a clear route from anomaly seeds to attribution.

### Limitations

- Default config is transductive and uses K-Means after thresholding.
- Different variants change features, granularity, and correctness behavior; the
  system name alone is insufficient provenance.
- Graph-attention decisions are less directly interpretable than VELOX.
- Canonical PIDSMaker output is scored nodes/edges, not a completed investigation.

### Possible Agent tool usage

An Agent could select an approved non-snooped/fixed ORTHRUS variant when
fine-grained anomaly seeds or richer local temporal structure are needed, then use a
separate sanitized tracing tool on visible graph evidence. It must choose a specific
approved variant/checkpoint, never silently use default transductive ORTHRUS in a
causal main run, and never treat K-Means output as independent validation.

## MAGIC

### Original paper

Jia et al., [*MAGIC: Detecting Advanced Persistent Threats via Masked Graph
Representation Learning*](https://www.usenix.org/system/files/usenixsecurity24-jia-zian.pdf),
USENIX Security 2024.

### Purpose

MAGIC learns benign graph representations through masked feature and structure
reconstruction, then performs outlier detection at entity or system-state
granularity. The original work also discusses feedback-driven model adaptation.

### PIDSMaker module location

- configuration: `config/magic.yml`;
- encoder/decoder: `pidsmaker/encoders/magic_encoder.py`;
- objectives: `objectives/reconstruct_masked_feat.py` and
  `objectives/predict_masked_struct.py`;
- specialized inference scoring: `detection/training_methods/inference_loop.py`;
- threshold/evaluation: `evaluation_methods/{evaluation_utils,node_evaluation}.py`;
- a MAGIC graph builder exists at
  `preprocessing/build_graph_methods/build_magic_graphs.py`, but `magic.yml` does
  not select it.

### Input

The pinned config uses default directed 15-minute construction graphs, path/cmd/IP
attributes for node identity, but the model input feature is only node type and
graph adjacency. It selects no explicit graph transformation and no edge features.

### Output

The model produces masked reconstruction losses and node embeddings. During
validation, PIDSMaker samples up to 5,000 embeddings to estimate a mean neighbor
distance. During test, it fits nearest-neighbor search on sampled **test** embeddings
and assigns each node a normalized `magic_score`. Node evaluation thresholds these
scores and writes scored node dictionaries, metrics, and plots.

### Training requirement

Benign graphs train a three-layer, four-head MAGIC GAT with two simultaneous
objectives: 50% masked-feature reconstruction using an SCE loss and masked-structure
prediction using BCE. No text embedding model is trained in the pinned config.

### Inference behavior

Inference embeds nodes, performs CPU/scikit-learn nearest-neighbor calculations,
and treats large relative neighbor distance as anomalous. The pinned threshold path
calculates the MAGIC threshold from the test directory, explicitly noted in source
as data leakage. This behavior is not admissible for causal-main held-out use.

### Computational cost

MAGIC runs attention in both encoder and feature decoder and adds nearest-neighbor
outlier search. The original paper notes KNN dominates inference on large target
sets; the USENIX 2025 comparative implementation reports substantially higher
training/inference cost than ORTHRUS on several datasets. Cost is sensitive to node
count and sampled-neighbor search.

### Strengths

- Learns both attribute and structural consistency.
- Produces node embeddings useful for outlier analysis.
- Does not require a learned text vocabulary in the pinned configuration.
- Can expose anomalies not captured by one event-type objective.

### Limitations

- Pinned scoring/thresholding uses test distribution information.
- Current config does not select the original simplified/no-redundant graph builder.
- KNN search can dominate inference and scale poorly.
- Outlier nodes are not an attack path, validation, or root-cause explanation.
- Sensitive to coverage and quality of benign training behavior.

### Possible Agent tool usage

MAGIC should remain unavailable for causal held-out tool use until its scoring and
threshold path is redesigned and validated without test fitting. In offline
agent-training analysis, an isolated evaluator could compare its structural
outlier scores with other detectors. The Agent must not use it as a “verification”
stage or assume that a distant embedding proves maliciousness.

## FLASH

### Original paper

King et al., [*FLASH: A Comprehensive Approach to Intrusion Detection via
Provenance Graph Representation Learning*](https://dartlab.org/assets/pdf/flash.pdf),
IEEE Symposium on Security and Privacy 2024.

### Purpose

FLASH combines semantic and temporal node representations with GraphSAGE node-type
prediction. The original system stores reusable GNN embeddings and uses a
lightweight XGBoost runtime classifier to improve real-time detection, while also
producing contextual attack-evidence graphs.

### PIDSMaker module location

- configuration: `config/flash.yml`;
- feature fitting/application:
  `featurization/featurization_methods/featurization_flash.py` and
  `feat_inference_methods/feat_inference_flash.py`;
- positional encoding: `PositionalEncoder` in `feat_inference_flash.py`;
- encoder: `encoders/sage.py`;
- objective: `objectives/predict_node_type.py`;
- specialized score/evaluation:
  `detection/training_methods/inference_loop.py` and
  `evaluation_methods/node_evaluation.py`.

### Input

Default directed graphs with process path/cmd, file path, netflow IP/port, and event
types. The feature stage builds chronological per-node documents from incident
`source → event → destination` properties, trains 30-dimensional Word2Vec on train,
adds sinusoidal positional encoding, and averages token embeddings.

### Output

The pinned model predicts one of three node types. PIDSMaker derives a confidence
margin from the two highest model outputs, records `flash_score` and whether the
node-type prediction is correct, takes the maximum score per node, and applies the
fixed threshold `0.53`. It emits suspicious node scores/flags and evaluation
artifacts. It does **not** emit the original embedding-database/XGBoost result or
attack-evidence graph.

### Training requirement

Train-only Word2Vec followed by a two-layer GraphSAGE node-type classifier with
balanced cross-entropy. However, pinned feature inference reconstructs node
documents from `train`, `val`, and `test` before applying embeddings, so temporal
scope must be audited beyond the feature-model fitting flag.

### Inference behavior

GraphSAGE produces node logits; a large normalized top-two confidence margin,
combined with the implementation's prediction condition, becomes anomaly evidence.
The original paper's embedding recycling database and XGBoost runtime path are not
present in the canonical PIDSMaker config.

### Computational cost

The pinned path runs GraphSAGE over graphs and retains potentially large per-node
document lists; the comparative USENIX study observed high memory/training costs for
its FLASH reimplementation. Original-paper runtime savings from embedding reuse do
not apply to the pinned path because that subsystem is absent.

### Strengths

- Combines semantic attributes, event context, temporal token position, and local
  graph structure.
- Native node-type prediction provides node-oriented anomaly signals.
- Fixed threshold makes the decision rule explicit, though not necessarily valid
  across environments.

### Limitations

- PIDSMaker is a partial reimplementation of the original end-to-end system.
- Feature inference scans all splits and aggregates node histories, creating a
  causal-boundary concern.
- Fixed `0.53` threshold is not environment-calibrated by the pinned config.
- GraphSAGE/document construction can be costly; no original embedding reuse.
- No reconstruction/attribution output.

### Possible Agent tool usage

After causal feature construction, threshold calibration, checkpointing, and
profiling are approved, an Agent could use FLASH when semantic node histories and
node-role deviations are relevant. It must not assume original-paper real-time cost
or evidence-graph output from this PIDSMaker implementation.

## KAIROS

### Original paper

Cheng et al., [*Kairos: Practical Intrusion Detection and Investigation using
Whole-system Provenance*](https://arxiv.org/abs/2308.05034), IEEE Symposium on
Security and Privacy 2024.

### Purpose

KAIROS models streaming temporal interactions, identifies anomalous and rare nodes,
links correlated suspicious time windows into queues, detects anomalous queues, and
supports attack investigation. Its original detection unit is a time-window queue,
not merely a suspicious node.

### PIDSMaker module location

- configuration: `config/kairos.yml`;
- hierarchical hashing: `featurization/feat_inference_methods/feat_inference_HFH.py`;
- TGN and graph attention: `encoders/tgn_encoder.py`, `tgn.py`, and
  `encoders/graph_attention.py`;
- edge-type objective: `objectives/predict_edge_type.py`;
- queue implementation: `detection/evaluation_methods/queue_evaluation.py`;
- canonical selected evaluation: `evaluation_methods/node_evaluation.py`.

### Input

Directed 15-minute graphs with process/file paths and netflow IP/port. Hierarchical
feature hashing creates 16-dimensional normalized node vectors. Batching uses
1,024-edge chunks and TGN last-neighbor graphs. Messages and time encodings are
edge features.

### Output

The stateful TGN predicts edge types and emits per-edge cross-entropy losses. Although
`kairos.yml` contains queue parameters, its selected `evaluation.used_method` is
`node_evaluation`, so the pinned canonical run aggregates edge losses to node scores
and thresholds at maximum validation loss. It does not select `queue_evaluation` and
therefore does not deliver the original anomalous queues or investigation graph.

### Training requirement

Self-supervised edge-type prediction over training graphs. The encoder uses TGN
memory (`use_memory: True`), temporal encoding, graph attention, a four-layer edge
MLP, and ordered state updates. Hierarchical hashing is deterministic, although the
config's `training_split: all` remains provenance that must not be ignored.

### Inference behavior

Each batch reads TGN memory/last-neighbor state, applies graph attention, predicts
event type, then updates memory with observed ground-truth graph state. The current
node evaluation reduces losses over a node's incident events. The original
IDF-rareness and queue-correlation behavior is not the selected output path; the
unused queue config even includes an option to include test in IDF.

### Computational cost

KAIROS is one of the heavier configurations because recurrent TGN memory updates are
sequential and graph attention/temporal-neighbor preprocessing are required. The
ORTHRUS paper reports longer training than its memoryless TGN variant. Original
KAIROS reports per-window processing below its window duration, but this does not
establish the pinned config's cost on the project hardware.

### Strengths

- Rich temporal state and local structure.
- Deterministic hierarchical attributes avoid a learned text vocabulary.
- Original design explicitly connects anomaly, rarity, temporal persistence, and
  investigation.

### Limitations

- Canonical PIDSMaker output omits the original queue detector/investigation.
- Stateful inference makes reset, ordering, replay, and checkpoint semantics
  critical.
- Higher runtime/memory and lower parallelism than stateless detectors.
- Current project classifies canonical KAIROS as a compatibility baseline, not an
  approved causal-main config.

### Possible Agent tool usage

An approved KAIROS-derived tool could be useful when persistent temporal behavior is
the deployment-visible concern and sufficient state/resource budget exists. The
Agent must know whether it is invoking current node-score evaluation or a separately
validated queue implementation; it cannot call the current config and claim an
attack queue or reconstructed investigation.

## NODLINK

### Original paper

Liu et al., [*NodLink: An Online System for Fine-Grained APT Attack Detection and
Investigation*](https://arxiv.org/abs/2311.02331), NDSS 2024.

### Purpose

NODLINK's original system combines fine-grained anomalous-node detection with an
online, importance-oriented Steiner Tree approximation, an in-memory evolving
hopset cache, and attack-graph output. PIDSMaker implements the learned anomaly
detector front end, not that complete online investigation system.

### PIDSMaker module location

- configuration: `config/nodlink.yml`;
- undirected transformation: `preprocessing/transformation_methods/transformation_undirected.py`;
- FastText: `featurization/featurization_methods/featurization_fasttext.py` and
  `feat_inference_methods/feat_inference_fasttext.py`;
- encoder: `encoders/sum_aggregation.py`;
- variational decoder: `decoders/nodlink_decoder.py`;
- objective/evaluation: `objectives/reconstruct_node_feat.py` and
  `evaluation_methods/node_evaluation.py`.

### Input

Graphs are made bidirectional by adding reverse edges. Process command lines, file
paths, and netflow IP/port are embedded with 256-dimensional train-only FastText.
The model consumes node embeddings and graph adjacency.

### Output

PIDSMaker produces node-feature reconstruction loss, aggregates per-node scores,
and thresholds at the 90th percentile of validation losses. The output is a ranked/
thresholded set of node anomalies and standard evaluation artifacts. There is no
pinned NODLINK in-memory hopset cache, Steiner Tree solver, or attack graph output.

### Training requirement

Train-only FastText (100 configured epochs), weighted/sum neighborhood aggregation,
and a variational autoencoder-like node decoder trained with MSE reconstruction.
The shared training loop still lacks an accepted checkpoint lifecycle.

### Inference behavior

The undirected neighborhood is aggregated through two linear layers; the
variational decoder reconstructs the original node feature. High reconstruction
loss indicates behavior unlike benign training. Validation determines a fixed
90th-percentile threshold.

### Computational cost

More costly than a linear detector because it constructs reverse edges, uses
256-dimensional embeddings, graph message passing, and variational decoding.
However, it avoids TGN recurrent state and multi-head attention. Original NODLINK's
high-throughput cache/STP optimizations cannot be credited to the pinned detector
because those modules are absent.

### Strengths

- Fine-grained node anomaly output.
- Train-only FastText and validation-derived threshold in the canonical config.
- Structural and semantic reconstruction can complement edge-type prediction.
- No recurrent temporal memory, simplifying reset semantics.

### Limitations

- Making graphs undirected discards causal direction for message passing and doubles
  some connectivity.
- 90th-percentile threshold can yield large alert volumes across environments.
- Stochastic variational decoding can add instability.
- Original attack correlation/investigation is not implemented.

### Possible Agent tool usage

An Agent could consider an approved NODLINK detector when it needs fine-grained
semantic/structural node anomalies without TGN state, especially as a complementary
comparison to edge-type predictors. It must not describe the returned nodes as a
Steiner attack graph or claim NODLINK's original online investigation throughput.

## ThreatRace

### Original paper

Wang et al., [*threaTrace: Detecting and Tracing Host-based Threats in Node Level
Through Provenance Graph Learning*](https://arxiv.org/abs/2111.04333), IEEE
Transactions on Information Forensics and Security, 2022.

### Purpose

The original threaTrace learns benign node roles with multiple GraphSAGE submodels,
flags nodes whose observed role is misclassified, and supports alert tracing and
feedback/retraining. PIDSMaker preserves the node-role prediction idea but not the
complete multi-model lifecycle.

### PIDSMaker module location

- configuration: `config/threatrace.yml`;
- features/batching: node-type and edge-distribution construction in shared data
  utilities;
- encoder: `encoders/sage.py`;
- objective: `objectives/predict_node_type.py`;
- specialized score/evaluation:
  `detection/training_methods/inference_loop.py` and
  `evaluation_methods/{evaluation_utils,node_evaluation}.py`.

### Input

Directed graphs. Model features are the node's one-hot type plus its edge-type
distribution; textual path/cmd/IP fields are retained in construction metadata but
are not the learned node input. The encoder is a two-layer 32-dimensional GraphSAGE.

### Output

The model outputs node-type logits and cross-entropy losses. PIDSMaker calculates a
log ratio between the highest and second-highest class probabilities, records
whether the predicted node type matches, and uses fixed threshold `1.5` to produce
node flags. Standard evaluation returns node scores, predictions, and hidden-label
metrics. It does not output the original tracing result.

### Training requirement

Self-supervised/benign node-type prediction in the shared PIDSMaker loop. The
original paper describes role labels, multiple submodels, special stopping and
feedback/retraining behavior; these are not represented by the single canonical
PIDSMaker configuration.

### Inference behavior

GraphSAGE aggregates local ancestors/neighbors and predicts expected node role.
Unexpected role evidence produces a high ratio/loss and can be flagged. The fixed
threshold is global rather than validation-calibrated in the pinned implementation.

### Computational cost

Moderate GNN cost: two GraphSAGE layers with small hidden size and no text model,
TGN, or attention. The original multi-model/retraining cost is absent. The USENIX
comparative study observed fast testing but potentially long training/stopping and
large false-positive output for its reimplementation.

### Strengths

- Simple node-role anomaly concept and compact input features.
- Avoids learned textual embeddings and recurrent temporal state.
- Node-level localization is easier to consume than whole-graph alarms.

### Limitations

- Single PIDSMaker model does not reproduce original multi-model feedback design.
- Fixed threshold may transfer poorly.
- Edge-distribution/node-type features can miss semantic masquerading.
- Original and comparative studies report false-positive fatigue risks.
- No actual trace graph in canonical output.

### Possible Agent tool usage

An approved ThreatRace config could provide a low-to-moderate-cost node-role anomaly
view when topology/type distributions are informative. An Agent should compare
alert volume and environment compatibility and should not use the name “ThreatRace”
as evidence that tracing or online feedback occurred.

## R-CAID

### Original paper

Goyal et al., [*R-CAID: Embedding Root Cause Analysis within Provenance-based
Intrusion Detection*](https://gangw.web.illinois.edu/rcaid-sp24.pdf), IEEE
Symposium on Security and Privacy 2024.

### Purpose

R-CAID embeds root-cause relationships into node representations so process
behavior is evaluated in the context of its causal roots. The original detector
performs process-level anomaly scoring/clustering and aims for resilience to mimicry.

### PIDSMaker module location

- configuration: `config/rcaid.yml`;
- pseudo-graph: `preprocessing/transformation_methods/transformation_rcaid_pseudo_graph.py`;
- Doc2Vec: `featurization/featurization_methods/featurization_doc2vec.py` and
  `feat_inference_methods/feat_inference_doc2vec.py`;
- encoder: `encoders/rcaid_encoder.py`;
- objective: `objectives/predict_node_type.py`;
- output/evaluation: `evaluation_methods/node_evaluation.py`.

### Input

Default graphs with process path/cmd, file path, and netflow IP. The transformation
identifies nodes whose earliest activity is outbound, creates pseudo roots connected
to every descendant, prunes roots connected to more than half the graph, then
relabels pseudo roots and assigns arbitrary timestamps to new edges. Doc2Vec includes
neighbor context.

### Output

The pinned R-CAID GAT predicts node types and produces per-node cross-entropy loss.
Node evaluation applies maximum validation loss and emits scored/thresholded nodes.
It does not return explicit root-cause IDs, causal paths, clusters, or the original
paper's process-level RCA report.

### Training requirement

The canonical config fits 128-dimensional Doc2Vec on `all` splits, builds the
pseudo-root overlay, and trains a three-layer multi-head GAT plus residual MLP for
node-type prediction. The all-split feature fit makes the config a transductive
compatibility baseline.

### Inference behavior

Pseudo-root edges allow root information to reach descendant embeddings in one
message-passing step. The GAT produces node representations; deviation in node-type
prediction becomes the anomaly score. PIDSMaker's pruning threshold is hard-coded
inside the transformation call at 0.5 when pruning is enabled.

### Computational cost

Potentially high memory and graph-processing cost: pseudo roots can connect to many
descendants, increasing edges before a three-layer attention network. The original
paper identifies pseudo-node/edge memory overhead as its main cost and introduces
pruning, which itself creates a security/accuracy trade-off.

### Strengths

- Injects long-range causal-root context directly into node embeddings.
- Process/node-level anomaly output can be more focused than window alarms.
- Designed to make local mimicry less effective when the immutable entry/root
  context remains abnormal.

### Limitations

- Current Doc2Vec fit is transductive.
- Pseudo-graph expansion can be large; pruning can remove useful or adversarially
  influenced roots.
- Added arbitrary timestamps require careful causal interpretation.
- The original clustering/RCA output is not implemented by the canonical pipeline.
- R-CAID lacked public source in the comparative study and was reimplemented from
  the paper, increasing fidelity uncertainty.

### Possible Agent tool usage

R-CAID should not be offered in causal held-out operation until a train-only feature
fit, causal pseudo-graph construction, checkpoint, parser, and resource profile are
approved. In offline comparisons, its root-context anomaly scores may test whether
local detectors miss long-range causal context. The Agent must not report a root
cause unless a separate, validated result actually identifies one.

## Cross-system conclusions for Agent use

The eight PIDSs are alternative capability bundles, not a fixed pipeline. No source
supports rules such as “ORTHRUS discovers, then MAGIC verifies” or “KAIROS always
reconstructs.” In the pinned implementation:

- VELOX and ORTHRUS primarily score event-type surprise;
- FLASH and ThreatRace score node-role surprise;
- NODLINK reconstructs semantic node features;
- MAGIC scores embedding outliers after masked graph learning;
- KAIROS provides stateful temporal event modeling but currently exports node
  scores rather than its original queue investigation;
- R-CAID injects causal-root context but currently exports node loss rather than a
  root-cause report.

Any future Agent-facing tool must expose the *actual approved config's* input,
granularity, score semantics, output artifacts, causality class, checkpoint status,
and cost profile. The Agent should select among available capabilities using
deployment-visible evidence and executor-owned resource constraints. It must not
select unavailable systems, infer original-paper outputs from a system name, query
hidden metrics, or combine transductive baselines with causal-main results.

## Primary source links

- PIDSMaker official repository and system list:
  <https://github.com/ubc-provenance/PIDSMaker>
- PIDSMaker framework paper: <https://arxiv.org/pdf/2601.22983>
- USENIX 2025 comparative study/VELOX:
  <https://www.usenix.org/system/files/usenixsecurity25-bilot.pdf>
- ORTHRUS:
  <https://www.usenix.org/system/files/conference/usenixsecurity25/sec25cycle1-prepub-103-jiang-baoxiang.pdf>
- MAGIC: <https://www.usenix.org/system/files/usenixsecurity24-jia-zian.pdf>
- FLASH: <https://dartlab.org/assets/pdf/flash.pdf>
- KAIROS: <https://arxiv.org/abs/2308.05034>
- NODLINK: <https://arxiv.org/abs/2311.02331>
- ThreatRace: <https://arxiv.org/abs/2111.04333>
- R-CAID: <https://gangw.web.illinois.edu/rcaid-sp24.pdf>
