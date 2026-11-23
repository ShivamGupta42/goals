import json
import os
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from goals.agent_hooks import session_start_payload, stop_payload
from goals.checkpoint_workflows import record_checkpoint
from goals.cli import app
from goals.models import CheckpointKind, CheckpointStatus, Event, EventType, GoalStatus
from goals.portability import render_context_block
from goals.runtime import create_goal, load_active_snapshot
from goals.storage import EventStore

REPO = Path(__file__).resolve().parents[1]
runner = CliRunner()


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _repo_with_goal(path: Path) -> None:
    _run(["git", "init", "-b", "feature"], path)
    _run(["git", "config", "user.email", "t@e.com"], path)
    _run(["git", "config", "user.name", "T"], path)
    _run(["git", "commit", "--allow-empty", "-m", "init"], path)
    create_goal("ship the plugin", path, workspace="in_place")


# --- hook backends --------------------------------------------------------- #
def test_session_start_injects_active_goal(tmp_path: Path) -> None:
    _repo_with_goal(tmp_path)
    payload = json.loads(session_start_payload(tmp_path))
    assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "ship the plugin" in payload["hookSpecificOutput"]["additionalContext"]


def test_session_start_is_silent_without_a_goal(tmp_path: Path) -> None:
    _run(["git", "init", "-b", "feature"], tmp_path)
    assert session_start_payload(tmp_path) == ""


def test_stop_is_a_noop_unless_enforced(tmp_path: Path) -> None:
    _repo_with_goal(tmp_path)
    assert stop_payload(tmp_path, enforce=False) == ""


def test_stop_blocks_when_enforced_and_work_remains(tmp_path: Path) -> None:
    _repo_with_goal(tmp_path)  # fresh goal: waiting on the agent
    payload = json.loads(stop_payload(tmp_path, enforce=True))
    assert payload["decision"] == "block"
    assert "ship the plugin" in payload["reason"]


def test_stop_is_silent_without_a_goal(tmp_path: Path) -> None:
    _run(["git", "init", "-b", "feature"], tmp_path)
    assert stop_payload(tmp_path, enforce=True) == ""


