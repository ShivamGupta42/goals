from __future__ import annotations

from pathlib import Path

from goals.models import (
    AssetProvenanceFinding,
    AssetProvenanceReport,
    AssetRecord,
    GoalSnapshot,
)


def analyze_asset_provenance(snapshot: GoalSnapshot) -> AssetProvenanceReport:
    source_ids = {source.source_id for source in snapshot.sources}
    findings: list[AssetProvenanceFinding] = []
    for asset in snapshot.assets:
        refs = [f"asset:{asset.asset_id}"]
        if not asset.locator:
            findings.append(
                _finding(
                    asset,
                    "p1",
                    "Asset has no locator.",
                    "Record a repo-relative path, public URL, or stable asset id so reviewers can inspect it.",
                    refs,
                )
            )
        elif _looks_like_local_path(asset.locator):
            findings.append(
                _finding(
                    asset,
                    "p1",
                    "Asset locator may expose a local machine path.",
                    "Replace the locator with a repo-relative path or sanitized external reference before publishing.",
                    refs,
                    detail=f"locator={asset.locator}",
                )
            )
        missing_sources = [
            source_id for source_id in asset.source_ids if source_id not in source_ids
        ]
        if missing_sources:
            findings.append(
                _finding(
                    asset,
                    "p1",
                    "Asset references missing source evidence.",
                    "Record the missing source or remove the stale source id before relying on the asset.",
                    [*refs, *(f"source:{source_id}" for source_id in missing_sources)],
                    detail=", ".join(missing_sources),
                )
            )
        if asset.origin in {"stock", "external", "derived"} and not asset.license:
            findings.append(
                _finding(
                    asset,
                    "p1",
                    "Asset license is missing.",
                    "Record the license or replace the asset with one that has clear usage rights.",
                    refs,
                )
            )
        if asset.origin == "generated":
            if not asset.creator_tool:
                findings.append(
                    _finding(
                        asset,
                        "p2",
                        "Generated asset is missing the creator tool.",
                        "Record the model, plugin, or tool used to generate the asset.",
                        refs,
                    )
                )
            if not asset.prompt:
                findings.append(
                    _finding(
                        asset,
                        "p2",
                        "Generated asset is missing the generation prompt.",
                        "Record a sanitized prompt or prompt summary so the asset can be reviewed later.",
                        refs,
                    )
                )
        if asset.usage_rights == "unknown" and asset.origin in {"stock", "external", "derived"}:
            findings.append(
                _finding(
                    asset,
                    "p1",
                    "Asset usage rights are unknown.",
                    "Confirm usage rights or choose a replacement before using the asset in a deliverable.",
                    refs,
                )
            )
        elif asset.usage_rights == "restricted":
            findings.append(
                _finding(
                    asset,
                    "p1",
                    "Asset has restricted usage rights.",
                    "Ask whether the restriction is acceptable for this goal, or replace the asset.",
                    refs,
                    needs_user=True,
                )
            )
        elif asset.usage_rights == "blocked":
            findings.append(
                _finding(
                    asset,
                    "p0",
                    "Asset usage is blocked.",
                    "Do not use this asset unless the user explicitly provides different rights evidence.",
                    refs,
                    needs_user=True,
                )
            )
    blocking = [finding for finding in findings if finding.severity in {"p0", "p1"}]
    return AssetProvenanceReport(
        goal_id=snapshot.goal_id,
        passed=not blocking,
        summary=(
            f"Checked {len(snapshot.assets)} asset(s): "
            f"{len([finding for finding in findings if finding.severity == 'p0'])} blocked, "
            f"{len([finding for finding in findings if finding.severity == 'p1'])} important, "
            f"{len([finding for finding in findings if finding.severity == 'p2'])} advisory."
        ),
        findings=findings,
        user_questions=[finding.summary for finding in findings if finding.needs_user],
        agent_actions=[
            finding.suggested_action
            for finding in findings
            if finding.suggested_action and not finding.needs_user
        ],
    )


def render_asset_summary(snapshot: GoalSnapshot) -> str:
    if not snapshot.assets:
        return "- No assets recorded yet."
    return "\n".join(_asset_line(asset) for asset in snapshot.assets[:8])


def render_asset_provenance_report(report: AssetProvenanceReport) -> str:
    lines = [
        "# Asset Provenance Report",
        "",
        f"Goal: {report.goal_id}",
        f"Overall: {'pass' if report.passed else 'needs attention'}",
        "",
        report.summary,
        "",
        "## Needs The User",
        _bullets(report.user_questions or ["No asset provenance decision is waiting on the user."]),
        "",
        "## Agent Can Work On",
        _bullets(report.agent_actions or ["No asset provenance cleanup is currently suggested."]),
        "",
        "## Findings",
    ]
    if not report.findings:
        lines.append("- No asset provenance issues found.")
    for finding in report.findings:
        marker = " user" if finding.needs_user else ""
        lines.append(
            f"- [{finding.severity.upper()}{marker}] {finding.asset_id}: {finding.summary}"
        )
        if finding.detail:
            lines.append(f"  Detail: {finding.detail}")
        if finding.suggested_action:
            lines.append(f"  Next: {finding.suggested_action}")
    return "\n".join(lines) + "\n"


def _finding(
    asset: AssetRecord,
    severity: str,
    summary: str,
    suggested_action: str,
    refs: list[str],
    *,
    detail: str = "",
    needs_user: bool = False,
) -> AssetProvenanceFinding:
    return AssetProvenanceFinding(
        severity=severity,  # type: ignore[arg-type]
        asset_id=asset.asset_id,
        title=asset.title,
        summary=f"{summary.rstrip('.')}: {asset.title}",
        detail=detail,
        suggested_action=suggested_action,
        needs_user=needs_user,
        evidence_refs=refs,
    )


def _looks_like_local_path(locator: str) -> bool:
    if not locator:
        return False
    if locator.startswith(("http://", "https://")):
        return False
    path = Path(locator).expanduser()
    return path.is_absolute() or locator.startswith("~")


def _asset_line(asset: AssetRecord) -> str:
    locator = f" `{asset.locator}`" if asset.locator else ""
    rights = f", rights={asset.usage_rights}"
    license_text = f", license={asset.license}" if asset.license else ""
    return (
        f"- {asset.asset_id}: {asset.title}{locator} "
        f"({asset.asset_type}, {asset.origin}{rights}{license_text})"
    )


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items)
