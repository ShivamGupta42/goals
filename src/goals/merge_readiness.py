from __future__ import annotations

import re

from goals.decisions import should_surface_decision
from goals.models import (
    Evidence,
    GoalSnapshot,
    MergeReadinessFinding,
    MergeReadinessReport,
)

MIGRATION_PROOF_PATTERNS = [
    "migration order",
    "migration ordering",
    "migration numbering",
    "migration sequence",
    "migration status",
    "schema migration check",
    "alembic heads",
    "alembic current",
    "single head",
    "django showmigrations",
    "rails db:migrate:status",
    "prisma migrate status",
]

MERGE_COORDINATION_PATTERNS = [
    "merge readiness",
    "merge rehearsal",
    "merge conflict",
    "conflict check",
    "integration branch",
    "parallel worktree",
    "worktree reconciliation",
    "base branch synced",
    "rebased on main",
    "main synced",
]

MERGE_RISK_PATTERNS = [
    "branch drift",
    "base branch moved",
    "behind main",
    "merge conflict",
    "merge conflicts",
    "parallel worktree",
    "parallel branch",
    "rebase needed",
    "schema conflict",
]

USER_DECISION_PATTERNS = [
    "approval",
    "permission",
    "user decision",
    "production data",
    "irreversible",
    "destructive",
    "breaking api",
    "breaking change",
]


def analyze_merge_readiness(snapshot: GoalSnapshot) -> MergeReadinessReport:
    """Inspect a goal snapshot for coordination risks before merge."""

    findings: list[MergeReadinessFinding] = []
    findings.extend(_migration_findings(snapshot))
    findings.extend(_parallel_findings(snapshot))
    findings.extend(_merge_risk_findings(snapshot))
    findings.extend(_architecture_findings(snapshot))
    blocking = [finding for finding in findings if finding.severity == "p0"]
    user_questions = [finding.summary for finding in findings if finding.needs_user]
    agent_actions = [
        finding.suggested_action
        for finding in findings
        if finding.suggested_action and not finding.needs_user
    ]
    return MergeReadinessReport(
        goal_id=snapshot.goal_id,
        passed=not blocking,
        summary=(
            f"Found {len(findings)} merge-readiness finding(s): "
            f"{len(blocking)} blocking, "
            f"{len([finding for finding in findings if finding.severity == 'p1'])} important, "
            f"{len([finding for finding in findings if finding.severity == 'p2'])} advisory."
        ),
        findings=findings,
        user_questions=user_questions,
        agent_actions=agent_actions,
    )


def render_merge_readiness_report(report: MergeReadinessReport) -> str:
    lines = [
        "# Goal Merge Readiness Report",
        "",
        f"Goal: {report.goal_id}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        "",
        report.summary,
        "",
        "## Needs The User",
        _bullets(report.user_questions or ["No merge decision is waiting on the user."]),
        "",
        "## Agent Can Work On",
        _bullets(report.agent_actions or ["No merge-specific agent action is suggested."]),
        "",
        "## Findings",
    ]
    if not report.findings:
        lines.append("- No merge-readiness findings.")
    for finding in report.findings:
        user = " user" if finding.needs_user else ""
        lines.append(f"- [{finding.severity.upper()}][{finding.area}{user}] {finding.summary}")
        if finding.detail:
            lines.append(f"  Detail: {finding.detail}")
        if finding.suggested_action:
            lines.append(f"  Next: {finding.suggested_action}")
    return "\n".join(lines) + "\n"


def _migration_findings(snapshot: GoalSnapshot) -> list[MergeReadinessFinding]:
    changed = _migration_changes(snapshot)
    if not changed:
        return []
    if _has_migration_order_proof(snapshot):
        return []
    refs = sorted({f"phase:{phase_id}" for phase_id, _ in changed})
    files = ", ".join(path for _, path in changed[:6])
    more = "" if len(changed) <= 6 else f" and {len(changed) - 6} more"
    return [
        MergeReadinessFinding(
            severity="p1",
            area="migration",
            summary="Migration files changed without recorded ordering proof.",
            detail=f"Changed migration-like files: {files}{more}.",
            suggested_action=(
                "Run the repo's migration-order or migration-status check, reconcile numbering "
                "against the target branch, and record the command in phase evidence before merge."
            ),
            evidence_refs=refs,
        )
    ]


def _parallel_findings(snapshot: GoalSnapshot) -> list[MergeReadinessFinding]:
    if snapshot.topology.mode == "single":
        return []
    if _has_merge_coordination_proof(snapshot):
        return []
    return [
        MergeReadinessFinding(
            severity="p1",
            area="parallel",
            summary=f"{snapshot.topology.mode} worktree mode lacks merge coordination proof.",
            detail=(
                "The goal topology allows parallel work, but no evidence mentions conflict checks, "
                "base-branch sync, integration branch review, or worktree reconciliation."
            ),
            suggested_action=(
                "Run a coordinator merge-readiness pass across active worktrees, record conflicts "
                "or base drift, and update evidence before merging."
            ),
        )
    ]


