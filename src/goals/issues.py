from __future__ import annotations

from pathlib import Path

from goals.architecture import analyze_code_architecture
from goals.decisions import should_surface_decision
from goals.gates import review_phase
from goals.merge_readiness import analyze_merge_readiness
from goals.models import (
    CheckpointStatus,
    GateFindingCategory,
    GateVerdict,
    GoalIssue,
    GoalIssueReport,
    GoalSnapshot,
    GoalStatus,
    PhaseStatus,
)
from goals.rubric import representative_category
from goals.sources import analyze_source_freshness, unresolved_claims

# Category-aware next step for a failing gate issue. The text renders in `goals check`
# (workflows._issue_lines appends `Next: {suggested_action}`), so it carries the rubric
# into plain output without touching the gate kernel.
_GATE_CATEGORY_ACTION: dict[GateFindingCategory, str] = {
    GateFindingCategory.BUG: "A check the agent ran is failing — fix the code, then re-verify.",
    GateFindingCategory.GAP: "Finish the unmet acceptance criterion, then re-verify.",
    GateFindingCategory.VERIFICATION_MISS: (
        "Add and run a check that proves this, then re-review."
    ),
}


def analyze_goal_issues(snapshot: GoalSnapshot) -> GoalIssueReport:
    issues: list[GoalIssue] = []
    issues.extend(_state_issues(snapshot))
    issues.extend(_phase_issues(snapshot))
    issues.extend(_decision_issues(snapshot))
    issues.extend(_source_issues(snapshot))
    issues.extend(_risk_issues(snapshot))
    issues.extend(_architecture_issues(snapshot))
    issues.extend(_merge_readiness_issues(snapshot))
    user_questions = [issue.summary for issue in issues if issue.needs_user]
    agent_actions = _unique(
        [
            issue.suggested_action
            for issue in issues
            if issue.suggested_action and not issue.needs_user
        ]
    )
    blocking = [issue for issue in issues if issue.severity == "p0"]
    return GoalIssueReport(
        goal_id=snapshot.goal_id,
        passed=not blocking,
        summary=(
            f"Found {len(issues)} issue(s): "
            f"{len(blocking)} blocking, "
            f"{len([issue for issue in issues if issue.severity == 'p1'])} important, "
            f"{len([issue for issue in issues if issue.severity == 'p2'])} advisory."
        ),
        issues=issues,
        user_questions=user_questions,
        agent_actions=agent_actions,
    )


def render_issue_report(report: GoalIssueReport) -> str:
    lines = [
        "# Goal Issue Report",
        "",
        f"Goal: {report.goal_id}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        "",
        report.summary,
        "",
        "## Needs The User",
        _bullets(report.user_questions or ["No important user decision is waiting."]),
        "",
        "## Agent Can Work On",
        _bullets(report.agent_actions or ["No agent-side actions are currently suggested."]),
        "",
        "## Issues",
    ]
    if not report.issues:
        lines.append("- No issues found.")
    for issue in report.issues:
        user = " user" if issue.needs_user else ""
        lines.append(f"- [{issue.severity.upper()}][{issue.area}{user}] {issue.summary}")
        if issue.detail:
            lines.append(f"  Detail: {issue.detail}")
        if issue.suggested_action:
            lines.append(f"  Next: {issue.suggested_action}")
    return "\n".join(lines) + "\n"


def _state_issues(snapshot: GoalSnapshot) -> list[GoalIssue]:
    issues: list[GoalIssue] = []
    accepted = [phase for phase in snapshot.phases if phase.status == PhaseStatus.ACCEPTED]
    if snapshot.status == GoalStatus.COMPLETE and len(accepted) != len(snapshot.phases):
        issues.append(
            GoalIssue(
                severity="p0",
                area="state",
                summary="Goal is marked complete before every phase is accepted.",
                suggested_action="Run `goals repair`, inspect events, and accept only reviewed phases.",
            )
        )
    if snapshot.status == GoalStatus.ACTIVE and snapshot.current_phase is None:
        issues.append(
            GoalIssue(
                severity="p0",
                area="state",
                summary="Goal is active but has no current phase.",
                suggested_action="Run `goals repair` or inspect the event log before continuing.",
            )
        )
    if not snapshot.definition_of_done:
        issues.append(
            GoalIssue(
                severity="p2",
                area="state",
                summary="Definition of done is missing.",
                suggested_action="Record a plain-language definition of done before closing the goal.",
            )
        )
    for blocker in snapshot.blockers:
        issues.append(
            GoalIssue(
                severity="p0",
                area="state",
                summary=f"Blocker recorded: {blocker}",
                suggested_action="Resolve the blocker or record why the goal can continue safely.",
            )
        )
    return issues


