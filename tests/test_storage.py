from pathlib import Path

from goals.models import (
    CreativeVariant,
    CreativeVariantScore,
    Event,
    EventType,
    ExternalReview,
    GoalArchitectureMap,
    HandoffOwner,
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


def test_creative_variant_replays_into_snapshot(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Demo goal",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/demo"
        ),
        phases=default_phases("Demo goal"),
        current_phase="P1",
    )
    variant = CreativeVariant(
        variant_id="VAR-demo",
        title="Calm direction",
        summary="Plain, trust-building direction.",
        best_for="non-technical users",
        scores=[CreativeVariantScore(criterion="clarity", score=5)],
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
            event_type=EventType.CREATIVE_VARIANT_RECORDED,
            payload={"variant": variant.model_dump()},
        )
    )

    derived = store.snapshot()

    assert derived.creative_variants[0].variant_id == "VAR-demo"
    assert derived.creative_variants[0].scores[0].criterion == "clarity"


def test_external_review_replays_into_snapshot(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Demo goal",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/demo"
        ),
        phases=default_phases("Demo goal"),
        current_phase="P1",
    )
    review = ExternalReview(
        review_id="REV-demo",
        title="Security review",
        reviewer="Security lead",
        reviewer_type="security",
        risk_domain="security",
        status="passed",
        scope=["Prompt injection"],
        summary="Approved.",
        evidence_refs=["evidence:P2"],
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
            event_type=EventType.EXTERNAL_REVIEW_RECORDED,
            payload={"review": review.model_dump()},
        )
    )

    derived = store.snapshot()

    assert derived.external_reviews[0].review_id == "REV-demo"
    assert derived.external_reviews[0].status == "passed"


def test_handoff_owner_replays_into_snapshot(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Demo goal",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/demo"
        ),
        phases=default_phases("Demo goal"),
        current_phase="P1",
    )
    owner = HandoffOwner(
        owner_id="OWN-demo",
        label="Support lead",
        role="reviewer",
        responsibility="Review the rollout checklist.",
        owner_type="team",
        phase_ids=["P2"],
        escalation_path="Escalate to coordinator.",
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
            event_type=EventType.HANDOFF_OWNER_RECORDED,
            payload={"owner": owner.model_dump()},
        )
    )

    derived = store.snapshot()

    assert derived.handoff_owners[0].owner_id == "OWN-demo"
    assert derived.handoff_owners[0].responsibility == "Review the rollout checklist."
