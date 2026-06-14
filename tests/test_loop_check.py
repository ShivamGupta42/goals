from goals.loop_builder import LoopDesign, LoopPhase
from goals.loop_check import apply_fixes, check_loop
from goals.skill_discovery import DiscoveredSkill


def _skills() -> list[DiscoveredSkill]:
    return [
        DiscoveredSkill(
            name="known-skill",
            description="A real skill.",
            sources=["claude"],
            agents=["claude"],
            path="/c/known-skill/SKILL.md",
        )
    ]


def _codes(design: LoopDesign, **kw) -> set[str]:
    return {f.code for f in check_loop(design, **kw).findings}


def _healthy() -> LoopDesign:
    return LoopDesign(
        objective="Healthy loop",
        definition_of_done=["All phases accepted."],
        phases=[
            LoopPhase(
                phase_id="P1",
                title="Plan",
                goal="Turn the objective into a definition of done.",
                acceptance_criteria=["The definition of done is visible and tests pass."],
                termination_conditions=["The user approves the plan."],
                skills=["known-skill"],
            ),
            LoopPhase(
                phase_id="P2",
                title="Execute",
                goal="Make the change.",
                acceptance_criteria=["The new test passes and evidence is recorded."],
            ),
        ],
    )


def test_healthy_loop_passes_clean() -> None:
    report = check_loop(_healthy(), skills=_skills())
    assert report.passed
    assert report.findings == []


# --- one failing fixture per defect class ---------------------------------- #
def test_detects_no_phases() -> None:
    assert "no-phases" in _codes(LoopDesign(objective="empty"), skills=_skills())


def test_detects_no_termination() -> None:
    design = LoopDesign(
        phases=[LoopPhase(phase_id="P1", title="P", acceptance_criteria=["A test passes."])]
    )
    assert "no-termination" in _codes(design, skills=_skills())


def test_detects_no_acceptance_anywhere() -> None:
    design = LoopDesign(
        phases=[LoopPhase(phase_id="P1", title="P", termination_conditions=["User approves."])]
    )
    assert "no-acceptance" in _codes(design, skills=_skills())


def test_detects_vague_acceptance() -> None:
    design = LoopDesign(
        phases=[
            LoopPhase(
                phase_id="P1",
                title="P",
                acceptance_criteria=["It works properly"],
                termination_conditions=["Done."],
            )
        ]
    )
    assert "vague-acceptance" in _codes(design, skills=_skills())


def test_detects_duplicate_phase_id() -> None:
    design = LoopDesign(
        phases=[
            LoopPhase(phase_id="P1", title="A", acceptance_criteria=["A test passes."]),
            LoopPhase(phase_id="P1", title="B", termination_conditions=["Done."]),
        ]
    )
    assert "duplicate-phase-id" in _codes(design, skills=_skills())


def test_detects_duplicate_phase_content() -> None:
    design = LoopDesign(
        phases=[
            LoopPhase(
                phase_id="P1",
                title="Plan",
                goal="same",
                acceptance_criteria=["A test passes."],
                termination_conditions=["Done."],
            ),
            LoopPhase(phase_id="P2", title="Plan", goal="same", acceptance_criteria=["Renders."]),
        ]
    )
    assert "duplicate-phase" in _codes(design, skills=_skills())


def test_detects_empty_phase() -> None:
    design = LoopDesign(
        phases=[
            LoopPhase(
                phase_id="P1",
                title="Real",
                acceptance_criteria=["A test passes."],
                termination_conditions=["Done."],
            ),
            LoopPhase(phase_id="P2", title="Hollow"),
        ]
    )
    assert "empty-phase" in _codes(design, skills=_skills())


def test_detects_unknown_skill() -> None:
    design = LoopDesign(
        phases=[
            LoopPhase(
                phase_id="P1",
                title="P",
                acceptance_criteria=["A test passes."],
                termination_conditions=["Done."],
                skills=["ghost-skill"],
            )
        ]
    )
    assert "unknown-skill" in _codes(design, skills=_skills())


def test_detects_missing_evidence_requirement() -> None:
    design = LoopDesign(
        phases=[
            LoopPhase(
                phase_id="P1",
                title="P",
                acceptance_criteria=["The dashboard renders the loop."],
                termination_conditions=["Done."],
            )
        ]
    )
    # "renders" is concrete (not vague) but mentions no evidence/test/check.
    codes = _codes(design, skills=_skills())
    assert "no-evidence-requirement" in codes
    assert "vague-acceptance" not in codes


# --- auto-fix -------------------------------------------------------------- #
def test_fix_adds_termination_and_evidence() -> None:
    design = LoopDesign(
        phases=[LoopPhase(phase_id="P1", title="P", acceptance_criteria=["The dashboard renders."])]
    )
    fixed, changes = apply_fixes(design, skills=_skills())
    assert changes
    report = check_loop(fixed, skills=_skills())
    assert "no-termination" not in {f.code for f in report.findings}
    assert "no-evidence-requirement" not in {f.code for f in report.findings}


def test_fix_resolves_duplicate_ids() -> None:
    design = LoopDesign(
        phases=[
            LoopPhase(
                phase_id="P1",
                title="A",
                acceptance_criteria=["A test passes."],
                termination_conditions=["Done."],
            ),
            LoopPhase(phase_id="P1", title="B", acceptance_criteria=["A test passes."]),
        ]
    )
    fixed, changes = apply_fixes(design, skills=_skills())
    ids = [p.phase_id for p in fixed.phases]
    assert len(ids) == len(set(ids))
    assert any("Reassigned" in change for change in changes)


def test_fix_is_idempotent() -> None:
    design = LoopDesign(
        phases=[LoopPhase(phase_id="P1", title="P", acceptance_criteria=["The dashboard renders."])]
    )
    fixed_once, _ = apply_fixes(design, skills=_skills())
    fixed_twice, changes = apply_fixes(fixed_once, skills=_skills())
    assert changes == []
    assert fixed_twice == fixed_once


def test_fix_is_a_no_op_on_a_healthy_loop() -> None:
    healthy = _healthy()
    fixed, changes = apply_fixes(healthy, skills=_skills())
    assert changes == []
    assert fixed == healthy
