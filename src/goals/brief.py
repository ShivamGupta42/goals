from __future__ import annotations

from goals.checkpoints import build_current_checkpoint_brief, render_current_checkpoint_brief
from goals.decisions import build_decision_brief
from goals.issues import analyze_goal_issues
from goals.models import (
    GoalBrief,
    GoalBriefAction,
    GoalIssue,
    GoalSnapshot,
    PhaseStatus,
)


def build_goal_brief(snapshot: GoalSnapshot) -> GoalBrief:
    """Build a non-technical summary of the current goal state."""

    decision_brief = build_decision_brief(snapshot)
    issue_report = analyze_goal_issues(snapshot)
    current_checkpoint = build_current_checkpoint_brief(snapshot)
    decision_summaries = {item.plain_summary for item in decision_brief.user_decisions}
    user_actions = [
        GoalBriefAction(
            title=item.title,
            plain_summary=item.plain_summary,
            why_it_matters=item.why_user_needed,
            suggested_reply=item.suggested_reply,
            what_happens_next=item.what_happens_next,
            priority="blocking" if item.highest_risk == "high" else "important",
            source="decision",
            evidence_refs=item.evidence_refs,
        )
        for item in decision_brief.user_decisions
    ]
    for issue in issue_report.issues:
        if not issue.needs_user or issue.summary in decision_summaries:
            continue
        user_actions.append(_issue_user_action(issue))

    agent_actions = _agent_actions(snapshot, issue_report.issues)
    waiting_on = _waiting_on(snapshot, user_actions)
    accepted_count = len(
        [phase for phase in snapshot.phases if phase.status == PhaseStatus.ACCEPTED]
    )
    proof_count = len([phase for phase in snapshot.phases if phase.evidence is not None])
    total_count = len(snapshot.phases)
    checks = _checks_run(snapshot)
    progress = f"{accepted_count}/{total_count} step(s) accepted."
    proof = f"{proof_count}/{total_count} step(s) have proof recorded" + (
        f"; checks include {', '.join(checks[:4])}." if checks else "."
    )
    summary = _summary(waiting_on, len(user_actions), len(agent_actions), snapshot)
    technical_details = [
        f"Goal id: {snapshot.goal_id}",
        f"Event offset: {snapshot.event_count}",
        issue_report.summary,
    ]
    return GoalBrief(
        goal_id=snapshot.goal_id,
        objective=snapshot.objective,
        status=str(snapshot.status),
        current_step=snapshot.current_phase or "none",
        waiting_on=waiting_on,
        summary=summary,
        progress=progress,
        proof=proof,
        current_checkpoint=current_checkpoint,
        user_actions=user_actions,
        agent_actions=agent_actions,
        technical_details=technical_details,
    )


def render_goal_brief(brief: GoalBrief) -> str:
    lines = [
        "# Goal Brief",
        "",
        f"Goal: {brief.objective}",
        f"Status: {brief.status}",
        f"Current step: {brief.current_step}",
        f"Waiting on: {brief.waiting_on}",
        "",
        brief.summary,
        "",
        render_current_checkpoint_brief(brief.current_checkpoint)
        if brief.current_checkpoint
        else "## Current Checkpoint\n\nNo current checkpoint.",
        "",
        "## What Needs Your Answer",
        _render_actions(brief.user_actions, empty="Nothing important is waiting on you."),
        "",
        "## What the Agent Can Do Next",
        _render_actions(
            brief.agent_actions,
            empty="No agent-side repair action is currently suggested.",
        ),
        "",
        "## Progress and Proof",
        f"- {brief.progress}",
        f"- {brief.proof}",
        "",
        "## Technical Details",
        _bullets(brief.technical_details),
    ]
    return "\n".join(lines) + "\n"


def _issue_user_action(issue: GoalIssue) -> GoalBriefAction:
    title = _issue_title(issue)
    return GoalBriefAction(
        title=title,
        plain_summary=_plain_issue_summary(issue),
        why_it_matters=_plain_issue_reason(issue),
        suggested_reply=_plain_suggested_reply(issue),
        what_happens_next="After you answer, the agent should record the decision and continue with proof.",
        priority="blocking" if issue.severity == "p0" else "important",
        source=_action_source(issue),
        evidence_refs=issue.evidence_refs,
    )


def _agent_actions(snapshot: GoalSnapshot, issues: list[GoalIssue]) -> list[GoalBriefAction]:
    actions = [
        GoalBriefAction(
            title=_agent_title(issue),
            plain_summary=_plain_agent_summary(issue),
            why_it_matters=_plain_agent_reason(issue),
            suggested_reply=issue.suggested_action,
            what_happens_next="The agent can do this without interrupting you and record the result.",
            priority="important" if issue.severity in {"p0", "p1"} else "later",
            source=_action_source(issue),
            evidence_refs=issue.evidence_refs,
        )
        for issue in issues
        if issue.suggested_action and not issue.needs_user
    ]
    if not snapshot.definition_of_done:
        actions.append(
            GoalBriefAction(
                title="Clarify done",
                plain_summary="The agent should write down what finished means for this goal.",
                why_it_matters="Clear finish criteria help the agent avoid stopping too early.",
                suggested_reply="Record a plain-language definition of done.",
                what_happens_next="The agent should add this to goal state before closure.",
                priority="later",
                source="proof",
            )
        )
    return _dedupe_actions(actions)[:8]


