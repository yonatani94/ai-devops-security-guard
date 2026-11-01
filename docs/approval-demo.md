# Human approval demonstration

The AI cannot approve a change. Two demos exercise the boundary without deploying
resources: a local signed approval and a GitHub protected environment.

## Local signing flow

First run a review and inspect its JSON/HTML report. Substitute the printed run
directory below. Keep reviewer keys out of the repository and away from the model.

```bash
uv run ai-devops-guard keygen --output-dir artifacts/reviewer-keys

uv run ai-devops-guard approve \
  --run-dir artifacts/demo/<run-id> \
  --input examples/terraform/risky.plan.json \
  --private-key artifacts/reviewer-keys/reviewer.key \
  --reviewer "Your name" \
  --reason "Reviewed the synthetic fixture for the portfolio demo"
```

The signing command displays the bundle digest and asks you to type
`APPROVE <first-12-digest-characters>`. It creates a 30-minute approval. A generic
`yes`, empty input, or the wrong digest is rejected. Identity is possession of the
trusted private key; the reviewer name is metadata, not authentication.

The execution side holds only the provisioned public key:

```bash
uv run ai-devops-guard simulate-deploy \
  --run-dir artifacts/demo/<run-id> \
  --input examples/terraform/risky.plan.json \
  --public-key artifacts/reviewer-keys/reviewer.pub
```

This verifies the signature, timestamps, exact input/report/audit binding, and
deterministic reanalysis, then creates a one-use simulation receipt. A changed file,
forged signature, different key, missing approval, incomplete review, or reused
receipt is denied. Gate attempts have separate audit logs in the run directory.

The automated verification script signs as **Automated demo operator (not human
approval)**. Its receipts prove code paths, not that a real person approved a change.
The temporary private key is destroyed after the verification run. Historical demo
approvals expire; generate a fresh run for interactive signing.

## GitHub protected environment

Two explicit modes are available on the manual **Protected approval demo** workflow:

| Mode | Environment | Self-review | Purpose |
| --- | --- | --- | --- |
| `independent` (default) | `security-review` | Prevented | Separate workflow initiator and reviewer |
| `solo-demo` | `security-review-solo-demo` | Permitted | Single-person, synthetic-only demonstration |

Both environments are configured with `yonatani94` as a required reviewer and
restricted to the `main` branch. With the default independent mode, that account
cannot approve a run it initiated. Use `solo-demo` for the owner's own test runs.
The relaxed self-review setting exists only on the separately named demo environment;
it does not change the independent mode's validator or environment policy.

In solo mode, the preflight checks the exact environment name, expected repository
owner reviewer, and explicit self-review setting. Verification additionally requires
an exact bundled risky fixture from `examples/` and fake inference. Arbitrary reviewed
input is rejected in this mode. No cloud credential or infrastructure operation is
part of either demonstration.

Start a test from the Actions tab with `kind=terraform` (or `kubernetes`) and
`mode=solo-demo`. The review job validates the environment, prepares the synthetic
bundle, publishes the risk report and digest in its summary, and uploads the artifact.
The simulation job then waits for the required reviewer.

As `yonatani94`, inspect the report, click **Review deployments**, select
`security-review-solo-demo`, then click **Approve and deploy**. The agent does not
perform this human approval on your behalf. After approval, the job verifies the
exact bundle digest, writes a zero-operation receipt labeled with the selected mode,
and publishes `guard-simulation-receipt` as a short-lived artifact.

For a production integration, use independent review and a different authorized
reviewer, protect `main`, and disallow administrator bypass if your plan supports it.
Neither demo implements a production deployment system.

An environment name alone does not enforce approval; the preflight is essential.
The repository owner controls environment settings and remains trusted. Required
reviewers and protection features depend on repository visibility and GitHub plan.
See [GitHub environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
and [the environment API](https://docs.github.com/en/rest/deployments/environments#get-an-environment).

The helper and artifact binding are locally tested. The first
[hosted negative-path run](https://github.com/yonatani94/ai-devops-security-guard/actions/runs/41346836821)
stopped at environment inspection with HTTP 404; the simulation job was skipped.
The environments are now configured; a genuine human approval still needs the
reviewer to approve a waiting run in GitHub.

### Troubleshooting HTTP 404

`gh api .../environments/security-review` returns 404 when the environment is
absent or inaccessible to the caller. The repository was inspected with owner
credentials after the initial failure and had zero environments, confirming the
missing setup in this case. Do not fix this by removing the preflight or granting
the workflow administration permissions.

Create `security-review` under repository Settings → Environments, choose a required
reviewer distinct from the workflow initiator, and enable Prevent self-review.
The workflow requires only `actions: read` for this lookup. If a configured
environment still returns an error, verify the repository and token access.
The workflow now emits an actionable error annotation and setup instructions in
the run summary while continuing to block execution.
