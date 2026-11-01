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
        ci.validate_environment(data)


def test_environment_requires_reviewers_and_prevents_self_review():
    ci.validate_environment(
        {
            "protection_rules": [
                {
                    "type": "required_reviewers",
                    "reviewers": [{"id": 1}],
                    "prevent_self_review": True,
                },
            ]
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
