from __future__ import annotations

import json
import os
import time
import types
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator, Union, get_args, get_origin

from pydantic import BaseModel

from goals.models import (
    Assumption,
    Decision,
    Evidence,
    Event,
    EventType,
    GateResult,
    GoalArchitectureMap,
    GoalSnapshot,
    GoalStatus,
    JudgementRecord,
    PhaseCheckpoint,
    PhaseStatus,
    ProblemBreakdown,
    SourceClaim,
    SourceRecord,
)


class GoalsError(RuntimeError):
    """Base error for user-facing Goals failures."""


_KNOWN_EVENT_TYPES = {member.value for member in EventType}


def _is_retired_event(line: str) -> bool:
    """True if a line is a well-formed event for a since-removed feature.

    Earlier versions recorded events (e.g. ``asset_recorded``) whose event_type
    is no longer a known member. They have no replay handler, so skipping them
    lets an upgraded Goals still load goals started on a previous version
    instead of bricking the whole goal. Genuinely corrupt lines are not retired.
    """
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return False
    event_type = data.get("event_type")
    return isinstance(event_type, str) and event_type not in _KNOWN_EVENT_TYPES


def _drop_unknown_fields(payload: object, model: type) -> object:
    """Strip keys a model — and its declared nested models — no longer declares.

    Forward-compat load: lets an older binary read an event or snapshot a newer one
    wrote with fields this binary does not know, at the top level and inside nested
    models and lists of models. Non-model values pass through unchanged, so a genuine
    type mismatch still surfaces at ``model_validate`` rather than being masked.
    """
    if not isinstance(payload, dict):
        return payload
    fields = getattr(model, "model_fields", {})
    cleaned: dict = {}
    for key, value in payload.items():
        if key not in fields:
            continue
        cleaned[key] = _clean_nested(value, fields[key].annotation)
    return cleaned


def _clean_nested(value: object, annotation: object) -> object:
    """Recurse into a value when its field declares a model or list-of-models."""
    nested = _nested_model(annotation)
    if nested is None:
        return value
    kind, submodel = nested
    if kind == "single" and isinstance(value, dict):
        return _drop_unknown_fields(value, submodel)
    if kind == "list" and isinstance(value, list):
        return [
            _drop_unknown_fields(item, submodel) if isinstance(item, dict) else item
            for item in value
        ]
    return value


def _nested_model(annotation: object) -> tuple[str, type] | None:
    """Classify a field annotation for nested forward-compat stripping.

    Returns ``("single", Model)`` for ``Model`` / ``Optional[Model]``, ``("list", Model)``
    for ``list[Model]`` / ``Optional[list[Model]]``, else ``None``. Other shapes (dicts,
    unions of multiple models, scalars) are intentionally left untouched.
    """
    annotation = _unwrap_optional(annotation)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return ("single", annotation)
    if get_origin(annotation) is list:
        args = get_args(annotation)
        if len(args) == 1:
            item = _unwrap_optional(args[0])
            if isinstance(item, type) and issubclass(item, BaseModel):
                return ("list", item)
    return None


