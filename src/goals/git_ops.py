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
    result = run_git(["rev-parse", "--show-toplevel"], cwd)
    return Path(result.stdout.strip()).resolve()


def git_path(repo: Path, path: str) -> Path:
    result = run_git(["rev-parse", "--git-path", path], repo)
    value = Path(result.stdout.strip())
    return value if value.is_absolute() else (repo / value).resolve()


def current_branch(repo: Path) -> str:
    result = run_git(["branch", "--show-current"], repo)
    branch = result.stdout.strip()
    if not branch:
        raise GoalsError("Refusing to run on a detached HEAD.")
    return branch


def require_clean_repo(repo: Path) -> None:
    result = run_git(["status", "--porcelain"], repo)
    if result.stdout.strip():
        raise GoalsError("Refusing to create a goal from a dirty working tree.")


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
        raise GoalsError(f"Worktree path already exists: {worktree}")
    existing = run_git(["branch", "--list", branch], repo).stdout.strip()
    if existing:
        raise GoalsError(f"Branch already exists: {branch}")
    run_git(["worktree", "add", "-b", branch, str(worktree)], repo)
    return worktree.resolve(), branch


def source_commit(repo: Path) -> str:
    result = run_git(["rev-parse", "--short", "HEAD"], repo, check=False)
    return result.stdout.strip() if result.returncode == 0 else "none"
