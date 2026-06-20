import json
from pathlib import Path

from goals.models import (
    CheckpointStatus,
    Event,
    EventType,
    GoalArchitectureMap,
    JudgementRecord,
    SourceClaim,
    SourceRecord,
)
from goals.runtime import default_phases
from goals.models import (
    Evidence,
    GateFactType,
    GateFinding,
    GateResult,
    GateVerdict,
    GoalSnapshot,
    GoalStatus,
    PhaseStatus,
    WorktreeLease,
)
from goals.storage import EventStore


def test_load_tolerates_legacy_state(tmp_path: Path) -> None:
    """A goal started on a previous version still loads after upgrade."""
    snapshot = GoalSnapshot(
        goal_id="legacy",
        objective="Legacy goal",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/legacy"
        ),
        phases=default_phases("Legacy goal"),
        current_phase="P1",
    )
    # A v1 GOAL_CREATED snapshot that still carried a since-removed field.
    legacy_snapshot = snapshot.model_dump()
    legacy_snapshot["assets"] = []
    created = Event(
        goal_id="legacy",
        event_type=EventType.GOAL_CREATED,
        payload={"snapshot": legacy_snapshot},
    )

    goal_dir = tmp_path / "goal"
    goal_dir.mkdir()
    retired = json.dumps(
        {
            "event_id": "evt-legacy-asset",
            "goal_id": "legacy",
            "event_type": "asset_recorded",  # removed in v2 — no replay handler
            "payload": {"asset": {"asset_id": "AST-1"}},
            "timestamp": "2026-01-01T00:00:00+00:00",
        }
    )
    (goal_dir / "events.jsonl").write_text(created.model_dump_json() + "\n" + retired + "\n")

    loaded = EventStore(goal_dir).snapshot()  # must not raise
    assert loaded.goal_id == "legacy"
    assert loaded.current_phase == "P1"
    # The retired event is skipped; only GOAL_CREATED is counted.
    assert loaded.event_count == 1


def test_genuinely_corrupt_event_still_raises(tmp_path: Path) -> None:
    from goals.storage import GoalsError

    snapshot = GoalSnapshot(
        goal_id="x",
        objective="x",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/x"
        ),
        phases=default_phases("x"),
        current_phase="P1",
    )
    created = Event(
        goal_id="x", event_type=EventType.GOAL_CREATED, payload={"snapshot": snapshot.model_dump()}
    )
    goal_dir = tmp_path / "goal"
    goal_dir.mkdir()
    (goal_dir / "events.jsonl").write_text(created.model_dump_json() + "\n{ not json \n")
    try:
        EventStore(goal_dir).read_events()
    except GoalsError:
        return
    raise AssertionError("corrupt event line should raise GoalsError")


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


def test_replay_tolerates_future_evidence_and_artifact_fields(tmp_path: Path) -> None:
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
            payload={"snapshot": snapshot.model_dump(), "future_event_payload": True},
        )
    )
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.PHASE_EVIDENCE,
            payload={
                "phase_id": "P1",
                "evidence": {
                    "checks_run": ["pytest"],
                    "verifications": [
                        {
                            "verification_id": "V-future",
                            "covers": "done",
                            "command": "true",
                            "future_verification_field": "ignored",
                        }
                    ],
                    "acceptance_met": ["done"],
                    "confidence": 0.9,
                    "future_evidence_field": "ignored",
                },
            },
        )
    )
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.PHASE_VERIFIED,
            payload={
                "phase_id": "P1",
                "verifications": [
                    {
                        "verification_id": "V-future",
                        "ran": True,
                        "passed": True,
                        "output_excerpt": "ok",
                        "future_result_field": "ignored",
                    }
                ],
                "artifacts": [
                    {
                        "path": "proof.txt",
                        "sha256": "abc",
                        "future_artifact_field": "ignored",
                    }
                ],
            },
        )
    )

    derived = store.snapshot()

    evidence = derived.phases[0].evidence
    assert evidence is not None
    assert evidence.verifications[0].verification_id == "V-future"
    assert evidence.verifications[0].passed is True
    assert evidence.artifacts[0].path == "proof.txt"
    assert evidence.artifacts[0].sha256 == "abc"


def test_reaccepting_earlier_phase_keeps_later_open_phase_current(tmp_path: Path) -> None:
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
    for phase_id in ("P1", "P2", "P3"):
        store.append(
            Event(
                goal_id="demo",
                event_type=EventType.PHASE_ACCEPTED,
                payload={"phase_id": phase_id},
            )
        )
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.PHASE_EVIDENCE,
            payload={"phase_id": "P4", "evidence": Evidence().model_dump()},
        )
    )
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.PHASE_EVIDENCE,
            payload={"phase_id": "P3", "evidence": Evidence().model_dump()},
        )
    )
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.PHASE_REVIEWED,
            payload={
                "phase_id": "P3",
                "gate_result": GateResult(
                    gate_id="phase-review", verdict=GateVerdict.PASS, summary="ok"
                ).model_dump(),
            },
        )
    )
    store.append(
        Event(goal_id="demo", event_type=EventType.PHASE_ACCEPTED, payload={"phase_id": "P3"})
    )

    derived = store.snapshot()

    assert derived.status == GoalStatus.ACTIVE
    assert derived.current_phase == "P4"
    assert derived.phases[2].status == PhaseStatus.ACCEPTED
    assert derived.phases[3].status == PhaseStatus.NEEDS_REVIEW


