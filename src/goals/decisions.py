from __future__ import annotations

from typing import Literal

from goals.models import (
    AutonomySignals,
    Decision,
    DecisionBrief,
    DecisionBriefItem,
    DecisionContext,
    DecisionExplanation,
    DecisionOption,
    GoalSnapshot,
    PersonalizationContext,
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


def build_decision_context(
    snapshot: GoalSnapshot,
    personalization: PersonalizationContext | None = None,
) -> DecisionContext:
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
        personalization=personalization,
    )


def render_decision_explanation(
    decision: Decision,
    context: DecisionContext,
    *,
    level: Literal["basic", "detailed", "technical"] = "basic",
) -> DecisionExplanation:
    surfaced, reason = should_surface_decision(decision, _autonomy(context))
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


def build_decision_brief(
    snapshot: GoalSnapshot,
    personalization: PersonalizationContext | None = None,
) -> DecisionBrief:
    context = build_decision_context(snapshot, personalization)
    user_decisions: list[DecisionBriefItem] = []
    agent_handled_count = 0
    autonomy = _autonomy(context)
    for decision in snapshot.decisions:
        surfaced, reason = should_surface_decision(decision, autonomy)
        if surfaced:
            user_decisions.append(_brief_item(snapshot, decision, context, reason))
        else:
            agent_handled_count += 1

    if user_decisions:
        summary = (
            f"{len(user_decisions)} decision(s) need your answer before the goal can continue "
            f"cleanly. {agent_handled_count} routine choice(s) can stay with the agent."
        )
    elif snapshot.decisions:
        summary = (
            "No important decisions are waiting on you. "
            f"The agent can handle {agent_handled_count} routine/reversible choice(s) and record the assumption."
        )
    else:
        summary = "No decisions are waiting on you."

    return DecisionBrief(
        goal_id=snapshot.goal_id,
        waiting_on_user=bool(user_decisions),
        summary=summary,
        user_decisions=user_decisions,
        agent_handled_count=agent_handled_count,
        agent_handled_summary=(
            f"{agent_handled_count} routine/reversible choice(s) can stay with the agent."
            if agent_handled_count
            else "No agent-handled routine choices are recorded."
        ),
    )


def render_decision_brief(brief: DecisionBrief) -> str:
    lines = [
        "# Decision Brief",
        "",
        f"Goal: {brief.goal_id}",
        f"Waiting on user: {'yes' if brief.waiting_on_user else 'no'}",
        "",
        brief.summary,
        "",
        "## What Needs Your Answer",
    ]
    if not brief.user_decisions:
        lines.append("- Nothing important is waiting on you.")
    for item in brief.user_decisions:
        lines.extend(
            [
                f"### {item.title}",
                "",
                item.plain_summary,
                "",
                f"Why this needs you: {item.why_user_needed}",
                f"Recommendation: {item.recommendation}",
                f"Suggested reply: `{item.suggested_reply}`",
                f"What happens next: {item.what_happens_next}",
                f"Confidence: {item.confidence:.0%}",
                "",
                "Options:",
                _bullets(item.option_summaries or ["No alternatives recorded."]),
                "",
                "What Goals knows so far:",
                _bullets(item.known_context or ["No prior goal context recorded yet."]),
                "",
                "Uncertainty:",
                _bullets(item.uncertainty or ["No major uncertainty recorded."]),
                "",
            ]
        )
    lines.extend(
        [
            "## What the Agent Can Handle",
            f"- {brief.agent_handled_summary}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _autonomy(context: DecisionContext) -> AutonomySignals | None:
    if context.personalization is None:
        return None
    return context.personalization.autonomy


def should_surface_decision(
    decision: Decision, autonomy: AutonomySignals | None = None
) -> tuple[bool, str]:
    """Decide whether a judgement is surfaced to the user or left to the agent.

    The first three rules are a **hard safety floor**: blocking, high-risk, and
    irreversible-and-not-trivial (irreversible with at least medium risk)
    decisions always surface, and ``autonomy`` (the user's learned preferences)
    can NEVER turn them off. Preferences only ever *tighten* the gate below the
    floor — e.g. a user who asks to "confirm anything I can't undo" surfaces even
    a low-risk irreversible decision the floor would have left with the agent.
    With ``autonomy=None`` the behaviour is unchanged.
    """
    if decision.priority == "blocking":
        return True, "This blocks the goal or changes its direction."
    if any(option.risk == "high" for option in decision.options):
        return True, "At least one option is high risk."
    if any(not option.reversible and option.risk == "medium" for option in decision.options):
        return True, "A meaningful option is not clearly reversible."
    # Below the floor: the default leaves this with the agent. Confirmed user
    # preferences may still ask about it (tighten) — never the reverse.
    if autonomy is not None:
        if autonomy.confirm_irreversible and any(
            not option.reversible for option in decision.options
        ):
            return True, "Asking because you've told me to confirm anything you can't undo."
        if autonomy.confirm_risky and any(option.risk != "low" for option in decision.options):
            return True, "Asking because you've told me to confirm anything risky."
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
    if context.personalization and context.personalization.guidance:
        summary.append(
            "User memory: " + "; ".join(context.personalization.guidance[:3])
        )
    return summary


def evidence_refs(context: DecisionContext) -> list[str]:
    refs: list[str] = []
    refs.extend([f"phase:{phase}" for phase in context.accepted_phases])
    refs.extend([f"check:{check}" for check in context.checks_run])
    refs.extend([f"file:{path}" for path in context.changed_files])
    refs.extend([f"source:{claim}" for claim in context.source_claims])
    if context.personalization:
        refs.extend([f"profile:{claim_id}" for claim_id in context.personalization.claim_ids])
    return refs


def _brief_item(
    snapshot: GoalSnapshot,
    decision: Decision,
    context: DecisionContext,
    reason: str,
) -> DecisionBriefItem:
    suggested_reply = decision.suggested_reply or f"I choose: {decision.recommendation}"
    return DecisionBriefItem(
        decision_id=decision.decision_id,
        title=decision.title,
        plain_summary=decision.plain_summary,
        why_user_needed=reason,
        recommendation=decision.recommendation,
        suggested_reply=suggested_reply,
        confidence=decision.confidence,
        highest_risk=_highest_risk(decision.options),
        all_options_reversible=bool(decision.options)
        and all(option.reversible for option in decision.options),
        option_summaries=[_option_summary(option) for option in decision.options],
        what_happens_next=_what_happens_next(snapshot, suggested_reply),
        known_context=decision.what_we_know or context_summary(context),
        uncertainty=decision.uncertainty or context.known_gaps + context.blockers,
        evidence_refs=decision.evidence_refs or evidence_refs(context),
    )


def _highest_risk(options: list[DecisionOption]) -> Literal["low", "medium", "high"]:
    order = {"low": 0, "medium": 1, "high": 2}
    if not options:
        return "medium"
    return max((option.risk for option in options), key=lambda risk: order[risk])


def _option_summary(option: DecisionOption) -> str:
    reversible = "reversible" if option.reversible else "not clearly reversible"
    return f"{option.label}: {option.explanation} ({option.risk} risk, {reversible})"


def _what_happens_next(snapshot: GoalSnapshot, suggested_reply: str) -> str:
    phase = snapshot.current_phase or "the next phase"
    return (
        f"If you reply `{suggested_reply}`, the agent should record the choice, "
        f"continue {phase}, and keep proof in Goals."
    )


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
