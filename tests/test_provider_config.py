import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ai_devops_guard.ai.base import ExplanationContext, ExplanationProvider
from ai_devops_guard.ai.compatible import CompatibleProvider
from ai_devops_guard.ai.config import AISettings, create_provider, load_settings
from ai_devops_guard.cli import main

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name,provider",
    [
        ("ollama", "ollama"),
        ("local-gateway", "openai-compatible"),
    ],
)
def test_load_real_config_and_provider_contract(name, provider):
    settings = load_settings(ROOT / f"examples/config/{name}.toml")
    adapter = create_provider(settings)
    assert adapter.provider_id == provider
    assert isinstance(adapter, ExplanationProvider)
    assert adapter.capabilities.structured_json
    assert adapter.capabilities.bounded_rule_lookup


def test_no_config_is_offline_fake():
    assert create_provider(load_settings(None)).provider_id == "fake"


@pytest.mark.parametrize(
    "fields",
    [
        {"provider": "unknown"},
        {"timeout_seconds": 0},
        {"timeout_seconds": float("nan")},
        {"max_output_tokens": 1},
        {"max_output_tokens": 9000},
        {"schema_mode": "auto"},
        {"api_key": "SECRET"},
        {"provider": "openai-compatible"},
        {"provider": "fake", "model": "ignored-model"},
        {"provider": "ollama", "endpoint": "https://ignored"},
        {"provider": "ollama", "model": "invalid\nname"},
    ],
)
def test_invalid_config_fails_closed(fields):
    with pytest.raises(ValidationError):
        AISettings(**fields)


@pytest.mark.parametrize(
    "text",
    [
        '[ai]\nprovider="fake"\nprovider="ollama"',
        '[ai]\nprovider="fake"\n[unexpected]\nx=1',
        '[ai]\nprovider="fake"\napi_key="SECRET"',
    ],
)
def test_config_errors_do_not_leak_to_console(tmp_path, capsys, text):
    config = tmp_path / "config.toml"
    config.write_text(text)
    code = main(
        [
            "review",
            "--plan",
            str(ROOT / "examples/terraform/safe.plan.json"),
            "--ai-config",
            str(config),
            "--output-dir",
            str(tmp_path / "output"),
        ]
    )
    assert code == 2
    captured = capsys.readouterr()
    assert "SECRET" not in captured.err + captured.out


def gateway(endpoint="https://gateway.example.com/v1", **kwargs):
    return AISettings(
        provider="openai-compatible",
        model="approved-deployment",
        endpoint=endpoint,
        auth_mode="bearer",
        **kwargs,
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://gateway.example.com/v1",
        "ftp://gateway.example.com/v1",
        "https://user:SECRET@gateway.example.com/v1",
        "https://gateway.example.com/v1?key=SECRET",
        "https://gateway.example.com/v1#fragment",
        "https://gateway.example.com/../v1",
        "https://gateway.example.com/%2f/v1",
        "https://gateway.example.com/\npath",
        "https://gateway.example.com\\@evil.example.com/v1",
        "https://evil.example.com/v1",
        "https://gateway.example.com.evil.example.com/v1",
        "https://gateway.example.com:99999/v1",
    ],
)
def test_endpoint_validation_prevents_credential_egress(monkeypatch, endpoint):
    monkeypatch.setenv("GUARD_ALLOWED_AI_HOSTS", "gateway.example.com")
    monkeypatch.setenv("GUARD_AI_TOKEN", "SECRET")
    with pytest.raises(ValueError):
        CompatibleProvider(gateway(endpoint))


def test_remote_host_allowlist_not_read_from_repository_config(monkeypatch):
    monkeypatch.delenv("GUARD_ALLOWED_AI_HOSTS", raising=False)
    monkeypatch.setenv("GUARD_AI_TOKEN", "SECRET")
    with pytest.raises(ValueError):
        CompatibleProvider(gateway())


