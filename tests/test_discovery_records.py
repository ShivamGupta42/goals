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


def _evidence(repo: Path, phase_id: str, extra: list[dict]) -> None:
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
    # The agent can't close it on its own word...
    _fails("checkpoint", "record", "P2", dp.property_id, "--status", "passed")
    # ...only after asking and getting the user's reply.
    _invoke("checkpoint", "record", "P2", dp.property_id, "--status", "needs_user")
    _say(repo, "Yes, I'd trust that number.")
    _invoke("checkpoint", "record", "P2", dp.property_id, "--status", "passed")
    assert run_gate(repo, "P2").verdict == GateVerdict.PASS


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
    assert "user check lives on P4" in _fails("assess", "want", "x", "--id", dp.property_id, "--phase", "P2")
