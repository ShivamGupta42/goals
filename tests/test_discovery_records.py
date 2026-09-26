"""Pain points and desired properties are first-class, and the run is held to them.

`goals assess want --proof auto` binds a property to a phase whose review needs an
engine-run automated check covering the property's id; `--proof user` adds a user
checkpoint (same id) to the last phase that only the user's reply can close.
(Roadmap: Discovery build step 3.)
"""

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from goals.cli import app
from goals.models import CheckpointKind, CheckpointStatus, GateVerdict, Phase
from goals.runtime import create_goal, load_active_snapshot, run_gate

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


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    repo = _git_repo(tmp_path / "repo")
    create_goal("ship it", repo, workspace="in_place")
    monkeypatch.chdir(repo)
    return repo


@pytest.fixture
def two_phase_repo(tmp_path: Path, monkeypatch) -> Path:
    repo = _git_repo(tmp_path / "two")
    phases = [
        Phase(phase_id="P1", title="Build", goal="Build it", acceptance_criteria=["Built."]),
        Phase(phase_id="P2", title="Hand over", goal="Hand it over", acceptance_criteria=["Handed."]),
    ]
    create_goal("two step goal", repo, workspace="in_place", phases=phases)
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


def _confirm_alignment_if_asked_for(repo: Path, phase_id: str) -> None:
    """Discovery records add a pending alignment check; confirm it the real way."""
    first = load_active_snapshot(repo).phases[0]
    alignment = next((c for c in first.checkpoints if c.checkpoint_id == "alignment"), None)
    if phase_id != first.phase_id or alignment is None or alignment.status == CheckpointStatus.PASSED:
        return
    _invoke("checkpoint", "record", phase_id, "alignment", "--status", "needs_user")
    _say(repo, "yes, that's what I want")
    _invoke("checkpoint", "record", phase_id, "alignment", "--status", "passed")


def _evidence(repo: Path, phase_id: str, extra: list[dict]) -> None:
    _confirm_alignment_if_asked_for(repo, phase_id)
    phase = next(p for p in load_active_snapshot(repo).phases if p.phase_id == phase_id)
    verifications = [
        {"covers": f"{phase_id}.C{i + 1}", "kind": "auto", "command": "true"}
        for i in range(len(phase.acceptance_criteria))
    ] + extra
    path = repo / f"evidence-{phase_id}.json"
    path.write_text(json.dumps({"checks_run": ["true"], "verifications": verifications}))
    _invoke("phase", "evidence", phase_id, "--file", str(path))
    _invoke("phase", "verify", phase_id)


def _say(repo: Path, text: str) -> None:
    payload = {"hook_event_name": "UserPromptSubmit", "prompt": text, "cwd": str(repo)}
    assert runner.invoke(app, ["hooks", "user-prompt"], input=json.dumps(payload)).exit_code == 0


def test_pain_points_are_recorded_and_reworded_by_id(repo: Path) -> None:
    out = _invoke("assess", "pain", "Logging takes too many taps")
    pain_id = out.strip().rsplit(" ", 1)[-1]
    _invoke("assess", "pain", "Logging takes too many taps on the phone", "--id", pain_id)
    pains = load_active_snapshot(repo).pain_points
    assert [p.statement for p in pains] == ["Logging takes too many taps on the phone"]
    assert "Unknown pain point id" in _fails("assess", "pain", "x", "--id", "PP-nope")


def test_an_auto_property_needs_an_executed_check_for_its_id(repo: Path) -> None:
    out = _invoke("assess", "want", "Logging takes under 5 seconds", "--proof", "auto", "--phase", "P1")
    assert "proven by an automated check in P1" in out
    dp = load_active_snapshot(repo).desired_properties[0].property_id

    # A manual note covering the property doesn't count: the user asked for this outcome.
    _evidence(repo, "P1", [{"covers": dp, "kind": "manual", "rationale": "felt fast"}])
    blocked = run_gate(repo, "P1")
    assert blocked.verdict != GateVerdict.PASS
    assert any(f.ref == dp and "Desired property" in f.message for f in blocked.findings)

    _evidence(repo, "P1", [{"covers": dp, "kind": "auto", "command": "true"}])
    assert run_gate(repo, "P1").verdict == GateVerdict.PASS


def test_an_auto_property_only_gates_its_own_phase(repo: Path) -> None:
    _invoke("assess", "want", "Works offline", "--proof", "auto", "--phase", "P3")
    _evidence(repo, "P1", [])
    assert run_gate(repo, "P1").verdict == GateVerdict.PASS


