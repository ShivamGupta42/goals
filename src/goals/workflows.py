from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from goals.health import GoalHealthReport, build_goal_health
from goals.loop_builder import load_design, profile_root_for_loop_path, to_snapshot
from goals.mode_a import ModeAAdapter, build_mode_a_plan
from goals.projections import emit_dashboard, export_goal, refresh_goal_outputs
from goals.storage import GoalsError
from goals.models import (
    ArchitectureCheckReport,
    CapabilityCheckReport,
    CurrentCheckpointBrief,
    GoalBrief,
    GoalIssueReport,
    GoalSnapshot,
    GoalStatus,
    MergeReadinessReport,
    ModeAPlan,
    PhaseStatus,
    PortableExport,
)
from goals.runtime import claim_worktree, create_goal, load_active_snapshot
from goals.user_memory import build_goal_memory_digest


@dataclass(frozen=True)
class WorkflowStart:
    snapshot: GoalSnapshot
    plan: ModeAPlan
    dashboard_path: Path


@dataclass(frozen=True)
class WorkflowNext:
    snapshot: GoalSnapshot
    plan: ModeAPlan
    dashboard_path: Path


@dataclass(frozen=True)
class WorkflowCheck:
    snapshot: GoalSnapshot
    dashboard_path: Path
    health: GoalHealthReport
    brief: GoalBrief
    checkpoint: CurrentCheckpointBrief
    issues: GoalIssueReport
    merge: MergeReadinessReport
    architecture: ArchitectureCheckReport
    capability: CapabilityCheckReport
    registry_count: int
    portable_path: Path | None = None

    @property
    def passed(self) -> bool:
        return self.health.passed


@dataclass(frozen=True)
class WorkflowView:
    snapshot: GoalSnapshot
    dashboard_path: Path
    architecture_path: Path
    portable_path: Path


@dataclass(frozen=True)
class WorkflowFinish:
    snapshot: GoalSnapshot
    check: WorkflowCheck
    export: PortableExport
    memory_digest: str = ""

    @property
    def passed(self) -> bool:
        phases_accepted = all(phase.status == PhaseStatus.ACCEPTED for phase in self.snapshot.phases)
        return self.snapshot.status == GoalStatus.COMPLETE and phases_accepted and self.check.passed


def start_workflow(
    objective: str,
    cwd: Path,
    *,
    agent: ModeAAdapter = "auto",
    autonomy: str = "standard",
    why: str = "",
    new_project: Path | None = None,
    workspace: str = "auto",
    loop: Path | None = None,
    profile_root: Path | None = None,
) -> WorkflowStart:
    phases = None
    definition_of_done = None
    if loop is not None:
        design = load_design(loop)
        if not design.phases:
            raise GoalsError("Loop design must include at least one phase before activation.")
        root = profile_root or profile_root_for_loop_path(loop, cwd=cwd)
        loop_snapshot = to_snapshot(design, profile_root=root)
        phases = loop_snapshot.phases
        definition_of_done = loop_snapshot.definition_of_done
        objective = objective or loop_snapshot.objective
        if not objective.strip():
            raise GoalsError("Loop design must include an objective, or pass one to `goals start`.")
        why = why or loop_snapshot.why
    snapshot = create_goal(
        objective,
        cwd,
        autonomy=autonomy,
        why=why,
        new_project=new_project,
        workspace=workspace,  # type: ignore[arg-type]
        phases=phases,
        definition_of_done=definition_of_done,
    )
    worktree = Path(snapshot.topology.worktree_path)
    dashboard_path = emit_dashboard(worktree)
    plan = build_mode_a_plan(snapshot, agent)
    return WorkflowStart(snapshot=snapshot, plan=plan, dashboard_path=dashboard_path)


def next_workflow(cwd: Path, *, agent: ModeAAdapter = "auto", full: bool = False) -> WorkflowNext:
    claim_worktree(cwd)
    dashboard_path = emit_dashboard(cwd)
    snapshot = load_active_snapshot(cwd)
    plan = build_mode_a_plan(snapshot, agent, full=full)
    return WorkflowNext(snapshot=snapshot, plan=plan, dashboard_path=dashboard_path)


def check_workflow(cwd: Path, *, refresh: bool = False) -> WorkflowCheck:
    claim_worktree(cwd)
    snapshot = load_active_snapshot(cwd)
    worktree = Path(snapshot.topology.worktree_path)
    export = export_goal(cwd) if refresh else None
    health = build_goal_health(snapshot, worktree)
    dashboard_path = emit_dashboard(cwd, health=health)
    return WorkflowCheck(
        snapshot=snapshot,
        dashboard_path=dashboard_path,
        health=health,
        brief=health.brief,
        checkpoint=health.checkpoint,
        issues=health.issues,
        merge=health.merge,
        architecture=health.architecture,
        capability=health.capability,
        registry_count=health.registry_count,
        portable_path=Path(export.markdown_path) if export is not None else None,
    )


