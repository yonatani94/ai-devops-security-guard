from typing import Literal, Protocol

from pydantic import Field

from ai_devops_guard.models import Contract

type RuleId = Literal["TF-AWS-001", "TF-AWS-002", "K8S-001", "K8S-002"]


class RuleLookupArguments(Contract):
    rule_ids: list[RuleId] = Field(min_length=1, max_length=4)


class RuleKnowledge(Contract):
    rules: dict[RuleId, str]


class ExplanationContext(Contract):
    """Closed-vocabulary context for inference; no plan text or resource identifiers."""

    finding_count: int = Field(ge=0)
    coverage_gap_count: int = Field(ge=0)
    rule_ids: list[RuleId] = Field(
        default_factory=list,
        max_length=4,
    )


class Explanation(Contract):
    status: Literal["simulated", "complete"]
    text: str = Field(min_length=1, max_length=2000)


class ExplanationProvider(Protocol):
    def explain(self, context: ExplanationContext) -> Explanation: ...