@pytest.mark.parametrize("token", ["", "has spaces", "SECRET\r\nInjected: header"])
def test_bad_tokens_rejected(monkeypatch, token):
    monkeypatch.setenv("GUARD_ALLOWED_AI_HOSTS", "gateway.example.com")
    monkeypatch.setenv("GUARD_AI_TOKEN", token)
    with pytest.raises(ValueError):
        CompatibleProvider(gateway())


def test_cleartext_loopback_never_receives_credentials(monkeypatch):
    monkeypatch.setenv("GUARD_AI_TOKEN", "SECRET")
    with pytest.raises(ValueError):
        CompatibleProvider(gateway("http://127.0.0.1:11434/v1"))


@pytest.mark.parametrize(
    "auth,header,prefix",
    [
        ("bearer", "Authorization", "Bearer "),
        ("api-key", "api-key", ""),
    ],
)
@pytest.mark.parametrize("schema_mode", ["json_schema", "json_object"])
def test_company_gateway_wire_contract(monkeypatch, auth, header, prefix, schema_mode):
    captured = {}
    monkeypatch.setenv("GUARD_ALLOWED_AI_HOSTS", "gateway.example.com")
    monkeypatch.setenv("GUARD_AI_TOKEN", "SECRET")

    class Connection:
        def __init__(self, host, port, timeout):
            captured.update(host=host, timeout=timeout)

        def request(self, method, path, body, headers):
            captured.update(method=method, path=path, payload=json.loads(body), headers=headers)

        def getresponse(self):
            return self

        status = 200

        def read(self, limit):
            return json.dumps(
                {
                    "id": "chatcmpl-test",
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": '{"text":"No supported findings."}'},
                        }
                    ],
                }
            ).encode()

        def close(self):
            captured["closed"] = True

    monkeypatch.setattr("ai_devops_guard.ai.compatible.HTTPSConnection", Connection)
    settings = AISettings(**(gateway(schema_mode=schema_mode).model_dump() | {"auth_mode": auth}))
    provider = CompatibleProvider(settings)
    result = provider.explain(ExplanationContext(finding_count=0, coverage_gap_count=0))
    assert result.status == "complete"
    assert captured["headers"][header] == prefix + "SECRET"
    assert captured["path"] == "/v1/chat/completions"
    assert captured["payload"]["response_format"]["type"] == schema_mode
    assert captured["payload"]["max_completion_tokens"] == 384
    assert captured["closed"]
    assert "SECRET" not in json.dumps(captured["payload"])
    assert provider.request_ids == ["chatcmpl-test"]
    assert "SECRET" not in repr(provider._token)


@pytest.mark.parametrize(
    "status,body",
    [
        (302, b""),
        (401, b"SECRET"),
        (429, b"SECRET"),
        (500, b"SECRET"),
        (200, b"{"),
        (200, b" " * 65_537),
        (200, b'{"choices":[]}'),
        (200, b'{"choices":[{"finish_reason":"length","message":{"content":"{}"}}]}'),
        (200, b'{"choices":[{"finish_reason":"stop","message":{"refusal":"refused"}}]}'),
        (200, b'{"choices":[{"finish_reason":"stop","message":{"tool_calls":[{}]}}]}'),
    ],
)
def test_gateway_failure_is_not_retried_or_redirected(monkeypatch, status, body):
    calls = []

    class Connection:
        def __init__(self, *args, **kwargs):
            self.status = status

        def request(self, *args, **kwargs):
            calls.append(True)

        def getresponse(self):
            return self

        def read(self, limit):
            return body

        def close(self):
            pass

    monkeypatch.setattr("ai_devops_guard.ai.compatible.HTTPConnection", Connection)
    provider = create_provider(load_settings(ROOT / "examples/config/local-gateway.toml"))
    with pytest.raises((ValueError, KeyError)):
        provider.explain(ExplanationContext(finding_count=0, coverage_gap_count=0))
    assert len(calls) == 1
