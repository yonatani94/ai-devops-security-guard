"""Private reports. Render untrusted strings as escaped, single-line Markdown."""

import html
import os
import re
from pathlib import Path

from ai_devops_guard.html_report import render_html
from ai_devops_guard.models import Assessment, AuditEvent
from ai_devops_guard.storage import read_regular


def _text(value: str) -> str:
    value = " ".join(value.split())
    value = html.escape(value, quote=False)
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", value)


def markdown(assessment: Assessment) -> str:
    lines = [
        "# Infrastructure risk assessment",
        "",
        f"Run: {assessment.run_id}",
        "",
        f"Decision: **{assessment.decision}**",
        "",
        f"Analysis complete: {assessment.analysis_complete}",
        "",
        f"AI status: **{assessment.ai_status}**",
        "",
        f"Input: {assessment.input_kind}. This report does not authorize deployment.",
        "",
        "## Findings",
        "",
    ]
    for finding in assessment.findings:
        lines.extend(
            [
                f"- **{_text(finding.rule_id)} / {_text(finding.severity)}**: "
                f"{_text(finding.summary)}",
                f"  Resource: {_text(finding.resource_address)}; "
                f"evidence: {_text(finding.evidence_path)}.",
                f"  Remediation: {_text(finding.remediation)}",
                "",
            ]
        )
    if not assessment.findings:
        lines.extend(["No findings recorded; check completeness and coverage below.", ""])
    lines.extend(["## Coverage gaps", ""])
    lines.extend(f"- {_text(gap)}" for gap in assessment.coverage_gaps)
    if not assessment.coverage_gaps:
        lines.append("None within the supported scope.")
    lines.extend(
        ["", "## Explanation", "", _text(assessment.ai_explanation or "Not generated."), ""]
    )
    return "\n".join(lines)


def write_reports(directory: Path, assessment: Assessment) -> None:
    events = [
        AuditEvent.model_validate_json(line)
        for line in read_regular(directory / "audit.jsonl", 4_194_304).splitlines()
    ]
    for name, content in (
        ("report.json", assessment.model_dump_json(indent=2) + "\n"),
        ("report.md", markdown(assessment)),
        ("report.html", render_html(assessment, events)),
    ):
        fd = os.open(directory / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
