import subprocess
from pathlib import Path

import pytest

from goals import runtime
from goals.cli import _phase_or_error
from goals.git_ops import (
    create_worktree,
    current_branch,
    git_root,
    goal_worktrees,
    require_clean_repo,
)
from goals.models import GoalSnapshot, Phase, WorktreeLease
from goals.runtime import active_goal_dir
from goals.storage import GoalsError


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _init_repo(path: Path) -> None:
    _run(["git", "init"], path)
    _run(["git", "config", "user.email", "test@example.com"], path)
    _run(["git", "config", "user.name", "Test User"], path)
    _run(["git", "commit", "--allow-empty", "-m", "init"], path)


def test_git_root_outside_a_repo_raises_clear_goals_error(tmp_path: Path, monkeypatch) -> None:
    # Previously surfaced a raw CalledProcessError traceback. The ceiling env
    # makes this deterministic even if the CI runner's TMPDIR is inside a repo:
    # git will not ascend above tmp_path while searching.
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    with pytest.raises(GoalsError, match="Not inside a git repository"):
        git_root(sandbox)


def test_no_active_goal_suggests_goals_start(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    with pytest.raises(GoalsError) as exc:
        active_goal_dir(tmp_path)
    message = str(exc.value)
    assert "No active goal" in message
    assert "goals start" in message


def test_no_active_goal_points_at_the_goal_worktree(tmp_path: Path, monkeypatch) -> None:
    # The exact mistake the user hit: running from the base checkout after
    # `goals start`. The error must name the worktree to cd into.
    _init_repo(tmp_path)
    fake_worktree = tmp_path / "repo-some-goal"
    monkeypatch.setattr(runtime, "goal_worktrees", lambda repo: [fake_worktree])
    with pytest.raises(GoalsError) as exc:
        active_goal_dir(tmp_path)
    message = str(exc.value)
    assert str(fake_worktree) in message
    assert "cd " in message and "worktree" in message.lower()


def test_goal_worktrees_finds_worktree_holding_state(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    _init_repo(base)
    worktree = tmp_path / "base-goal"
    _run(["git", "worktree", "add", "-b", "goal/x", str(worktree)], base)
    # A plain worktree without goal state must NOT be reported...
    assert goal_worktrees(base) == []
    # ...but one with goal.json state must be.
    state = worktree / ".agent-workflow" / "goals" / "x"
    state.mkdir(parents=True)
    (state / "goal.json").write_text("{}")
    assert worktree.resolve() in [p.resolve() for p in goal_worktrees(base)]


def test_goal_worktrees_handles_paths_with_spaces(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    _init_repo(base)
    worktree = tmp_path / "base with space"
    _run(["git", "worktree", "add", "-b", "goal/y", str(worktree)], base)
    state = worktree / ".agent-workflow" / "goals" / "y"
    state.mkdir(parents=True)
    (state / "goal.json").write_text("{}")
    assert worktree.resolve() in [p.resolve() for p in goal_worktrees(base)]


def test_unreadable_multiple_goals_message_names_them(tmp_path: Path) -> None:
    # Goal dirs with no goal.json are corrupt; the error names them + points to repair.
    _init_repo(tmp_path)
    for name in ("alpha", "beta"):
        (tmp_path / ".agent-workflow" / "goals" / name).mkdir(parents=True)
    with pytest.raises(GoalsError) as exc:
        active_goal_dir(tmp_path)
    message = str(exc.value)
    assert "No readable goal" in message
    assert "alpha" in message and "beta" in message


def test_multiple_in_place_goals_resolve_to_most_recent(tmp_path: Path) -> None:
    # Several valid in-place goals in one dir resolve to the most recently updated
    # instead of bricking.
    _init_repo(tmp_path)
    goals_root = tmp_path / ".agent-workflow" / "goals"
    for name, updated in (("old", "2026-01-01T00:00:00+00:00"), ("new", "2026-06-01T00:00:00+00:00")):
        d = goals_root / name
        d.mkdir(parents=True)
        (d / "goal.json").write_text(f'{{"last_updated": "{updated}"}}')
    assert active_goal_dir(tmp_path).name == "new"


def test_dirty_tree_message_states_the_fix(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    (tmp_path / "dirty.txt").write_text("x")
    with pytest.raises(GoalsError, match="Commit or stash"):
        require_clean_repo(tmp_path)


def test_detached_head_message_states_the_fix(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout.strip()
    _run(["git", "checkout", "--detach", head], tmp_path)
    with pytest.raises(GoalsError, match="Check out a branch"):
        current_branch(tmp_path)


def test_existing_branch_message_states_the_fix(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    _init_repo(base)
    _run(["git", "branch", "goal/dup"], base)
    with pytest.raises(GoalsError, match="git branch -D goal/dup"):
        create_worktree(base, "dup", "objective")


def test_unknown_phase_id_lists_valid_phases(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="g",
        objective="o",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="b",
        ),
        phases=[
            Phase(phase_id="P1", title="a", goal="g"),
            Phase(phase_id="P2", title="b", goal="g"),
        ],
        current_phase="P1",
    )
    with pytest.raises(GoalsError, match="Valid phases: P1, P2"):
        _phase_or_error(snapshot, "P9")
