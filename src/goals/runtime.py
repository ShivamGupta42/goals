from __future__ import annotations

from pathlib import Path
from typing import Literal

from goals.architecture import architecture_for_snapshot, render_architecture_markdown
from goals.checkpoints import phase_checkpoint_blockers
from goals.dashboard import render_dashboard
from goals.git_ops import (
    create_worktree,
    current_branch,
    git_path,
    git_root,
    goal_worktrees,
    has_commits,
    require_clean_repo,
    slugify,
)
from goals.gates import review_phase
from goals.models import (
    Event,
    EventType,
    GateResult,
    GateVerdict,
    GoalSnapshot,
    Phase,
    WorktreeLease,
    utc_now,
)
from goals.storage import (
    EventStore,
    GoalsError,
    atomic_write_text,
    derive_snapshot as derive_snapshot,
)


def default_phases(objective: str) -> list[Phase]:
    return [
        Phase(
            phase_id="P1",
            title="Confirm outcome and plan",
            goal=f"Turn the objective into a clear definition of done: {objective}",
            acceptance_criteria=[
                "The goal has a plain-language objective.",
                "The definition of done is visible.",
                "The next phase is unblocked.",
            ],
        ),
        Phase(
            phase_id="P2",
            title="Inspect project and choose approach",
            goal="Understand the project shape and choose the lowest-risk implementation path.",
            acceptance_criteria=[
                "Relevant files and commands are identified.",
                "Repo-specific risks or constraints are recorded.",
            ],
        ),
        Phase(
            phase_id="P3",
            title="Execute the core change",
            goal="Make the smallest complete change that satisfies the goal.",
            acceptance_criteria=[
                "Changed files are listed.",
                "Checks or tests are recorded.",
                "Known gaps are explicit.",
            ],
        ),
        Phase(
            phase_id="P4",
            title="Review, explain, and close",
            goal="Verify the outcome, explain decisions, and capture learnings.",
            acceptance_criteria=[
                "Evidence proves the definition of done.",
                "Remaining risks are listed or empty.",
                "Dashboard reflects final state.",
            ],
        ),
    ]


def create_goal(
    objective: str,
    cwd: Path,
    *,
    autonomy: str = "standard",
    why: str = "",
    new_project: Path | None = None,
) -> GoalSnapshot:
    repo = _ensure_repo(cwd, new_project)
    require_clean_repo(repo)
    if not has_commits(repo):
        raise GoalsError(
            "Repository has no commits. Create an initial commit before creating a goal."
        )
    base_branch = current_branch(repo)
    goal_id = slugify(objective)
    worktree, branch = create_worktree(repo, goal_id, objective)
    lease = WorktreeLease(
        base_repo=str(repo),
        base_branch=base_branch,
        worktree_path=str(worktree),
        branch=branch,
    )
    snapshot = GoalSnapshot(
        goal_id=goal_id,
        objective=objective,
        why=why or "Keep a long-running agent task understandable, reviewable, and resumable.",
        definition_of_done=[
            "All phases are accepted.",
            "The dashboard shows no blocking decisions.",
            "Evidence exists for completed work.",
        ],
        autonomy=autonomy,  # type: ignore[arg-type]
        topology=lease,
        phases=default_phases(objective),
        current_phase="P1",
        last_updated=utc_now(),
    )
    goal_dir = worktree / ".agent-workflow" / "goals" / goal_id
    store = EventStore(goal_dir)
    store.append(
        Event(
            goal_id=goal_id,
            event_type=EventType.GOAL_CREATED,
            payload={"snapshot": snapshot.model_dump()},
        )
    )
    write_workflow_gitignore(repo)
    write_workflow_gitignore(worktree)
    return store.snapshot()


def active_goal_dir(cwd: Path) -> Path:
    repo = git_root(cwd)
    goals_dir = repo / ".agent-workflow" / "goals"
    goals = sorted(p for p in goals_dir.iterdir() if p.is_dir()) if goals_dir.exists() else []
    if not goals:
        raise GoalsError("No active goal in this directory." + _goal_location_hint(repo))
    if len(goals) > 1:
        active = [p for p in goals if (p / "goal.json").exists()]
        if len(active) == 1:
            return active[0]
        names = ", ".join(p.name for p in goals)
        raise GoalsError(
            f"Multiple goals found here ({names}). cd into the specific goal's "
            "worktree and re-run."
        )
    return goals[0]


def _goal_location_hint(repo: Path) -> str:
    """Tell the user where the goal actually lives.

    The common mistake is running a command from the base checkout after
    `goals start`, where no goal state exists — the state is in the goal's
    worktree. Name those worktrees so the next step is obvious.
    """
    worktrees = goal_worktrees(repo)
    if not worktrees:
        return (
            ' No goal exists for this repo yet. Run `goals start "<objective>"` to '
            "create one, then cd into the worktree it prints."
        )
    listing = "\n".join(f"  cd {path}" for path in worktrees)
    return (
        " A goal's state lives in its own worktree, not here. cd into it and re-run:\n"
        + listing
    )


