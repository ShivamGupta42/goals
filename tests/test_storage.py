from pathlib import Path

from goals.models import Event, EventType, GoalArchitectureMap
from goals.runtime import default_phases
from goals.models import Evidence, GateResult, GateVerdict, GoalSnapshot, GoalStatus, WorktreeLease
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
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.PHASE_EVIDENCE,
            payload={
                "phase_id": "P1",
                "evidence": {
                    "checks_run": ["pytest"],
                    "acceptance_met": ["done"],
                    "confidence": 0.9,
                },
            },
        )
    )
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.PHASE_REVIEWED,
            payload={
                "phase_id": "P1",
                "gate_result": {
                    "gate_id": "phase-review",
                    "verdict": "pass",
                    "summary": "ok",
                },
            },
        )
    )
    store.append(
        Event(goal_id="demo", event_type=EventType.PHASE_ACCEPTED, payload={"phase_id": "P1"})
    )
    derived = store.snapshot()
    assert derived.goal_id == "demo"
    assert derived.current_phase == "P2"
    assert derived.event_count == 5
    assert isinstance(derived.phases[0].evidence, Evidence)
    assert isinstance(derived.phases[0].reviews[0], GateResult)
    assert derived.phases[0].reviews[0].verdict == GateVerdict.PASS
    assert derived.status == GoalStatus.ACTIVE
    assert (tmp_path / "goal" / "goal.json").exists()


def test_architecture_update_replays_into_snapshot(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Demo goal",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/demo"
        ),
        phases=default_phases("Demo goal"),
        current_phase="P1",
    )
    architecture = GoalArchitectureMap(
        title="Demo architecture",
        overview="One user-facing map.",
        nodes=[
            {
                "node_id": "ui",
                "label": "Dashboard",
                "plain_summary": "Shows the goal in plain language.",
                "status": "built",
            }
        ],
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
        Event(
            goal_id="demo",
            event_type=EventType.ARCHITECTURE_UPDATED,
            payload={"architecture": architecture.model_dump()},
        )
    )

    derived = store.snapshot()

    assert derived.architecture is not None
    assert derived.architecture.title == "Demo architecture"
    assert derived.architecture.nodes[0].label == "Dashboard"