def test_stop_does_not_trap_a_paused_goal(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    from goals import agent_hooks
    from goals.models import GoalStatus

    real = agent_hooks.load_active_snapshot(tmp_path)
    paused = real.model_copy(update={"status": GoalStatus.PAUSED})
    monkeypatch.setattr(agent_hooks, "load_active_snapshot", lambda _cwd: paused)
    assert stop_payload(tmp_path, enforce=True) == ""


def _snapshot_with_reviews(tmp_path: Path, monkeypatch, reviews):
    """Return the active goal with ``reviews`` recorded on its current phase."""
    from goals import agent_hooks
    from goals.models import GateResult

    real = agent_hooks.load_active_snapshot(tmp_path)
    built = [
        GateResult(gate_id="phase-review", verdict=verdict, summary="x")
        for verdict in reviews
    ]
    phases = [
        phase.model_copy(update={"reviews": built})
        if phase.phase_id == real.current_phase
        else phase
        for phase in real.phases
    ]
    patched = real.model_copy(update={"phases": phases})
    monkeypatch.setattr(agent_hooks, "load_active_snapshot", lambda _cwd: patched)
    return patched


def test_stop_breaker_trips_on_blocked_verdict(tmp_path: Path, monkeypatch) -> None:
    from goals.models import GateVerdict

    _repo_with_goal(tmp_path)
    # The gate already gave up on this phase (BLOCKED). The Stop hook must not
    # re-trap the agent in a loop it has already declared dead.
    _snapshot_with_reviews(tmp_path, monkeypatch, [GateVerdict.BLOCKED])
    assert stop_payload(tmp_path, enforce=True) == ""


def test_stop_breaker_trips_after_attempt_cap(tmp_path: Path, monkeypatch) -> None:
    from goals.models import GateVerdict

    _repo_with_goal(tmp_path)
    # Three failed reviews reach the default cap even without a BLOCKED verdict.
    _snapshot_with_reviews(tmp_path, monkeypatch, [GateVerdict.FAIL] * 3)
    assert stop_payload(tmp_path, enforce=True) == ""


def test_stop_still_blocks_below_attempt_cap(tmp_path: Path, monkeypatch) -> None:
    from goals.models import GateVerdict

    _repo_with_goal(tmp_path)
    # Two failed reviews are below the cap: there is still room to converge, so
    # the Stop hook keeps the loop working.
    _snapshot_with_reviews(tmp_path, monkeypatch, [GateVerdict.FAIL] * 2)
    payload = json.loads(stop_payload(tmp_path, enforce=True))
    assert payload["decision"] == "block"


def test_stop_breaker_cap_is_configurable(tmp_path: Path, monkeypatch) -> None:
    from goals.agent_hooks import MAX_ATTEMPTS_ENV
    from goals.models import GateVerdict

    _repo_with_goal(tmp_path)
    _snapshot_with_reviews(tmp_path, monkeypatch, [GateVerdict.FAIL])
    # A single attempt is below the default cap (3) but at a cap of 1.
    assert json.loads(stop_payload(tmp_path, enforce=True))["decision"] == "block"
    monkeypatch.setenv(MAX_ATTEMPTS_ENV, "1")
    assert stop_payload(tmp_path, enforce=True) == ""


def test_stop_breaker_cap_can_be_raised(tmp_path: Path, monkeypatch) -> None:
    from goals.agent_hooks import MAX_ATTEMPTS_ENV
    from goals.models import GateVerdict

    _repo_with_goal(tmp_path)
    # Raising the cap loosens the breaker: four failures still block at a cap of
    # five, and the fifth trips it.
    monkeypatch.setenv(MAX_ATTEMPTS_ENV, "5")
    _snapshot_with_reviews(tmp_path, monkeypatch, [GateVerdict.FAIL] * 4)
    assert json.loads(stop_payload(tmp_path, enforce=True))["decision"] == "block"
    _snapshot_with_reviews(tmp_path, monkeypatch, [GateVerdict.FAIL] * 5)
    assert stop_payload(tmp_path, enforce=True) == ""


def test_stop_breaker_cap_ignores_garbage_env(tmp_path: Path, monkeypatch) -> None:
    from goals.agent_hooks import MAX_ATTEMPTS_ENV
    from goals.models import GateVerdict

    _repo_with_goal(tmp_path)
    _snapshot_with_reviews(tmp_path, monkeypatch, [GateVerdict.FAIL] * 2)
    # A typo or non-positive value must fall back to the default, never disable
    # the breaker by raising the cap to infinity.
    monkeypatch.setenv(MAX_ATTEMPTS_ENV, "not-a-number")
    assert json.loads(stop_payload(tmp_path, enforce=True))["decision"] == "block"


def test_stop_breaker_keys_off_latest_review_not_history(tmp_path: Path, monkeypatch) -> None:
    from goals.models import GateVerdict

    _repo_with_goal(tmp_path)
    # A later PASS means the phase converged: stale BLOCKED/FAIL from earlier
    # cycles must not trip the breaker and let the agent stop short.
    _snapshot_with_reviews(
        tmp_path,
        monkeypatch,
        [GateVerdict.BLOCKED, GateVerdict.FAIL, GateVerdict.PASS],
    )
    payload = json.loads(stop_payload(tmp_path, enforce=True))
    assert payload["decision"] == "block"


def _transcript(tmp_path: Path, output_tokens: int) -> str:
    path = tmp_path / "transcript.jsonl"
    path.write_text(
        '{"type":"assistant","message":{"usage":{"output_tokens":%d}}}\n' % output_tokens,
        encoding="utf-8",
    )
    return str(path)


def test_stop_token_budget_trips_when_exceeded(tmp_path: Path, monkeypatch) -> None:
    from goals.agent_hooks import MAX_TOKENS_ENV

    _repo_with_goal(tmp_path)  # fresh goal: waiting on the agent, would block
    transcript = _transcript(tmp_path, output_tokens=500)
    monkeypatch.setenv(MAX_TOKENS_ENV, "100")
    assert stop_payload(tmp_path, enforce=True, transcript_path=transcript) == ""


def test_stop_token_budget_blocks_when_under(tmp_path: Path, monkeypatch) -> None:
    from goals.agent_hooks import MAX_TOKENS_ENV

    _repo_with_goal(tmp_path)
    transcript = _transcript(tmp_path, output_tokens=50)
    monkeypatch.setenv(MAX_TOKENS_ENV, "100")
    payload = json.loads(stop_payload(tmp_path, enforce=True, transcript_path=transcript))
    assert payload["decision"] == "block"


def test_stop_token_budget_trips_exactly_at_cap(tmp_path: Path, monkeypatch) -> None:
    from goals.agent_hooks import MAX_TOKENS_ENV

    _repo_with_goal(tmp_path)
    # The ceiling is inclusive: hitting it exactly must stop, not block.
    transcript = _transcript(tmp_path, output_tokens=100)
    monkeypatch.setenv(MAX_TOKENS_ENV, "100")
    assert stop_payload(tmp_path, enforce=True, transcript_path=transcript) == ""


def test_stop_token_budget_is_off_without_cap(tmp_path: Path, monkeypatch) -> None:
    from goals.agent_hooks import MAX_TOKENS_ENV

    _repo_with_goal(tmp_path)
    transcript = _transcript(tmp_path, output_tokens=10**9)
    monkeypatch.delenv(MAX_TOKENS_ENV, raising=False)
    # No cap set: a huge transcript must not trip the gate.
    payload = json.loads(stop_payload(tmp_path, enforce=True, transcript_path=transcript))
    assert payload["decision"] == "block"


def test_stop_token_budget_ignores_garbage_cap(tmp_path: Path, monkeypatch) -> None:
    from goals.agent_hooks import MAX_TOKENS_ENV

    _repo_with_goal(tmp_path)
    transcript = _transcript(tmp_path, output_tokens=10**9)
    monkeypatch.setenv(MAX_TOKENS_ENV, "lots")
    # A non-integer cap disables the ceiling rather than capping at a wrong value.
    payload = json.loads(stop_payload(tmp_path, enforce=True, transcript_path=transcript))
    assert payload["decision"] == "block"


def test_stop_fails_open_on_unexpected_error(tmp_path: Path, monkeypatch) -> None:
    from goals import agent_hooks

    def boom(_cwd):
        raise ValueError("unexpected")

    monkeypatch.setattr(agent_hooks, "load_active_snapshot", boom)
    # Must NOT raise (a raising Stop hook is treated as a block — fail open).
    assert stop_payload(tmp_path, enforce=True) == ""
    assert session_start_payload(tmp_path) == ""


# --- session start names the goal that is really in progress --------------- #
def _base_repo(path: Path) -> Path:
    path.mkdir()
    for cmd in (
        ["git", "init", "-q", "-b", "feature"],
        ["git", "config", "user.email", "t@e.com"],
        ["git", "config", "user.name", "T"],
    ):
        _run(cmd, path)
    (path / "README.md").write_text("# demo\n")
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-q", "-m", "init"], path)
    return path


def _goal_in_worktree(base: Path, objective: str) -> Path:
    return Path(create_goal(objective, base, workspace="worktree").topology.worktree_path)


def _finish(folder: Path) -> None:
    """Accept every phase of the goal in ``folder`` (through the event log), so it is complete."""
    snapshot = load_active_snapshot(folder)
    store = EventStore(folder / ".agent-workflow" / "goals" / snapshot.goal_id)
    for phase in snapshot.phases:
        store.append(
            Event(
                goal_id=snapshot.goal_id,
                event_type=EventType.PHASE_ACCEPTED,
                actor="test",
                payload={"phase_id": phase.phase_id},
            )
        )
    assert load_active_snapshot(folder).status == GoalStatus.COMPLETE


def _context(payload: str) -> str:
    return json.loads(payload)["hookSpecificOutput"]["additionalContext"]


def _today(folder: Path) -> str:
    """The exact payload this hook gave before it looked past the session's own folder."""
    block = render_context_block(load_active_snapshot(folder))
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": block}}
    )


