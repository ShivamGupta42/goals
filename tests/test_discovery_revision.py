"""When the user's understanding shifts mid-goal, Discovery starts over honestly.

`goals assess revise --reason` supersedes what Discovery recorded, reopens the
first phase for a fresh "yes", and sends accepted phases back for review — no
stale PASS survives, and nothing stays "done" against the old framing.
(Roadmap: Discovery build step 5.)
"""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from goals.cli import app
from goals.models import CheckpointStatus, GateVerdict, GoalStatus, PhaseStatus
from goals.runtime import create_goal, load_active_snapshot, run_gate

runner = CliRunner()
ALIGN = ["checkpoint", "record", "P1", "alignment", "--kind", "understanding"]


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


def _invoke(*args: str) -> str:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.stdout
    return result.stdout


def _fails(*args: str) -> str:
    result = runner.invoke(app, list(args))
    assert result.exit_code == 1, result.stdout
    return result.stdout


def _say(repo: Path, text: str) -> None:
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": text, "cwd": str(repo)}
    assert runner.invoke(app, ["hooks", "user-prompt"], input=json.dumps(payload)).exit_code == 0


def _accept(repo: Path, phase_id: str, extra: list[dict] | None = None) -> None:
    phase = next(p for p in load_active_snapshot(repo).phases if p.phase_id == phase_id)
    verifications = [
        {"covers": f"{phase_id}.C{i + 1}", "kind": "auto", "command": "true"}
        for i in range(len(phase.acceptance_criteria))
    ] + (extra or [])
    path = repo / f"evidence-{phase_id}.json"
    path.write_text(json.dumps({"checks_run": ["true"], "verifications": verifications}))
    _invoke("phase", "evidence", phase_id, "--file", str(path))
    _invoke("phase", "verify", phase_id)
    assert run_gate(repo, phase_id).verdict == GateVerdict.PASS
    _invoke("phase", "accept", phase_id)


def _discovery_then_two_phases(repo: Path) -> None:
    _invoke("assess", "pain", "Logging takes too many taps")
    _invoke("assess", "want", "Logs in under 5 seconds", "--proof", "auto", "--phase", "P2")
    _invoke("assess", "want", "I trust the number", "--proof", "user")
    _invoke(*ALIGN, "--status", "needs_user")
    _say(repo, "yes, that's it")
    _invoke(*ALIGN, "--status", "passed")
    _accept(repo, "P1")
    dp = next(w for w in load_active_snapshot(repo).desired_properties if w.proof == "auto")
    _accept(repo, "P2", [{"covers": dp.property_id, "kind": "auto", "command": "true"}])


def test_revising_reopens_confirmation_and_sends_done_work_back(repo: Path) -> None:
    _discovery_then_two_phases(repo)
    out = _invoke("assess", "revise", "--reason", "They want a paper log, not an app")
    assert "P1 reopened" in out and "re-review P2" in out

    snapshot = load_active_snapshot(repo)
    p1, p2, p3, p4 = snapshot.phases
    assert snapshot.current_phase == "P1"
    assert p1.status == PhaseStatus.IN_PROGRESS and p1.reviews == []
    assert p2.status == PhaseStatus.NEEDS_REVIEW and p2.reviews == []
    alignment = next(c for c in p1.checkpoints if c.checkpoint_id == "alignment")
    assert alignment.status == CheckpointStatus.PENDING and not alignment.user_message_id
    # Everything Discovery recorded is superseded, and the user check it added is dropped.
    assert {p.status for p in snapshot.pain_points} == {"superseded"}
    assert {w.status for w in snapshot.desired_properties} == {"superseded"}
    user_dp = next(w for w in snapshot.desired_properties if w.proof == "user")
    assert next(c for c in p4.checkpoints if c.checkpoint_id == user_dp.property_id).status == (
        CheckpointStatus.WAIVED
    )


def test_no_stale_pass_survives_a_revision(repo: Path) -> None:
    _discovery_then_two_phases(repo)
    _invoke("assess", "revise", "--reason", "Different audience")
    # P1's old PASS is gone, and its "yes" was to the old framing.
    _fails("phase", "accept", "P1")
    _invoke(*ALIGN, "--status", "needs_user")
    _fails(*ALIGN, "--status", "passed")  # the old "yes, that's it" doesn't count
    _say(repo, "yes, the paper log")
    _invoke(*ALIGN, "--status", "passed")


def test_check_names_what_to_redo(repo: Path) -> None:
    _discovery_then_two_phases(repo)
    _invoke("assess", "revise", "--reason", "Different audience")
    check = _invoke("check")
    assert "Discovery was revised: Different audience" in check
    assert "re-review P2" in check
    assert "P2 has evidence but no review" in check


def test_superseded_properties_stop_gating_and_new_ones_start(repo: Path) -> None:
    _discovery_then_two_phases(repo)
    _invoke("assess", "revise", "--reason", "Different audience")
    # The old auto property no longer gates P2's re-review...
    assert run_gate(repo, "P2").verdict == GateVerdict.PASS
    # ...a new one bound to a phase still ahead does.
    _invoke("assess", "want", "Prints on one page", "--proof", "auto", "--phase", "P3")
    dp = next(w for w in load_active_snapshot(repo).desired_properties if w.status == "active")
    assert dp.phase_id == "P3"


def test_a_completed_goal_reopens(repo: Path) -> None:
    for phase_id in ("P1", "P2", "P3", "P4"):
        _accept(repo, phase_id)
    assert load_active_snapshot(repo).status == GoalStatus.COMPLETE
    _invoke("assess", "revise", "--reason", "Wrong problem")
    snapshot = load_active_snapshot(repo)
    assert snapshot.status == GoalStatus.ACTIVE and snapshot.current_phase == "P1"
    assert all(p.status == PhaseStatus.NEEDS_REVIEW for p in snapshot.phases[1:])


def test_the_notes_keep_the_history(repo: Path) -> None:
    _discovery_then_two_phases(repo)
    _invoke("assess", "revise", "--reason", "They want a paper log")
    notes = next((repo / ".agent-workflow" / "goals").iterdir()) / "DISCOVERY.md"
    text = notes.read_text()
    assert "## Revisions" in text and "They want a paper log" in text
    assert "Logging takes too many taps" not in text  # superseded, no longer current
