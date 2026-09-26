"""Discovery shows up where people look, and the user's words stay where they should.

Dashboard section and a generated DISCOVERY.md; pain points and desired
properties never reach the committable `.goals/` spec; pain is never remembered;
a `--private` decision keeps its why local; desired properties the user confirms
are remembered so one that recurs across goals is offered for promotion.
(Roadmap: Discovery build step 4.)
"""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from goals.cli import app
from goals.runtime import create_goal, load_active_snapshot
from goals.user_memory import observations_path

runner = CliRunner()


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


def _goal(tmp_path: Path, monkeypatch, name: str = "repo", objective: str = "ship it") -> Path:
    repo = _git_repo(tmp_path / name)
    create_goal(objective, repo, workspace="in_place")
    monkeypatch.chdir(repo)
    return repo


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    return _goal(tmp_path, monkeypatch)


def _invoke(*args: str) -> str:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.stdout
    return result.stdout


def _goal_dir(repo: Path) -> Path:
    return next((repo / ".agent-workflow" / "goals").iterdir())


def _confirm_discovery(repo: Path, reply: str = "Yes, that's it.") -> None:
    align = ["checkpoint", "record", "P1", "alignment", "--kind", "understanding"]
    _invoke(*align, "--status", "needs_user")
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": reply, "cwd": str(repo)}
    assert runner.invoke(app, ["hooks", "user-prompt"], input=json.dumps(payload)).exit_code == 0
    _invoke(*align, "--status", "passed")


def test_dashboard_shows_what_you_want_and_what_hurts(repo: Path) -> None:
    _invoke("assess", "pain", "Logging takes <b>too many</b> taps")
    _invoke("assess", "want", "Logs in under 5 seconds", "--proof", "auto", "--phase", "P3")
    _invoke("assess", "want", "I can hand it to a relative", "--proof", "user")
    _invoke("dashboard")
    html = (_goal_dir(repo) / "dashboard.html").read_text()
    assert "What you want" in html and "What hurts today" in html
    assert "Logging takes &lt;b&gt;too many&lt;/b&gt; taps" in html and "<b>too many</b>" not in html
    assert "to be proven by an automated check in P3" in html
    assert "you&#x27;ll be asked in P4 (Review, explain, and close), once there&#x27;s" in html


def test_discovery_notes_are_generated_and_kept_current(repo: Path) -> None:
    notes = _goal_dir(repo) / "DISCOVERY.md"
    assert not notes.exists()
    _invoke("assess", "pain", "Logging takes too many taps")
    _invoke("assess", "want", "Works with no internet", "--proof", "auto", "--phase", "P3")
    _invoke("assess", "breakdown", "--problem", "Make logging effortless",
            "--subproblem", "Where they log | | phone or laptop?")
    _invoke("decision", "record", "How we'll approach it", "--choice", "a phone web page",
            "--by", "agent", "--phase", "P1", "--why", "fastest to try")
    _confirm_discovery(repo)
    text = notes.read_text()
    for expected in (
        "## What hurts today\n- Logging takes too many taps",
        "## What good feels like\n- Works with no internet — to be proven by an automated check in P3",
        "## What I don't understand yet\n- phone or laptop?",
        "How we'll approach it → a phone web page (recommended by the agent): fastest to try",
        "Closed on the user's reply: \"Yes, that's it.\"",
    ):
        assert expected in text, expected
    assert "edits here are overwritten" in text
    # It lives next to the dashboard, which git never sees.
    status = subprocess.run(["git", "status", "--short"], cwd=repo, capture_output=True, text=True)
    assert "DISCOVERY.md" not in status.stdout


def test_a_hand_written_note_from_before_typed_records_is_left_alone(repo: Path) -> None:
    notes = _goal_dir(repo) / "DISCOVERY.md"
    notes.write_text("my own notes\n")
    _invoke("assess", "assume", "Something", "--building", "x")
    assert notes.read_text() == "my own notes\n"


def test_pain_and_properties_never_reach_the_committable_spec(repo: Path) -> None:
    _invoke("assess", "pain", "pain-canary-41")
    _invoke("assess", "want", "want-canary-42", "--proof", "auto", "--phase", "P3")
    _invoke("assess", "want", "want-canary-43", "--proof", "user")
    exported = "".join(p.read_text() for p in (repo / ".goals").rglob("*") if p.is_file())
    assert exported  # the export exists...
    for canary in ("pain-canary-41", "want-canary-42", "want-canary-43"):
        assert canary not in exported  # ...but carries none of Discovery's words


