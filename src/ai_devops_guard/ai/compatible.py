"""Company gateway transport using the Chat Completions wire protocol."""

import json
import os
import re
from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urlsplit

from pydantic import SecretStr

from ai_devops_guard.ai.agent import StructuredAgent
from ai_devops_guard.ai.config import AISettings


class CompatibleProvider(StructuredAgent):
    provider_id = "openai-compatible"
    MAX_RESPONSE_BYTES = 65_536

    def __init__(self, settings: AISettings):
        self.model = settings.model
        self.timeout = settings.timeout_seconds
        self.schema_mode = settings.schema_mode
        self.token_parameter = settings.token_parameter
        self.max_output_tokens = settings.max_output_tokens
        self.request_ids = []
        self._executor = None
        endpoint = settings.endpoint or ""
        # urlsplit normalizes certain control characters; reject before parsing.
        if any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in endpoint):
            raise ValueError("invalid endpoint")
        parts = urlsplit(endpoint)
        if (
            not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
            or "\\" in endpoint
            or not re.fullmatch(r"[A-Za-z0-9_/-]*", parts.path)
            or ".." in parts.path
        ):
            raise ValueError("endpoint must be a base URL without credentials or query parameters")
        loopback = parts.hostname in {"127.0.0.1", "::1"}
        if parts.scheme == "http" and loopback:
            if settings.auth_mode != "none":
                raise ValueError("credentials are not sent over cleartext loopback")
        elif parts.scheme == "https":
            allowed = {
                host.strip().lower()
                for host in os.environ.get("GUARD_ALLOWED_AI_HOSTS", "").split(",")
                if host.strip()
            }
            if parts.hostname.lower() not in allowed or settings.auth_mode == "none":
                raise ValueError(
                    "HTTPS gateway requires a trusted host allowlist and authentication"
                )
        else:
            raise ValueError("remote gateways require HTTPS; cleartext is loopback-only")
        token = os.environ.get("GUARD_AI_TOKEN", "") if settings.auth_mode != "none" else ""
        if settings.auth_mode != "none" and (
            not token or any(ord(c) < 33 or ord(c) > 126 for c in token) or len(token) > 16_384
        ):
            raise ValueError("missing or invalid GUARD_AI_TOKEN")
        self._token = SecretStr(token)
        self._auth_mode = settings.auth_mode
        self._scheme, self._host = parts.scheme, parts.hostname
        self._port = parts.port
        self._path = parts.path.rstrip("/") + "/chat/completions"

    def _generate(self, messages: list[dict], schema: dict) -> str:
        # Some compatible gateways offer JSON mode only. It must be explicitly selected;
        # local validation and the dispatcher remain mandatory in both modes.
        response_format = (
            {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.get("title", "guard_response"),
                    "strict": True,
                    "schema": schema,
                },
            }
            if self.schema_mode == "json_schema"
            else {"type": "json_object"}
        )
        messages = [dict(message) for message in messages]
        messages[0]["content"] += " Output JSON matching this schema: " + json.dumps(schema)
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "response_format": response_format,
            self.token_parameter: self.max_output_tokens,
        }
        headers = {"Content-Type": "application/json"}
        if self._auth_mode == "bearer":
            headers["Authorization"] = "Bearer " + self._token.get_secret_value()
        elif self._auth_mode == "api-key":
            headers["api-key"] = self._token.get_secret_value()
        factory = HTTPSConnection if self._scheme == "https" else HTTPConnection
        connection = factory(self._host, self._port, timeout=self.timeout)
        try:
            connection.request("POST", self._path, json.dumps(payload), headers=headers)
            response = connection.getresponse()
            # No redirects, retries, proxy discovery, error-body logging, or fallback.
            if response.status != 200:
                raise ValueError("gateway request failed")
            body = response.read(self.MAX_RESPONSE_BYTES + 1)
            if len(body) > self.MAX_RESPONSE_BYTES:
                raise ValueError("gateway response exceeds limit")
            envelope = json.loads(body)
            choices = envelope["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError("expected exactly one completion")
            choice = choices[0]
            message = choice["message"]
            if (
                choice.get("finish_reason") != "stop"
                or message.get("refusal")
                or message.get("tool_calls")
                or not isinstance(message.get("content"), str)
            ):
                raise ValueError("refused, truncated, or unsupported gateway completion")
            request_id = envelope.get("id")
            if isinstance(request_id, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
                self.request_ids.append(request_id)
            return message["content"]
        finally:
            connection.close()
