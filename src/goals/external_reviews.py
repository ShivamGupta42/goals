from __future__ import annotations

from goals.boundaries import detect_professional_domains
from goals.models import (
    ExternalReview,
    ExternalReviewFinding,
    ExternalReviewReport,
    GoalSnapshot,
)


HIGH_STAKES_REVIEW_DOMAINS = {
    "medical",
    "legal",
    "financial",
    "safety",
    "security",
    "compliance",
    "privacy",
    "production",
}


def analyze_external_reviews(snapshot: GoalSnapshot) -> ExternalReviewReport:
    reviews = snapshot.external_reviews
    phase_ids = {phase.phase_id for phase in snapshot.phases}
    high_stakes_domains = _high_stakes_domains(snapshot)
    findings: list[ExternalReviewFinding] = []

    if high_stakes_domains and not reviews:
        findings.append(
            ExternalReviewFinding(
                severity="p0",
                review_id="missing",
                title="External review required",
                summary="External review is required before high-stakes work is accepted.",
                detail=f"Detected high-stakes domain(s): {', '.join(high_stakes_domains)}.",
                suggested_action=(
                    "Ask the user who should review this work, or narrow the goal to a safe "
                    "information-organizing artifact before continuing."
                ),
                needs_user=True,
                evidence_refs=[f"external-review:{domain}" for domain in high_stakes_domains],
            )
        )

    for review in reviews:
        refs = [f"external-review:{review.review_id}"]
        missing_phases = [phase_id for phase_id in review.phase_ids if phase_id not in phase_ids]
        if missing_phases:
            findings.append(
                _finding(
                    review,
                    "p1",
                    "External review references unknown phases.",
                    "Remove stale phase ids or update the goal phases before review.",
                    [*refs, *(f"phase:{phase_id}" for phase_id in missing_phases)],
                    detail=", ".join(missing_phases),
                )
            )
        if not review.scope:
            findings.append(
                _finding(
                    review,
                    "p1",
                    "External review is missing its scope.",
                    "Record what the reviewer is checking so the review is auditable.",
                    refs,
                )
            )

        if review.status in {"required", "requested"}:
            if not review.reviewer:
                findings.append(
                    _finding(
                        review,
                        "p1",
                        "External reviewer needs to be chosen.",
                        "Ask the user to name the reviewer or confirm the review route.",
                        refs,
                        needs_user=True,
                    )
                )
            if not review.summary:
                findings.append(
                    _finding(
                        review,
                        "p1",
                        "External review request is missing a plain summary.",
                        "Record the requested review and what is still waiting.",
                        refs,
                    )
                )
        elif review.status == "passed":
            if not review.summary:
                findings.append(
                    _finding(
                        review,
                        "p1",
                        "Passed external review has no summary.",
                        "Record what the reviewer approved in plain language.",
                        refs,
                    )
                )
            if not review.evidence_refs:
                findings.append(
                    _finding(
                        review,
                        "p1",
                        "Passed external review has no evidence reference.",
                        "Attach the review note, approval link, checklist, or evidence id.",
                        refs,
                    )
                )
        elif review.status == "failed":
            findings.append(
                _finding(
                    review,
                    "p0",
                    "External review failed.",
                    "Ask the user whether to revise, stop, or explicitly waive the review risk.",
                    refs,
                    needs_user=True,
                )
            )
        elif review.status == "blocked":
            findings.append(
                _finding(
                    review,
                    "p0",
                    "External review is blocked.",
                    "Ask the user for a reviewer, escalation path, or safer narrowed scope.",
                    refs,
                    needs_user=True,
                )
            )
        elif review.status == "waived":
            if review.risk_domain in HIGH_STAKES_REVIEW_DOMAINS:
                findings.append(
                    _finding(
                        review,
                        "p0",
                        "High-stakes external review was waived.",
                        "Ask the user to confirm the waiver and record why proceeding is acceptable.",
                        refs,
                        needs_user=True,
                    )
                )
            elif not review.waiver_reason:
                findings.append(
                    _finding(
                        review,
                        "p1",
                        "External review waiver needs a reason.",
                        "Record why review was waived and what makes the decision reversible.",
                        refs,
                    )
                )

    blocking = [finding for finding in findings if finding.severity in {"p0", "p1"}]
    return ExternalReviewReport(
        goal_id=snapshot.goal_id,
        passed=not blocking,
        reviews_checked=len(reviews),
        high_stakes_domains=high_stakes_domains,
        summary=_summary(reviews, findings, high_stakes_domains),
        findings=findings,
        user_questions=[finding.summary for finding in findings if finding.needs_user],
        agent_actions=_unique(
            [
                finding.suggested_action
                for finding in findings
                if finding.suggested_action and not finding.needs_user
            ]
        ),
    )


