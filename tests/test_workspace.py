import subprocess
from pathlib import Path

import pytest

from goals.git_ops import untracked_paths
from goals.runtime import (
    active_goal_dir,
    create_goal,
    load_active_snapshot,
    resolve_workspace,
)
from goals.storage import GoalsError
from goals.workflows import render_start_workflow, start_workflow


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
def test_slugify_keeps_whole_words_and_stays_short() -> None:
    from goals.git_ops import slugify

    slug = slugify("Build a tiny tip-split CLI that divides a bill by N people")
    assert len(slug) <= 32
    assert not slug.endswith("-")
    # No mid-word truncation like the old 48-char hard cut ("…a-bill-b").
    assert all(part.isalnum() for part in slug.split("-"))
    assert slug.startswith("build")
    assert slugify("") == "goal"


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


def test_resolve_on_feature_branch_auto_defaults_in_place_but_ambiguous(tmp_path: Path) -> None:
    _git_repo(tmp_path, branch="feature")
    plan = resolve_workspace(tmp_path, requested="auto")
    assert plan.mode == "in_place"  # the calm, no-cd default
    assert plan.ambiguous is True  # caller may still prompt to offer a worktree


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


def test_new_in_place_still_protects_main(tmp_path: Path) -> None:
    # A fresh --new project starts on main; --in-place must not bypass protection.
    _git_repo(tmp_path, branch="main")
    plan = resolve_workspace(tmp_path, requested="in_place", new_project_created=True)
    assert plan.mode == "worktree"


def test_second_in_place_goal_is_refused(tmp_path: Path) -> None:
    _git_repo(tmp_path, branch="feature")
    create_goal("first goal", tmp_path, workspace="in_place")
    with pytest.raises(GoalsError, match="already active here"):
        create_goal("second goal", tmp_path, workspace="in_place")
    # The escape hatch is a worktree.
    snapshot = create_goal("second goal", tmp_path, workspace="worktree")
    assert Path(snapshot.topology.worktree_path) != tmp_path


def test_in_place_slug_collision_is_refused_not_merged(tmp_path: Path) -> None:
    # Two different objectives that slugify to the same id must not silently
    # merge into one goal's event log.
    _git_repo(tmp_path, branch="feature")
    create_goal("Build the API!", tmp_path, workspace="in_place")
    with pytest.raises(GoalsError, match="already active here"):
        create_goal("Build the API?", tmp_path, workspace="in_place")
    # The first goal's log is intact — its objective is unchanged.
    assert load_active_snapshot(tmp_path).objective == "Build the API!"


def test_dirty_tree_only_blocks_worktree_not_in_place(tmp_path: Path) -> None:
    _git_repo(tmp_path, branch="feature")
    (tmp_path / "dirty.txt").write_text("x")  # uncommitted change
    # in-place is fine while you're actively working...
    create_goal("in place ok", tmp_path, workspace="in_place")
    # ...but a worktree off a dirty base is refused.
    with pytest.raises(GoalsError, match="dirty working tree"):
        create_goal("worktree blocked", tmp_path, workspace="worktree")


# --- untracked files do not block a new working folder -------------------- #
def test_create_goal_still_refuses_untracked_files_unless_told_otherwise(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "notes.txt").write_text("x")
    with pytest.raises(GoalsError, match="dirty working tree"):
        create_goal("strict by default", tmp_path, workspace="worktree")


def test_untracked_only_tree_does_not_block_a_worktree_start(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plan.md").write_text("y")

    snapshot = create_goal(
        "worktree with notes", tmp_path, workspace="worktree", allow_untracked=True
    )

    worktree = Path(snapshot.topology.worktree_path)
    assert worktree.is_dir()
    assert (tmp_path / "notes.txt").exists()  # untracked files stay in the main checkout
    assert not (worktree / "notes.txt").exists()


def test_untracked_files_do_not_hide_a_tracked_change(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "README.md").write_text("# changed\n")
    with pytest.raises(GoalsError, match="dirty working tree"):
        create_goal("blocked", tmp_path, workspace="worktree", allow_untracked=True)


def test_a_staged_new_file_still_blocks_a_worktree_start(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "new.txt").write_text("x")
    _run(["git", "add", "new.txt"], tmp_path)
    with pytest.raises(GoalsError, match="dirty working tree"):
        create_goal("blocked", tmp_path, workspace="worktree", allow_untracked=True)


def test_untracked_paths_names_files_inside_new_folders(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "docs" / "plans").mkdir(parents=True)
    (tmp_path / "docs" / "plans" / "a.md").write_text("x")
    (tmp_path / "top.txt").write_text("y")
    (tmp_path / "caf\u00e9 notes.md").write_text("z")
    (tmp_path / ".agent-workflow").mkdir()
    (tmp_path / ".agent-workflow" / "x.json").write_text("{}")
    (tmp_path / "README.md").write_text("# changed\n")  # tracked: never listed

    names = untracked_paths(tmp_path, ignored_prefixes=(".agent-workflow/", ".goals/"))

    assert names == ["caf\u00e9 notes.md", "docs/plans/a.md", "top.txt"]


def test_start_message_names_the_files_left_behind(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    (tmp_path / "notes.txt").write_text("x")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "plan.md").write_text("y")

    text = render_start_workflow(
        start_workflow("start with notes", tmp_path, agent="claude", workspace="worktree")
    )

    assert "Not copied into the new folder" in text
    assert "notes.txt" in text and "docs/plan.md" in text


def test_start_message_has_no_left_behind_line_on_a_clean_tree(tmp_path: Path) -> None:
    _git_repo(tmp_path)

    text = render_start_workflow(
        start_workflow("clean start", tmp_path, agent="claude", workspace="worktree")
    )

    assert "Not copied" not in text


def test_start_message_caps_the_left_behind_list(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    for index in range(7):
        (tmp_path / f"f{index}.txt").write_text("x")

    text = render_start_workflow(
        start_workflow("many untracked", tmp_path, agent="claude", workspace="worktree")
    )

    assert "f0.txt" in text and "f4.txt" in text
    assert "f5.txt" not in text
    assert "(+2 more)" in text


def test_untracked_paths_skips_the_source_path_of_a_staged_rename(tmp_path: Path) -> None:
    """`git status -z` follows a rename with its source path as a bare field; here the source
    is named like an untracked entry, so reading it as one would list a tracked file."""
    _git_repo(tmp_path)
    (tmp_path / "?? odd.txt").write_text("a")
    _run(["git", "add", "-A"], tmp_path)
    _run(["git", "commit", "-m", "odd name"], tmp_path)
    _run(["git", "mv", "?? odd.txt", "renamed.txt"], tmp_path)
    (tmp_path / "x.txt").write_text("y")

    assert untracked_paths(tmp_path) == ["x.txt"]


def test_start_message_keeps_odd_file_names_on_one_line(tmp_path: Path) -> None:
    _git_repo(tmp_path)
    try:
        (tmp_path / "new\nline.txt").write_text("x")
        (tmp_path / "back`tick.txt").write_text("x")
    except OSError:
        pytest.skip("this file system rejects these names")

    text = render_start_workflow(
        start_workflow("odd names", tmp_path, agent="claude", workspace="worktree")
    )

    note = [line for line in text.splitlines() if line.startswith("Not copied")]
    assert len(note) == 1
    assert "new?line.txt" in note[0] and "back?tick.txt" in note[0]