def _waiting_on(
    snapshot: GoalSnapshot,
    user_actions: list[GoalBriefAction],
) -> str:
    if user_actions:
        return "you"
    # A terminal goal isn't waiting on anyone. Even if leftover agent-side
    # follow-ups remain, those surface under Issues — saying "waiting on agent"
    # on a complete goal contradicts its status.
    if str(snapshot.status) in {"complete", "failed"}:
        return "no one"
    return "agent"


def _summary(
    waiting_on: str,
    user_action_count: int,
    agent_action_count: int,
    snapshot: GoalSnapshot,
) -> str:
    if waiting_on == "you":
        return (
            f"{user_action_count} important item(s) need your answer. "
            f"The agent still has {agent_action_count} repair or follow-up action(s) it can handle."
        )
    if agent_action_count:
        return (
            "Nothing important needs your answer right now. "
            f"The agent has {agent_action_count} action(s) it can take next."
        )
    if str(snapshot.status) == "complete":
        return "The goal looks complete and nothing is waiting on you."
    return "The goal is moving; nothing important needs your answer right now."


def _plain_issue_summary(issue: GoalIssue) -> str:
    if issue.area == "gate" and "unsafe" in issue.summary.lower():
        return "The latest review found something unsafe, so the agent should not continue alone."
    if issue.area == "merge":
        return "There is a merge-readiness risk that may affect how the work is combined."
    if issue.area == "state":
        return "The goal state has a blocker that needs a clear path forward."
    return issue.summary


def _plain_issue_reason(issue: GoalIssue) -> str:
    if issue.area == "gate":
        return "Continuing without an answer could make the work unsafe or incorrect."
    if issue.area == "merge":
        return (
            "Merge choices can affect production data, conflicts, or the final project direction."
        )
    if issue.area == "state":
        return "The agent needs a reliable state before it can keep working independently."
    return issue.detail or "This may change the goal outcome or risk."


def _plain_suggested_reply(issue: GoalIssue) -> str:
    if issue.suggested_action:
        return issue.suggested_action
    if issue.area == "checkpoint":
        return "Answer the checkpoint question, or ask the agent to explain why it is needed."
    if issue.area == "gate":
        return "Pause and explain the unsafe part before continuing."
    return "Please explain the choice and recommended next step."


def _plain_agent_summary(issue: GoalIssue) -> str:
    if issue.area == "merge":
        return "The agent should resolve merge-readiness proof before merge."
    if issue.area == "source":
        return "The agent should strengthen or clean up source evidence."
    if issue.area == "evidence":
        return "The agent should add missing proof for the current step."
    if issue.area == "gate":
        return "The agent should fix review findings and run the gate again."
    if issue.area == "checkpoint":
        return "The agent should complete or waive the checkpoint before review."
    return issue.summary


def _plain_agent_reason(issue: GoalIssue) -> str:
    if issue.detail:
        return issue.detail
    if issue.area == "merge":
        return "This keeps coordination work with the agent unless a high-risk choice appears."
    if issue.area == "evidence":
        return "The goal needs proof before the step can be accepted."
    return "This is repair work the agent can do without asking you first."


def _issue_title(issue: GoalIssue) -> str:
    labels = {
        "decision": "Decision needed",
        "checkpoint": "Checkpoint needs you",
        "gate": "Review needs you",
        "merge": "Merge choice",
        "state": "Goal blocker",
    }
    return labels.get(str(issue.area), "Important question")


def _agent_title(issue: GoalIssue) -> str:
    labels = {
        "architecture": "Answer architecture gap",
        "checkpoint": "Complete checkpoint",
        "evidence": "Add missing proof",
        "gate": "Fix review issue",
        "merge": "Check merge readiness",
        "risk": "Resolve recorded risk",
        "source": "Fix source evidence",
        "state": "Repair goal state",
    }
    return labels.get(str(issue.area), "Continue repair work")


def _checks_run(snapshot: GoalSnapshot) -> list[str]:
    checks: list[str] = []
    for phase in snapshot.phases:
        if phase.evidence is not None:
            checks.extend(phase.evidence.checks_run)
    return _dedupe(checks)


def _action_source(issue: GoalIssue) -> str:
    if issue.area == "checkpoint":
        return "checkpoint"
    if issue.area == "merge":
        return "merge"
    return "issue"


def _dedupe_actions(actions: list[GoalBriefAction]) -> list[GoalBriefAction]:
    deduped: list[GoalBriefAction] = []
    seen: set[tuple[str, str]] = set()
    for action in actions:
        key = (action.title, action.plain_summary)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _render_actions(actions: list[GoalBriefAction], *, empty: str) -> str:
    if not actions:
        return f"- {empty}"
    lines: list[str] = []
    for action in actions:
        lines.extend(
            [
                f"### {action.title}",
                "",
                action.plain_summary,
                "",
                f"Why it matters: {action.why_it_matters}",
            ]
        )
        if action.suggested_reply:
            lines.append(f"Suggested reply or command: `{action.suggested_reply}`")
        if action.what_happens_next:
            lines.append(f"What happens next: {action.what_happens_next}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
