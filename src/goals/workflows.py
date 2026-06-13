from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from goals.architecture import analyze_code_architecture
from goals.brief import build_goal_brief
from goals.checkpoints import build_current_checkpoint_brief
from goals.issues import analyze_goal_issues
from goals.merge_readiness import analyze_merge_readiness
from goals.mode_a import ModeAAdapter, build_mode_a_plan
from goals.models import (
    ArchitectureCheckReport,
    CurrentCheckpointBrief,
    GoalBrief,
    GoalIssueReport,
    GoalSnapshot,
    MergeReadinessReport,
    ModeAPlan,
)
from goals.registry import validate_registries
from goals.runtime import claim_worktree, create_goal, emit_architecture, emit_dashboard, load_active_snapshot


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
    brief: GoalBrief
    checkpoint: CurrentCheckpointBrief
    issues: GoalIssueReport
    merge: MergeReadinessReport
    architecture: ArchitectureCheckReport
    registry_count: int

    @property
    def passed(self) -> bool:
        return not self.issues.issues and self.merge.passed and self.architecture.passed


@dataclass(frozen=True)
class WorkflowView:
    snapshot: GoalSnapshot
    dashboard_path: Path
    architecture_path: Path


def start_workflow(
    objective: str,
    cwd: Path,
    *,
    agent: ModeAAdapter = "auto",
    autonomy: str = "standard",
    why: str = "",
    new_project: Path | None = None,
) -> WorkflowStart:
    snapshot = create_goal(objective, cwd, autonomy=autonomy, why=why, new_project=new_project)
    worktree = Path(snapshot.topology.worktree_path)
    dashboard_path = emit_dashboard(worktree)
    plan = build_mode_a_plan(snapshot, agent)
    return WorkflowStart(snapshot=snapshot, plan=plan, dashboard_path=dashboard_path)


def next_workflow(cwd: Path, *, agent: ModeAAdapter = "auto") -> WorkflowNext:
    claim_worktree(cwd)
    dashboard_path = emit_dashboard(cwd)
    snapshot = load_active_snapshot(cwd)
    plan = build_mode_a_plan(snapshot, agent)
    return WorkflowNext(snapshot=snapshot, plan=plan, dashboard_path=dashboard_path)


def check_workflow(cwd: Path) -> WorkflowCheck:
    claim_worktree(cwd)
    dashboard_path = emit_dashboard(cwd)
    snapshot = load_active_snapshot(cwd)
    worktree = Path(snapshot.topology.worktree_path)
    return WorkflowCheck(
        snapshot=snapshot,
        dashboard_path=dashboard_path,
        brief=build_goal_brief(snapshot),
        checkpoint=build_current_checkpoint_brief(snapshot),
        issues=analyze_goal_issues(snapshot),
        merge=analyze_merge_readiness(snapshot),
        architecture=analyze_code_architecture(snapshot, worktree),
        registry_count=len(validate_registries(worktree)),
    )


def view_workflow(cwd: Path) -> WorkflowView:
    claim_worktree(cwd)
    dashboard_path = emit_dashboard(cwd)
    architecture_path = emit_architecture(cwd)
    snapshot = load_active_snapshot(cwd)
    return WorkflowView(
        snapshot=snapshot,
        dashboard_path=dashboard_path,
        architecture_path=architecture_path,
    )


def render_start_workflow(report: WorkflowStart) -> str:
    plan = report.plan
    snapshot = report.snapshot
    worktree = Path(snapshot.topology.worktree_path)
    agent_label = _agent_label(plan)
    paste_target = _paste_target(plan.adapter)
    return "\n".join(
        [
            "# Goal Started",
            "",
            f"Goal: {snapshot.objective}",
            f"Worktree: `{worktree}`",
            f"Dashboard: `{report.dashboard_path}`",
            f"Agent: {agent_label}",
            "",
            "Next:",
            f"1. `cd {worktree}`",
            f"2. `goals next --agent {plan.adapter}`",
            f"3. Paste the output into {paste_target}.",
            "",
            "Tip: on macOS, use `goals next --agent "
            f"{plan.adapter} | pbcopy` from the worktree to copy the handoff.",
        ]
    ) + "\n"


def render_check_workflow(report: WorkflowCheck) -> str:
    brief = report.brief
    checkpoint = report.checkpoint
    issues = report.issues
    merge = report.merge
    architecture = report.architecture
    lines = [
        "# Goal Check",
        "",
        f"Goal: {report.snapshot.objective}",
        f"Status: {report.snapshot.status}",
        f"Current phase: {report.snapshot.current_phase or 'none'}",
        f"Waiting on: {brief.waiting_on}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        f"Dashboard: `{report.dashboard_path}`",
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
            f"Dashboard: `{report.dashboard_path}`",
            f"Architecture map: `{report.architecture_path}`",
            "",
            "Open the dashboard file in a browser for the user-friendly status page.",
        ]
    ) + "\n"


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
        lines.append(f"[{issue.severity}][{owner}][{issue.area}] {summary}.{action}")
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