def test_session_in_base_checkout_is_pointed_at_the_goal_in_a_worktree(tmp_path: Path) -> None:
    base = _base_repo(tmp_path / "base")
    live = _goal_in_worktree(base, "build the real thing")
    context = _context(session_start_payload(base))
    assert "build the real thing" in context
    assert f"Goal folder: {live}" in context
    assert "Waiting on:" in context
    # Goal first, next action last (a long block loses its middle).
    assert context.index("build the real thing") < context.index("Waiting on:")
    assert context.rstrip().splitlines()[-1].startswith("Next:")


def test_finished_goal_in_this_folder_is_not_shown_when_another_is_live(tmp_path: Path) -> None:
    base = _base_repo(tmp_path / "base")
    create_goal("the old finished job", base, workspace="in_place")
    _finish(base)
    live = _goal_in_worktree(base, "the live job")
    context = _context(session_start_payload(base))
    assert "the live job" in context
    assert "the old finished job" not in context
    assert f"Goal folder: {live}" in context
    assert "finished" in context  # says why the session was redirected


def test_session_in_a_finished_worktree_is_pointed_at_the_live_one(tmp_path: Path) -> None:
    base = _base_repo(tmp_path / "base")
    done = _goal_in_worktree(base, "done job")
    live = _goal_in_worktree(base, "live job")
    _finish(done)
    context = _context(session_start_payload(done))
    assert "live job" in context and "done job" not in context
    assert f"Goal folder: {live}" in context


