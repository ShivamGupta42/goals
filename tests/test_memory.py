from pathlib import Path

from goals.memory import (
    append_memory_entry,
    apply_memory_sync,
    derive_memory_suggestions,
    load_memory,
    memory_path,
    plan_memory_sync,
    render_memory_sync_plan,
)
from goals.models import GoalSnapshot, SelfEvolutionEntry, WorktreeLease
from goals.runtime import default_phases
from goals.storage import GoalsError


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


def test_memory_sync_imports_sanitized_cross_project_suggestions(tmp_path: Path) -> None:
    source_root = tmp_path / "source-project"
    target_root = tmp_path / "target-project"
    source_root.mkdir()
    target_root.mkdir()
    source_snapshot = GoalSnapshot(
        goal_id="source-goal",
        objective="Improve source project",
        topology=WorktreeLease(
            base_repo=str(source_root),
            base_branch="main",
            worktree_path=str(source_root),
            branch="goal/source",
        ),
        phases=default_phases("Improve source project"),
        current_phase="P2",
    )
    target_snapshot = GoalSnapshot(
        goal_id="target-goal",
        objective="Improve target project",
        topology=WorktreeLease(
            base_repo=str(target_root),
            base_branch="main",
            worktree_path=str(target_root),
            branch="goal/target",
        ),
        phases=default_phases("Improve target project"),
        current_phase="P1",
    )
    append_memory_entry(
        source_root,
        SelfEvolutionEntry(
            kind="friction",
            area="skill",
            note="Private client Alpha setup command was missed.",
            severity="medium",
            goal_id="source-goal",
            phase_id="P2",
        ),
        source_snapshot,
    )
    append_memory_entry(
        source_root,
        SelfEvolutionEntry(
            kind="friction",
            area="skill",
            note="Private client Alpha setup command was missed again.",
            severity="medium",
            goal_id="source-goal-2",
            phase_id="P2",
        ),
        source_snapshot,
    )

    plan = plan_memory_sync(target_root, source_root, target_snapshot)
    rendered = render_memory_sync_plan(plan)

    assert plan.dry_run is True
    assert len(plan.candidates) == 1
    assert "Cross-Project Memory Sync" in rendered
    assert "Private client Alpha" not in rendered
    private_plan = plan_memory_sync(
        target_root,
        source_root,
        target_snapshot,
        include_private=True,
    )
    assert private_plan.source_label == "source-project"
    assert "Private client Alpha" in private_plan.candidates[0].plain_summary

    applied = apply_memory_sync(target_root, plan, target_snapshot)
    target_memory = load_memory(target_root, target_snapshot)
    target_suggestions = derive_memory_suggestions(target_memory)

    assert applied.dry_run is False
    assert applied.imported_count == 1
    assert "Private client Alpha" not in target_memory.entries[0].note
    assert target_suggestions[0].user_visible is True
    assert "cross-project-memory:external-project:skill" in target_suggestions[0].evidence_refs


def test_memory_sync_rejects_current_project_memory(tmp_path: Path) -> None:
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
        current_phase="P1",
    )
    append_memory_entry(
        tmp_path,
        SelfEvolutionEntry(
            kind="friction",
            area="phase",
            note="Repeated phase confusion.",
            severity="high",
            goal_id="demo",
            phase_id="P1",
        ),
        snapshot,
    )

    try:
        plan_memory_sync(tmp_path, memory_path(tmp_path, snapshot), snapshot)
    except GoalsError as exc:
        assert "current project memory" in str(exc)
    else:
        raise AssertionError("Expected current-project memory sync to fail.")