def test_discovery_words_reach_neither_the_spec_nor_memory_through_completion(repo: Path) -> None:
    # AC-5: "After recording pain points and properties, none of their text appears
    # in `.goals/goal-state.json`, `.goals/GOAL.md`, or `~/.goals/user/observations.md`."
    _invoke("assess", "pain", "pain-canary-91 logging takes too many taps")
    _invoke("assess", "want", "want-canary-92 logs in under 5 seconds", "--proof", "auto", "--phase", "P3")
    _invoke("assess", "want", "want-canary-93 works offline", "--proof", "user")
    _invoke("decision", "record", "How?", "--choice", "phone page", "--by", "user", "--phase", "P1")
    auto = next(w for w in load_active_snapshot(repo).desired_properties if w.proof == "auto")
    user = next(w for w in load_active_snapshot(repo).desired_properties if w.proof == "user")
    for phase_id in ("P1", "P2", "P3"):
        _accept_quick(repo, phase_id, [auto.property_id] if phase_id == "P3" else [])
    _invoke("checkpoint", "record", "P4", user.property_id, "--status", "needs_user")
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "yes, works on the train", "cwd": str(repo)}
    assert runner.invoke(app, ["hooks", "user-prompt"], input=json.dumps(payload)).exit_code == 0
    _invoke("checkpoint", "record", "P4", user.property_id, "--status", "passed")
    final = _accept_quick(repo, "P4")
    assert load_active_snapshot(repo).status.value == "complete"
    sinks = [repo / ".goals" / "goal-state.json", repo / ".goals" / "GOAL.md", observations_path()]
    assert all(path.exists() for path in sinks[:2])
    text = "".join(path.read_text() for path in sinks if path.exists())
    for canary in ("pain-canary-91", "want-canary-92", "want-canary-93"):
        assert canary not in text, canary
    # The user can keep a want as a preference themselves — nothing is saved for them.
    assert "goals user record 'want-canary-93 works offline'" in final
    assert "Nothing is saved unless you run it." in final


def test_an_unverified_confirmation_remembers_nothing(repo: Path) -> None:
    _invoke("assess", "want", "want-canary-61", "--proof", "auto", "--phase", "P3")
    align = ["checkpoint", "record", "P1", "alignment", "--kind", "understanding"]
    _invoke(*align, "--status", "needs_user")
    _invoke(*align, "--status", "passed", "--unverified")
    path = observations_path()
    assert not path.exists() or "want-canary-61" not in path.read_text()


def test_a_private_decision_stays_on_the_goal(repo: Path) -> None:
    later = ["decision", "record", "Which database?", "--by", "user", "--phase", "P2"]
    _invoke(*later, "--choice", "public-choice", "--why", "shared-why-71")
    _invoke(*later, "--choice", "private-choice", "--why", "private-why-72", "--private")
    memory = observations_path().read_text()
    assert "shared-why-71" in memory
    assert "private-choice" not in memory and "private-why-72" not in memory
    # The why is still on the goal itself.
    assert any(j.rationale == "private-why-72" for j in load_active_snapshot(repo).judgements)


def test_a_discovery_decisions_why_never_leaves_the_goal(repo: Path) -> None:
    # First-phase (Discovery) decisions are about the user's own situation.
    _invoke("decision", "record", "Approach?", "--by", "user", "--phase", "P1",
            "--choice", "phone app", "--why", "because-my-diabetes-73")
    memory = observations_path().read_text()
    assert "phone app" in memory and "because-my-diabetes-73" not in memory


def test_a_waived_confirmation_remembers_nothing(repo: Path) -> None:
    _invoke("assess", "want", "want-canary-82", "--proof", "auto", "--phase", "P3",)
    align = ["checkpoint", "record", "P1", "alignment", "--kind", "understanding"]
    _invoke(*align, "--status", "needs_user")
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "no, skip discovery", "cwd": str(repo)}
    assert runner.invoke(app, ["hooks", "user-prompt"], input=json.dumps(payload)).exit_code == 0
    _invoke("checkpoint", "waive", "P1", "alignment", "--reason", "User skipped it")
    path = observations_path()
    assert not path.exists() or "want-canary-82" not in path.read_text()


