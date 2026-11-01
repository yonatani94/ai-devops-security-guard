import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from ai_devops_guard.audit import AuditError, AuditWriter
from ai_devops_guard.models import AuditEvent, TerraformPlan
from ai_devops_guard.rules.terraform import review_plan
from ai_devops_guard.tools import ToolDenied, ToolDispatcher, ToolExecutionError

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "terraform"


@pytest.fixture
def data():
    return json.loads((EXAMPLES / "risky.plan.json").read_text())


def review(data):
    return review_plan(TerraformPlan.model_validate(data))


def events(path):
    return [AuditEvent.model_validate_json(line) for line in path.read_text().splitlines()]


def test_risky_fixture_has_evidence():
    data = json.loads((EXAMPLES / "risky.plan.json").read_text())
    result = review(data)
    assert {f.rule_id for f in result.findings} == {"TF-AWS-001", "TF-AWS-002"}
    assert result.analysis_complete
    for finding in result.findings:
        node = data
        for part in finding.evidence_path.split("/")[1:]:
            node = node[int(part)] if isinstance(node, list) else node[part]
        assert isinstance(node, str)


def test_safe_fixture_is_clear_within_supported_scope():
    result = review(json.loads((EXAMPLES / "safe.plan.json").read_text()))
    assert result.findings == []
    assert result.analysis_complete


@pytest.mark.parametrize(
    "protocol,start,end,source,expected",
    [
        ("tcp", 20, 30, "0.0.0.0/0", True),
        ("6", 22, 22, "::/0", True),
        ("-1", 0, 0, "::/0", True),
        ("udp", 22, 22, "0.0.0.0/0", False),
        ("tcp", 443, 443, "0.0.0.0/0", False),
        ("tcp", 22, 22, "10.0.0.0/8", False),
    ],
)
def test_ssh_semantics(data, protocol, start, end, source, expected):
    data["resource_changes"] = data["resource_changes"][:1]
    rule = data["resource_changes"][0]["change"]["after"]["ingress"][0]
    rule.update(protocol=protocol, from_port=start, to_port=end)
    rule["cidr_blocks"] = [] if ":" in source else [source]
    rule["ipv6_cidr_blocks"] = [source] if ":" in source else []
    result = review(data)
    assert bool(result.findings) == expected
    assert result.analysis_complete


@pytest.mark.parametrize(
    "effect,action,resource,expected",
    [
        ("Allow", ["s3:GetObject", "*"], ["*"], True),
        ("Deny", "*", "*", False),
        ("Allow", "s3:*", "*", False),
        ("Allow", "*", "arn:aws:s3:::demo/*", False),
    ],
)
def test_iam_semantics(data, effect, action, resource, expected):
    data["resource_changes"] = data["resource_changes"][1:]
    data["resource_changes"][0]["change"]["after"]["policy"] = json.dumps(
        {
            "Statement": {"Effect": effect, "Action": action, "Resource": resource},
        }
    )
    result = review(data)
    assert bool(result.findings) == expected
    assert result.analysis_complete


@pytest.mark.parametrize("kind", ["unknown", "sensitive", "unsupported", "malformed", "missing"])
def test_coverage_gaps_are_explicit(data, kind):
    resource = data["resource_changes"][0]
    if kind == "unknown":
        resource["change"]["after_unknown"] = {"ingress": [{"cidr_blocks": True}]}
    elif kind == "sensitive":
        resource["change"]["after_sensitive"] = {"ingress": True}
    elif kind == "unsupported":
        resource["type"] = "aws_s3_bucket"
    elif kind == "malformed":
        resource["change"]["after"]["ingress"][0]["from_port"] = "22"
    else:
        resource["change"]["after"] = None
    result = review(data)
    assert result.coverage_gaps
    assert not result.analysis_complete


@pytest.mark.parametrize(
    "policy",
    [
        "invalid-json",
        '{"Statement": []}',
        '{"Statement": [{"Effect": "Allow", "NotAction": "x", "Resource": "*"}]}',
    ],
)
def test_malformed_or_unsupported_iam_is_incomplete(data, policy):
    data["resource_changes"][1]["change"]["after"]["policy"] = policy
    assert not review(data).analysis_complete


@pytest.mark.parametrize("actions", [["delete"], ["no-op"]])
def test_unchanged_or_deleted_resources_are_skipped(data, actions):
    for resource in data["resource_changes"]:
        resource["change"]["actions"] = actions
    assert review(data).findings == []


def test_allowed_review_is_correlated_and_private(tmp_path):
    log = tmp_path / "audit.jsonl"
    run_id = uuid4()
    with AuditWriter(log) as writer:
        result = ToolDispatcher(EXAMPLES / "risky.plan.json", writer, run_id).call(
            "review_plan", {}
        )
    assert len(result.findings) == 2
    records = events(log)
    assert [r.status for r in records] == ["started", "succeeded"]
    assert {r.run_id for r in records} == {run_id}
    assert records[0].call_id == records[1].call_id
    assert records[1].duration_ms >= 0
    assert os.stat(log).st_mode & 0o777 == 0o600


@pytest.mark.parametrize(
    "tool,args,caller",
    [
        ("shell SECRET", {}, "pipeline"),
        ("review_plan", {"path": "SECRET"}, "pipeline"),
        ("review_plan", {}, "model"),
        ("review_plan", {}, "spoofed"),
    ],
)
def test_denials_are_logged_without_untrusted_content(tmp_path, tool, args, caller):
    log = tmp_path / "audit.jsonl"
    with AuditWriter(log) as writer:
        dispatcher = ToolDispatcher(tmp_path / "missing", writer, uuid4())
        with pytest.raises(ToolDenied):
            dispatcher.call(tool, args, caller=caller)
    assert [r.status for r in events(log)] == ["denied"]
    assert "SECRET" not in log.read_text()


