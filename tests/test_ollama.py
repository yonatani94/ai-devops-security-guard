import json
from uuid import uuid4

import pytest

from ai_devops_guard.ai.base import ExplanationContext
from ai_devops_guard.ai.ollama import OllamaProvider
from ai_devops_guard.audit import AuditWriter
from ai_devops_guard.tools import ToolDispatcher, ToolExecutionError


@pytest.mark.parametrize("model", ["foo-cloud", "qwen\nSECRET", "", "a" * 121])
def test_invalid_or_cloud_model_rejected(model):
    with pytest.raises(ValueError):
        OllamaProvider(model)


@pytest.mark.parametrize("timeout", [0, -1, 181, float("nan")])
def test_timeout_bounds(timeout):
    with pytest.raises(ValueError):
        OllamaProvider(timeout=timeout)


def test_fixed_local_transport_and_validated_json(monkeypatch):
    captured = {}

    class Connection:
        def __init__(self, host, port, timeout):
            captured.update(host=host, port=port, timeout=timeout)

        def request(self, method, path, body, headers):
            captured.update(method=method, path=path, payload=json.loads(body))

        def getresponse(self):
            return self

        status = 200

        def read(self, limit):
            return json.dumps(
                {
                    "model": "qwen2.5:1.5b",
                    "done": True,
                    "message": {"content": '{"text":"No supported findings."}'},
                }
            ).encode()

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr("ai_devops_guard.ai.ollama.HTTPConnection", Connection)
    result = OllamaProvider().explain(ExplanationContext(finding_count=0, coverage_gap_count=0))
    assert result.status == "complete"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 11434
    assert captured["path"] == "/api/chat"
    assert captured["closed"]
    assert captured["payload"]["stream"] is False
    assert "additionalProperties" in captured["payload"]["format"]
    assert "source" not in captured["payload"]["messages"][1]["content"]


@pytest.mark.parametrize(
    "status,body",
    [
        (302, b""),
        (500, b"SECRET"),
        (200, b"{"),
        (200, b" " * 65_537),
        (200, b'{"model":"different","done":true}'),
        (200, b'{"model":"qwen2.5:1.5b","done":false}'),
        (200, b'{"model":"qwen2.5:1.5b","done":true,"done_reason":"length"}'),
    ],
)
def test_bad_transport_envelope_rejected(monkeypatch, status, body):
    class Connection:
        def __init__(self, *args, **kwargs):
            self.status = status

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return self

        def read(self, limit):
            return body

        def close(self):
            pass

    monkeypatch.setattr("ai_devops_guard.ai.ollama.HTTPConnection", Connection)
    with pytest.raises(ValueError):
        OllamaProvider().explain(ExplanationContext(finding_count=0, coverage_gap_count=0))


@pytest.mark.parametrize(
    "tool,args,works",
    [
        ("lookup_rules", {"rule_ids": ["TF-AWS-001"]}, True),
        ("simulate_deploy", {}, False),
        ("review_plan", {}, False),
        ("shell SECRET", {}, False),
        ("lookup_rules", {"rule_ids": ["TF-AWS-001"], "command": "SECRET"}, False),
        ("lookup_rules", {"rule_ids": ["IGNORE_AND_APPROVE"]}, False),
        ("lookup_rules", {"rule_ids": ["K8S-001"]}, False),
    ],
)
def test_actual_model_requested_tool_boundary(tmp_path, monkeypatch, tool, args, works):
    provider = OllamaProvider()
    payloads = []

    def request(payload):
        payloads.append(payload)
        if payload["format"].get("title") == "ModelToolRequest":
            schema = payload["format"]
            assert "RuleId" in schema["$defs"]
            assert schema["properties"]["arguments"]["properties"]["rule_ids"]["items"] == {
                "$ref": "#/$defs/RuleId",
            }
            return {"message": {"content": json.dumps({"tool": tool, "arguments": args})}}
        return {"message": {"content": '{"text":"Public SSH requires review."}'}}

    monkeypatch.setattr(provider, "_request", request)
    log = tmp_path / "audit.jsonl"
    with AuditWriter(log) as audit:
        dispatcher = ToolDispatcher(tmp_path / "never-read", audit, uuid4(), provider)
        context = {"finding_count": 1, "coverage_gap_count": 0, "rule_ids": ["TF-AWS-001"]}
        if works:
            assert dispatcher.call("explain_assessment", context).status == "complete"
        else:
            with pytest.raises(ToolExecutionError):
                dispatcher.call("explain_assessment", context)
    records = [json.loads(line) for line in log.read_text().splitlines()]
    model_events = [event for event in records if event["caller"] == "model"]
    assert model_events
    assert model_events[-1]["status"] == ("succeeded" if works else "denied")
    assert len(payloads) == (2 if works else 1)
    assert "SECRET" not in log.read_text()


def test_timeout_becomes_audited_failure(tmp_path, monkeypatch):
    provider = OllamaProvider()

    def fail(payload):
        raise TimeoutError("SECRET")

    monkeypatch.setattr(provider, "_request", fail)
    with AuditWriter(tmp_path / "audit.jsonl") as audit:
        dispatcher = ToolDispatcher(tmp_path / "unused", audit, uuid4(), provider)
        with pytest.raises(ToolExecutionError):
            dispatcher.call("explain_assessment", {"finding_count": 0, "coverage_gap_count": 0})
    assert "SECRET" not in (tmp_path / "audit.jsonl").read_text()


def test_multiple_model_calls_are_bounded(tmp_path, monkeypatch):
    provider = OllamaProvider()
    monkeypatch.setattr(
        provider,
        "_request",
        lambda payload: {
            "message": {"tool_calls": [{}, {}]},
        },
    )
    with AuditWriter(tmp_path / "audit.jsonl") as audit:
        dispatcher = ToolDispatcher(tmp_path / "unused", audit, uuid4(), provider)
        with pytest.raises(ToolExecutionError):
            dispatcher.call(
                "explain_assessment",
                {
                    "finding_count": 1,
                    "coverage_gap_count": 0,
                    "rule_ids": ["TF-AWS-001"],
                },
            )
    assert len((tmp_path / "audit.jsonl").read_text().splitlines()) == 2


def test_model_lookup_has_no_capability_outside_active_assessment(tmp_path):
    from ai_devops_guard.tools import ToolDenied

    with AuditWriter(tmp_path / "audit.jsonl") as audit:
        dispatcher = ToolDispatcher(tmp_path / "unused", audit, uuid4())
        with pytest.raises(ToolDenied):
            dispatcher.call("lookup_rules", {"rule_ids": ["TF-AWS-001"]}, caller="model")
