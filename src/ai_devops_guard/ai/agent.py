"""Provider-independent, bounded structured worker. Permissions live in the dispatcher."""

import json
from abc import ABC, abstractmethod

from pydantic import Field, JsonValue

from ai_devops_guard.ai.base import (
    Explanation,
    ExplanationContext,
    ProviderCapabilities,
    RuleKnowledge,
    RuleLookupArguments,
    ToolExecutor,
)
from ai_devops_guard.models import Contract


class ModelResponse(Contract):
    text: str = Field(min_length=1, max_length=2000)


class ModelToolRequest(Contract):
    tool: str = Field(min_length=1, max_length=80)
    arguments: dict[str, JsonValue]


class StructuredAgent(ABC):
    status = "complete"
    capabilities = ProviderCapabilities(structured_json=True, bounded_rule_lookup=True)
    request_ids: list[str]
    _executor: ToolExecutor | None = None

    def bind_tool_executor(self, executor: ToolExecutor) -> None:
        self._executor = executor

    @abstractmethod
    def _generate(self, messages: list[dict], schema: dict) -> str:
        """Return one bounded JSON response or raise; no retries or provider fallback."""

    def explain(self, context: ExplanationContext) -> Explanation:
        facts = context.model_dump()
        if context.rule_ids:
            if self._executor is None:
                raise ValueError("read-only tool executor not bound")
            schema = ModelToolRequest.model_json_schema()
            schema["properties"]["tool"]["enum"] = ["lookup_rules"]
            arguments_schema = RuleLookupArguments.model_json_schema()
            schema.setdefault("$defs", {}).update(arguments_schema.pop("$defs", {}))
            schema["properties"]["arguments"] = arguments_schema
            proposal = ModelToolRequest.model_validate_json(
                self._generate(
                    [
                        {
                            "role": "system",
                            "content": (
                                "Propose one read-only tool call as JSON, not an explanation. "
                                "Use tool lookup_rules. Arguments must contain "
                                "the supplied rule_ids. "
                                "You cannot execute infrastructure operations."
                            ),
                        },
                        {"role": "user", "content": json.dumps(facts)},
                    ],
                    schema,
                )
            )
            knowledge = self._executor(proposal.tool, proposal.arguments)
            if not isinstance(knowledge, RuleKnowledge):
                raise ValueError("unexpected tool result")
            facts["trusted_rule_context"] = knowledge.model_dump()
        parsed = ModelResponse.model_validate_json(
            self._generate(
                [
                    {
                        "role": "system",
                        "content": (
                            "You explain infrastructure security findings to a DevOps engineer. "
                            "Return JSON with one text field. Write two brief sentences. "
                            "Explain facts, impact and remediation in fewer than 65 words. "
                            "Do not invent findings or severities. "
                            "Coverage gaps mean the review is incomplete. Zero findings mean only "
                            "the supported checks found nothing. Never approve or execute changes."
                        ),
                    },
                    {"role": "user", "content": json.dumps(facts)},
                ],
                ModelResponse.model_json_schema(),
            )
        )
        return Explanation(status="complete", text=parsed.text)
