from __future__ import annotations

from goals.models import GoalSnapshot, SourceClaim, SourceRecord


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


def _source_line(source: SourceRecord) -> str:
    locator = f" `{source.locator}`" if source.locator else ""
    summary = f" - {source.summary}" if source.summary else ""
    return f"- {source.source_id}: {source.title}{locator} ({source.credibility}){summary}"


def _claim_line(claim: SourceClaim) -> str:
    source_ids = ", ".join(claim.source_ids) if claim.source_ids else "no source"
    return f"- {claim.claim} [{source_ids}] confidence={claim.confidence:.0%}"
