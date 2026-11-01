# Infrastructure data boundaries

GUARD reviews infrastructure configuration without needing application source,
business records or runtime traffic. This is a narrow data contract, not a general
secret scanner or a guarantee that infrastructure files contain no secrets.

| Surface | Data allowed | Handling |
| --- | --- | --- |
| Local input reader | One bounded plan or manifest | Read only, no cloud access |
| Model context | Finding count, coverage-gap count, supported rule IDs | Closed typed contract |
| Rule lookup result | Application-owned static rule guidance | Scoped to active findings |
| HTTP request | Context, schemas, fixed prompts, configured model | Local Ollama or approved compatible endpoint |
| JSONL tool audit | Counts, rule IDs, hashes, correlation IDs, status and duration | No raw input, prompts or exceptions |
| Review reports | Findings with resource identifiers, evidence paths, AI explanation | Private infrastructure artifacts |
| Reusable CI summary | Decision and counts | No raw configuration or model explanation |

The provider/model configuration and transport metadata also identify the selected
endpoint and model. Authenticated gateways send the configured credential in a
request header to the exact trusted host. These credentials are transport secrets,
not infrastructure input or model context. The secret-free reusable workflow makes
no model request and inherits no secrets.

## Regression evidence

`tests/test_data_boundary.py` places synthetic canaries in infrastructure resource
names, password fields, Terraform outputs, Kubernetes environment variables,
annotations, image strings and application-like values. It runs the real pipeline
through both adapters and captures their serialized HTTP requests.

The tests require all canaries to remain absent from requests and tool audits,
check the exact context field set, and confirm that reports intentionally retain
resource identifiers. Sensitive Terraform rule values mark analysis incomplete
and prevent inference. Existing tests cover malformed tool proposals, denied
capabilities and sanitized provider errors.

These tests cover the supported parsers and transports. They are regression tests,
not a proof about every possible input, dependency or future adapter. Treat
identifiers in local reports as private, restrict artifact access, and use short
retention. Do not commit real plans, credentials, Terraform state or Kubernetes
Secrets to the public project.
