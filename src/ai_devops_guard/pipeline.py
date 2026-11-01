"""Review orchestration: evidence first, policy second, advisory AI last."""

from pathlib import Path
from uuid import uuid4

from ai_devops_guard.ai.base import ExplanationProvider
from ai_devops_guard.audit import AuditWriter
from ai_devops_guard.models import Assessment
from ai_devops_guard.policy import evaluate
from ai_devops_guard.reports import write_reports
from ai_devops_guard.rules.terraform import RuleResult
from ai_devops_guard.tools import ToolDispatcher, ToolExecutionError


def _explain(result: RuleResult, assessment: Assessment, tools: ToolDispatcher) -> Assessment:
    # Never ask a model to interpret incomplete or unsupported infrastructure data.
    if not result.analysis_complete:
        return assessment
    try:
        explanation = tools.call(
            "explain_assessment",
            {
                "finding_count": len(result.findings),
                "coverage_gap_count": len(result.coverage_gaps),
                "rule_ids": sorted({finding.rule_id for finding in result.findings}),
            },
        )
    except ToolExecutionError:
        updates = {
            "decision": "error",
            "ai_status": "failed",
            "analysis_complete": False,
            "coverage_gaps": [*assessment.coverage_gaps, "Explanation generation failed."],
        }
    else:
        updates = {"ai_status": explanation.status, "ai_explanation": explanation.text}
    # Revalidate instead of model_copy(update=...), which bypasses model validation.
    return Assessment(**(assessment.model_dump() | updates))


def run_review(
    plan: Path,
    output: Path,
    *,
    input_kind: str = "terraform",
    provider: ExplanationProvider | None = None,
) -> tuple[Assessment, Path]:
    run_id = uuid4()
    output.mkdir(parents=True, exist_ok=True)
    directory = output / str(run_id)
    directory.mkdir(mode=0o700)
    with AuditWriter(directory / "audit.jsonl") as audit:
        tools = ToolDispatcher(plan, audit, run_id, provider=provider, input_kind=input_kind)
        try:
            result = tools.call(
                "review_plan" if input_kind == "terraform" else "review_kubernetes", {}
            )
        except ToolExecutionError:
            assessment = Assessment(
                run_id=run_id,
                findings=[],
                decision="error",
                analysis_complete=False,
                coverage_gaps=["Infrastructure review failed; consult the audit log."],
            )
        else:
            assessment = _explain(result, evaluate(result, run_id), tools)
    assessment = Assessment(
        **(
            assessment.model_dump()
            | {
                "source_digest": tools.source_digest,
                "input_kind": input_kind,
                "ai_model": getattr(provider, "model", None),
            }
        )
    )
    write_reports(directory, assessment)
    return assessment, directory
