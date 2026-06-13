from __future__ import annotations

from goals.models import Decision, DecisionOption


def explain_decision(
    *,
    title: str,
    plain_summary: str,
    why_it_matters: str,
    recommendation: str,
    options: list[DecisionOption],
    confidence: float,
    technical_details: str = "",
) -> Decision:
    return Decision(
        title=title,
        plain_summary=plain_summary,
        why_it_matters=why_it_matters,
        recommendation=recommendation,
        options=options,
        confidence=confidence,
        suggested_reply=f"I choose: {recommendation}",
        technical_details=technical_details,
    )