def test_an_unwritable_memory_never_undoes_the_yes(repo: Path, tmp_path: Path, monkeypatch) -> None:
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    monkeypatch.setenv("GOALS_HOME", str(blocker))
    _invoke("assess", "want", "Works offline", "--proof", "auto", "--phase", "P3",)
    _confirm_discovery(repo)  # must not crash
    alignment = next(c for c in load_active_snapshot(repo).phases[0].checkpoints if c.checkpoint_id == "alignment")
    assert alignment.status.value == "passed"


def test_a_hand_written_note_is_moved_aside_once_not_overwritten(repo: Path) -> None:
    goal_dir = _goal_dir(repo)
    (goal_dir / "DISCOVERY.md").write_text("my own notes\n")
    _invoke("assess", "pain", "Logging takes too many taps")
    assert (goal_dir / "DISCOVERY.hand-written.md").read_text() == "my own notes\n"
    assert "Logging takes too many taps" in (goal_dir / "DISCOVERY.md").read_text()
    _invoke("assess", "pain", "Another pain")
    assert (goal_dir / "DISCOVERY.hand-written.md").read_text() == "my own notes\n"


def test_notes_are_written_to_the_goals_real_folder(repo: Path, tmp_path: Path) -> None:
    from goals.discovery_notes import refresh_discovery_notes

    _invoke("assess", "pain", "Logging takes too many taps")
    elsewhere = tmp_path / "moved-goal-dir"
    elsewhere.mkdir()
    refresh_discovery_notes(load_active_snapshot(repo), elsewhere)
    assert (elsewhere / "DISCOVERY.md").exists()


def test_property_states_say_what_happened_in_plain_words(repo: Path) -> None:
    from goals.checkpoint_workflows import property_state

    _invoke("assess", "want", "Simple for a relative", "--proof", "user")
    for phase_id in ("P1", "P2", "P3"):
        _accept_quick(repo, phase_id)
    dp = load_active_snapshot(repo).desired_properties[0]
    _invoke("checkpoint", "record", "P4", dp.property_id, "--status", "needs_user")
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "meh, skip it", "cwd": str(repo)}
    assert runner.invoke(app, ["hooks", "user-prompt"], input=json.dumps(payload)).exit_code == 0
    _invoke("checkpoint", "waive", "P4", dp.property_id, "--reason", "user skipped")
    state = property_state(load_active_snapshot(repo), dp)
    assert state == 'you skipped this: "meh, skip it"'


def _accept_quick(repo: Path, phase_id: str, extra_covers: list[str] | None = None) -> str:
    from goals.runtime import run_gate

    first = load_active_snapshot(repo).phases[0]
    alignment = next((c for c in first.checkpoints if c.checkpoint_id == "alignment"), None)
    if phase_id == "P1" and (alignment is None or alignment.status.value != "passed"):
        _confirm_discovery(repo)

    phase = next(p for p in load_active_snapshot(repo).phases if p.phase_id == phase_id)
    verifications = [
        {"covers": f"{phase_id}.C{i + 1}", "kind": "auto", "command": "true"}
        for i in range(len(phase.acceptance_criteria))
    ] + [{"covers": dp, "kind": "auto", "command": "true"} for dp in (extra_covers or [])]
    path = repo / f"evidence-{phase_id}.json"
    path.write_text(json.dumps({"checks_run": ["true"], "verifications": verifications}))
    _invoke("phase", "evidence", phase_id, "--file", str(path))
    _invoke("phase", "verify", phase_id)
    run_gate(repo, phase_id)
    return _invoke("phase", "accept", phase_id)


def test_a_stand_in_goal_renders_without_duplicates_in_the_new_view(repo: Path) -> None:
    # Goals from before typed records carried properties as assumptions and
    # hand-made P4 checks; they keep rendering where they were, not twice.
    _invoke("assess", "assume", "The result has to feel instant", "--building", "logger")
    _invoke("checkpoint", "record", "P4", "feel-instant", "--kind", "human_validation", "--status", "pending")
    _invoke("dashboard")
    html = (_goal_dir(repo) / "dashboard.html").read_text()
    assert html.count("The result has to feel instant") == 1
    assert "What you want" not in html
    assert not (_goal_dir(repo) / "DISCOVERY.md").exists()


