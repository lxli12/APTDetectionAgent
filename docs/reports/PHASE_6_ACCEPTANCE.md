# Phase 6 acceptance report

Requirements: REQ-ENV-001..004, REQ-RESOURCE-001..003, REQ-TOOL-001.

## Scope

Phase 6 implements an environment-driven, localhost-only OpenAI-compatible vLLM
client with no cross-environment imports. It validates request bounds, response
shape, endpoint consistency, and sanitized failures.

## Local evidence

Evidence on 2026-07-14:

- Phase 6 focused suite: 10/10 passed;
- full suite: 129/129 passed;
- governance and `git diff --check`: passed;
- PIDSMaker remains pinned and clean.

## AutoDL pre-smoke gate

Read-only checks found both GPUs idle, no existing vLLM process, the 30-GiB
Llama-3.1-8B candidate directory with tokenizer/config and four model shards, and
the expected Python/vLLM/PyTorch versions. A short conservative smoke may therefore
use GPU 0 only, a unique run directory, localhost, a non-conflicting environment
port, and a reduced initial context/memory profile. It must verify startup, model
listing, one bounded completion, logs, GPU use, and clean owned-process shutdown.

## Remote evidence

At commit `8cfbc0d6e290acd820cb491c6ca621b1a8a79b53`, the existing `pids`
environment passed governance, compile, and 129/129 tests in 1.617 seconds.

Run `phase6_vllm_smoke_20260714_002` then validated the separate `vllm`
environment with a bounded foreground session because tmux is not installed:

- vLLM 0.5.3.post1 loaded the four-shard Llama-3.1-8B model on GPU 0;
- conservative profile: TP=1, memory utilization 0.75, max model length 2048;
- model weights reported 14.9888 GiB and observed GPU allocation peaked at
  approximately 17,665 MiB; GPU 1 remained unused;
- `/v1/models` succeeded and the Phase 6 client received `OK.` from one request
  bounded to 16 completion tokens (39 prompt, 3 completion tokens);
- the owned process shut down cleanly; localhost port 18000 refused connections
  afterward and both GPUs returned to 0 MiB.

Attempt `phase6_vllm_smoke_20260714_001` is retained as
`FAILED_PRECONDITION_MISSING_TMUX`; no process started in that attempt. No directory
was overwritten or deleted. The bounded smoke is not approval to use foreground
sessions for training or formal evaluation.

The smoke also proved vLLM 0.5.3 logs prompt bodies by default. Future formal launch
commands must use `--disable-log-requests`; this harmless smoke prompt remains only
in its protected local run log.
