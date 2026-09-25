"""A user checkpoint closes on the user's recorded reply, not the agent's word.

The UserPromptSubmit hook records the user's own typed message in the goal that
is waiting on them. Passing or waiving a user checkpoint must cite such a reply —
recorded after the checkpoint was put to the user, and not already used to close
another — or say --unverified, which every view shows as not verified.
(Roadmap: Discovery build step 2.)
"""

import json
import os
import subprocess
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from goals.agent_hooks import MAX_USER_MESSAGE_CHARS, record_user_prompt
from goals.checkpoint_workflows import record_checkpoint, waive_checkpoint
from goals.cli import app
from goals.models import CheckpointKind, CheckpointStatus, GoalStatus
from goals.runtime import create_goal, load_active_snapshot
from goals.setup import CODEX_USER_PROMPT_COMMAND, setup_agents
from goals.storage import EventStore, GoalsError, lock_file

ASK = ["checkpoint", "record", "P1", "alignment", "--kind", "understanding"]
REPO_ROOT = Path(__file__).resolve().parents[1]


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


def _payload(text: str, cwd: Path) -> str:
    return json.dumps(
        {"hook_event_name": "UserPromptSubmit", "prompt": text, "cwd": str(cwd), "session_id": "s-1"}
    )


def _say(cwd: Path, text: str) -> None:
    result = CliRunner().invoke(app, ["hooks", "user-prompt"], input=_payload(text, cwd))
    assert result.exit_code == 0 and result.stdout == ""


def _ask(cwd: Path, checkpoint_id: str = "alignment", **kwargs) -> None:
    record_checkpoint(
        cwd,
        kwargs.pop("phase", "P1"),
        checkpoint_id,
        kind=kwargs.pop("kind", CheckpointKind.UNDERSTANDING),
        status=CheckpointStatus.NEEDS_USER,
        **kwargs,
    )


def _checkpoint(cwd: Path, checkpoint_id: str = "alignment", phase: int = 0):
    phases = load_active_snapshot(cwd).phases
    return next(c for c in phases[phase].checkpoints if c.checkpoint_id == checkpoint_id)


# --------------------------------------------------------------------------- #
# Closing rules
# --------------------------------------------------------------------------- #
def test_passing_a_waiting_checkpoint_needs_a_recorded_reply(repo: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, [*ASK, "--status", "needs_user"]).exit_code == 0

    refused = runner.invoke(app, [*ASK, "--status", "passed"])
    assert refused.exit_code == 1
    assert "no reply from them has been recorded" in refused.stdout

    _say(repo, "Yes — that's exactly it.")
    closed = runner.invoke(app, [*ASK, "--status", "passed"])
    assert closed.exit_code == 0
    assert "Closed on the user's reply: \"Yes — that's exactly it.\"" in closed.stdout
    checkpoint = _checkpoint(repo)
    message = load_active_snapshot(repo).user_messages[-1]
    assert checkpoint.status == CheckpointStatus.PASSED
    assert checkpoint.user_message_id == message.message_id
    assert message.session_id == "s-1"


def test_a_reply_from_before_the_question_does_not_count(repo: Path) -> None:
    _ask(repo)
    _say(repo, "sure")
    early = load_active_snapshot(repo).user_messages[-1]
    # Re-asking (e.g. after a correction) resets the clock: the old "sure" no longer answers it.
    _ask(repo, summary="revised")
    with pytest.raises(GoalsError):
        record_checkpoint(repo, "P1", "alignment", status=CheckpointStatus.PASSED)
    with pytest.raises(GoalsError, match="isn't an unused reply"):
        record_checkpoint(
            repo, "P1", "alignment", status=CheckpointStatus.PASSED, user_message_id=early.message_id
        )
    _say(repo, "yes, the revised one")
    closed = record_checkpoint(repo, "P1", "alignment", status=CheckpointStatus.PASSED)
    assert closed.user_message_id == load_active_snapshot(repo).user_messages[-1].message_id


def test_one_reply_closes_one_question(repo: Path) -> None:
    _ask(repo, "first")
    _ask(repo, "second", kind=CheckpointKind.APPROVAL)
    _say(repo, "yes")
    record_checkpoint(repo, "P1", "first", status=CheckpointStatus.PASSED)
    with pytest.raises(GoalsError):
        record_checkpoint(repo, "P1", "second", status=CheckpointStatus.PASSED)