def test_several_live_goals_are_listed_and_the_user_is_asked_which(tmp_path: Path) -> None:
    base = _base_repo(tmp_path / "base")
    alpha = _goal_in_worktree(base, "alpha job")
    beta = _goal_in_worktree(base, "beta job")
    context = _context(session_start_payload(base))
    assert "alpha job" in context and "beta job" in context
    assert str(alpha) in context and str(beta) in context
    assert "goals:context:start" not in context  # no single goal is named as the active one
    last = context.rstrip().splitlines()[-1]
    assert last.startswith("Next:") and "ask the user which" in last
    # Re-injected after every /compact: must not interrupt work already settled in the chat.
    assert "already" in last


def test_listing_is_capped(tmp_path: Path, monkeypatch) -> None:
    from goals import agent_hooks

    monkeypatch.setattr(agent_hooks, "MAX_LISTED_GOALS", 2)
    base = _base_repo(tmp_path / "base")
    for name in ("one", "two", "three"):
        _goal_in_worktree(base, f"{name} job")
    context = _context(session_start_payload(base))
    assert sum(f"{name} job" in context for name in ("one", "two", "three")) == 2
    assert "1 more" in context


def test_own_live_goal_still_wins_and_gets_status_lines(tmp_path: Path) -> None:
    base = _base_repo(tmp_path / "base")
    alpha = _goal_in_worktree(base, "alpha job")
    _goal_in_worktree(base, "beta job")
    context = _context(session_start_payload(alpha))
    assert "alpha job" in context and "beta job" not in context
    assert "Goal folder:" not in context  # already in the right folder
    assert "Waiting on:" in context
    assert context.rstrip().splitlines()[-1].startswith("Next:")


def test_a_failing_status_line_falls_back_to_todays_block(tmp_path: Path, monkeypatch) -> None:
    from goals import agent_hooks

    base = _base_repo(tmp_path / "base")
    alpha = _goal_in_worktree(base, "alpha job")

    def boom(*_args, **_kwargs):
        raise ValueError("unexpected")

    monkeypatch.setattr(agent_hooks, "build_goal_brief", boom)
    assert session_start_payload(alpha) == _today(alpha)


def test_waiting_on_you_names_the_open_question(tmp_path: Path) -> None:
    base = _base_repo(tmp_path / "base")
    live = _goal_in_worktree(base, "alpha job")
    record_checkpoint(
        live,
        "P1",
        "alignment",
        kind=CheckpointKind.UNDERSTANDING,
        status=CheckpointStatus.NEEDS_USER,
        needs_user=True,
        title="Does this match what you want?",
        summary="waiting",
    )
    context = _context(session_start_payload(base))
    assert "Waiting on: you" in context
    assert "Does this match what you want?" in context


def test_only_finished_goals_elsewhere_gives_exactly_todays_output(tmp_path: Path) -> None:
    base = _base_repo(tmp_path / "base")
    create_goal("the old finished job", base, workspace="in_place")
    _finish(base)
    done = _goal_in_worktree(base, "another finished job")
    _finish(done)
    assert session_start_payload(base) == _today(base)


def test_a_goal_that_is_paused_does_not_count_as_in_progress(tmp_path: Path, monkeypatch) -> None:
    base = _base_repo(tmp_path / "base")
    _goal_in_worktree(base, "paused job")
    real = EventStore.snapshot

    def paused(self):
        snapshot = real(self)
        snapshot.status = GoalStatus.PAUSED
        return snapshot

    monkeypatch.setattr(EventStore, "snapshot", paused)
    assert session_start_payload(base) == ""


