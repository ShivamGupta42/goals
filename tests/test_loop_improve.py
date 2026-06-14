from pathlib import Path

from goals.loop_builder import load_design, new_session, run_script
from goals.loop_check import check_loop
from goals.loop_improve import (
    apply_loop_improvements,
    detect_phase_regression,
    log_phase_regression,
    plan_loop_improvements,
)
from goals.memory import load_memory
from goals.models import (
    Evidence,
    GateResult,
    GateVerdict,
    GoalSnapshot,
    Phase,
    WorktreeLease,
)


def _snapshot(tmp_path: Path, phase: Phase) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id="demo",
        objective="Demo",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=[phase],
        current_phase=phase.phase_id,
    )


# --- detection / routing --------------------------------------------------- #
def test_clean_phase_has_no_regressions(tmp_path: Path) -> None:
    phase = Phase(
        phase_id="P1",
        title="P",
        goal="g",
        evidence=Evidence(acceptance_met=["done"], confidence=0.9),
        reviews=[GateResult(gate_id="phase-review", verdict=GateVerdict.PASS, summary="ok")],
    )
    assert detect_phase_regression(_snapshot(tmp_path, phase), "P1") == []


def test_unmet_acceptance_routes_to_improve_now(tmp_path: Path) -> None:
    phase = Phase(
        phase_id="P1",
        title="P",
        goal="g",
        evidence=Evidence(acceptance_not_met=["DoD not visible"], confidence=0.4),
    )
    findings = detect_phase_regression(_snapshot(tmp_path, phase), "P1")
    blocking = [f for f in findings if f.routing == "improve_now"]
    assert any(f.severity == "p0" for f in blocking)


def test_known_gap_routes_to_defer(tmp_path: Path) -> None:
    phase = Phase(
        phase_id="P1",
        title="P",
        goal="g",
        evidence=Evidence(acceptance_met=["x"], confidence=0.9, known_gaps=["migration order unclear"]),
    )
    findings = detect_phase_regression(_snapshot(tmp_path, phase), "P1")
    assert findings and all(f.routing == "defer" for f in findings)


def test_blocked_and_needs_human_reviews_surface_even_without_p0(tmp_path: Path) -> None:
    # A blocking verdict with no itemized p0 must still route to improve-now.
    for verdict in (GateVerdict.BLOCKED, GateVerdict.NEEDS_HUMAN):
        phase = Phase(
            phase_id="P1",
            title="P",
            goal="g",
            reviews=[GateResult(gate_id="phase-review", verdict=verdict, summary="data-loss risk")],
        )
        findings = detect_phase_regression(_snapshot(tmp_path, phase), "P1")
        assert any(f.routing == "improve_now" for f in findings), verdict


def test_unsafe_review_is_blocking(tmp_path: Path) -> None:
    phase = Phase(
        phase_id="P1",
        title="P",
        goal="g",
        reviews=[
            GateResult(gate_id="phase-review", verdict=GateVerdict.UNSAFE, summary="leak", p0=["secret"])
        ],
    )
    findings = detect_phase_regression(_snapshot(tmp_path, phase), "P1")
    assert any(f.routing == "improve_now" and f.area == "safety" for f in findings)


# --- logging with evidence ------------------------------------------------- #
def test_simulated_failed_phase_writes_evidence_backed_memory(tmp_path: Path) -> None:
    phase = Phase(
        phase_id="P1",
        title="P",
        goal="g",
        evidence=Evidence(acceptance_not_met=["DoD not visible"], confidence=0.3),
    )
    snapshot = _snapshot(tmp_path, phase)
    report = log_phase_regression(tmp_path, snapshot, "P1")

    assert report.recorded >= 1
    assert report.surfaced  # the unmet-acceptance finding surfaces
    memory = load_memory(tmp_path, snapshot)
    assert memory.entries
    # Every recorded entry carries evidence references back to the phase.
    assert all(entry.evidence_refs for entry in memory.entries)
    assert any("phase:P1" in entry.evidence_refs for entry in memory.entries)


def test_logging_is_idempotent(tmp_path: Path) -> None:
    phase = Phase(
        phase_id="P1",
        title="P",
        goal="g",
        evidence=Evidence(acceptance_not_met=["x"], confidence=0.3),
    )
    snapshot = _snapshot(tmp_path, phase)
    log_phase_regression(tmp_path, snapshot, "P1")
    first = len(load_memory(tmp_path, snapshot).entries)
    log_phase_regression(tmp_path, snapshot, "P1")
    assert len(load_memory(tmp_path, snapshot).entries) == first


# --- improvement loop ------------------------------------------------------ #
def test_improve_is_a_no_op_with_no_memory(tmp_path: Path) -> None:
    phase = Phase(phase_id="P1", title="P", goal="g")
    snapshot = _snapshot(tmp_path, phase)
    plan = plan_loop_improvements(tmp_path, snapshot)
    assert plan.improvements == []
    assert "nothing to improve" in plan.summary.lower()


def test_improve_turns_memory_into_reviewable_change_set(tmp_path: Path) -> None:
    # Two related blocking failures accumulate into an actionable suggestion.
    for note in ("DoD not visible", "tests missing"):
        phase = Phase(
            phase_id="P1",
            title="P",
            goal="g",
            evidence=Evidence(acceptance_not_met=[note], confidence=0.3),
        )
        log_phase_regression(tmp_path, _snapshot(tmp_path, phase), "P1")
    snapshot = _snapshot(tmp_path, Phase(phase_id="P1", title="P", goal="g"))
    plan = plan_loop_improvements(tmp_path, snapshot)
    assert plan.improvements
    assert plan.dry_run is True


def test_deferred_items_do_not_auto_apply(tmp_path: Path) -> None:
    # A deferred-only finding with no loop design present applies nothing.
    phase = Phase(
        phase_id="P1",
        title="P",
        goal="g",
        evidence=Evidence(acceptance_met=["x"], confidence=0.9, known_gaps=["later"]),
    )
    snapshot = _snapshot(tmp_path, phase)
    log_phase_regression(tmp_path, snapshot, "P1")
    plan = apply_loop_improvements(tmp_path, snapshot, design_dir=None)
    assert plan.applied == []
    assert plan.dry_run is False


def test_improve_applies_safe_loop_design_fixes_on_approval(tmp_path: Path) -> None:
    # A saved design with a fixable defect; --apply applies the safe fix.
    session = new_session(tmp_path, skills=[])
    run_script(
        session,
        ["objective Fixme", "add Plan", "accept The dashboard renders.", "save"],
        write=lambda _msg: None,
    )
    snapshot = _snapshot(tmp_path, Phase(phase_id="P1", title="P", goal="g"))
    plan = apply_loop_improvements(tmp_path, snapshot, design_dir=tmp_path)
    assert plan.applied  # termination + evidence fixes applied
    assert check_loop(load_design(tmp_path)).has_blocking is False


# --- dogfood: the builder reproduces its own goal spec --------------------- #
def test_builder_reproduces_its_own_goal_spec(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1] / "examples" / "visual-builder.loop"
    ).read_text(encoding="utf-8")
    session = new_session(tmp_path, skills=[])
    run_script(session, script.splitlines(), write=lambda _msg: None)

    design = session.design
    assert len(design.phases) == 3
    assert "visual goal-loop builder" in design.objective
    # The reproduced loop is itself healthy under the linter.
    assert check_loop(design).passed
    # And it round-trips through save/load.
    reloaded = load_design(tmp_path)
    assert reloaded == design
