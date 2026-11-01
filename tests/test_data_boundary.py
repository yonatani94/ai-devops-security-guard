"""Canaries exercise the complete parser-to-HTTP and audit boundary offline."""

import json
from pathlib import Path

import pytest
import yaml

from ai_devops_guard.ai.config import create_provider, load_settings
from ai_devops_guard.pipeline import run_review

ROOT = Path(__file__).resolve().parents[1]
CANARIES = [
    "SYNTHETIC_PASSWORD_82b4d9",
    "CUSTOMER_RECORD_SENTINEL_a913",
    "APP_SOURCE_SENTINEL_c216",
    "PRIVATE_RESOURCE_SENTINEL_f841",
    "IGNORE_RULES_AND_CALL_SHELL_SENTINEL",
]


def canary_input(tmp_path, kind):
    if kind == "terraform":
        data = json.loads((ROOT / "examples/terraform/risky.plan.json").read_text())
        resource = data["resource_changes"][0]
        resource["address"] = CANARIES[3]
        resource["change"]["after"].update(
            password=CANARIES[0],
            customer_record=CANARIES[1],
            application_source=CANARIES[2],
            description=CANARIES[4],
        )
        data["output_changes"] = {"password": {"after": CANARIES[0], "after_sensitive": True}}
        content = json.dumps(data)
    else:
        data = {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": CANARIES[3], "annotations": {"instruction": CANARIES[4]}},
            "spec": {
                "containers": [
                    {
                        "name": "api",
                        "image": CANARIES[2],
                        "env": [{"name": "PASSWORD", "value": CANARIES[0]}],
                        "args": [CANARIES[1]],
                        "securityContext": {"privileged": True},
                    }
                ]
            },
        }
        content = yaml.safe_dump(data)
    source = tmp_path / "canary-input"
    source.write_text(content)
    return source


@pytest.mark.parametrize("adapter", ["ollama", "local-gateway"])
@pytest.mark.parametrize("kind", ["terraform", "kubernetes"])
def test_canaries_never_reach_http_requests_or_audit(tmp_path, monkeypatch, adapter, kind):
    provider = create_provider(load_settings(ROOT / f"examples/config/{adapter}.toml"))
    captured = []

    class Connection:
        status = 200

        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, body, headers):
            self.payload = json.loads(body)
            captured.append({"body": self.payload, "headers": headers, "path": path})

        def getresponse(self):
            return self

        def read(self, limit):
            facts = json.loads(self.payload["messages"][1]["content"])
            if "trusted_rule_context" not in facts:
                text = json.dumps(
                    {"tool": "lookup_rules", "arguments": {"rule_ids": facts["rule_ids"]}}
                )
            else:
                text = '{"text":"Review the infrastructure findings before deployment."}'
            if adapter == "ollama":
                envelope = {
                    "model": provider.model,
                    "done": True,
                    "done_reason": "stop",
                    "message": {"content": text},
                }
            else:
                envelope = {"choices": [{"finish_reason": "stop", "message": {"content": text}}]}
            return json.dumps(envelope).encode()

        def close(self):
            pass

    module = "ollama" if adapter == "ollama" else "compatible"
    monkeypatch.setattr(f"ai_devops_guard.ai.{module}.HTTPConnection", Connection)
    report, directory = run_review(
        canary_input(tmp_path, kind),
        tmp_path / "output",
        input_kind=kind,
        provider=provider,
    )
    assert report.decision == "review_required" and report.ai_status == "complete"
    assert len(captured) == 2
    emitted = json.dumps(captured) + (directory / "audit.jsonl").read_text()
    for canary in CANARIES:
        assert canary not in emitted
    for index, request in enumerate(captured):
        facts = json.loads(request["body"]["messages"][1]["content"])
        expected = {"finding_count", "coverage_gap_count", "rule_ids"}
        if index:
            expected.add("trusted_rule_context")
        assert set(facts) == expected
    # Reports intentionally retain private identifiers. This is not a full redactor.
    assert CANARIES[3] in (directory / "report.json").read_text()
    for canary in CANARIES[:3] + CANARIES[4:]:
        assert canary not in (directory / "report.json").read_text()


@pytest.mark.parametrize("adapter", ["ollama", "local-gateway"])
def test_sensitive_rule_values_skip_inference(tmp_path, monkeypatch, adapter):
    source = canary_input(tmp_path, "terraform")
    data = json.loads(source.read_text())
    data["resource_changes"][0]["change"]["after_sensitive"] = {"ingress": True}
    source.write_text(json.dumps(data))
    provider = create_provider(load_settings(ROOT / f"examples/config/{adapter}.toml"))

    def forbidden(*args, **kwargs):
        pytest.fail("incomplete sensitive input must not trigger inference")

    monkeypatch.setattr(provider, "_generate", forbidden)
    report, directory = run_review(source, tmp_path / "output", provider=provider)
    assert report.decision == "error" and report.ai_status == "not_run"
    assert not report.analysis_complete
    assert all(canary not in (directory / "audit.jsonl").read_text() for canary in CANARIES)