def view_workflow(cwd: Path) -> WorkflowView:
    claim_worktree(cwd)
    export, architecture_path, dashboard_path = refresh_goal_outputs(cwd)
    portable_path = Path(export.markdown_path)
    snapshot = load_active_snapshot(cwd)
    return WorkflowView(
        snapshot=snapshot,
        dashboard_path=dashboard_path,
        architecture_path=architecture_path,
        portable_path=portable_path,
    )


def finish_workflow(cwd: Path) -> WorkflowFinish:
    check = check_workflow(cwd, refresh=True)
    export = export_goal(cwd)
    snapshot = load_active_snapshot(cwd)
    try:
        digest = build_goal_memory_digest(snapshot.goal_id)
    except GoalsError:
        digest = ""
    return WorkflowFinish(snapshot=snapshot, check=check, export=export, memory_digest=digest)


def render_start_workflow(report: WorkflowStart) -> str:
    plan = report.plan
    snapshot = report.snapshot
    topology = snapshot.topology
    worktree = Path(topology.worktree_path)
    repo = Path(topology.base_repo)
    agent_label = _agent_label(plan)
    paste_target = _paste_target(plan.adapter)

    is_worktree = worktree != repo
    is_non_git = not topology.base_branch
    if is_worktree:
        location = f"Worktree: `{worktree}` (branch `{topology.branch}`)"
        notice = (
            "Created an isolated worktree so your base checkout stays untouched."
            if topology.base_branch in ("main", "master")
            else "Created an isolated worktree (run several goals in parallel this way)."
        )
        steps = [
            f"1. Work in `{worktree}` — `cd` there yourself, or the goals plugin "
            "drives your agent there for you.",
            f"2. `goals next --agent {plan.adapter}`",
        ]
        tip = (
            "Tip: on macOS, `goals next --agent "
            f"{plan.adapter} | pbcopy` from the worktree copies the handoff."
        )
    else:
        location = (
            f"Working in place: `{worktree}`"
            + (f" (branch `{topology.branch}`)" if not is_non_git else "")
        )
        notice = (
            "No git repository here — working directly with no isolation. "
            "`git init` (one commit) to get worktree isolation and parallel goals."
            if is_non_git
            else f"Working in place on `{topology.branch}` (use --worktree for parallel goals)."
        )
        steps = [f"1. `goals next --agent {plan.adapter}` (no cd needed)"]
        tip = "Tip: use `--worktree` next time to isolate a goal in its own branch."

    return "\n".join(
        [
            "# Goal Started",
            "",
            f"Goal: {snapshot.objective}",
            location,
            f"Dashboard: {_dashboard_link(report.dashboard_path)} (click to open)",
            f"Agent: {agent_label}",
            "",
            notice,
            "",
            "Next:",
            *steps,
            f"{len(steps) + 1}. Paste the output into {paste_target}.",
            "",
            tip,
        ]
    ) + "\n"


def render_check_workflow(report: WorkflowCheck) -> str:
    brief = report.brief
    checkpoint = report.checkpoint
    issues = report.issues
    merge = report.merge
    architecture = report.architecture
    capability = report.capability
    lines = [
        "# Goal Check",
        "",
        f"Goal: {report.snapshot.objective}",
        f"Status: {report.snapshot.status}",
        f"Current phase: {report.snapshot.current_phase or 'none'}",
        f"Waiting on: {brief.waiting_on}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        f"Dashboard: {_dashboard_link(report.dashboard_path)} (click to open)",
        "",
        "## Plain-Language Brief",
        brief.summary,
        f"- Progress: {brief.progress}",
        f"- Proof: {brief.proof}",
        "",
        "## Next Safe Step",
        checkpoint.next_safe_step,
        "",
        "## Needs The User",
        _bullets(
            [
                f"{action.title}: {action.plain_summary} "
                f"Suggested reply: {action.suggested_reply}"
                for action in brief.user_actions
            ],
            empty="Nothing important is waiting on the user.",
        ),
        "",
        "## Agent Can Do",
        _bullets(
            [
                f"{action.title}: {action.suggested_reply or action.plain_summary}"
                for action in brief.agent_actions[:6]
            ],
            empty="No agent-side repair action is currently suggested.",
        ),
        "",
        "## Blocking Signals",
        _bullets(_issue_lines(issues), empty=issues.summary),
        "",
        "## Merge Readiness",
        f"Overall: {'pass' if merge.passed else 'needs attention'}",
        _bullets(_merge_lines(merge), empty=merge.summary),
        "",
        "## Architecture",
        f"Overall: {'pass' if architecture.passed else 'needs attention'}",
        _bullets(_architecture_lines(architecture), empty=architecture.summary),
        "",
        "## Capabilities",
        f"Overall: {'pass' if capability.passed else 'needs attention'}",
        _bullets(_capability_lines(capability), empty=capability.summary),
        "",
        "## Registry",
        f"Validated registry files: {report.registry_count}",
        "",
        "Useful next commands:",
        "- `goals next --agent codex` or `goals next --agent claude`",
        "- `goals view`",
    ]
    return "\n".join(lines) + "\n"


