import subprocess
from pathlib import Path

from typer.testing import CliRunner

from goals.cli import app
from goals.memory import (
    _entry_key,
    append_memory_entry,
    apply_memory_sync,
    derive_memory_suggestions,
    latest_event_ref,
    load_memory,
    memory_path,
    plan_memory_sync,
    render_memory_sync_plan,
)
from goals.models import Event, EventType, GoalSnapshot, SelfEvolutionEntry, WorktreeLease
from goals.runtime import (
    active_goal_dir,
    append_event,
    create_goal,
    default_phases,
    load_active_snapshot,
)
from goals.storage import EventStore, GoalsError

runner = CliRunner()


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


# --- new notes point back to the event they came from ---------------------- #
def _events() -> list[Event]:
    def make(event_id: str, phase: str | None) -> Event:
        payload = {"phase_id": phase} if phase else {}
        return Event(
            event_id=event_id, goal_id="g", event_type=EventType.PHASE_EVIDENCE, payload=payload
        )

    return [make("e1", "P1"), make("e2", "P2"), make("e3", "P1"), make("e4", None)]


def test_latest_event_ref_is_the_newest_event_of_that_phase() -> None:
    assert latest_event_ref(_events(), "P1") == "event:e3"
    assert latest_event_ref(_events(), "P2") == "event:e2"


def test_latest_event_ref_is_none_when_the_phase_has_no_event() -> None:
    assert latest_event_ref(_events(), "P9") is None  # a phase that has no event, or a typo
    assert latest_event_ref(_events(), None) is None
    assert latest_event_ref([], "P1") is None


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repo(path: Path) -> None:
    _git(path, "init", "-b", "feature")
    _git(path, "config", "user.email", "t@example.com")
    _git(path, "config", "user.name", "T")
    (path / "README.md").write_text("# demo\n")
    _git(path, "add", "-A")
    _git(path, "commit", "-m", "init")


def _evidence_event(goal_id: str, phase: str) -> Event:
    return Event(
        goal_id=goal_id,
        event_type=EventType.PHASE_EVIDENCE,
        payload={"phase_id": phase, "evidence": {}},
    )


def test_memory_record_attaches_the_event_of_the_phase_it_names(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    create_goal("ship the thing", tmp_path, workspace="in_place")
    monkeypatch.chdir(tmp_path)
    goal_id = load_active_snapshot(tmp_path).goal_id
    for phase in ("P1", "P2", "P1", "P2"):  # the newest P1 event is not the newest event overall
        append_event(tmp_path, _evidence_event(goal_id, phase))
    events = EventStore(active_goal_dir(tmp_path)).read_events()
    newest_p1 = [e for e in events if e.payload.get("phase_id") == "P1"][-1]
    newest_p2 = [e for e in events if e.payload.get("phase_id") == "P2"][-1]
    assert newest_p1.event_id != newest_p2.event_id

    result = runner.invoke(
        app,
        ["memory", "record", "Proof set up late", "--area", "phase", "--phase", "P1",
         "--evidence", "my-own-ref"],
    )

    assert result.exit_code == 0, result.output
    entry = load_memory(tmp_path, load_active_snapshot(tmp_path)).entries[-1]
    assert [r for r in entry.evidence_refs if r.startswith("event:")] == [
        f"event:{newest_p1.event_id}"
    ]
    assert "my-own-ref" in entry.evidence_refs  # what the agent passed is kept


def test_memory_record_for_a_phase_with_no_event_adds_no_event_ref(
    tmp_path: Path, monkeypatch
) -> None:
    _repo(tmp_path)
    create_goal("ship the thing", tmp_path, workspace="in_place")
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["memory", "record", "Typo phase", "--phase", "P9"])

    assert result.exit_code == 0, result.output
    entry = load_memory(tmp_path, load_active_snapshot(tmp_path)).entries[-1]
    assert not [r for r in entry.evidence_refs if r.startswith("event:")]


def test_memory_record_without_a_goal_adds_no_event_ref(tmp_path: Path, monkeypatch) -> None:
    _repo(tmp_path)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, ["memory", "record", "A note with no goal", "--area", "docs"])

    assert result.exit_code == 0, result.output
    assert load_memory(tmp_path, None).entries[-1].evidence_refs == []


def test_event_refs_do_not_change_which_notes_count_as_duplicates() -> None:
    plain = SelfEvolutionEntry(kind="friction", area="phase", note="same", goal_id="g", phase_id="P1")
    with_ref = plain.model_copy(update={"evidence_refs": ["event:e3"]})
    assert _entry_key(plain) == _entry_key(with_ref)
