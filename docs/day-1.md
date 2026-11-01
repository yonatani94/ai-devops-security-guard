# Day 1 — offline review foundation

Completed November 1, 2026.

Historical notes for the initial offline increment. The project subsequently grew
into the release candidate documented in the root README and verification notes.

## What we built

```text
Synthetic Terraform plan
  -> restricted, audited review_plan tool
  -> deterministic findings + explicit coverage gaps
  -> application-owned policy decision
  -> restricted, audited explain_assessment tool (counts only)
  -> validated simulated explanation
  -> private JSON and Markdown reports
```

The tool dispatcher has no shell, cloud API, Terraform apply, or Kubernetes access.
The two rules detect public SSH ingress and exact wildcard IAM Action/Resource
combinations in supported AWS Terraform resource shapes. The fake provider makes
the entire demo repeatable and credential-free; it is not real AI inference.

Exit codes distinguish a scoped pass (`0`), required review (`1`), and incomplete
analysis/execution error (`2`). Every run has its own directory and audit correlation
ID. A successful tool execution is distinct from a safe policy result.

## What we learned

1. Validate external formats separately from application-owned contracts. Terraform
   can add metadata without changing the fields these narrow rules consume.
2. Keep unknown values and unsupported shapes visible. No finding is not proof of
   safety, and incomplete coverage must not produce a pass.
3. The application grants capabilities. Model text cannot choose file paths, gain
   shell access, or approve infrastructure changes.
4. Separate rule evidence, explanations, and policy. Even an explanation that says
   “approve everything” cannot change the findings or decision.
5. Audit before execution and before returning results. If logging fails, the call
   stops. Fixed error codes avoid leaking secrets through exception messages.
6. Minimize provider input and logs. The fake provider needs only counts; report
   identifiers still deserve private storage and review before sharing.
7. Use nonzero exit codes deliberately in CI. A risky fixture is expected to return
   `1`; an unknown fixture returns `2` even if no finding could be established.

## Verification

- Contract, rule, tool-permission, disk-failure, provider-failure, and CLI tests.
- Safe/risky/unknown fixture reviews and validated report/audit serialization.
- Markdown escaping for untrusted strings; private output file permissions.
- Lint and formatting checks; workflow YAML parsing and local workflow commands.

The GitHub workflow has not run remotely. The repository is local and unpublished.
Local audit logs are not immutable, and the Python dispatcher is not OS isolation.

## Next session: real inference adapter (60–90 minutes)

Check available hardware and choose a locally runnable model with an acceptable
license. Add an allowlisted model context, local-provider configuration, validated
structured response, timeouts, and sanitized failure handling. Keep policy outside
the model and retain fake inference for tests. If model setup takes longer, split
installation from adapter implementation into separate sessions.

Subsequent milestones: bounded model-requested read-only tools, protected human
approval tied to reviewed artifacts, Kubernetes inputs, and a portfolio release
with a chosen open-source license and threat model.
