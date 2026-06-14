import json
from pathlib import Path

from goals.models import GoalSnapshot, WorktreeLease
from goals.portability import (
    build_native_goal_emission,
    build_portable_state,
    export_goal,
    render_context_block,
    render_goal_markdown,
    sync_context_files,
    _replace_block,
)
from goals.runtime import default_phases
from goals.models import UserMemoryEvent
from goals.user_memory import append_user_event


def snapshot_for(tmp_path: Path) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id="demo",
        objective="Ship onboarding cleanup",
        why="Reduce drop-off",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Ship onboarding cleanup"),
        current_phase="P1",
        definition_of_done=["Onboarding has no dead steps."],
    )


def test_build_portable_state_is_sanitized(tmp_path: Path) -> None:
    state = build_portable_state(snapshot_for(tmp_path))
    payload = json.dumps(state)
    # No local machine path leaks into the committable spec.
    assert str(tmp_path) not in payload
    assert state["spec_version"] == 1
    assert state["branch"] == "goal/demo"
    assert state["current_phase"] == "P1"
    assert state["phases"], "phases should be exported"
    assert all("acceptance_criteria" in phase for phase in state["phases"])


def test_portable_state_excludes_user_memory(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GOALS_HOME", str(tmp_path / "home"))
    append_user_event(
        UserMemoryEvent(
            kind="manual",
            area="communication",
            summary="Prefer unusually specific private wording.",
            source="manual",
            confidence=0.95,
        )
    )

    state = build_portable_state(snapshot_for(tmp_path))
    rendered = render_goal_markdown(snapshot_for(tmp_path))
    payload = json.dumps(state) + rendered

    assert "unusually specific private wording" not in payload
    assert "user memory" not in payload.lower()


def test_render_goal_markdown_marks_current_phase(tmp_path: Path) -> None:
    text = render_goal_markdown(snapshot_for(tmp_path))
    assert "# Goal: Ship onboarding cleanup" in text
    assert "→ P1" in text
    assert "## Definition of Done" in text
    assert "- [ ]" in text  # unmet acceptance criteria render as empty checkboxes


def test_export_goal_writes_committable_pair(monkeypatch, tmp_path: Path) -> None:
    snapshot = snapshot_for(tmp_path)
    monkeypatch.setattr("goals.portability.load_active_snapshot", lambda cwd: snapshot)
    result = export_goal(tmp_path)
    state_path = Path(result.state_path)
    markdown_path = Path(result.markdown_path)
    assert state_path.exists() and markdown_path.exists()
    assert state_path.parent.name == ".goals"
    parsed = json.loads(state_path.read_text())
    assert parsed["spec_version"] == 1
    assert result.phase_count == len(snapshot.phases)


def test_context_sync_creates_then_preserves(monkeypatch, tmp_path: Path) -> None:
    snapshot = snapshot_for(tmp_path)
    monkeypatch.setattr("goals.portability.load_active_snapshot", lambda cwd: snapshot)

    first = sync_context_files(tmp_path)
    assert set(first.created) == {"AGENTS.md", "CLAUDE.md"}
    agents = tmp_path / "AGENTS.md"
    assert "goals:context:start" in agents.read_text()
    assert "Ship onboarding cleanup" in agents.read_text()

    # Idempotent: a second identical sync changes nothing.
    second = sync_context_files(tmp_path)
    assert set(second.unchanged) == {"AGENTS.md", "CLAUDE.md"}

    # Human content outside the markers is preserved across updates.
    human = "# AGENTS\n\nHand-written project notes.\n\n"
    agents.write_text(human + render_context_block(snapshot) + "\n")
    object.__setattr__(snapshot, "objective", "Ship onboarding cleanup v2")
    third = sync_context_files(tmp_path, targets=("AGENTS.md",))
    assert third.updated == ["AGENTS.md"]
    updated = agents.read_text()
    assert "Hand-written project notes." in updated
    assert "Ship onboarding cleanup v2" in updated
    assert updated.count("goals:context:start") == 1


def test_replace_block_appends_when_no_markers() -> None:
    out = _replace_block("# Title\n\nbody\n", "<!-- goals:context:start -->X<!-- goals:context:end -->")
    assert "body" in out
    assert "goals:context:start" in out


def test_replace_block_collapses_duplicates() -> None:
    block = "<!-- goals:context:start -->\nNEW\n<!-- goals:context:end -->"
    old = "<!-- goals:context:start -->\nOLD\n<!-- goals:context:end -->"
    existing = f"# T\n\n{old}\n\nmiddle notes\n\n{old}\n"
    out = _replace_block(existing, block)
    assert out.count("goals:context:start") == 1
    assert "NEW" in out
    assert "OLD" not in out
    assert "middle notes" in out  # human content between duplicates is preserved


def test_emit_caps_claude_goal_length(tmp_path: Path) -> None:
    snapshot = snapshot_for(tmp_path)
    snapshot.phases[0].acceptance_criteria = [
        f"Criterion {i} with a fair amount of descriptive prose to inflate length"
        for i in range(200)
    ]
    snapshot.current_phase = snapshot.phases[0].phase_id
    emission = build_native_goal_emission(snapshot, "claude")
    assert len(emission.command) < 4000
    assert "`.goals/GOAL.md`" in emission.condition


def test_emit_native_goal_claude_and_codex(tmp_path: Path) -> None:
    snapshot = snapshot_for(tmp_path)
    claude = build_native_goal_emission(snapshot, "claude")
    assert claude.command.startswith("/goal ")
    assert "phase P1" in claude.condition
    assert "goals phase accept P1" in claude.condition
    assert claude.notes

    codex = build_native_goal_emission(snapshot, "codex")
    assert codex.adapter == "codex"
    # The codex paste-target is task text, NOT a shell command: it must not be
    # wrapped in `codex "..."`, which would let the backticks in the condition
    # run as shell command substitution (e.g. `goals phase accept P1`) on paste.
    assert not codex.command.startswith("codex ")
    assert not codex.command.strip().startswith('codex "')
    assert codex.command == codex.condition
