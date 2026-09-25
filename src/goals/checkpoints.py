from __future__ import annotations

from goals.models import (
    CheckpointKind,
    CheckpointStatus,
    CurrentCheckpointBrief,
    GoalSnapshot,
    Phase,
    PhaseCheckpoint,
    PhaseStatus,
    UserMessage,
)

COMPLETE_CHECKPOINT_STATUSES = {CheckpointStatus.PASSED, CheckpointStatus.WAIVED}
# Kinds whose whole point is the user's answer: closing one needs their reply.
USER_CHECKPOINT_KINDS = {
    CheckpointKind.UNDERSTANDING,
    CheckpointKind.HUMAN_VALIDATION,
    CheckpointKind.APPROVAL,
}


def checkpoint_blocks_phase(checkpoint: PhaseCheckpoint) -> bool:
    if not checkpoint.required:
        return False
    if checkpoint.status in COMPLETE_CHECKPOINT_STATUSES:
        return False
    return True


def checkpoint_waits_on_user(checkpoint: PhaseCheckpoint) -> bool:
    if not checkpoint_blocks_phase(checkpoint):
        return False
    return checkpoint.needs_user or checkpoint.status == CheckpointStatus.NEEDS_USER


def is_user_checkpoint(checkpoint: PhaseCheckpoint) -> bool:
    """A checkpoint only the user can close: owned by them, a user kind, or asked."""
    return (
        checkpoint.user_owned
        or checkpoint.kind in USER_CHECKPOINT_KINDS
        or checkpoint_is_asked(checkpoint)
    )


def checkpoint_is_asked(checkpoint: PhaseCheckpoint) -> bool:
    """Open and put to the user — whether or not it is required."""
    if checkpoint.status in COMPLETE_CHECKPOINT_STATUSES:
        return False
    return checkpoint.needs_user or checkpoint.status == CheckpointStatus.NEEDS_USER


def replies_since_asked(
    snapshot: GoalSnapshot, checkpoint: PhaseCheckpoint | None
) -> list[UserMessage]:
    """User messages recorded after this checkpoint was last put to the user.

    A checkpoint counts as asked only while it is open and put to the user;
    ``asked_at`` is the moment it was (re)asked (``updated_at`` for checkpoints
    recorded before that field). If the asking host session is known, only its
    replies count. A reply already cited by another checkpoint doesn't count:
    one answer closes one question.
    """
    if checkpoint is None or not checkpoint_is_asked(checkpoint):
        return []
    asked_at = checkpoint.asked_at or checkpoint.updated_at
    cited = {
        other.user_message_id
        for phase in snapshot.phases
        for other in phase.checkpoints
        if other.user_message_id and other is not checkpoint
    }
    return [
        m
        for m in snapshot.user_messages
        if m.recorded_at > asked_at
        and m.message_id not in cited
        and (not checkpoint.asked_session or m.session_id == checkpoint.asked_session)
    ]


def user_message_by_id(snapshot: GoalSnapshot, message_id: str) -> UserMessage | None:
    for message in snapshot.user_messages:
        if message.message_id == message_id:
            return message
    return None


def phase_checkpoint_blockers(phase: Phase) -> list[str]:
    blockers: list[str] = []
    for checkpoint in phase.checkpoints:
        if not checkpoint_blocks_phase(checkpoint):
            continue
        label = checkpoint.title or checkpoint.checkpoint_id
        if checkpoint_waits_on_user(checkpoint):
            blockers.append(f"Required checkpoint needs the user: {label}.")
        elif checkpoint.status == CheckpointStatus.BLOCKED:
            blockers.append(f"Required checkpoint is blocked: {label}.")
        else:
            blockers.append(f"Required checkpoint is not complete: {label}.")
    return blockers


def build_current_checkpoint_brief(snapshot: GoalSnapshot) -> CurrentCheckpointBrief:
    phase = _current_phase(snapshot)
    if phase is None:
        return CurrentCheckpointBrief(
            goal_id=snapshot.goal_id,
            phase_id="none",
            phase_title="No active phase",
            status="complete" if str(snapshot.status) == "complete" else str(snapshot.status),
            waiting_on="no one" if str(snapshot.status) == "complete" else "agent",
            why_it_matters="There is no active phase to validate.",
            what_changed="No current phase is selected.",
            proof=["All phases are accepted."] if str(snapshot.status) == "complete" else [],
            unresolved=[],
            next_safe_step="No action is needed."
            if str(snapshot.status) == "complete"
            else "Select or repair the current phase.",
        )

    checkpoint = _active_checkpoint(phase)
    blockers = phase_checkpoint_blockers(phase)
    waiting_on = _waiting_on(phase, blockers)
    proof = _proof_for(phase, checkpoint)
    unresolved = blockers or _phase_unresolved(phase)
    return CurrentCheckpointBrief(
        goal_id=snapshot.goal_id,
        phase_id=phase.phase_id,
        phase_title=phase.title,
        checkpoint_id=checkpoint.checkpoint_id if checkpoint else "",
        checkpoint_title=checkpoint.title if checkpoint else "Phase evidence and review",
        status=str(checkpoint.status if checkpoint else phase.status),
        waiting_on=waiting_on,
        why_it_matters=_why_it_matters(phase, checkpoint),
        what_changed=_what_changed(phase, checkpoint),
        proof=proof,
        unresolved=unresolved,
        next_safe_step=_next_safe_step(waiting_on, phase, checkpoint, unresolved),
        evidence_refs=checkpoint.evidence_refs if checkpoint else [],
        decision_refs=checkpoint.decision_refs if checkpoint else [],
    )


