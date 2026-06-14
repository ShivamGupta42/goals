from pathlib import Path

from goals.models import (
    CheckpointStatus,
    Event,
    EventType,
    GoalArchitectureMap,
    SourceClaim,
    SourceRecord,
)
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


def test_checkpoint_events_replay_and_upsert(tmp_path: Path) -> None:
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
        Event(
            goal_id="demo",
            event_type=EventType.PHASE_CHECKPOINT_RECORDED,
            payload={
                "phase_id": "P1",
                "checkpoint": {
                    "checkpoint_id": "CP-user",
                    "kind": "human_validation",
                    "title": "Confirm the plan",
                    "status": "needs_user",
                    "required": True,
                    "needs_user": True,
                    "summary": "The user needs to confirm the first step.",
                    "evidence_refs": ["brief:P1"],
                },
            },
        )
    )
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.PHASE_CHECKPOINT_RECORDED,
            payload={
                "phase_id": "P1",
                "checkpoint": {
                    "checkpoint_id": "CP-user",
                    "kind": "human_validation",
                    "title": "Confirm the plan",
                    "status": "passed",
                    "required": True,
                    "summary": "Confirmed.",
                    "evidence_refs": ["brief:P1", "reply:P1"],
                },
            },
        )
    )

    derived = store.snapshot()

    assert len(derived.phases[0].checkpoints) == 1
    assert derived.phases[0].checkpoints[0].status == CheckpointStatus.PASSED
    assert derived.phases[0].checkpoints[0].evidence_refs == ["brief:P1", "reply:P1"]


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


def test_source_record_replays_into_snapshot(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Demo goal",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/demo"
        ),
        phases=default_phases("Demo goal"),
        current_phase="P1",
    )
    source = SourceRecord(
        source_id="SRC-demo",
        title="Customer interview",
        source_type="interview",
        summary="Customer wants simpler progress reports.",
        credibility="high",
    )
    claim = SourceClaim(
        claim="Users need plain-language progress.",
        source_ids=["SRC-demo"],
        confidence=0.8,
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
            event_type=EventType.SOURCE_RECORDED,
            payload={"source": source.model_dump(), "claims": [claim.model_dump()]},
        )
    )

    derived = store.snapshot()

    assert derived.sources[0].title == "Customer interview"
    assert derived.source_claims[0].claim == "Users need plain-language progress."
