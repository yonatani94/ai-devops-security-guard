# Release-candidate verification

Local and hosted verification recorded November 1, 2026. The repository is public
and ordinary hosted CI passed. Human-approved protected execution remains pending.

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

- 234 passing offline tests, zero failures/errors: [JUnit evidence](demo-evidence/tests.xml).
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
| Protected GitHub approval | Configuration preflight, required environment and digest-bound artifact flow | Hosted missing-environment preflight blocked; human-approved run pending |
| CI integration | Immutable action pins, read-only permissions, offline tests and smoke review | Hosted CI passed; see exact run/commit below |
| Production-oriented package/docs | Build, tests, threat model, security policy, contributing guide, MIT license | Locally verified release candidate |
| Introducing the project visually | 22-second evidence replay, GIF, video and inspected key frames | Ready for user review |
| Public GitHub portfolio | Public MIT repository: yonatani94/ai-devops-security-guard | Published and verified |

## What this session taught

Real models can return the wrong tool format or hallucinate from incomplete facts.
Schema composition can also fail at the provider boundary even when unit contracts
look valid. The implementation now uses one structured proposal with independent
permissions, tests schema references, rejects truncated generation, and skips AI
when deterministic coverage is incomplete. The model never owns policy or approval.

## Hosted evidence

- [CI run 41346712622](https://github.com/yonatani94/ai-devops-security-guard/actions/runs/41346712622)
  passed on commit `d95b3526e5a1965171f53d6a594ceaceafaa1417`. All installation,
  lint, formatting, test and CLI smoke steps executed successfully; 231 tests passed.
- [Approval negative-path run 41346836821](https://github.com/yonatani94/ai-devops-security-guard/actions/runs/41346836821)
  stopped at environment inspection with HTTP 404 because `security-review` was
  absent. Artifact preparation/upload and the protected simulation were skipped.
  This proves the unconfigured gate stops execution, not that a human approved.
- Private vulnerability reporting was enabled and its API state verified.

The CI badge shows subsequent `main` runs. Embedded demo evidence is a dated
snapshot; its explicit run/commit bindings distinguish it from newer revisions.

## Next step

Provide a required-reviewer GitHub username distinct from the workflow initiator,
configure the protected environment, and exercise the genuine approval transition.
Separately, validate the company gateway template against an approved endpoint and
model using CI-injected credentials; no cloud-hosted provider access is claimed.
