from pathlib import Path

from goals.creative import analyze_creative_variants, render_creative_comparison_report
from goals.models import (
    AssetRecord,
    CreativeVariant,
    CreativeVariantScore,
    GoalSnapshot,
    SourceRecord,
    WorktreeLease,
)
from goals.runtime import default_phases


def snapshot_with_variants(
    tmp_path: Path,
    variants: list[CreativeVariant],
    assets: list[AssetRecord] | None = None,
) -> GoalSnapshot:
    return GoalSnapshot(
        goal_id="demo",
        objective="Create campaign concepts",
        topology=WorktreeLease(
            base_repo=str(tmp_path),
            base_branch="main",
            worktree_path=str(tmp_path),
            branch="goal/demo",
        ),
        phases=default_phases("Create campaign concepts"),
        current_phase="P1",
        assets=assets or [],
        creative_variants=variants,
        sources=[
            SourceRecord(
                source_id="SRC-brand",
                title="Brand note",
                source_type="document",
                summary="Brand direction note.",
            )
        ],
    )


def test_creative_comparison_passes_and_recommends_selected_variant(tmp_path: Path) -> None:
    snapshot = snapshot_with_variants(
        tmp_path,
        [
            CreativeVariant(
                title="Calm launch",
                summary="Quiet launch direction.",
                best_for="trust-building",
                status="selected",
                source_ids=["SRC-brand"],
                scores=[
                    CreativeVariantScore(
                        criterion="brand_fit",
                        score=5,
                        rationale="Matches voice.",
                    )
                ],
                strengths=["Clear and calm."],
            ),
            CreativeVariant(
                title="Bold launch",
                summary="Louder campaign direction.",
                best_for="awareness",
                status="rejected",
                scores=[CreativeVariantScore(criterion="brand_fit", score=3)],
                risks=["May feel too loud."],
            ),
        ],
    )

    report = analyze_creative_variants(snapshot)
    rendered = render_creative_comparison_report(report)

    assert report.passed is True
    assert report.recommended_variant_id == snapshot.creative_variants[0].variant_id
    assert report.user_questions == []
    assert "Creative Variant Comparison" in rendered
    assert "Overall: pass" in rendered


def test_creative_comparison_flags_missing_scores_and_references(tmp_path: Path) -> None:
    snapshot = snapshot_with_variants(
        tmp_path,
        [
            CreativeVariant(
                title="Option A",
                summary="First option.",
                best_for="fast draft",
                asset_ids=["AST-missing"],
            ),
            CreativeVariant(title="Option B"),
        ],
    )

    report = analyze_creative_variants(snapshot)

    assert report.passed is False
    assert report.user_questions == []
    assert any("no comparison scores" in finding.summary for finding in report.findings)
    assert any("missing assets" in finding.summary for finding in report.findings)
    assert any("missing a summary" in finding.summary for finding in report.findings)
    assert any("Score this variant" in action for action in report.agent_actions)


def test_creative_comparison_surfaces_restricted_or_blocked_assets(tmp_path: Path) -> None:
    restricted = AssetRecord(
        asset_id="AST-restricted",
        title="Restricted logo",
        locator="assets/logo.png",
        asset_type="image",
        origin="external",
        license="Vendor license",
        usage_rights="restricted",
    )
    blocked = AssetRecord(
        asset_id="AST-blocked",
        title="Blocked photo",
        locator="assets/photo.png",
        asset_type="image",
        origin="external",
        license="Do not use",
        usage_rights="blocked",
    )
    snapshot = snapshot_with_variants(
        tmp_path,
        [
            CreativeVariant(
                title="Logo-led concept",
                summary="Uses the partner logo.",
                best_for="partner launch",
                asset_ids=[restricted.asset_id],
                scores=[CreativeVariantScore(criterion="brand_fit", score=4)],
                status="selected",
            ),
            CreativeVariant(
                title="Photo-led concept",
                summary="Uses the blocked photo.",
                best_for="visual punch",
                asset_ids=[blocked.asset_id],
                scores=[CreativeVariantScore(criterion="brand_fit", score=5)],
                status="shortlisted",
            ),
        ],
        assets=[restricted, blocked],
    )

    report = analyze_creative_variants(snapshot)

    assert report.passed is False
    assert any("restricted asset" in question for question in report.user_questions)
    assert any("blocked asset" in question for question in report.user_questions)
    assert any(finding.severity == "p0" for finding in report.findings)


def test_creative_comparison_is_quiet_until_variants_exist(tmp_path: Path) -> None:
    snapshot = snapshot_with_variants(tmp_path, [])

    report = analyze_creative_variants(snapshot)

    assert report.passed is True
    assert report.findings == []
    assert report.recommended_variant_id is None
