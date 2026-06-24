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
    GateFactType,
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
    phase = load_active_snapshot(repo).phases[0]
    expanded: list[dict] = []
    for verification in verifications:
        if verification.get("covers") == "done" and phase.acceptance_criteria:
            for index, _criterion in enumerate(phase.acceptance_criteria, start=1):
                copy = dict(verification)
                copy["covers"] = f"{phase.phase_id}.C{index}"
                expanded.append(copy)
        else:
            expanded.append(verification)
    evidence = Evidence(
        acceptance_met=["done"],
        verifications=[Verification(**v) for v in expanded],
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


# --- typed facts: the kernel reports *why*, mechanically -------------------- #
def _facts(phase: Phase, **kw) -> list[GateFactType]:
    return [f.fact_type for f in review_phase(phase, **kw).findings]


def test_prose_only_evidence_reports_no_passing_check_fact() -> None:
    phase = Phase(
        phase_id="P1",
        title="Step",
        goal="Do it",
        evidence=Evidence(checks_run=["I ran it"], confidence=0.95),
    )
    assert GateFactType.NO_PASSING_CHECK in _facts(phase)


def test_acceptance_not_met_reports_a_gap_fact() -> None:
    phase = Phase(
        phase_id="P1",
        title="Step",
        goal="Do it",
        evidence=Evidence(
            acceptance_not_met=["signup works"],
            verifications=[
                Verification(covers="done", kind="auto", command="true", ran=True, passed=True)
            ],
        ),
    )
    facts = _facts(phase)
    assert GateFactType.ACCEPTANCE_NOT_MET in facts
    assert review_phase(phase).verdict == GateVerdict.FAIL


def test_ran_and_failed_check_is_a_bug_fact_and_suppresses_generic_line() -> None:
    # A check the engine ran that exited non-zero is CHECK_FAILED — distinct from
    # "nothing ran". The generic NO_PASSING_CHECK line is suppressed to avoid
    # double-reporting, and its substring must be gone.
    phase = Phase(
        phase_id="P1",
        title="Step",
        goal="Do it",
        evidence=Evidence(
            verifications=[
                Verification(covers="done", kind="auto", command="false", ran=True, passed=False)
            ]
        ),
    )
    result = review_phase(phase)
    facts = [f.fact_type for f in result.findings]
    assert GateFactType.CHECK_FAILED in facts
    assert GateFactType.NO_PASSING_CHECK not in facts
    assert not any("no automated check" in line.lower() for line in result.p0)
    assert result.verdict == GateVerdict.FAIL


def test_missing_falsifier_fact_carries_assumption_ref() -> None:
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
    findings = review_phase(phase, load_bearing=[("A-load", "the premise")]).findings
    falsifier = [f for f in findings if f.fact_type == GateFactType.MISSING_FALSIFIER]
    assert falsifier and falsifier[0].ref == "A-load"


def test_failed_check_and_missing_falsifier_keep_stable_order() -> None:
    # When a ran-and-failed check co-occurs with an uncovered load-bearing assumption,
    # CHECK_FAILED precedes MISSING_FALSIFIER — a stable order p0 consumers can rely on.
    phase = Phase(
        phase_id="P1",
        title="Step",
        goal="Do it",
        evidence=Evidence(
            verifications=[
                Verification(covers="done", kind="auto", command="false", ran=True, passed=False)
            ]
        ),
    )
    facts = _facts(phase, load_bearing=[("A-load", "the premise")])
    assert facts == [GateFactType.CHECK_FAILED, GateFactType.MISSING_FALSIFIER]


def test_p0_mirrors_finding_messages_verbatim() -> None:
    phase = Phase(
        phase_id="P1",
        title="Step",
        goal="Do it",
        evidence=Evidence(checks_run=["note"], confidence=0.9),
    )
    result = review_phase(phase)
    assert result.p0 == [f.message for f in result.findings]


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


def test_review_cap_blocks_at_default_after_three_attempts(tmp_path: Path) -> None:
    repo = _repo_with_goal(tmp_path)
    goal_id = load_active_snapshot(repo).goal_id
    _record_evidence(repo, goal_id, [{"covers": "done", "kind": "auto", "command": "false"}])
    verify_phase(repo, "P1")
    assert run_gate(repo, "P1").verdict == GateVerdict.FAIL  # attempt 1
    assert run_gate(repo, "P1").verdict == GateVerdict.FAIL  # attempt 2
    assert run_gate(repo, "P1").verdict == GateVerdict.BLOCKED  # attempt 3 == default cap


def test_review_cap_honors_raised_env(tmp_path: Path, monkeypatch) -> None:
    # GOALS_MAX_PHASE_ATTEMPTS must *raise* the cap too, not only lower it: the
    # gate and the Stop hook share resolve_max_phase_attempts, so at a cap of 5
    # the gate keeps returning FAIL past the default 3 and only BLOCKs at 5.
    monkeypatch.setenv("GOALS_MAX_PHASE_ATTEMPTS", "5")
    repo = _repo_with_goal(tmp_path)
    goal_id = load_active_snapshot(repo).goal_id
    _record_evidence(repo, goal_id, [{"covers": "done", "kind": "auto", "command": "false"}])
    verify_phase(repo, "P1")
    verdicts = [run_gate(repo, "P1").verdict for _ in range(5)]
    assert verdicts == [GateVerdict.FAIL] * 4 + [GateVerdict.BLOCKED]


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


def test_depends_assumption_with_no_phase_to_attribute_errors(monkeypatch) -> None:
    # If there is no phase to attribute a load-bearing assumption to, recording it
    # must fail loudly rather than silently escape the gate.
    from goals.models import GoalSnapshot, WorktreeLease

    snap = GoalSnapshot(
        goal_id="g",
        objective="o",
        topology=WorktreeLease(
            base_repo="/r", base_branch="main", worktree_path="/r", branch="goal/g"
        ),
        phases=[],
        current_phase=None,
    )
    monkeypatch.setattr("goals.cli.load_active_snapshot", lambda cwd: snap)
    result = CliRunner().invoke(app, ["assess", "assume", "X", "--depends"])
    assert result.exit_code == 1
    assert "must belong to a phase" in result.stdout


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
