"""Discovery shows up where people look, and the user's words stay where they should.

Dashboard section and a generated DISCOVERY.md; pain points and desired
properties never reach the committable `.goals/` spec; pain is never remembered;
a `--private` decision keeps its why local; desired properties the user confirms
are remembered so one that recurs across goals is offered for promotion.
(Roadmap: Discovery build step 4.)
"""

import json
import os
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from goals.cli import app
from goals.runtime import create_goal, load_active_snapshot
from goals.user_memory import build_goal_memory_digest, observations_path

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


def test_only_properties_marked_remember_are_remembered_and_never_pain(repo: Path) -> None:
    _invoke("assess", "pain", "pain-canary-51")
    _invoke("assess", "want", "Works with no internet", "--proof", "auto", "--phase", "P3", "--remember")
    _invoke("assess", "want", "want-canary-52", "--proof", "auto", "--phase", "P3")
    _confirm_discovery(repo)
    memory = observations_path().read_text()
    assert "pain-canary-51" not in memory
    assert "want-canary-52" not in memory  # not marked --remember: stays on this goal
    assert memory.count("Works with no internet") == 1
    assert "what you wanted in this goal" in memory


def test_an_unverified_confirmation_remembers_nothing(repo: Path) -> None:
    _invoke("assess", "want", "want-canary-61", "--proof", "auto", "--phase", "P3")
    align = ["checkpoint", "record", "P1", "alignment", "--kind", "understanding"]
    _invoke(*align, "--status", "needs_user")
    _invoke(*align, "--status", "passed", "--unverified")
    path = observations_path()
    assert not path.exists() or "want-canary-61" not in path.read_text()


def test_a_private_decision_stays_on_the_goal(repo: Path) -> None:
    base = ["decision", "record", "Approach?", "--by", "user", "--phase", "P1"]
    _invoke(*base, "--choice", "public-choice", "--why", "shared-why-71")
    _invoke(*base, "--choice", "private-choice", "--why", "private-why-72", "--private")
    memory = observations_path().read_text()
    assert "shared-why-71" in memory
    assert "private-choice" not in memory and "private-why-72" not in memory
    # The why is still on the goal itself.
    assert any(j.rationale == "private-why-72" for j in load_active_snapshot(repo).judgements)


def test_a_property_confirmed_in_two_goals_is_offered_for_promotion(tmp_path: Path, monkeypatch) -> None:
    for name in ("first", "second"):
        repo = _goal(tmp_path, monkeypatch, name=name, objective=f"{name} goal")
        _invoke("assess", "want", "Works with no internet", "--proof", "auto", "--phase", "P3",
                "--remember")
        _confirm_discovery(repo)
    digest = build_goal_memory_digest("second-goal")
    assert "Seen across several goals" in digest and "Works with no internet" in digest
    assert os.environ["GOALS_HOME"] in str(observations_path())  # never the real home


# --------------------------------------------------------------------------- #
# Review fixes (phase 4)
# --------------------------------------------------------------------------- #
def test_memory_is_written_once_at_the_first_yes_only(repo: Path) -> None:
    _invoke("assess", "want", "Works with no internet", "--proof", "auto", "--phase", "P3", "--remember")
    _confirm_discovery(repo)
    # Edits to the closed checkpoint don't re-remember anything...
    _invoke(*["checkpoint", "record", "P1", "alignment"], "--summary", "tidied")
    _invoke(*["checkpoint", "record", "P1", "alignment"], "--evidence-ref", "notes")
    # ...and a property added after the yes was never confirmed, so it isn't remembered.
    _invoke("assess", "want", "want-canary-81", "--proof", "auto", "--phase", "P3", "--remember")
    _invoke(*["checkpoint", "record", "P1", "alignment"], "--summary", "again")
    memory = observations_path().read_text()
    assert memory.count("Works with no internet") == 1
    assert "want-canary-81" not in memory


def test_a_waived_confirmation_remembers_nothing(repo: Path) -> None:
    _invoke("assess", "want", "want-canary-82", "--proof", "auto", "--phase", "P3", "--remember")
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
    _invoke("assess", "want", "Works offline", "--proof", "auto", "--phase", "P3", "--remember")
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


def _accept_quick(repo: Path, phase_id: str) -> None:
    from goals.runtime import run_gate

    phase = next(p for p in load_active_snapshot(repo).phases if p.phase_id == phase_id)
    verifications = [
        {"covers": f"{phase_id}.C{i + 1}", "kind": "auto", "command": "true"}
        for i in range(len(phase.acceptance_criteria))
    ]
    path = repo / f"evidence-{phase_id}.json"
    path.write_text(json.dumps({"checks_run": ["true"], "verifications": verifications}))
    _invoke("phase", "evidence", phase_id, "--file", str(path))
    _invoke("phase", "verify", phase_id)
    run_gate(repo, phase_id)
    _invoke("phase", "accept", phase_id)


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
