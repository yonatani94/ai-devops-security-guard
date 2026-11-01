"""Validated contracts. Input plans remain untrusted and may contain secrets."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


class Contract(BaseModel):
    """Reject accidental fields in application-owned records."""

    model_config = ConfigDict(extra="forbid", strict=True)


class TerraformChange(BaseModel):
    """Supported resource-change fields; retain Terraform's nested value markers."""

    model_config = ConfigDict(extra="ignore", strict=True)
    actions: list[Literal["no-op", "create", "read", "update", "delete", "forget"]]
    before: dict[str, JsonValue] | None = None
    after: dict[str, JsonValue] | None = None
    after_unknown: dict[str, JsonValue] = Field(default_factory=dict)
    before_sensitive: dict[str, JsonValue] | bool = Field(default_factory=dict)
    after_sensitive: dict[str, JsonValue] | bool = Field(default_factory=dict)

    @field_validator("actions")
    @classmethod
    def supported_actions(cls, value: list[str]) -> list[str]:
        supported = {
            ("no-op",),
            ("create",),
            ("read",),
            ("update",),
            ("delete",),
            ("delete", "create"),
            ("create", "delete"),
            ("forget",),
            ("create", "forget"),
        }
        if tuple(value) not in supported:
            raise ValueError("unsupported Terraform action sequence")
        return value


class TerraformResourceChange(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    address: str = Field(min_length=1)
    mode: Literal["managed", "data"]
    type: str = Field(min_length=1)
    name: str = Field(min_length=1)
    change: TerraformChange


class TerraformPlan(BaseModel):
    """A reviewable subset, not a complete Terraform JSON schema."""

    model_config = ConfigDict(extra="ignore", strict=True)
    format_version: str
    terraform_version: str = Field(min_length=1)
    # Required: missing change data must not be mistaken for an empty plan.
    resource_changes: list[TerraformResourceChange]

    @field_validator("format_version")
    @classmethod
    def supported_format(cls, value: str) -> str:
        if re.fullmatch(r"1\.[0-9]+", value) is None:
            raise ValueError("unsupported Terraform JSON format: expected major version 1")
        return value


class Finding(Contract):
    rule_id: str = Field(min_length=1)
    resource_address: str = Field(min_length=1)
    severity: Literal["low", "medium", "high", "critical"]
    summary: str = Field(min_length=1)
    evidence_path: str = Field(min_length=1, description="JSON Pointer; excludes raw values")
    remediation: str = Field(min_length=1)


class Assessment(Contract):
    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    findings: list[Finding]
    decision: Literal["pass", "review_required", "error"]
    analysis_complete: bool
    coverage_gaps: list[str] = Field(default_factory=list)
    ai_status: Literal["not_run", "simulated", "complete", "failed"] = "not_run"
    ai_explanation: str | None = None
    ai_model: str | None = None
    ai_provider: str | None = None
    ai_request_ids: list[str] = Field(default_factory=list)
    input_kind: Literal["terraform", "kubernetes"] = "terraform"
    source_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def prevent_incomplete_pass(self) -> "Assessment":
        if self.decision == "pass" and (
            not self.analysis_complete
            or self.coverage_gaps
            or self.findings
            or self.ai_status == "failed"
        ):
            raise ValueError("findings, incomplete analysis, or failed AI cannot produce a pass")
        return self


class AuditEvent(Contract):
    """One call event. Callers must sanitize data before constructing this record."""

    schema_version: Literal["1.0"] = "1.0"
    run_id: UUID
    call_id: UUID
    timestamp: datetime
    caller: Literal["pipeline", "model"]
    tool: str = Field(min_length=1)
    permission: Literal["allowed", "denied"]
    status: Literal["started", "succeeded", "failed", "denied"]
    sanitized_arguments: dict[str, JsonValue] = Field(default_factory=dict)
    duration_ms: float | None = Field(default=None, ge=0)
    input_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    output_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    error_code: str | None = None

    @field_validator("timestamp")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() is None or value.utcoffset().total_seconds() != 0:
            raise ValueError("audit timestamp must be timezone-aware UTC")
        return value

    @model_validator(mode="after")
    def consistent_permission(self) -> "AuditEvent":
        if (self.permission == "denied") != (self.status == "denied"):
            raise ValueError("denied permission must have denied status and vice versa")
        return self