def test_unverified_closes_it_but_says_so_everywhere(repo: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, [*ASK, "--status", "needs_user"]).exit_code == 0
    closed = runner.invoke(app, [*ASK, "--status", "passed", "--unverified"])
    assert closed.exit_code == 0
    note = "Not verified: closed without a recorded reply from the user."
    assert note in closed.stdout
    checkpoint = _checkpoint(repo)
    assert checkpoint.unverified is True and checkpoint.user_message_id == ""
    assert note in runner.invoke(app, ["checkpoint", "list"]).stdout
    check = runner.invoke(app, ["check"]).stdout
    assert "## Your Replies On Record" in check and note in check


def test_waive_is_held_to_the_same_rule(repo: Path) -> None:
    runner = CliRunner()
    assert runner.invoke(app, [*ASK, "--status", "needs_user"]).exit_code == 0
    waive = ["checkpoint", "waive", "P1", "alignment", "--reason", "User said skip it"]
    assert runner.invoke(app, waive).exit_code == 1
    _say(repo, "skip it, just build")
    assert runner.invoke(app, waive).exit_code == 0
    assert _checkpoint(repo).status == CheckpointStatus.WAIVED
    assert _checkpoint(repo).user_message_id
    with pytest.raises(GoalsError):
        _ask(repo, "other")
        waive_checkpoint(repo, "P1", "other", "skip")
    assert waive_checkpoint(repo, "P1", "other", "skip", unverified=True).unverified


def test_a_user_check_never_put_to_the_user_cannot_be_closed_quietly(repo: Path) -> None:
    runner = CliRunner()
    feel = ["checkpoint", "record", "P4", "feel", "--kind", "human_validation"]
    assert runner.invoke(app, [*feel, "--status", "pending"]).exit_code == 0
    refused = runner.invoke(app, [*feel, "--status", "passed"])
    assert refused.exit_code == 1 and "hasn't been put to them yet" in refused.stdout
    waived = runner.invoke(app, ["checkpoint", "waive", "P4", "feel", "--reason", "n/a"])
    assert waived.exit_code == 1
    fresh = runner.invoke(
        app, ["checkpoint", "record", "P2", "ok", "--kind", "approval", "--status", "passed"]
    )
    assert fresh.exit_code == 1


# --------------------------------------------------------------------------- #
# Updates can't shed the user's ownership (review cycle: defaults overwrote state)
# --------------------------------------------------------------------------- #
def test_omitting_kind_on_update_keeps_the_user_kind(repo: Path) -> None:
    _ask(repo)
    _say(repo, "yes")
    closed = record_checkpoint(repo, "P1", "alignment", status=CheckpointStatus.PASSED)
    assert closed.kind == CheckpointKind.UNDERSTANDING and closed.user_message_id


def test_a_bare_update_keeps_status_instead_of_closing_on_a_question(repo: Path) -> None:
    _ask(repo, "plan", kind=CheckpointKind.APPROVAL)
    _say(repo, "wait, what does step 3 mean?")
    result = CliRunner().invoke(app, ["checkpoint", "record", "P1", "plan", "--summary", "clarified"])
    assert result.exit_code == 0
    kept = _checkpoint(repo, "plan")
    assert kept.status == CheckpointStatus.NEEDS_USER and kept.needs_user and kept.required


def test_unasking_or_relabelling_cannot_shed_ownership(repo: Path) -> None:
    # A custom checkpoint put to the user stays the user's after "--status pending".
    record_checkpoint(repo, "P1", "custom", status=CheckpointStatus.NEEDS_USER)
    record_checkpoint(repo, "P1", "custom", status=CheckpointStatus.PENDING, needs_user=False)
    with pytest.raises(GoalsError):
        record_checkpoint(repo, "P1", "custom", status=CheckpointStatus.PASSED)
    # A user kind swapped to custom stays the user's too.
    _ask(repo, "approve", kind=CheckpointKind.APPROVAL)
    record_checkpoint(
        repo, "P1", "approve", kind=CheckpointKind.CUSTOM, status=CheckpointStatus.PENDING
    )
    with pytest.raises(GoalsError):
        record_checkpoint(repo, "P1", "approve", status=CheckpointStatus.PASSED)
    assert _checkpoint(repo, "approve").user_owned


