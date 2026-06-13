from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator

from goals.models import Event, EventType, GoalSnapshot, PhaseStatus


class GoalsError(RuntimeError):
    """Base error for user-facing Goals failures."""


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


@contextmanager
def lock_file(path: Path, timeout_seconds: float = 5.0) -> Iterator[None]:
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() - start > timeout_seconds:
                raise GoalsError(f"Timed out waiting for lock: {lock_path}") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        lock_path.unlink(missing_ok=True)


class EventStore:
    def __init__(self, goal_dir: Path):
        self.goal_dir = goal_dir
        self.events_path = goal_dir / "events.jsonl"
        self.snapshot_path = goal_dir / "goal.json"

    def read_events(self) -> list[Event]:
        if not self.events_path.exists():
            return []
        events: list[Event] = []
        for line_number, line in enumerate(self.events_path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                events.append(Event.model_validate_json(line))
            except Exception as exc:  # noqa: BLE001
                raise GoalsError(
                    f"Invalid event at {self.events_path}:{line_number}: {exc}"
                ) from exc
        return events

    def append(self, event: Event) -> None:
        with lock_file(self.events_path):
            events = self.read_events()
            if any(existing.event_id == event.event_id for existing in events):
                return
            lines = [existing.model_dump_json() for existing in events]
            lines.append(event.model_dump_json())
            atomic_write_text(self.events_path, "\n".join(lines) + "\n")
            snapshot = derive_snapshot(events + [event])
            atomic_write_text(self.snapshot_path, snapshot.model_dump_json(indent=2) + "\n")

    def snapshot(self) -> GoalSnapshot:
        events = self.read_events()
        if not events:
            raise GoalsError("No events found for this goal.")
        return derive_snapshot(events)


def derive_snapshot(events: list[Event]) -> GoalSnapshot:
    if not events:
        raise GoalsError("Cannot derive a snapshot without events.")
    first = events[0]
    if first.event_type != EventType.GOAL_CREATED:
        raise GoalsError("First event must be goal_created.")
    snapshot = GoalSnapshot.model_validate(first.payload["snapshot"])
    snapshot.event_count = len(events)
    for event in events[1:]:
        snapshot.last_updated = event.timestamp
        payload = event.payload
        if event.event_type == EventType.PHASE_STARTED:
            phase = _phase(snapshot, payload["phase_id"])
            phase.status = PhaseStatus.IN_PROGRESS
            snapshot.current_phase = phase.phase_id
        elif event.event_type == EventType.PHASE_EVIDENCE:
            phase = _phase(snapshot, payload["phase_id"])
            phase.evidence = payload["evidence"]
            phase.status = PhaseStatus.NEEDS_REVIEW
        elif event.event_type == EventType.PHASE_REVIEWED:
            phase = _phase(snapshot, payload["phase_id"])
            phase.reviews.append(payload["gate_result"])
        elif event.event_type == EventType.PHASE_ACCEPTED:
            phase = _phase(snapshot, payload["phase_id"])
            phase.status = PhaseStatus.ACCEPTED
            snapshot.current_phase = _next_pending_phase_id(snapshot)
            if snapshot.current_phase is None:
                snapshot.status = "complete"
        elif event.event_type == EventType.DECISION_REQUESTED:
            snapshot.decisions.append(payload["decision"])
            if payload["decision"].get("priority") == "blocking":
                snapshot.status = "blocked"
        elif event.event_type == EventType.LEARNING_CAPTURED:
            snapshot.learnings.append(payload["learning"])
    return GoalSnapshot.model_validate(snapshot.model_dump())


def _phase(snapshot: GoalSnapshot, phase_id: str):
    for phase in snapshot.phases:
        if phase.phase_id == phase_id:
            return phase
    raise GoalsError(f"Unknown phase id: {phase_id}")


def _next_pending_phase_id(snapshot: GoalSnapshot) -> str | None:
    for phase in snapshot.phases:
        if phase.status == PhaseStatus.PENDING:
            return phase.phase_id
    return None
