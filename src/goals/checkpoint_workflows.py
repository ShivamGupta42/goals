from __future__ import annotations

from pathlib import Path

from goals.checkpoints import (
    COMPLETE_CHECKPOINT_STATUSES,
    USER_CHECKPOINT_KINDS,
    build_current_checkpoint_brief,
    checkpoint_is_asked,
    is_user_checkpoint,
    replies_since_asked,
    user_message_by_id,
)
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
            provenance = checkpoint_provenance(snapshot, checkpoint)
            if provenance:
                lines.append(f"  {provenance}")
    if not found:
        lines.append("- No checkpoints recorded.")
    return "\n".join(lines) + "\n"


def checkpoint_provenance(snapshot: GoalSnapshot, checkpoint: PhaseCheckpoint) -> str:
    """Plain-language line saying how a closed user checkpoint was closed."""
    if checkpoint.user_message_id:
        message = user_message_by_id(snapshot, checkpoint.user_message_id)
        if message is None:
            return f"Cites reply {checkpoint.user_message_id}, not found on this machine."
        return f'Closed on the user\'s reply: "{_clip(message.text)}"'
    if checkpoint.unverified:
        return "Not verified: closed without a recorded reply from the user."
    return ""


def confirmation_lines(snapshot: GoalSnapshot) -> list[str]:
    """One line per closed user checkpoint, and the reply (if any) it was closed on."""
    lines: list[str] = []
    for phase in snapshot.phases:
        for checkpoint in phase.checkpoints:
            if checkpoint.status not in COMPLETE_CHECKPOINT_STATUSES:
                continue
            provenance = checkpoint_provenance(snapshot, checkpoint)
            if not provenance and not (
                checkpoint.user_owned or checkpoint.kind in USER_CHECKPOINT_KINDS
            ):
                continue
            label = checkpoint.title or checkpoint.checkpoint_id
            lines.append(
                f"{phase.phase_id} {label} ({checkpoint.status}): "
                + (provenance or "no reply on record.")
            )
    return lines


def record_checkpoint(
    cwd: Path,
    phase_id: str,
    checkpoint_id: str,
    *,
    title: str = "",
    kind: CheckpointKind | None = None,
    status: CheckpointStatus | None = None,
    required: bool | None = None,
    needs_user: bool | None = None,
    summary: str = "",
    evidence_refs: list[str] | None = None,
    decision_refs: list[str] | None = None,
    notes: str = "",
    user_message_id: str | None = None,
    unverified: bool = False,
) -> PhaseCheckpoint:
    """Record or update a checkpoint.

    ``None`` means "keep what's recorded" (or the default for a new checkpoint),
    so an update that omits an option can't quietly change it — e.g. close a
    checkpoint by defaulting ``status`` to passed, or drop ``needs_user``.
    """
    snapshot = load_active_snapshot(cwd)
    phase = _phase_or_error(snapshot, phase_id)
    existing = _checkpoint_or_none(phase, checkpoint_id)
    if kind is None:
        kind = existing.kind if existing else CheckpointKind.CUSTOM
    if status is None:
        status = existing.status if existing else CheckpointStatus.PASSED
    if required is None:
        required = existing.required if existing else True
    closing = status in COMPLETE_CHECKPOINT_STATUSES
    if closing:
        needs_user = False
    elif status == CheckpointStatus.NEEDS_USER:
        needs_user = True
    elif needs_user is None:
        needs_user = existing.needs_user if existing else False
    user_owned = (
        (existing is not None and is_user_checkpoint(existing))
        or kind in USER_CHECKPOINT_KINDS
        or needs_user
    )
    cited, unverified = _closing_provenance(
        snapshot,
        phase_id,
        checkpoint_id,
        existing,
        user_owned=user_owned,
        closing=closing,
        user_message_id=user_message_id,
        unverified=unverified,
    )
    checkpoint = PhaseCheckpoint(
        checkpoint_id=checkpoint_id,
        kind=kind,
        title=title or (existing.title if existing else checkpoint_id),
        status=status,
        required=required,
        needs_user=needs_user,
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
        user_message_id=cited,
        unverified=unverified,
        user_owned=user_owned,
    )
    _append_checkpoint(cwd, snapshot.goal_id, phase_id, checkpoint)
    return checkpoint


def waive_checkpoint(
    cwd: Path,
    phase_id: str,
    checkpoint_id: str,
    reason: str,
    *,
    user_message_id: str | None = None,
    unverified: bool = False,
) -> PhaseCheckpoint:
    snapshot = load_active_snapshot(cwd)
    phase = _phase_or_error(snapshot, phase_id)
    existing = _checkpoint_or_none(phase, checkpoint_id)
    if existing is None:
        raise GoalsError(f"Unknown checkpoint id for {phase_id}: {checkpoint_id}")
    user_owned = is_user_checkpoint(existing)
    cited, unverified = _closing_provenance(
        snapshot,
        phase_id,
        checkpoint_id,
        existing,
        user_owned=user_owned,
        closing=True,
        user_message_id=user_message_id,
        unverified=unverified,
    )
    checkpoint = existing.model_copy(
        update={
            "status": CheckpointStatus.WAIVED,
            "needs_user": False,
            "summary": reason,
            "updated_at": utc_now(),
            "notes": reason,
            "user_message_id": cited,
            "unverified": unverified,
            "user_owned": user_owned,
        }
    )
    _append_checkpoint(cwd, snapshot.goal_id, phase_id, checkpoint)
    return checkpoint


def _closing_provenance(
    snapshot: GoalSnapshot,
    phase_id: str,
    checkpoint_id: str,
    existing: PhaseCheckpoint | None,
    *,
    user_owned: bool,
    closing: bool,
    user_message_id: str | None,
    unverified: bool,
) -> tuple[str, bool]:
    """Decide how a checkpoint may be closed; return (cited message id, unverified).

    A user-owned checkpoint can only be passed or waived with a reply the host
    recorded after it was asked (and not already used to close another
    checkpoint) — or an explicit ``unverified`` claim, shown as not verified.
    A checkpoint that was already a closed user checkpoint keeps its provenance;
    relabelling a closed agent checkpoint as a user one counts as a new closing.
    """
    if not closing or not user_owned:
        return "", False
    if (
        existing is not None
        and existing.status in COMPLETE_CHECKPOINT_STATUSES
        and is_user_checkpoint(existing)
    ):
        return existing.user_message_id, existing.unverified
    replies = replies_since_asked(snapshot, existing)
    if user_message_id:
        if not any(m.message_id == user_message_id for m in replies):
            raise GoalsError(
                f"{user_message_id} isn't an unused reply recorded after {phase_id} checkpoint "
                f"{checkpoint_id} was put to the user."
            )
        return user_message_id, False
    if replies:
        return replies[-1].message_id, False
    if unverified:
        return "", True
    if existing is None or not checkpoint_is_asked(existing):
        raise GoalsError(
            f"{phase_id} checkpoint {checkpoint_id} is the user's to answer and hasn't been "
            "put to them yet. Record it with --status needs_user, ask them, and close it after "
            "they reply — or pass --unverified on a host without the Goals hook (it will show "
            "as not verified)."
        )
    raise GoalsError(
        f"{phase_id} checkpoint {checkpoint_id} waits on the user, and no reply from them has "
        "been recorded since it was asked. Ask them and wait for their answer — Goals records "
        "it when they reply. On a host without the Goals hook, pass --unverified (it will show "
        "as not verified)."
    )


def _clip(text: str, limit: int = 160) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


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
