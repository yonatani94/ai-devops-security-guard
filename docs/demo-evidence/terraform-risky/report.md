# Infrastructure risk assessment

Run: b27e7ce3-85e5-441d-a763-3a0b329574be

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

The review is complete as there are no coverage gaps\. Both rules have been reviewed and found to be compliant\. No findings were found for the rules TF\-AWS\-001 and TF\-AWS\-002\. The coverage is 100% complete\. The findings indicate that the public IPv4/IPv6 ingress permits TCP port 22, which should be restricted to SSH sources\. Additionally, an IAM Allow statement uses wildcard actions and resources, which should be scoped to reduce privileges\.