def _phase_issues(snapshot: GoalSnapshot) -> list[GoalIssue]:
    issues: list[GoalIssue] = []
    current_phase = snapshot.current_phase
    for phase in snapshot.phases:
        refs = [f"phase:{phase.phase_id}"]
        issues.extend(_checkpoint_issues(phase.phase_id, phase.checkpoints, refs))
        if phase.status == PhaseStatus.ACCEPTED:
            if not phase.reviews or phase.reviews[-1].verdict != GateVerdict.PASS:
                issues.append(
                    GoalIssue(
                        severity="p0",
                        area="gate",
                        summary=f"{phase.phase_id} is accepted without a passing latest review.",
                        suggested_action=f"Run `goals phase review {phase.phase_id}` before accepting this phase.",
                        evidence_refs=refs,
                    )
                )
            continue
        if phase.phase_id == current_phase and phase.evidence is None:
            issues.append(
                GoalIssue(
                    severity="p1",
                    area="evidence",
                    summary=f"{phase.phase_id} has no evidence yet.",
                    suggested_action=f"Create evidence and run `goals phase evidence {phase.phase_id} --file ...`.",
                    evidence_refs=refs,
                )
            )
        if phase.evidence is not None:
            issues.extend(_evidence_issues(phase.phase_id, phase.evidence, refs))
            synthetic_review = review_phase(phase)
            if synthetic_review.verdict != GateVerdict.PASS and not phase.reviews:
                issues.append(
                    GoalIssue(
                        severity="p1",
                        area="gate",
                        summary=f"{phase.phase_id} is not ready for review.",
                        detail=synthetic_review.summary,
                        suggested_action=f"Fix evidence gaps before running `goals phase review {phase.phase_id}`.",
                        evidence_refs=refs,
                    )
                )
        if phase.status == PhaseStatus.NEEDS_REVIEW and not phase.reviews:
            issues.append(
                GoalIssue(
                    severity="p1",
                    area="gate",
                    summary=f"{phase.phase_id} has evidence but no review.",
                    suggested_action=f"Run `goals phase review {phase.phase_id}`.",
                    evidence_refs=refs,
                )
            )
        if phase.reviews:
            latest = phase.reviews[-1]
            category = representative_category(latest.findings)
            if latest.verdict in {GateVerdict.BLOCKED, GateVerdict.NEEDS_HUMAN, GateVerdict.UNSAFE}:
                # Escalation case (cap reached or human gate): keep the "ask for help"
                # action, but still carry the rubric tag.
                issues.append(
                    GoalIssue(
                        severity="p0",
                        area="gate",
                        summary=f"{phase.phase_id} latest review is {latest.verdict}.",
                        detail=latest.summary,
                        suggested_action="Change approach or ask for help before accepting the phase.",
                        needs_user=latest.verdict in {GateVerdict.NEEDS_HUMAN, GateVerdict.UNSAFE},
                        evidence_refs=refs,
                        category=category,
                    )
                )
            elif latest.verdict == GateVerdict.FAIL:
                issues.append(
                    GoalIssue(
                        severity="p1",
                        area="gate",
                        summary=f"{phase.phase_id} latest review failed.",
                        detail=latest.summary,
                        suggested_action=_GATE_CATEGORY_ACTION.get(
                            category, "Fix review findings and rerun the phase review."
                        ),
                        evidence_refs=refs,
                        category=category,
                    )
                )
    return issues


def _checkpoint_issues(phase_id: str, checkpoints, refs: list[str]) -> list[GoalIssue]:
    issues: list[GoalIssue] = []
    for checkpoint in checkpoints:
        if not checkpoint.required:
            continue
        if checkpoint.status in {CheckpointStatus.PASSED, CheckpointStatus.WAIVED}:
            continue
        needs_user = checkpoint.needs_user or checkpoint.status == CheckpointStatus.NEEDS_USER
        label = checkpoint.title or checkpoint.checkpoint_id
        issues.append(
            GoalIssue(
                severity="p0",
                area="checkpoint",
                summary=f"{phase_id} checkpoint is not complete: {label}.",
                detail=checkpoint.summary
                or "A required checkpoint must pass or be waived before this phase can be accepted.",
                suggested_action=(
                    f"Ask the user to answer checkpoint {checkpoint.checkpoint_id}: {label}."
                    if needs_user
                    else f"Complete or waive checkpoint {checkpoint.checkpoint_id} before review."
                ),
                needs_user=needs_user,
                evidence_refs=[*refs, *checkpoint.evidence_refs],
            )
        )
    return issues


