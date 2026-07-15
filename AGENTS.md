# APTDetectionAgent development rules

These rules apply to the entire repository and must be followed throughout
development.

## 1. Sources of truth
- `docs/design/APT_Detection_Agent_Design.md` is the current source of truth
  for research behavior, deployment protocol, memory policy, tool actions,
  training, and evaluation.

## 2. Local development boundary

- The local machine is an Apple Silicon Mac (M1). It is for source code,
  documentation, lightweight unit tests, lint/static checks, and Git operations.
- Do not run datasets, model training, inference experiments, benchmarks, GPU
  workloads, or environment-reproduction experiments locally.
- No experiment data is available locally. Do not fabricate local data or use a
  local result as evidence for an experimental claim.
- Delete ad hoc Python or shell scripts (including temporary `.py` and `.sh`
  probes) as soon as the check is complete. Do not keep one-off test, inspection,
  migration, or debugging scripts after their result has been incorporated into
  project code or documentation. Keep only files required to build, test,
  operate, document, or reproduce the completed project.
- Keep generated data, checkpoints, caches, logs, and run outputs out of Git.

## 3. Authoritative remote environment

- All data processing and experiments run on the AutoDL server through the SSH
  alias `apt_agent` (host `connect.bjb1.seetacloud.com`, port `23341`, user
  `root`, identity file `~/.ssh/id_ed25519_autodl`). Credentials and passwords
  must never be committed, printed into logs, or copied into documentation.
- The environment was last inspected on 2026-07-15: Ubuntu 22.04.3, 2 x RTX
  4090 (24 GB each), NVIDIA driver 580.105.08, an effective cgroup limit of 32
  vCPU, and 240 GiB memory. The host-level `lscpu` and `free` output exposes
  larger host resources, so always use cgroup limits and GPU visibility when
  recording effective experiment resources.
- The `pids` Conda environment currently uses Python 3.10.20, PyTorch
  2.3.0+cu121, and sees both GPUs. The isolated `vllm` environment uses Python
  3.10.20, PyTorch 2.3.1+cu121, and vLLM 0.5.3.post1. Re-inspect before relying
  on these versions because the live machine remains authoritative.
- The actual AutoDL machine is authoritative for the OS, CUDA/driver, Python,
  Conda environments, packages, storage paths, databases, and hardware. The
  PIDSMaker package metadata and any local environment are not authoritative for
  this project environment.
- The supplied `setup_server.sh` is historical setup reference only. Before an
  experiment, inspect the live server and record the effective environment. Do
  not claim that the script describes the server unless the live state confirms
  it.
- The server may be powered off. A failed connection while it is off is not an
  environment result. Resume inspection and experiments after it becomes
  available.
- Remote experiments may be started and monitored autonomously when they are in
  the current task scope. Use reproducible commands/configs, preserve logs and
  resolved configuration, and report failures as well as successful results.

### 3.1 Server storage ownership

- `/root/APTDetectionAgent` is the canonical remote repository path. Keep source
  code, versioned configuration, prompts, scripts, tests, and documentation
  there. Do not place datasets, model weights, checkpoints, caches, databases,
  or experiment outputs in the repository or elsewhere on the system disk.
- `/root/autodl-tmp` is the canonical large-file data disk. The inspected
  instance has a 30 GB system disk and a 350 GB data disk, so large-file routing
  is mandatory, not an optional optimization.
- Use this data-disk layout unless a verified backend requirement needs a more
  specific compatible path:

  ```text
  /root/autodl-tmp/
  ├── data/
  │   ├── raw-datasets/          raw dataset dumps and extracted datasets
  │       ├── training-environments/
          └── evaluation-environments/ 
  │   └── sft-data/              generated SFT manifests/examples/exports
  ├── llm-models/                 explicitly managed model weights and Hugging Face home and download cache
      └──vllm/
  ├── postgresql/                 PostgreSQL data directory
  └── apt-detection-agent/
      ├── pidsmaker-output/
      ├── experiments-result/            Agent run outputs, traces, metrics, reports
      ├── sft-checkpoints/            Agent/SFT checkpoints
  ```

- Route native pipeline preprocessing, construction, transformation,
  featurization, batching, checkpoints, cache, and other large artifacts to
  `/root/autodl-tmp/apt-detection-agent/pidsmaker-output`. Reference-only PIDSMaker
  equivalence outputs may use `/root/autodl-tmp/pidsmaker` but must never be
  mixed with production Agent artifacts.
- PostgreSQL 17 is configured to use
  `/root/autodl-tmp/postgresql/17/main`. Its service was not running during the
  2026-07-15 inspection; check readiness before work that depends on it.
- Dataset dumps currently live under `/root/autodl-tmp/data/raw-datasets`, SFT
  datasets belong under `/root/autodl-tmp/data/sft-data`, and the default Llama
  model lives under `/root/autodl-tmp/llm-models/Llama-3.1-8B`.
- Set package/model caches such as `HF_HOME`, model downloads, temporary
  training data, and large build caches to data-disk paths. Inspect free space
  before every large download or experiment and fail early if the reserved
  margin would be exhausted.
