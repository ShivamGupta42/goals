from pathlib import Path

from goals.memory import append_memory_entry, derive_memory_suggestions, load_memory, memory_path
from goals.models import GoalSnapshot, SelfEvolutionEntry, WorktreeLease
from goals.runtime import default_phases


def test_memory_records_repeated_friction_as_visible_suggestion(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Improve goal flow",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Improve goal flow"),
        current_phase="P2",
    )

    append_memory_entry(
        tmp_path,
        SelfEvolutionEntry(
            kind="friction",
            area="skill",
            note="Agent missed the same setup command.",
            severity="medium",
            goal_id="demo",
            phase_id="P2",
        ),
        snapshot,
    )
    append_memory_entry(
        tmp_path,
        SelfEvolutionEntry(
            kind="friction",
            area="skill",
            note="Agent missed the same setup command again.",
            severity="medium",
            goal_id="demo-2",
            phase_id="P2",
        ),
        snapshot,
    )

    memory = load_memory(tmp_path, snapshot)
    suggestions = derive_memory_suggestions(memory)

    assert memory_path(tmp_path, snapshot).exists()
    assert suggestions[0].area == "skill"
    assert suggestions[0].user_visible is True
    assert "Update an existing skill" in suggestions[0].recommended_change


def test_high_severity_gap_is_actionable_without_repetition(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Improve safety",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Improve safety"),
        current_phase="P4",
    )
    append_memory_entry(
        tmp_path,
        SelfEvolutionEntry(
            kind="gap",
            area="safety",
            note="Safety scanner missed generated state.",
            severity="high",
            goal_id="demo",
            phase_id="P4",
        ),
        snapshot,
    )

    suggestion = derive_memory_suggestions(load_memory(tmp_path, snapshot))[0]

    assert suggestion.severity == "high"
    assert suggestion.user_visible is True
    assert "missing capability" in suggestion.recommended_change
