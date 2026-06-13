from __future__ import annotations

from goals.models import Evidence, GateResult, GateVerdict, Phase


def review_phase(phase: Phase, *, attempt: int = 1, max_attempts: int = 3) -> GateResult:
    capped_attempt = max(1, min(attempt, max_attempts))
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
