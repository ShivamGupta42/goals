from __future__ import annotations

from goals.models import (
    AssetRecord,
    CreativeVariant,
    CreativeVariantComparisonReport,
    CreativeVariantFinding,
    GoalSnapshot,
)


def analyze_creative_variants(snapshot: GoalSnapshot) -> CreativeVariantComparisonReport:
    variants = snapshot.creative_variants
    findings: list[CreativeVariantFinding] = []
    asset_by_id = {asset.asset_id: asset for asset in snapshot.assets}
    source_ids = {source.source_id for source in snapshot.sources}
    compare_mode = len(variants) > 1

    for variant in variants:
        refs = [f"creative:{variant.variant_id}"]
        if not variant.summary:
            findings.append(
                _finding(
                    variant,
                    "p2",
                    "Creative variant is missing a summary.",
                    "Add a plain summary so non-technical reviewers can compare it.",
                    refs,
                )
            )
        if not variant.best_for:
            findings.append(
                _finding(
                    variant,
                    "p2",
                    "Creative variant is missing a best-for note.",
                    "Record when this variant is the right choice.",
                    refs,
                )
            )
        if compare_mode and not variant.scores:
            findings.append(
                _finding(
                    variant,
                    "p1",
                    "Creative variant has no comparison scores.",
                    "Score this variant against explicit criteria before selecting a direction.",
                    refs,
                )
            )
        missing_assets = [asset_id for asset_id in variant.asset_ids if asset_id not in asset_by_id]
        if missing_assets:
            findings.append(
                _finding(
                    variant,
                    "p1",
                    "Creative variant references missing assets.",
                    "Record the missing assets or remove stale asset ids before review.",
                    [*refs, *(f"asset:{asset_id}" for asset_id in missing_assets)],
                    detail=", ".join(missing_assets),
                )
            )
        missing_sources = [
            source_id for source_id in variant.source_ids if source_id not in source_ids
        ]
        if missing_sources:
            findings.append(
                _finding(
                    variant,
                    "p1",
                    "Creative variant references missing sources.",
                    "Record the missing source evidence or remove stale source ids before review.",
                    [*refs, *(f"source:{source_id}" for source_id in missing_sources)],
                    detail=", ".join(missing_sources),
                )
            )
        findings.extend(_asset_rights_findings(variant, asset_by_id, refs))

    selected = [variant for variant in variants if variant.status == "selected"]
    if len(selected) > 1:
        findings.append(
            CreativeVariantFinding(
                severity="p1",
                variant_id="multiple",
                title="Multiple selected variants",
                summary="More than one creative variant is marked selected.",
                suggested_action="Keep one selected variant and mark the others shortlisted or rejected.",
                evidence_refs=[f"creative:{variant.variant_id}" for variant in selected],
            )
        )
    elif (
        compare_mode
        and not selected
        and not any(variant.status == "shortlisted" for variant in variants)
    ):
        findings.append(
            CreativeVariantFinding(
                severity="p2",
                variant_id="comparison",
                title="No shortlisted variant",
                summary="No creative variant has been shortlisted or selected yet.",
                suggested_action="Shortlist the best current variant or record why more exploration is needed.",
                evidence_refs=[f"creative:{variant.variant_id}" for variant in variants],
            )
        )

    recommended = _recommended_variant(variants)
    blocking = [finding for finding in findings if finding.severity in {"p0", "p1"}]
    return CreativeVariantComparisonReport(
        goal_id=snapshot.goal_id,
        passed=not blocking,
        variants_compared=len(variants),
        recommended_variant_id=recommended.variant_id if recommended is not None else None,
        summary=_summary(variants, findings, recommended),
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


def render_creative_summary(snapshot: GoalSnapshot) -> str:
    if not snapshot.creative_variants:
        return "- No creative variants recorded yet."
    return "\n".join(_variant_line(variant) for variant in snapshot.creative_variants[:8])


def render_creative_comparison_report(report: CreativeVariantComparisonReport) -> str:
    lines = [
        "# Creative Variant Comparison",
        "",
        f"Goal: {report.goal_id}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        "",
        report.summary,
        "",
        f"Recommended variant: {report.recommended_variant_id or 'none'}",
        "",
        "## Needs The User",
        _bullets(
            report.user_questions or ["No important creative decision is waiting on the user."]
        ),
        "",
        "## Agent Can Work On",
        _bullets(
            report.agent_actions or ["No creative comparison cleanup is currently suggested."]
        ),
        "",
        "## Findings",
    ]
    if not report.findings:
        lines.append("- No creative comparison issues found.")
    for finding in report.findings:
        marker = " user" if finding.needs_user else ""
        lines.append(
            f"- [{finding.severity.upper()}{marker}] {finding.variant_id}: {finding.summary}"
        )
        if finding.detail:
            lines.append(f"  Detail: {finding.detail}")
        if finding.suggested_action:
            lines.append(f"  Next: {finding.suggested_action}")
    return "\n".join(lines) + "\n"


def _asset_rights_findings(
    variant: CreativeVariant,
    asset_by_id: dict[str, AssetRecord],
    refs: list[str],
) -> list[CreativeVariantFinding]:
    findings: list[CreativeVariantFinding] = []
    if variant.status == "rejected":
        return findings
    needs_user = variant.status in {"selected", "shortlisted"}
    for asset_id in variant.asset_ids:
        asset = asset_by_id.get(asset_id)
        if asset is None:
            continue
        asset_refs = [*refs, f"asset:{asset.asset_id}"]
        if asset.usage_rights == "blocked":
            action = (
                "Replace the asset or ask the user for explicit rights evidence before using this direction."
                if needs_user
                else "Reject this variant or replace the blocked asset before shortlisting it."
            )
            findings.append(
                _finding(
                    variant,
                    "p0" if needs_user else "p1",
                    "Creative direction includes a blocked asset.",
                    action,
                    asset_refs,
                    detail=f"{asset.title} is marked blocked.",
                    needs_user=needs_user,
                )
            )
        elif asset.usage_rights == "restricted":
            action = (
                "Ask whether this usage restriction is acceptable, or choose another variant."
                if needs_user
                else "Do not shortlist this variant until the restriction is acceptable or the asset is replaced."
            )
            findings.append(
                _finding(
                    variant,
                    "p1",
                    "Creative direction includes a restricted asset.",
                    action,
                    asset_refs,
                    detail=f"{asset.title} is marked restricted.",
                    needs_user=needs_user,
                )
            )
        elif asset.usage_rights == "unknown" and asset.origin in {"stock", "external", "derived"}:
            findings.append(
                _finding(
                    variant,
                    "p1",
                    "Creative direction has unclear asset rights.",
                    "Confirm asset rights or replace the asset before selecting this variant.",
                    asset_refs,
                    detail=f"{asset.title} has unknown rights.",
                )
            )
    return findings


def _recommended_variant(variants: list[CreativeVariant]) -> CreativeVariant | None:
    if not variants:
        return None
    selected = [variant for variant in variants if variant.status == "selected"]
    if len(selected) == 1:
        return selected[0]
    shortlisted = [variant for variant in variants if variant.status == "shortlisted"]
    pool = shortlisted or variants
    return sorted(
        pool,
        key=lambda variant: (
            _score_average(variant),
            len(variant.strengths),
            -len(variant.risks),
        ),
        reverse=True,
    )[0]


def _score_average(variant: CreativeVariant) -> float:
    if not variant.scores:
        return 0.0
    return sum(score.score for score in variant.scores) / len(variant.scores)


def _summary(
    variants: list[CreativeVariant],
    findings: list[CreativeVariantFinding],
    recommended: CreativeVariant | None,
) -> str:
    if not variants:
        return "No creative variants are recorded yet. This is fine until the goal explores creative directions."
    p0 = len([finding for finding in findings if finding.severity == "p0"])
    p1 = len([finding for finding in findings if finding.severity == "p1"])
    p2 = len([finding for finding in findings if finding.severity == "p2"])
    selected = len([variant for variant in variants if variant.status == "selected"])
    recommendation = (
        f" Recommended current direction: {recommended.title}." if recommended is not None else ""
    )
    return (
        f"Compared {len(variants)} creative variant(s): {selected} selected, "
        f"{p0} blocked, {p1} important, {p2} advisory issue(s)."
        f"{recommendation}"
    )


def _finding(
    variant: CreativeVariant,
    severity: str,
    summary: str,
    suggested_action: str,
    refs: list[str],
    *,
    detail: str = "",
    needs_user: bool = False,
) -> CreativeVariantFinding:
    return CreativeVariantFinding(
        severity=severity,  # type: ignore[arg-type]
        variant_id=variant.variant_id,
        title=variant.title,
        summary=f"{summary.rstrip('.')}: {variant.title}",
        detail=detail,
        suggested_action=suggested_action,
        needs_user=needs_user,
        evidence_refs=refs,
    )


def _variant_line(variant: CreativeVariant) -> str:
    score = f", score={_score_average(variant):.1f}/5" if variant.scores else ""
    best_for = f", best for {variant.best_for}" if variant.best_for else ""
    assets = f", assets={', '.join(variant.asset_ids)}" if variant.asset_ids else ""
    return f"- {variant.variant_id}: {variant.title} ({variant.status}{score}{best_for}{assets})"


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
