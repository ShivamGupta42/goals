import hashlib
from pathlib import Path

from goals.audit import build_audit_report
from goals.dashboard import render_dashboard
from goals.models import Event, EventType, Evidence, GoalSnapshot, Verification, WorktreeLease
from goals.runtime import append_event, create_goal, default_phases, verify_phase
from goals.storage import EventStore


def _snapshot(goal_id: str = "demo") -> GoalSnapshot:
    return GoalSnapshot(
        goal_id=goal_id,
        objective="Demo goal",
        topology=WorktreeLease(
            base_repo="/repo", base_branch="main", worktree_path="/wt", branch="goal/demo"
        ),
        phases=default_phases("Demo goal"),
        current_phase="P1",
    )


def test_event_append_adds_trace_and_phase_cause(tmp_path: Path) -> None:
    store = EventStore(tmp_path / "goal")
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.GOAL_CREATED,
            payload={"snapshot": _snapshot().model_dump()},
        )
    )
    store.append(
        Event(goal_id="demo", event_type=EventType.PHASE_STARTED, payload={"phase_id": "P1"})
    )
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.PHASE_EVIDENCE,
            payload={"phase_id": "P1", "evidence": Evidence().model_dump()},
        )
    )

    events = store.read_events()

    assert events[0].trace_id == "demo"
    assert events[0].actor == "goals-cli"
    assert events[1].caused_by == events[0].event_id
    assert events[2].caused_by == events[1].event_id


def test_phase_evidence_without_started_phase_falls_back_to_previous_event(
    tmp_path: Path,
) -> None:
    store = EventStore(tmp_path / "goal")
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.GOAL_CREATED,
            payload={"snapshot": _snapshot().model_dump()},
        )
    )
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.PHASE_EVIDENCE,
            payload={"phase_id": "P1", "evidence": Evidence().model_dump()},
        )
    )

    events = store.read_events()

    assert events[1].caused_by == events[0].event_id


def test_strict_audit_reports_dangling_cause(tmp_path: Path) -> None:
    goal_dir = tmp_path / "goal"
    store = EventStore(goal_dir)
    store.append(
        Event(
            goal_id="demo",
            event_type=EventType.GOAL_CREATED,
            payload={"snapshot": _snapshot().model_dump()},
        )
    )
    bad = Event(
        goal_id="demo",
        event_type=EventType.PHASE_STARTED,
        caused_by="missing-event",
        payload={"phase_id": "P1"},
    )
    with (goal_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(bad.model_dump_json() + "\n")

    report = build_audit_report(goal_dir, worktree=tmp_path, strict=True)

    assert not report.passed
    assert report.dangling_causes == [f"{bad.event_id} caused_by=missing-event"]


def test_phase_verify_records_output_and_artifact_hashes(tmp_path: Path) -> None:
    create_goal("Trust proof", tmp_path, workspace="in_place")
    proof = tmp_path / "proof.txt"
    proof.write_text("proof\n", encoding="utf-8")
    snapshot = append_event(
        tmp_path,
        Event(
            goal_id="trust-proof",
            event_type=EventType.PHASE_EVIDENCE,
            payload={
                "phase_id": "P1",
                "evidence": Evidence(
                    changed_files=["proof.txt"],
                    verifications=[
                        Verification(covers="proof exists", command="printf 'verified\\n'")
                    ],
                ).model_dump(),
            },
        ),
    )

    verify_phase(tmp_path, "P1")
    goal_dir = tmp_path / ".agent-workflow" / "goals" / snapshot.goal_id
    verified = EventStore(goal_dir).snapshot().phases[0].evidence

    assert verified is not None
    assert verified.verifications[0].exit_code == 0
    assert verified.verifications[0].output_sha256 == hashlib.sha256(b"verified\n").hexdigest()
    assert verified.artifacts[0].path == "proof.txt"
    assert verified.artifacts[0].sha256 == hashlib.sha256(b"proof\n").hexdigest()


def test_strict_audit_fails_when_hashed_artifact_changes(tmp_path: Path) -> None:
    create_goal("Trust proof", tmp_path, workspace="in_place")
    proof = tmp_path / "proof.txt"
    proof.write_text("proof\n", encoding="utf-8")
    snapshot = append_event(
        tmp_path,
        Event(
            goal_id="trust-proof",
            event_type=EventType.PHASE_EVIDENCE,
            payload={
                "phase_id": "P1",
                "evidence": Evidence(
                    changed_files=["proof.txt"],
                    verifications=[Verification(covers="proof exists", command="true")],
                ).model_dump(),
            },
        ),
    )
    verify_phase(tmp_path, "P1")
    proof.write_text("changed\n", encoding="utf-8")
    goal_dir = tmp_path / ".agent-workflow" / "goals" / snapshot.goal_id

    report = build_audit_report(goal_dir, worktree=tmp_path, strict=True)

    assert not report.passed
    assert len(report.artifact_mismatches) == 1
    mismatch = report.artifact_mismatches[0]
    assert mismatch.path == "proof.txt"
    assert mismatch.reason == "sha256 mismatch"
    assert mismatch.expected_sha256 == hashlib.sha256(b"proof\n").hexdigest()
    assert mismatch.actual_sha256 == hashlib.sha256(b"changed\n").hexdigest()


def test_dashboard_shows_lineage_diagnostic_when_chain_is_unavailable(tmp_path: Path) -> None:
    snapshot = _snapshot()
    snapshot.topology.worktree_path = str(tmp_path)
    output = tmp_path / "dashboard.html"
    event = Event(
        goal_id="demo",
        event_type=EventType.GOAL_CREATED,
        payload={"snapshot": snapshot.model_dump()},
    )

    render_dashboard(snapshot, output, events=[event])

    html = output.read_text(encoding="utf-8")
    assert "Lineage" in html
    assert "unavailable" in html
    assert "No events found for phase: P1" in html
