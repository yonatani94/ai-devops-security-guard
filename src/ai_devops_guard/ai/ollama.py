"""Native Ollama transport for the provider-independent structured worker."""

import json
import re
from http.client import HTTPConnection

from ai_devops_guard.ai.agent import StructuredAgent


class OllamaProvider(StructuredAgent):
    provider_id = "ollama"
    MAX_RESPONSE_BYTES = 65_536

    def __init__(
        self, model: str = "qwen2.5:1.5b", timeout: float = 60, max_output_tokens: int = 384
    ):
        if not re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,120}", model) or "cloud" in model.lower():
            raise ValueError("invalid local model name")
        if not 0 < timeout <= 180:
            raise ValueError("timeout must be between 0 and 180 seconds")
        if type(max_output_tokens) is not int or not 64 <= max_output_tokens <= 4096:
            raise ValueError("invalid output token budget")
        self.model = model
        self.timeout = timeout
        self.max_output_tokens = max_output_tokens
        self._executor = None
        self.request_ids = []

    def _generate(self, messages: list[dict], schema: dict) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "keep_alive": "5m",
            "format": schema,
            "options": {
                "temperature": 0,
                "num_predict": self.max_output_tokens,
                "num_ctx": 2048,
                "seed": 7,
            },
            "messages": messages,
        }
        return self._request(payload)["message"]["content"]

    def _request(self, payload: dict) -> dict:
        connection = HTTPConnection("127.0.0.1", 11434, timeout=self.timeout)
        try:
            connection.request(
                "POST",
                "/api/chat",
                json.dumps(payload),
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError("local provider request failed")
            body = response.read(self.MAX_RESPONSE_BYTES + 1)
            if len(body) > self.MAX_RESPONSE_BYTES:
                raise ValueError("provider response exceeds limit")
            envelope = json.loads(body)
            if envelope.get("done") is not True or envelope.get("model") != self.model:
                raise ValueError("incomplete or mismatched model response")
            if envelope.get("done_reason") not in (None, "stop"):
                raise ValueError("model did not finish normally")
            return envelope
        finally:
            connection.close()
