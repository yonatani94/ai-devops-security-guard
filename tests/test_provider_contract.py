import json
from pathlib import Path

import pytest

from ai_devops_guard.ai.config import create_provider, load_settings
from ai_devops_guard.pipeline import run_review

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("adapter", ["ollama", "local-gateway"])
@pytest.mark.parametrize(
    "tool,arguments,expected",
    [
        ("lookup_rules", {"rule_ids": ["TF-AWS-001", "TF-AWS-002"]}, "review_required"),
        ("simulate_deploy", {}, "error"),
        ("lookup_rules", {"rule_ids": ["K8S-001"]}, "error"),
        ("lookup_rules", {"rule_ids": ["TF-AWS-001"], "command": "SECRET"}, "error"),
    ],
)
def test_provider_switch_preserves_model_permission_boundary(
    tmp_path, monkeypatch, adapter, tool, arguments, expected
):
    provider = create_provider(load_settings(ROOT / f"examples/config/{adapter}.toml"))
    requests = []

    def generate(messages, schema):
        requests.append(messages)
        if schema["title"] == "ModelToolRequest":
            return json.dumps({"tool": tool, "arguments": arguments})
        return '{"text":"Review public SSH and wildcard IAM access."}'

    monkeypatch.setattr(provider, "_generate", generate)
    report, path = run_review(
        ROOT / "examples/terraform/risky.plan.json", tmp_path, provider=provider
    )
    assert report.decision == expected
    assert report.ai_provider == provider.provider_id
    assert len(report.findings) == 2
    audit = (path / "audit.jsonl").read_text()
    assert "SECRET" not in audit
    events = [json.loads(line) for line in audit.splitlines()]
    model = [e for e in events if e["caller"] == "model"]
    assert model[-1]["status"] == ("succeeded" if expected == "review_required" else "denied")
    assert len(requests) == (2 if expected == "review_required" else 1)
    assert all("aws_security_group.ssh" not in json.dumps(m) for m in requests)


@pytest.mark.parametrize("adapter", ["ollama", "local-gateway"])
def test_provider_failure_never_falls_back(tmp_path, monkeypatch, adapter):
    provider = create_provider(load_settings(ROOT / f"examples/config/{adapter}.toml"))

    def fail(*args):
        raise TimeoutError("SECRET provider failure")

    monkeypatch.setattr(provider, "_generate", fail)
    report, path = run_review(
        ROOT / "examples/terraform/safe.plan.json", tmp_path, provider=provider
    )
    assert report.decision == "error"
    assert report.ai_status == "failed"
    assert not report.ai_explanation
    assert "SECRET" not in (path / "audit.jsonl").read_text()
