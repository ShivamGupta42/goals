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
    assert "you&#x27;ll be asked in P4, once there&#x27;s something to try" in html


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


def test_pain_is_never_remembered_but_confirmed_properties_are(repo: Path) -> None:
    _invoke("assess", "pain", "pain-canary-51")
    _invoke("assess", "want", "Works with no internet", "--proof", "auto", "--phase", "P3")
    _confirm_discovery(repo)
    memory = observations_path().read_text()
    assert "pain-canary-51" not in memory
    assert "Works with no internet" in memory


def test_an_unverified_confirmation_remembers_nothing(repo: Path) -> None:
    _invoke("assess", "want", "want-canary-61", "--proof", "auto", "--phase", "P3")
    align = ["checkpoint", "record", "P1", "alignment", "--kind", "understanding"]
    _invoke(*align, "--status", "needs_user")
    _invoke(*align, "--status", "passed", "--unverified")
    path = observations_path()
    assert not path.exists() or "want-canary-61" not in path.read_text()


def test_private_keeps_the_why_out_of_memory(repo: Path) -> None:
    base = ["decision", "record", "Approach?", "--by", "user", "--phase", "P1"]
    _invoke(*base, "--choice", "public-choice", "--why", "shared-why-71")
    _invoke(*base, "--choice", "private-choice", "--why", "private-why-72", "--private")
    memory = observations_path().read_text()
    assert "shared-why-71" in memory
    assert "private-choice" in memory and "private-why-72" not in memory
    # The why is still on the goal itself.
    assert any(j.rationale == "private-why-72" for j in load_active_snapshot(repo).judgements)


def test_a_property_confirmed_in_two_goals_is_offered_for_promotion(tmp_path: Path, monkeypatch) -> None:
    for name in ("first", "second"):
        repo = _goal(tmp_path, monkeypatch, name=name, objective=f"{name} goal")
        _invoke("assess", "want", "Works with no internet", "--proof", "auto", "--phase", "P3")
        _confirm_discovery(repo)
    digest = build_goal_memory_digest("second-goal")
    assert "Seen across several goals" in digest and "Works with no internet" in digest
    assert os.environ["GOALS_HOME"] in str(observations_path())  # never the real home
