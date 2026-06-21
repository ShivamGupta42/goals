from __future__ import annotations

from pathlib import Path

from goals.checkpoints import build_current_checkpoint_brief
from goals.models import (
    CheckpointKind,
    CheckpointStatus,
    CurrentCheckpointBrief,
    Event,
    EventType,
    GoalSnapshot,
    Phase,
    PhaseCheckpoint,
    utc_now,
)
from goals.runtime import append_event, load_active_snapshot
from goals.storage import GoalsError


def current_checkpoint(cwd: Path) -> CurrentCheckpointBrief:
    return build_current_checkpoint_brief(load_active_snapshot(cwd))


def render_checkpoint_list(snapshot: GoalSnapshot) -> str:
    lines = ["# Phase Checkpoints", ""]
    found = False
    for phase in snapshot.phases:
        if not phase.checkpoints:
            continue
        found = True
        lines.append(f"## {phase.phase_id} - {phase.title}")
        for checkpoint in phase.checkpoints:
            required = "required" if checkpoint.required else "optional"
            user = " user" if checkpoint.needs_user else ""
            lines.append(
                f"- [{checkpoint.status}][{checkpoint.kind}][{required}{user}] "
                f"{checkpoint.checkpoint_id}: {checkpoint.title}"
            )
            if checkpoint.summary:
                lines.append(f"  Summary: {checkpoint.summary}")
            if checkpoint.evidence_refs:
                lines.append(f"  Evidence: {', '.join(checkpoint.evidence_refs)}")
    if not found:
        lines.append("- No checkpoints recorded.")
    return "\n".join(lines) + "\n"


def record_checkpoint(
    cwd: Path,
    phase_id: str,
    checkpoint_id: str,
    *,
    title: str = "",
    kind: CheckpointKind = CheckpointKind.CUSTOM,
    status: CheckpointStatus = CheckpointStatus.PASSED,
    required: bool = True,
    needs_user: bool = False,
    summary: str = "",
    evidence_refs: list[str] | None = None,
    decision_refs: list[str] | None = None,
    notes: str = "",
) -> PhaseCheckpoint:
    snapshot = load_active_snapshot(cwd)
    phase = _phase_or_error(snapshot, phase_id)
    existing = _checkpoint_or_none(phase, checkpoint_id)
    checkpoint = PhaseCheckpoint(
        checkpoint_id=checkpoint_id,
        kind=kind,
        title=title or (existing.title if existing else checkpoint_id),
        status=status,
        required=required,
        needs_user=needs_user or status == CheckpointStatus.NEEDS_USER,
        summary=summary or (existing.summary if existing else ""),
        evidence_refs=evidence_refs
        if evidence_refs is not None
        else (existing.evidence_refs if existing else []),
        decision_refs=decision_refs
        if decision_refs is not None
        else (existing.decision_refs if existing else []),
        created_at=existing.created_at if existing else utc_now(),
        updated_at=utc_now(),
        notes=notes or (existing.notes if existing else ""),
    )
    _append_checkpoint(cwd, snapshot.goal_id, phase_id, checkpoint)
    return checkpoint


def waive_checkpoint(cwd: Path, phase_id: str, checkpoint_id: str, reason: str) -> PhaseCheckpoint:
    snapshot = load_active_snapshot(cwd)
    phase = _phase_or_error(snapshot, phase_id)
    existing = _checkpoint_or_none(phase, checkpoint_id)
    if existing is None:
        raise GoalsError(f"Unknown checkpoint id for {phase_id}: {checkpoint_id}")
    checkpoint = existing.model_copy(
        update={
            "status": CheckpointStatus.WAIVED,
            "needs_user": False,
            "summary": reason,
            "updated_at": utc_now(),
            "notes": reason,
        }
    )
    _append_checkpoint(cwd, snapshot.goal_id, phase_id, checkpoint)
    return checkpoint


def _append_checkpoint(cwd: Path, goal_id: str, phase_id: str, checkpoint: PhaseCheckpoint) -> None:
    append_event(
        cwd,
        Event(
            goal_id=goal_id,
            event_type=EventType.PHASE_CHECKPOINT_RECORDED,
            payload={"phase_id": phase_id, "checkpoint": checkpoint.model_dump()},
        ),
    )


def _phase_or_error(snapshot: GoalSnapshot, phase_id: str) -> Phase:
    for phase in snapshot.phases:
        if phase.phase_id == phase_id:
            return phase
    valid = ", ".join(p.phase_id for p in snapshot.phases) or "none"
    raise GoalsError(f"Unknown phase id: {phase_id}. Valid phases: {valid}.")


def _checkpoint_or_none(phase: Phase, checkpoint_id: str) -> PhaseCheckpoint | None:
    for checkpoint in phase.checkpoints:
        if checkpoint.checkpoint_id == checkpoint_id:
            return checkpoint
    return None
