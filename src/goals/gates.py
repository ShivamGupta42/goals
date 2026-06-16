from __future__ import annotations

from collections.abc import Sequence

from goals.checkpoints import checkpoint_waits_on_user, phase_checkpoint_blockers
from goals.models import Evidence, GateResult, GateVerdict, Phase


def review_phase(
    phase: Phase,
    *,
    load_bearing: Sequence[tuple[str, str]] = (),
    attempt: int = 1,
    max_attempts: int = 3,
) -> GateResult:
    """Gate a phase on *executed* proof, not narrated proof.

    ``load_bearing`` is the phase's load-bearing assumptions as ``(id, statement)``
    pairs (supplied by the caller, which has the snapshot). A phase passes only when
    its acceptance criteria and load-bearing assumptions are each backed by a
    verification the engine actually ran and that passed — see ``_evidence_issues``.
    """
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
    issues = _evidence_issues(evidence, load_bearing)
    if issues:
        return GateResult(
            gate_id="phase-review",
            verdict=_blocked_after_cap(capped_attempt, max_attempts),
            summary=_summary(
                "Evidence is not verified by execution.", capped_attempt, max_attempts
            ),
            p0=issues,
            attempts=capped_attempt,
        )
    return GateResult(
        gate_id="phase-review",
        verdict=GateVerdict.PASS,
        summary="Evidence is verified by executed checks.",
        attempts=capped_attempt,
    )


def _evidence_issues(
    evidence: Evidence,
    load_bearing: Sequence[tuple[str, str]],
) -> list[str]:
    """Block unless the claims are backed by checks the engine ran and passed.

    Two un-gameable requirements (the engine never decides *what* to test — the
    model does — it only insists the proof was executed, not narrated):
      1. at least one ``auto`` verification actually ran and passed, so a phase can
         never be accepted on prose alone, and
      2. every load-bearing assumption has an ``auto`` falsifier that ran and passed
         — a test that would fail if the assumption were false.
    """
    issues: list[str] = []
    if evidence.acceptance_not_met:
        issues.append("Some acceptance criteria are explicitly not met.")
    if evidence.ambiguous:
        issues.append("Some acceptance criteria are ambiguous.")

    verifications = evidence.verifications
    for v in verifications:
        if v.kind == "auto" and not v.command.strip():
            issues.append(f"Auto verification {v.verification_id} has no command to run.")
        if v.kind == "manual" and not v.rationale.strip():
            issues.append(
                f"Manual verification {v.verification_id} needs a rationale "
                "(why it cannot be automated)."
            )

    if not any(v.kind == "auto" and v.ran and v.passed for v in verifications):
        issues.append(
            "No automated check has been executed and passed. Add a runnable check "
            "and run `goals phase verify` (recorded notes are not proof)."
        )

    for assumption_id, statement in load_bearing:
        if not any(
            v.covers.strip() == assumption_id and v.kind == "auto" and v.ran and v.passed
            for v in verifications
        ):
            issues.append(
                f"Load-bearing assumption has no passing falsifier ({assumption_id}): {statement}"
            )

    return issues


def _blocked_after_cap(attempt: int, max_attempts: int) -> GateVerdict:
    return GateVerdict.BLOCKED if attempt >= max_attempts else GateVerdict.FAIL


def _summary(base: str, attempt: int, max_attempts: int) -> str:
    if attempt >= max_attempts:
        return f"{base} Review-fix cap reached; ask for help or change approach."
    return base
