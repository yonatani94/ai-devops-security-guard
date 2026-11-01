from ai_devops_guard.ai.base import Explanation, ExplanationContext


class FakeProvider:
    status = "simulated"
    model = None

    def explain(self, context: ExplanationContext) -> Explanation:
        return Explanation(
            status="simulated",
            text=(
                "SIMULATED AI — deterministic template; no model inference. "
                f"The supported checks produced {context.finding_count} finding(s) and "
                f"{context.coverage_gap_count} coverage gap(s). "
                "Review each finding's evidence and remediation. "
                "Zero findings do not establish comprehensive infrastructure safety."
            ),
        )
