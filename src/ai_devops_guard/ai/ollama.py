"""At most two bounded structured requests to a fixed loopback Ollama endpoint."""

import json
import re
from collections.abc import Callable
from http.client import HTTPConnection

from pydantic import Field, JsonValue

from ai_devops_guard.ai.base import (
    Explanation,
    ExplanationContext,
    RuleKnowledge,
    RuleLookupArguments,
)
from ai_devops_guard.models import Contract

RULE_CATALOG = {
    "TF-AWS-001": "Public IPv4/IPv6 ingress permits TCP port 22. Restrict SSH sources.",
    "TF-AWS-002": "An IAM Allow statement uses wildcard actions and resources. Scope privileges.",
    "K8S-001": "A workload explicitly enables a privileged container. Remove privileged mode.",
    "K8S-002": "RBAC wildcard permissions. Scope API groups, resources and verbs.",
}


class ModelResponse(Contract):
    text: str = Field(min_length=1, max_length=2000)


class ModelToolRequest(Contract):
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, JsonValue]


class OllamaProvider:
    """One bounded read-only tool proposal, followed by an advisory explanation.

    Only application-owned rule descriptions and counts enter the prompt. The server
    is a trusted local dependency; timeouts apply to socket operations, with no retry.
    """

    status = "complete"
    MAX_RESPONSE_BYTES = 65_536

    def __init__(self, model: str = "qwen2.5:1.5b", timeout: float = 60):
        if not re.fullmatch(r"[a-zA-Z0-9_.:/-]{1,120}", model) or "cloud" in model.lower():
            raise ValueError("invalid local model name")
        if not 0 < timeout <= 180:
            raise ValueError("timeout must be between 0 and 180 seconds")
        self.model = model
        self.timeout = timeout
        self._executor = None

    def bind_tool_executor(self, executor: Callable) -> None:
        self._executor = executor

    def explain(self, context: ExplanationContext) -> Explanation:
        facts = context.model_dump()
        payload = {
            "model": self.model,
            "stream": False,
            "keep_alive": "5m",
            "format": ModelResponse.model_json_schema(),
            "options": {"temperature": 0, "num_predict": 384, "num_ctx": 2048, "seed": 7},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You explain infrastructure security findings to a DevOps engineer. "
                        "Return JSON with one text field. Write two brief sentences. "
                        "Explain facts, impact and remediation in fewer than 65 words. "
                        "Do not invent findings or severities. "
                        "If coverage gaps exist, say review is incomplete. Zero findings mean only "
                        "the supported checks found nothing. You cannot approve or execute changes."
                    ),
                },
                {"role": "user", "content": json.dumps(facts)},
            ],
        }
        if context.rule_ids:
            if self._executor is None:
                raise ValueError("read-only tool executor not bound")
            lookup_payload = dict(payload)
            schema = ModelToolRequest.model_json_schema()
            schema["properties"]["tool"]["enum"] = ["lookup_rules"]
            arguments_schema = RuleLookupArguments.model_json_schema()
            # JSON Schema refs resolve at the root, not inside the nested arguments schema.
            schema.setdefault("$defs", {}).update(arguments_schema.pop("$defs", {}))
            schema["properties"]["arguments"] = arguments_schema
            lookup_payload["format"] = schema
            lookup_payload["messages"] = [
                {
                    "role": "system",
                    "content": (
                        "Propose one read-only tool call as JSON, not an explanation. "
                        "Use tool lookup_rules with arguments containing the supplied rule_ids. "
                        "You cannot execute infrastructure operations."
                    ),
                },
                {"role": "user", "content": json.dumps(facts)},
            ]
            message = self._request(lookup_payload)["message"]
            proposal = ModelToolRequest.model_validate_json(message["content"])
            knowledge = self._executor(proposal.tool, proposal.arguments)
            if not isinstance(knowledge, RuleKnowledge):
                raise ValueError("unexpected tool result")
            facts["trusted_rule_context"] = knowledge.model_dump()
            payload["messages"][1]["content"] = json.dumps(facts)
        envelope = self._request(payload)
        parsed = ModelResponse.model_validate_json(envelope["message"]["content"])
        return Explanation(status="complete", text=parsed.text)

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