def _evidence_issues(phase_id: str, evidence, refs: list[str]) -> list[GoalIssue]:
    issues: list[GoalIssue] = []
    if evidence.acceptance_not_met:
        issues.append(
            GoalIssue(
                severity="p1",
                area="evidence",
                summary=f"{phase_id} has unmet acceptance criteria.",
                detail=", ".join(evidence.acceptance_not_met),
                suggested_action="Complete or explicitly defer unmet acceptance criteria.",
                evidence_refs=refs,
            )
        )
    if evidence.ambiguous:
        issues.append(
            GoalIssue(
                severity="p1",
                area="evidence",
                summary=f"{phase_id} has ambiguous acceptance criteria.",
                detail=", ".join(evidence.ambiguous),
                suggested_action="Resolve ambiguity with a reversible assumption or a user decision.",
                evidence_refs=refs,
            )
        )
    if not evidence.checks_run:
        issues.append(
            GoalIssue(
                severity="p1",
                area="evidence",
                summary=f"{phase_id} has no checks recorded.",
                suggested_action="Run the relevant checks and record them as phase evidence.",
                evidence_refs=refs,
            )
        )
    if evidence.confidence < 0.7:
        issues.append(
            GoalIssue(
                severity="p2",
                area="evidence",
                summary=f"{phase_id} evidence confidence is below 0.7.",
                detail=f"confidence={evidence.confidence:.0%}",
                suggested_action="Add proof or record the known gap before accepting this phase.",
                evidence_refs=refs,
            )
        )
    return issues


def _decision_issues(snapshot: GoalSnapshot) -> list[GoalIssue]:
    issues: list[GoalIssue] = []
    for decision in snapshot.decisions:
        surfaced, reason = should_surface_decision(decision)
        if surfaced:
            issues.append(
                GoalIssue(
                    severity="p0" if decision.priority == "blocking" else "p1",
                    area="decision",
                    summary=decision.plain_summary,
                    detail=reason,
                    suggested_action=decision.suggested_reply
                    or f"I choose: {decision.recommendation}",
                    needs_user=True,
                    evidence_refs=decision.evidence_refs,
                )
            )
    return issues


def _source_issues(snapshot: GoalSnapshot) -> list[GoalIssue]:
    issues = [
        GoalIssue(
            severity="p1",
            area="source",
            summary=f"Source-backed claim is unresolved: {claim.claim}",
            detail="The claim has no source or references a missing source.",
            suggested_action="Record the source or lower confidence before relying on this claim.",
            evidence_refs=[f"source:{source_id}" for source_id in claim.source_ids],
        )
        for claim in unresolved_claims(snapshot)
    ]
    for claim in snapshot.source_claims:
        if claim.confidence < 0.5:
            issues.append(
                GoalIssue(
                    severity="p2",
                    area="source",
                    summary=f"Source-backed claim has low confidence: {claim.claim}",
                    detail=f"confidence={claim.confidence:.0%}",
                    suggested_action="Find stronger evidence or mark the claim as uncertain.",
                    evidence_refs=[f"source:{source_id}" for source_id in claim.source_ids],
                )
            )
    freshness = analyze_source_freshness(snapshot)
    for finding in freshness.findings:
        issues.append(
            GoalIssue(
                severity=finding.severity,
                area="source",
                summary=finding.summary,
                detail=finding.detail,
                suggested_action=finding.suggested_action,
                needs_user=finding.needs_user,
                evidence_refs=finding.evidence_refs,
            )
        )
    return issues


def _risk_issues(snapshot: GoalSnapshot) -> list[GoalIssue]:
    return [
        GoalIssue(
            severity="p1",
            area="risk",
            summary=f"Risk recorded: {risk}",
            suggested_action="Mitigate, accept, or convert this risk into a clear decision.",
        )
        for risk in snapshot.risks
    ]


def _architecture_issues(snapshot: GoalSnapshot) -> list[GoalIssue]:
    issues = [
        GoalIssue(
            severity="p2",
            area="architecture",
            summary=f"Architecture question remains: {question}",
            suggested_action="Answer or explicitly defer this architecture question.",
        )
        for question in (snapshot.architecture.questions if snapshot.architecture else [])
    ]
    report = analyze_code_architecture(snapshot, Path(snapshot.topology.worktree_path))
    issues.extend(
        GoalIssue(
            severity=finding.severity,
            area="architecture",
            summary=finding.summary,
            detail=finding.detail,
            suggested_action=finding.suggested_action,
            needs_user=finding.needs_user,
            evidence_refs=finding.evidence_refs,
        )
        for finding in report.findings
    )
    return issues


def _merge_readiness_issues(snapshot: GoalSnapshot) -> list[GoalIssue]:
    report = analyze_merge_readiness(snapshot)
    return [
        GoalIssue(
            severity=finding.severity,
            area="merge",
            summary=finding.summary,
            detail=finding.detail,
            suggested_action=finding.suggested_action,
            needs_user=finding.needs_user,
            evidence_refs=finding.evidence_refs,
        )
        for finding in report.findings
    ]


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique
