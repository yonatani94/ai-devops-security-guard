"""Application-owned knowledge, independent of any inference provider."""

RULE_CATALOG = {
    "TF-AWS-001": "Public IPv4/IPv6 ingress permits TCP port 22. Restrict SSH sources.",
    "TF-AWS-002": "An IAM Allow statement uses wildcard actions and resources. Scope privileges.",
    "K8S-001": "A workload explicitly enables a privileged container. Remove privileged mode.",
    "K8S-002": "RBAC wildcard permissions. Scope API groups, resources and verbs.",
    "K8S-003": "A workload shares a host network, PID or IPC namespace. Disable host sharing "
    "unless separately justified and approved.",
}
