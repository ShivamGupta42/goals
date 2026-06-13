from __future__ import annotations

from datetime import datetime, timezone

from goals.models import (
    GoalSnapshot,
    SourceClaim,
    SourceFreshnessFinding,
    SourceFreshnessReport,
    SourceRecord,
)

DEFAULT_FRESHNESS_DAYS = {
    "url": 180,
    "dataset": 365,
    "document": 365,
    "file": 365,
    "interview": 540,
    "observation": 180,
    "other": 365,
}
HIGH_STAKES_TERMS = {
    "billing",
    "compliance",
    "financial",
    "health",
    "legal",
    "medical",
    "money",
    "privacy",
    "production",
    "regulatory",
    "safety",
}


def render_source_summary(snapshot: GoalSnapshot) -> str:
    if not snapshot.sources:
        return "- No sources recorded yet."
    return "\n".join(_source_line(source) for source in snapshot.sources[:8])


def render_claim_summary(snapshot: GoalSnapshot) -> str:
    if not snapshot.source_claims:
        return "- No source-backed claims recorded yet."
    return "\n".join(_claim_line(claim) for claim in snapshot.source_claims[:8])


def unresolved_claims(snapshot: GoalSnapshot) -> list[SourceClaim]:
    source_ids = {source.source_id for source in snapshot.sources}
    return [
        claim
        for claim in snapshot.source_claims
        if not claim.source_ids
        or any(source_id not in source_ids for source_id in claim.source_ids)
    ]


def analyze_source_freshness(
    snapshot: GoalSnapshot,
    *,
    max_age_days: int | None = None,
    now: datetime | None = None,
) -> SourceFreshnessReport:
    """Check whether recorded sources are fresh enough for claims that rely on them."""

    now = now or datetime.now(timezone.utc)
    claim_index = _claim_index(snapshot)
    findings: list[SourceFreshnessFinding] = []
    high_stakes = _high_stakes_context(snapshot)
    for source in snapshot.sources:
        threshold = max_age_days or DEFAULT_FRESHNESS_DAYS.get(
            source.source_type,
            DEFAULT_FRESHNESS_DAYS["other"],
        )
        refs = claim_index.get(source.source_id, [])
        parsed = _parse_timestamp(source.added_at)
        if parsed is None:
            findings.append(
                SourceFreshnessFinding(
                    severity="p1",
                    source_id=source.source_id,
                    title=source.title,
                    source_type=source.source_type,
                    summary=f"Source freshness cannot be checked: {source.title}",
                    detail=f"Added-at timestamp is not valid ISO-8601: {source.added_at}",
                    max_age_days=threshold,
                    claim_refs=refs,
                    suggested_action="Re-record this source with a valid timestamp or manually verify it before relying on it.",
                    evidence_refs=[f"source:{source.source_id}"],
                )
            )
            continue
        age_days = max((now - parsed).days, 0)
        if age_days <= threshold:
            continue
        needs_user = high_stakes and _supports_confident_claim(snapshot, source.source_id)
        findings.append(
            SourceFreshnessFinding(
                severity="p1" if refs else "p2",
                source_id=source.source_id,
                title=source.title,
                source_type=source.source_type,
                summary=f"Source may be stale: {source.title}",
                detail=(
                    f"Recorded {age_days} day(s) ago; freshness window is "
                    f"{threshold} day(s) for {source.source_type} sources."
                ),
                age_days=age_days,
                max_age_days=threshold,
                claim_refs=refs,
                suggested_action=(
                    "Ask the user whether to proceed with stale high-stakes evidence, or refresh the source first."
                    if needs_user
                    else "Refresh, replace, or mark this source as stale before relying on related claims."
                ),
                needs_user=needs_user,
                evidence_refs=[f"source:{source.source_id}"],
            )
        )
    blocking = [finding for finding in findings if finding.severity in {"p0", "p1"}]
    user_questions = [finding.summary for finding in findings if finding.needs_user]
    agent_actions = [
        finding.suggested_action
        for finding in findings
        if finding.suggested_action and not finding.needs_user
    ]
    return SourceFreshnessReport(
        goal_id=snapshot.goal_id,
        passed=not blocking,
        summary=(
            f"Checked {len(snapshot.sources)} source(s): "
            f"{len([finding for finding in findings if finding.severity == 'p1'])} stale or unverifiable, "
            f"{len([finding for finding in findings if finding.severity == 'p2'])} advisory."
        ),
        findings=findings,
        user_questions=user_questions,
        agent_actions=agent_actions,
    )


def render_source_freshness_report(report: SourceFreshnessReport) -> str:
    lines = [
        "# Source Freshness Report",
        "",
        f"Goal: {report.goal_id}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        "",
        report.summary,
        "",
        "## Needs The User",
        _bullets(report.user_questions or ["No source freshness decision is waiting on the user."]),
        "",
        "## Agent Can Work On",
        _bullets(report.agent_actions or ["No source refresh action is currently suggested."]),
        "",
        "## Findings",
    ]
    if not report.findings:
        lines.append("- No stale or unverifiable sources found.")
    for finding in report.findings:
        marker = " user" if finding.needs_user else ""
        lines.append(
            f"- [{finding.severity.upper()}{marker}] {finding.source_id}: {finding.summary}"
        )
        if finding.detail:
            lines.append(f"  Detail: {finding.detail}")
        if finding.claim_refs:
            lines.append(f"  Claims: {', '.join(finding.claim_refs)}")
        if finding.suggested_action:
            lines.append(f"  Next: {finding.suggested_action}")
    return "\n".join(lines) + "\n"


def _source_line(source: SourceRecord) -> str:
    locator = f" `{source.locator}`" if source.locator else ""
    summary = f" - {source.summary}" if source.summary else ""
    return f"- {source.source_id}: {source.title}{locator} ({source.credibility}){summary}"


def _claim_line(claim: SourceClaim) -> str:
    source_ids = ", ".join(claim.source_ids) if claim.source_ids else "no source"
    return f"- {claim.claim} [{source_ids}] confidence={claim.confidence:.0%}"


def _claim_index(snapshot: GoalSnapshot) -> dict[str, list[str]]:
    claims: dict[str, list[str]] = {}
    for claim in snapshot.source_claims:
        for source_id in claim.source_ids:
            claims.setdefault(source_id, []).append(claim.claim)
    return claims


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _high_stakes_context(snapshot: GoalSnapshot) -> bool:
    text = " ".join([snapshot.objective, snapshot.why, " ".join(snapshot.risks)]).lower()
    return any(term in text for term in HIGH_STAKES_TERMS)


def _supports_confident_claim(snapshot: GoalSnapshot, source_id: str) -> bool:
    return any(
        source_id in claim.source_ids and claim.confidence >= 0.7
        for claim in snapshot.source_claims
    )


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
