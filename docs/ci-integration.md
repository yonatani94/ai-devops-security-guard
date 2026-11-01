# Reusable infrastructure review

The secret-free reusable workflow reviews one Terraform JSON plan or Kubernetes
YAML file from a caller repository. It installs GUARD separately from caller files,
uses the offline explanation provider, and fails when findings or analysis errors
require attention. It does not generate plans, run Terraform providers, execute the
caller's project, connect to a cluster, or authorize deployment.

## Caller example

Commit a synthetic input first. Replace the input path for your own repository.
The revision below pins both the workflow and its trusted implementation.

```yaml
name: Infrastructure security
on: [pull_request, workflow_dispatch]
permissions:
  contents: read
jobs:
  review:
    uses: yonatani94/ai-devops-security-guard/.github/workflows/reusable-review.yml@d8c7c66213d901266def575ea23a9b96b672c9fe
    with:
      kind: terraform
      input-path: infrastructure/plan.json
```

Use `kind: kubernetes` for a supported manifest. Input paths must remain within
the checkout. Absolute paths, `..` components and symlink components are rejected.
Treat input and code as untrusted. The workflow does not execute caller code or
install caller dependencies. Python runs in isolated mode against trusted GUARD.
Do not add `secrets: inherit` or run this integration via `pull_request_target`.
The workflow needs no cloud or model credentials. The `GITHUB_TOKEN` has
`contents: read` for checkouts, and checkout credentials are not persisted.

The caller checkout uses GitHub's event checkout semantics. A pull request review
therefore covers the merge checkout, while a dispatch covers the selected ref.
The input SHA256 and correlation ID identify the actual bytes reviewed. The
workflow's own GUARD checkout is pinned independently of the caller checkout.

## Results and reports

| Outcome | Reusable job | Meaning |
| --- | --- | --- |
| `pass` | Success | Supported checks found no findings |
| `review_required` | Failure | Human review is needed |
| `error` or execution failure | Failure | No usable complete passing review |

The job summary contains only the decision and counts. Successful calls expose
`decision`, `input-digest` and `run-id` outputs. Do not depend on outputs propagating
from failed reusable calls. A downstream deployment job must depend on this job
and retain its own protected environment and independent approval policy.
A pass never means comprehensive safety or authorization to deploy.

Reports remain on the ephemeral runner by default. Set `upload-reports: true` only
when your repository access policy permits storing infrastructure identifiers in
Actions artifacts. Set a unique `artifact-name` for parallel calls. Retention is
one day. Raw source files are not uploaded by this workflow. Artifact upload uses
GitHub's artifact service but grants no repository write permission.

## Verified hosted behavior

All runs below use synthetic fixtures, offline explanations and zero infrastructure
operations. Failing runs are deliberate demonstrations of the gate.

| Scenario | Actual decision | Hosted outcome |
| --- | --- | --- |
| Safe Terraform and Kubernetes | `pass` | [Both jobs succeeded](https://github.com/yonatani94/ai-devops-security-guard/actions/runs/41354650630) |
| Public SSH and wildcard IAM | `review_required`, 2 findings | [Gate blocked](https://github.com/yonatani94/ai-devops-security-guard/actions/runs/41354696977) |
| Unknown Terraform values | `error`, 2 coverage gaps | [Gate blocked](https://github.com/yonatani94/ai-devops-security-guard/actions/runs/41354699554) |
| Kubernetes host namespaces | `review_required`, 3 findings | [Gate blocked](https://github.com/yonatani94/ai-devops-security-guard/actions/runs/41354702137) |

[Machine-readable evidence](ci-integration/evidence.json) preserves source commits,
step outcomes, hashes and correlation IDs. The calls were hosted within this
repository. Use the pinned external caller example for your own repository's pilot.

## Live AI integration remains separate

Use the existing local CLI or trusted company-gateway configuration for actual
inference. The reusable workflow intentionally exposes no credential or endpoint
input yet. Add authenticated inference only in a trusted integration after the
company approves its endpoint, model, credential handling and access policy.

References: [GitHub reusable workflows](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows)
and [workflow events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request).
