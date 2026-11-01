"""Application-owned capability boundary. No shell or cloud access."""

import os
import stat
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic
from uuid import UUID, uuid4

from pydantic import ValidationError

from ai_devops_guard.ai.base import (
    Explanation,
    ExplanationContext,
    ExplanationProvider,
    RuleKnowledge,
    RuleLookupArguments,
)
from ai_devops_guard.ai.catalog import RULE_CATALOG
from ai_devops_guard.ai.fake import FakeProvider
from ai_devops_guard.audit import AuditWriter
from ai_devops_guard.models import AuditEvent, Contract, TerraformPlan
from ai_devops_guard.rules.kubernetes import parse_manifests, review_manifests
from ai_devops_guard.rules.terraform import RuleResult, review_plan


class ToolDenied(PermissionError):
    pass


class ToolExecutionError(RuntimeError):
    pass


class ReviewArguments(Contract):
    """No caller-controlled file paths or execution options."""


class ToolDispatcher:
    """Review only the plan bound by trusted application setup.

    Caller identity is supplied by the application, never by a model payload.
    This boundary does not sandbox malicious Python running in the same process.
    """

    MAX_PLAN_BYTES = 1_048_576

    def __init__(
        self,
        plan_path: Path,
        audit: AuditWriter,
        run_id: UUID,
        provider: ExplanationProvider | None = None,
        input_kind: str = "terraform",
    ):
        self._plan_path = plan_path.absolute()
        self._audit = audit
        self._run_id = run_id
        self._provider = provider if provider is not None else FakeProvider()
        if input_kind not in {"terraform", "kubernetes"}:
            raise ValueError("unsupported input kind")
        self.input_kind = input_kind
        self.source_digest = None
        self._active_rules = frozenset()
        self._provider.bind_tool_executor(
            lambda tool, arguments: self.call(tool, arguments, caller="model"),
        )

    def call(
        self, tool: str, arguments: dict, *, caller: str = "pipeline"
    ) -> RuleResult | Explanation | RuleKnowledge:
        call_id = uuid4()
        known_tool = isinstance(tool, str) and tool in {
            "review_plan",
            "review_kubernetes",
            "explain_assessment",
            "lookup_rules",
        }
        # Do not copy untrusted tool names, paths, arguments, errors, or plan values to logs.
        metadata = dict(
            run_id=self._run_id,
            call_id=call_id,
            caller="model" if caller == "model" else "pipeline",
            tool=tool if known_tool else "unregistered_tool",
        )

        def record(status, permission="allowed", **extra):
            self._audit.write(
                AuditEvent(
                    **metadata,
                    timestamp=datetime.now(UTC),
                    status=status,
                    permission=permission,
                    **extra,
                )
            )

        try:
            required_caller = "model" if tool == "lookup_rules" else "pipeline"
            if not known_tool or caller != required_caller:
                raise ToolDenied
            if tool == "review_plan" and self.input_kind != "terraform":
                raise ToolDenied
            if tool == "review_kubernetes" and self.input_kind != "kubernetes":
                raise ToolDenied
            schema = (
                RuleLookupArguments
                if tool == "lookup_rules"
                else ExplanationContext
                if tool == "explain_assessment"
                else ReviewArguments
            )
            args = schema.model_validate(arguments)
            if tool == "lookup_rules" and not set(args.rule_ids) <= self._active_rules:
                raise ToolDenied
        except (ToolDenied, ValidationError):
            record("denied", "denied", error_code="permission_or_arguments_denied")
            raise ToolDenied("tool or arguments not permitted") from None

        # Only validated counts and closed-vocabulary rule IDs are ever logged.
        metadata["sanitized_arguments"] = args.model_dump()
        record("started")  # A failed write prevents execution.
        started = monotonic()
        try:
            if tool == "review_plan":
                result = review_plan(self._read_plan())
            elif tool == "review_kubernetes":
                result = review_manifests(parse_manifests(self._read_bytes()))
            elif tool == "lookup_rules":
                result = RuleKnowledge(rules={rule: RULE_CATALOG[rule] for rule in args.rule_ids})
            else:
                self._active_rules = frozenset(args.rule_ids)
                try:
                    response = self._provider.explain(args)
                finally:
                    self._active_rules = frozenset()
                # Validate provider output even if an adapter bypasses its return annotation.
                result = Explanation.model_validate(response)
                if result.status != getattr(self._provider, "status", "simulated"):
                    raise ValueError("provider status mismatch")
        except Exception:
            record(
                "failed",
                duration_ms=(monotonic() - started) * 1000,
                error_code="explanation_failed"
                if tool == "explain_assessment"
                else "review_failed",
            )
            message = "plan review failed" if tool == "review_plan" else "explanation failed"
            raise ToolExecutionError(f"{message}; see audit status") from None
        record(
            "succeeded",
            duration_ms=(monotonic() - started) * 1000,
            input_digest=self.source_digest,
            output_digest=sha256(result.model_dump_json().encode()).hexdigest(),
        )
        return result  # A failed completion write prevents delivery of a result.

    def _read_plan(self) -> TerraformPlan:
        return TerraformPlan.model_validate_json(self._read_bytes())

    def _read_bytes(self) -> bytes:
        fd = os.open(self._plan_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("plan must be a regular file")
            data = stream.read(self.MAX_PLAN_BYTES + 1)
        if len(data) > self.MAX_PLAN_BYTES:
            raise ValueError("plan exceeds size limit")
        self.source_digest = sha256(data).hexdigest()
        return data
