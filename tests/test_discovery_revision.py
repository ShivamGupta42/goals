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
    assert "P1 reopened" in out and "P2 can be re-reviewed only after P1 is accepted again" in out

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
    # No advice the engine would refuse: P2's review waits for P1.
    assert "Run `goals phase review P2`" not in check


def _reconfirm_p1(repo: Path) -> None:
    _invoke(*ALIGN, "--status", "needs_user")
    _say(repo, "yes, the new plan")
    _invoke(*ALIGN, "--status", "passed")
    _accept(repo, "P1")


def test_later_phases_wait_for_the_user_to_reconfirm(repo: Path) -> None:
    _discovery_then_two_phases(repo)
    _invoke("assess", "revise", "--reason", "Different audience")
    # No rubber-stamping P2 on its old evidence before the user says yes again.
    assert "waits until P1 is re-confirmed" in _fails("phase", "review", "P2")
    assert "waits until P1 is re-confirmed" in _fails("phase", "accept", "P2")
    # A want for the new framing can still target P2, since it isn't accepted.
    _invoke("assess", "want", "Prints on one page", "--proof", "auto", "--phase", "P2")
    _reconfirm_p1(repo)
    dp = next(w for w in load_active_snapshot(repo).desired_properties if w.status == "active")
    # The old property no longer gates P2; the new one does.
    blocked = run_gate(repo, "P2")
    assert blocked.verdict != GateVerdict.PASS and any(f.ref == dp.property_id for f in blocked.findings)


def test_a_set_aside_property_cannot_be_revived_by_id(repo: Path) -> None:
    _discovery_then_two_phases(repo)
    user_dp = next(w for w in load_active_snapshot(repo).desired_properties if w.proof == "user")
    _invoke("assess", "revise", "--reason", "Different audience")
    out = _fails("assess", "want", user_dp.statement, "--id", user_dp.property_id)
    assert "set aside when Discovery was revised" in out


def test_an_earlier_unverified_close_stays_visible_after_a_revision(repo: Path) -> None:
    _discovery_then_two_phases(repo)
    _invoke("phase", "start", "P3")
    _accept(repo, "P3")
    user_dp = next(w for w in load_active_snapshot(repo).desired_properties if w.proof == "user")
    _invoke("checkpoint", "record", "P4", user_dp.property_id, "--status", "needs_user")
    _invoke("checkpoint", "record", "P4", user_dp.property_id, "--status", "passed", "--unverified")
    _invoke("assess", "revise", "--reason", "Different audience")
    assert "Not verified" in _invoke("check")


def test_an_older_goals_cannot_silently_undo_a_revision(repo: Path) -> None:
    # An older binary skips DISCOVERY_REVISED and could accept on stale reviews;
    # replay ignores an accept that didn't pass review after the revision.
    from goals.models import Event, EventType
    from goals.storage import EventStore

    _discovery_then_two_phases(repo)
    _invoke("assess", "revise", "--reason", "Different audience")
    snapshot = load_active_snapshot(repo)
    store = EventStore(next((repo / ".agent-workflow" / "goals").iterdir()))
    for phase_id in ("P1", "P2"):
        store.append(Event(goal_id=snapshot.goal_id, event_type=EventType.PHASE_ACCEPTED, payload={"phase_id": phase_id}))
    after = load_active_snapshot(repo)
    assert after.phases[0].status == PhaseStatus.IN_PROGRESS
    assert after.phases[1].status == PhaseStatus.NEEDS_REVIEW


def test_a_revision_asks_for_a_yes_even_if_discovery_was_skipped(repo: Path) -> None:
    _accept(repo, "P1")
    _invoke("assess", "revise", "--reason", "Wrong problem")
    alignment = next(c for c in load_active_snapshot(repo).phases[0].checkpoints if c.kind.value == "understanding")
    assert alignment.status == CheckpointStatus.PENDING and alignment.required and alignment.user_owned
    _fails("phase", "accept", "P1")


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
    current, set_aside = text.split("## Set aside by revisions")
    assert "Logging takes too many taps" not in current  # no longer what hurts today...
    assert "Logging takes too many taps" in set_aside  # ...but what was dropped is on record


# --------------------------------------------------------------------------- #
# Final-review fixes
# --------------------------------------------------------------------------- #
def test_the_revision_block_lifts_once_the_user_reconfirms(repo: Path) -> None:
    _discovery_then_two_phases(repo)
    _invoke("assess", "revise", "--reason", "Different audience")
    _reconfirm_p1(repo)
    assert load_active_snapshot(repo).discovery_revisions[-1].settled
    # Reopening P1 later for an unrelated reason doesn't re-trigger the revision block.
    _invoke("phase", "start", "P1")
    assert "Discovery was revised" not in _invoke("check")


def test_an_older_goals_reviewing_on_its_own_cannot_undo_a_revision(repo: Path) -> None:
    # An older binary skips DISCOVERY_REVISED, so its own review of P1 passes on
    # the stale alignment; replay still won't accept P1 while it's blocked, nor
    # count a later phase's pass before P1 is re-confirmed.
    from goals.models import Event, EventType, GateResult
    from goals.storage import EventStore

    _discovery_then_two_phases(repo)
    _invoke("assess", "revise", "--reason", "Different audience")
    snapshot = load_active_snapshot(repo)
    store = EventStore(next((repo / ".agent-workflow" / "goals").iterdir()))
    passed = GateResult(gate_id="phase-review", verdict=GateVerdict.PASS, summary="ok").model_dump()
    for phase_id in ("P1", "P2"):
        store.append(Event(goal_id=snapshot.goal_id, event_type=EventType.PHASE_REVIEWED,
                           payload={"phase_id": phase_id, "gate_result": passed}))
        store.append(Event(goal_id=snapshot.goal_id, event_type=EventType.PHASE_ACCEPTED,
                           payload={"phase_id": phase_id}))
    after = load_active_snapshot(repo)
    assert after.phases[0].status != PhaseStatus.ACCEPTED
    assert after.phases[1].status != PhaseStatus.ACCEPTED
    assert not after.discovery_revisions[-1].settled


def test_an_older_goals_rerecording_alignment_keeps_it_the_users(repo: Path) -> None:
    from goals.models import Event, EventType
    from goals.storage import EventStore

    _discovery_then_two_phases(repo)
    _invoke("assess", "revise", "--reason", "Different audience")
    snapshot = load_active_snapshot(repo)
    old_style = {"checkpoint_id": "alignment", "kind": "custom", "title": "Does this match?",
                 "status": "passed", "required": True, "needs_user": False}
    EventStore(next((repo / ".agent-workflow" / "goals").iterdir())).append(
        Event(goal_id=snapshot.goal_id, event_type=EventType.PHASE_CHECKPOINT_RECORDED,
              payload={"phase_id": "P1", "checkpoint": old_style}))
    alignment = next(c for c in load_active_snapshot(repo).phases[0].checkpoints if c.checkpoint_id == "alignment")
    assert alignment.user_owned and alignment.kind.value == "understanding"
