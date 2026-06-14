import subprocess
from pathlib import Path

import pytest

from goals.runtime import (
    active_goal_dir,
    create_goal,
    load_active_snapshot,
    resolve_workspace,
)
from goals.storage import GoalsError


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _git_repo(path: Path, *, branch: str = "main") -> None:
    _run(["git", "init", "-b", branch], path)
    _run(["git", "config", "user.email", "t@example.com"], path)
    _run(["git", "config", "user.name", "T"], path)
    (path / "README.md").write_text("# demo\n")
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-m", "init"], path)


# --- resolver (pure) ------------------------------------------------------- #
def test_resolve_non_git_dir_is_in_place(tmp_path: Path) -> None:
    plan = resolve_workspace(tmp_path)
    assert plan.mode == "in_place"
    assert plan.is_git is False
    assert plan.base_branch == ""


def test_resolve_on_main_forces_worktree_even_when_in_place_requested(tmp_path: Path) -> None:
    _git_repo(tmp_path, branch="main")
    plan = resolve_workspace(tmp_path, requested="in_place")
    assert plan.mode == "worktree"  # main is protected
    assert plan.ambiguous is False


def test_resolve_on_feature_branch_auto_is_ambiguous_worktree(tmp_path: Path) -> None:
    _git_repo(tmp_path, branch="feature")
    plan = resolve_workspace(tmp_path, requested="auto")
    assert plan.mode == "worktree"
    assert plan.ambiguous is True  # caller may prompt


def test_resolve_feature_branch_in_place_honored(tmp_path: Path) -> None:
    _git_repo(tmp_path, branch="feature")
    plan = resolve_workspace(tmp_path, requested="in_place")
    assert plan.mode == "in_place"
    assert plan.ambiguous is False


# --- create_goal end to end ------------------------------------------------ #
def test_start_on_main_creates_a_worktree(tmp_path: Path) -> None:
    _git_repo(tmp_path, branch="main")
    snapshot = create_goal("evaluate things", tmp_path)
    worktree = Path(snapshot.topology.worktree_path)
    assert worktree != tmp_path  # isolated, not the base checkout
    assert snapshot.topology.branch.startswith("goal/")
    assert worktree.exists()


def test_start_in_place_on_feature_branch(tmp_path: Path) -> None:
    _git_repo(tmp_path, branch="feature")
    snapshot = create_goal("do the thing", tmp_path, workspace="in_place")
    assert Path(snapshot.topology.worktree_path) == tmp_path
    assert snapshot.topology.branch == "feature"
    # State is in the current repo, so it resolves from here with no cd.
    assert active_goal_dir(tmp_path).parent.name == "goals"
    assert load_active_snapshot(tmp_path).objective == "do the thing"


def test_start_in_a_non_git_directory_works_in_place(tmp_path: Path) -> None:
    snapshot = create_goal("offline notes goal", tmp_path)
    assert Path(snapshot.topology.worktree_path) == tmp_path.resolve()
    assert snapshot.topology.base_branch == ""
    # Full non-git support: state lives here and loads back without git.
    assert (tmp_path / ".agent-workflow" / "goals").is_dir()
    assert load_active_snapshot(tmp_path).objective == "offline notes goal"


def test_force_worktree_on_feature_branch(tmp_path: Path) -> None:
    _git_repo(tmp_path, branch="feature")
    snapshot = create_goal("isolate me", tmp_path, workspace="worktree")
    assert Path(snapshot.topology.worktree_path) != tmp_path


def test_dirty_tree_only_blocks_worktree_not_in_place(tmp_path: Path) -> None:
    _git_repo(tmp_path, branch="feature")
    (tmp_path / "dirty.txt").write_text("x")  # uncommitted change
    # in-place is fine while you're actively working...
    create_goal("in place ok", tmp_path, workspace="in_place")
    # ...but a worktree off a dirty base is refused.
    with pytest.raises(GoalsError, match="dirty working tree"):
        create_goal("worktree blocked", tmp_path, workspace="worktree")
