from __future__ import annotations

import re
import subprocess
from pathlib import Path

from goals.storage import GoalsError


def run_git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git_root(cwd: Path) -> Path:
    result = run_git(["rev-parse", "--show-toplevel"], cwd, check=False)
    if result.returncode != 0:
        raise GoalsError(
            f"Not inside a git repository: {cwd}\n"
            "Goals tracks work per git repo. cd into your project's repo (or run "
            "`git init` and make a first commit), then try again."
        )
    return Path(result.stdout.strip()).resolve()


def goal_worktrees(repo: Path) -> list[Path]:
    """Return paths of linked worktrees that actually hold goal state.

    Used to point a user who ran a command from the base checkout at the
    worktree where their goal lives.
    """
    result = run_git(["worktree", "list", "--porcelain"], repo, check=False)
    if result.returncode != 0:
        return []
    found: list[Path] = []
    for line in result.stdout.splitlines():
        if not line.startswith("worktree "):
            continue
        worktree = Path(line[len("worktree ") :])
        goals_dir = worktree / ".agent-workflow" / "goals"
        if not goals_dir.is_dir():
            continue
        if any((child / "goal.json").exists() for child in goals_dir.iterdir() if child.is_dir()):
            found.append(worktree)
    return found


def git_path(repo: Path, path: str) -> Path:
    result = run_git(["rev-parse", "--git-path", path], repo)
    value = Path(result.stdout.strip())
    return value if value.is_absolute() else (repo / value).resolve()


def current_branch(repo: Path) -> str:
    result = run_git(["branch", "--show-current"], repo)
    branch = result.stdout.strip()
    if not branch:
        raise GoalsError(
            "Refusing to run on a detached HEAD. Check out a branch first "
            "(e.g. `git switch -c my-branch`)."
        )
    return branch


def require_clean_repo(repo: Path) -> None:
    result = run_git(["status", "--porcelain"], repo)
    if result.stdout.strip():
        raise GoalsError(
            "Refusing to create a goal from a dirty working tree. Commit or stash "
            "your changes first (`git status` to see them)."
        )


def has_commits(repo: Path) -> bool:
    result = run_git(["rev-parse", "--verify", "HEAD"], repo, check=False)
    return result.returncode == 0


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "goal"


def create_worktree(repo: Path, goal_id: str, objective: str) -> tuple[Path, str]:
    branch = f"goal/{goal_id}"
    worktree = repo.parent / f"{repo.name}-{goal_id}"
    if worktree.exists():
        raise GoalsError(
            f"Worktree path already exists: {worktree}\n"
            "A goal for this objective may already exist — cd into it, or remove it "
            f"with `git worktree remove {worktree}`."
        )
    existing = run_git(["branch", "--list", branch], repo).stdout.strip()
    if existing:
        raise GoalsError(
            f"Branch already exists: {branch}\n"
            "A goal for this objective may already exist. Delete the branch with "
            f"`git branch -D {branch}`, or start with a different objective."
        )
    run_git(["worktree", "add", "-b", branch, str(worktree)], repo)
    return worktree.resolve(), branch


def source_commit(repo: Path) -> str:
    result = run_git(["rev-parse", "--short", "HEAD"], repo, check=False)
    return result.stdout.strip() if result.returncode == 0 else "none"
