# vLLM process and client protocol

Requirements: REQ-ENV-001..004, REQ-RESOURCE-001..003, REQ-TOOL-001.

The vLLM server runs only in the existing `vllm` Conda environment. The controller
uses `src/apt_detection_agent/llm/vllm_client.py`, which depends on Python HTTP
stdlib and Pydantic and never imports vLLM, PyTorch, or CUDA libraries.

Runtime configuration is injected with `VLLM_HOST`, `VLLM_PORT`,
`VLLM_BASE_URL`, and `VLLM_MODEL_PATH`. Host and base URL must resolve to a
localhost HTTP `/v1` endpoint, must agree on the port, and cannot contain URL
credentials. Port 8000 is retained only as the historical default candidate and can
be replaced without code changes.

The client supports the OpenAI-compatible model-list and chat-completions endpoints,
bounds generation parameters, validates response shape, and sanitizes transport
errors. It sends no API key because the approved interface is localhost-only.

AutoDL read-only pre-smoke evidence on 2026-07-14 found the candidate model directory
`/root/autodl-tmp/llm-models/Llama-3.1-8B` (30 GiB on disk), four safetensor shards,
idle GPUs, no existing vLLM server, and the pinned `vllm` environment at Python
3.10.20, vLLM 0.5.3.post1, and PyTorch 2.3.1+cu121. These observations do not alter
the 32-vCPU/240-GiB/2×24-GiB resource quota.
