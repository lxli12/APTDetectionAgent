# ADR 0005: Controller dependency boundary

Status: accepted
Requirements: REQ-ENV-002, REQ-ENV-004, REQ-GOV-001.

Read-only dependency audit on 2026-07-14 found that AutoDL system Python 3.10.12
does not provide Pydantic, PyYAML, or httpx. The `pids` environment contains
Pydantic 2.12.5, PyYAML 6.0.3, and httpx 0.28.1; `vllm` contains Pydantic 2.13.3,
PyYAML 6.0.3, and httpx 0.28.1. Those packages belong to their respective runtime
environments and do not authorize cross-environment controller imports.

Phase 1 uses only Pydantic 2.13.4 for strict, versioned data contracts. PyYAML and
an HTTP client are deferred until their owning phases. A third lightweight
controller environment is recommended for remote runtime, but creating or installing
it requires explicit approval. It must exclude PyTorch, PyG, PIDSMaker, vLLM, W&B,
and database administration tooling.
