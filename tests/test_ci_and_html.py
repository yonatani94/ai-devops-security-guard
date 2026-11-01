import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest

from ai_devops_guard.html_report import render_html
from ai_devops_guard.models import Assessment
from ai_devops_guard.pipeline import run_review

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ci_review", ROOT / "scripts/ci_review.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"protection_rules": []},
        {
            "protection_rules": [
                {"type": "required_reviewers", "reviewers": [], "prevent_self_review": True},
            ]
        },
        {
            "protection_rules": [
                {
                    "type": "required_reviewers",
                    "reviewers": [{"id": 1}],
                    "prevent_self_review": False,
                },
            ]
        },
    ],
)
def test_environment_fails_closed(data):
    with pytest.raises(ValueError):
        ci.validate_environment({"name": "security-review", **data})


def test_environment_requires_reviewers_and_prevents_self_review():
    ci.validate_environment(
        {
            "name": "security-review",
            "protection_rules": [
                {
                    "type": "required_reviewers",
                    "reviewers": [{"id": 1}],
                    "prevent_self_review": True,
                },
            ],
        }
    )


@pytest.mark.parametrize("kind", ["terraform", "kubernetes"])
def test_ci_artifact_binding(tmp_path, monkeypatch, kind):
    monkeypatch.chdir(ROOT)
    output = tmp_path / "bundle"
    digest = ci.prepare(kind, output)
    ci.verify(output, digest)
    assert (output / "github-simulation-receipt.json").exists()
    with pytest.raises(ValueError):
        ci.verify(output, "0" * 64)


def test_script_free_html_escapes_model_text():
    report = Assessment(
        run_id=uuid4(),
        findings=[],
        decision="pass",
        analysis_complete=True,
        ai_status="simulated",
        ai_explanation='<script>alert("x")</script>',
    )
    html = render_html(report, [])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Content-Security-Policy" in html
    assert "default-src 'none'" in html


def test_pipeline_html_matches_assessment(tmp_path):
    report, directory = run_review(ROOT / "examples/terraform/risky.plan.json", tmp_path)
    html = (directory / "report.html").read_text()
    assert str(report.run_id) in html
    assert "REVIEW REQUIRED" in html
    assert "TF-AWS-001" in html
    assert "SIMULATED" in html


def solo_environment():
    return {
        "name": "security-review-solo-demo",
        "protection_rules": [
            {
                "type": "required_reviewers",
                "prevent_self_review": False,
                "reviewers": [{"type": "User", "reviewer": {"login": "yonatani94"}}],
            }
        ],
    }


def test_explicit_solo_mode_accepts_named_owner_reviewer():
    ci.validate_environment(solo_environment(), "solo-demo", "yonatani94")


@pytest.mark.parametrize(
    "change", ["wrong_name", "wrong_reviewer", "no_reviewer", "self_review_prevented"]
)
def test_solo_policy_cannot_be_used_for_other_environments_or_reviewers(change):
    data = solo_environment()
    if change == "wrong_name":
        data["name"] = "security-review"
    elif change == "wrong_reviewer":
        data["protection_rules"][0]["reviewers"][0]["reviewer"]["login"] = "someone-else"
    elif change == "no_reviewer":
        data["protection_rules"][0]["reviewers"] = []
    else:
        data["protection_rules"][0]["prevent_self_review"] = True
    with pytest.raises(ValueError):
        ci.validate_environment(data, "solo-demo", "yonatani94")


def test_solo_mode_cannot_replace_independent_default():
    with pytest.raises(ValueError):
        ci.validate_environment(solo_environment())
    with pytest.raises(ValueError):
        ci.validate_environment(solo_environment(), "solo-demo")
    with pytest.raises(ValueError):
        ci.environment_for("bypass")


@pytest.mark.parametrize("kind", ["terraform", "kubernetes"])
def test_solo_fixture_verification_records_mode(tmp_path, monkeypatch, kind):
    import json

    monkeypatch.chdir(ROOT)
    output = tmp_path / "bundle"
    digest = ci.prepare(kind, output, "solo-demo")
    ci.verify(output, digest, "solo-demo")
    receipt = json.loads((output / "github-simulation-receipt.json").read_text())
    assert receipt["approval_mode"] == "solo-demo"
    assert receipt["self_review_permitted"] is True
    assert receipt["infrastructure_operations"] == 0


def test_solo_mode_rejects_other_valid_reviewed_input(tmp_path, monkeypatch):
    import json
    import shutil

    from ai_devops_guard.approval import review_bundle

    monkeypatch.chdir(ROOT)
    data = json.loads((ROOT / "examples/terraform/risky.plan.json").read_text())
    data["resource_changes"][0]["change"]["after"]["description"] = "Different input"
    source = tmp_path / "custom.plan.json"
    source.write_text(json.dumps(data))
    _, run = run_review(source, tmp_path / "runs")
    output = tmp_path / "bundle"
    output.mkdir()
    shutil.copytree(run, output / "review")
    (output / "input").write_bytes(source.read_bytes())
    _, digest = review_bundle(output / "review", output / "input")
    with pytest.raises(ValueError, match="solo demo"):
        ci.verify(output, digest, "solo-demo")
    assert not (output / "github-simulation-receipt.json").exists()