- AutoDL states that local system/data disks have no redundant copy and that
  released instances lose their data. Back up important results, manifests,
  final checkpoints, and reports to durable storage. See the official
  [instance data](https://www.autodl.com/docs/instance_data/) and
  [local data disk](https://www.autodl.com/docs/local_disk/) documentation.

### 3.2 Remote setup and academic acceleration

- At the 2026-07-15 inspection, no repository existed under `/root`. Clone it to
  `/root/APTDetectionAgent` before remote development or experiments.
- Production Agent code must not import the `pidsmaker` package. A reference
  equivalence run may install the unchanged submodule in an isolated environment
  and must record the pinned revision.
- AutoDL's built-in academic proxy may be enabled for a download session with
  `source /etc/network_turbo`. It is intended for academic GitHub and Hugging
  Face access, is not guaranteed to be stable, and should be disabled afterward
  with `unset http_proxy && unset https_proxy` because it can affect normal
  networking. Do not persist proxy values or mirror endpoints in committed
  files. Follow the current official
  [academic acceleration documentation](https://www.autodl.com/docs/network_turbo/)
  whenever the service behavior changes.
- Prefer resumable, checksum-verifiable downloads. Record the upstream model or
  dataset identifier, revision, license, destination, and checksum/manifest;
  never treat a partially downloaded directory as a valid artifact.

## 4. LLM provider and model policy

- Llama-3.1-8B at `/root/autodl-tmp/llm-models/Llama-3.1-8B` is the default LLM
  for development and smoke tests. Serve it from the isolated `vllm`
  environment through an OpenAI-compatible local endpoint; do not load the LLM
  into the PIDSMaker `pids` environment.
- Keep the Agent policy dependent on a small provider-neutral completion/chat
  interface. Provider clients own transport, authentication, retries, timeout,
  token accounting, and response normalization; domain code must not depend on
  a vendor SDK.
- Preserve configurable local/open-model backends for vLLM/OpenAI-compatible
  serving and Hugging Face Transformers. The model path or Hugging Face model ID
  must come from configuration, so common research families such as Llama,
  Qwen, Mistral, and DeepSeek-compatible checkpoints can be compared without
  changing controller code. Supporting an interface does not authorize an
  unplanned model download.
- Preserve optional closed-model adapters for OpenAI, Anthropic, DeepSeek API,
  and Qwen/DashScope-compatible services. Enable them only through experiment
  configuration and environment-provided credentials. Never hardcode API keys,
  base URLs containing secrets, or vendor-specific model assumptions.
- Record provider, exact model/revision, tokenizer, generation parameters,
  context limit, input/output tokens, latency, and serving mode in every run.
  Never silently fall back from one provider/model to another.

## 5. PIDSMaker boundary

- `PIDSMaker/` is an unchanged, pinned upstream reference submodule. Do not modify its
  source, configuration logic, package metadata, tests, or internal behavior.
- Migrate the required node-level PIDSMaker subset into the repository-level
  runnable `pidsmaker_adapter/` directory while retaining recognizable
  upstream module boundaries (`config`, preprocessing, featurization, tasks,
  models, and node evaluation). Record the upstream commit/path and material
  changes. Exclude triage, edge/queue evaluation, synthetic attacks, and the
  `ATLASV2_EDR` and `CARBANAKV2_EDR` datasets.
- Agent-owned paths, schemas, finite configuration options, hashes, checkpoints, and typed tool
  interfaces are authoritative. Production code must not invoke PIDSMaker CLI,
  import `pidsmaker`, or expose arbitrary internal functions to the LLM.
- The Agent owns incorporated preprocessing, features, intermediate artifacts,
  detector checkpoints, training, inference, orchestration, memory, traces,
  evaluation, and SFT artifacts. PIDSMaker remains a reference oracle only.
- Preserve PIDSMaker's native train/validation/test boundaries and never expose
  test labels, attack identity, malicious nodes, attack times, or label-derived
  metrics to held-out online observations or deployable memory.

## 6. Implementation conventions

- Keep modules cohesive and reusable so components can be replaced or disabled
  in ablations. Prefer explicit typed schemas at module boundaries.
- Names should state purpose directly without becoming verbose. Reuse a shared
  abstraction only when ownership and semantics are genuinely shared.
- Keep the dependency direction defined by the current design. In
  particular, controller and policy code must not import PIDSMaker internals or
  construct arbitrary backend shell commands.
- Expose only validated discrete actions and finite configuration options. Preserve stage
  invalidation, cache reuse, fallback, and cost information in tool contracts.
- Keep prompt text in runtime-loaded `.txt` files and stable settings in YAML.
- Keep experiments reproducible: version configs and thin entry points; snapshot
  resolved config, commands, logs, traces, metrics, and reports in the run.
- For uncertain style or organization choices, consult
  [LHY-24/TuneAgent](https://github.com/LHY-24/TuneAgent) and
  [AI45Lab/AgentDoG](https://github.com/AI45Lab/AgentDoG), while preserving this
  repository's current design and ownership rules.

## 7. Verification and Git discipline

- Verify changes in proportion to their risk. Local checks may validate Agent
  code and architecture; experimental conclusions require AutoDL runs.
- Add or update tests for public contracts, dependency boundaries, sanitization,
  invalid actions, fallbacks, and failure handling.