def test_a_broken_lookup_falls_back_to_exactly_todays_output(tmp_path: Path, monkeypatch) -> None:
    from goals import agent_hooks

    base = _base_repo(tmp_path / "base")
    create_goal("the old finished job", base, workspace="in_place")
    _finish(base)
    _goal_in_worktree(base, "the live job")

    def boom(*_args, **_kwargs):
        raise ValueError("unexpected")

    monkeypatch.setattr(agent_hooks, "_live_goals_elsewhere", boom)
    assert session_start_payload(base) == _today(base)


def test_a_broken_lookup_with_no_own_goal_is_silent(tmp_path: Path, monkeypatch) -> None:
    from goals import agent_hooks

    base = _base_repo(tmp_path / "base")
    _goal_in_worktree(base, "the live job")

    def boom(*_args, **_kwargs):
        raise ValueError("unexpected")

    monkeypatch.setattr(agent_hooks, "_live_goals_elsewhere", boom)
    assert session_start_payload(base) == ""


def test_a_corrupt_log_in_another_folder_is_skipped(tmp_path: Path) -> None:
    base = _base_repo(tmp_path / "base")
    broken = _goal_in_worktree(base, "broken job")
    _goal_in_worktree(base, "good job")
    (next((broken / ".agent-workflow" / "goals").iterdir()) / "events.jsonl").write_text("not json\n")
    context = _context(session_start_payload(base))
    assert "good job" in context and "broken job" not in context


def test_the_only_live_goal_being_corrupt_gives_todays_output(tmp_path: Path) -> None:
    base = _base_repo(tmp_path / "base")
    create_goal("the old finished job", base, workspace="in_place")
    _finish(base)
    broken = _goal_in_worktree(base, "broken job")
    (next((broken / ".agent-workflow" / "goals").iterdir()) / "events.jsonl").write_text("not json\n")
    assert session_start_payload(base) == _today(base)


# --- hooks CLI ------------------------------------------------------------- #
def test_hooks_session_start_names_the_worktree_goal(tmp_path: Path, monkeypatch) -> None:
    base = _base_repo(tmp_path / "base")
    live = _goal_in_worktree(base, "build the real thing")
    monkeypatch.chdir(base)
    result = runner.invoke(app, ["hooks", "session-start"])
    assert result.exit_code == 0
    assert f"Goal folder: {live}" in _context(result.stdout)


