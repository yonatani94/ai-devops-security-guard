import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "reusable_review", ROOT / "scripts/reusable_review.py"
)
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


@pytest.mark.parametrize(
    "kind,name,decision,code,count",
    [
        ("terraform", "safe.plan.json", "pass", "0", "0"),
        ("terraform", "risky.plan.json", "review_required", "1", "2"),
        ("terraform", "unknown.plan.json", "error", "2", "0"),
        ("kubernetes", "safe.yaml", "pass", "0", "0"),
        ("kubernetes", "risky.yaml", "review_required", "1", "2"),
    ],
)
def test_reusable_review_returns_gate_results(tmp_path, kind, name, decision, code, count):
    result = ci.review(ROOT, f"examples/{kind}/{name}", kind, tmp_path)
    assert result["decision"] == decision
    assert result["exit-code"] == code
    assert result["finding-count"] == count
    assert len(result["input-digest"]) == 64
    report = json.loads((Path(result["report-directory"]) / "report.json").read_text())
    assert report["ai_status"] in {"simulated", "not_run"}


@pytest.mark.parametrize("relative", ["", "../outside", "/etc/passwd", "examples/../README.md"])
def test_input_cannot_escape_checkout(tmp_path, relative):
    with pytest.raises(ValueError):
        ci.confined_input(tmp_path, relative)


@pytest.mark.parametrize("intermediate", [False, True])
def test_symlink_components_are_rejected(tmp_path, intermediate):
    data = tmp_path / "data"
    data.mkdir()
    (data / "input").write_text("{}")
    link = tmp_path / "link"
    link.symlink_to(data if intermediate else data / "input")
    with pytest.raises(ValueError, match="symlink"):
        ci.confined_input(tmp_path, "link/input" if intermediate else "link")


def test_untrusted_code_in_checkout_never_executes(tmp_path):
    marker = tmp_path / "executed"
    (tmp_path / "sitecustomize.py").write_text(f"open({str(marker)!r}, 'w').write('bad')")
    (tmp_path / "pyproject.toml").write_text("not a Python project")
    (tmp_path / "plan.json").write_bytes((ROOT / "examples/terraform/safe.plan.json").read_bytes())
    result = ci.review(tmp_path, "plan.json", "terraform", tmp_path / "output")
    assert result["decision"] == "pass"
    assert not marker.exists()


def test_invalid_input_writes_error_output_without_raw_path(tmp_path, monkeypatch, capsys):
    outputs, summary = tmp_path / "outputs", tmp_path / "summary"
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    code = ci.main(
        [
            "--workspace",
            str(tmp_path),
            "--input-path",
            "CANARY\nforged-output=true",
            "--kind",
            "terraform",
            "--output",
            str(tmp_path / "out"),
        ]
    )
    assert code == 2
    assert outputs.read_text() == "decision=error\nexit-code=2\n"
    assert "CANARY" not in capsys.readouterr().out + summary.read_text()