def _merge_risk_findings(snapshot: GoalSnapshot) -> list[MergeReadinessFinding]:
    findings: list[MergeReadinessFinding] = []
    for source, text in _merge_sensitive_text(snapshot):
        lowered = text.lower()
        if not _contains_any(lowered, MERGE_RISK_PATTERNS + USER_DECISION_PATTERNS):
            continue
        needs_user = _contains_any(lowered, USER_DECISION_PATTERNS) and not _covered_by_decision(
            snapshot, lowered
        )
        severity = "p0" if needs_user else "p1"
        findings.append(
            MergeReadinessFinding(
                severity=severity,
                area="decision" if needs_user else "branch",
                summary=(
                    "Merge risk may need user approval."
                    if needs_user
                    else "Merge-sensitive risk needs coordinator follow-up."
                ),
                detail=f"{source}: {text}",
                suggested_action=(
                    "Ask the user for the high-risk merge decision in plain language."
                    if needs_user
                    else "Resolve or record the merge risk before accepting the goal as merge-ready."
                ),
                needs_user=needs_user,
            )
        )
    return _dedupe_findings(findings)


def _architecture_findings(snapshot: GoalSnapshot) -> list[MergeReadinessFinding]:
    if snapshot.architecture is None:
        return []
    findings = []
    for question in snapshot.architecture.questions:
        lowered = question.lower()
        if _contains_any(lowered, ["merge", "migration", "parallel", "worktree"]):
            findings.append(
                MergeReadinessFinding(
                    severity="p2",
                    area="architecture",
                    summary=f"Architecture question affects merge readiness: {question}",
                    suggested_action=(
                        "Answer, defer, or record why this architecture question does not block merge."
                    ),
                )
            )
    return findings


def _migration_changes(snapshot: GoalSnapshot) -> list[tuple[str, str]]:
    changed: list[tuple[str, str]] = []
    for phase in snapshot.phases:
        if phase.evidence is None:
            continue
        for path in phase.evidence.changed_files:
            if _is_migration_path(path):
                changed.append((phase.phase_id, path))
    return changed


def _has_migration_order_proof(snapshot: GoalSnapshot) -> bool:
    return any(
        _contains_any(_evidence_text(phase.evidence), MIGRATION_PROOF_PATTERNS)
        for phase in snapshot.phases
        if phase.evidence is not None
    )


def _has_merge_coordination_proof(snapshot: GoalSnapshot) -> bool:
    return any(
        _contains_any(_evidence_text(phase.evidence), MERGE_COORDINATION_PATTERNS)
        for phase in snapshot.phases
        if phase.evidence is not None
    )


def _merge_sensitive_text(snapshot: GoalSnapshot) -> list[tuple[str, str]]:
    items = [(f"risk:{index + 1}", risk) for index, risk in enumerate(snapshot.risks)]
    items.extend(
        (f"blocker:{index + 1}", blocker) for index, blocker in enumerate(snapshot.blockers)
    )
    for phase in snapshot.phases:
        evidence = phase.evidence
        if evidence is None:
            continue
        for item in evidence.ambiguous + evidence.known_gaps + evidence.acceptance_not_met:
            items.append((f"phase:{phase.phase_id}", item))
    return items


def _covered_by_decision(snapshot: GoalSnapshot, risk_text: str) -> bool:
    risk_terms = {
        term
        for term in ["migration", "production", "data", "destructive", "breaking", "api"]
        if term in risk_text
    }
    for decision in snapshot.decisions:
        surfaced, _ = should_surface_decision(decision)
        if not surfaced:
            continue
        decision_text = " ".join(
            [
                decision.title,
                decision.plain_summary,
                decision.why_it_matters,
                decision.recommendation,
                decision.technical_details,
            ]
        ).lower()
        if risk_terms and any(term in decision_text for term in risk_terms):
            return True
    return False


def _is_migration_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lower()
    name = normalized.rsplit("/", 1)[-1]
    if "/migrations/" in f"/{normalized}":
        return True
    if "/alembic/versions/" in f"/{normalized}":
        return True
    if re.search(r"/versions/[0-9a-f]+[_-].+\.(py|sql)$", f"/{normalized}"):
        return True
    return "migration" in name and name.endswith((".py", ".sql", ".rb", ".js", ".ts"))


def _evidence_text(evidence: Evidence | None) -> str:
    if evidence is None:
        return ""
    return " ".join(
        [
            *evidence.changed_files,
            *evidence.checks_run,
            *evidence.acceptance_met,
            *evidence.acceptance_not_met,
            *evidence.ambiguous,
            *evidence.known_gaps,
            evidence.notes,
        ]
    ).lower()


def _contains_any(text: str, patterns: list[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _dedupe_findings(findings: list[MergeReadinessFinding]) -> list[MergeReadinessFinding]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[MergeReadinessFinding] = []
    for finding in findings:
        key = (finding.severity, finding.area, finding.detail)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(finding)
    return deduped


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