def render_external_review_summary(snapshot: GoalSnapshot) -> str:
    if not snapshot.external_reviews:
        return "- No external reviews recorded yet."
    return "\n".join(_review_line(review) for review in snapshot.external_reviews[:8])


def render_external_review_report(report: ExternalReviewReport) -> str:
    lines = [
        "# External Review Report",
        "",
        f"Goal: {report.goal_id}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        "",
        report.summary,
        "",
        "## Needs The User",
        _bullets(report.user_questions or ["No external review decision is waiting on the user."]),
        "",
        "## Agent Can Work On",
        _bullets(report.agent_actions or ["No external review cleanup is currently suggested."]),
        "",
        "## Findings",
    ]
    if not report.findings:
        lines.append("- No external review issues found.")
    for finding in report.findings:
        marker = " user" if finding.needs_user else ""
        lines.append(
            f"- [{finding.severity.upper()}{marker}] {finding.review_id}: {finding.summary}"
        )
        if finding.detail:
            lines.append(f"  Detail: {finding.detail}")
        if finding.suggested_action:
            lines.append(f"  Next: {finding.suggested_action}")
    return "\n".join(lines) + "\n"


def _summary(
    reviews: list[ExternalReview],
    findings: list[ExternalReviewFinding],
    high_stakes_domains: list[str],
) -> str:
    if not reviews and high_stakes_domains:
        return (
            "No external review is recorded for high-stakes domain(s): "
            + ", ".join(high_stakes_domains)
            + "."
        )
    if not reviews:
        return "No external reviews are recorded yet. This is fine until work touches high-stakes, regulated, production, security, or irreversible decisions."
    p0 = len([finding for finding in findings if finding.severity == "p0"])
    p1 = len([finding for finding in findings if finding.severity == "p1"])
    p2 = len([finding for finding in findings if finding.severity == "p2"])
    passed = len([review for review in reviews if review.status == "passed"])
    waiting = len([review for review in reviews if review.status in {"required", "requested"}])
    return (
        f"Checked {len(reviews)} external review(s): {passed} passed, "
        f"{waiting} waiting, {p0} blocked, {p1} important, {p2} advisory issue(s)."
    )


def _finding(
    review: ExternalReview,
    severity: str,
    summary: str,
    suggested_action: str,
    refs: list[str],
    *,
    detail: str = "",
    needs_user: bool = False,
) -> ExternalReviewFinding:
    return ExternalReviewFinding(
        severity=severity,  # type: ignore[arg-type]
        review_id=review.review_id,
        title=review.title,
        summary=f"{summary.rstrip('.')}: {review.title}",
        detail=detail,
        suggested_action=suggested_action,
        needs_user=needs_user,
        evidence_refs=refs,
    )


def _review_line(review: ExternalReview) -> str:
    phases = f", phases={', '.join(review.phase_ids)}" if review.phase_ids else ""
    scope = f", scope={', '.join(review.scope)}" if review.scope else ""
    reviewer = f", reviewer={review.reviewer}" if review.reviewer else ""
    return (
        f"- {review.review_id}: {review.title} "
        f"({review.risk_domain}, {review.status}, {review.reviewer_type}{reviewer}{phases}{scope})"
    )


def _high_stakes_domains(snapshot: GoalSnapshot) -> list[str]:
    text = " ".join(
        [
            snapshot.objective,
            snapshot.why,
            *snapshot.definition_of_done,
            *snapshot.risks,
            *(claim.claim for claim in snapshot.source_claims),
        ]
    )
    domains = set(detect_professional_domains(text))
    domains.update(
        review.risk_domain
        for review in snapshot.external_reviews
        if review.risk_domain in HIGH_STAKES_REVIEW_DOMAINS
    )
    return sorted(domains)


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique
