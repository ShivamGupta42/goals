from __future__ import annotations

from typing import Literal

from goals.models import (
    Decision,
    DecisionContext,
    DecisionExplanation,
    DecisionOption,
    GoalSnapshot,
    PhaseStatus,
)


def explain_decision(
    *,
    title: str,
    plain_summary: str,
    why_it_matters: str,
    recommendation: str,
    options: list[DecisionOption],
    confidence: float,
    technical_details: str = "",
    context: DecisionContext | None = None,
    priority: Literal["blocking", "important", "later"] = "important",
) -> Decision:
    decision = Decision(
        title=title,
        plain_summary=plain_summary,
        why_it_matters=why_it_matters,
        recommendation=recommendation,
        options=options,
        confidence=confidence,
        priority=priority,
        suggested_reply=f"I choose: {recommendation}",
        technical_details=technical_details,
    )
    if context is not None:
        decision.what_we_know = context_summary(context)
        decision.evidence_refs = evidence_refs(context)
        decision.uncertainty = context.known_gaps + context.blockers
    return decision


def build_decision_context(snapshot: GoalSnapshot) -> DecisionContext:
    checks: list[str] = []
    changed_files: list[str] = []
    known_gaps: list[str] = []
    accepted_phases: list[str] = []
    for phase in snapshot.phases:
        if phase.status == PhaseStatus.ACCEPTED:
            accepted_phases.append(f"{phase.phase_id}: {phase.title}")
        if phase.evidence is None:
            continue
        checks.extend(phase.evidence.checks_run)
        changed_files.extend(phase.evidence.changed_files)
        known_gaps.extend(phase.evidence.known_gaps)
    return DecisionContext(
        goal_objective=snapshot.objective,
        goal_status=str(snapshot.status),
        current_phase=snapshot.current_phase,
        accepted_phases=_dedupe(accepted_phases),
        checks_run=_dedupe(checks),
        changed_files=_dedupe(changed_files),
        known_gaps=_dedupe(known_gaps + snapshot.risks),
        prior_decisions=_dedupe([decision.title for decision in snapshot.decisions]),
        source_claims=_dedupe(
            [
                f"{claim.claim} ({', '.join(claim.source_ids) or 'no source'})"
                for claim in snapshot.source_claims
            ]
        ),
        blockers=_dedupe(snapshot.blockers),
        learnings=_dedupe(snapshot.learnings),
    )


def render_decision_explanation(
    decision: Decision,
    context: DecisionContext,
    *,
    level: Literal["basic", "detailed", "technical"] = "basic",
) -> DecisionExplanation:
    surfaced, reason = should_surface_decision(decision)
    sections = {
        "basic": _render_basic(decision, context, reason),
        "detailed": _render_detailed(decision, context, reason),
        "technical": _render_technical(decision, context, reason),
    }
    return DecisionExplanation(
        level=level,
        surfaced_to_user=surfaced,
        reason_for_surface=reason,
        markdown=sections[level],
        decision=decision,
        context=context,
    )


def should_surface_decision(decision: Decision) -> tuple[bool, str]:
    if decision.priority == "blocking":
        return True, "This blocks the goal or changes its direction."
    if any(option.risk == "high" for option in decision.options):
        return True, "At least one option is high risk."
    if any(not option.reversible and option.risk == "medium" for option in decision.options):
        return True, "A meaningful option is not clearly reversible."
    return False, "The agent can choose a reversible or low-risk option and record the assumption."


def context_summary(context: DecisionContext) -> list[str]:
    summary = [f"Goal: {context.goal_objective}"]
    if context.accepted_phases:
        summary.append(f"Accepted phases: {', '.join(context.accepted_phases)}")
    if context.checks_run:
        summary.append(f"Checks run: {', '.join(context.checks_run[:4])}")
    if context.changed_files:
        summary.append(f"Changed files: {', '.join(context.changed_files[:4])}")
    if context.known_gaps:
        summary.append(f"Known gaps: {', '.join(context.known_gaps[:4])}")
    if context.source_claims:
        summary.append(f"Source-backed claims: {', '.join(context.source_claims[:4])}")
    return summary


def evidence_refs(context: DecisionContext) -> list[str]:
    refs: list[str] = []
    refs.extend([f"phase:{phase}" for phase in context.accepted_phases])
    refs.extend([f"check:{check}" for check in context.checks_run])
    refs.extend([f"file:{path}" for path in context.changed_files])
    refs.extend([f"source:{claim}" for claim in context.source_claims])
    return refs


def _render_basic(decision: Decision, context: DecisionContext, reason: str) -> str:
    options = "\n".join(f"- {option.label}: {option.explanation}" for option in decision.options)
    return "\n".join(
        [
            f"# {decision.title}",
            "",
            decision.plain_summary,
            "",
            f"**Recommendation:** {decision.recommendation}",
            f"**Why you are seeing this:** {reason}",
            f"**Suggested reply:** `{decision.suggested_reply or f'I choose: {decision.recommendation}'}`",
            "",
            "## Options",
            options or "- No alternatives recorded.",
            "",
            "## What we know so far",
            _bullets(context_summary(context)),
        ]
    )


def _render_detailed(decision: Decision, context: DecisionContext, reason: str) -> str:
    option_lines = []
    for option in decision.options:
        tradeoffs = "; ".join(option.tradeoffs) if option.tradeoffs else "No tradeoffs recorded."
        reversible = "reversible" if option.reversible else "not clearly reversible"
        option_lines.append(f"- **{option.label}** ({option.risk} risk, {reversible}): {tradeoffs}")
    return "\n".join(
        [
            _render_basic(decision, context, reason),
            "",
            "## Tradeoffs",
            "\n".join(option_lines) or "- No tradeoffs recorded.",
            "",
            f"## Confidence\n- {decision.confidence:.0%}",
            "",
            "## Uncertainty",
            _bullets(
                decision.uncertainty or context.known_gaps or ["No major uncertainty recorded."]
            ),
        ]
    )


def _render_technical(decision: Decision, context: DecisionContext, reason: str) -> str:
    return "\n".join(
        [
            _render_detailed(decision, context, reason),
            "",
            "## Technical Details",
            decision.technical_details or "No technical details recorded.",
            "",
            "## Evidence References",
            _bullets(
                decision.evidence_refs
                or evidence_refs(context)
                or ["No evidence references recorded."]
            ),
            "",
            "## Prior Decisions",
            _bullets(context.prior_decisions or ["No prior decisions recorded."]),
        ]
    )


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _dedupe(items: list[str]) -> list[str]:
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
