# Infrastructure risk assessment

Run: 2d853103-97c0-4cda-953d-ffaf10a04a66

Decision: **review_required**

Analysis complete: True

AI status: **complete**

Input: terraform. This report does not authorize deployment.

## Findings

- **TF\-AWS\-001 / high**: Ingress permits public access to TCP port 22\.
  Resource: aws\_security\_group\.ssh; evidence: /resource\_changes/0/change/after/ingress/0/cidr\_blocks/0.
  Remediation: Restrict SSH to approved networks or remove SSH ingress\.

- **TF\-AWS\-002 / high**: IAM statement allows wildcard actions on wildcard resources; conditions and external policy controls require human review\.
  Resource: aws\_iam\_policy\.reader; evidence: /resource\_changes/1/change/after/policy.
  Remediation: Scope actions and resources to required workload permissions\.

## Coverage gaps

None within the supported scope.

## Explanation

The AWS infrastructure allows public IPv4/IPv6 ingress on port 22, which is not secure\. Review the SSH source restrictions to enhance security\. Additionally, the IAM Allow statement for wildcard actions and resources is not appropriate\. Review the policy to ensure proper resource and action scope\.
