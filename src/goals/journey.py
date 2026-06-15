"""The building journey — the plain-English trace of how a goal got built.

PACERS' *Assess* and *Choose* stages, made legible. The agent records assumptions
(what it's leaning on) and breakdowns (how it split the problem); this module turns
them into something a non-technical reader can follow, at one of three audience
levels. The dashboard renders the same data as HTML; this module owns the shared
logic so the two surfaces agree.
"""

from __future__ import annotations

from goals.models import Assumption, Audience, GoalSnapshot

# Broken assumptions are the highest-trust signal ("the agent assumed X, and X was
# false") so they sort first; holding/validated follow. Within a status, the
# load-bearing ones (depends_on) come before incidental ones.
_STATUS_ORDER = {"broken": 0, "holding": 1, "validated": 2}


def reframe(base: str, notes: dict[str, str], audience: Audience) -> str:
    """Render an explanation for the chosen audience.

    The base statement is always high-school readable and complete on its own.
    ``college`` and ``hobbyist`` only *add* framing; when no note exists for the
    audience we fall back to the base rather than inventing one.
    """
    if audience == "high_school":
        return base
    extra = (notes or {}).get(audience, "").strip()
    return f"{base} {extra}".strip() if extra else base


def sort_assumptions(assumptions: list[Assumption]) -> list[Assumption]:
    """Order assumptions for display: broken first, then load-bearing."""
    return sorted(
        assumptions,
        key=lambda a: (_STATUS_ORDER.get(a.status, 1), not a.depends_on),
    )


def render_journey_text(snapshot: GoalSnapshot, audience: Audience = "high_school") -> str:
    """Plain-language journey for the terminal — assumptions, open questions, calls."""
    lines = ["# The building journey", ""]

    if snapshot.breakdowns:
        lines.append("## How the agent broke the problem down")
        for breakdown in snapshot.breakdowns:
            scope = f" ({breakdown.phase_id})" if breakdown.phase_id else ""
            problem = reframe(breakdown.problem, breakdown.audience_notes, audience)
            lines.append(f"\n### {problem}{scope}")
            if breakdown.pause_note:
                lines.append(f"_Pause:_ {breakdown.pause_note}")
            for sub in breakdown.subproblems:
                lines.append(f"- **{reframe(sub.statement, sub.audience_notes, audience)}**")
                for task in sub.tasks:
                    lines.append(f"    - task: {task}")
                for question in sub.open_questions:
                    lines.append(f"    - open question: {question}")
            if breakdown.system_view:
                lines.append(f"_What keeps feeding this:_ {breakdown.system_view}")
        lines.append("")

    if snapshot.assumptions:
        lines.append("## What the agent assumed")
        for assumption in sort_assumptions(snapshot.assumptions):
            flag = " [load-bearing]" if assumption.depends_on else ""
            text = reframe(assumption.statement, assumption.audience_notes, audience)
            lines.append(f"- ({assumption.status}){flag} {text}")
            if assumption.toward:
                lines.append(f"    toward: {assumption.toward}")
        lines.append("")

    if snapshot.judgements:
        lines.append("## What was decided")
        for judgement in snapshot.judgements:
            who = judgement.decided_by
            lines.append(f"- {judgement.question} → chose: {judgement.choice} ({who})")

    if len(lines) <= 2:
        return "No building journey recorded yet.\n"
    return "\n".join(lines).rstrip() + "\n"
