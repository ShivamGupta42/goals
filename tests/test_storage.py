from pathlib import Path

from goals.models import Event, EventType
from goals.runtime import default_phases
from goals.models import GoalSnapshot, WorktreeLease
from goals.storage import EventStore


def test_event_append_and_snapshot_derivation(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Demo goal",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/demo"
        ),
        phases=default_phases("Demo goal"),
        current_phase="P1",
    )
    store = EventStore(tmp_path / "goal")
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.GOAL_CREATED,
            payload={"snapshot": snapshot.model_dump()},
        )
    )
    store.append(
        Event(goal_id="demo", event_type=EventType.PHASE_STARTED, payload={"phase_id": "P1"})
    )
    derived = store.snapshot()
    assert derived.goal_id == "demo"
    assert derived.current_phase == "P1"
    assert derived.event_count == 2
    assert (tmp_path / "goal" / "goal.json").exists()
