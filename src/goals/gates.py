from __future__ import annotations

from goals.checkpoints import checkpoint_waits_on_user, phase_checkpoint_blockers
from goals.models import Evidence, GateResult, GateVerdict, Phase


def review_phase(phase: Phase, *, attempt: int = 1, max_attempts: int = 3) -> GateResult:
    capped_attempt = max(1, min(attempt, max_attempts))
    checkpoint_issues = phase_checkpoint_blockers(phase)
    if checkpoint_issues:
        needs_user = any(checkpoint_waits_on_user(checkpoint) for checkpoint in phase.checkpoints)
        return GateResult(
            gate_id="phase-review",
            verdict=GateVerdict.NEEDS_HUMAN
            if needs_user
            else _blocked_after_cap(capped_attempt, max_attempts),
            summary=_summary(
                "A required checkpoint is not complete.", capped_attempt, max_attempts
            ),
            p0=checkpoint_issues,
            attempts=capped_attempt,
        )
    evidence = phase.evidence
    if evidence is None:
        return GateResult(
            gate_id="phase-review",
            verdict=_blocked_after_cap(capped_attempt, max_attempts),
            summary=_summary(
                "No evidence was recorded for this phase.", capped_attempt, max_attempts
            ),
            p0=["Record phase evidence before review."],
            attempts=capped_attempt,
        )
    issues = _evidence_issues(evidence)
    if issues:
        return GateResult(
            gate_id="phase-review",
            verdict=_blocked_after_cap(capped_attempt, max_attempts),
            summary=_summary("Evidence is incomplete.", capped_attempt, max_attempts),
            p0=issues,
            attempts=capped_attempt,
        )
    return GateResult(
        gate_id="phase-review",
        verdict=GateVerdict.PASS,
        summary="Evidence satisfies the phase review gate.",
        attempts=capped_attempt,
    )


def _evidence_issues(evidence: Evidence) -> list[str]:
    issues: list[str] = []
    if evidence.acceptance_not_met:
        issues.append("Some acceptance criteria are explicitly not met.")
    if evidence.ambiguous:
        issues.append("Some acceptance criteria are ambiguous.")
    if evidence.confidence < 0.7:
        issues.append("Evidence confidence is below 0.7.")
    if not evidence.checks_run:
        issues.append("No checks or tests were recorded.")
    return issues


def _blocked_after_cap(attempt: int, max_attempts: int) -> GateVerdict:
    return GateVerdict.BLOCKED if attempt >= max_attempts else GateVerdict.FAIL


def _summary(base: str, attempt: int, max_attempts: int) -> str:
    if attempt >= max_attempts:
        return f"{base} Review-fix cap reached; ask for help or change approach."
    return base
