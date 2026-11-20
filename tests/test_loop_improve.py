import subprocess
from pathlib import Path

from goals.loop_builder import load_design, new_session, run_script
from goals.loop_check import check_loop
from goals.loop_improve import (
    LoopImprovement,
    LoopImprovementPlan,
    apply_loop_improvements,
    detect_phase_regression,
    log_phase_regression,
    plan_loop_improvements,
    render_loop_improvement_plan,
)
from goals.memory import append_memory_entry, load_memory
from goals.models import (
    Evidence,
    GateResult,
    GateVerdict,
    GoalSnapshot,
    Phase,
    SelfEvolutionEntry,
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
    first_report = log_phase_regression(tmp_path, snapshot, "P1")
    first = len(load_memory(tmp_path, snapshot).entries)
    second_report = log_phase_regression(tmp_path, snapshot, "P1")
    assert len(load_memory(tmp_path, snapshot).entries) == first
    # recorded reflects only what was newly written, not all findings.
    assert first_report.recorded >= 1
    assert second_report.recorded == 0
    assert "already recorded" in second_report.summary


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


def test_improve_works_design_first_without_an_active_goal(tmp_path: Path) -> None:
    # Design-first flow: a saved loop with no snapshot still surfaces and applies
    # the safe loop-design fixes. The builder always runs inside a git repo, so
    # memory resolution (which falls back to git_root when there is no snapshot)
    # has a root to find.
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    session = new_session(tmp_path, skills=[])
    run_script(
        session,
        ["objective Fixme", "add Plan", "accept The dashboard renders.", "save"],
        write=lambda _msg: None,
    )
    plan = plan_loop_improvements(tmp_path, None, design_dir=tmp_path)
    assert any(imp.auto_applicable for imp in plan.improvements)
    applied = apply_loop_improvements(tmp_path, None, design_dir=tmp_path)
    assert applied.applied
    assert check_loop(load_design(tmp_path)).has_blocking is False


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


# --- evidence behind each suggestion --------------------------------------- #
def _note(goal_id: str, note: str, refs: list[str], severity: str = "medium") -> SelfEvolutionEntry:
    return SelfEvolutionEntry(
        kind="friction",
        area="phase",
        note=note,
        severity=severity,  # type: ignore[arg-type]
        goal_id=goal_id,
        phase_id="P1",
        evidence_refs=refs,
    )


def _plan_from_notes(tmp_path: Path, notes: list[SelfEvolutionEntry]) -> LoopImprovementPlan:
    snapshot = _snapshot(tmp_path, Phase(phase_id="P1", title="P", goal="g"))
    for entry in notes:
        append_memory_entry(tmp_path, entry, snapshot)
    return plan_loop_improvements(tmp_path, snapshot)


def test_suggestion_carries_the_notes_and_ids_behind_it(tmp_path: Path) -> None:
    first = _note("g1", "Proof check was not set up before review.", ["event:abc-123"])
    second = _note("g2", "Proof check missing again at review time.", [])
    plan = _plan_from_notes(tmp_path, [first, second])

    imp = plan.improvements[0]
    assert imp.occurrences == 2
    assert imp.severity == "medium"
    assert imp.entry_ids == [first.entry_id, second.entry_id]
    assert "Proof check missing again at review time." in imp.why

    text = render_loop_improvement_plan(plan)
    assert "why: " in text and "Proof check missing again" in text
    assert "seen 2 times" in text and "severity medium" in text
    assert first.entry_id in text and second.entry_id in text
    assert "event:abc-123" in text and "g1" in text and "g2" in text


def test_a_suggestion_with_no_references_says_so(tmp_path: Path) -> None:
    plan = _plan_from_notes(tmp_path, [_note("", "Needs a closer look.", [], severity="high")])

    text = render_loop_improvement_plan(plan)

    assert "refs: none recorded" in text
    entry_id = plan.improvements[0].entry_ids[0]
    assert f"seen 1 time · severity high · notes {entry_id} · refs: none recorded" in text


def test_long_notes_and_many_references_are_cut(tmp_path: Path) -> None:
    refs = [f"event:{n:04d}" for n in range(12)]
    long_note = "word " * 200
    plan = _plan_from_notes(tmp_path, [_note("g1", "first", refs), _note("g2", long_note, [])])

    text = render_loop_improvement_plan(plan)

    assert "event:0000" in text and "event:0011" not in text
    assert "more" in text  # "+N more" marks what was left out
    assert max(len(line) for line in text.splitlines()) < 400
    assert "…" in text


def test_loop_check_improvement_says_why_too() -> None:
    plan = LoopImprovementPlan(
        goal_id="",
        summary="1 proposed improvement(s)",
        improvements=[
            LoopImprovement(
                target="loop-design",
                title="Fix missing-termination",
                detail="Add a stop condition.",
                source="loop-check",
                auto_applicable=True,
                evidence_refs=["P1"],
                why="The loop has no stop condition.",
            )
        ],
    )

    text = render_loop_improvement_plan(plan)

    assert "why: The loop has no stop condition." in text
    assert "refs: P1" in text
    assert "seen" not in text  # a linter finding has no note count


def test_design_fixes_get_the_linter_message_as_the_why(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    session = new_session(tmp_path, skills=[])
    run_script(
        session,
        ["objective Fixme", "add Plan", "accept The dashboard renders.", "save"],
        write=lambda _msg: None,
    )
    plan = plan_loop_improvements(tmp_path, None, design_dir=tmp_path)

    fixes = [imp for imp in plan.improvements if imp.auto_applicable]
    assert fixes and all(imp.why for imp in fixes)


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