def test_relabelling_a_closed_agent_checkpoint_as_the_users_is_refused(repo: Path) -> None:
    record_checkpoint(repo, "P1", "sneaky", status=CheckpointStatus.PASSED)
    with pytest.raises(GoalsError, match="hasn't been put to them yet"):
        record_checkpoint(
            repo, "P1", "sneaky", kind=CheckpointKind.UNDERSTANDING, status=CheckpointStatus.PASSED
        )


def test_an_optional_user_checkpoint_closes_on_a_real_reply(repo: Path) -> None:
    _ask(repo, "nice-to-have", required=False)
    _say(repo, "yes please")
    closed = record_checkpoint(repo, "P1", "nice-to-have", status=CheckpointStatus.PASSED)
    assert closed.user_message_id and not closed.required


def test_already_closed_user_checkpoint_keeps_its_provenance(repo: Path) -> None:
    _ask(repo)
    _say(repo, "yes")
    first = record_checkpoint(repo, "P1", "alignment", status=CheckpointStatus.PASSED)
    again = record_checkpoint(repo, "P1", "alignment", status=CheckpointStatus.PASSED, summary="tidy")
    assert again.user_message_id == first.user_message_id


def test_agent_checkpoints_still_close_freely(repo: Path) -> None:
    result = CliRunner().invoke(app, ["checkpoint", "record", "P1", "lint", "--status", "passed"])
    assert result.exit_code == 0
    lint = _checkpoint(repo, "lint")
    assert lint.kind == CheckpointKind.CUSTOM and not lint.unverified and not lint.user_owned


