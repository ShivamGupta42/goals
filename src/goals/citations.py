from __future__ import annotations

import re

from goals.models import (
    CitationQualityFinding,
    CitationQualityReport,
    GoalSnapshot,
    SourceClaim,
    SourceRecord,
)

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
ABSOLUTE_TERMS = {
    "always",
    "certainly",
    "guaranteed",
    "guarantees",
    "never",
    "proves",
    "undeniable",
}


def analyze_citation_quality(snapshot: GoalSnapshot) -> CitationQualityReport:
    """Check whether source-backed claims are traceable and appropriately qualified."""

    source_index = {source.source_id: source for source in snapshot.sources}
    high_stakes = _high_stakes_context(snapshot)
    findings: list[CitationQualityFinding] = []

    for claim in snapshot.source_claims:
        refs = _claim_refs(claim)
        known_sources = [
            source_index[source_id] for source_id in claim.source_ids if source_id in source_index
        ]
        missing_sources = [
            source_id for source_id in claim.source_ids if source_id not in source_index
        ]
        needs_user = high_stakes and claim.confidence >= 0.7

        if not claim.source_ids:
            findings.append(
                _finding(
                    "p1",
                    claim,
                    "Claim has no citation.",
                    "Record a source for this claim, lower confidence, or remove the claim before relying on it.",
                    detail="No source ids are attached to the claim.",
                    needs_user=needs_user,
                    evidence_refs=refs,
                )
            )
        elif missing_sources:
            findings.append(
                _finding(
                    "p1",
                    claim,
                    "Claim cites missing source evidence.",
                    "Record the missing source or remove the stale source id before relying on this claim.",
                    detail=f"Missing source id(s): {', '.join(missing_sources)}.",
                    needs_user=needs_user,
                    evidence_refs=refs + [f"source:{source_id}" for source_id in missing_sources],
                )
            )

        if claim.confidence < 0.5:
            findings.append(
                _finding(
                    "p2",
                    claim,
                    "Claim confidence is low.",
                    "Gather stronger evidence, soften the claim, or mark it as uncertain.",
                    detail=f"confidence={claim.confidence:.0%}",
                    evidence_refs=refs,
                )
            )

        if (
            claim.confidence >= 0.8
            and known_sources
            and all(source.credibility == "low" for source in known_sources)
        ):
            findings.append(
                _finding(
                    "p1",
                    claim,
                    "High-confidence claim relies only on low-credibility sources.",
                    "Find stronger evidence or lower the claim confidence before presenting it as reliable.",
                    detail=f"Cited source id(s): {', '.join(claim.source_ids)}.",
                    needs_user=needs_user,
                    evidence_refs=refs,
                )
            )

        if _uses_absolute_language(claim.claim):
            findings.append(
                _finding(
                    "p2",
                    claim,
                    "Claim uses absolute language.",
                    "Soften the wording or add stronger evidence before using absolute terms.",
                    detail="Absolute language can overstate what the cited evidence proves.",
                    evidence_refs=refs,
                )
            )

    for source in _cited_sources(snapshot):
        source_refs = _source_claim_refs(snapshot, source.source_id)
        if not source.locator:
            findings.append(
                CitationQualityFinding(
                    severity="p1",
                    source_ids=[source.source_id],
                    summary=f"Cited source has no locator: {source.title}",
                    detail="Reviewers cannot inspect the citation without a URL, file name, interview id, or stable source locator.",
                    suggested_action="Add a stable locator or replace the source before relying on its claims.",
                    evidence_refs=[f"source:{source.source_id}", *source_refs],
                )
            )
        if not source.summary:
            findings.append(
                CitationQualityFinding(
                    severity="p2",
                    source_ids=[source.source_id],
                    summary=f"Cited source has no summary: {source.title}",
                    detail="A short summary helps non-technical users understand why the source supports the claim.",
                    suggested_action="Add a one-sentence summary before presenting the cited claim.",
                    evidence_refs=[f"source:{source.source_id}", *source_refs],
                )
            )
        if source.source_type == "url" and source.locator and not _looks_like_url(source.locator):
            findings.append(
                CitationQualityFinding(
                    severity="p2",
                    source_ids=[source.source_id],
                    summary=f"URL source locator is not a URL: {source.title}",
                    detail=f"locator={source.locator}",
                    suggested_action="Use an https URL or change the source type if this is not a web source.",
                    evidence_refs=[f"source:{source.source_id}", *source_refs],
                )
            )

    blocking = [finding for finding in findings if finding.severity in {"p0", "p1"}]
    user_questions = [finding.summary for finding in findings if finding.needs_user]
    agent_actions = _unique(
        [
            finding.suggested_action
            for finding in findings
            if finding.suggested_action and not finding.needs_user
        ]
    )
    return CitationQualityReport(
        goal_id=snapshot.goal_id,
        passed=not blocking,
        summary=(
            f"Checked {len(snapshot.source_claims)} source-backed claim(s): "
            f"{len([finding for finding in findings if finding.severity == 'p1'])} important, "
            f"{len([finding for finding in findings if finding.severity == 'p2'])} advisory."
        ),
        findings=findings,
        user_questions=user_questions,
        agent_actions=agent_actions,
    )