def render_view_workflow(report: WorkflowView) -> str:
    return "\n".join(
        [
            "# Goal View",
            "",
            f"Goal: {report.snapshot.objective}",
            f"Dashboard: {_dashboard_link(report.dashboard_path)} (click to open)",
            f"Architecture map: `{report.architecture_path}`",
            f"Portable goal spec: `{report.portable_path}`",
            "",
            "Open the dashboard file in a browser for the user-friendly status page.",
            "The portable spec (`.goals/`) is sanitized and safe to commit so any",
            "agent can resume this goal.",
        ]
    ) + "\n"


def _dashboard_link(path: Path) -> str:
    """Render the dashboard path as a bare, clickable file:// URL.

    Terminals linkify a bare URL but not a backtick-wrapped path, and `as_uri`
    encodes spaces correctly (worktree dirs can contain them). Matches the
    pattern already used for `goals view --open` (cli.py).
    """
    return path.resolve().as_uri()


def _agent_label(plan: ModeAPlan) -> str:
    status = "ready" if plan.adapter_ready else "not confirmed"
    detail = f" - {plan.adapter_detail}" if plan.adapter_detail else ""
    return f"{plan.adapter} ({status}{detail})"


def _paste_target(agent: str) -> str:
    if agent == "codex":
        return "Codex"
    if agent == "claude":
        return "Claude Code"
    return "your native agent"


def _bullets(items: list[str], *, empty: str) -> str:
    if not items:
        return f"- {empty}"
    return "\n".join(f"- {item}" for item in items)


def _issue_lines(report: GoalIssueReport) -> list[str]:
    lines = []
    for issue in report.issues[:8]:
        owner = "user" if issue.needs_user else "agent"
        action = f" Next: {issue.suggested_action}" if issue.suggested_action else ""
        summary = issue.summary.rstrip(".")
        category = f"[{issue.category}]" if issue.category else ""
        lines.append(f"[{issue.severity}][{owner}][{issue.area}]{category} {summary}.{action}")
    if len(report.issues) > 8:
        lines.append(f"{len(report.issues) - 8} more issue(s); run `goals issues`.")
    return lines


def _merge_lines(report: MergeReadinessReport) -> list[str]:
    lines = []
    for finding in report.findings[:6]:
        owner = "user" if finding.needs_user else "agent"
        action = f" Next: {finding.suggested_action}" if finding.suggested_action else ""
        summary = finding.summary.rstrip(".")
        lines.append(f"[{finding.severity}][{owner}][{finding.area}] {summary}.{action}")
    if len(report.findings) > 6:
        lines.append(f"{len(report.findings) - 6} more finding(s); run `goals merge-check`.")
    return lines


def render_finish_workflow(report: WorkflowFinish) -> str:
    lines = [
        "# Goal Finish",
        "",
        f"Goal: {report.snapshot.objective}",
        f"Status: {report.snapshot.status}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        f"Portable spec: `{report.export.markdown_path}`",
        "",
        "## Closeout Gate",
    ]
    if report.snapshot.status != GoalStatus.COMPLETE:
        lines.append("- Goal is not complete; every phase must be reviewed and accepted first.")
    unaccepted = [
        phase.phase_id for phase in report.snapshot.phases if phase.status != PhaseStatus.ACCEPTED
    ]
    if unaccepted:
        lines.append(f"- Unaccepted phases: {', '.join(unaccepted)}")
    if not report.check.passed:
        lines.append("- `goals check` still reports issues, merge risk, or architecture risk.")
    if report.passed:
        lines.append("- All phases are accepted and the final check passed.")
    lines.extend(
        [
            "",
            "## Check Summary",
            f"- Issues: {report.check.issues.summary}",
            f"- Merge: {report.check.merge.summary}",
            f"- Architecture: {report.check.architecture.summary}",
        ]
    )
    if report.memory_digest:
        lines.extend(["", "## Goal Execution Memory", report.memory_digest.rstrip()])
    lines.extend(
        [
            "",
            "Next:",
            "- Commit the refreshed `.goals` portable state with the implementation.",
        ]
    )
    return "\n".join(lines) + "\n"


def _architecture_lines(report: ArchitectureCheckReport) -> list[str]:
    lines = []
    for finding in report.findings[:6]:
        action = f" Next: {finding.suggested_action}" if finding.suggested_action else ""
        summary = finding.summary.rstrip(".")
        lines.append(f"[{finding.severity}][{finding.area}] {summary}.{action}")
    if len(report.findings) > 6:
        lines.append(
            f"{len(report.findings) - 6} more finding(s); run `goals architecture check`."
        )
    return lines


def _capability_lines(report: CapabilityCheckReport) -> list[str]:
    lines = []
    for gap in report.gaps[:6]:
        owner = "user" if gap.needs_user else "agent"
        action = f" Next: {gap.suggested_action}" if gap.suggested_action else ""
        summary = gap.title.rstrip(".")
        lines.append(f"[{gap.severity}][{owner}][{gap.status}] {summary}.{action}")
    if len(report.gaps) > 6:
        lines.append(f"{len(report.gaps) - 6} more gap(s); run `goals capability check`.")
    return lines
