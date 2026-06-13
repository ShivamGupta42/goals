from __future__ import annotations

from collections import Counter

from goals.models import (
    GoalSnapshot,
    HandoffOwner,
    HandoffOwnerFinding,
    HandoffOwnerReport,
)


def analyze_handoff_owners(snapshot: GoalSnapshot) -> HandoffOwnerReport:
    owners = snapshot.handoff_owners
    phase_ids = {phase.phase_id for phase in snapshot.phases}
    findings: list[HandoffOwnerFinding] = []

    label_counts = Counter(_normalized(owner.label) for owner in owners)
    for owner in owners:
        refs = [f"handoff:{owner.owner_id}"]
        if not owner.role:
            findings.append(
                _finding(
                    owner,
                    "p2",
                    "Handoff owner is missing a role.",
                    "Add the plain role this owner plays before relying on the handoff.",
                    refs,
                )
            )
        if not owner.responsibility:
            findings.append(
                _finding(
                    owner,
                    "p1",
                    "Handoff owner is missing a responsibility.",
                    "Record the specific work this owner is accountable for.",
                    refs,
                )
            )
        missing_phases = [phase_id for phase_id in owner.phase_ids if phase_id not in phase_ids]
        if missing_phases:
            findings.append(
                _finding(
                    owner,
                    "p1",
                    "Handoff owner references unknown phases.",
                    "Remove stale phase ids or update the goal phases before review.",
                    [*refs, *(f"phase:{phase_id}" for phase_id in missing_phases)],
                    detail=", ".join(missing_phases),
                )
            )
        if owner.status == "blocked":
            findings.append(
                _finding(
                    owner,
                    "p0",
                    "Handoff owner is blocked.",
                    "Ask the user who should own this work next, or record a replacement owner.",
                    refs,
                    needs_user=True,
                )
            )
        if owner.confirmation == "needs_user":
            findings.append(
                _finding(
                    owner,
                    "p1",
                    "Handoff owner needs user confirmation.",
                    "Ask the user to confirm this owner or choose a safer default.",
                    refs,
                    needs_user=True,
                )
            )
        if label_counts[_normalized(owner.label)] > 1:
            findings.append(
                _finding(
                    owner,
                    "p2",
                    "Handoff owner label is duplicated.",
                    "Clarify duplicate owner labels so the dashboard is unambiguous.",
                    refs,
                )
            )
        if owner.owner_type in {"team", "external"} and not owner.escalation_path:
            findings.append(
                _finding(
                    owner,
                    "p2",
                    "Handoff owner has no escalation path.",
                    "Record where the agent should route blockers before interrupting the user.",
                    refs,
                )
            )

    blocking = [finding for finding in findings if finding.severity in {"p0", "p1"}]
    return HandoffOwnerReport(
        goal_id=snapshot.goal_id,
        passed=not blocking,
        owners_checked=len(owners),
        summary=_summary(owners, findings),
        findings=findings,
        user_questions=[finding.summary for finding in findings if finding.needs_user],
        agent_actions=_unique(
            [
                finding.suggested_action
                for finding in findings
                if finding.suggested_action and not finding.needs_user
            ]
        ),
    )


def render_handoff_summary(snapshot: GoalSnapshot) -> str:
    if not snapshot.handoff_owners:
        return "- No handoff owners recorded yet."
    return "\n".join(_owner_line(owner) for owner in snapshot.handoff_owners[:8])


def render_handoff_owner_report(report: HandoffOwnerReport) -> str:
    lines = [
        "# Handoff Owner Report",
        "",
        f"Goal: {report.goal_id}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        "",
        report.summary,
        "",
        "## Needs The User",
        _bullets(report.user_questions or ["No handoff decision is waiting on the user."]),
        "",
        "## Agent Can Work On",
        _bullets(report.agent_actions or ["No handoff cleanup is currently suggested."]),
        "",
        "## Findings",
    ]
    if not report.findings:
        lines.append("- No handoff owner issues found.")
    for finding in report.findings:
        marker = " user" if finding.needs_user else ""
        lines.append(
            f"- [{finding.severity.upper()}{marker}] {finding.owner_id}: {finding.summary}"
        )
        if finding.detail:
            lines.append(f"  Detail: {finding.detail}")
        if finding.suggested_action:
            lines.append(f"  Next: {finding.suggested_action}")
    return "\n".join(lines) + "\n"


def _summary(owners: list[HandoffOwner], findings: list[HandoffOwnerFinding]) -> str:
    if not owners:
        return "No handoff owners are recorded yet. This is fine until a phase changes ownership, review responsibility, or follow-up accountability."
    p0 = len([finding for finding in findings if finding.severity == "p0"])
    p1 = len([finding for finding in findings if finding.severity == "p1"])
    p2 = len([finding for finding in findings if finding.severity == "p2"])
    active = len([owner for owner in owners if owner.status == "active"])
    return (
        f"Checked {len(owners)} handoff owner(s): {active} active, "
        f"{p0} blocked, {p1} important, {p2} advisory issue(s)."
    )


def _finding(
    owner: HandoffOwner,
    severity: str,
    summary: str,
    suggested_action: str,
    refs: list[str],
    *,
    detail: str = "",
    needs_user: bool = False,
) -> HandoffOwnerFinding:
    return HandoffOwnerFinding(
        severity=severity,  # type: ignore[arg-type]
        owner_id=owner.owner_id,
        label=owner.label,
        summary=f"{summary.rstrip('.')}: {owner.label}",
        detail=detail,
        suggested_action=suggested_action,
        needs_user=needs_user,
        evidence_refs=refs,
    )


def _owner_line(owner: HandoffOwner) -> str:
    phases = f", phases={', '.join(owner.phase_ids)}" if owner.phase_ids else ""
    scope = f", scope={', '.join(owner.decision_scope)}" if owner.decision_scope else ""
    return (
        f"- {owner.owner_id}: {owner.label} "
        f"({owner.owner_type}, {owner.status}, confirmation={owner.confirmation}{phases}{scope})"
    )


def _normalized(value: str) -> str:
    return " ".join(value.lower().split())


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
