# Bring your own AI provider

GUARD owns the review contract, tool permissions, audit, policy, and approval.
An adapter owns inference transport, endpoint authentication, and response
normalization. Changing provider must not alter the security decision model.

## Implemented adapters

| Adapter | Configuration | Verification |
| --- | --- | --- |
| `fake` | Default; deterministic offline explanation | Unit/CLI/CI tests |
| `ollama` | Native loopback `/api/chat` | Real local synthetic evaluations |
| `openai-compatible` | Configurable Chat Completions gateway | Wire-contract tests and real local compatible-API evaluation |

The compatible adapter is a wire-protocol integration, not universal provider
support. It can target a company gateway implementing the documented protocol.
Azure/OpenAI hosted endpoints have not been exercised with company credentials.
Native Bedrock SigV4, Anthropic Messages, provider SDK credential acquisition, mTLS,
legacy Azure query-versioned endpoints, streaming, and automatic failover are not
implemented. They require separate adapters or an existing company gateway.

## Select an adapter

```bash
# Native local inference.
uv run ai-devops-guard review --plan examples/terraform/risky.plan.json \
  --ai-config examples/config/ollama.toml --output-dir artifacts/native

# Same worker through the compatible API. No credential is read for loopback mode.
uv run ai-devops-guard review --plan examples/terraform/risky.plan.json \
  --ai-config examples/config/local-gateway.toml --output-dir artifacts/gateway
```

Both risky reviews should return `1`, indicating human review is required. Neither
deploys resources. They use the same rule catalog, two-request bound, one scoped
model lookup, local output validation, report format, and separate approval flow.

## Company configuration

Copy `examples/config/company-gateway.toml` and replace the placeholder endpoint
and approved model/deployment identifier. Configuration contains no literal token:

```toml
[ai]
provider = "openai-compatible"
endpoint = "https://ai-gateway.example.com/v1"
model = "your-approved-model-or-deployment"
auth_mode = "bearer"
schema_mode = "json_schema"
token_parameter = "max_completion_tokens"
max_output_tokens = 384
timeout_seconds = 60
```

Provision these from trusted CI configuration or your existing secret manager:

- `GUARD_ALLOWED_AI_HOSTS`: comma-separated exact approved hostnames; no wildcards.
- `GUARD_AI_TOKEN`: the only environment variable from which this adapter reads a
  credential. It can contain an API key or a pre-acquired short-lived bearer token.

`auth_mode = "bearer"` sends `Authorization: Bearer ...`; `"api-key"` sends the
`api-key` header. Authentication is mandatory for HTTPS gateways. Cleartext HTTP
is permitted only to literal loopback addresses with `auth_mode = "none"`; no token
is read or sent in that mode. Remote cleartext, userinfo, query strings, fragments,
control characters and endpoint hosts outside the allowlist are rejected before
connection. TLS verification uses Python's default trusted certificate store;
there is no insecure skip-verification flag, proxy discovery, or redirect following.

The allowlist is separate from repository configuration so a PR cannot nominate a
new destination for the token merely by editing TOML. The surrounding CI workflow
and its installed dependencies still need to be trusted. Use an isolated review
job with only the provider credential; do not inject cloud deployment credentials.
Do not run PR-controlled Python, scripts, or dependency installation with secrets.
Install a trusted release of GUARD in a protected workflow and treat the plan or
manifest artifact as data. This adapter is not an OS/network egress firewall.

For Azure's v1 interface, the base URL has the form
`https://RESOURCE.openai.azure.com/openai/v1` and `model` is the deployment name.
Acquire credentials through your approved identity system outside GUARD and inject
the token. GUARD does not auto-discover Azure credentials, renew tokens or create
cloud identities. See [Microsoft's endpoint and authentication documentation](https://learn.microsoft.com/en-us/azure/foundry-classic/openai/how-to/switching-endpoints?view=foundry-classic).

## Capability differences are explicit

`schema_mode = "json_schema"` sends a strict schema request. A gateway/model that
does not support it fails; GUARD never silently downgrades or changes providers.
If the approved gateway offers JSON mode only, explicitly choose `"json_object"`.
The same Pydantic contracts and independent dispatcher checks apply afterward.
Valid JSON alone is not a safety or correctness guarantee.

`token_parameter` explicitly selects `max_completion_tokens` or the older gateway
parameter `max_tokens`. There are no arbitrary request headers/body overrides.
Response refusal, truncation, non-200 status, invalid JSON, oversized data, timeout,
or a disallowed tool proposal fails closed. There are no automatic retries.
Timeouts apply to socket operations, not a hard overall wall-clock deadline.

CLI provider/model/timeout options override the corresponding TOML values. The
combined configuration is revalidated: changing an adapter while leaving incompatible
endpoint/auth fields fails instead of silently ignoring them. Reports record the
logical adapter, configured model/deployment, and bounded provider request IDs when
returned; credentials and raw error bodies are never included.

Protocol references: [official OpenAI structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[Chat Completions request contract](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create),
and [Ollama's compatible API](https://docs.ollama.com/api/openai-compatibility).

## Add another provider

Implement `ExplanationProvider` in `ai/base.py`, declare capabilities and stable
provider identity, bind the supplied tool executor, and register the constructor
in `ai/config.py`. For a structured-JSON backend, subclass `StructuredAgent` and
implement `_generate(messages, schema)` so the bounded worker is reused. Never
move permissions, file access or approval into an adapter. Config cannot import
arbitrary Python modules.

Run the shared provider contract suite plus wire-format/authentication tests for
the new adapter, then perform an opt-in synthetic integration run. Mocks establish
contract behavior; they do not prove access to a real company endpoint. No adapter
may fall back to fake inference on error or gain extra tools when switched.
