from pathlib import Path

import pytest

from goals.loop_builder import (
    LoopPhase,
    BuilderSession,
    LoopDesign,
    apply_command,
    build_portable_state,
    load_design,
    new_session,
    render_loop_html,
    run_script,
    save_design,
    to_portable_state,
    to_snapshot,
)
from goals.skill_discovery import DiscoveredSkill
from goals.storage import GoalsError


def _skills() -> list[DiscoveredSkill]:
    return [
        DiscoveredSkill(
            name="goals-decision-explainer",
            description="Explain a decision in plain language.",
            sources=["claude"],
            agents=["claude"],
            path="/c/goals-decision-explainer/SKILL.md",
        ),
        DiscoveredSkill(
            name="shared-skill",
            description="Available to both agents.",
            sources=["claude", "codex"],
            agents=["claude", "codex"],
            path="/c/shared-skill/SKILL.md",
        ),
        DiscoveredSkill(
            name="bundled-skill",
            description="Bundled with Goals but not installed.",
            sources=["bundled"],
            agents=[],
            path="/b/bundled-skill/SKILL.md",
        ),
    ]


def _session(tmp_path: Path) -> BuilderSession:
    return BuilderSession(design=LoopDesign(), out_dir=tmp_path, skills=_skills())


def _drive(session: BuilderSession, *commands: str) -> list[str]:
    out: list[str] = []
    run_script(session, list(commands), write=out.append)
    return out


def test_new_session_starts_empty(tmp_path: Path) -> None:
    session = new_session(tmp_path, skills=_skills())
    assert session.design.phases == []
    assert session.design.objective == ""