# --------------------------------------------------------------------------- #
# The hook: silent, scoped, host-shaped
# --------------------------------------------------------------------------- #
def test_hook_is_silent_fail_open_and_hidden(repo: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    for stdin in ("", "not json", "[1, 2]", json.dumps({"prompt": 42})):
        result = runner.invoke(app, ["hooks", "user-prompt"], input=stdin)
        assert result.exit_code == 0 and result.stdout == ""
    assert "user-prompt" not in runner.invoke(app, ["hooks", "--help"]).stdout
    elsewhere = tmp_path / "no-goal-here"
    elsewhere.mkdir()
    assert record_user_prompt(elsewhere, "hello") == 0


def test_hook_needs_the_hosts_event_shape(repo: Path) -> None:
    _ask(repo)
    bare = json.dumps({"prompt": "yes", "cwd": str(repo)})
    assert CliRunner().invoke(app, ["hooks", "user-prompt"], input=bare).exit_code == 0
    assert load_active_snapshot(repo).user_messages == []
    _say(repo, "yes")
    assert len(load_active_snapshot(repo).user_messages) == 1


def test_hook_records_only_while_asked_and_clips_long_text(repo: Path) -> None:
    assert record_user_prompt(repo, "just chatting") == 0
    _ask(repo)
    assert record_user_prompt(repo, "   ") == 0
    assert record_user_prompt(repo, "/goals:next") == 0  # a command, not an answer
    assert record_user_prompt(repo, "x" * (MAX_USER_MESSAGE_CHARS + 50)) == 1
    text = load_active_snapshot(repo).user_messages[-1].text
    assert len(text) == MAX_USER_MESSAGE_CHARS and text.endswith("…")


def test_hook_skips_goals_that_are_not_active(repo: Path, monkeypatch) -> None:
    _ask(repo)
    real = EventStore.snapshot

    def paused(self):
        snapshot = real(self)
        snapshot.status = GoalStatus.PAUSED
        return snapshot

    monkeypatch.setattr(EventStore, "snapshot", paused)
    assert record_user_prompt(repo, "yes") == 0


def test_hook_finds_a_worktree_goal_from_the_base_checkout(tmp_path: Path, monkeypatch) -> None:
    base = _git_repo(tmp_path / "base")
    worktree = Path(create_goal("parallel goal", base, workspace="worktree").topology.worktree_path)
    assert worktree != base
    monkeypatch.chdir(worktree)
    _ask(worktree)
    # The session's cwd is the base checkout; the goal lives in the worktree.
    assert record_user_prompt(base, "yes from the base checkout") == 1
    assert load_active_snapshot(worktree).user_messages[-1].text == "yes from the base checkout"


def test_a_reply_for_one_goal_never_lands_in_another(tmp_path: Path, monkeypatch) -> None:
    base = _git_repo(tmp_path / "base")
    alpha = Path(create_goal("alpha goal", base, workspace="worktree").topology.worktree_path)
    beta = Path(create_goal("beta goal", base, workspace="worktree").topology.worktree_path)
    for worktree in (alpha, beta):
        monkeypatch.chdir(worktree)
        _ask(worktree, kind=CheckpointKind.APPROVAL)
    # From inside alpha's worktree, only alpha records the reply.
    assert record_user_prompt(alpha, "yes, go ahead") == 1
    assert [m.text for m in load_active_snapshot(alpha).user_messages] == ["yes, go ahead"]
    assert load_active_snapshot(beta).user_messages == []
    # From the base checkout, two waiting goals make it ambiguous: nobody records it.
    assert record_user_prompt(base, "yes") == 0
    monkeypatch.chdir(beta)
    with pytest.raises(GoalsError):
        record_checkpoint(beta, "P1", "alignment", status=CheckpointStatus.PASSED)


# --------------------------------------------------------------------------- #
# Privacy and views
# --------------------------------------------------------------------------- #
def test_user_words_stay_local(repo: Path) -> None:
    _ask(repo)
    _say(repo, "my private reply 7f3a")
    record_checkpoint(repo, "P1", "alignment", status=CheckpointStatus.PASSED)
    exported = "".join(p.read_text() for p in (repo / ".goals").rglob("*") if p.is_file())
    assert "7f3a" not in exported


def test_dashboard_shows_the_reply_escaped(repo: Path) -> None:
    _ask(repo)
    _say(repo, "yes <script>alert(1)</script>")
    record_checkpoint(repo, "P1", "alignment", status=CheckpointStatus.PASSED)
    assert CliRunner().invoke(app, ["dashboard"]).exit_code == 0
    html = next((repo / ".agent-workflow" / "goals").glob("*/dashboard.html")).read_text()
    assert "Your replies on record" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "<script>alert(1)" not in html


# --------------------------------------------------------------------------- #
# Reliability: locks and the hook wrapper
# --------------------------------------------------------------------------- #
def test_a_lock_left_by_a_dead_process_is_broken(repo: Path) -> None:
    dead = subprocess.Popen(["true"])
    dead.wait()
    goal_dir = next((repo / ".agent-workflow" / "goals").iterdir())
    (goal_dir / "events.jsonl.lock").write_text(str(dead.pid))
    _ask(repo)
    started = time.monotonic()
    assert record_user_prompt(repo, "yes") == 1
    assert time.monotonic() - started < 2


def test_a_live_lock_is_still_respected(tmp_path: Path) -> None:
    target = tmp_path / "events.jsonl"
    (tmp_path / "events.jsonl.lock").write_text(str(os.getpid()))
    with pytest.raises(GoalsError, match="Timed out"):
        with lock_file(target, timeout_seconds=0.2):
            pass


def test_bootstrap_never_lets_a_hook_block_the_session(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake = fake_bin / "goals"
    fake.write_text('#!/bin/sh\necho "from goals"\nexit 2\n')
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"}
    bootstrap = str(REPO_ROOT / "scripts" / "plugin-bootstrap.sh")
    hook = subprocess.run(
        ["sh", bootstrap, "hooks", "user-prompt"], env=env, capture_output=True, text=True
    )
    assert hook.returncode == 0 and "from goals" in hook.stdout
    other = subprocess.run(["sh", bootstrap, "status"], env=env, capture_output=True, text=True)
    assert other.returncode == 2  # non-hook commands still report failure


# --------------------------------------------------------------------------- #
# Codex wiring
# --------------------------------------------------------------------------- #
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
    assert CODEX_USER_PROMPT_COMMAND.endswith("|| true")
    assert any("saves what you type" in a.detail and a.changed for a in first.actions)

    second = setup_agents(["codex"], codex_home=codex_home)
    assert json.loads((codex_home / "hooks.json").read_text()) == data
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


def test_codex_setup_refuses_an_unexpected_hooks_shape(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    (codex_home / "hooks.json").write_text(json.dumps({"hooks": {"UserPromptSubmit": {}}}))
    with pytest.raises(GoalsError, match="unexpected shape"):
        setup_agents(["codex"], codex_home=codex_home)


def test_codex_setup_dry_run_changes_nothing(tmp_path: Path) -> None:
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    setup_agents(["codex"], codex_home=codex_home, dry_run=True)
    assert not (codex_home / "hooks.json").exists()


# --------------------------------------------------------------------------- #
# Re-review fixes: optional downgrade, session binding, scoping, edits
# --------------------------------------------------------------------------- #
def test_an_open_user_checkpoint_cannot_be_made_optional(repo: Path) -> None:
    _ask(repo, "appr", kind=CheckpointKind.APPROVAL)
    refused = CliRunner().invoke(app, ["checkpoint", "record", "P1", "appr", "--optional"])
    assert refused.exit_code == 1 and "can't be made optional" in refused.stdout
    assert _checkpoint(repo, "appr").required


def test_a_reply_only_counts_from_the_session_that_asked(repo: Path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "asking-session")
    _ask(repo, "prod", kind=CheckpointKind.APPROVAL)
    assert _checkpoint(repo, "prod").asked_session == "asking-session"
    # Chat typed in another session doesn't land in this goal at all.
    assert record_user_prompt(repo, "can you fix the README typo", session_id="other") == 0
    with pytest.raises(GoalsError):
        record_checkpoint(repo, "P1", "prod", status=CheckpointStatus.PASSED)
    assert record_user_prompt(repo, "yes, ship it", session_id="asking-session") == 1
    closed = record_checkpoint(repo, "P1", "prod", status=CheckpointStatus.PASSED)
    assert load_active_snapshot(repo).user_messages[-1].message_id == closed.user_message_id


def test_a_session_match_in_a_worktree_beats_the_ambiguity_rule(tmp_path: Path, monkeypatch) -> None:
    base = _git_repo(tmp_path / "base")
    alpha = Path(create_goal("alpha goal", base, workspace="worktree").topology.worktree_path)
    beta = Path(create_goal("beta goal", base, workspace="worktree").topology.worktree_path)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "session-a")
    monkeypatch.chdir(alpha)
    _ask(alpha, kind=CheckpointKind.APPROVAL)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "session-b")
    monkeypatch.chdir(beta)
    _ask(beta, kind=CheckpointKind.APPROVAL)
    # Both wait, from the base checkout — but the session says whose question it is.
    assert record_user_prompt(base, "yes", session_id="session-a") == 1
    assert [m.text for m in load_active_snapshot(alpha).user_messages] == ["yes"]
    assert load_active_snapshot(beta).user_messages == []


def test_a_leftover_goal_in_the_base_checkout_does_not_hide_worktree_goals(
    tmp_path: Path, monkeypatch
) -> None:
    base = _git_repo(tmp_path / "base")
    create_goal("old in-place goal", base, workspace="in_place")  # nothing waiting
    worktree = Path(create_goal("new goal", base, workspace="worktree").topology.worktree_path)
    monkeypatch.chdir(worktree)
    _ask(worktree)
    assert record_user_prompt(base, "yes") == 1
    assert load_active_snapshot(worktree).user_messages[-1].text == "yes"


def test_editing_an_asked_checkpoint_keeps_the_users_reply(repo: Path) -> None:
    _ask(repo, "plan", kind=CheckpointKind.APPROVAL)
    _say(repo, "approved")
    record_checkpoint(repo, "P1", "plan", summary="tidied wording")  # an edit, not a re-ask
    closed = record_checkpoint(repo, "P1", "plan", status=CheckpointStatus.PASSED)
    assert closed.user_message_id


def test_an_optional_question_still_shows_as_waiting_on_the_user(repo: Path) -> None:
    _ask(repo, "redis", kind=CheckpointKind.APPROVAL, required=False, title="Use Redis?")
    check = CliRunner().invoke(app, ["check"]).stdout
    assert "Waiting on: you" in check
    assert "optional question waiting on the user: Use Redis?" in check


def test_a_stamped_question_ignores_replies_from_other_sessions(repo: Path, monkeypatch) -> None:
    # An unstamped question in the same goal lets another session's message in;
    # the stamped question must still refuse to close on it.
    _ask(repo, "legacy", kind=CheckpointKind.APPROVAL)  # no host session known
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "asking-session")
    _ask(repo, "stamped", kind=CheckpointKind.APPROVAL)
    assert record_user_prompt(repo, "yes to legacy", session_id="other") == 1
    with pytest.raises(GoalsError):
        record_checkpoint(repo, "P1", "stamped", status=CheckpointStatus.PASSED)
    closed = record_checkpoint(repo, "P1", "legacy", status=CheckpointStatus.PASSED)
    assert closed.user_message_id
