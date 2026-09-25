"""A user checkpoint closes on the user's recorded reply, not the agent's word.

The UserPromptSubmit hook records the user's own typed message while a goal waits
on them. Passing or waiving a user checkpoint must cite such a reply — recorded
after the checkpoint was put to the user — or say --unverified, which every view
shows as not verified. (Roadmap: Discovery build step 2.)
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from goals.agent_hooks import MAX_USER_MESSAGE_CHARS, record_user_prompt
from goals.checkpoint_workflows import record_checkpoint, waive_checkpoint
from goals.cli import app
from goals.models import CheckpointKind, CheckpointStatus
from goals.runtime import create_goal, load_active_snapshot
from goals.setup import CODEX_USER_PROMPT_COMMAND, setup_agents
from goals.storage import GoalsError

ASK = ["checkpoint", "record", "P1", "alignment", "--kind", "understanding"]


def _git_repo(path: Path) -> Path:
    path.mkdir()
    for cmd in (
        ["git", "init", "-q", "-b", "feature"],
        ["git", "config", "user.email", "t@e.com"],
        ["git", "config", "user.name", "T"],
    ):
        subprocess.run(cmd, cwd=path, check=True)
    (path / "README.md").write_text("# demo\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    repo = _git_repo(tmp_path / "repo")
    create_goal("ship it", repo, workspace="in_place")
    monkeypatch.chdir(repo)
    return repo


def _say(repo: Path, text: str) -> None:
    result = CliRunner().invoke(
        app, ["hooks", "user-prompt"], input=json.dumps({"prompt": text, "cwd": str(repo)})
    )
    assert result.exit_code == 0 and result.stdout == ""


def _alignment(repo: Path):
    return next(c for c in load_active_snapshot(repo).phases[0].checkpoints if c.checkpoint_id == "alignment")


def test_passing_a_waiting_checkpoint_needs_a_recorded_reply(repo: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, [*ASK, "--status", "needs_user"]).exit_code == 0

    refused = runner.invoke(app, [*ASK, "--status", "passed"])
    assert refused.exit_code == 1
    assert "no reply from them has been recorded" in refused.stdout

    _say(repo, "Yes — that's exactly it.")
    assert runner.invoke(app, [*ASK, "--status", "passed"]).exit_code == 0
    checkpoint = _alignment(repo)
    assert checkpoint.status == CheckpointStatus.PASSED
    message = load_active_snapshot(repo).user_messages[-1]
    assert checkpoint.user_message_id == message.message_id
    assert message.text == "Yes — that's exactly it."
    listed = runner.invoke(app, ["checkpoint", "list"]).stdout
    assert 'User said: "Yes — that\'s exactly it."' in listed


def test_a_reply_from_before_the_question_does_not_count(repo: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, [*ASK, "--status", "needs_user"]).exit_code == 0
    _say(repo, "sure")
    # Re-asking (e.g. after a correction) resets the clock: the old "sure" no longer answers it.
    assert runner.invoke(app, [*ASK, "--status", "needs_user", "--summary", "revised"]).exit_code == 0
    assert runner.invoke(app, [*ASK, "--status", "passed"]).exit_code == 1
    _say(repo, "yes, the revised one")
    assert runner.invoke(app, [*ASK, "--status", "passed"]).exit_code == 0
    assert load_active_snapshot(repo).user_messages[-1].text == "yes, the revised one"


def test_unverified_closes_it_but_says_so_everywhere(repo: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, [*ASK, "--status", "needs_user"]).exit_code == 0
    assert runner.invoke(app, [*ASK, "--status", "passed", "--unverified"]).exit_code == 0
    checkpoint = _alignment(repo)
    assert checkpoint.unverified is True and checkpoint.user_message_id == ""
    note = "Not verified: closed without a recorded reply from the user."
    assert note in runner.invoke(app, ["checkpoint", "list"]).stdout
    check = runner.invoke(app, ["check"]).stdout
    assert "## What You Confirmed" in check and note in check


def test_waive_is_held_to_the_same_rule(repo: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, [*ASK, "--status", "needs_user"]).exit_code == 0
    waive = ["checkpoint", "waive", "P1", "alignment", "--reason", "User said skip it"]
    assert runner.invoke(app, waive).exit_code == 1
    _say(repo, "skip it, just build")
    assert runner.invoke(app, waive).exit_code == 0
    assert _alignment(repo).status == CheckpointStatus.WAIVED
    assert _alignment(repo).user_message_id


def test_a_user_check_never_put_to_the_user_cannot_be_closed_quietly(repo: Path) -> None:
    runner = CliRunner()
    feel = ["checkpoint", "record", "P4", "feel", "--kind", "human_validation"]
    assert runner.invoke(app, [*feel, "--status", "pending"]).exit_code == 0
    refused = runner.invoke(app, [*feel, "--status", "passed"])
    assert refused.exit_code == 1 and "hasn't been put to them yet" in refused.stdout
    waived = runner.invoke(app, ["checkpoint", "waive", "P4", "feel", "--reason", "n/a"])
    assert waived.exit_code == 1
    # A brand-new user checkpoint recorded straight as passed is refused too.
    fresh = runner.invoke(
        app, ["checkpoint", "record", "P2", "ok", "--kind", "approval", "--status", "passed"]
    )
    assert fresh.exit_code == 1


def test_omitting_kind_on_update_keeps_the_user_kind(repo: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, [*ASK, "--status", "needs_user"]).exit_code == 0
    bare = ["checkpoint", "record", "P1", "alignment", "--status", "passed"]
    assert runner.invoke(app, bare).exit_code == 1
    assert _alignment(repo).kind == CheckpointKind.UNDERSTANDING


def test_agent_checkpoints_still_close_freely(repo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["checkpoint", "record", "P1", "lint", "--status", "passed"])
    assert result.exit_code == 0
    lint = next(c for c in load_active_snapshot(repo).phases[0].checkpoints if c.checkpoint_id == "lint")
    assert lint.kind == CheckpointKind.CUSTOM and not lint.unverified


def test_cited_message_must_be_a_reply_to_this_question(repo: Path) -> None:
    _say(repo, "unrelated earlier chat")  # nothing waits: not recorded
    assert load_active_snapshot(repo).user_messages == []
    record_checkpoint(repo, "P1", "alignment", kind=CheckpointKind.UNDERSTANDING, status=CheckpointStatus.NEEDS_USER)
    _say(repo, "first answer")
    _say(repo, "second answer")
    first = load_active_snapshot(repo).user_messages[0]
    with pytest.raises(GoalsError, match="is not a reply recorded after"):
        record_checkpoint(repo, "P1", "alignment", status=CheckpointStatus.PASSED, user_message_id="UM-bogus")
    closed = record_checkpoint(
        repo, "P1", "alignment", status=CheckpointStatus.PASSED, user_message_id=first.message_id
    )
    assert closed.user_message_id == first.message_id
    # Re-recording an already-closed checkpoint keeps its original provenance.
    again = record_checkpoint(repo, "P1", "alignment", status=CheckpointStatus.PASSED, summary="tidy")
    assert again.user_message_id == first.message_id


def test_hook_is_silent_and_fail_open(repo: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    for stdin in ("", "not json", "[1, 2]", json.dumps({"prompt": 42})):
        result = runner.invoke(app, ["hooks", "user-prompt"], input=stdin)
        assert result.exit_code == 0 and result.stdout == ""
    elsewhere = tmp_path / "no-goal-here"
    elsewhere.mkdir()
    assert record_user_prompt(elsewhere, "hello") == 0


def test_hook_records_only_while_waiting_and_clips_long_text(repo: Path) -> None:
    assert record_user_prompt(repo, "just chatting") == 0
    record_checkpoint(repo, "P1", "alignment", kind=CheckpointKind.UNDERSTANDING, status=CheckpointStatus.NEEDS_USER)
    assert record_user_prompt(repo, "   ") == 0
    assert record_user_prompt(repo, "x" * (MAX_USER_MESSAGE_CHARS + 50)) == 1
    text = load_active_snapshot(repo).user_messages[-1].text
    assert len(text) == MAX_USER_MESSAGE_CHARS and text.endswith("…")


def test_hook_finds_a_worktree_goal_from_the_base_checkout(tmp_path: Path, monkeypatch) -> None:
    base = _git_repo(tmp_path / "base")
    snapshot = create_goal("parallel goal", base, workspace="worktree")
    worktree = Path(snapshot.topology.worktree_path)
    assert worktree != base
    monkeypatch.chdir(worktree)
    record_checkpoint(worktree, "P1", "alignment", kind=CheckpointKind.UNDERSTANDING, status=CheckpointStatus.NEEDS_USER)
    # The session's cwd is the base checkout; the goal lives in the worktree.
    assert record_user_prompt(base, "yes from the base checkout") == 1
    assert load_active_snapshot(worktree).user_messages[-1].text == "yes from the base checkout"


def test_user_words_stay_local(repo: Path) -> None:
    record_checkpoint(repo, "P1", "alignment", kind=CheckpointKind.UNDERSTANDING, status=CheckpointStatus.NEEDS_USER)
    _say(repo, "my private reply 7f3a")
    record_checkpoint(repo, "P1", "alignment", status=CheckpointStatus.PASSED)
    exported = "".join(p.read_text() for p in (repo / ".goals").rglob("*") if p.is_file())
    assert "7f3a" not in exported


def test_dashboard_shows_the_reply_escaped(repo: Path) -> None:
    record_checkpoint(repo, "P1", "alignment", kind=CheckpointKind.UNDERSTANDING, status=CheckpointStatus.NEEDS_USER)
    _say(repo, "yes <script>alert(1)</script>")
    record_checkpoint(repo, "P1", "alignment", status=CheckpointStatus.PASSED)
    assert CliRunner().invoke(app, ["dashboard"]).exit_code == 0
    html = next((repo / ".agent-workflow" / "goals").glob("*/dashboard.html")).read_text()
    assert "What you confirmed" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>alert(1)" not in html


def test_waive_function_matches_cli(repo: Path) -> None:
    record_checkpoint(repo, "P1", "alignment", kind=CheckpointKind.UNDERSTANDING, status=CheckpointStatus.NEEDS_USER)
    with pytest.raises(GoalsError):
        waive_checkpoint(repo, "P1", "alignment", "skip")
    waived = waive_checkpoint(repo, "P1", "alignment", "skip", unverified=True)
    assert waived.unverified and waived.status == CheckpointStatus.WAIVED


def test_codex_setup_adds_the_hook_once_and_keeps_other_hooks(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    other = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "other"}]}]}}
    (codex_home / "hooks.json").write_text(json.dumps(other))

    first = setup_agents(["codex"], codex_home=codex_home)
    data = json.loads((codex_home / "hooks.json").read_text())
    assert data["hooks"]["Stop"] == other["hooks"]["Stop"]
    commands = [h["command"] for g in data["hooks"]["UserPromptSubmit"] for h in g["hooks"]]
    assert commands == [CODEX_USER_PROMPT_COMMAND]
    assert any("user-prompt hook" in a.detail and a.changed for a in first.actions)

    second = setup_agents(["codex"], codex_home=codex_home)
    again = json.loads((codex_home / "hooks.json").read_text())
    assert again == data
    assert any(a.detail == "user-prompt hook already configured" for a in second.actions)


def test_codex_setup_writes_through_a_symlinked_hooks_file(tmp_path: Path) -> None:
    dotfiles = tmp_path / "dotfiles"
    dotfiles.mkdir()
    real = dotfiles / "hooks.json"
    real.write_text(json.dumps({"hooks": {}}))
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    os.symlink(real, codex_home / "hooks.json")

    setup_agents(["codex"], codex_home=codex_home)
    assert (codex_home / "hooks.json").is_symlink()
    assert "UserPromptSubmit" in json.loads(real.read_text())["hooks"]


def test_codex_setup_dry_run_changes_nothing(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    setup_agents(["codex"], codex_home=codex_home, dry_run=True)
    assert not (codex_home / "hooks.json").exists()
