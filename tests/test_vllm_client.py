"""Phase 6 environment-driven vLLM HTTP boundary tests.

Requirements: REQ-ENV-001..004, REQ-TOOL-001, REQ-RESOURCE-002.
"""

from __future__ import annotations

import json
import unittest
import urllib.error

from pydantic import ValidationError

from apt_detection_agent.llm import ChatMessage, VLLMClient, VLLMConfig


ENV = {
    "VLLM_HOST": "127.0.0.1",
    "VLLM_PORT": "8123",
    "VLLM_BASE_URL": "http://127.0.0.1:8123/v1",
    "VLLM_MODEL_PATH": "/models/approved-llama",
    "VLLM_TIMEOUT_SECONDS": "9",
}


class RecordingTransport:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[object, int]] = []

    def __call__(self, request: object, timeout: int) -> bytes:
        self.calls.append((request, timeout))
        return json.dumps(self.response).encode()


class VLLMConfigTests(unittest.TestCase):
    def test_all_runtime_values_are_environment_driven(self) -> None:
        config = VLLMConfig.from_environment(ENV)
        self.assertEqual(config.port, 8123)
        self.assertEqual(config.base_url, ENV["VLLM_BASE_URL"])
        self.assertEqual(config.model_path, ENV["VLLM_MODEL_PATH"])
        self.assertEqual(config.timeout_seconds, 9)

    def test_historical_port_is_only_a_default_candidate(self) -> None:
        config = VLLMConfig.from_environment({"VLLM_MODEL_PATH": "/models/approved"})
        self.assertEqual(config.port, 8000)
        self.assertEqual(config.base_url, "http://127.0.0.1:8000/v1")

    def test_ipv6_loopback_default_url_is_valid(self) -> None:
        config = VLLMConfig.from_environment(
            {"VLLM_HOST": "::1", "VLLM_PORT": "9000", "VLLM_MODEL_PATH": "/m"}
        )
        self.assertEqual(config.base_url, "http://[::1]:9000/v1")

    def test_remote_host_credentials_and_port_mismatch_are_rejected(self) -> None:
        invalid = (
            {**ENV, "VLLM_HOST": "0.0.0.0", "VLLM_BASE_URL": "http://0.0.0.0:8123/v1"},
            {**ENV, "VLLM_BASE_URL": "http://user:pass@127.0.0.1:8123/v1"},
            {**ENV, "VLLM_BASE_URL": "http://127.0.0.1:9999/v1"},
            {**ENV, "VLLM_BASE_URL": "http://127.0.0.1:8123/not-v1"},
        )
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                VLLMConfig.from_environment(values)

    def test_model_path_is_required(self) -> None:
        with self.assertRaises(ValidationError):
            VLLMConfig.from_environment({})


class VLLMClientTests(unittest.TestCase):
    def test_list_models_uses_openai_compatible_endpoint(self) -> None:
        transport = RecordingTransport({"data": [{"id": "approved-model"}]})
        client = VLLMClient(VLLMConfig.from_environment(ENV), transport)
        self.assertEqual(client.list_models(), ("approved-model",))
        request, timeout = transport.calls[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8123/v1/models")
        self.assertEqual(request.method, "GET")
        self.assertEqual(timeout, 9)

    def test_chat_request_and_standardized_response(self) -> None:
        transport = RecordingTransport(
            {
                "id": "request-1",
                "model": "approved-model",
                "choices": [{"message": {"content": '{"action":"no_change"}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            }
        )
        client = VLLMClient(VLLMConfig.from_environment(ENV), transport)
        result = client.chat(
            (ChatMessage(role="user", content="deployment-visible observation"),),
            max_tokens=128,
        )
        self.assertEqual(result.request_id, "request-1")
        self.assertEqual(result.completion_tokens, 4)
        request, _ = transport.calls[0]
        body = json.loads(request.data)
        self.assertEqual(body["model"], ENV["VLLM_MODEL_PATH"])
        self.assertNotIn("api_key", body)

    def test_generation_bounds_are_enforced_before_transport(self) -> None:
        transport = RecordingTransport({})
        client = VLLMClient(VLLMConfig.from_environment(ENV), transport)
        with self.assertRaises(ValueError):
            client.chat((ChatMessage(role="user", content="x"),), max_tokens=5000)
        with self.assertRaises(ValueError):
            client.chat((), max_tokens=1)
        self.assertEqual(transport.calls, [])

    def test_malformed_or_network_failure_is_sanitized(self) -> None:
        malformed = VLLMClient(VLLMConfig.from_environment(ENV), RecordingTransport({}))
        with self.assertRaisesRegex(RuntimeError, "malformed response"):
            malformed.chat((ChatMessage(role="user", content="x"),), max_tokens=1)

        def failed_transport(request: object, timeout: int) -> bytes:
            raise urllib.error.URLError("sensitive endpoint detail")

        failed = VLLMClient(VLLMConfig.from_environment(ENV), failed_transport)
        with self.assertRaisesRegex(RuntimeError, "URLError") as raised:
            failed.list_models()
        self.assertNotIn("sensitive endpoint detail", str(raised.exception))

    def test_no_vllm_or_torch_runtime_import(self) -> None:
        import apt_detection_agent.llm.vllm_client as module

        source_names = set(module.__dict__)
        self.assertNotIn("vllm", source_names)
        self.assertNotIn("torch", source_names)


if __name__ == "__main__":
    unittest.main()
