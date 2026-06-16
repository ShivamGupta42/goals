"""The accept gate must earn trust by execution, not narration.

Examples here are deliberately generic (a trivial check that exits 0/1). The gate
encodes no domain knowledge — only that proof was *run*, not asserted.
"""

import subprocess
from pathlib import Path

from typer.testing import CliRunner

from goals.cli import app
from goals.gates import review_phase
from goals.models import (
    Assumption,
    Evidence,
    Event,
    EventType,
    GateVerdict,
    Phase,
    Verification,
)
from goals.runtime import (
    append_event,
    create_goal,
    load_active_snapshot,
    run_gate,
    verify_phase,
)


def _repo_with_goal(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (
        ["git", "init", "-q", "-b", "feature"],
        ["git", "config", "user.email", "t@e.com"],
        ["git", "config", "user.name", "T"],
    ):
        subprocess.run(cmd, cwd=repo, check=True)
    (repo / "README.md").write_text("# demo\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    create_goal("ship it", repo, workspace="in_place")
    return repo


def _record_evidence(repo: Path, goal_id: str, verifications: list[dict]) -> None:
    # Build through the model (as the CLI does) so verification ids are baked into
    # the stored payload and stay stable across event replay.
    evidence = Evidence(
        acceptance_met=["done"],
        verifications=[Verification(**v) for v in verifications],
    )
    append_event(
        repo,
        Event(
            goal_id=goal_id,
            event_type=EventType.PHASE_EVIDENCE,
            payload={"phase_id": "P1", "evidence": evidence.model_dump()},
        ),
    )


# --- unit: the gate logic ------------------------------------------------- #
def test_prose_only_evidence_is_rejected() -> None:
    # The old hole: a non-empty checks_run string + high confidence used to pass.
    phase = Phase(
        phase_id="P1",
        title="Step",
        goal="Do it",
        evidence=Evidence(checks_run=["I ran it, it works"], confidence=0.95),
    )
    result = review_phase(phase)
    assert result.verdict == GateVerdict.FAIL
    assert any("no automated check" in issue.lower() for issue in result.p0)


def test_declared_but_unrun_check_does_not_pass() -> None:
    phase = Phase(
        phase_id="P1",
        title="Step",
        goal="Do it",
        evidence=Evidence(
            verifications=[Verification(covers="done", kind="auto", command="true")]
        ),
    )
    # ran defaults False — declaring a command is not running it.
    assert review_phase(phase).verdict == GateVerdict.FAIL


def test_executed_passing_check_passes() -> None:
    phase = Phase(
        phase_id="P1",
        title="Step",
        goal="Do it",
        evidence=Evidence(
            verifications=[
                Verification(covers="done", kind="auto", command="true", ran=True, passed=True)
            ]
        ),
    )
    assert review_phase(phase).verdict == GateVerdict.PASS


# --- integration: only the engine can flip passed ------------------------- #
def test_agent_cannot_fake_a_pass(tmp_path: Path) -> None:
    repo = _repo_with_goal(tmp_path)
    goal_id = load_active_snapshot(repo).goal_id
    # Agent records a verification it claims already passed — the reducer strips it.
    _record_evidence(
        repo,
        goal_id,
        [{"covers": "done", "kind": "auto", "command": "true", "ran": True, "passed": True}],
    )
    snap = load_active_snapshot(repo)
    v = snap.phases[0].evidence.verifications[0]
    assert v.ran is False and v.passed is False  # trust cannot be self-asserted
    assert run_gate(repo, "P1").verdict == GateVerdict.FAIL


def test_engine_verify_earns_the_pass(tmp_path: Path) -> None:
    repo = _repo_with_goal(tmp_path)
    goal_id = load_active_snapshot(repo).goal_id
    _record_evidence(repo, goal_id, [{"covers": "done", "kind": "auto", "command": "true"}])
    assert run_gate(repo, "P1").verdict == GateVerdict.FAIL  # not yet run
    verify_phase(repo, "P1")  # engine runs `true` -> exit 0
    snap = load_active_snapshot(repo)
    assert snap.phases[0].evidence.verifications[0].passed is True
    assert run_gate(repo, "P1").verdict == GateVerdict.PASS


def test_failing_command_blocks(tmp_path: Path) -> None:
    repo = _repo_with_goal(tmp_path)
    goal_id = load_active_snapshot(repo).goal_id
    _record_evidence(repo, goal_id, [{"covers": "done", "kind": "auto", "command": "false"}])
    verify_phase(repo, "P1")  # engine runs `false` -> exit 1
    assert run_gate(repo, "P1").verdict == GateVerdict.FAIL


# --- load-bearing assumptions must have an executed falsifier ------------- #
def test_load_bearing_assumption_needs_a_passing_falsifier(tmp_path: Path) -> None:
    repo = _repo_with_goal(tmp_path)
    goal_id = load_active_snapshot(repo).goal_id
    append_event(
        repo,
        Event(
            goal_id=goal_id,
            event_type=EventType.ASSUMPTION_RECORDED,
            payload={
                "assumption": Assumption(
                    assumption_id="A-load", statement="the core premise", depends_on=True,
                    phase_id="P1",
                ).model_dump()
            },
        ),
    )
    # An executed check that does NOT cover the assumption -> still blocked.
    _record_evidence(repo, goal_id, [{"covers": "done", "kind": "auto", "command": "true"}])
    verify_phase(repo, "P1")
    blocked = run_gate(repo, "P1")
    assert blocked.verdict == GateVerdict.FAIL
    assert any("A-load" in issue for issue in blocked.p0)

    # Add a falsifier that covers the assumption and run it -> passes.
    _record_evidence(
        repo,
        goal_id,
        [
            {"covers": "done", "kind": "auto", "command": "true"},
            {"covers": "A-load", "kind": "auto", "command": "true"},
        ],
    )
    verify_phase(repo, "P1")
    assert run_gate(repo, "P1").verdict == GateVerdict.PASS


def test_re_recording_evidence_invalidates_a_prior_pass(tmp_path: Path) -> None:
    # Bypass guard: pass the gate once, then re-record different (unverified)
    # evidence. The stale PASS must not let `accept` ride through unverified.
    import pytest

    from goals.runtime import transition_phase
    from goals.storage import GoalsError

    repo = _repo_with_goal(tmp_path)
    goal_id = load_active_snapshot(repo).goal_id
    _record_evidence(repo, goal_id, [{"covers": "done", "kind": "auto", "command": "true"}])
    verify_phase(repo, "P1")
    assert run_gate(repo, "P1").verdict == GateVerdict.PASS  # records a PASS review

    # Re-record evidence — the prior review is now stale and must be cleared.
    _record_evidence(repo, goal_id, [{"covers": "done", "kind": "auto", "command": "true"}])
    assert load_active_snapshot(repo).phases[0].reviews == []
    with pytest.raises(GoalsError):
        transition_phase(repo, "P1", "accept")  # cannot accept on a stale/absent review

    # Re-verify + re-review earns it back.
    verify_phase(repo, "P1")
    assert run_gate(repo, "P1").verdict == GateVerdict.PASS
    transition_phase(repo, "P1", "accept")  # now allowed


def test_re_verify_after_review_also_invalidates_it(tmp_path: Path) -> None:
    import pytest

    from goals.runtime import transition_phase
    from goals.storage import GoalsError

    repo = _repo_with_goal(tmp_path)
    goal_id = load_active_snapshot(repo).goal_id
    _record_evidence(repo, goal_id, [{"covers": "done", "kind": "auto", "command": "true"}])
    verify_phase(repo, "P1")
    assert run_gate(repo, "P1").verdict == GateVerdict.PASS
    verify_phase(repo, "P1")  # re-run checks -> prior review is stale
    assert load_active_snapshot(repo).phases[0].reviews == []
    with pytest.raises(GoalsError):
        transition_phase(repo, "P1", "accept")


def test_depends_assumption_without_phase_is_still_gated(tmp_path: Path, monkeypatch) -> None:
    # A load-bearing assumption recorded with no --phase must NOT escape the gate:
    # it is attributed to the current phase so a falsifier is still required.
    repo = _repo_with_goal(tmp_path)
    monkeypatch.chdir(repo)
    result = CliRunner().invoke(app, ["assess", "assume", "the core premise", "--depends"])
    assert result.exit_code == 0, result.stdout
    snap = load_active_snapshot(repo)
    assumption = snap.assumptions[0]
    assert assumption.depends_on is True
    assert assumption.phase_id == snap.current_phase  # attributed, not None

    # An executed check that doesn't cover the assumption -> gate still blocks.
    _record_evidence(repo, snap.goal_id, [{"covers": "done", "kind": "auto", "command": "true"}])
    verify_phase(repo, "P1")
    blocked = run_gate(repo, "P1")
    assert blocked.verdict == GateVerdict.FAIL
    assert any(assumption.assumption_id in issue for issue in blocked.p0)
