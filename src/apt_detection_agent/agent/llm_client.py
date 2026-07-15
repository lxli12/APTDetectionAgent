"""Small OpenAI-compatible HTTP client with no provider SDK dependency."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    model: str
    temperature: float = 0.0
    max_tokens: int = 1024


class LLMClient:
    def __init__(self, base_url: str, config: GenerationConfig, api_key: str = "") -> None:
        self.endpoint = base_url.rstrip("/") + "/chat/completions"
        self.config = config
        self.api_key = api_key

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        payload = json.dumps({
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }).encode()
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(self.endpoint, data=payload, headers=headers, method="POST")
        with urlopen(request, timeout=60) as response:
            body = json.loads(response.read())
        return str(body["choices"][0]["message"]["content"])
