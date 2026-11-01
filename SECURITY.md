# Security policy

This is a read-only portfolio release candidate. It is not a comprehensive scanner
or a production deployment authorization service. It never invokes apply, kubectl,
cloud SDKs, shell commands, or deployment APIs from its review or approval code.

Do not submit credentials, production plans, state, kubeconfig, or secrets in issues.
Private vulnerability reporting is enabled. Use the repository's
[Security tab](https://github.com/yonatani94/ai-devops-security-guard/security)
to report a vulnerability privately.

Review [the threat model](docs/threat-model.md) before integrating the tool. Report
logic bugs using minimal synthetic reproductions. Report suspected security bypasses
through the private channel rather than a public issue.

The Python review process and its installed dependencies must be trusted. Model
proposals are untrusted, and only one read-only rule-lookup capability is granted.
Keep signing keys off CI workers, model services and untrusted checkouts. Provision
the trusted public key independently; a public key embedded in an untrusted approval
is not an identity anchor.

Local file modes and JSON logs do not protect against a malicious process running
as the same OS user, administrators, or compromised dependencies. Ed25519 signatures
provide artifact authenticity relative to the configured key, not proof that a named
person understood a report. The reviewer name is descriptive metadata.
