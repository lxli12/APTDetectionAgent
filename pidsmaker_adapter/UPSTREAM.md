# PIDSMaker migration provenance

- Upstream submodule revision: `32602734bc9f896be5fc0f03f0a185c967cd6624`
- Upstream source root: `PIDSMaker/pidsmaker/`
- Migrated source root: `pidsmaker_adapter/upstream/`

The migrated subset retains the upstream boundaries for configuration, construction,
transformation, featurization, batching, encoders, decoders, objectives, models, and
data utilities. Imports were moved into the project-owned namespace.

Material changes:

- removed triage, edge/queue/time-window evaluators, experiment sweeps, MC dropout,
  few-shot/synthetic-attack execution, mimicry, and debug probes;
- excluded the upstream CLI and its unconstrained dotted overrides;
- replaced opaque public hash directories with readable checkpoint paths and
  content-addressed internal stage caches carrying canonical manifests;
- fixed detector seed at 42 and construction windows at 15 minutes;
- forced train-only text featurization and disabled test-dependent clustering;
- replaced test-label epoch selection with train-only updates and validation-loss
  selection;
- added graph-local node scoring, validation-only quantile calibration, uniform
  split-result schemas, and explicit visibility controls.
- changed FLASH feature inference from an all-splits node-context merge to a frozen
  train-only Word2Vec model with current-graph-only node documents.
- reset TGN neighbor and node-feature state at every native split boundary while
  retaining only the global storage offset needed to address immutable edge data.
- versioned cache compatibility independently per pipeline stage; manifests still
  record the exact adapter Git revision without invalidating unrelated upstream
  stages for a training-only fix.
- removed stale TGN neighbor-loader/runtime-memory pickle handling; checkpoints
  contain reset state dictionaries while temporal neighbor graphs remain immutable
  batching artifacts.

Production adapter code does not import the installed `pidsmaker` package or invoke
its CLI. The submodule remains an unchanged reference oracle.