def render_current_checkpoint_brief(brief: CurrentCheckpointBrief) -> str:
    lines = [
        "## Current Checkpoint",
        "",
        f"Step: {brief.phase_id} - {brief.phase_title}",
        f"Checkpoint: {brief.checkpoint_title or 'Phase evidence and review'}",
        f"Status: {brief.status}",
        f"Waiting on: {brief.waiting_on}",
        "",
        f"Why it matters: {brief.why_it_matters}",
        f"What changed: {brief.what_changed}",
        "",
        "Proof:",
        _bullets(brief.proof or ["No proof recorded yet."]),
        "",
        "Unresolved:",
        _bullets(brief.unresolved or ["Nothing blocking this checkpoint."]),
        "",
        f"Next safe step: {brief.next_safe_step}",
    ]
    return "\n".join(lines)


def _current_phase(snapshot: GoalSnapshot) -> Phase | None:
    if snapshot.current_phase:
        for phase in snapshot.phases:
            if phase.phase_id == snapshot.current_phase:
                return phase
    for phase in snapshot.phases:
        if phase.status != PhaseStatus.ACCEPTED:
            return phase
    return snapshot.phases[-1] if snapshot.phases else None


def _active_checkpoint(phase: Phase) -> PhaseCheckpoint | None:
    for checkpoint in phase.checkpoints:
        if checkpoint_blocks_phase(checkpoint):
            return checkpoint
    for checkpoint in phase.checkpoints:
        if checkpoint.status not in COMPLETE_CHECKPOINT_STATUSES:
            return checkpoint
    return phase.checkpoints[-1] if phase.checkpoints else None


def _waiting_on(phase: Phase, blockers: list[str]) -> str:
    if any(checkpoint_waits_on_user(checkpoint) for checkpoint in phase.checkpoints):
        return "you"
    if blockers or phase.status != PhaseStatus.ACCEPTED:
        return "agent"
    return "no one"


def _proof_for(phase: Phase, checkpoint: PhaseCheckpoint | None) -> list[str]:
    proof: list[str] = []
    if checkpoint:
        proof.extend(checkpoint.evidence_refs)
        if checkpoint.summary and checkpoint.status in COMPLETE_CHECKPOINT_STATUSES:
            proof.append(checkpoint.summary)
    if phase.evidence is not None:
        proof.extend(phase.evidence.checks_run)
        proof.extend(phase.evidence.acceptance_met)
        if phase.evidence.notes:
            proof.append(phase.evidence.notes)
    return _dedupe(proof)


def _phase_unresolved(phase: Phase) -> list[str]:
    if phase.evidence is None:
        return ["Phase evidence has not been recorded yet."]
    unresolved: list[str] = []
    unresolved.extend(phase.evidence.acceptance_not_met)
    unresolved.extend(phase.evidence.ambiguous)
    if phase.evidence.confidence < 0.7:
        unresolved.append("Evidence confidence is below 0.7.")
    if not phase.evidence.checks_run:
        unresolved.append("No checks or tests were recorded.")
    return _dedupe(unresolved)


def _why_it_matters(phase: Phase, checkpoint: PhaseCheckpoint | None) -> str:
    if checkpoint:
        return (
            checkpoint.summary
            or "This checkpoint decides whether the current step has enough proof to continue."
        )
    if phase.status == PhaseStatus.ACCEPTED:
        return "This step has been accepted."
    return "The agent needs proof for this step before it can safely continue."


def _what_changed(phase: Phase, checkpoint: PhaseCheckpoint | None) -> str:
    if checkpoint and checkpoint.notes:
        return checkpoint.notes
    if phase.evidence and phase.evidence.changed_files:
        return "Changed files: " + ", ".join(phase.evidence.changed_files[:5])
    if phase.evidence and phase.evidence.notes:
        return phase.evidence.notes
    return "No change summary has been recorded yet."


def _next_safe_step(
    waiting_on: str,
    phase: Phase,
    checkpoint: PhaseCheckpoint | None,
    unresolved: list[str],
) -> str:
    if waiting_on == "you":
        label = checkpoint.title if checkpoint else phase.title
        return f"Answer the checkpoint question for {label}; the agent should not review or accept this phase yet."
    if unresolved:
        return "The agent should resolve the checkpoint gap, record proof, then run phase review."
    if phase.status == PhaseStatus.ACCEPTED:
        return "Move to the next phase."
    return "Run phase review, then accept the phase only if the review passes."


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
