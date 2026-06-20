from __future__ import annotations

from pathlib import Path
import re

from goals.decisions import should_surface_decision
from goals.git_ops import list_worktrees, run_git
from goals.models import (
    Evidence,
    GoalSnapshot,
    MergeReadinessFinding,
    MergeReadinessReport,
    ParallelMergeScan,
    ParallelWorktreeInfo,
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
    parallel_scan = _parallel_merge_scan(snapshot)
    findings.extend(_migration_findings(snapshot))
    findings.extend(_parallel_findings(snapshot, parallel_scan))
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
        parallel_scan=parallel_scan,
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
    if report.parallel_scan is not None:
        lines.extend(
            [
                "",
                "## Parallel Worktree Scan",
                "",
                f"Base branch: {report.parallel_scan.base_branch}",
                f"Active branch: {report.parallel_scan.active_branch}",
                "Sibling worktrees:",
                _bullets(
                    [
                        (
                            f"{item.label} ({item.branch}): "
                            f"{len(item.changed_files)} changed file(s), "
                            f"{'dirty' if item.dirty else 'clean'}, "
                            f"behind base by {item.behind_base}"
                        )
                        for item in report.parallel_scan.sibling_worktrees
                    ]
                    or ["No sibling worktrees with merge-relevant changes."],
                ),
                "Overlaps:",
                _bullets(report.parallel_scan.overlapping_files or ["No file overlap detected."]),
            ]
        )
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


def _parallel_findings(
    snapshot: GoalSnapshot,
    scan: ParallelMergeScan | None,
) -> list[MergeReadinessFinding]:
    findings = _parallel_scan_findings(scan)
    if findings:
        return findings
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


def _parallel_scan_findings(scan: ParallelMergeScan | None) -> list[MergeReadinessFinding]:
    if scan is None or not scan.sibling_worktrees:
        return []
    findings: list[MergeReadinessFinding] = []
    dirty = [item for item in scan.sibling_worktrees if item.dirty]
    if dirty:
        labels = ", ".join(_worktree_ref(item) for item in dirty[:5])
        more = "" if len(dirty) <= 5 else f" and {len(dirty) - 5} more"
        findings.append(
            MergeReadinessFinding(
                severity="p1",
                area="parallel",
                summary="Parallel worktree has uncommitted changes before merge.",
                detail=f"Dirty sibling worktrees: {labels}{more}.",
                suggested_action=(
                    "Ask worker agents to commit, stash, or discard local changes before the "
                    "coordinator attempts a merge rehearsal."
                ),
            )
        )
    drifted = [
        item for item in scan.sibling_worktrees if item.behind_base > 0 or item.ahead_base > 0
    ]
    active_drift = scan.active_changed_files and any(item.behind_base > 0 for item in drifted)
    if drifted or active_drift:
        labels = ", ".join(
            f"{_worktree_ref(item)} behind={item.behind_base} ahead={item.ahead_base}"
            for item in drifted[:5]
        )
        findings.append(
            MergeReadinessFinding(
                severity="p1",
                area="branch",
                summary="Parallel worktree branches need coordinator sync proof.",
                detail=labels or "Active branch has merge-relevant changes without sync proof.",
                suggested_action=(
                    "Fetch the target branch, rebase or merge each active worktree as needed, "
                    "and record the merge rehearsal result before asking the user."
                ),
            )
        )
    if scan.overlapping_files:
        files = ", ".join(scan.overlapping_files[:8])
        more = (
            ""
            if len(scan.overlapping_files) <= 8
            else f" and {len(scan.overlapping_files) - 8} more"
        )
        findings.append(
            MergeReadinessFinding(
                severity="p1",
                area="parallel",
                summary="Parallel worktrees touch the same files.",
                detail=f"Overlapping files: {files}{more}.",
                suggested_action=(
                    "Run a merge rehearsal or integration branch for the overlapping files and "
                    "record the resolved owner before merge."
                ),
            )
        )
    if scan.overlapping_migrations:
        files = ", ".join(scan.overlapping_migrations[:8])
        findings.append(
            MergeReadinessFinding(
                severity="p1",
                area="migration",
                summary="Parallel worktrees include overlapping migration changes.",
                detail=f"Migration-like overlap: {files}.",
                suggested_action=(
                    "Reconcile migration numbering against the target branch and other worktrees, "
                    "then record the migration-order proof before merge."
                ),
            )
        )
    return _dedupe_findings(findings)


def _parallel_merge_scan(snapshot: GoalSnapshot) -> ParallelMergeScan | None:
    base_repo = Path(snapshot.topology.base_repo)
    active_path = Path(snapshot.topology.worktree_path)
    worktrees = _git_worktrees(base_repo)
    if len(worktrees) <= 1:
        return None
    base_branch = snapshot.topology.base_branch
    active_changed = sorted(
        set(_snapshot_changed_files(snapshot))
        | set(_changed_files_since_base(active_path, base_branch))
    )
    active_migrations = sorted(path for path in active_changed if _is_migration_path(path))
    active_branch = snapshot.topology.branch
    sibling_infos: list[ParallelWorktreeInfo] = []
    active_resolved = _safe_resolve(active_path)
    for worktree in worktrees:
        path = worktree["path"]
        if not isinstance(path, Path):
            path = Path(str(path))
        if _safe_resolve(path) == active_resolved:
            continue
        branch = str(worktree["branch"])
        if branch == base_branch:
            continue
        changed = _changed_files_since_base(path, base_branch)
        dirty = _is_dirty(path)
        if not changed and not dirty:
            continue
        ahead, behind = _ahead_behind_base(path, base_branch)
        migrations = sorted(item for item in changed if _is_migration_path(item))
        sibling_infos.append(
            ParallelWorktreeInfo(
                label=path.name,
                branch=branch,
                head=str(worktree["head"]),
                dirty=dirty,
                changed_files=changed,
                migration_files=migrations,
                ahead_base=ahead,
                behind_base=behind,
            )
        )
    if not sibling_infos:
        return None
    sibling_changed = {path for item in sibling_infos for path in item.changed_files}
    sibling_migrations = {path for item in sibling_infos for path in item.migration_files}
    overlapping_migrations = (
        sorted(set(active_migrations) | sibling_migrations)
        if active_migrations and sibling_migrations
        else []
    )
    return ParallelMergeScan(
        base_branch=base_branch,
        active_branch=active_branch,
        active_changed_files=active_changed,
        active_migration_files=active_migrations,
        sibling_worktrees=sibling_infos,
        overlapping_files=sorted(set(active_changed) & sibling_changed),
        overlapping_migrations=overlapping_migrations,
    )


def _merge_risk_findings(snapshot: GoalSnapshot) -> list[MergeReadinessFinding]:
    findings: list[MergeReadinessFinding] = []
    for source, text in _merge_sensitive_text(snapshot):
        lowered = text.lower()
        if not _contains_any(lowered, MERGE_RISK_PATTERNS + USER_DECISION_PATTERNS):
            continue
        risk_status, decision_refs = _risk_status(snapshot, source, lowered)
        if risk_status in {
            "accepted-risk",
            "intentional-scope-limit",
            "production-follow-up",
        }:
            continue
        needs_user = _contains_any(lowered, USER_DECISION_PATTERNS) and not decision_refs
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
                risk_status="blocker" if needs_user else risk_status,
                decision_refs=decision_refs,
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


def _snapshot_changed_files(snapshot: GoalSnapshot) -> list[str]:
    changed: list[str] = []
    for phase in snapshot.phases:
        if phase.evidence is None:
            continue
        changed.extend(phase.evidence.changed_files)
    return changed


def _has_migration_order_proof(snapshot: GoalSnapshot) -> bool:
    return any(
        _contains_any(_evidence_positive_text(phase.evidence), MIGRATION_PROOF_PATTERNS)
        for phase in snapshot.phases
        if phase.evidence is not None
    )


def _has_merge_coordination_proof(snapshot: GoalSnapshot) -> bool:
    return any(
        _contains_any(_evidence_positive_text(phase.evidence), MERGE_COORDINATION_PATTERNS)
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


def _risk_status(snapshot: GoalSnapshot, source: str, risk_text: str) -> tuple[str, list[str]]:
    refs = _covering_judgement_refs(snapshot, source, risk_text)
    if refs:
        if _contains_any(risk_text, ["simulation", "simulated", "out of scope", "scope limit"]):
            return "intentional-scope-limit", refs
        if _contains_any(risk_text, ["production follow-up", "production followup", "later production"]):
            return "production-follow-up", refs
        return "accepted-risk", refs
    return "unknown", []


def _covering_judgement_refs(snapshot: GoalSnapshot, source: str, risk_text: str) -> list[str]:
    risk_terms = {
        term
        for term in ["migration", "production", "data", "destructive", "breaking", "api"]
        if term in risk_text
    }
    refs: list[str] = []
    for judgement in snapshot.judgements:
        if source in judgement.evidence_refs:
            refs.append(judgement.judgement_id)
            continue
        judgement_text = " ".join(
            [judgement.question, judgement.choice, judgement.rationale, *judgement.evidence_refs]
        ).lower()
        if risk_terms and any(term in judgement_text for term in risk_terms):
            refs.append(judgement.judgement_id)
    if refs:
        return sorted(set(refs))
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
            refs.append(decision.decision_id)
    return sorted(set(refs))


def _git_worktrees(repo: Path) -> list[dict[str, str | Path]]:
    # Enumeration lives in git_ops.list_worktrees (single source of truth); this
    # only applies merge-readiness's normalization on top.
    return [_normalize_worktree_record(record) for record in list_worktrees(repo)]


def _normalize_worktree_record(record: dict[str, str | Path]) -> dict[str, str | Path]:
    path = record.get("path")
    if not isinstance(path, Path):
        path = Path(str(path or ""))
    branch = str(record.get("branch") or "(unknown)")
    return {
        "path": path,
        "branch": branch,
        "head": str(record.get("head") or ""),
    }


def _changed_files_since_base(worktree: Path, base_branch: str) -> list[str]:
    candidates = [base_branch, f"origin/{base_branch}"]
    for candidate in candidates:
        result = run_git(["diff", "--name-only", f"{candidate}...HEAD"], worktree, check=False)
        if result.returncode == 0:
            return sorted(line for line in result.stdout.splitlines() if line)
    result = run_git(["diff", "--name-only", "HEAD"], worktree, check=False)
    if result.returncode == 0:
        return sorted(line for line in result.stdout.splitlines() if line)
    return []


def _is_dirty(worktree: Path) -> bool:
    result = run_git(["status", "--porcelain"], worktree, check=False)
    return result.returncode == 0 and bool(result.stdout.strip())


def _ahead_behind_base(worktree: Path, base_branch: str) -> tuple[int, int]:
    candidates = [base_branch, f"origin/{base_branch}"]
    for candidate in candidates:
        result = run_git(
            ["rev-list", "--left-right", "--count", f"{candidate}...HEAD"],
            worktree,
            check=False,
        )
        if result.returncode != 0:
            continue
        left, _, right = result.stdout.strip().partition("\t")
        if not right:
            left, _, right = result.stdout.strip().partition(" ")
        try:
            behind = int(left)
            ahead = int(right)
        except ValueError:
            return (0, 0)
        return (ahead, behind)
    return (0, 0)


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def _worktree_ref(item: ParallelWorktreeInfo) -> str:
    return f"{item.label} ({item.branch})"


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


def _evidence_positive_text(evidence: Evidence | None) -> str:
    if evidence is None:
        return ""
    return " ".join([*evidence.checks_run, *evidence.acceptance_met]).lower()


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
