# Release-candidate verification

Local verification completed November 1, 2026. This records evidence, not a claim
that the repository is already public or that hosted approval has been exercised.

## Actual executions

| Scenario | CLI exit | Findings | AI result | Successful model tool calls |
| --- | --- | --- | --- | --- |
| Terraform safe | 0 | 0 | Real local inference complete | 0 |
| Terraform risky | 1 | 2 | Real local inference complete | 1 |
| Terraform unknown | 2 | 0 | Not run: two coverage gaps | 0 |
| Kubernetes safe | 0 | 0 | Real local inference complete | 0 |
| Kubernetes risky | 1 | 2 | Real local inference complete | 1 |

Model: `qwen2.5:1.5b`, served locally by Ollama. Both native and compatible
transports passed the five scenarios and gate checks; [compatible API evidence](gateway-evidence/proof.json)
records the second transport. No company-hosted provider authentication is claimed. Exact run IDs, input SHA256 values,
timings, reports and audit logs are in [the evidence directory](demo-evidence/proof.json).
Timings describe this one workstation/run set; they are not performance benchmarks.
The model tag is recorded, but model weights are not part of the Python lockfile.

The automated local gate exercise proved: unsigned requests blocked, changed inputs
blocked, signed synthetic bundle accepted, replay blocked, and a model deployment
tool probe denied. The signing identity is explicitly an automated test operator,
not a person. No real infrastructure operations were performed.

## Checks

- 231 passing offline tests, zero failures/errors: [JUnit evidence](demo-evidence/tests.xml).
- Ruff lint and formatting checks passed.
- Both GitHub workflows passed actionlint 1.7.12. The official downloaded validator
  archive was checked against the upstream release's SHA256 checksum before use.
- A source distribution and wheel built successfully using the declared backend.
- The wheel was installed in an isolated temporary environment and its CLI was
  exercised outside the source checkout.
- FFprobe confirmed a 22-second H.264 video at 1280×800. The GIF and key frames were
  rendered from actual evidence and visually inspected for readability/overlap.
- The HTML report is script-free with escaped values and CSP, covered by tests.
  Browser rendering of the local HTML was not independently verified: the browser
  file-URL policy blocked that preview. The media is a separately rendered evidence
  walkthrough, not an HTML screenshot or a fake live UI.

## Requirement audit

| Requirement | Evidence | Status |
| --- | --- | --- |
| Terraform review before deployment | Real risky/safe/unknown CLI runs and rule tests | Locally verified |
| Kubernetes review before deployment | Real risky/safe CLI runs; workload/RBAC shape tests | Locally verified |
| Provider independence | Explicit adapter contract, company config, shared security tests, two live local transports | Locally verified; company endpoint access pending |
| Real AI-assisted analysis | Four successful local inference runs; advisory text in reports | Locally verified |
| Least-privilege tool capabilities | Closed input contracts; active-rule scope; denied shell/deployment tests | Locally verified at application boundary |
| Auditable AI tool calls | Actual caller=model lookup events; IDs, safe arguments and hashes | Locally verified |
| Human-controlled sensitive actions | Interactive signature challenge and public-key verifier | Implemented; automated demonstration verified |
| Protected GitHub approval | Configuration preflight, required environment and digest-bound artifact flow | Local helper/tests/lint verified; hosted execution pending |
| CI integration | Immutable action pins, read-only permissions, offline tests and smoke review | Local commands/lint verified; hosted execution pending |
| Production-oriented package/docs | Build, tests, threat model, security policy, contributing guide, MIT license | Locally verified release candidate |
| Introducing the project visually | 22-second evidence replay, GIF, video and inspected key frames | Ready for user review |
| Public GitHub portfolio | No public repository created during local preparation | Publication approved by user; first hosted run pending |

## What this session taught

Real models can return the wrong tool format or hallucinate from incomplete facts.
Schema composition can also fail at the provider boundary even when unit contracts
look valid. The implementation now uses one structured proposal with independent
permissions, tests schema references, rejects truncated generation, and skips AI
when deterministic coverage is incomplete. The model never owns policy or approval.

## Next step

Review the result, approve the public repository destination, then publish and run
hosted CI. Configure a required reviewer distinct from the workflow initiator before
exercising the protected environment. Record actual hosted run URLs and outcomes
here after they are verified; do not mark them complete from YAML alone.
