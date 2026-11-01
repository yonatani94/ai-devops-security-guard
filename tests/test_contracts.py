import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from ai_devops_guard.models import Assessment, AuditEvent, TerraformPlan

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "terraform"


@pytest.fixture
def plan_data():
    return json.loads((EXAMPLES / "risky.plan.json").read_text())


@pytest.mark.parametrize("name", ["safe", "risky"])
def test_synthetic_plans_parse(name):
    plan = TerraformPlan.model_validate_json((EXAMPLES / f"{name}.plan.json").read_text())
    assert len(plan.resource_changes) == 2
    assert plan.resource_changes[0].change.after_unknown["id"] is True


@pytest.mark.parametrize("version", ["2.0", "0.1", "1", "garbage", 1.2])
def test_rejects_unsupported_format(plan_data, version):
    plan_data["format_version"] = version
    with pytest.raises(ValidationError):
        TerraformPlan.model_validate(plan_data)


def test_accepts_minor_version_and_extra_metadata(plan_data):
    plan_data["format_version"] = "1.99"
    plan_data["future_metadata"] = {"example": True}
    assert TerraformPlan.model_validate(plan_data).format_version == "1.99"


@pytest.mark.parametrize("changes", [None, "invalid", [{}]])
def test_rejects_malformed_changes(plan_data, changes):
    plan_data["resource_changes"] = changes
    with pytest.raises(ValidationError):
        TerraformPlan.model_validate(plan_data)


def test_missing_changes_is_not_an_empty_plan(plan_data):
    del plan_data["resource_changes"]
    with pytest.raises(ValidationError):
        TerraformPlan.model_validate(plan_data)


def test_explicit_empty_changes_are_valid(plan_data):
    plan_data["resource_changes"] = []
    assert TerraformPlan.model_validate(plan_data).resource_changes == []


def test_preserves_nested_sensitive_and_unknown_markers(plan_data):
    change = plan_data["resource_changes"][0]["change"]
    change["after_sensitive"] = {"nested": [{"password": True}]}
    change["after_unknown"] = {"nested": [{"id": True}]}
    parsed = TerraformPlan.model_validate(plan_data).resource_changes[0].change
    assert parsed.after_sensitive == change["after_sensitive"]
    assert parsed.after_unknown == change["after_unknown"]


@pytest.mark.parametrize("actions", [[], ["execute"], ["update", "delete"]])
def test_rejects_unsupported_action_sequence(plan_data, actions):
    plan_data["resource_changes"][0]["change"]["actions"] = actions
    with pytest.raises(ValidationError):
        TerraformPlan.model_validate(plan_data)


@pytest.mark.parametrize("complete,gaps", [(False, []), (True, ["unsupported resource"])])
def test_incomplete_assessment_cannot_pass(complete, gaps):
    with pytest.raises(ValidationError):
        Assessment(
            run_id=uuid4(),
            findings=[],
            decision="pass",
            analysis_complete=complete,
            coverage_gaps=gaps,
        )


def audit_data():
    return dict(
        run_id=uuid4(),
        call_id=uuid4(),
        timestamp=datetime.now(UTC),
        caller="pipeline",
        tool="read_plan",
        permission="allowed",
        status="succeeded",
    )


def test_audit_json_round_trip():
    event = AuditEvent(**audit_data())
    assert AuditEvent.model_validate_json(event.model_dump_json()) == event


@pytest.mark.parametrize(
    "update",
    [
        {"timestamp": datetime(2026, 1, 1)},
        {"permission": "denied"},
        {"duration_ms": -1},
        {"input_digest": "not-a-sha256"},
        {"raw_prompt": "unexpected field"},
    ],
)
def test_rejects_invalid_audit_records(update):
    with pytest.raises(ValidationError):
        AuditEvent(**(audit_data() | update))


def test_denied_call_is_representable():
    event = AuditEvent(**(audit_data() | {"permission": "denied", "status": "denied"}))
    assert event.status == "denied"


def test_invalid_json_is_rejected():
    with pytest.raises(ValidationError):
        TerraformPlan.model_validate_json('{"format_version":')
