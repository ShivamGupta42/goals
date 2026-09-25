from __future__ import annotations

import os
from pathlib import Path

from goals.checkpoints import (
    COMPLETE_CHECKPOINT_STATUSES,
    USER_CHECKPOINT_KINDS,
    build_current_checkpoint_brief,
    checkpoint_is_asked,
    is_future_phase,
    is_user_checkpoint,
    replies_since_asked,
    user_message_by_id,
)
from goals.models import (
    CheckpointKind,
    DesiredProperty,
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


def property_state(snapshot: GoalSnapshot, wanted: DesiredProperty) -> str:
    """Where a desired property's proof stands, in plain words."""
    phase = next((p for p in snapshot.phases if p.phase_id == wanted.phase_id), None)
    if phase is None:
        return f"bound to {wanted.phase_id}, which this goal doesn't have"
    if wanted.proof == "auto":
        verifications = phase.evidence.verifications if phase.evidence is not None else []
        proven = any(
            v.covers.strip() == wanted.property_id and v.kind == "auto" and v.ran and v.passed
            for v in verifications
        )
        return (
            f"proven by an automated check in {phase.phase_id}"
            if proven
            else f"to be proven by an automated check in {phase.phase_id}"
        )
    check = next((c for c in phase.checkpoints if c.checkpoint_id == wanted.property_id), None)
    if check is None:
        return f"to be confirmed by you in {phase.phase_id}"
    if check.status in COMPLETE_CHECKPOINT_STATUSES:
        return checkpoint_provenance(snapshot, check) or f"closed in {phase.phase_id}"
    if checkpoint_is_asked(check):
        return "waiting on your answer"
    return f"you'll be asked in {phase.phase_id}, once there's something to try"


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
    asked_status_given = status is not None
    if status is None:
        status = existing.status if existing else CheckpointStatus.PASSED
    if required is None:
        required = existing.required if existing else True
    closing = status in COMPLETE_CHECKPOINT_STATUSES
    if (
        existing is not None
        and is_user_checkpoint(existing)
        and existing.required
        and not required
        and not closing
    ):
        raise GoalsError(
            f"{phase_id} checkpoint {checkpoint_id} is the user's to answer; it can't be made "
            "optional. Waive it on their reply instead (or --unverified, shown as not verified)."
        )
    _refuse_early_property_check(snapshot, phase_id, checkpoint_id, asking=needs_user is True or status == CheckpointStatus.NEEDS_USER, closing=closing)
    explicitly_asked = status == CheckpointStatus.NEEDS_USER and asked_status_given
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
    # Asking starts the reply window. An edit to an already-asked checkpoint keeps
    # it (so the user's answer still counts); an explicit --status needs_user
    # re-asks. The asking host session, when known, is the one whose replies count.
    now_asked = not closing and needs_user
    was_asked = existing is not None and checkpoint_is_asked(existing)
    if now_asked and (explicitly_asked or not was_asked):
        asked_at, asked_session = utc_now(), current_host_session()
    elif now_asked and existing is not None:
        asked_at, asked_session = existing.asked_at, existing.asked_session
    else:
        asked_at, asked_session = "", ""
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
        asked_at=asked_at,
        asked_session=asked_session,
    )
    _append_checkpoint(cwd, snapshot.goal_id, phase_id, checkpoint)
    if closing and cited and kind == CheckpointKind.UNDERSTANDING:
        _remember_confirmed_properties(snapshot, phase_id)
    return checkpoint


def _remember_confirmed_properties(snapshot: GoalSnapshot, phase_id: str) -> None:
    """Once the user confirms Discovery on their own reply, remember what they want.

    Each active desired property becomes an observation in the user's memory, so
    one that recurs across goals is offered for promotion (with their say-so) in
    the end-of-goal digest. Pain points are never remembered. Best-effort: a
    memory problem never undoes the confirmation.
    """
    if not snapshot.phases or phase_id != snapshot.phases[0].phase_id:
        return
    from goals.user_memory import infer_area, record_observation

    for wanted in snapshot.desired_properties:
        if wanted.status != "active":
            continue
        try:
            record_observation(
                goal_id=snapshot.goal_id,
                choice=wanted.statement,
                context="What good feels like (a desired property you confirmed)",
                area=infer_area(wanted.statement),
                phase_id=phase_id,
            )
        except GoalsError:
            return


#: Env vars through which a host tells the agent's shell its session id. The
#: user-prompt hook receives the same id, so a reply can be tied to the session
#: that asked. Unknown host → no stamp → any reply after asking counts.
HOST_SESSION_ENV_VARS = ("CLAUDE_CODE_SESSION_ID",)


def current_host_session() -> str:
    for name in HOST_SESSION_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


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
    _refuse_early_property_check(snapshot, phase_id, checkpoint_id, asking=False, closing=True)
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


def _refuse_early_property_check(
    snapshot: GoalSnapshot, phase_id: str, checkpoint_id: str, *, asking: bool, closing: bool
) -> None:
    """A desired property the user judges is asked in its own phase, not before.

    Asking during Discovery would let "yes, that's what I want" count as "yes, it
    feels right" before anything exists to try.
    """
    if not (asking or closing):
        return
    is_property_check = any(
        wanted.property_id == checkpoint_id and wanted.proof == "user" and wanted.status == "active"
        for wanted in snapshot.desired_properties
    )
    if is_property_check and is_future_phase(snapshot, phase_id):
        raise GoalsError(
            f"{checkpoint_id} is a desired property the user judges once there's something to "
            f"try; ask it when {phase_id} is the current phase (now {snapshot.current_phase})."
        )


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