def render_citation_quality_summary(snapshot: GoalSnapshot) -> str:
    if not snapshot.source_claims:
        return "- No citations to review yet."
    report = analyze_citation_quality(snapshot)
    if not report.findings:
        return f"- {report.summary}"
    return "\n".join(
        f"- {finding.severity.upper()}: {finding.summary}" for finding in report.findings[:6]
    )


def render_citation_quality_report(report: CitationQualityReport) -> str:
    lines = [
        "# Citation Quality Report",
        "",
        f"Goal: {report.goal_id}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        "",
        report.summary,
        "",
        "## Needs The User",
        _bullets(report.user_questions or ["No citation quality decision is waiting on the user."]),
        "",
        "## Agent Can Work On",
        _bullets(report.agent_actions or ["No citation cleanup is currently suggested."]),
        "",
        "## Findings",
    ]
    if not report.findings:
        lines.append("- No citation quality issues found.")
    for finding in report.findings:
        marker = " user" if finding.needs_user else ""
        target = finding.claim or ", ".join(finding.source_ids)
        lines.append(f"- [{finding.severity.upper()}{marker}] {target}: {finding.summary}")
        if finding.detail:
            lines.append(f"  Detail: {finding.detail}")
        if finding.source_ids:
            lines.append(f"  Sources: {', '.join(finding.source_ids)}")
        if finding.suggested_action:
            lines.append(f"  Next: {finding.suggested_action}")
    return "\n".join(lines) + "\n"


def _finding(
    severity: str,
    claim: SourceClaim,
    summary: str,
    suggested_action: str,
    *,
    detail: str = "",
    needs_user: bool = False,
    evidence_refs: list[str] | None = None,
) -> CitationQualityFinding:
    return CitationQualityFinding(
        severity=severity,  # type: ignore[arg-type]
        claim=claim.claim,
        source_ids=claim.source_ids,
        summary=f"{summary.rstrip('.')}: {claim.claim}",
        detail=detail,
        suggested_action=(
            "Ask whether to proceed with weak high-stakes citation evidence, or find stronger evidence first."
            if needs_user
            else suggested_action
        ),
        needs_user=needs_user,
        evidence_refs=evidence_refs or _claim_refs(claim),
    )


def _cited_sources(snapshot: GoalSnapshot) -> list[SourceRecord]:
    source_ids = {source_id for claim in snapshot.source_claims for source_id in claim.source_ids}
    return [source for source in snapshot.sources if source.source_id in source_ids]


def _source_claim_refs(snapshot: GoalSnapshot, source_id: str) -> list[str]:
    return [
        f"claim:{_slug(claim.claim)}"
        for claim in snapshot.source_claims
        if source_id in claim.source_ids
    ]


def _claim_refs(claim: SourceClaim) -> list[str]:
    refs = [f"claim:{_slug(claim.claim)}"]
    refs.extend(f"source:{source_id}" for source_id in claim.source_ids)
    return refs


def _high_stakes_context(snapshot: GoalSnapshot) -> bool:
    text = " ".join(
        [
            snapshot.objective,
            snapshot.why,
            *snapshot.definition_of_done,
            *snapshot.risks,
            *(claim.claim for claim in snapshot.source_claims),
        ]
    ).lower()
    return any(term in text for term in HIGH_STAKES_TERMS)


def _uses_absolute_language(claim: str) -> bool:
    words = set(re.findall(r"[a-z]+", claim.lower()))
    return bool(words & ABSOLUTE_TERMS)


def _looks_like_url(locator: str) -> bool:
    return locator.startswith(("https://", "http://"))


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48] or "claim"


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        unique.append(item)
    return unique


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
