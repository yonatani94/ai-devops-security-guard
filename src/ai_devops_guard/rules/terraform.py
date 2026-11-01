"""Narrow checks of planned after-state, not effective AWS authorization."""

import json
from ipaddress import ip_network

from pydantic import Field, JsonValue

from ai_devops_guard.models import Contract, Finding, TerraformPlan


class RuleResult(Contract):
    findings: list[Finding] = Field(default_factory=list)
    coverage_gaps: list[str] = Field(default_factory=list)

    @property
    def analysis_complete(self) -> bool:
        return not self.coverage_gaps


def _marked(value: JsonValue) -> bool:
    if isinstance(value, dict):
        return any(_marked(item) for item in value.values())
    if isinstance(value, list):
        return any(_marked(item) for item in value)
    return value is True


def _strings(value: JsonValue) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValueError("expected string or list of strings")


def _ssh(after: dict[str, JsonValue], address: str, base: str) -> list[Finding]:
    findings = []
    ingress = after["ingress"]
    if not isinstance(ingress, list):
        raise ValueError("unsupported ingress")
    for index, rule in enumerate(ingress):
        protocol = rule["protocol"]
        if protocol not in {"tcp", "6", "-1", "udp", "17", "icmp", "1", "icmpv6", "58"}:
            raise ValueError("unsupported protocol")
        if protocol in {"tcp", "6"}:
            start, end = rule["from_port"], rule["to_port"]
            if type(start) is not int or type(end) is not int or not 0 <= start <= end <= 65535:
                raise ValueError("invalid TCP range")
            exposes_ssh = start <= 22 <= end
        else:
            exposes_ssh = protocol == "-1"
        # Parse even non-SSH sources so malformed input remains visible.
        for field in ("cidr_blocks", "ipv6_cidr_blocks"):
            sources = rule.get(field, [])
            if not isinstance(sources, list):
                raise ValueError("unsupported CIDR list")
            for source_index, source in enumerate(sources):
                if not isinstance(source, str):
                    raise ValueError("invalid CIDR")
                network = ip_network(source, strict=False)
                if exposes_ssh and network.prefixlen == 0:
                    findings.append(
                        Finding(
                            rule_id="TF-AWS-001",
                            resource_address=address,
                            severity="high",
                            summary="Ingress permits public access to TCP port 22.",
                            evidence_path=f"{base}/ingress/{index}/{field}/{source_index}",
                            remediation="Restrict SSH to approved networks or remove SSH ingress.",
                        )
                    )
    return findings


def _iam(after: dict[str, JsonValue], address: str, base: str) -> list[Finding]:
    policy = json.loads(after["policy"])
    statements = policy["Statement"]
    if isinstance(statements, dict):
        statements = [statements]
    if not isinstance(statements, list) or not statements:
        raise ValueError("unsupported policy statements")
    findings = []
    for statement in statements:
        if statement["Effect"] not in {"Allow", "Deny"}:
            raise ValueError("unsupported effect")
        if "NotAction" in statement or "NotResource" in statement:
            raise ValueError("negative IAM elements not supported")
        actions = _strings(statement["Action"])
        resources = _strings(statement["Resource"])
        if not actions or not resources:
            raise ValueError("empty IAM elements")
        if statement["Effect"] == "Allow" and "*" in actions and "*" in resources:
            findings.append(
                Finding(
                    rule_id="TF-AWS-002",
                    resource_address=address,
                    severity="high",
                    summary="IAM statement allows wildcard actions on wildcard resources; "
                    "conditions and external policy controls require human review.",
                    # Policy is a JSON string in the outer document: do not invent nested pointers.
                    evidence_path=f"{base}/policy",
                    remediation="Scope actions and resources to required workload permissions.",
                )
            )
    return findings


def review_plan(plan: TerraformPlan) -> RuleResult:
    result = RuleResult()
    checks = {"aws_security_group": _ssh, "aws_iam_policy": _iam}
    for index, resource in enumerate(plan.resource_changes):
        path = f"/resource_changes/{index}/change/after"
        change = resource.change
        if change.actions in (["no-op"], ["delete"]):
            continue
        if resource.mode != "managed" or resource.type not in checks:
            result.coverage_gaps.append(f"{path}: unsupported resource or mode")
            continue
        if "forget" in change.actions:
            result.coverage_gaps.append(f"{path}: forget action requires separate review")
            continue
        fields = ("ingress",) if resource.type == "aws_security_group" else ("policy",)
        unknown = any(_marked(change.after_unknown.get(field)) for field in fields)
        sensitive = change.after_sensitive is True or (
            isinstance(change.after_sensitive, dict)
            and any(_marked(change.after_sensitive.get(field)) for field in fields)
        )
        if unknown or sensitive:
            result.coverage_gaps.append(f"{path}: unknown or sensitive values remain")
        if change.after is None:
            result.coverage_gaps.append(f"{path}: missing planned state")
            continue
        try:
            result.findings.extend(checks[resource.type](change.after, resource.address, path))
        except (ValueError, TypeError, KeyError, AttributeError):
            result.coverage_gaps.append(f"{path}: malformed or unsupported rule input")
    return result
