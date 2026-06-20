from __future__ import annotations

from collections.abc import Sequence

from goals.checkpoints import checkpoint_waits_on_user, phase_checkpoint_blockers
from goals.criteria import criterion_cover_aliases, criterion_refs
from goals.models import (
    Evidence,
    GateFactType,
    GateFinding,
    GateResult,
    GateVerdict,
    Phase,
    Verification,
)


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
        no_evidence = GateFinding(
            fact_type=GateFactType.NO_EVIDENCE,
            message="Record phase evidence before review.",
        )
        return GateResult(
            gate_id="phase-review",
            verdict=_blocked_after_cap(capped_attempt, max_attempts),
            summary=_summary(
                "No evidence was recorded for this phase.", capped_attempt, max_attempts
            ),
            p0=[no_evidence.message],
            findings=[no_evidence],
            attempts=capped_attempt,
        )
    findings = _evidence_findings(phase, evidence, load_bearing)
    if findings:
        return GateResult(
            gate_id="phase-review",
            verdict=_blocked_after_cap(capped_attempt, max_attempts),
            summary=_summary(
                "Evidence is not verified by execution.", capped_attempt, max_attempts
            ),
            p0=[finding.message for finding in findings],
            findings=findings,
            attempts=capped_attempt,
        )
    return GateResult(
        gate_id="phase-review",
        verdict=GateVerdict.PASS,
        summary="Evidence is verified by executed checks.",
        attempts=capped_attempt,
    )


def _evidence_findings(
    phase: Phase,
    evidence: Evidence,
    load_bearing: Sequence[tuple[str, str]],
) -> list[GateFinding]:
    """Block unless the claims are backed by checks the engine ran and passed.

    Returns typed *facts* about the proof state — never human categories; the rubric
    (``goals.rubric``) maps facts to a vocabulary at read-time. Each fact's ``message``
    is verbatim, so ``GateResult.p0`` (derived from these) stays back-compatible.

    Two un-gameable requirements (the engine never decides *what* to test — the
    model does — it only insists the proof was executed, not narrated):
      1. every acceptance criterion is covered by a valid verification, and
      2. every load-bearing assumption has an ``auto`` falsifier that ran and passed
         — a test that would fail if the assumption were false.
    """
    findings: list[GateFinding] = []
    if evidence.acceptance_not_met:
        findings.append(
            GateFinding(
                fact_type=GateFactType.ACCEPTANCE_NOT_MET,
                message="Some acceptance criteria are explicitly not met.",
            )
        )
    if evidence.ambiguous:
        findings.append(
            GateFinding(
                fact_type=GateFactType.AMBIGUOUS,
                message="Some acceptance criteria are ambiguous.",
            )
        )

    verifications = evidence.verifications
    for v in verifications:
        if v.kind == "auto" and not v.command.strip():
            findings.append(
                GateFinding(
                    fact_type=GateFactType.VERIFICATION_UNRUNNABLE,
                    message=f"Auto verification {v.verification_id} has no command to run.",
                    ref=v.verification_id,
                )
            )
        if v.kind in {"manual", "production", "waived"} and not v.rationale.strip():
            findings.append(
                GateFinding(
                    fact_type=GateFactType.VERIFICATION_UNRUNNABLE,
                    message=(
                        f"{v.kind.title()} verification {v.verification_id} needs a rationale "
                        "(why local automated proof is not appropriate)."
                    ),
                    ref=v.verification_id,
                )
            )

    failed = [v for v in verifications if v.kind == "auto" and v.ran and not v.passed]
    for v in failed:
        findings.append(
            GateFinding(
                fact_type=GateFactType.CHECK_FAILED,
                message=f"Automated check {v.verification_id} ran and failed (covers {v.covers}).",
                ref=v.verification_id,
            )
        )

    if not any(_verification_counts_as_coverage(v) for v in verifications):
        # A check that ran and failed already carries the signal via CHECK_FAILED;
        # suppress the generic line so the CLI and the memory friction note do not
        # double-report. The no-check-ran case still emits it (preserving the gate's
        # prose-rejection guarantee).
        if not failed:
            findings.append(
                GateFinding(
                    fact_type=GateFactType.NO_PASSING_CHECK,
                    message=(
                        "No automated check has been executed and passed. Add a runnable check "
                        "and run `goals phase verify` (recorded notes are not proof)."
                    ),
                )
            )

    findings.extend(_criterion_coverage_findings(evidence, phase))

    for assumption_id, statement in load_bearing:
        if not any(
            v.covers.strip() == assumption_id and v.kind == "auto" and v.ran and v.passed
            for v in verifications
        ):
            findings.append(
                GateFinding(
                    fact_type=GateFactType.MISSING_FALSIFIER,
                    message=(
                        f"Load-bearing assumption has no passing falsifier "
                        f"({assumption_id}): {statement}"
                    ),
                    ref=assumption_id,
                )
            )

    return findings


def _criterion_coverage_findings(evidence: Evidence, phase: Phase) -> list[GateFinding]:
    findings: list[GateFinding] = []
    verifications = evidence.verifications
    for ref in criterion_refs(phase):
        aliases = criterion_cover_aliases(phase, ref)
        if any(_verification_counts_as_coverage(v) and v.covers.strip() in aliases for v in verifications):
            continue
        findings.append(
            GateFinding(
                fact_type=GateFactType.CRITERION_UNVERIFIED,
                message=(
                    f"Acceptance criterion {ref.criterion_id} has no valid verification: "
                    f"{ref.text}"
                ),
                ref=ref.criterion_id,
            )
        )
    return findings


def _verification_counts_as_coverage(v: Verification) -> bool:
    if v.kind == "auto":
        return v.ran and v.passed
    return bool(v.rationale.strip())


def _blocked_after_cap(attempt: int, max_attempts: int) -> GateVerdict:
    return GateVerdict.BLOCKED if attempt >= max_attempts else GateVerdict.FAIL


def _summary(base: str, attempt: int, max_attempts: int) -> str:
    if attempt >= max_attempts:
        return f"{base} Review-fix cap reached; ask for help or change approach."
    return base
