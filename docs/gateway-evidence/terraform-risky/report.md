# Infrastructure risk assessment

Run: 735a75fa-8555-4e53-8868-cf106f968b1a

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

The AWS security findings reveal that public IPv4 and IPv6 ingress are permitted to the EC2 instance SSH port 22, potentially exposing the environment to uncontrolled access\. Additionally, an IAM Allow statement has wildcard actions and resources, which grants elevated privileges\. These findings indicate a gap in the security review and require immediate attention for proper handling and control\.
