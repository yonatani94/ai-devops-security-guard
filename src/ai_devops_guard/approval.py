"""Signed, artifact-bound local approval demonstration. Never deploys resources."""

import json
import stat
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from pydantic import Field, ValidationError

from ai_devops_guard.audit import AuditWriter
from ai_devops_guard.models import Assessment, AuditEvent, Contract, TerraformPlan
from ai_devops_guard.policy import evaluate
from ai_devops_guard.rules.kubernetes import parse_manifests, review_manifests
from ai_devops_guard.rules.terraform import review_plan
from ai_devops_guard.storage import read_regular, write_private


class GateDenied(RuntimeError):
    pass


class ApprovalClaims(Contract):
    schema_version: str = "1.0"
    run_id: UUID
    bundle_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer: str = Field(min_length=1, max_length=120)
    reason: str = Field(min_length=1, max_length=500)
    key_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    issued_at: datetime
    expires_at: datetime


class SignedApproval(Contract):
    claims: ApprovalClaims
    signature: str = Field(pattern=r"^[a-f0-9]{128}$")


def _canonical(claims: ApprovalClaims) -> bytes:
    return json.dumps(
        claims.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()


def generate_keys(directory: Path) -> str:
    """Local demo keys; keep the private file off the verifier/agent machine."""
    directory.mkdir(parents=True, mode=0o700, exist_ok=False)
    key = Ed25519PrivateKey.generate()
    write_private(directory / "reviewer.key", key.private_bytes_raw())
    public = key.public_key().public_bytes_raw()
    write_private(directory / "reviewer.pub", public)
    return sha256(public).hexdigest()


def review_bundle(directory: Path, source: Path) -> tuple[Assessment, str]:
    report_bytes = read_regular(directory / "report.json")
    report = Assessment.model_validate_json(report_bytes)
    if (
        not report.analysis_complete
        or report.coverage_gaps
        or report.decision == "error"
        or report.ai_status not in {"simulated", "complete"}
    ):
        raise GateDenied("incomplete or failed reviews cannot be approved")
    source_bytes = read_regular(source)
    digest = sha256(source_bytes).hexdigest()
    if report.source_digest != digest:
        raise GateDenied("input changed after review")
    result = (
        review_plan(TerraformPlan.model_validate_json(source_bytes))
        if report.input_kind == "terraform"
        else review_manifests(parse_manifests(source_bytes))
    )
    expected = evaluate(result, report.run_id)
    if (
        expected.decision != report.decision
        or expected.findings != report.findings
        or expected.coverage_gaps != report.coverage_gaps
    ):
        raise GateDenied("report does not match deterministic reanalysis")
    audit_bytes = read_regular(directory / "audit.jsonl", 4_194_304)
    records = [AuditEvent.model_validate_json(line) for line in audit_bytes.splitlines()]
    pending = {}
    completed = set()
    review_tool = "review_plan" if report.input_kind == "terraform" else "review_kubernetes"
    for event in records:
        if event.run_id != report.run_id:
            raise GateDenied("audit run mismatch")
        if event.status == "denied":
            continue
        if event.status == "started":
            if event.call_id in pending or event.call_id in completed:
                raise GateDenied("duplicate audit call")
            pending[event.call_id] = event
        elif event.status in {"succeeded", "failed"}:
            start = pending.pop(event.call_id, None)
            if start is None or start.tool != event.tool or start.caller != event.caller:
                raise GateDenied("inconsistent audit call")
            if event.status != "succeeded":
                raise GateDenied("failed tool call")
            completed.add(event.call_id)
    if pending:
        raise GateDenied("unfinished audit call")
    if not any(
        e.tool == review_tool and e.status == "succeeded" and e.input_digest == digest
        for e in records
    ):
        raise GateDenied("missing matching infrastructure review event")
    if not any(e.tool == "explain_assessment" and e.status == "succeeded" for e in records):
        raise GateDenied("missing explanation event")
    binding = json.dumps(
        {
            "run_id": str(report.run_id),
            "source_digest": digest,
            "report_digest": sha256(report_bytes).hexdigest(),
            "audit_digest": sha256(audit_bytes).hexdigest(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return report, sha256(binding).hexdigest()


def approve(
    directory: Path,
    source: Path,
    private_key: Path,
    reviewer: str,
    reason: str,
    confirm: Callable[[str], str] = input,
) -> Path:
    report, digest = review_bundle(directory, source)
    # The signed key, not a self-asserted reviewer string, establishes identity.
    if stat.S_IMODE(private_key.stat(follow_symlinks=False).st_mode) & 0o077:
        raise GateDenied("private key permissions must be owner-only")
    key = Ed25519PrivateKey.from_private_bytes(read_regular(private_key, 32))
    challenge = f"APPROVE {digest[:12]}"
    print(f"Run {report.run_id}; decision={report.decision}; findings={len(report.findings)}")
    print(f"Bundle SHA256: {digest}")
    if (
        confirm(f"Review report.json. Type '{challenge}' to sign this local simulation: ").strip()
        != challenge
    ):
        raise GateDenied("reviewer confirmation did not match")
    now = datetime.now(UTC)
    claims = ApprovalClaims(
        run_id=report.run_id,
        bundle_digest=digest,
        reviewer=reviewer,
        reason=reason,
        key_fingerprint=sha256(key.public_key().public_bytes_raw()).hexdigest(),
        issued_at=now,
        expires_at=now + timedelta(minutes=30),
    )
    signed = SignedApproval(claims=claims, signature=key.sign(_canonical(claims)).hex())
    target = directory / "approval.json"
    write_private(target, signed.model_dump_json(indent=2).encode())
    return target


def simulate_deploy(directory: Path, source: Path, public_key: Path, approval_path: Path) -> Path:
    """Public-key-only verifier. Success writes a marker, never invokes deployment tools."""
    call_id = uuid4()
    log_path = directory / f"gate-{call_id}.jsonl"
    # Separate gate run ID keeps malformed/untrusted report data out of this audit record.
    gate_run = uuid4()
    with AuditWriter(log_path) as audit:

        def event(status, error_code=None):
            audit.write(
                AuditEvent(
                    run_id=gate_run,
                    call_id=call_id,
                    timestamp=datetime.now(UTC),
                    caller="pipeline",
                    tool="simulate_deploy",
                    permission="allowed",
                    status=status,
                    error_code=error_code,
                )
            )

        event("started")
        try:
            report, digest = review_bundle(directory, source)
            public_bytes = read_regular(public_key, 32)
            key = Ed25519PublicKey.from_public_bytes(public_bytes)
            approval = SignedApproval.model_validate_json(read_regular(approval_path, 16_384))
            key.verify(bytes.fromhex(approval.signature), _canonical(approval.claims))
            claims = approval.claims
            now = datetime.now(UTC)
            if (
                claims.schema_version != "1.0"
                or claims.run_id != report.run_id
                or claims.bundle_digest != digest
                or claims.key_fingerprint != sha256(public_bytes).hexdigest()
                or claims.issued_at.utcoffset() is None
                or claims.expires_at.utcoffset() is None
                or not claims.issued_at <= now < claims.expires_at
                or claims.expires_at - claims.issued_at > timedelta(hours=1)
            ):
                raise GateDenied("approval binding or validity window failed")
            receipt = directory / "simulation-receipt.json"
            write_private(
                receipt,
                json.dumps(
                    {
                        "simulation_only": True,
                        "run_id": str(report.run_id),
                        "bundle_digest": digest,
                        "reviewer_key_fingerprint": claims.key_fingerprint,
                        "verified_at": now.isoformat(),
                        "infrastructure_operations": 0,
                    },
                    indent=2,
                ).encode(),
            )
        except (OSError, ValueError, TypeError, ValidationError, InvalidSignature, GateDenied):
            event("failed", "approval_or_bundle_invalid")
            raise GateDenied(
                "simulation denied: missing, invalid, expired, changed, or replayed approval"
            ) from None
        event("succeeded")
    return receipt