def test_reopening_completed_goal_marks_it_active(tmp_path: Path) -> None:
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
    for phase_id in ("P1", "P2", "P3", "P4"):
        store.append(
            Event(
                goal_id="demo",
                event_type=EventType.PHASE_ACCEPTED,
                payload={"phase_id": phase_id},
            )
        )
    store.append(
        Event(goal_id="demo", event_type=EventType.PHASE_STARTED, payload={"phase_id": "P2"})
    )

    derived = store.snapshot()

    assert derived.status == GoalStatus.ACTIVE
    assert derived.current_phase == "P2"
    assert derived.phases[1].status == PhaseStatus.IN_PROGRESS


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


def test_decision_record_replays_into_snapshot(tmp_path: Path) -> None:
    snapshot = GoalSnapshot(
        goal_id="demo",
        objective="Demo goal",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/demo"
        ),
        phases=default_phases("Demo goal"),
        current_phase="P1",
    )
    judgement = JudgementRecord(
        question="Where should sessions live?",
        choice="Redis",
        rationale="Fast and shared across nodes.",
        decided_by="user",
        reversible=True,
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
            event_type=EventType.DECISION_RECORDED,
            payload={"judgement": judgement.model_dump()},
        )
    )

    derived = store.snapshot()

    assert len(derived.judgements) == 1
    assert derived.judgements[0].question == "Where should sessions live?"
    assert derived.judgements[0].choice == "Redis"
    assert derived.judgements[0].decided_by == "user"
    assert derived.judgements[0].reversible is True


def test_gate_result_with_findings_round_trips() -> None:
    """The new typed findings survive dump -> validate (event persistence path)."""
    result = GateResult(
        gate_id="phase-review",
        verdict=GateVerdict.FAIL,
        summary="Evidence is not verified by execution.",
        p0=["Automated check V-1 ran and failed (covers done)."],
        findings=[
            GateFinding(
                fact_type=GateFactType.CHECK_FAILED,
                message="Automated check V-1 ran and failed (covers done).",
                ref="V-1",
            )
        ],
    )
    again = GateResult.model_validate(result.model_dump())
    assert again == result
    assert again.findings[0].fact_type is GateFactType.CHECK_FAILED
    assert again.findings[0].ref == "V-1"


def test_phase_reviewed_replay_tolerates_unknown_gate_result_field(tmp_path: Path) -> None:
    """An older binary must still replay an event a newer one wrote with extra keys."""
    from goals.models import Event, EventType
    from goals.runtime import default_phases

    snapshot = GoalSnapshot(
        goal_id="g",
        objective="Ship it",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/g"
        ),
        phases=default_phases("Ship it"),
        current_phase="P1",
    )
    created = Event(
        goal_id="g",
        event_type=EventType.GOAL_CREATED,
        payload={"snapshot": snapshot.model_dump()},
    )
    # A gate_result written by a newer Goals that declares a field this binary does not.
    gate_result = GateResult(
        gate_id="phase-review",
        verdict=GateVerdict.FAIL,
        summary="Evidence is not verified by execution.",
        p0=["No automated check has been executed and passed."],
    ).model_dump()
    gate_result["a_future_field"] = {"nested": 1}
    reviewed = Event(
        goal_id="g",
        event_type=EventType.PHASE_REVIEWED,
        payload={"phase_id": "P1", "gate_result": gate_result},
    )

    goal_dir = tmp_path / "goal"
    goal_dir.mkdir()
    (goal_dir / "events.jsonl").write_text(
        created.model_dump_json() + "\n" + reviewed.model_dump_json() + "\n"
    )

    loaded = EventStore(goal_dir).snapshot()  # must not raise on the unknown field
    p1 = next(phase for phase in loaded.phases if phase.phase_id == "P1")
    assert len(p1.reviews) == 1
    assert p1.reviews[0].verdict == GateVerdict.FAIL


