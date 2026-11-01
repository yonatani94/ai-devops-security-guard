"""Review desired Kubernetes manifests without connecting to a cluster."""

import yaml
from yaml.events import AliasEvent

from ai_devops_guard.models import Finding
from ai_devops_guard.rules.terraform import RuleResult


class StrictLoader(yaml.SafeLoader):
    def compose_node(self, parent, index):
        if self.check_event(AliasEvent):
            raise ValueError("YAML aliases are not supported")
        return super().compose_node(parent, index)

    def construct_mapping(self, node, deep=False):
        mapping = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in mapping:
                raise ValueError("duplicate or non-string YAML key")
            mapping[key] = self.construct_object(value_node, deep=deep)
        return mapping


def parse_manifests(data: bytes) -> list[dict]:
    docs = []
    for doc in yaml.load_all(data, Loader=StrictLoader):
        if doc is None:
            continue
        if not isinstance(doc, dict):
            raise ValueError("expected Kubernetes object")
        docs.append(doc)
        if len(docs) > 128:
            raise ValueError("too many Kubernetes objects")
    if not docs:
        raise ValueError("empty Kubernetes input")
    return docs


def _mapping(value):
    if not isinstance(value, dict):
        raise ValueError("expected object")
    return value


def _strings(value):
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError("expected string list")
    return value


def _containers(doc, base, address):
    paths = {
        "Pod": ("spec",),
        "Deployment": ("spec", "template", "spec"),
        "StatefulSet": ("spec", "template", "spec"),
        "DaemonSet": ("spec", "template", "spec"),
        "ReplicaSet": ("spec", "template", "spec"),
        "Job": ("spec", "template", "spec"),
        "CronJob": ("spec", "jobTemplate", "spec", "template", "spec"),
    }
    spec = doc
    path = base
    for part in paths[doc["kind"]]:
        spec = _mapping(spec[part])
        path += f"/{part}"
    findings = []
    for group in ("containers", "initContainers", "ephemeralContainers"):
        containers = spec[group] if group == "containers" else spec.get(group, [])
        if not isinstance(containers, list) or (group == "containers" and not containers):
            raise ValueError("invalid containers")
        for index, container in enumerate(containers):
            container = _mapping(container)
            if not isinstance(container.get("name"), str) or not container["name"]:
                raise ValueError("invalid container name")
            context = _mapping(container.get("securityContext", {}))
            privileged = context.get("privileged", False)
            if type(privileged) is not bool:
                raise ValueError("privileged must be boolean")
            if privileged:
                findings.append(
                    Finding(
                        rule_id="K8S-001",
                        resource_address=address,
                        severity="critical",
                        summary="Container explicitly enables privileged mode.",
                        evidence_path=f"{path}/{group}/{index}/securityContext/privileged",
                        remediation="Remove privileged mode and grant only required capabilities.",
                    )
                )
    return findings


def _rbac(doc, base, address):
    rules = doc["rules"]
    if not isinstance(rules, list):
        raise ValueError("invalid RBAC rules")
    findings = []
    for index, rule in enumerate(rules):
        rule = _mapping(rule)
        verbs = _strings(rule["verbs"])
        if not verbs:
            raise ValueError("missing RBAC verbs")
        if "resources" not in rule and "nonResourceURLs" not in rule:
            raise ValueError("missing RBAC scope")
        for field in ("verbs", "apiGroups", "resources", "nonResourceURLs"):
            values = _strings(rule.get(field, []))
            if any("*" in value for value in values):
                findings.append(
                    Finding(
                        rule_id="K8S-002",
                        resource_address=address,
                        severity="high",
                        summary="RBAC rule includes wildcard permissions.",
                        evidence_path=f"{base}/rules/{index}/{field}",
                        remediation="List only required API groups, resources and verbs.",
                    )
                )
    return findings


def review_manifests(docs: list[dict]) -> RuleResult:
    result = RuleResult()
    versions = {
        "Pod": "v1",
        "Job": "batch/v1",
        "CronJob": "batch/v1",
        "Role": "rbac.authorization.k8s.io/v1",
        "ClusterRole": "rbac.authorization.k8s.io/v1",
    }
    for kind in ("Deployment", "StatefulSet", "DaemonSet", "ReplicaSet"):
        versions[kind] = "apps/v1"
    for index, doc in enumerate(docs):
        base = f"/documents/{index}"
        try:
            kind = doc["kind"]
            if kind not in versions or doc.get("apiVersion") != versions[kind]:
                raise ValueError("unsupported kind or API version")
            meta = _mapping(doc["metadata"])
            name, namespace = meta["name"], meta.get("namespace", "default")
            if not all(isinstance(v, str) and 0 < len(v) <= 253 for v in (name, namespace)):
                raise ValueError("invalid resource metadata")
            address = f"{kind}/{namespace}/{name}"
            check = _rbac if kind in {"Role", "ClusterRole"} else _containers
            result.findings.extend(check(doc, base, address))
        except (ValueError, TypeError, KeyError, AttributeError):
            result.coverage_gaps.append(f"{base}: malformed or unsupported Kubernetes object")
    return result
