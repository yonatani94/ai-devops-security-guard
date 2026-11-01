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

After publishing, create an environment named `security-review`. Add a different
trusted person as a required reviewer, enable **Prevent self-review**, restrict
deployment branches to `main`, and disallow administrator bypass if your plan
supports it. Protect `main` and require CI/code review for workflow changes.

Run **Protected approval demo** manually from `main`. The review job checks the
actual environment configuration through the GitHub API and refuses to continue
unless required reviewers are configured and self-review is prevented. It reviews
only a chosen synthetic fixture with fake inference, then uploads the exact input
and review files. The `simulate` job waits on the protected environment. After a
human approves in GitHub, it downloads this run's artifact, verifies the expected
bundle digest, and writes a simulation receipt. It has no cloud credentials.

An environment name alone does not enforce approval; the preflight is essential.
The repository owner controls environment settings and remains trusted. Required
reviewers and protection features depend on repository visibility and GitHub plan.
See [GitHub environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments)
and [the environment API](https://docs.github.com/en/rest/deployments/environments#get-an-environment).

The helper and artifact binding are locally tested. The first
[hosted negative-path run](https://github.com/yonatani94/ai-devops-security-guard/actions/runs/41346836821)
stopped at environment inspection with HTTP 404; the simulation job was skipped.
A genuine human-approved hosted run is still pending reviewer/environment setup.