def test_a_user_property_blocks_the_last_phase_of_a_custom_loop(two_phase_repo: Path) -> None:
    repo = two_phase_repo
    out = _invoke("assess", "want", "I trust the number without checking it", "--proof", "user")
    assert "the user confirms it in P2" in out
    dp = load_active_snapshot(repo).desired_properties[0]
    assert dp.phase_id == "P2"
    check = next(c for c in load_active_snapshot(repo).phases[1].checkpoints if c.checkpoint_id == dp.property_id)
    assert check.kind == CheckpointKind.HUMAN_VALIDATION
    assert check.status == CheckpointStatus.PENDING and check.required and check.user_owned

    _evidence(repo, "P2", [])
    blocked = run_gate(repo, "P2")
    assert blocked.verdict != GateVerdict.PASS
    assert any("checkpoint" in issue.lower() for issue in blocked.p0)
    _fails("phase", "accept", "P2")  # AC-4: accepting phases[-1] is refused
    # The agent can't close it on its own word...
    _fails("checkpoint", "record", "P2", dp.property_id, "--status", "passed")
    # ...only after asking and getting the user's reply.
    _invoke("checkpoint", "record", "P2", dp.property_id, "--status", "needs_user")
    _say(repo, "Yes, I'd trust that number.")
    _invoke("checkpoint", "record", "P2", dp.property_id, "--status", "passed")
    assert run_gate(repo, "P2").verdict == GateVerdict.PASS
    assert "Accepted phase P2" in _invoke("phase", "accept", "P2")


def test_want_validates_proof_and_phase(repo: Path) -> None:
    assert "Say how it's proven" in _fails("assess", "want", "Fast")
    assert "needs --phase" in _fails("assess", "want", "Fast", "--proof", "auto")
    assert "Unknown phase id: P9" in _fails("assess", "want", "Fast", "--proof", "auto", "--phase", "P9")
    assert "proof" in _fails("assess", "want", "Fast", "--proof", "vibes", "--phase", "P3")
    assert "Unknown desired property id" in _fails("assess", "want", "x", "--id", "DP-nope")


def test_rewording_keeps_proof_and_phase_and_refreshes_an_open_check(repo: Path) -> None:
    _invoke("assess", "want", "Simple enough for a relative", "--proof", "user")
    dp = load_active_snapshot(repo).desired_properties[0]
    _invoke("assess", "want", "Simple enough for a non-technical relative", "--id", dp.property_id)
    snapshot = load_active_snapshot(repo)
    reworded = snapshot.desired_properties[0]
    assert (reworded.proof, reworded.phase_id) == ("user", "P4")
    check = next(c for c in snapshot.phases[3].checkpoints if c.checkpoint_id == dp.property_id)
    assert check.title == "Ask the user: Simple enough for a non-technical relative"
    assert check.status == CheckpointStatus.PENDING
    assert "record a new property" in _fails("assess", "want", "x", "--id", dp.property_id, "--proof", "auto")
    assert "is proven in P4" in _fails("assess", "want", "x", "--id", dp.property_id, "--phase", "P2")


# --------------------------------------------------------------------------- #
# Review fixes (phase 3): no escaping via accepted phases, rewording, or asking early
# --------------------------------------------------------------------------- #
def _accept(repo: Path, phase_id: str) -> None:
    _evidence(repo, phase_id, [])
    assert run_gate(repo, phase_id).verdict == GateVerdict.PASS
    _invoke("phase", "accept", phase_id)


def test_a_property_cannot_be_bound_or_moved_to_an_accepted_phase(repo: Path) -> None:
    out = _invoke("assess", "want", "Works offline", "--proof", "auto", "--phase", "P3")
    dp = load_active_snapshot(repo).desired_properties[0].property_id
    assert dp in out
    _accept(repo, "P1")
    assert "already accepted" in _fails("assess", "want", "Fast", "--proof", "auto", "--phase", "P1")
    assert "is proven in P3" in _fails("assess", "want", "Works offline", "--id", dp, "--phase", "P1")


def test_rewording_after_the_users_yes_goes_through_a_revision(two_phase_repo: Path) -> None:
    repo = two_phase_repo
    _invoke("assess", "want", "Simple enough for my mum", "--proof", "user")
    dp = load_active_snapshot(repo).desired_properties[0].property_id
    # Before the user's yes to Discovery, wording can still be tuned.
    _invoke("assess", "want", "Simple enough for my mum to use", "--id", dp)
    _accept(repo, "P1")  # confirms Discovery on the user's reply
    out = _fails("assess", "want", "Needs no setup at all", "--id", dp)
    assert "confirmed Discovery" in out and "goals assess revise" in out
    _invoke("checkpoint", "record", "P2", dp, "--status", "needs_user")
    _say(repo, "Yes, mum could use it.")
    _invoke("checkpoint", "record", "P2", dp, "--status", "passed")
    assert "confirmed Discovery" in _fails("assess", "want", "Something else", "--id", dp)


