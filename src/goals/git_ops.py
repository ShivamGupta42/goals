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
    if result.returncode == 0:
        return Path(result.stdout.strip()).resolve()
    # Only claim "not a repository" when git actually said so; surface any other
    # failure (corrupt repo, permissions, bad $GIT_DIR) with git's own message
    # instead of mislabeling it.
    detail = result.stderr.strip()
    if "not a git repository" in detail.lower():
        raise GoalsError(
            f"Not inside a git repository: {cwd}\n"
            "Goals tracks work per git repo. cd into your project's repo (or run "
            "`git init` and make a first commit), then try again."
        )
    raise GoalsError(f"git could not resolve the repository at {cwd}: {detail or 'unknown error'}")


#: Branch names goals treats as a protected base checkout — never worked in
#: place; a goal on one of these always gets its own worktree.
DEFAULT_BRANCHES = frozenset({"main", "master"})


def find_git_root(cwd: Path) -> Path | None:
    """Return the git repo root for ``cwd``, or ``None`` if not in a git repo.

    The non-raising counterpart of :func:`git_root`, used to decide between
    git and non-git (in-place) workspace modes.
    """
    result = run_git(["rev-parse", "--show-toplevel"], cwd, check=False)
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).resolve()


def list_worktrees(repo: Path) -> list[dict[str, str | Path]]:
    """Parse ``git worktree list --porcelain`` into records.

    Each record has a ``path`` (Path) and, when present, ``head`` and ``branch``.
    The single source of truth for worktree enumeration, shared by goal-location
    hints and merge-readiness scanning. Returns ``[]`` if git is unavailable or
    the command fails.
    """
    try:
        result = run_git(["worktree", "list", "--porcelain"], repo, check=False)
    except OSError:
        return []
    if result.returncode != 0:
        return []
    records: list[dict[str, str | Path]] = []
    current: dict[str, str | Path] = {}
    for line in result.stdout.splitlines():
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            if current:
                records.append(current)
            current = {"path": Path(value)}
        elif key == "HEAD":
            current["head"] = value[:12]
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key == "detached":
            current["branch"] = "(detached)"
    if current:
        records.append(current)
    return records


def goal_worktrees(repo: Path) -> list[Path]:
    """Return paths of linked worktrees that actually hold goal state.

    Used to point a user who ran a command from the base checkout at the
    worktree where their goal lives.
    """
    found: list[Path] = []
    for record in list_worktrees(repo):
        worktree = record["path"]
        if not isinstance(worktree, Path):
            continue
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


def require_clean_repo(repo: Path, *, ignored_prefixes: tuple[str, ...] = ()) -> None:
    result = run_git(["status", "--porcelain"], repo)
    dirty = [
        line
        for line in result.stdout.splitlines()
        if line and not _ignored_status_line(line, ignored_prefixes)
    ]
    if dirty:
        raise GoalsError(
            "Refusing to create a goal from a dirty working tree. Commit or stash "
            "your changes first (`git status` to see them)."
        )


def has_commits(repo: Path) -> bool:
    result = run_git(["rev-parse", "--verify", "HEAD"], repo, check=False)
    return result.returncode == 0


def _ignored_status_line(line: str, ignored_prefixes: tuple[str, ...]) -> bool:
    if not ignored_prefixes:
        return False
    paths = _status_paths(line)
    return bool(paths) and all(_matches_prefix(path, ignored_prefixes) for path in paths)


def _status_paths(line: str) -> list[str]:
    payload = line[3:] if len(line) > 3 else ""
    if not payload:
        return []
    return [_clean_status_path(path) for path in payload.split(" -> ")]


def _clean_status_path(path: str) -> str:
    return path.strip().strip('"').removeprefix("./")


def _matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    for prefix in prefixes:
        normalized = prefix.strip().removeprefix("./")
        if not normalized:
            continue
        directory = normalized if normalized.endswith("/") else f"{normalized}/"
        if path == normalized.rstrip("/") or path.startswith(directory):
            return True
    return False


def slugify(text: str, max_len: int = 32) -> str:
    """A short, readable slug for branch/worktree/goal-id names.

    Keeps whole words up to ``max_len`` so names never truncate mid-word (the old
    48-char hard cut produced things like ``…divides-a-bill-b``). Collisions are
    handled by the callers, which refuse or error clearly rather than corrupt.
    """
    words = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower()).split()
    slug = ""
    for word in words:
        candidate = f"{slug}-{word}" if slug else word
        if slug and len(candidate) > max_len:
            break
        slug = candidate
    return slug[:max_len] or "goal"


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