def _unwrap_optional(annotation: object) -> object:
    """Reduce ``X | None`` / ``Optional[X]`` to ``X`` (leave other unions alone)."""
    if get_origin(annotation) in (Union, types.UnionType):
        non_none = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(non_none) == 1:
            return non_none[0]
    return annotation


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
                if _is_retired_event(line):
                    continue
                raise GoalsError(
                    f"Invalid event at {self.events_path}:{line_number}: {exc}"
                ) from exc
        return events

    def append(self, event: Event) -> None:
        with lock_file(self.events_path):
            events = self.read_events()
            if any(existing.event_id == event.event_id for existing in events):
                return
            snapshot = derive_snapshot(events + [event])
            lines = [existing.model_dump_json() for existing in events]
            lines.append(event.model_dump_json())
            atomic_write_text(self.events_path, "\n".join(lines) + "\n")
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
    snapshot = GoalSnapshot.model_validate(
        _drop_unknown_fields(first.payload["snapshot"], GoalSnapshot)
    )
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
            evidence = Evidence.model_validate(payload["evidence"])
            # Recorded evidence declares *what* will be verified; it can never assert
            # that a check passed. Strip any agent-set execution result so the only
            # path to ran/passed is the engine running it (PHASE_VERIFIED).
            for verification in evidence.verifications:
                verification.ran = False
                verification.passed = False
                verification.output_excerpt = ""
                verification.ran_at = ""
            phase.evidence = evidence
            phase.status = PhaseStatus.NEEDS_REVIEW
            # New evidence invalidates any prior review: a PASS must reflect the
            # *current* evidence, or re-recording evidence after a pass would let
            # `accept` ride a stale review without re-verifying.
            phase.reviews.clear()
        elif event.event_type == EventType.PHASE_VERIFIED:
            phase = _phase(snapshot, payload["phase_id"])
            if phase.evidence is not None:
                executed = {
                    item["verification_id"]: item for item in payload.get("verifications", [])
                }
                for verification in phase.evidence.verifications:
                    result = executed.get(verification.verification_id)
                    if result is not None:
                        verification.ran = bool(result.get("ran"))
                        verification.passed = bool(result.get("passed"))
                        verification.output_excerpt = result.get("output_excerpt", "")
                        verification.ran_at = result.get("ran_at", "")
                # Re-running checks changes the proof, so any prior review is stale.
                phase.reviews.clear()
        elif event.event_type == EventType.PHASE_REVIEWED:
            phase = _phase(snapshot, payload["phase_id"])
            # Drop GateResult keys this binary no longer declares — at the top level and
            # inside nested models — so an older binary can replay an event a newer one
            # wrote with an added field (e.g. `findings`, or a new field inside a finding).
            # Matches the snapshot-level forward-compat stance above.
            phase.reviews.append(
                GateResult.model_validate(_drop_unknown_fields(payload["gate_result"], GateResult))
            )
        elif event.event_type == EventType.PHASE_CHECKPOINT_RECORDED:
            phase = _phase(snapshot, payload["phase_id"])
            checkpoint = PhaseCheckpoint.model_validate(payload["checkpoint"])
            _upsert_checkpoint(phase.checkpoints, checkpoint)
        elif event.event_type == EventType.PHASE_ACCEPTED:
            phase = _phase(snapshot, payload["phase_id"])
            phase.status = PhaseStatus.ACCEPTED
            snapshot.current_phase = _next_pending_phase_id(snapshot)
            if snapshot.current_phase is None:
                snapshot.status = GoalStatus.COMPLETE
        elif event.event_type == EventType.DECISION_REQUESTED:
            decision = Decision.model_validate(payload["decision"])
            snapshot.decisions.append(decision)
            if payload["decision"].get("priority") == "blocking":
                snapshot.status = GoalStatus.BLOCKED
        elif event.event_type == EventType.DECISION_RECORDED:
            snapshot.judgements.append(JudgementRecord.model_validate(payload["judgement"]))
        elif event.event_type == EventType.ASSUMPTION_RECORDED:
            assumption = Assumption.model_validate(payload["assumption"])
            _upsert_assumption(snapshot.assumptions, assumption)
        elif event.event_type == EventType.BREAKDOWN_RECORDED:
            breakdown = ProblemBreakdown.model_validate(payload["breakdown"])
            _upsert_breakdown(snapshot.breakdowns, breakdown)
        elif event.event_type == EventType.ARCHITECTURE_UPDATED:
            snapshot.architecture = GoalArchitectureMap.model_validate(payload["architecture"])
        elif event.event_type == EventType.SOURCE_RECORDED:
            source = SourceRecord.model_validate(payload["source"])
            if not any(existing.source_id == source.source_id for existing in snapshot.sources):
                snapshot.sources.append(source)
            for claim_payload in payload.get("claims", []):
                claim = SourceClaim.model_validate(claim_payload)
                if not any(existing.claim == claim.claim for existing in snapshot.source_claims):
                    snapshot.source_claims.append(claim)
        elif event.event_type == EventType.LEARNING_CAPTURED:
            snapshot.learnings.append(payload["learning"])
    return GoalSnapshot.model_validate(snapshot.model_dump())


def _phase(snapshot: GoalSnapshot, phase_id: str):
    for phase in snapshot.phases:
        if phase.phase_id == phase_id:
            return phase
    raise GoalsError(f"Unknown phase id: {phase_id}")


def _upsert_checkpoint(checkpoints: list[PhaseCheckpoint], checkpoint: PhaseCheckpoint) -> None:
    for index, existing in enumerate(checkpoints):
        if existing.checkpoint_id == checkpoint.checkpoint_id:
            checkpoints[index] = checkpoint
            return
    checkpoints.append(checkpoint)


def _upsert_assumption(assumptions: list[Assumption], assumption: Assumption) -> None:
    # Re-emitting an assumption (e.g. flipping status holding -> broken) replaces
    # the prior record rather than stacking a duplicate.
    for index, existing in enumerate(assumptions):
        if existing.assumption_id == assumption.assumption_id:
            assumptions[index] = assumption
            return
    assumptions.append(assumption)


def _upsert_breakdown(breakdowns: list[ProblemBreakdown], breakdown: ProblemBreakdown) -> None:
    for index, existing in enumerate(breakdowns):
        if existing.breakdown_id == breakdown.breakdown_id:
            breakdowns[index] = breakdown
            return
    breakdowns.append(breakdown)


def _next_pending_phase_id(snapshot: GoalSnapshot) -> str | None:
    for phase in snapshot.phases:
        if phase.status == PhaseStatus.PENDING:
            return phase.phase_id
    return None