def test_build_a_full_loop_end_to_end(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _drive(
        session,
        "objective Build a thing",
        "why It matters",
        "dod All phases accepted",
        "add Plan :: turn objective into DoD",
        "accept The definition of done is visible.",
        "terminate Plan is approved by the user.",
        "attach shared-skill",
        "add Execute :: make the change",
        "accept Tests pass.",
    )
    design = session.design
    assert design.objective == "Build a thing"
    assert [p.phase_id for p in design.phases] == ["P1", "P2"]
    assert design.phases[0].termination_conditions == ["Plan is approved by the user."]
    assert design.phases[0].skills == ["shared-skill"]


def test_empty_loop_renders_and_projects(tmp_path: Path) -> None:
    design = LoopDesign(objective="Empty loop")
    html = render_loop_html(design, skills=_skills())
    assert "No phases yet." in html
    state = to_portable_state(design)
    assert state["phases"] == []
    assert state["objective"] == "Empty loop"


def test_attach_claude_only_skill_emits_codex_install_hint(tmp_path: Path) -> None:
    session = _session(tmp_path)
    out = _drive(
        session,
        "add Plan",
        "attach goals-decision-explainer",
    )
    combined = "\n".join(out)
    assert "goals-decision-explainer" in combined
    assert ".agents/skills" in combined  # the portability install suggestion


def test_attach_bundled_skill_emits_install_hint(tmp_path: Path) -> None:
    session = _session(tmp_path)
    out = _drive(session, "add Plan", "attach bundled-skill")
    combined = "\n".join(out)
    assert "bundled-skill" in combined
    assert "goals skills install --target both" in combined


def test_attach_shared_skill_has_no_install_hint(tmp_path: Path) -> None:
    session = _session(tmp_path)
    out = _drive(session, "add Plan", "attach shared-skill")
    assert ".codex/skills" not in "\n".join(out)


def test_attach_unknown_skill_warns_but_attaches(tmp_path: Path) -> None:
    session = _session(tmp_path)
    out = _drive(session, "add Plan", "attach not-a-real-skill")
    assert "Warning" in out[-1]
    assert session.design.phases[0].skills == ["not-a-real-skill"]


def test_reorder_moves_phases(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _drive(session, "add First", "add Second", "add Third")
    _drive(session, "move P3 up")
    assert [p.title for p in session.design.phases] == ["First", "Third", "Second"]
    _drive(session, "move P1 down")
    assert [p.title for p in session.design.phases] == ["Third", "First", "Second"]


def test_reorder_at_edge_is_a_no_op(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _drive(session, "add First", "add Second")
    out = _drive(session, "move P1 up")
    assert "edge" in out[-1]
    assert [p.title for p in session.design.phases] == ["First", "Second"]


def test_delete_phase_clears_selection(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _drive(session, "add First", "add Second")
    _drive(session, "delete P2")
    assert [p.phase_id for p in session.design.phases] == ["P1"]
    assert session.selected is None


def test_phase_ids_stay_stable_across_delete(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _drive(session, "add First", "add Second", "add Third")
    _drive(session, "delete P2")
    # Ids are stable references, not renumbered, so P1 and P3 survive.
    assert [p.phase_id for p in session.design.phases] == ["P1", "P3"]


def test_edit_commands_require_a_selected_phase(tmp_path: Path) -> None:
    session = _session(tmp_path)
    out = _drive(session, "accept something")
    assert "Select a phase first" in out[-1]


def test_portable_projection_equals_portability(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _drive(
        session,
        "objective Round trip",
        "add Plan",
        "accept DoD visible.",
        "terminate User approves.",
        "attach shared-skill",
    )
    design = session.design
    # The builder must not reimplement portability — its portable output is
    # exactly what portability.build_portable_state produces for the snapshot.
    # (last_updated is a wall-clock stamp set per snapshot build, so drop it.)
    left = to_portable_state(design)
    right = build_portable_state(to_snapshot(design))
    left.pop("last_updated")
    right.pop("last_updated")
    assert left == right


def test_termination_and_skills_survive_into_portable_spec(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _drive(
        session,
        "objective Survives",
        "add Plan",
        "terminate User approves the plan.",
        "attach shared-skill",
    )
    state = to_portable_state(session.design)
    phase = state["phases"][0]
    assert phase["acceptance_criteria"] == []
    assert phase["protocol"]["termination_conditions"] == ["User approves the plan."]
    assert phase["protocol"]["skills"] == ["shared-skill"]


def test_save_writes_all_four_artifacts_and_round_trips(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _drive(session, "objective Saved loop", "add Plan", "accept DoD visible.")
    result = save_design(session.design, tmp_path, skills=_skills())

    for path in (result.design_path, result.state_path, result.markdown_path, result.html_path):
        assert Path(path).is_file()

    reloaded = load_design(Path(result.design_path))
    assert reloaded == session.design  # JSON round-trip is lossless.


def test_exported_html_is_standalone_and_escapes(tmp_path: Path) -> None:
    design = LoopDesign(
        objective="<script>alert(1)</script>",
        phases=[],
    )
    html = render_loop_html(design, skills=_skills())
    assert html.startswith("<!DOCTYPE html>")
    assert "http://" not in html and "https://" not in html  # no remote assets
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_html_shows_attached_skill_availability(tmp_path: Path) -> None:
    session = _session(tmp_path)
    _drive(session, "add Plan", "attach goals-decision-explainer", "attach shared-skill")
    html = render_loop_html(session.design, skills=_skills())
    assert "goals-decision-explainer" in html
    assert "shared-skill" in html
    # The Claude-only skill surfaces the codex install hint in the HTML too.
    assert ".agents/skills" in html


def test_next_phase_id_never_collides_with_custom_ids(tmp_path: Path) -> None:
    # A custom/hand-edited id that has no trailing number must not reset the
    # counter back to P1 and collide with an existing P1.
    design = LoopDesign(phases=[LoopPhase(phase_id="P1", title="One")])
    session = BuilderSession(design=design, out_dir=tmp_path, skills=[])
    _drive(session, "add setup-phase", "add Another")
    ids = [p.phase_id for p in session.design.phases]
    assert len(ids) == len(set(ids))  # all unique


def test_to_snapshot_rejects_duplicate_phase_ids(tmp_path: Path) -> None:
    design = LoopDesign(
        phases=[LoopPhase(phase_id="P1", title="A"), LoopPhase(phase_id="P1", title="B")]
    )
    with pytest.raises(GoalsError, match="Duplicate phase ids"):
        to_snapshot(design)


def test_add_rejects_empty_title(tmp_path: Path) -> None:
    session = _session(tmp_path)
    out = _drive(session, "add :: just a goal")
    assert "needs a title" in out[-1]
    assert session.design.phases == []


def test_html_export_never_leaks_an_absolute_home_path(tmp_path: Path) -> None:
    # The export lands in committable, path-free .goals/loop.html, so the
    # Claude-only install hint must use ~/.agents/skills, not the expanded home.
    session = _session(tmp_path)
    _drive(session, "add Plan", "attach goals-decision-explainer")
    html = render_loop_html(session.design, skills=_skills())
    assert str(Path.home()) not in html
    assert "~/.agents/skills" in html


def test_unknown_command_is_reported(tmp_path: Path) -> None:
    session = _session(tmp_path)
    response = apply_command(session, "frobnicate everything")
    assert "Unknown command" in response.message


def test_comments_and_blank_lines_are_ignored(tmp_path: Path) -> None:
    session = _session(tmp_path)
    assert apply_command(session, "").message == ""
    assert apply_command(session, "# a comment").message == ""