def test_a_property_check_is_asked_in_its_own_phase_not_during_discovery(two_phase_repo: Path) -> None:
    repo = two_phase_repo
    _invoke("assess", "want", "I trust the number", "--proof", "user")
    dp = load_active_snapshot(repo).desired_properties[0].property_id
    early = _fails("checkpoint", "record", "P2", dp, "--status", "needs_user")
    assert "once there's something to try" in early
    _fails("checkpoint", "record", "P2", dp, "--status", "passed", "--unverified")
    _fails("checkpoint", "waive", "P2", dp, "--reason", "n/a", "--unverified")
    # Not actionable yet, so `goals issues` doesn't nag the agent to close or waive it.
    assert dp not in _invoke("issues")
    _accept(repo, "P1")
    _invoke("checkpoint", "record", "P2", dp, "--status", "needs_user")
    assert "Waiting on: you" in _invoke("check")


def test_an_accepted_phase_missing_its_property_proof_is_flagged(repo: Path) -> None:
    # e.g. accepted by an older Goals that didn't know about desired properties.
    from goals.models import DesiredProperty, Event, EventType
    from goals.storage import EventStore

    _accept(repo, "P1")
    snapshot = load_active_snapshot(repo)
    wanted = DesiredProperty(statement="Logs in under 5 seconds", proof="auto", phase_id="P1")
    goal_dir = next((repo / ".agent-workflow" / "goals").iterdir())
    EventStore(goal_dir).append(
        Event(
            goal_id=snapshot.goal_id,
            event_type=EventType.DESIRED_PROPERTY_RECORDED,
            payload={"property": wanted.model_dump()},
        )
    )
    issues = _invoke("issues")
    assert f"P1 was accepted without proving desired property {wanted.property_id}" in issues


def test_properties_show_in_goals_next_and_the_journey(repo: Path) -> None:
    _invoke("assess", "pain", "Logging takes too many taps")
    _invoke("assess", "want", "Logs in under 5 seconds", "--proof", "auto", "--phase", "P1")
    dp = load_active_snapshot(repo).desired_properties[0].property_id
    nxt = _invoke("next", "--agent", "claude")
    assert "What the user asked for, proven in this phase:" in nxt and dp in nxt
    journey = _invoke("assess", "journey")
    assert "## What hurts today" in journey and "Logging takes too many taps" in journey
    assert "## What the user wants" in journey and dp in journey


# --------------------------------------------------------------------------- #
# Final-review fixes
# --------------------------------------------------------------------------- #
def test_the_first_discovery_record_asks_for_the_users_yes(repo: Path) -> None:
    # An agent can't skip the alignment gate by never recording it...
    _invoke("assess", "pain", "Logging takes too many taps")
    alignment = next(c for c in load_active_snapshot(repo).phases[0].checkpoints if c.checkpoint_id == "alignment")
    assert alignment.kind == CheckpointKind.UNDERSTANDING and alignment.status == CheckpointStatus.PENDING
    assert alignment.required and alignment.user_owned
    # ...or by recording over it: it stays pending, and passing it needs the user's reply.
    assert "(pending)" in _invoke("checkpoint", "record", "P1", "alignment", "--title", "User agreed")
    _fails("checkpoint", "record", "P1", "alignment", "--status", "passed")
    _evidence(repo, "P1", [])  # confirms it the real way first
    assert run_gate(repo, "P1").verdict == GateVerdict.PASS


def test_a_custom_alignment_recorded_early_is_converted_and_reopened(repo: Path) -> None:
    _invoke("checkpoint", "record", "P1", "alignment", "--title", "User agreed", "--status", "passed")
    _invoke("assess", "pain", "Logging takes too many taps")
    alignment = next(c for c in load_active_snapshot(repo).phases[0].checkpoints if c.checkpoint_id == "alignment")
    assert alignment.kind == CheckpointKind.UNDERSTANDING and alignment.status == CheckpointStatus.PENDING


def test_a_user_judged_property_is_not_checked_in_the_first_phase(repo: Path) -> None:
    out = _fails("assess", "want", "feels calm", "--proof", "user", "--phase", "P1")
    assert "Leave --phase off" in out


def test_a_property_added_after_a_passing_review_must_still_be_proven(repo: Path) -> None:
    _evidence(repo, "P1", [])
    _accept(repo, "P1")
    _evidence(repo, "P2", [])
    assert run_gate(repo, "P2").verdict == GateVerdict.PASS
    _invoke("assess", "want", "Works offline", "--proof", "auto", "--phase", "P2")
    dp = next(w for w in load_active_snapshot(repo).desired_properties if w.status == "active")
    out = _fails("phase", "accept", "P2")
    assert dp.property_id in out and "last review passed before" in out
    _evidence(repo, "P2", [{"covers": dp.property_id, "kind": "auto", "command": "true"}])
    assert run_gate(repo, "P2").verdict == GateVerdict.PASS
    _invoke("phase", "accept", "P2")
