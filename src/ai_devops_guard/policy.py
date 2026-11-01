"""Application-owned policy: explanations never decide approval."""

from uuid import UUID

from ai_devops_guard.models import Assessment
from ai_devops_guard.rules.terraform import RuleResult


def evaluate(result: RuleResult, run_id: UUID) -> Assessment:
    if not result.analysis_complete:
        decision = "error"
    elif result.findings:
        decision = "review_required"
    else:
        decision = "pass"
    return Assessment(
        run_id=run_id,
        findings=result.findings,
        decision=decision,
        analysis_complete=result.analysis_complete,
        coverage_gaps=result.coverage_gaps,
    )