def load_active_snapshot(cwd: Path) -> GoalSnapshot:
    return EventStore(active_goal_dir(cwd)).snapshot()


def append_event(cwd: Path, event: Event) -> GoalSnapshot:
    goal_dir = active_goal_dir(cwd)
    store = EventStore(goal_dir)
    store.append(event)
    return store.snapshot()


def transition_phase(cwd: Path, phase_id: str, action: Literal["start", "accept"]) -> GoalSnapshot:
    snapshot = load_active_snapshot(cwd)
    phase = _find_phase(snapshot, phase_id)
    if action == "start":
        event_type = EventType.PHASE_STARTED
    elif action == "accept":
        checkpoint_issues = phase_checkpoint_blockers(phase)
        if checkpoint_issues:
            raise GoalsError(
                "Required checkpoint must pass or be waived before acceptance: "
                + "; ".join(checkpoint_issues)
            )
        if not phase.reviews or phase.reviews[-1].verdict != GateVerdict.PASS:
            raise GoalsError(
                f"Latest phase review must pass before accepting {phase_id}. "
                f"Record evidence, then run `goals phase review {phase_id}` and fix "
                "any findings first."
            )
        event_type = EventType.PHASE_ACCEPTED
    else:
        raise GoalsError(f"Unsupported phase transition: {action}")
    return append_event(
        cwd, Event(goal_id=snapshot.goal_id, event_type=event_type, payload={"phase_id": phase_id})
    )


def claim_worktree(cwd: Path) -> WorktreeLease:
    snapshot = load_active_snapshot(cwd)
    lease = snapshot.topology
    worktree = Path(lease.worktree_path)
    if not worktree.exists():
        raise GoalsError(f"Worktree missing: {worktree}")
    branch = current_branch(worktree)
    if branch != lease.branch:
        raise GoalsError(f"Expected branch {lease.branch}, found {branch}.")
    return lease


def run_gate(cwd: Path, phase_id: str, *, max_attempts: int = 3) -> GateResult:
    snapshot = load_active_snapshot(cwd)
    phase = _find_phase(snapshot, phase_id)
    attempt = len([review for review in phase.reviews if review.gate_id == "phase-review"]) + 1
    result = review_phase(phase, attempt=attempt, max_attempts=max_attempts)
    append_event(
        cwd,
        Event(
            goal_id=snapshot.goal_id,
            event_type=EventType.PHASE_REVIEWED,
            payload={"phase_id": phase_id, "gate_result": result.model_dump()},
        ),
    )
    return result


def emit_dashboard(cwd: Path) -> Path:
    snapshot = load_active_snapshot(cwd)
    goal_dir = (
        Path(snapshot.topology.worktree_path) / ".agent-workflow" / "goals" / snapshot.goal_id
    )
    output_path = goal_dir / "dashboard.html"
    architecture_path = emit_architecture(cwd)
    render_dashboard(snapshot, output_path, architecture_path=architecture_path)
    return output_path


def emit_architecture(cwd: Path) -> Path:
    snapshot = load_active_snapshot(cwd)
    goal_dir = (
        Path(snapshot.topology.worktree_path) / ".agent-workflow" / "goals" / snapshot.goal_id
    )
    architecture_path = goal_dir / "architecture.md"
    render_architecture_markdown(architecture_for_snapshot(snapshot), architecture_path)
    return architecture_path


def write_workflow_gitignore(repo: Path) -> None:
    path = git_path(repo, "info/exclude")
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    rules = [".agent-workflow/goals/", ".agent-workflow/self-evolution/", ".goals-worktrees/"]
    missing = [rule for rule in rules if rule not in existing.splitlines()]
    if missing:
        suffix = "\n".join(["", "# Goals local state", *missing, ""])
        atomic_write_text(path, existing.rstrip() + suffix)


def _ensure_repo(cwd: Path, new_project: Path | None) -> Path:
    if new_project is None:
        return git_root(cwd)
    new_project.mkdir(parents=True, exist_ok=True)
    subprocess_args = [["git", "init"]]
    import subprocess

    for args in subprocess_args:
        subprocess.run(
            args, cwd=new_project, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    readme = new_project / "README.md"
    if not readme.exists():
        readme.write_text(f"# {new_project.name}\n\nCreated with Goals.\n")
    gitignore = new_project / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".agent-workflow/goals/\n.goals-worktrees/\n")
    subprocess.run(["git", "add", "README.md", ".gitignore"], cwd=new_project, check=True)
    subprocess.run(
        ["git", "commit", "-m", "chore: initialize workspace"],
        cwd=new_project,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return new_project.resolve()


def _find_phase(snapshot: GoalSnapshot, phase_id: str) -> Phase:
    phase = next(
        (candidate for candidate in snapshot.phases if candidate.phase_id == phase_id), None
    )
    if phase is None:
        valid = ", ".join(p.phase_id for p in snapshot.phases) or "none"
        raise GoalsError(f"Unknown phase: {phase_id}. Valid phases: {valid}.")
    return phase
