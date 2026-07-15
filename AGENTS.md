# APTDetectionAgent development rules

These rules apply to the entire repository and must be followed throughout
development.

## 1. Sources of truth

- `docs/architecture/PROJECT_ARCHITECTURE_DESIGN_v1.1.md` is the frozen source
  of truth for repository structure, module ownership, dependency direction,
  and the PIDSMaker boundary.
- `docs/design/APT_Detection_Agent_Design_v0.4.md` is the current source of truth
  for research behavior, deployment protocol, memory policy, tool actions,
  training, and evaluation.
- If the two documents appear to conflict, preserve the frozen repository and
  ownership boundary first, then implement the research behavior through the
  Agent-owned schemas, adapter, tools, controller, memory, evaluation, and
  experiment modules. Record any unresolved conflict before implementation.

## 2. Local development boundary

- The local machine is an Apple Silicon Mac (M1). It is for source code,
  documentation, lightweight unit tests, lint/static checks, and Git operations.
- Do not run datasets, model training, inference experiments, benchmarks, GPU
  workloads, or environment-reproduction experiments locally.
- No experiment data is available locally. Do not fabricate local data or use a
  local result as evidence for an experimental claim.
- Keep generated data, checkpoints, caches, logs, and run outputs out of Git.

## 3. Authoritative remote environment

- All data processing and experiments run on the AutoDL server through the SSH
  alias `apt_agent` (host `connect.bjb1.seetacloud.com`, port `23341`, user
  `root`, identity file `~/.ssh/id_ed25519_autodl`). Credentials and passwords
  must never be committed, printed into logs, or copied into documentation.
- The expected server capacity is 2 x RTX 4090 (24 GB each), 32 vCPU Intel Xeon
  Gold 6430, and 240 GB RAM. Treat this only as an expectation until verified on
  the running server.
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

## 4. PIDSMaker boundary

- `PIDSMaker/` is an unchanged, pinned upstream git submodule. Do not modify its
  source, configuration logic, package metadata, tests, or internal behavior.
- Do not copy PIDSMaker implementation or artifacts into Agent-owned modules.
- Integrate only through `src/apt_detection_agent/pidsmaker_adapter/` and typed,
  validated tools. Adapt request construction and result normalization on the
  Agent side when the live environment requires compatibility work.
- PIDSMaker owns preprocessing, features, intermediate artifacts, PIDS models,
  PIDS checkpoints, training, inference, and backend evaluation. The Agent owns
  orchestration, memory, decisions, execution traces, Agent evaluation, and
  Agent/SFT artifacts.
- Preserve PIDSMaker's native train/validation/test boundaries and never expose
  test labels, attack identity, malicious nodes, attack times, or label-derived
  metrics to held-out online observations or deployable memory.

## 5. Implementation conventions

- Keep modules cohesive and reusable so components can be replaced or disabled
  in ablations. Prefer explicit typed schemas at module boundaries.
- Names should state purpose directly without becoming verbose. Reuse a shared
  abstraction only when ownership and semantics are genuinely shared.
- Keep the dependency direction defined by the frozen architecture. In
  particular, controller and policy code must not import PIDSMaker internals or
  construct arbitrary backend shell commands.
- Expose only validated discrete actions and candidates. Preserve stage
  invalidation, cache reuse, fallback, and cost information in tool contracts.
- Keep prompt text in runtime-loaded `.txt` files and stable settings in YAML.
- Keep experiments reproducible: version configs and thin entry points; snapshot
  resolved config, commands, logs, traces, metrics, and reports in the run.
- For uncertain style or organization choices, consult
  [LHY-24/TuneAgent](https://github.com/LHY-24/TuneAgent) and
  [AI45Lab/AgentDoG](https://github.com/AI45Lab/AgentDoG), while preserving this
  repository's frozen architecture and ownership rules.

## 6. Verification and Git discipline

- Verify changes in proportion to their risk. Local checks may validate Agent
  code and architecture; experimental conclusions require AutoDL runs.
- Add or update tests for public contracts, dependency boundaries, sanitization,
  invalid actions, fallbacks, and failure handling.
- Review `git status` before staging. Never commit secrets, `.env` files, data,
  checkpoints, caches, logs, or generated experiment outputs.
- Make timely, focused commits after a coherent change is verified. Use messages
  that describe the implemented behavior. Push maintained work to GitHub rather
  than accumulating unrelated local changes.
- Do not hide an unverified assumption in code or documentation. Mark pending
  server validation, experimental evidence, and design decisions explicitly.