@pytest.mark.parametrize("kind", ["missing", "invalid", "oversize", "symlink", "directory"])
def test_read_failures_are_audited(tmp_path, kind):
    plan = tmp_path / "plan.json"
    if kind == "invalid":
        plan.write_text('{"SECRET":')
    elif kind == "oversize":
        plan.write_bytes(b" " * (ToolDispatcher.MAX_PLAN_BYTES + 1))
    elif kind == "symlink":
        plan.symlink_to(EXAMPLES / "safe.plan.json")
    elif kind == "directory":
        plan.mkdir()
    log = tmp_path / "audit.jsonl"
    with AuditWriter(log) as writer:
        with pytest.raises(ToolExecutionError, match="plan review failed"):
            ToolDispatcher(plan, writer, uuid4()).call("review_plan", {})
    assert [r.status for r in events(log)] == ["started", "failed"]
    assert "SECRET" not in log.read_text()


def test_plan_secrets_do_not_enter_audit(tmp_path, data):
    data["resource_changes"][0]["address"] = "SECRET-ADDRESS"
    data["resource_changes"][0]["change"]["after"]["password"] = "SECRET-PASSWORD"
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(data))
    log = tmp_path / "audit.jsonl"
    with AuditWriter(log) as writer:
        ToolDispatcher(plan, writer, uuid4()).call("review_plan", {})
    assert "SECRET" not in log.read_text()


def test_writer_refuses_existing_file_and_symlink(tmp_path):
    target = tmp_path / "existing"
    target.write_text("preserve")
    link = tmp_path / "link"
    link.symlink_to(target)
    for path in (target, link):
        with pytest.raises(AuditError):
            AuditWriter(path)
    assert target.read_text() == "preserve"


@pytest.mark.parametrize("fail_on", [1, 2])
def test_audit_failure_blocks_execution_or_result(tmp_path, monkeypatch, fail_on):
    log = tmp_path / "audit.jsonl"
    with AuditWriter(log) as writer:
        dispatcher = ToolDispatcher(EXAMPLES / "safe.plan.json", writer, uuid4())
        writes, reads = [], []
        original_read = dispatcher._read_plan

        def read():
            reads.append(True)
            return original_read()

        def write(event):
            writes.append(event)
            if len(writes) == fail_on:
                raise AuditError("disk failure")

        monkeypatch.setattr(writer, "write", write)
        monkeypatch.setattr(dispatcher, "_read_plan", read)
        with pytest.raises(AuditError):
            dispatcher.call("review_plan", {})
        assert len(reads) == fail_on - 1


def test_real_write_failure_is_wrapped(tmp_path, monkeypatch):
    with AuditWriter(tmp_path / "audit.jsonl") as writer:

        def fail(*args):
            raise OSError("SECRET error")

        monkeypatch.setattr(os, "write", fail)
        event = AuditEvent(
            run_id=uuid4(),
            call_id=uuid4(),
            timestamp=datetime.now(UTC),
            caller="pipeline",
            tool="review_plan",
            permission="allowed",
            status="started",
        )
        with pytest.raises(AuditError, match="cannot persist audit event"):
            writer.write(event)


@pytest.mark.parametrize("failure", ["fsync", "zero_write"])
def test_persistence_failure_blocks_result(tmp_path, monkeypatch, failure):
    with AuditWriter(tmp_path / "audit.jsonl") as writer:
        if failure == "zero_write":
            monkeypatch.setattr(os, "write", lambda *args: 0)
        else:

            def fail(*args):
                raise OSError("cannot flush")

            monkeypatch.setattr(os, "fsync", fail)
        with pytest.raises(AuditError):
            ToolDispatcher(EXAMPLES / "safe.plan.json", writer, uuid4()).call("review_plan", {})


def test_short_writes_still_produce_complete_jsonl(tmp_path, monkeypatch):
    original_write = os.write
    monkeypatch.setattr(os, "write", lambda fd, data: original_write(fd, data[:11]))
    log = tmp_path / "audit.jsonl"
    with AuditWriter(log) as writer:
        ToolDispatcher(EXAMPLES / "safe.plan.json", writer, uuid4()).call("review_plan", {})
    assert [event.status for event in events(log)] == ["started", "succeeded"]


def test_closed_writer_fails_safely(tmp_path):
    writer = AuditWriter(tmp_path / "audit.jsonl")
    writer.close()
    writer.close()
    with pytest.raises(AuditError, match="closed"):
        ToolDispatcher(EXAMPLES / "safe.plan.json", writer, uuid4()).call("review_plan", {})


def test_unexpected_tool_error_is_sanitized_and_audited(tmp_path, monkeypatch):
    log = tmp_path / "audit.jsonl"
    with AuditWriter(log) as writer:
        dispatcher = ToolDispatcher(EXAMPLES / "safe.plan.json", writer, uuid4())

        def fail():
            raise RuntimeError("SECRET implementation detail")

        monkeypatch.setattr(dispatcher, "_read_plan", fail)
        with pytest.raises(ToolExecutionError) as error:
            dispatcher.call("review_plan", {})
        assert "SECRET" not in str(error.value)
    assert [event.status for event in events(log)] == ["started", "failed"]
    assert "SECRET" not in log.read_text()
