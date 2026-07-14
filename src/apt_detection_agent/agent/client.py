"""OpenAI-compatible localhost client with no vLLM import.

Requirements: REQ-ENV-001..004, REQ-TOOL-001, REQ-RESOURCE-002.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator

from apt_detection_agent.schemas.common import StrictModel


class VLLMConfig(StrictModel):
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    base_url: str
    model_path: str
    timeout_seconds: int = Field(default=30, ge=1, le=300)

    @field_validator("host")
    @classmethod
    def localhost_only(cls, value: str) -> str:
        if value not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("vLLM must be reached through a localhost interface")
        return value

    @model_validator(mode="after")
    def base_url_matches_localhost(self) -> "VLLMConfig":
        parsed = urlparse(self.base_url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("VLLM_BASE_URL must be localhost HTTP")
        if parsed.port != self.port:
            raise ValueError("VLLM_BASE_URL port must match VLLM_PORT")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("VLLM_BASE_URL cannot contain credentials, query, or fragment")
        if parsed.path.rstrip("/") != "/v1":
            raise ValueError("VLLM_BASE_URL must end at the OpenAI-compatible /v1 root")
        if not self.model_path:
            raise ValueError("VLLM_MODEL_PATH is required")
        return self

    @classmethod
    def from_environment(cls, environ: dict[str, str] | None = None) -> "VLLMConfig":
        values = environ if environ is not None else os.environ
        host = values.get("VLLM_HOST", "127.0.0.1")
        port = int(values.get("VLLM_PORT", "8000"))
        url_host = f"[{host}]" if host == "::1" else host
        return cls(
            host=host,
            port=port,
            base_url=values.get("VLLM_BASE_URL", f"http://{url_host}:{port}/v1"),
            model_path=values.get("VLLM_MODEL_PATH", ""),
            timeout_seconds=int(values.get("VLLM_TIMEOUT_SECONDS", "30")),
        )


class ChatMessage(StrictModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1)


class ChatResponse(StrictModel):
    request_id: str
    model: str
    content: str = Field(min_length=1)
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)


Transport = Callable[[urllib.request.Request, int], bytes]


def _default_transport(request: urllib.request.Request, timeout: int) -> bytes:
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


@dataclass(frozen=True)
class VLLMClient:
    config: VLLMConfig
    transport: Transport = _default_transport

    def list_models(self) -> tuple[str, ...]:
        payload = self._request("GET", "/models", None)
        try:
            data = payload["data"]
            if not isinstance(data, list):
                raise TypeError
            return tuple(str(item["id"]) for item in data)
        except (KeyError, TypeError) as exc:
            raise RuntimeError("vLLM returned a malformed model list") from exc

    def chat(
        self,
        messages: tuple[ChatMessage, ...],
        *,
        max_tokens: int,
        temperature: float = 0.0,
    ) -> ChatResponse:
        if not messages:
            raise ValueError("chat requires at least one message")
        if not 1 <= max_tokens <= 4096:
            raise ValueError("max_tokens exceeds the approved controller bound")
        if not 0.0 <= temperature <= 1.0:
            raise ValueError("temperature must be between zero and one")
        payload = self._request(
            "POST",
            "/chat/completions",
            {
                "model": self.config.model_path,
                "messages": [item.model_dump() for item in messages],
                "max_tokens": max_tokens,
                "temperature": temperature,
            },
        )
        try:
            choice = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage", {})
            return ChatResponse(
                request_id=str(payload["id"]),
                model=str(payload["model"]),
                content=str(choice),
                prompt_tokens=int(usage.get("prompt_tokens", 0)),
                completion_tokens=int(usage.get("completion_tokens", 0)),
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError("vLLM returned a malformed response") from exc

    def _request(self, method: str, suffix: str, body: dict[str, object] | None) -> dict:
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            self.config.base_url.rstrip("/") + suffix,
            data=data,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            raw = self.transport(request, self.config.timeout_seconds)
            payload = json.loads(raw)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"vLLM request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("vLLM response must be a JSON object")
        return payload
