from pathlib import Path

import pytest
import yaml

from ai_devops_guard.pipeline import run_review
from ai_devops_guard.rules.kubernetes import parse_manifests, review_manifests

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "kubernetes"


@pytest.mark.parametrize(
    "name,decision,count",
    [
        ("safe", "pass", 0),
        ("risky", "review_required", 2),
    ],
)
def test_kubernetes_pipeline(tmp_path, name, decision, count):
    report, _ = run_review(EXAMPLES / f"{name}.yaml", tmp_path, input_kind="kubernetes")
    assert report.decision == decision
    assert len(report.findings) == count
    assert report.input_kind == "kubernetes"
    assert report.source_digest
    assert report.analysis_complete


@pytest.mark.parametrize(
    "text",
    [
        "",
        "[]",
        "kind: Pod\nkind: Deployment",
        "a: &anchor {x: 1}\nb: *anchor",
        "!!python/object/apply:os.system ['touch /tmp/guard-should-not-execute']",
    ],
)
def test_rejects_unsafe_or_ambiguous_yaml(text):
    with pytest.raises((ValueError, yaml.YAMLError)):
        parse_manifests(text.encode())


def test_resource_limit():
    with pytest.raises(ValueError, match="too many"):
        parse_manifests(b"kind: Pod\n---\n" * 129)


@pytest.mark.parametrize(
    "kind,version,path",
    [
        ("Pod", "v1", []),
        ("Deployment", "apps/v1", ["template", "spec"]),
        ("StatefulSet", "apps/v1", ["template", "spec"]),
        ("DaemonSet", "apps/v1", ["template", "spec"]),
        ("ReplicaSet", "apps/v1", ["template", "spec"]),
        ("Job", "batch/v1", ["template", "spec"]),
        ("CronJob", "batch/v1", ["jobTemplate", "spec", "template", "spec"]),
    ],
)
def test_workload_shapes(kind, version, path):
    pod = {"containers": [{"name": "api", "securityContext": {"privileged": True}}]}
    spec = pod
    for part in reversed(path):
        spec = {part: spec}
    result = review_manifests(
        [{"kind": kind, "apiVersion": version, "metadata": {"name": "example"}, "spec": spec}]
    )
    assert len(result.findings) == 1
    assert result.findings[0].severity == "critical"
    assert result.analysis_complete


@pytest.mark.parametrize("group", ["containers", "initContainers", "ephemeralContainers"])
def test_all_container_groups(group):
    spec = {"containers": [{"name": "main"}]}
    spec[group] = [{"name": "privileged", "securityContext": {"privileged": True}}]
    result = review_manifests(
        [{"kind": "Pod", "apiVersion": "v1", "metadata": {"name": "test"}, "spec": spec}]
    )
    assert len(result.findings) == 1
    assert f"/{group}/0/" in result.findings[0].evidence_path


@pytest.mark.parametrize(
    "update",
    [
        {"kind": "Secret"},
        {"apiVersion": "apps/v999"},
        {"metadata": {}},
        {"spec": {"containers": []}},
        {"spec": {"containers": [{"name": "api", "securityContext": {"privileged": "true"}}]}},
    ],
)
def test_unsupported_or_malformed_is_not_complete(update):
    doc = {
        "kind": "Pod",
        "apiVersion": "v1",
        "metadata": {"name": "test"},
        "spec": {"containers": [{"name": "api"}]},
    } | update
    assert not review_manifests([doc]).analysis_complete


@pytest.mark.parametrize(
    "field,value",
    [
        ("verbs", ["*"]),
        ("resources", ["pods/*"]),
        ("apiGroups", ["*"]),
        ("nonResourceURLs", ["/healthz/*"]),
    ],
)
def test_rbac_wildcards(field, value):
    rule = {"verbs": ["get"], "apiGroups": [""], "resources": ["pods"], field: value}
    result = review_manifests(
        [
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRole",
                "metadata": {"name": "demo"},
                "rules": [rule],
            }
        ]
    )
    assert len(result.findings) == 1
    assert result.findings[0].rule_id == "K8S-002"