def test_hooks_session_start_command(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["hooks", "session-start"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_hooks_session_start_empty_without_goal(tmp_path: Path, monkeypatch) -> None:
    _run(["git", "init", "-b", "feature"], tmp_path)
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["hooks", "session-start"])
    assert result.exit_code == 0
    assert result.stdout == ""


def test_hooks_stop_command_reads_transcript_from_stdin(tmp_path: Path, monkeypatch) -> None:
    from goals.agent_hooks import MAX_TOKENS_ENV

    _repo_with_goal(tmp_path)
    transcript = _transcript(tmp_path, output_tokens=500)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOALS_ENFORCE", "1")
    monkeypatch.setenv(MAX_TOKENS_ENV, "100")
    # The hook input arrives as JSON on stdin; the token ceiling trips, so the
    # command allows the stop (empty output) rather than blocking.
    stdin = json.dumps({"transcript_path": transcript, "hook_event_name": "Stop"})
    result = runner.invoke(app, ["hooks", "stop"], input=stdin)
    assert result.exit_code == 0
    assert result.stdout == ""


def test_hooks_stop_command_blocks_without_transcript(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOALS_ENFORCE", "1")
    # No stdin payload: the gate still works off durable state and blocks.
    result = runner.invoke(app, ["hooks", "stop"], input="")
    assert result.exit_code == 0
    assert json.loads(result.stdout)["decision"] == "block"


def test_hooks_stop_command_tolerates_malformed_stdin(tmp_path: Path, monkeypatch) -> None:
    _repo_with_goal(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOALS_ENFORCE", "1")
    # A JSON array (not an object) and a non-string transcript_path are both
    # ignored — the path degrades to None — so the gate falls back to durable
    # state and blocks rather than crashing.
    for stdin in ("[1, 2, 3]", json.dumps({"transcript_path": 123})):
        result = runner.invoke(app, ["hooks", "stop"], input=stdin)
        assert result.exit_code == 0
        assert json.loads(result.stdout)["decision"] == "block"


# --- plugin manifests ------------------------------------------------------ #
def test_plugin_manifest_is_valid() -> None:
    data = json.loads((REPO / ".claude-plugin" / "plugin.json").read_text())
    assert data["name"] == "goals"
    assert data["version"] and data["description"]


def test_marketplace_manifest_lists_the_plugin() -> None:
    data = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    assert data["name"] == "goals"
    names = [p["name"] for p in data["plugins"]]
    assert "goals" in names


def test_hooks_json_wires_session_start_and_stop() -> None:
    data = json.loads((REPO / "hooks" / "hooks.json").read_text())
    events = data["hooks"]
    assert "SessionStart" in events and "Stop" in events
    cmds = [
        h["command"]
        for group in events.values()
        for entry in group
        for h in entry["hooks"]
    ]
    # Hooks run THROUGH the self-bootstrapping wrapper so the plugin installs its
    # own CLI on first use — but still resolve to `goals hooks <event>`.
    assert any(c.endswith("hooks session-start") and "plugin-bootstrap.sh" in c for c in cmds)
    assert any(c.endswith("hooks stop") and "plugin-bootstrap.sh" in c for c in cmds)
    assert all("${CLAUDE_PLUGIN_ROOT}" in c for c in cmds)


def test_commands_exist_with_frontmatter() -> None:
    for name in ("create", "next", "check", "diagram", "improve", "import"):
        text = (REPO / "commands" / f"{name}.md").read_text()
        assert text.startswith("---")  # frontmatter
        assert "description:" in text


def test_import_command_drives_loop_import_and_validation() -> None:
    text = (REPO / "commands" / "import.md").read_text()
    assert "goals loop import" in text
    assert "--no-prompt" in text
    assert "goals loop check" in text
    assert 'goals loop check --out "$OUT_DIR"' in text
    assert "--target-agent claude" in text


# --- self-bootstrapping plugin wrapper ------------------------------------- #
BOOTSTRAP = REPO / "scripts" / "plugin-bootstrap.sh"


def test_bootstrap_wrapper_exists_and_is_executable() -> None:
    assert BOOTSTRAP.exists()
    assert os.access(BOOTSTRAP, os.X_OK)


def test_bootstrap_wrapper_contract() -> None:
    text = BOOTSTRAP.read_text()
    # installs from the plugin's OWN bundled source (the cloned repo)
    assert "uv tool install" in text
    assert "CLAUDE_PLUGIN_ROOT" in text
    # diagnostics must go to stderr so stdout stays clean for the hook's JSON
    assert ">&2" in text
    # fail-open: a session hook must never crash the session
    assert "exit 0" in text


def test_bootstrap_fast_paths_to_existing_goals(tmp_path: Path) -> None:
    # With a `goals` already on PATH, the wrapper must exec it directly and emit
    # ONLY its output (no install noise leaking into the hook's stdout).
    bindir = tmp_path / "bin"
    bindir.mkdir()
    stub = bindir / "goals"
    stub.write_text('#!/bin/sh\necho "STUB:$*"\n')
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}"}
    res = subprocess.run(
        [str(BOOTSTRAP), "hooks", "session-start"],
        capture_output=True, text=True, env=env,
    )
    assert res.returncode == 0
    assert res.stdout.strip() == "STUB:hooks session-start"


def test_bootstrap_fails_open_when_cli_unavailable(tmp_path: Path) -> None:
    # No goals, no uv, no usable plugin root → exit 0 with empty stdout, never
    # crashing the session. (Hermetic: empty PATH means no curl/network.)
    emptybin = tmp_path / "empty"
    emptybin.mkdir()
    env = {
        "PATH": str(emptybin),
        "HOME": str(tmp_path),
        "CLAUDE_PLUGIN_ROOT": str(tmp_path / "nope"),
    }
    res = subprocess.run(
        [str(BOOTSTRAP), "hooks", "session-start"],
        capture_output=True, text=True, env=env,
    )
    assert res.returncode == 0
    assert res.stdout == ""
