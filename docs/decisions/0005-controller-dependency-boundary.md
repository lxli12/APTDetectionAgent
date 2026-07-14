# ADR 0005: Controller dependency boundary

Status: accepted
Requirements: REQ-ENV-002, REQ-ENV-004, REQ-GOV-001.

Read-only dependency audit on 2026-07-14 found that AutoDL system Python 3.10.12
does not provide Pydantic, PyYAML, or httpx. The `pids` environment contains
Pydantic 2.12.5, PyYAML 6.0.3, and httpx 0.28.1; `vllm` contains Pydantic 2.13.3,
PyYAML 6.0.3, and httpx 0.28.1. Those packages belong to their respective runtime
environments and do not authorize cross-environment controller imports.

The user has prohibited creation of another Conda environment and authorized use
and modification of the existing `pids` environment. The initial controller process
therefore runs with the `pids` Python and pins the already installed Pydantic 2.12.5.
This is an interpreter/runtime decision, not permission for the controller to import
PIDSMaker, PyTorch, or PyG: PIDSMaker remains a separately launched subprocess and
the controller import allowlist is tested. PyYAML and an HTTP client are deferred
until their owning phases. The controller must not import vLLM or W&B.
