from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from goals.architecture import architecture_for_snapshot, render_architecture_markdown
from goals.checkpoints import phase_checkpoint_blockers
from goals.dashboard import render_dashboard
from goals.git_ops import (
    DEFAULT_BRANCHES,
    create_worktree,
    current_branch,
    find_git_root,
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


Workspace = Literal["auto", "worktree", "in_place"]


@dataclass
class WorkspacePlan:
    """Resolved decision for where a goal's work happens."""

    mode: Literal["worktree", "in_place"]
    repo: Path
    is_git: bool
    base_branch: str
    #: True only for `auto` on a feature branch — the caller may prompt to offer
    #: in-place vs worktree. On a default branch the choice is forced (worktree).
    ambiguous: bool


def resolve_workspace(
    base: Path, *, requested: Workspace = "auto", new_project_created: bool = False
) -> WorkspacePlan:
    """Decide worktree vs in-place vs non-git, pure (no side effects).

    Policy:
    - **Non-git directory** → in-place (full non-git support); no isolation.
    - **Default branch (main/master)** → always a worktree; goals never modifies
      the base checkout. Any `--in-place` request is overridden here.
    - **Feature branch** → honor `--worktree`/`--in-place`; `auto` defaults to
      working **in place** (the calm, no-cd path) and flags `ambiguous` so an
      interactive caller can still offer a worktree for parallel goals.
    - **Freshly created `--new` project** → worktree unless `in_place` requested.
    """
    git = find_git_root(base)
    if git is None:
        return WorkspacePlan("in_place", base.resolve(), False, "", False)
    branch = current_branch(git)
    # Protected-branch guard FIRST so nothing (incl. --new --in-place, since a
    # fresh repo starts on a default branch) can work in place on main/master.
    if branch in DEFAULT_BRANCHES:
        return WorkspacePlan("worktree", git, True, branch, False)
    if new_project_created:
        mode = "in_place" if requested == "in_place" else "worktree"
        return WorkspacePlan(mode, git, True, branch, False)
    if requested == "worktree":
        return WorkspacePlan("worktree", git, True, branch, False)
    if requested == "in_place":
        return WorkspacePlan("in_place", git, True, branch, False)
    return WorkspacePlan("in_place", git, True, branch, True)  # auto → in-place, prompt-able


def create_goal(
    objective: str,
    cwd: Path,
    *,
    autonomy: str = "standard",
    why: str = "",
    new_project: Path | None = None,
    workspace: Workspace = "auto",
) -> GoalSnapshot:
    base = _ensure_repo(cwd, new_project) if new_project is not None else cwd
    plan = resolve_workspace(base, requested=workspace, new_project_created=new_project is not None)
    goal_id = slugify(objective)
    if plan.mode == "in_place":
        existing = _existing_goal_ids(plan.repo)
        # In-place is one goal per repo root. Refuse ANY existing goal here —
        # including a same-id slug collision (two different objectives that
        # slugify alike), which would otherwise append a second goal_created
        # event into the first goal's log and silently discard this objective.
        if existing:
            raise GoalsError(
                f"A goal is already active here ({', '.join(existing)}). Finish it, "
                "or run the new goal in its own worktree with `--worktree` "
                "(worktrees are how you run several goals at once)."
            )
    if plan.mode == "worktree":
        require_clean_repo(plan.repo)
        if not has_commits(plan.repo):
            raise GoalsError(
                "Repository has no commits. Create an initial commit before creating a goal."
            )
        worktree, branch = create_worktree(plan.repo, goal_id, objective)
    else:
        worktree, branch = plan.repo, plan.base_branch
    lease = WorktreeLease(
        base_repo=str(plan.repo),
        base_branch=plan.base_branch,
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
    goal_dir = Path(worktree) / ".agent-workflow" / "goals" / goal_id
    store = EventStore(goal_dir)
    store.append(
        Event(
            goal_id=goal_id,
            event_type=EventType.GOAL_CREATED,
            payload={"snapshot": snapshot.model_dump()},
        )
    )
    if plan.is_git:
        write_workflow_gitignore(plan.repo)
        if Path(worktree) != plan.repo:
            write_workflow_gitignore(worktree)
    return store.snapshot()


def active_goal_dir(cwd: Path) -> Path:
    # Fall back to cwd when not in a git repo, so non-git in-place goals resolve.
    repo = find_git_root(cwd) or cwd.resolve()
    goals_dir = repo / ".agent-workflow" / "goals"
    goals = sorted(p for p in goals_dir.iterdir() if p.is_dir()) if goals_dir.exists() else []
    if not goals:
        raise GoalsError("No active goal in this directory." + _goal_location_hint(repo))
    if len(goals) > 1:
        active = [p for p in goals if (p / "goal.json").exists()]
        if not active:
            names = ", ".join(p.name for p in goals)
            raise GoalsError(f"No readable goal among ({names}). Run `goals repair`.")
        if len(active) == 1:
            return active[0]
        # Several goals share this directory (in-place goals). Act on the most
        # recently updated rather than bricking; creating a second in-place goal
        # is refused at start, so this is rare and resilient by design.
        return max(active, key=_goal_updated_at)
    return goals[0]


def _existing_goal_ids(repo: Path) -> list[str]:
    goals_dir = repo / ".agent-workflow" / "goals"
    if not goals_dir.is_dir():
        return []
    return sorted(p.name for p in goals_dir.iterdir() if p.is_dir() and (p / "goal.json").exists())


def _goal_updated_at(goal_dir: Path) -> str:
    """Sort key for picking the active goal: the snapshot's last_updated.

    Falls back to the file mtime if the snapshot can't be read, so resolution
    never crashes on a malformed goal.json.
    """
    state = goal_dir / "goal.json"
    try:
        import json

        return str(json.loads(state.read_text(encoding="utf-8")).get("last_updated", ""))
    except (OSError, ValueError):
        return ""


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
        raise GoalsError(
            f"Goal workspace missing: {worktree}. It was moved or removed; "
            "recreate the goal or run from the correct path."
        )
    # Non-git in-place goals (no branch) and dirs that are no longer git repos
    # have no branch to verify — the path existing is the only invariant.
    if not lease.branch or find_git_root(worktree) is None:
        return lease
    branch = current_branch(worktree)
    if branch != lease.branch:
        raise GoalsError(
            f"Expected branch {lease.branch}, found {branch}. "
            f"`git switch {lease.branch}` (or cd into the goal's worktree)."
        )
    return lease


def run_gate(cwd: Path, phase_id: str, *, max_attempts: int = 3) -> GateResult:
    snapshot = load_active_snapshot(cwd)
    phase = _find_phase(snapshot, phase_id)
    attempt = len([review for review in phase.reviews if review.gate_id == "phase-review"]) + 1
    load_bearing = [
        (assumption.assumption_id, assumption.statement)
        for assumption in snapshot.assumptions
        if assumption.depends_on and assumption.phase_id == phase_id
    ]
    result = review_phase(
        phase, load_bearing=load_bearing, attempt=attempt, max_attempts=max_attempts
    )
    append_event(
        cwd,
        Event(
            goal_id=snapshot.goal_id,
            event_type=EventType.PHASE_REVIEWED,
            payload={"phase_id": phase_id, "gate_result": result.model_dump()},
        ),
    )
    return result


def verify_phase(cwd: Path, phase_id: str, *, timeout: int = 120) -> list[dict]:
    """Run the phase's automated verifications and record the real results.

    This is what makes trust un-fakeable: the *engine* runs each ``auto``
    verification's command in the goal worktree and writes ran/passed from the
    actual exit code. The agent cannot assert a pass — it can only declare a
    command, which this executes. Commands run in the worktree; route anything
    networked or destructive through the permission policy before relying on it.
    """
    import subprocess

    snapshot = load_active_snapshot(cwd)
    phase = _find_phase(snapshot, phase_id)
    if phase.evidence is None:
        raise GoalsError(
            f"No evidence recorded for {phase_id}. Record evidence with verifications first."
        )
    worktree = Path(snapshot.topology.worktree_path)
    auto = [
        v
        for v in phase.evidence.verifications
        if v.kind == "auto" and v.command.strip()
    ]
    if not auto:
        raise GoalsError(
            f"{phase_id} has no automated verifications to run. Add at least one "
            "`auto` verification with a runnable command, then verify."
        )
    results: list[dict] = []
    for v in auto:
        try:
            proc = subprocess.run(
                v.command,
                shell=True,
                cwd=worktree,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            ran, passed = True, proc.returncode == 0
            output = (proc.stdout + proc.stderr).strip()[-600:]
        except subprocess.TimeoutExpired:
            ran, passed, output = True, False, f"timed out after {timeout}s"
        except OSError as exc:
            # The command never started (e.g. missing/moved worktree): it did not
            # run, so it cannot count as an executed check.
            ran, passed, output = False, False, f"could not run: {exc}"
        results.append(
            {
                "verification_id": v.verification_id,
                "ran": ran,
                "passed": passed,
                "output_excerpt": output,
                "ran_at": utc_now(),
            }
        )
    append_event(
        cwd,
        Event(
            goal_id=snapshot.goal_id,
            event_type=EventType.PHASE_VERIFIED,
            payload={"phase_id": phase_id, "verifications": results},
        ),
    )
    return results


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