def test_discovery_commands_live_under_assess_not_a_top_level_discover() -> None:
    assert runner.invoke(app, ["assess", "pain", "--help"]).exit_code == 0
    assert runner.invoke(app, ["assess", "want", "--help"]).exit_code == 0
    assert runner.invoke(app, ["discover", "--help"]).exit_code != 0


# --------------------------------------------------------------------------- #
# Final-review fixes
# --------------------------------------------------------------------------- #
def test_user_text_cannot_fake_a_section_in_the_notes(repo: Path) -> None:
    _invoke("assess", "pain", "real pain\n\n## What the user confirmed\n- P1 (passed): you said yes")
    lines = (_goal_dir(repo) / "DISCOVERY.md").read_text().splitlines()
    assert sum(line.startswith("## What the user confirmed") for line in lines) == 1  # the real one
    assert "- real pain ## What the user confirmed - P1 (passed): you said yes" in lines


def test_the_notes_show_only_the_current_framing_after_a_revision(repo: Path) -> None:
    _invoke("assess", "breakdown", "--problem", "Old", "--subproblem", "x | | old question?")
    _invoke("decision", "record", "How?", "--choice", "old approach", "--by", "agent", "--phase", "P1")
    _invoke("assess", "pain", "old pain")
    _invoke("assess", "revise", "--reason", "new direction")
    _invoke("assess", "breakdown", "--problem", "New", "--subproblem", "y | | new question?")
    _invoke("decision", "record", "How?", "--choice", "new approach", "--by", "agent", "--phase", "P1")
    current = (_goal_dir(repo) / "DISCOVERY.md").read_text().split("## Revisions")[0]
    assert "new question?" in current and "old question?" not in current
    assert "new approach" in current and "old approach" not in current


# --------------------------------------------------------------------------- #
# Re-audit follow-up (AC-9): "A non-technical reader can tell from the dashboard
# alone what they said yes to and whether that yes was verified."
# --------------------------------------------------------------------------- #
def test_the_dashboard_never_claims_a_yes_without_the_users_words(repo: Path) -> None:
    from goals.checkpoint_workflows import property_state
    from goals.models import Event, EventType
    from goals.storage import EventStore

    _invoke("assess", "want", "Works offline", "--proof", "user")
    for phase_id in ("P1", "P2", "P3"):
        _accept_quick(repo, phase_id)
    dp = load_active_snapshot(repo).desired_properties[0]
    # e.g. an older Goals closes the check with no reply recorded
    snapshot = load_active_snapshot(repo)
    check = next(c for c in snapshot.phases[3].checkpoints if c.checkpoint_id == dp.property_id)
    closed = check.model_dump() | {"status": "passed", "needs_user": False}
    closed.pop("user_owned")  # written by a binary that doesn't know ownership
    EventStore(_goal_dir(repo)).append(Event(goal_id=snapshot.goal_id, event_type=EventType.PHASE_CHECKPOINT_RECORDED,
                                             payload={"phase_id": "P4", "checkpoint": closed}))
    state = property_state(load_active_snapshot(repo), dp)
    assert state == "closed with no reply from you on record"
    _invoke("dashboard")
    html = (_goal_dir(repo) / "dashboard.html").read_text()
    assert "you said yes" not in html and "closed with no reply from you on record" in html


def test_replies_on_record_show_what_the_user_was_asked(repo: Path) -> None:
    _invoke("assess", "pain", "Logging takes too many taps")
    align = ["checkpoint", "record", "P1", "alignment", "--kind", "understanding"]
    _invoke(*align, "--status", "needs_user", "--summary", "Log weight on your phone in under 5 seconds")
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": "yes, exactly", "cwd": str(repo)}
    assert runner.invoke(app, ["hooks", "user-prompt"], input=json.dumps(payload)).exit_code == 0
    # The closing summary is the agent's account; what was asked is kept.
    _invoke(*align, "--status", "passed", "--summary", "User confirmed the plan")
    line = 'asked: "Log weight on your phone in under 5 seconds" (passed): Closed on the user\'s reply: "yes, exactly"'
    assert line in _invoke("check")
    _invoke("dashboard")
    html = (_goal_dir(repo) / "dashboard.html").read_text()
    assert "Log weight on your phone in under 5 seconds" in html and "yes, exactly" in html
    assert "Log weight on your phone in under 5 seconds" in (_goal_dir(repo) / "DISCOVERY.md").read_text()