def test_replay_strips_unknown_field_inside_a_finding(tmp_path: Path) -> None:
    """Nested forward-compat: a future sub-field on GateFinding must not brick replay."""
    from goals.models import Event, EventType
    from goals.runtime import default_phases

    snapshot = GoalSnapshot(
        goal_id="g",
        objective="Ship it",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/g"
        ),
        phases=default_phases("Ship it"),
        current_phase="P1",
    )
    created = Event(
        goal_id="g",
        event_type=EventType.GOAL_CREATED,
        payload={"snapshot": snapshot.model_dump()},
    )
    gate_result = GateResult(
        gate_id="phase-review",
        verdict=GateVerdict.FAIL,
        summary="Evidence is not verified by execution.",
        p0=["Automated check V-1 ran and failed (covers done)."],
        findings=[
            GateFinding(
                fact_type=GateFactType.CHECK_FAILED,
                message="Automated check V-1 ran and failed (covers done).",
                ref="V-1",
            )
        ],
    ).model_dump()
    # A newer binary added a field *inside* the finding (GateFinding is extra="forbid").
    gate_result["findings"][0]["a_future_subfield"] = {"nested": 1}
    reviewed = Event(
        goal_id="g",
        event_type=EventType.PHASE_REVIEWED,
        payload={"phase_id": "P1", "gate_result": gate_result},
    )

    goal_dir = tmp_path / "goal"
    goal_dir.mkdir()
    (goal_dir / "events.jsonl").write_text(
        created.model_dump_json() + "\n" + reviewed.model_dump_json() + "\n"
    )

    loaded = EventStore(goal_dir).snapshot()  # must not raise on the nested unknown field
    p1 = next(phase for phase in loaded.phases if phase.phase_id == "P1")
    assert p1.reviews[0].findings[0].fact_type == GateFactType.CHECK_FAILED
    assert p1.reviews[0].findings[0].ref == "V-1"


def test_snapshot_load_strips_unknown_nested_field(tmp_path: Path) -> None:
    """The same recursion protects the snapshot tree, not just gate results."""
    from goals.models import Event, EventType
    from goals.runtime import default_phases

    snapshot = GoalSnapshot(
        goal_id="g",
        objective="Ship it",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/g"
        ),
        phases=default_phases("Ship it"),
        current_phase="P1",
    )
    snap_dict = snapshot.model_dump()
    # A future field inside a list-of-models element (list[Phase] is extra="forbid")...
    snap_dict["phases"][0]["a_future_phase_field"] = "tomorrow"
    # ...and inside a single-model field (topology is a WorktreeLease, extra="forbid").
    snap_dict["topology"]["a_future_topology_field"] = "later"
    created = Event(
        goal_id="g", event_type=EventType.GOAL_CREATED, payload={"snapshot": snap_dict}
    )

    goal_dir = tmp_path / "goal"
    goal_dir.mkdir()
    (goal_dir / "events.jsonl").write_text(created.model_dump_json() + "\n")

    loaded = EventStore(goal_dir).snapshot()  # must not raise on the nested unknown fields
    assert loaded.phases[0].phase_id == "P1"
    assert loaded.topology.branch == "goal/g"


def test_nested_model_classifies_every_supported_and_unsupported_shape() -> None:
    """Lock the recursion contract: only single-model and list-of-model recurse;
    every other annotation shape is left untouched (fail-safe under-strip)."""
    import typing

    from goals.models import GateVerdict, Phase, WorktreeLease
    from goals.storage import _nested_model

    # Supported — these recurse.
    assert _nested_model(WorktreeLease) == ("single", WorktreeLease)
    assert _nested_model(typing.Optional[WorktreeLease]) == ("single", WorktreeLease)
    assert _nested_model(WorktreeLease | None) == ("single", WorktreeLease)
    assert _nested_model(list[Phase]) == ("list", Phase)
    assert _nested_model(typing.Optional[list[Phase]]) == ("list", Phase)

    # Unsupported — these must classify to None (never recurse into the wrong shape).
    assert _nested_model(str) is None
    assert _nested_model(int) is None
    assert _nested_model(list[str]) is None
    assert _nested_model(dict[str, WorktreeLease]) is None  # dict-of-model not recursed
    assert _nested_model(dict[str, str]) is None
    assert _nested_model(tuple[Phase, ...]) is None
    assert _nested_model(WorktreeLease | Phase) is None  # multi-arm union left alone
    assert _nested_model(typing.Literal["a", "b"]) is None
    assert _nested_model(GateVerdict) is None  # enum


def test_ref_bearing_finding_requires_a_ref() -> None:
    """The kernel's ref invariant is enforced at the type boundary."""
    import pytest
    from pydantic import ValidationError

    # ref-bearing fact without a ref -> rejected.
    for fact in (
        GateFactType.CHECK_FAILED,
        GateFactType.VERIFICATION_UNRUNNABLE,
        GateFactType.MISSING_FALSIFIER,
    ):
        with pytest.raises(ValidationError):
            GateFinding(fact_type=fact, message="m")

    # ref-bearing fact with a ref -> accepted; non-ref fact needs no ref.
    GateFinding(fact_type=GateFactType.CHECK_FAILED, message="m", ref="V-1")
    GateFinding(fact_type=GateFactType.NO_PASSING_CHECK, message="m")
